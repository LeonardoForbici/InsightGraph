from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Optional

from event_stream import SSEEvent

logger = logging.getLogger("insightgraph.cross_project_impact")

ImpactSeverity = Literal["BREAKING", "DEGRADED", "INFORMATIONAL"]
CROSS_REL_TYPES = {"CALLS_HTTP", "CONSUMES_API", "IMPORTS", "MAPS_TO_COLUMN", "CALLS", "CALLS_RESOLVED"}
BREAKING_REL_TYPES = {"CALLS_HTTP", "CONSUMES_API"}
DEGRADED_REL_TYPES = {"IMPORTS", "MAPS_TO_COLUMN", "CALLS", "CALLS_RESOLVED"}


@dataclass(slots=True)
class AffectedNode:
    workspace_id: str
    project_id: str
    project_name: str
    node_key: str
    symbol_name: str
    relation_type: str
    severity: ImpactSeverity


@dataclass(slots=True)
class CrossProjectImpactResult:
    origin_project_id: str
    workspace_id: Optional[str]
    file_path: str
    changed_nodes: list[str]
    affected: list[AffectedNode]
    timestamp: float = field(default_factory=time.time)

    @property
    def total_affected(self) -> int:
        return len(self.affected)

    @property
    def breaking_count(self) -> int:
        return sum(1 for node in self.affected if node.severity == "BREAKING")

    def to_payload(self) -> dict:
        return {
            "workspace_id": self.workspace_id,
            "origin_project_id": self.origin_project_id,
            "file_path": self.file_path,
            "changed_nodes": self.changed_nodes,
            "total_affected": self.total_affected,
            "breaking_count": self.breaking_count,
            "affected": [asdict(item) for item in self.affected],
            "timestamp": self.timestamp,
        }


class CrossProjectImpactEngine:
    def __init__(self, registry, memory_nodes: list[dict], memory_edges: list[dict], event_stream=None):
        self._registry = registry
        self._memory_nodes = memory_nodes
        self._memory_edges = memory_edges
        self._event_stream = event_stream

    async def analyze(
        self,
        origin_project_id: str,
        changed_file: str,
        changed_nodes: list[str],
    ) -> CrossProjectImpactResult:
        origin_project = self._registry.get_project(origin_project_id)
        workspace_id = origin_project.workspace_id if origin_project else None
        siblings = self._registry.get_sibling_projects(origin_project_id)
        sibling_map = {p.id: p for p in siblings}
        sibling_ids = set(sibling_map.keys())

        if not sibling_ids or not changed_nodes:
            return CrossProjectImpactResult(
                origin_project_id=origin_project_id,
                workspace_id=workspace_id,
                file_path=changed_file,
                changed_nodes=changed_nodes,
                affected=[],
            )

        node_index = {node.get("namespace_key"): node for node in self._memory_nodes if node.get("namespace_key")}

        affected_items: list[AffectedNode] = []
        seen: set[tuple[str, str]] = set()

        for edge in self._memory_edges:
            rel_type = str(edge.get("type") or "")
            if rel_type not in CROSS_REL_TYPES:
                continue

            source_key = edge.get("source")
            target_key = edge.get("target")
            if source_key not in changed_nodes and target_key not in changed_nodes:
                continue

            other_key = target_key if source_key in changed_nodes else source_key
            other_node = node_index.get(other_key)
            if not other_node:
                continue

            project_id = self._resolve_project_id(other_node, sibling_ids)
            if not project_id:
                continue

            sibling = sibling_map.get(project_id)
            if not sibling:
                continue

            dedupe_key = (project_id, other_key)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            affected_items.append(
                AffectedNode(
                    workspace_id=sibling.workspace_id,
                    project_id=project_id,
                    project_name=sibling.name,
                    node_key=other_key,
                    symbol_name=str(other_node.get("name") or other_key),
                    relation_type=rel_type,
                    severity=self._severity_for_relation(rel_type),
                )
            )

        result = CrossProjectImpactResult(
            origin_project_id=origin_project_id,
            workspace_id=workspace_id,
            file_path=changed_file,
            changed_nodes=changed_nodes,
            affected=affected_items,
        )

        if result.total_affected > 0:
            await self._publish(result)

        return result

    def _resolve_project_id(self, node: dict, sibling_ids: set[str]) -> Optional[str]:
        explicit = node.get("project_id")
        if isinstance(explicit, str) and explicit in sibling_ids:
            return explicit

        node_file = str(node.get("file") or "")
        if not node_file:
            return None

        node_file_path = Path(node_file).resolve()
        for sibling in self._registry.list_projects():
            if sibling.id not in sibling_ids:
                continue
            sibling_path = Path(sibling.path).resolve()
            try:
                node_file_path.relative_to(sibling_path)
                return sibling.id
            except ValueError:
                continue

        return None

    @staticmethod
    def _severity_for_relation(relation_type: str) -> ImpactSeverity:
        if relation_type in BREAKING_REL_TYPES:
            return "BREAKING"
        if relation_type in DEGRADED_REL_TYPES:
            return "DEGRADED"
        return "INFORMATIONAL"

    async def _publish(self, result: CrossProjectImpactResult) -> None:
        if not self._event_stream:
            return

        payload = result.to_payload()
        try:
            await self._event_stream.publish(
                SSEEvent(type="impact_detected", payload=payload, timestamp=time.time())
            )
        except Exception as exc:
            logger.warning("Failed to publish cross-project impact event: %s", exc)
