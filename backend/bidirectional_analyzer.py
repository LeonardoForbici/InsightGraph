"""
BidirectionalAnalyzer — Orchestrates TaintPropagator, FragilityCalculator and SideEffectDetector
for bidirectional impact analysis (BOTTOM_UP and TOP_DOWN).

Requirements: 5.1–5.8
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("insightgraph")

# Relationships followed when building chains
_CHAIN_RELATIONSHIPS = {
    "CALLS",
    "CALLS_HTTP",
    "SERIALIZED_BY",
    "DISPLAYED_BY",
    "MAPPED_FROM",
}

# Layer ordering for BOTTOM_UP (database → angular)
_LAYER_ORDER_BOTTOM_UP = ["database", "procedure", "java", "typescript", "angular"]

# Layer ordering for TOP_DOWN (angular → database)
_LAYER_ORDER_TOP_DOWN = ["angular", "typescript", "java", "procedure", "database"]

# Timeout for bidirectional analysis (seconds)
_ANALYSIS_TIMEOUT = 15.0


@dataclass
class PropagationChainItem:
    node_key: str
    name: str
    layer: str
    data_type: str
    fragility_score: float
    precision_risk: bool
    side_effect_risk: bool


@dataclass
class BidirectionalResult:
    origin_key: str
    direction: str                          # "BOTTOM_UP" | "TOP_DOWN"
    chain: list[PropagationChainItem]
    taint_path: Optional[object]            # TaintPath | None
    side_effects: list                      # list[SideEffect]
    total_hops: int
    isolated: bool
    elapsed_seconds: float
    truncated: bool = False


class BidirectionalAnalyzer:
    """
    Orchestrates TaintPropagator, FragilityCalculator and SideEffectDetector
    for bidirectional impact analysis.

    Requirements: 5.1–5.8
    """

    def __init__(
        self,
        taint_propagator,
        symbol_resolver,
        side_effect_detector,
        fragility_calculator,
        impact_engine,
    ):
        self._taint_propagator = taint_propagator
        self._symbol_resolver = symbol_resolver
        self._side_effect_detector = side_effect_detector
        self._fragility_calculator = fragility_calculator
        self._impact_engine = impact_engine

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    async def analyze(
        self,
        origin_key: str,
        direction: str,
        change=None,
    ) -> BidirectionalResult:
        """
        Orchestrate TaintPropagator, FragilityCalculator and SideEffectDetector
        for a bidirectional analysis.

        Args:
            origin_key: namespace_key of the origin node
            direction:  "BOTTOM_UP" or "TOP_DOWN"
            change:     optional change descriptor dict

        Returns:
            BidirectionalResult — never raises HTTP 500.

        Requirements: 5.1, 5.2, 5.7, 5.8
        """
        start = time.monotonic()

        try:
            result = await asyncio.wait_for(
                self._analyze_inner(origin_key, direction, change, start),
                timeout=_ANALYSIS_TIMEOUT,
            )
            return result
        except asyncio.TimeoutError:
            # Return partial result with truncated=True (task 1.5.5)
            elapsed = time.monotonic() - start
            logger.warning(
                "BidirectionalAnalyzer: timeout after %.1fs for origin=%s direction=%s",
                elapsed,
                origin_key,
                direction,
            )
            # Build whatever partial chain we can synchronously
            try:
                if direction == "BOTTOM_UP":
                    partial_chain = self._build_bottom_up_chain(origin_key)
                else:
                    partial_chain = self._build_top_down_chain(origin_key)
            except Exception:
                partial_chain = []

            return BidirectionalResult(
                origin_key=origin_key,
                direction=direction,
                chain=partial_chain,
                taint_path=None,
                side_effects=[],
                total_hops=len(partial_chain),
                isolated=len(partial_chain) == 0,
                elapsed_seconds=time.monotonic() - start,
                truncated=True,
            )
        except Exception as e:
            # Never raise HTTP 500 — always return a valid BidirectionalResult (task 1.5.4)
            logger.error(
                "BidirectionalAnalyzer: unexpected error for origin=%s: %s",
                origin_key,
                e,
            )
            elapsed = time.monotonic() - start
            return BidirectionalResult(
                origin_key=origin_key,
                direction=direction,
                chain=[],
                taint_path=None,
                side_effects=[],
                total_hops=0,
                isolated=True,
                elapsed_seconds=elapsed,
                truncated=False,
            )

    # ──────────────────────────────────────────────
    # Inner async implementation
    # ──────────────────────────────────────────────

    async def _analyze_inner(
        self,
        origin_key: str,
        direction: str,
        change,
        start: float,
    ) -> BidirectionalResult:
        """Core analysis logic, wrapped by analyze() for timeout handling."""

        # Build propagation chain
        if direction == "BOTTOM_UP":
            chain = self._build_bottom_up_chain(origin_key)
        else:
            chain = self._build_top_down_chain(origin_key)

        # Isolated check (task 1.5.4)
        isolated = len(chain) == 0

        # Taint propagation (task 1.5.1)
        taint_path = None
        if change is not None:
            try:
                change_type = change.get("change_type", "") if isinstance(change, dict) else ""
                old_type = change.get("old_type", "") if isinstance(change, dict) else ""
                new_type = change.get("new_type", "") if isinstance(change, dict) else ""
                taint_path = self._taint_propagator.propagate(
                    origin_key, change_type, old_type, new_type
                )
            except Exception as e:
                logger.warning("BidirectionalAnalyzer: taint propagation failed: %s", e)

        # Fragility calculation for origin node (task 1.5.1)
        try:
            await self._fragility_calculator.calculate(origin_key)
        except Exception as e:
            logger.warning("BidirectionalAnalyzer: fragility calculation failed for %s: %s", origin_key, e)

        # Side effect detection (task 1.5.1)
        side_effects = []
        if change is not None:
            try:
                affected_set = [item.node_key for item in chain]
                side_effects = await self._side_effect_detector.detect(change, affected_set)
            except Exception as e:
                logger.warning("BidirectionalAnalyzer: side effect detection failed: %s", e)

        elapsed = time.monotonic() - start

        return BidirectionalResult(
            origin_key=origin_key,
            direction=direction,
            chain=chain,
            taint_path=taint_path,
            side_effects=side_effects,
            total_hops=len(chain),
            isolated=isolated,
            elapsed_seconds=elapsed,
            truncated=False,
        )

    # ──────────────────────────────────────────────
    # Chain builders
    # ──────────────────────────────────────────────

    def _build_bottom_up_chain(self, origin_key: str) -> list[PropagationChainItem]:
        """
        Follow outgoing relationships from origin_key toward the frontend.

        Traversal order: database → procedure → java → typescript → angular
        Relationships followed: CALLS, CALLS_HTTP, SERIALIZED_BY, DISPLAYED_BY, MAPPED_FROM

        Requirements: 5.1, 5.6
        """
        return self._build_chain(origin_key, outgoing=True, layer_order=_LAYER_ORDER_BOTTOM_UP)

    def _build_top_down_chain(self, origin_key: str) -> list[PropagationChainItem]:
        """
        Follow incoming relationships (reverse direction) from origin_key toward the database.

        Traversal order: angular → typescript → java → procedure → database
        Relationships followed (reversed): CALLS, CALLS_HTTP, SERIALIZED_BY, DISPLAYED_BY, MAPPED_FROM

        Requirements: 5.2, 5.3
        """
        return self._build_chain(origin_key, outgoing=False, layer_order=_LAYER_ORDER_TOP_DOWN)

    def _build_chain(
        self,
        origin_key: str,
        outgoing: bool,
        layer_order: list[str],
    ) -> list[PropagationChainItem]:
        """
        BFS over memory_edges to build a PropagationChain.

        Args:
            origin_key: starting node key
            outgoing:   True → follow source→target edges (BOTTOM_UP)
                        False → follow target→source edges (TOP_DOWN)
            layer_order: expected layer progression for ordering

        Returns:
            list[PropagationChainItem] ordered by layer_order
        """
        memory_edges: list = self._taint_propagator._memory_edges
        memory_nodes: dict = self._taint_propagator._memory_nodes

        visited: set[str] = {origin_key}
        # BFS queue
        from collections import deque
        queue: deque[str] = deque([origin_key])
        items: list[PropagationChainItem] = []

        while queue:
            current_key = queue.popleft()

            for edge in memory_edges:
                src = edge.get("from") or edge.get("source") or ""
                tgt = edge.get("to") or edge.get("target") or ""
                rel_type = edge.get("type") or ""

                if rel_type not in _CHAIN_RELATIONSHIPS:
                    continue

                if outgoing:
                    # Follow source → target
                    if src != current_key:
                        continue
                    neighbor_key = tgt
                else:
                    # Follow target → source (reverse)
                    if tgt != current_key:
                        continue
                    neighbor_key = src

                if not neighbor_key or neighbor_key in visited:
                    continue

                visited.add(neighbor_key)
                queue.append(neighbor_key)

                item = self._make_chain_item(neighbor_key, memory_nodes)
                items.append(item)

        # Sort by layer order
        layer_index = {layer: i for i, layer in enumerate(layer_order)}
        items.sort(key=lambda x: layer_index.get(x.layer, len(layer_order)))

        return items

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    def _make_chain_item(self, node_key: str, memory_nodes: dict) -> PropagationChainItem:
        """Build a PropagationChainItem for a given node_key."""
        node_data = memory_nodes.get(node_key, {})
        props = node_data.get("properties", node_data) if isinstance(node_data, dict) else {}
        labels = node_data.get("labels", []) if isinstance(node_data, dict) else []

        name = props.get("name") or node_key.split(":")[-1]
        data_type = props.get("data_type") or props.get("type") or ""
        file_path = props.get("file") or ""
        layer = self._taint_propagator._infer_layer(labels, file_path)

        # Fragility score from calculator cache (task 1.5.2 / 1.5.3)
        cached = self._fragility_calculator._cache.get(node_key)
        fragility_score = cached.fragility_score if cached is not None else 0.0

        # Side effect risk from node properties
        side_effect_risk = bool(props.get("side_effect_risk", False))

        return PropagationChainItem(
            node_key=node_key,
            name=name,
            layer=layer,
            data_type=data_type,
            fragility_score=fragility_score,
            precision_risk=False,
            side_effect_risk=side_effect_risk,
        )
