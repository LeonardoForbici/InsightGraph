"""
ImpactEngine — BFS-based impact analysis over the dependency graph.

Requirements: 4.1–4.8, 5.1–5.4, 11.1–11.6
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Literal, Optional

logger = logging.getLogger("insightgraph")

# ──────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────

Category = Literal["DIRECT", "TRANSITIVE", "INFERRED"]
ResolutionMethod = Literal["exact_key", "qualified_name", "heuristic", "semantic"]


@dataclass
class AffectedItem:
    namespace_key: str
    name: str
    labels: list[str]
    category: Category
    confidence_score: int          # 0–100
    call_chain: list[str]          # ordered from target_key to this item
    requires_manual_review: bool   # True when confidence_score < 40
    resolution_method: ResolutionMethod = "exact_key"


@dataclass
class AnalysisMetadata:
    total_affected: int = 0
    high_confidence_count: int = 0   # score >= 70
    low_confidence_count: int = 0    # score < 70
    parse_errors: list[str] = field(default_factory=list)
    unresolved_links: list[str] = field(default_factory=list)
    semantic_analysis_available: bool = False
    truncated: bool = False
    elapsed_seconds: float = 0.0


@dataclass
class AffectedSet:
    items: list[AffectedItem]
    analysis_metadata: AnalysisMetadata


# ──────────────────────────────────────────────
# ChangeDescriptor (also used by REST layer)
# ──────────────────────────────────────────────

@dataclass
class ChangeDescriptor:
    change_type: str   # rename_parameter | change_column_type | change_method_signature | change_procedure_param
    target_key: str
    parameter_name: Optional[str] = None
    old_type: Optional[str] = None
    new_type: Optional[str] = None
    max_depth: int = 5


# Relationship types relevant per change_type
_REL_TYPES_BY_CHANGE: dict[str, list[str]] = {
    "rename_parameter":        ["HAS_PARAMETER", "CALLS", "CALLS_RESOLVED", "CALLS_NHOP", "HAS_METHOD"],
    "change_column_type":      ["READS_COLUMN", "WRITES_COLUMN", "MAPS_TO_COLUMN", "HAS_FIELD", "CALLS_HTTP", "DISPLAYED_BY", "CALLS_NHOP"],
    "change_method_signature": ["CALLS", "CALLS_RESOLVED", "CALLS_NHOP", "HAS_METHOD", "CONSUMES_API"],
    "change_procedure_param":  ["HAS_PARAMETER", "CALLS", "CALLS_RESOLVED", "CALLS_NHOP", "CONSUMES_API", "CALLS_HTTP"],
}
_DEFAULT_REL_TYPES = ["CALLS", "CALLS_RESOLVED", "CALLS_NHOP", "HAS_METHOD", "HAS_PARAMETER", "CONSUMES_API"]

MAX_NODES = 50_000


class ImpactEngine:
    """
    Calculates the Affected_Set for a given ChangeDescriptor by performing
    BFS over the dependency graph (Neo4j or memory fallback).

    Requirements: 4.1–4.8, 5.1–5.4, 11.1–11.6
    """

    def __init__(self, neo4j_service, memory_nodes: list[dict], memory_edges: list[dict]):
        self._neo4j = neo4j_service
        self._memory_nodes = memory_nodes
        self._memory_edges = memory_edges

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    def analyze(self, change: ChangeDescriptor) -> AffectedSet:
        """
        Orchestrate impact analysis for a ChangeDescriptor.

        Requirements: 4.1–4.8, 11.5
        """
        start = time.monotonic()
        rel_types = _REL_TYPES_BY_CHANGE.get(change.change_type, _DEFAULT_REL_TYPES)

        items, truncated = self._bfs_impact(
            start_key=change.target_key,
            rel_types=rel_types,
            max_depth=change.max_depth,
        )

        # Assign categories and confidence
        for item in items:
            depth = len(item.call_chain) - 1  # 0-based depth from target
            if depth == 1:
                item.category = "DIRECT"
            elif depth <= change.max_depth // 2:
                item.category = "TRANSITIVE"
            else:
                item.category = "INFERRED"

        high = sum(1 for i in items if i.confidence_score >= 70)
        low = sum(1 for i in items if i.confidence_score < 70)

        metadata = AnalysisMetadata(
            total_affected=len(items),
            high_confidence_count=high,
            low_confidence_count=low,
            truncated=truncated,
            elapsed_seconds=round(time.monotonic() - start, 3),
        )

        return AffectedSet(items=items, analysis_metadata=metadata)

    # ──────────────────────────────────────────────
    # BFS
    # ──────────────────────────────────────────────

    def _bfs_impact(
        self,
        start_key: str,
        rel_types: list[str],
        max_depth: int,
    ) -> tuple[list[AffectedItem], bool]:
        """
        BFS from start_key following rel_types up to max_depth levels.

        Returns (affected_items, truncated).

        Requirements: 4.1–4.5, 4.8, 5.1, 5.2
        """
        if self._neo4j.is_connected:
            try:
                return self._bfs_neo4j(start_key, rel_types, max_depth)
            except Exception as e:
                logger.warning("Neo4j BFS failed, falling back to memory: %s", e)

        return self._bfs_memory(start_key, rel_types, max_depth)

    def _bfs_neo4j(
        self,
        start_key: str,
        rel_types: list[str],
        max_depth: int,
    ) -> tuple[list[AffectedItem], bool]:
        """BFS using Cypher APOC-free variable-length path query."""
        rel_filter = "|".join(rel_types)
        query = f"""
        MATCH path = (start:Entity {{namespace_key: $start_key}})-[:{rel_filter}*1..{max_depth}]->(affected:Entity)
        RETURN
            affected.namespace_key AS ns_key,
            affected.name          AS name,
            labels(affected)       AS labels,
            [n IN nodes(path) | n.namespace_key] AS chain
        LIMIT {MAX_NODES}
        """
        rows = self._neo4j.graph.run(query, start_key=start_key).data()
        truncated = len(rows) >= MAX_NODES

        items: list[AffectedItem] = []
        seen: set[str] = set()
        for row in rows:
            ns_key = row.get("ns_key")
            if not ns_key or ns_key == start_key or ns_key in seen:
                continue
            seen.add(ns_key)
            chain = list(row.get("chain") or [])
            if not chain or chain[0] != start_key:
                chain = [start_key] + chain

            score = self._compute_confidence(ns_key, "exact_key")
            items.append(AffectedItem(
                namespace_key=ns_key,
                name=row.get("name") or ns_key.split(":")[-1],
                labels=list(row.get("labels") or []),
                category="DIRECT",  # will be overwritten in analyze()
                confidence_score=score,
                call_chain=chain,
                requires_manual_review=score < 40,
                resolution_method="exact_key",
            ))

        return items, truncated

    def _bfs_memory(
        self,
        start_key: str,
        rel_types: list[str],
        max_depth: int,
    ) -> tuple[list[AffectedItem], bool]:
        """BFS over memory_edges."""
        rel_types_set = set(rel_types)

        # Build adjacency: source → list of (target, rel_type)
        adj: dict[str, list[tuple[str, str]]] = {}
        for edge in self._memory_edges:
            src = edge.get("source") or edge.get("from")
            tgt = edge.get("target") or edge.get("to")
            rtype = edge.get("type", "")
            if src and tgt and rtype in rel_types_set:
                adj.setdefault(src, []).append((tgt, rtype))

        # Build node lookup
        node_lookup: dict[str, dict] = {
            n["namespace_key"]: n
            for n in self._memory_nodes
            if n.get("namespace_key")
        }

        # BFS
        queue: deque[tuple[str, list[str], int]] = deque()
        queue.append((start_key, [start_key], 0))
        visited: set[str] = {start_key}
        items: list[AffectedItem] = []
        truncated = False

        while queue:
            if len(visited) >= MAX_NODES:
                truncated = True
                break

            current_key, chain, depth = queue.popleft()
            if depth >= max_depth:
                continue

            for (neighbor, _rtype) in adj.get(current_key, []):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                new_chain = chain + [neighbor]

                node_data = node_lookup.get(neighbor, {})
                raw_labels = node_data.get("labels", [])
                labels = [raw_labels] if isinstance(raw_labels, str) else list(raw_labels)

                score = self._compute_confidence(neighbor, "exact_key")
                items.append(AffectedItem(
                    namespace_key=neighbor,
                    name=node_data.get("name") or neighbor.split(":")[-1],
                    labels=labels,
                    category="DIRECT",  # overwritten in analyze()
                    confidence_score=score,
                    call_chain=new_chain,
                    requires_manual_review=score < 40,
                    resolution_method="exact_key",
                ))
                queue.append((neighbor, new_chain, depth + 1))

        return items, truncated

    # ──────────────────────────────────────────────
    # Confidence scoring
    # ──────────────────────────────────────────────

    def _compute_confidence(
        self,
        ns_key: str,
        resolution_method: ResolutionMethod,
    ) -> int:
        """
        Return Confidence_Score based on resolution method.

        exact_key      → 100
        qualified_name → 70–99  (use 85 as midpoint)
        heuristic      → 40–69  (use 55 as midpoint)
        semantic       → 0–39   (use 25 as midpoint)

        Requirements: 4.6, 11.1–11.4
        """
        if resolution_method == "exact_key":
            return 100
        if resolution_method == "qualified_name":
            return 85
        if resolution_method == "heuristic":
            return 55
        # semantic
        return 25
