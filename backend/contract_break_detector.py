"""
ContractBreakDetector — Detects signature contract breaks via Signature_Hash comparison.

Requirements: 6.1, 6.3, 6.5, 10.5
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger("insightgraph")


class ContractBreakDetector:
    """
    Compares current Signature_Hash against the stored hash in Neo4j or memory_nodes.
    Marks contract_broken = True when hashes differ.

    Usage:
        detector = ContractBreakDetector(neo4j_service, memory_nodes)
        broken = detector.check_and_mark(ns_key, current_hash)
        all_broken = detector.get_all_broken()
    """

    # Confidence score for hash-based contract break detection (Requirement 6.5)
    CONTRACT_BREAK_CONFIDENCE = 95

    def __init__(self, neo4j_service, memory_nodes: list[dict]):
        """
        Args:
            neo4j_service: Neo4jService instance (may be disconnected).
            memory_nodes:  Reference to the global memory_nodes list.
        """
        self._neo4j = neo4j_service
        self._memory_nodes = memory_nodes

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    def check_and_mark(self, ns_key: str, current_hash: str) -> bool:
        """
        Compare current_hash with the stored signature_hash for ns_key.

        If they differ:
          - Sets contract_broken = True on the node
          - Saves previous_signature_hash
          - Updates signature_hash to current_hash

        Returns True if a contract break was detected, False otherwise.

        Requirements: 6.1, 6.5, 10.5
        """
        if not current_hash:
            return False

        stored_hash = self._get_stored_hash(ns_key)

        # No stored hash yet — first scan, just persist
        if stored_hash is None:
            self._update_node(ns_key, {"signature_hash": current_hash})
            return False

        if stored_hash == current_hash:
            return False

        # Hash changed → contract break
        props = {
            "contract_broken": True,
            "previous_signature_hash": stored_hash,
            "signature_hash": current_hash,
        }
        self._update_node(ns_key, props)
        logger.info(
            "Contract break detected for %s (confidence=%d)",
            ns_key,
            self.CONTRACT_BREAK_CONFIDENCE,
        )
        return True

    def get_all_broken(self) -> list[dict]:
        """
        Return all artefacts with contract_broken = True from the last scan.

        Tries Neo4j first; falls back to memory_nodes.

        Requirements: 6.3
        """
        if self._neo4j.is_connected:
            try:
                result = self._neo4j.graph.run(
                    "MATCH (n:Entity) WHERE n.contract_broken = true RETURN n"
                ).data()
                return [dict(row["n"]) for row in result]
            except Exception as e:
                logger.warning("Neo4j get_all_broken failed, using memory: %s", e)

        # Memory fallback
        return [
            node for node in self._memory_nodes
            if node.get("contract_broken") is True
        ]

    # ──────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────

    def _get_stored_hash(self, ns_key: str) -> str | None:
        """Retrieve the stored signature_hash for ns_key."""
        if self._neo4j.is_connected:
            try:
                result = self._neo4j.graph.run(
                    "MATCH (n:Entity {namespace_key: $key}) RETURN n.signature_hash AS h",
                    key=ns_key,
                ).data()
                if result:
                    return result[0].get("h")
            except Exception as e:
                logger.warning("Neo4j _get_stored_hash failed for %s: %s", ns_key, e)

        # Memory fallback
        for node in self._memory_nodes:
            if node.get("namespace_key") == ns_key:
                return node.get("signature_hash")
        return None

    def _update_node(self, ns_key: str, props: dict) -> None:
        """Update node properties in Neo4j and memory."""
        # Update memory
        for node in self._memory_nodes:
            if node.get("namespace_key") == ns_key:
                node.update(props)
                break

        # Update Neo4j
        if self._neo4j.is_connected:
            try:
                set_clause = ", ".join(f"n.{k} = ${k}" for k in props)
                self._neo4j.graph.run(
                    f"MATCH (n:Entity {{namespace_key: $ns_key}}) SET {set_clause}",
                    ns_key=ns_key,
                    **props,
                )
            except Exception as e:
                logger.warning("Neo4j _update_node failed for %s: %s", ns_key, e)
