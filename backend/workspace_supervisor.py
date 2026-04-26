from __future__ import annotations

import asyncio
import logging

from project_worker import ProjectWorker

logger = logging.getLogger("insightgraph.workspace_supervisor")


class WorkspaceSupervisor:
    def __init__(
        self,
        registry,
        incremental_scanner,
        cross_impact_engine,
        memory_nodes: list[dict],
        event_stream=None,
        max_concurrency: int = 4,
    ) -> None:
        self._registry = registry
        self._scanner = incremental_scanner
        self._cross_engine = cross_impact_engine
        self._memory_nodes = memory_nodes
        self._event_stream = event_stream
        self._max_concurrency = max(1, max_concurrency)

        self._workers: dict[str, ProjectWorker] = {}

    async def boot(self) -> None:
        projects = self._registry.list_projects()
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def _spawn(project) -> None:
            async with semaphore:
                await self.add_project(project)

        await asyncio.gather(*[_spawn(project) for project in projects], return_exceptions=False)
        logger.info("Workspace supervisor boot completed with %d workers", len(self._workers))

    async def shutdown(self) -> None:
        workers = list(self._workers.items())
        self._workers = {}
        for _, worker in workers:
            await worker.stop()

    async def add_project(self, project):
        existing = self._workers.get(project.id)
        if existing:
            return existing

        worker = ProjectWorker(
            project=project,
            registry=self._registry,
            incremental_scanner=self._scanner,
            cross_impact_engine=self._cross_engine,
            memory_nodes=self._memory_nodes,
            event_stream=self._event_stream,
        )
        self._workers[project.id] = worker
        await worker.start()
        return worker

    async def remove_project(self, project_id: str) -> None:
        worker = self._workers.pop(project_id, None)
        if worker:
            await worker.stop()

    async def restart_project(self, project_id: str) -> None:
        await self.remove_project(project_id)
        project = self._registry.get_project(project_id)
        if project:
            await self.add_project(project)

    def status(self) -> list[dict]:
        status_rows: list[dict] = []
        for project in self._registry.list_projects():
            status_rows.append(
                {
                    "project_id": project.id,
                    "workspace_id": project.workspace_id,
                    "name": project.name,
                    "path": project.path,
                    "type": project.type,
                    "status": project.status,
                    "updated_at": project.updated_at,
                    "last_error": project.last_error,
                    "watching": project.id in self._workers,
                }
            )
        return status_rows
