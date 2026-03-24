"""
SymbolResolver — Resolves the exact identity of symbols using Type_Context from the AST,
avoiding confusion between homonymous methods in distinct modules.

Requirements: 2.1–2.7
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("insightgraph")


@dataclass
class TypeContext:
    declaring_class: str
    param_types: list[str]
    return_type: str
    module: str


@dataclass
class ResolvedSymbol:
    namespace_key: str
    name: str
    type_context: TypeContext
    resolution_method: str          # "exact_key" | "qualified_name" | "heuristic"
    confidence_score: int
    semantic_conflicts: list[str]   # namespace_keys of homonyms


class SymbolResolver:
    """
    Resolves symbol identity using Type_Context from the AST.

    Uses Neo4j when available; falls back to memory_nodes.

    Requirements: 2.1–2.7
    """

    def __init__(self, neo4j_service, memory_nodes: dict, deep_parser):
        """
        Args:
            neo4j_service: Neo4j service with `.driver` attribute and `.query(cypher, params)` method.
                           May be None to force in-memory fallback.
            memory_nodes:  dict {node_key: {"labels": [...], "properties": {...}}}
            deep_parser:   DeepParser instance for AST extraction.
        """
        self._neo4j = neo4j_service
        self._memory_nodes: dict = memory_nodes or {}
        self._deep_parser = deep_parser

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    def resolve(self, name: str, context_key: str = "") -> list[ResolvedSymbol]:
        """
        Search for all nodes with the given name in Neo4j first, then memory.
        If context_key is provided, prioritize symbols in the same module/namespace.

        Returns list of ResolvedSymbol, each with a unique namespace_key.

        Requirements: 2.1, 2.5, 2.6
        """
        results: list[ResolvedSymbol] = []
        seen_keys: set[str] = set()

        # ── 1. Neo4j search ───────────────────────────────────────────────────
        neo4j_symbols = self._search_neo4j_by_name(name)
        for sym in neo4j_symbols:
            if sym.namespace_key not in seen_keys:
                seen_keys.add(sym.namespace_key)
                results.append(sym)

        # ── 2. Memory fallback ────────────────────────────────────────────────
        memory_symbols = self._search_memory_by_name(name)
        for sym in memory_symbols:
            if sym.namespace_key not in seen_keys:
                seen_keys.add(sym.namespace_key)
                results.append(sym)

        # ── 3. Prioritize symbols in the same module/namespace as context_key ─
        if context_key and results:
            context_module = self._extract_module_from_key(context_key)
            same_module = [s for s in results if s.type_context.module == context_module]
            other_module = [s for s in results if s.type_context.module != context_module]
            results = same_module + other_module

        return results

    def detect_conflicts(self, name: str) -> list[ResolvedSymbol]:
        """
        Find all symbols with the same name but different modules/namespaces.
        Returns list of ResolvedSymbol with semantic_conflicts populated
        (list of other namespace_keys with same name).

        Requirements: 2.2, 2.7
        """
        all_symbols = self.resolve(name)

        # Group by module
        by_module: dict[str, list[ResolvedSymbol]] = {}
        for sym in all_symbols:
            mod = sym.type_context.module
            by_module.setdefault(mod, []).append(sym)

        # Only symbols that appear in more than one module are conflicts
        if len(by_module) <= 1:
            return []

        all_keys = [sym.namespace_key for sym in all_symbols]
        conflicts: list[ResolvedSymbol] = []

        for sym in all_symbols:
            other_keys = [k for k in all_keys if k != sym.namespace_key]
            sym.semantic_conflicts = other_keys
            conflicts.append(sym)

        # Persist conflicts to Neo4j
        if conflicts:
            self._persist_semantic_conflicts(conflicts)

        return conflicts

    # ──────────────────────────────────────────────
    # Private helpers — AST
    # ──────────────────────────────────────────────

    def _extract_type_context_from_ast(self, node_key: str) -> Optional[TypeContext]:
        """
        Use DeepParser to extract AST info for the node.
        Extracts declaring_class, param_types, return_type from the AST.
        Returns None if AST extraction fails.

        Requirements: 2.1, 2.4
        """
        try:
            # Resolve node properties from Neo4j or memory
            node_props = self._get_node_properties(node_key)
            if node_props is None:
                return None

            source_code = node_props.get("source_code") or node_props.get("source") or ""
            file_path = node_props.get("file") or ""
            declaring_class = node_props.get("declaring_class") or node_props.get("class_name") or ""
            module = self._extract_module_from_key(node_key)

            # Try to extract param_types and return_type from stored properties first
            param_types_raw = node_props.get("param_types") or node_props.get("parameter_types") or []
            if isinstance(param_types_raw, str):
                param_types = [t.strip() for t in param_types_raw.split(",") if t.strip()]
            else:
                param_types = list(param_types_raw)

            return_type = node_props.get("return_type") or node_props.get("returnType") or "void"

            # If we have source code, try to enrich via DeepParser signature hash
            if source_code and self._deep_parser is not None:
                try:
                    name = node_props.get("name") or node_key.split(".")[-1]
                    # compute_signature_hash validates the param/return combination
                    self._deep_parser.compute_signature_hash(name, param_types, return_type)
                except Exception as e:
                    logger.debug("SymbolResolver: signature hash failed for %s: %s", node_key, e)

            return TypeContext(
                declaring_class=declaring_class,
                param_types=param_types,
                return_type=return_type,
                module=module,
            )

        except Exception as e:
            logger.warning("SymbolResolver: _extract_type_context_from_ast failed for %s: %s", node_key, e)
            return None

    # ──────────────────────────────────────────────
    # Private helpers — PL/SQL
    # ──────────────────────────────────────────────

    def _resolve_plsql_procedure(
        self,
        schema: str,
        package: str,
        proc_name: str,
    ) -> Optional[ResolvedSymbol]:
        """
        Build composite key: `{schema}.{package}.{proc_name}` (or `{schema}.{proc_name}` if no package).
        Search Neo4j/memory for a Procedure node matching this composite key.
        Returns ResolvedSymbol with resolution_method="exact_key" if found.

        Requirements: 2.3
        """
        if package:
            composite_key = f"{schema}.{package}.{proc_name}"
        else:
            composite_key = f"{schema}.{proc_name}"

        # Try Neo4j first
        sym = self._search_neo4j_by_key(composite_key)
        if sym is not None:
            return sym

        # Try memory
        sym = self._search_memory_by_key(composite_key)
        if sym is not None:
            return sym

        # Try case-insensitive variants (PL/SQL is case-insensitive)
        composite_key_upper = composite_key.upper()
        composite_key_lower = composite_key.lower()

        for key_variant in (composite_key_upper, composite_key_lower):
            sym = self._search_memory_by_key(key_variant)
            if sym is not None:
                return sym

        return None

    # ──────────────────────────────────────────────
    # Private helpers — Neo4j
    # ──────────────────────────────────────────────

    def _use_neo4j(self) -> bool:
        return (
            self._neo4j is not None
            and getattr(self._neo4j, "is_connected", False)
        )

    def _neo4j_query(self, cypher: str, params: dict) -> list[dict]:
        """Run a Cypher query, trying .query() then .graph.run() fallback."""
        try:
            return self._neo4j.query(cypher, params)
        except Exception:
            try:
                return self._neo4j.graph.run(cypher, **params).data()
            except Exception as e:
                logger.warning("SymbolResolver: Neo4j query failed: %s", e)
                return []

    def _search_neo4j_by_name(self, name: str) -> list[ResolvedSymbol]:
        """Search Neo4j for all nodes with the given name."""
        if not self._use_neo4j():
            return []
        try:
            cypher = """
            MATCH (n {name: $name})
            RETURN
                n.namespace_key AS namespace_key,
                n.name AS name,
                labels(n) AS labels,
                n.file AS file,
                n.module AS module,
                n.declaring_class AS declaring_class,
                n.param_types AS param_types,
                n.return_type AS return_type,
                n.resolution_method AS resolution_method,
                n.confidence_score AS confidence_score,
                n.semantic_conflicts AS semantic_conflicts
            """
            rows = self._neo4j_query(cypher, {"name": name})
            return [self._row_to_resolved_symbol(row) for row in rows if row.get("namespace_key")]
        except Exception as e:
            logger.warning("SymbolResolver: _search_neo4j_by_name failed for %s: %s", name, e)
            return []

    def _search_neo4j_by_key(self, namespace_key: str) -> Optional[ResolvedSymbol]:
        """Search Neo4j for a node with the given namespace_key."""
        if not self._use_neo4j():
            return None
        try:
            cypher = """
            MATCH (n {namespace_key: $key})
            RETURN
                n.namespace_key AS namespace_key,
                n.name AS name,
                labels(n) AS labels,
                n.file AS file,
                n.module AS module,
                n.declaring_class AS declaring_class,
                n.param_types AS param_types,
                n.return_type AS return_type,
                n.resolution_method AS resolution_method,
                n.confidence_score AS confidence_score,
                n.semantic_conflicts AS semantic_conflicts
            LIMIT 1
            """
            rows = self._neo4j_query(cypher, {"key": namespace_key})
            if rows:
                return self._row_to_resolved_symbol(rows[0])
        except Exception as e:
            logger.warning("SymbolResolver: _search_neo4j_by_key failed for %s: %s", namespace_key, e)
        return None

    def _row_to_resolved_symbol(self, row: dict) -> ResolvedSymbol:
        """Convert a Neo4j result row to a ResolvedSymbol."""
        namespace_key = row.get("namespace_key") or ""
        name = row.get("name") or namespace_key.split(".")[-1]
        file_path = row.get("file") or ""
        module = row.get("module") or self._extract_module_from_key(namespace_key)
        declaring_class = row.get("declaring_class") or ""

        param_types_raw = row.get("param_types") or []
        if isinstance(param_types_raw, str):
            param_types = [t.strip() for t in param_types_raw.split(",") if t.strip()]
        else:
            param_types = list(param_types_raw)

        return_type = row.get("return_type") or "void"
        resolution_method = row.get("resolution_method") or "qualified_name"
        confidence_score = int(row.get("confidence_score") or 80)

        conflicts_raw = row.get("semantic_conflicts") or []
        if isinstance(conflicts_raw, str):
            semantic_conflicts = [c.strip() for c in conflicts_raw.split(",") if c.strip()]
        else:
            semantic_conflicts = list(conflicts_raw)

        return ResolvedSymbol(
            namespace_key=namespace_key,
            name=name,
            type_context=TypeContext(
                declaring_class=declaring_class,
                param_types=param_types,
                return_type=return_type,
                module=module,
            ),
            resolution_method=resolution_method,
            confidence_score=confidence_score,
            semantic_conflicts=semantic_conflicts,
        )

    # ──────────────────────────────────────────────
    # Private helpers — Memory
    # ──────────────────────────────────────────────

    def _search_memory_by_name(self, name: str) -> list[ResolvedSymbol]:
        """Search memory_nodes for all nodes with the given name."""
        results: list[ResolvedSymbol] = []
        for node_key, node_data in self._memory_nodes.items():
            props = node_data.get("properties") or {}
            node_name = props.get("name") or ""
            if node_name != name:
                continue
            sym = self._memory_node_to_resolved_symbol(node_key, node_data)
            results.append(sym)
        return results

    def _search_memory_by_key(self, namespace_key: str) -> Optional[ResolvedSymbol]:
        """Search memory_nodes for a node with the given namespace_key."""
        node_data = self._memory_nodes.get(namespace_key)
        if node_data is None:
            return None
        return self._memory_node_to_resolved_symbol(namespace_key, node_data)

    def _memory_node_to_resolved_symbol(self, node_key: str, node_data: dict) -> ResolvedSymbol:
        """Convert a memory node dict to a ResolvedSymbol."""
        props = node_data.get("properties") or {}
        name = props.get("name") or node_key.split(".")[-1]
        module = props.get("module") or self._extract_module_from_key(node_key)
        declaring_class = props.get("declaring_class") or props.get("class_name") or ""

        param_types_raw = props.get("param_types") or props.get("parameter_types") or []
        if isinstance(param_types_raw, str):
            param_types = [t.strip() for t in param_types_raw.split(",") if t.strip()]
        else:
            param_types = list(param_types_raw)

        return_type = props.get("return_type") or props.get("returnType") or "void"
        resolution_method = props.get("resolution_method") or "qualified_name"
        confidence_score = int(props.get("confidence_score") or 80)

        conflicts_raw = props.get("semantic_conflicts") or []
        if isinstance(conflicts_raw, str):
            semantic_conflicts = [c.strip() for c in conflicts_raw.split(",") if c.strip()]
        else:
            semantic_conflicts = list(conflicts_raw)

        return ResolvedSymbol(
            namespace_key=node_key,
            name=name,
            type_context=TypeContext(
                declaring_class=declaring_class,
                param_types=param_types,
                return_type=return_type,
                module=module,
            ),
            resolution_method=resolution_method,
            confidence_score=confidence_score,
            semantic_conflicts=semantic_conflicts,
        )

    # ──────────────────────────────────────────────
    # Private helpers — Conflict persistence (task 1.2.5)
    # ──────────────────────────────────────────────

    def _persist_semantic_conflicts(self, conflicts: list[ResolvedSymbol]) -> None:
        """
        Register semantic_conflicts as a property on the graph node via MERGE.
        When conflicts are detected, update the node in Neo4j with
        `semantic_conflicts` property (list of namespace_keys).

        Requirements: 2.7
        """
        if not self._use_neo4j():
            # Update in-memory nodes as fallback
            for sym in conflicts:
                node_data = self._memory_nodes.get(sym.namespace_key)
                if node_data is not None:
                    props = node_data.setdefault("properties", {})
                    props["semantic_conflicts"] = sym.semantic_conflicts
            return

        for sym in conflicts:
            try:
                cypher = """
                MERGE (n {namespace_key: $key})
                SET n.semantic_conflicts = $conflicts
                """
                self._neo4j_query(cypher, {
                    "key": sym.namespace_key,
                    "conflicts": sym.semantic_conflicts,
                })
            except Exception as e:
                logger.warning(
                    "SymbolResolver: failed to persist semantic_conflicts for %s: %s",
                    sym.namespace_key, e,
                )

    # ──────────────────────────────────────────────
    # Private helpers — Utilities
    # ──────────────────────────────────────────────

    def _get_node_properties(self, node_key: str) -> Optional[dict]:
        """Retrieve node properties from Neo4j or memory."""
        if self._use_neo4j():
            try:
                cypher = """
                MATCH (n {namespace_key: $key})
                RETURN properties(n) AS props
                LIMIT 1
                """
                rows = self._neo4j_query(cypher, {"key": node_key})
                if rows:
                    return rows[0].get("props") or {}
            except Exception as e:
                logger.warning("SymbolResolver: _get_node_properties Neo4j failed for %s: %s", node_key, e)

        node_data = self._memory_nodes.get(node_key)
        if node_data is not None:
            return node_data.get("properties") or {}

        return None

    def _extract_module_from_key(self, key: str) -> str:
        """
        Infer module/namespace from a namespace_key.
        E.g. "com.example.payroll.EmployeeService.save" → "com.example.payroll"
             "HR.PKG_EMPLOYEE.GET_SALARY" → "HR.PKG_EMPLOYEE"
        """
        if not key:
            return ""
        parts = key.split(".")
        if len(parts) >= 3:
            return ".".join(parts[:-2])
        if len(parts) == 2:
            return parts[0]
        return key
