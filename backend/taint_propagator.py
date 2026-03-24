"""
TaintPropagator — Rastreia a propagação de um valor contaminado através do grafo de dependências,
registrando o tipo de dado em cada ponto da cadeia e sinalizando riscos de precisão.

Requirements: 1.1–1.8
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("insightgraph")

# Relacionamentos rastreados pelo BFS
_TRACKED_RELATIONSHIPS = [
    "MAPS_TO_COLUMN",
    "MAPPED_FROM",
    "SERIALIZED_BY",
    "DISPLAYED_BY",
    "HAS_PARAMETER",
    "HAS_FIELD",
    "CALLS",
    "CALLS_HTTP",
]

# Tabela de conversões perigosas: (from_type_upper, to_type_upper) -> description
_DANGEROUS_CONVERSIONS: dict[tuple[str, str], str] = {
    ("DECIMAL", "NUMBER"):  "Precision loss: DECIMAL to JavaScript number (IEEE 754)",
    ("DECIMAL", "FLOAT"):   "Precision loss: DECIMAL to float",
    ("BIGINT", "INT"):      "Overflow risk: BIGINT to Java int",
    ("BIGINT", "INTEGER"):  "Overflow risk: BIGINT to Java int",
    ("NUMBER", "FLOAT"):    "Precision loss: NUMBER to float",
    ("NUMERIC", "NUMBER"):  "Precision loss: NUMERIC to JavaScript number (IEEE 754)",
    ("NUMERIC", "FLOAT"):   "Precision loss: NUMERIC to float",
}


@dataclass
class TaintPoint:
    node_key: str
    name: str
    layer: str                      # "database" | "procedure" | "java" | "typescript" | "angular"
    data_type: str                  # native type at this layer (e.g., "NUMBER", "BigDecimal", "number")
    precision_risk: bool
    precision_risk_description: str
    resolved: bool


@dataclass
class TaintPath:
    origin_key: str
    origin_layer: str
    destination_layer: str
    points: list[TaintPoint] = field(default_factory=list)
    total_hops: int = 0
    unresolved_links: list[str] = field(default_factory=list)


class TaintPropagator:
    """
    Rastreia a propagação de um valor contaminado através do grafo de dependências.

    Usa BFS via Neo4j quando disponível; cai para memory_nodes/memory_edges caso contrário.

    Requirements: 1.1–1.8
    """

    def __init__(self, neo4j_service, memory_nodes: dict, memory_edges: list):
        """
        Args:
            neo4j_service: Serviço Neo4j com atributos `.driver` e método `.query(cypher, params)`.
                           Pode ser None para forçar fallback em memória.
            memory_nodes: dict {node_key: {"labels": [...], "properties": {...}}}
            memory_edges: list de dicts [{"from": key, "to": key, "type": rel_type, "properties": {...}}]
        """
        self._neo4j = neo4j_service
        self._memory_nodes: dict = memory_nodes or {}
        self._memory_edges: list = memory_edges or []

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    def propagate(
        self,
        origin_key: str,
        change_type: str,
        old_type: str,
        new_type: str,
    ) -> TaintPath:
        """
        Rastreia todos os artefatos alcançáveis a partir de origin_key via BFS.

        Retorna um TaintPath completo com todos os nós alcançáveis.
        Elos não resolvidos aparecem como TaintPoint(resolved=False) sem interromper o rastreamento.

        Requirements: 1.1, 1.5, 1.7, 1.8
        """
        visited: set[str] = set()
        points: list[TaintPoint] = []
        unresolved_links: list[str] = []

        # Resolve o nó de origem
        origin_point = self._resolve_node(origin_key, old_type or new_type)
        if origin_point is not None:
            # Detecta risco de precisão na origem (mudança de tipo)
            if old_type and new_type:
                risk, desc = self._detect_precision_risk(old_type, new_type)
                origin_point.precision_risk = risk
                origin_point.precision_risk_description = desc
            points.append(origin_point)
            visited.add(origin_key)
        else:
            # Origem não resolvida — registra como unresolved e continua
            unresolved_links.append(origin_key)
            unresolved_point = TaintPoint(
                node_key=origin_key,
                name=origin_key,
                layer="unknown",
                data_type=old_type or "",
                precision_risk=False,
                precision_risk_description="",
                resolved=False,
            )
            points.append(unresolved_point)
            visited.add(origin_key)

        # BFS
        queue: deque[str] = deque([origin_key])
        while queue:
            current_key = queue.popleft()
            neighbors = self._follow_relationships(current_key, visited)
            for point in neighbors:
                visited.add(point.node_key)
                if not point.resolved:
                    unresolved_links.append(point.node_key)
                points.append(point)
                queue.append(point.node_key)

        # Determina camadas de origem e destino
        origin_layer = points[0].layer if points else "unknown"
        destination_layer = points[-1].layer if points else "unknown"

        return TaintPath(
            origin_key=origin_key,
            origin_layer=origin_layer,
            destination_layer=destination_layer,
            points=points,
            total_hops=len(points),
            unresolved_links=unresolved_links,
        )

    def _follow_relationships(self, key: str, visited: set) -> list[TaintPoint]:
        """
        Retorna os TaintPoints dos vizinhos diretos de `key` via os relacionamentos rastreados,
        excluindo nós já visitados.

        Tenta Neo4j primeiro; cai para memória se indisponível.

        Requirements: 1.5
        """
        use_neo4j = (
            self._neo4j is not None
            and getattr(self._neo4j, "is_connected", False)
        )

        if use_neo4j:
            try:
                return self._follow_neo4j(key, visited)
            except Exception as e:
                logger.warning("TaintPropagator: Neo4j follow failed for %s, using memory: %s", key, e)

        return self._follow_memory(key, visited)

    # ──────────────────────────────────────────────
    # Neo4j path
    # ──────────────────────────────────────────────

    def _follow_neo4j(self, key: str, visited: set) -> list[TaintPoint]:
        """Segue relacionamentos rastreados via Cypher."""
        rel_types = "|".join(_TRACKED_RELATIONSHIPS)
        cypher = f"""
        MATCH (a {{namespace_key: $key}})-[r:{rel_types}]->(b)
        WHERE NOT b.namespace_key IN $visited
        RETURN
            b.namespace_key AS node_key,
            b.name AS name,
            labels(b) AS labels,
            b.file AS file,
            b.data_type AS data_type,
            b.type AS type_prop,
            type(r) AS rel_type
        """
        try:
            rows = self._neo4j.query(cypher, {"key": key, "visited": list(visited)})
        except Exception:
            # Fallback: try .graph.run() pattern (py2neo)
            rows = self._neo4j.graph.run(cypher, key=key, visited=list(visited)).data()

        points: list[TaintPoint] = []
        for row in rows:
            node_key = row.get("node_key") or ""
            if not node_key or node_key in visited:
                continue

            labels = row.get("labels") or []
            file_path = row.get("file") or ""
            data_type = row.get("data_type") or row.get("type_prop") or ""
            layer = self._infer_layer(labels, file_path)

            points.append(TaintPoint(
                node_key=node_key,
                name=row.get("name") or node_key,
                layer=layer,
                data_type=data_type,
                precision_risk=False,
                precision_risk_description="",
                resolved=True,
            ))

        return points

    # ──────────────────────────────────────────────
    # Memory fallback
    # ──────────────────────────────────────────────

    def _follow_memory(self, key: str, visited: set) -> list[TaintPoint]:
        """Segue relacionamentos rastreados via memory_edges."""
        tracked = set(_TRACKED_RELATIONSHIPS)
        points: list[TaintPoint] = []

        for edge in self._memory_edges:
            from_key = edge.get("from") or edge.get("source") or ""
            to_key = edge.get("to") or edge.get("target") or ""
            rel_type = edge.get("type") or ""

            if from_key != key:
                continue
            if rel_type not in tracked:
                continue
            if to_key in visited:
                continue

            node_data = self._memory_nodes.get(to_key)
            if node_data is None:
                # Elo não resolvido
                points.append(TaintPoint(
                    node_key=to_key,
                    name=to_key,
                    layer="unknown",
                    data_type="",
                    precision_risk=False,
                    precision_risk_description="",
                    resolved=False,
                ))
                continue

            labels = node_data.get("labels") or []
            props = node_data.get("properties") or {}
            file_path = props.get("file") or ""
            data_type = props.get("data_type") or props.get("type") or ""
            layer = self._infer_layer(labels, file_path)

            points.append(TaintPoint(
                node_key=to_key,
                name=props.get("name") or to_key,
                layer=layer,
                data_type=data_type,
                precision_risk=False,
                precision_risk_description="",
                resolved=True,
            ))

        return points

    def _resolve_node(self, key: str, hint_type: str = "") -> Optional[TaintPoint]:
        """
        Resolve um nó pelo seu key, tentando Neo4j e depois memória.
        Retorna None se o nó não for encontrado em nenhuma fonte.
        """
        # Tenta Neo4j
        use_neo4j = (
            self._neo4j is not None
            and getattr(self._neo4j, "is_connected", False)
        )
        if use_neo4j:
            try:
                cypher = """
                MATCH (n {namespace_key: $key})
                RETURN n.name AS name, labels(n) AS labels, n.file AS file,
                       n.data_type AS data_type, n.type AS type_prop
                LIMIT 1
                """
                try:
                    rows = self._neo4j.query(cypher, {"key": key})
                except Exception:
                    rows = self._neo4j.graph.run(cypher, key=key).data()

                if rows:
                    row = rows[0]
                    labels = row.get("labels") or []
                    file_path = row.get("file") or ""
                    data_type = row.get("data_type") or row.get("type_prop") or hint_type
                    return TaintPoint(
                        node_key=key,
                        name=row.get("name") or key,
                        layer=self._infer_layer(labels, file_path),
                        data_type=data_type,
                        precision_risk=False,
                        precision_risk_description="",
                        resolved=True,
                    )
            except Exception as e:
                logger.warning("TaintPropagator: _resolve_node Neo4j failed for %s: %s", key, e)

        # Tenta memória
        node_data = self._memory_nodes.get(key)
        if node_data is not None:
            labels = node_data.get("labels") or []
            props = node_data.get("properties") or {}
            file_path = props.get("file") or ""
            data_type = props.get("data_type") or props.get("type") or hint_type
            return TaintPoint(
                node_key=key,
                name=props.get("name") or key,
                layer=self._infer_layer(labels, file_path),
                data_type=data_type,
                precision_risk=False,
                precision_risk_description="",
                resolved=True,
            )

        return None

    # ──────────────────────────────────────────────
    # Precision risk detection (task 1.1.2)
    # ──────────────────────────────────────────────

    def _detect_precision_risk(self, from_type: str, to_type: str) -> tuple[bool, str]:
        """
        Detecta se a conversão from_type → to_type representa risco de perda de precisão.

        Tabela de conversões perigosas:
        - DECIMAL → number (JS): precision loss due to IEEE 754
        - BIGINT → int (Java): overflow risk
        - NUMBER → float: precision loss
        - NUMERIC → number: precision loss
        - DECIMAL → float: precision loss

        Retorna (True, description) para conversões perigosas, (False, "") caso contrário.

        Requirements: 1.3
        """
        from_upper = from_type.upper().strip()
        to_upper = to_type.upper().strip()

        description = _DANGEROUS_CONVERSIONS.get((from_upper, to_upper))
        if description:
            return True, description

        return False, ""

    # ──────────────────────────────────────────────
    # Layer inference (task 1.1.3)
    # ──────────────────────────────────────────────

    def _infer_layer(self, labels: list[str], file: str) -> str:
        """
        Classifica um nó em uma das camadas arquiteturais com base em seus labels e caminho de arquivo.

        Camadas:
        - "database"   — labels: Column, Table, View; ou arquivo .sql
        - "procedure"  — labels: Procedure, Function, Package; ou arquivo .pls/.pkb/.pks
        - "java"       — labels: JavaClass, JavaMethod; ou arquivo .java
        - "typescript" — labels: TypeScriptClass, TypeScriptFunction; ou arquivo .ts (exceto .component.ts)
        - "angular"    — labels: AngularComponent; ou arquivo .component.ts/.html
        - "unknown"    — padrão

        Requirements: 1.2
        """
        label_set = set(labels or [])
        file_lower = (file or "").lower()

        # Database
        if label_set & {"Column", "Table", "View"} or file_lower.endswith(".sql"):
            return "database"

        # Procedure
        if (
            label_set & {"Procedure", "Function", "Package"}
            or file_lower.endswith(".pls")
            or file_lower.endswith(".pkb")
            or file_lower.endswith(".pks")
        ):
            return "procedure"

        # Java
        if label_set & {"JavaClass", "JavaMethod"} or file_lower.endswith(".java"):
            return "java"

        # Angular (must be checked before typescript — .component.ts matches both)
        if (
            label_set & {"AngularComponent"}
            or file_lower.endswith(".component.ts")
            or file_lower.endswith(".html")
        ):
            return "angular"

        # TypeScript (generic .ts, not .component.ts)
        if label_set & {"TypeScriptClass", "TypeScriptFunction"} or file_lower.endswith(".ts"):
            return "typescript"

        return "unknown"
