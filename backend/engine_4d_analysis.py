from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


BREAKING_RELATIONS = {"CALLS_HTTP", "CONSUMES_API"}
DEGRADED_RELATIONS = {"IMPORTS", "MAPS_TO_COLUMN", "CALLS", "CALLS_RESOLVED", "DEPENDS_ON"}


@dataclass(slots=True)
class BlastNode:
    node_key: str
    node_name: str
    project_id: Optional[str]
    project_name: Optional[str]
    severity: str
    hop: int
    parent_key: Optional[str]
    edge_type: Optional[str]


class DeepArchitecture4DEngine:
    def __init__(self, registry, memory_nodes: list[dict], memory_edges: list[dict], neo4j_service=None) -> None:
        self._registry = registry
        self._memory_nodes = memory_nodes
        self._memory_edges = memory_edges
        self._neo4j = neo4j_service

    def simulate_blast_radius(self, workspace_id: str, symbol: str, max_hops: int = 8) -> dict:
        projects = self._registry.list_projects(workspace_id)
        if not projects:
            return {
                "workspace_id": workspace_id,
                "symbol": symbol,
                "origin_nodes": [],
                "blast_radius": [],
                "total_impacted": 0,
                "max_hops": max_hops,
            }

        workspace_project_ids = {project.id for project in projects}
        project_name_by_id = {project.id: project.name for project in projects}

        node_index = self._workspace_node_index(projects)
        edge_index = self._workspace_neighbors(node_index.keys())

        origin_keys = self._resolve_symbol_keys(symbol, node_index)
        if not origin_keys:
            return {
                "workspace_id": workspace_id,
                "symbol": symbol,
                "origin_nodes": [],
                "blast_radius": [],
                "total_impacted": 0,
                "max_hops": max_hops,
            }

        queue: deque[tuple[str, int, Optional[str], Optional[str]]] = deque()
        visited: set[str] = set()
        results: list[BlastNode] = []

        for origin in origin_keys:
            queue.append((origin, 0, None, None))

        while queue:
            current_key, hop, parent_key, rel_type = queue.popleft()
            if current_key in visited:
                continue
            visited.add(current_key)

            node = node_index.get(current_key)
            if not node:
                continue

            project_id = self._resolve_project_id(node, projects)
            if project_id and project_id not in workspace_project_ids:
                continue

            severity = self._classify(rel_type, hop)
            results.append(
                BlastNode(
                    node_key=current_key,
                    node_name=str(node.get("name") or current_key),
                    project_id=project_id,
                    project_name=project_name_by_id.get(project_id),
                    severity=severity,
                    hop=hop,
                    parent_key=parent_key,
                    edge_type=rel_type,
                )
            )

            if hop >= max_hops:
                continue

            for neighbor_key, neighbor_rel in edge_index.get(current_key, []):
                if neighbor_key in visited:
                    continue
                queue.append((neighbor_key, hop + 1, current_key, neighbor_rel))

        serializable = [
            {
                "node_key": item.node_key,
                "node_name": item.node_name,
                "project_id": item.project_id,
                "project_name": item.project_name,
                "severity": item.severity,
                "hop": item.hop,
                "parent_key": item.parent_key,
                "edge_type": item.edge_type,
            }
            for item in sorted(results, key=lambda row: (row.hop, row.node_name.lower()))
        ]

        return {
            "workspace_id": workspace_id,
            "symbol": symbol,
            "origin_nodes": origin_keys,
            "blast_radius": serializable,
            "total_impacted": max(0, len(serializable) - len(origin_keys)),
            "max_hops": max_hops,
        }

    def get_god_symbols(self, workspace_id: str, limit: int = 5) -> dict:
        projects = self._registry.list_projects(workspace_id)
        if not projects:
            return {"workspace_id": workspace_id, "items": []}
        project_name_by_id = {project.id: project.name for project in projects}

        node_index = self._workspace_node_index(projects)
        if not node_index:
            return {"workspace_id": workspace_id, "items": []}

        degree: dict[str, int] = defaultdict(int)
        inbound: dict[str, int] = defaultdict(int)
        outbound: dict[str, int] = defaultdict(int)

        workspace_keys = set(node_index.keys())
        for edge in self._memory_edges:
            source = edge.get("source")
            target = edge.get("target")
            if source not in workspace_keys or target not in workspace_keys:
                continue
            degree[source] += 1
            degree[target] += 1
            outbound[source] += 1
            inbound[target] += 1

        ranked = sorted(workspace_keys, key=lambda key: (degree[key], inbound[key], outbound[key]), reverse=True)

        items = []
        for key in ranked[: max(1, limit)]:
            node = node_index[key]
            project_id = self._resolve_project_id(node, projects)
            items.append(
                {
                    "node_key": key,
                    "name": str(node.get("name") or key),
                    "project_id": project_id,
                    "project_name": project_name_by_id.get(project_id),
                    "file": node.get("file"),
                    "total_dependencies": degree[key],
                    "inbound_dependencies": inbound[key],
                    "outbound_dependencies": outbound[key],
                }
            )

        return {"workspace_id": workspace_id, "items": items}

    def _workspace_node_index(self, projects: list) -> dict[str, dict]:
        project_roots = [(project.id, Path(project.path).resolve()) for project in projects]
        index: dict[str, dict] = {}

        for node in self._memory_nodes:
            key = node.get("namespace_key")
            if not key:
                continue

            project_id = node.get("project_id")
            if project_id and any(project.id == project_id for project in projects):
                index[key] = node
                continue

            node_file = node.get("file")
            if not node_file:
                continue

            try:
                node_path = Path(str(node_file)).resolve()
            except Exception:
                continue

            for _, root in project_roots:
                try:
                    node_path.relative_to(root)
                    index[key] = node
                    break
                except ValueError:
                    continue

        return index

    def _workspace_neighbors(self, workspace_keys: set[str]) -> dict[str, list[tuple[str, str]]]:
        neighbors: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for edge in self._memory_edges:
            source = edge.get("source")
            target = edge.get("target")
            rel_type = str(edge.get("type") or "UNKNOWN")
            if source not in workspace_keys or target not in workspace_keys:
                continue

            neighbors[source].append((target, rel_type))
            neighbors[target].append((source, rel_type))

        return neighbors

    def _resolve_symbol_keys(self, symbol: str, node_index: dict[str, dict]) -> list[str]:
        if symbol in node_index:
            return [symbol]

        lowered = symbol.strip().lower()
        if not lowered:
            return []

        exact_name = [
            key
            for key, node in node_index.items()
            if str(node.get("name") or "").lower() == lowered
        ]
        if exact_name:
            return exact_name

        fuzzy = [
            key
            for key, node in node_index.items()
            if lowered in key.lower() or lowered in str(node.get("name") or "").lower()
        ]
        return fuzzy[:5]

    def _resolve_project_id(self, node: dict, projects: list) -> Optional[str]:
        project_id = node.get("project_id")
        if isinstance(project_id, str) and any(project.id == project_id for project in projects):
            return project_id

        node_file = node.get("file")
        if not node_file:
            return None

        try:
            node_path = Path(str(node_file)).resolve()
        except Exception:
            return None

        for project in projects:
            try:
                node_path.relative_to(Path(project.path).resolve())
                return project.id
            except ValueError:
                continue

        return None

    @staticmethod
    def _classify(relation_type: Optional[str], hop: int) -> str:
        if hop == 0:
            return "ORIGIN"
        if relation_type in BREAKING_RELATIONS:
            return "BREAKING"
        if relation_type in DEGRADED_RELATIONS:
            return "DEGRADED"
        return "INFORMATIONAL"
