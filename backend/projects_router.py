"""
ProjectsRouter — API REST para Workspaces e Projects.

Endpoints:
  POST   /workspaces                      → criar workspace
  GET    /workspaces                      → listar workspaces
  DELETE /workspaces/{id}                 → remover workspace

  POST   /workspaces/{ws_id}/projects     → adicionar projeto
  GET    /workspaces/{ws_id}/projects     → listar projetos
  DELETE /projects/{id}                  → remover projeto
  PATCH  /projects/{id}/active           → eleva prioridade (ativo no UI)
  GET    /projects/status                → snapshot de todos os workers
  GET    /projects/{id}/impact/cross     → último impacto cross-projeto
  GET    /events/stream                  → SSE stream (filtrado por project_id)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("insightgraph.router.projects")

router = APIRouter(tags=["projects"])

# Esses objetos são injetados pelo main.py após inicialização
_registry = None
_supervisor = None
_event_stream = None
_cross_engine = None

def init_router(registry, supervisor, event_stream, cross_engine):
    global _registry, _supervisor, _event_stream, _cross_engine
    _registry      = registry
    _supervisor    = supervisor
    _event_stream  = event_stream
    _cross_engine  = cross_engine


# ── Pydantic models ───────────────────────────

class CreateWorkspaceRequest(BaseModel):
    name: str
    root_path: str
    description: str = ""

class CreateProjectRequest(BaseModel):
    name: str
    path: str
    type: str = "other"
    watch_interval: int = 5
    git_poll_interval: int = 30


# ── Workspaces ────────────────────────────────

@router.post("/workspaces", status_code=201)
async def create_workspace(body: CreateWorkspaceRequest):
    ws = _registry.create_workspace(
        name=body.name,
        root_path=body.root_path,
        description=body.description,
    )
    return ws.to_dict()


@router.get("/workspaces")
async def list_workspaces():
    workspaces = _registry.list_workspaces()
    out = []
    for ws in workspaces:
        projects = _registry.list_projects(ws.id)
        d = ws.to_dict()
        d["projects"] = [p.to_dict() for p in projects]
        d["project_count"] = len(projects)
        out.append(d)
    return out


@router.delete("/workspaces/{workspace_id}", status_code=204)
async def delete_workspace(workspace_id: str):
    projects = _registry.list_projects(workspace_id)
    for p in projects:
        await _supervisor.remove_project(p.id)
    ok = _registry.delete_workspace(workspace_id)
    if not ok:
        raise HTTPException(404, "Workspace not found")


# ── Projects ──────────────────────────────────

@router.post("/workspaces/{workspace_id}/projects", status_code=201)
async def create_project(workspace_id: str, body: CreateProjectRequest):
    ws = _registry.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(404, "Workspace not found")

    project = _registry.create_project(
        workspace_id=workspace_id,
        name=body.name,
        path=body.path,
        type=body.type,
        watch_interval=body.watch_interval,
        git_poll_interval=body.git_poll_interval,
    )
    await _supervisor.add_project(project)
    return project.to_dict()


@router.get("/workspaces/{workspace_id}/projects")
async def list_projects(workspace_id: str):
    projects = _registry.list_projects(workspace_id)
    return [p.to_dict() for p in projects]


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: str):
    await _supervisor.remove_project(project_id)
    ok = _registry.delete_project(project_id)
    if not ok:
        raise HTTPException(404, "Project not found")


@router.patch("/projects/{project_id}/active")
async def set_active_project(project_id: str):
    """
    Sinaliza que este projeto está ativo no UI → eleva para polling rápido.
    """
    p = _registry.get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    _supervisor.set_active(project_id)
    return {"status": "active", "project_id": project_id}


@router.get("/projects/status")
async def get_all_workers_status():
    return _supervisor.get_status()


@router.get("/projects/{project_id}/impact/cross")
async def get_cross_impact(project_id: str):
    """
    Retorna o último resultado de impacto cross-projeto para um projeto.
    """
    p = _registry.get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    siblings = _registry.get_sibling_projects(project_id)
    return {
        "project_id": project_id,
        "project_name": p.name,
        "workspace_id": p.workspace_id,
        "siblings": [{"id": s.id, "name": s.name, "type": s.type} for s in siblings],
    }


# ── SSE Stream por projeto ────────────────────

@router.get("/events/stream")
async def sse_stream(
    project_id: Optional[str] = Query(None),
    workspace_id: Optional[str] = Query(None),
):
    """
    Server-Sent Events filtrado por project_id ou workspace_id.

    Conectar:
      GET /events/stream?project_id=<uuid>
      GET /events/stream?workspace_id=<uuid>   (recebe eventos de todos os projetos)
      GET /events/stream                        (todos os eventos globais)
    """
    if not _event_stream:
        raise HTTPException(503, "Event stream not initialized")

    # Resolve filtro de projetos aceitos
    accepted_ids: Optional[set] = None
    if project_id:
        accepted_ids = {project_id}
    elif workspace_id:
        projects = _registry.list_projects(workspace_id)
        accepted_ids = {p.id for p in projects}

    client_queue = await _event_stream.subscribe()

    async def generator():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(
                        client_queue.get(), timeout=25.0
                    )
                    # Filtra por projeto se solicitado
                    if accepted_ids:
                        pid = event.payload.get("project_id")
                        # cross_project events also have origin_project_id
                        origin = event.payload.get("origin_project_id")
                        if pid not in accepted_ids and origin not in accepted_ids:
                            # ainda verifica se afeta algum projeto do workspace
                            affected = event.payload.get("cross_project", {})
                            if not affected:
                                continue

                    data = json.dumps({
                        "type": event.type,
                        "payload": event.payload,
                        "timestamp": event.timestamp,
                    })
                    yield f"data: {data}\n\n"

                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"

        except asyncio.CancelledError:
            pass
        finally:
            await _event_stream.unsubscribe(client_queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
