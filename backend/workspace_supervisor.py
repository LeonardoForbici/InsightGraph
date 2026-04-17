"""
WorkspaceSupervisor — Gerenciador central de todos os ProjectWorkers.

É o "processo-pai" que:
  - Mantém um dict de workers ativos por project_id
  - Inicia/para workers conforme projetos são adicionados/removidos
  - Controla prioridade (active/background) com base no projeto selecionado no frontend
  - Expõe status de todos os workers para a API REST
  - É singleton (uma instância por processo FastAPI)

Uso:
    supervisor = WorkspaceSupervisor(registry, scanner, cross_engine, stream)
    await supervisor.boot()               # carrega projetos salvos
    await supervisor.add_project(proj)    # adiciona projeto em runtime
    await supervisor.set_active(proj_id)  # eleva prioridade
    await supervisor.shutdown()           # graceful stop
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from project_worker import ProjectWorker

logger = logging.getLogger("insightgraph.supervisor")


class WorkspaceSupervisor:

    def __init__(
        self,
        registry,
        incremental_scanner,
        cross_impact_engine,
        event_stream=None,
        redis_client=None,
    ):
        self._registry = registry
        self._scanner = incremental_scanner
        self._cross = cross_impact_engine
        self._stream = event_stream
        self._redis = redis_client

        # project_id → ProjectWorker
        self._workers: dict[str, ProjectWorker] = {}
        self._active_project_id: Optional[str] = None

    # ── Boot / Shutdown ───────────────────────

    async def boot(self):
        """Reinicia workers para todos os projetos salvos em todos os workspaces."""
        workspaces = self._registry.list_workspaces()
        count = 0
        for ws in workspaces:
            projects = self._registry.list_projects(ws.id)
            for p in projects:
                await self._spawn(p)
                count += 1
        logger.info("WorkspaceSupervisor booted: %d workers iniciados", count)

    async def shutdown(self):
        logger.info("WorkspaceSupervisor shutting down %d workers...", len(self._workers))
        tasks = [w.stop() for w in self._workers.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        self._workers.clear()
        logger.info("WorkspaceSupervisor shutdown complete")

    # ── Gestão de projetos ────────────────────

    async def add_project(self, project) -> ProjectWorker:
        """Cria e inicia um worker para um projeto recém-adicionado."""
        if project.id in self._workers:
            return self._workers[project.id]
        worker = await self._spawn(project)
        logger.info("Project adicionado ao supervisor: %s", project.name)
        return worker

    async def remove_project(self, project_id: str):
        """Para e remove o worker de um projeto."""
        worker = self._workers.pop(project_id, None)
        if worker:
            await worker.stop()
            logger.info("Project removido do supervisor: %s", project_id)

    async def restart_project(self, project_id: str):
        """Para e reinicia o worker de um projeto (ex: após mudança de config)."""
        await self.remove_project(project_id)
        p = self._registry.get_project(project_id)
        if p:
            await self._spawn(p)

    # ── Prioridade ────────────────────────────

    def set_active(self, project_id: Optional[str]):
        """
        Eleva o projeto selecionado para 'active' (polling rápido).
        Rebaixa o anterior para 'background'.
        """
        if self._active_project_id and self._active_project_id in self._workers:
            self._workers[self._active_project_id].set_priority("background")

        self._active_project_id = project_id

        if project_id and project_id in self._workers:
            self._workers[project_id].set_priority("active")
            logger.debug("Priority escalated: %s → active", project_id)

    # ── Status ────────────────────────────────

    def get_status(self) -> list[dict]:
        """Retorna snapshot de status de todos os workers."""
        out = []
        for pid, worker in self._workers.items():
            p = worker._project
            out.append({
                "project_id": pid,
                "project_name": p.name,
                "workspace_id": p.workspace_id,
                "status": p.status,
                "priority": worker.priority,
                "path": p.path,
                "last_scanned_at": p.last_scanned_at,
                "last_commit": p.last_commit,
                "error_message": p.error_message,
            })
        return out

    def get_worker(self, project_id: str) -> Optional[ProjectWorker]:
        return self._workers.get(project_id)

    # ── Interno ───────────────────────────────

    async def _spawn(self, project) -> ProjectWorker:
        worker = ProjectWorker(
            project=project,
            registry=self._registry,
            incremental_scanner=self._scanner,
            cross_impact_engine=self._cross,
            event_stream=self._stream,
            redis_client=self._redis,
            priority="background",
        )
        self._workers[project.id] = worker
        await worker.start()
        return worker
