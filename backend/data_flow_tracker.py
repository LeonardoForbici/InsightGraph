"""
DataFlowTracker — Traces data flow from a DB column to the Angular frontend.

Chain: Column → Entity (MAPS_TO_COLUMN) → DTO (MAPPED_FROM) → Endpoint (SERIALIZED_BY) → Component (DISPLAYED_BY)

Requirements: 7.1–7.6
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("insightgraph")


@dataclass
class DataFlowLink:
    from_key: str
    to_key: str
    rel_type: str
    resolved: bool = True   # False = unresolved link


@dataclass
class DataFlowChain:
    column_key: str
    links: list[DataFlowLink] = field(default_factory=list)


# Ordered chain of relationship types to follow
_CHAIN_STEPS = [
    "MAPS_TO_COLUMN",   # Column → JPA field (Entity)
    "MAPPED_FROM",      # Entity field → DTO field
    "SERIALIZED_BY",    # DTO field → API Endpoint
    "DISPLAYED_BY",     # API Endpoint → Angular Component
]


class DataFlowTracker:
    """
    Traces the data flow path from a column (or any node) through the
    dependency graph up to the Angular frontend.

    Requirements: 7.1–7.6
    """

    def __init__(self, neo4j_service, memory_nodes: list[dict], memory_edges: list[dict]):
        self._neo4j = neo4j_service
        self._memory_nodes = memory_nodes
        self._memory_edges = memory_edges

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    def trace_column_to_frontend(self, column_key: str) -> DataFlowChain:
        """
        Trace the data flow chain starting from column_key.

        Follows: MAPS_TO_COLUMN → MAPPED_FROM → SERIALIZED_BY → DISPLAYED_BY

        Unresolved links are included with resolved=False without interrupting
        the chain.

        Requirements: 7.1–7.6
        """
        chain = DataFlowChain(column_key=column_key)

        if self._neo4j.is_connected:
            try:
                self._trace_neo4j(column_key, chain)
                return chain
            except Exception as e:
                logger.warning("Neo4j trace_column_to_frontend failed, using memory: %s", e)
                chain.links = []  # reset before memory fallback

        self._trace_memory(column_key, chain)
        return chain

    # ──────────────────────────────────────────────
    # Neo4j path
    # ──────────────────────────────────────────────

    def _trace_neo4j(self, start_key: str, chain: DataFlowChain) -> None:
        """Follow each step in _CHAIN_STEPS via Cypher, appending links."""
        current_key = start_key

        for rel_type in _CHAIN_STEPS:
            query = """
            MATCH (a:Entity {namespace_key: $key})-[r:""" + rel_type + """]->(b:Entity)
            RETURN b.namespace_key AS next_key
            LIMIT 1
            """
            rows = self._neo4j.graph.run(query, key=current_key).data()
            if rows and rows[0].get("next_key"):
                next_key = rows[0]["next_key"]
                chain.links.append(DataFlowLink(
                    from_key=current_key,
                    to_key=next_key,
                    rel_type=rel_type,
                    resolved=True,
                ))
                current_key = next_key
            else:
                # Unresolved link — record it but continue
                chain.links.append(DataFlowLink(
                    from_key=current_key,
                    to_key="unresolved",
                    rel_type=rel_type,
                    resolved=False,
                ))
                # Don't advance current_key; subsequent steps will also be unresolved

    # ──────────────────────────────────────────────
    # Memory fallback
    # ──────────────────────────────────────────────

    def _trace_memory(self, start_key: str, chain: DataFlowChain) -> None:
        """Follow each step in _CHAIN_STEPS over memory_edges."""
        # Build lookup: (source, rel_type) → target
        edge_lookup: dict[tuple[str, str], str] = {}
        for edge in self._memory_edges:
            src = edge.get("source") or edge.get("from")
            tgt = edge.get("target") or edge.get("to")
            rtype = edge.get("type", "")
            if src and tgt and rtype:
                # Keep first match per (src, rel_type)
                key = (src, rtype)
                if key not in edge_lookup:
                    edge_lookup[key] = tgt

        current_key = start_key
        for rel_type in _CHAIN_STEPS:
            next_key = edge_lookup.get((current_key, rel_type))
            if next_key:
                chain.links.append(DataFlowLink(
                    from_key=current_key,
                    to_key=next_key,
                    rel_type=rel_type,
                    resolved=True,
                ))
                current_key = next_key
            else:
                chain.links.append(DataFlowLink(
                    from_key=current_key,
                    to_key="unresolved",
                    rel_type=rel_type,
                    resolved=False,
                ))
