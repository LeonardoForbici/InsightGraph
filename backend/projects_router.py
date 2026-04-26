from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(tags=["projects"])

_registry = None
_supervisor = None
_event_stream = None
_analysis_4d_engine = None


def init_router(registry, supervisor, event_stream, analysis_4d_engine=None) -> None:
    global _registry, _supervisor, _event_stream, _analysis_4d_engine
    _registry = registry
    _supervisor = supervisor
    _event_stream = event_stream
    _analysis_4d_engine = analysis_4d_engine


def _ensure_ready() -> None:
    if _registry is None or _supervisor is None or _event_stream is None:
        raise HTTPException(status_code=503, detail="Projects subsystem not initialized")


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    root_path: str = Field(min_length=1)


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    path: str = Field(min_length=1)
    type: str = Field(default="other")


@router.post("/workspaces", status_code=201)
async def create_workspace(payload: WorkspaceCreateRequest):
    _ensure_ready()
    if not Path(payload.root_path).exists():
        raise HTTPException(status_code=400, detail="root_path does not exist")

    workspace = _registry.create_workspace(payload.name, payload.root_path)
    return workspace.to_dict()


@router.get("/workspaces")
async def list_workspaces():
    _ensure_ready()
    workspaces = []
    for workspace in _registry.list_workspaces():
        projects = _registry.list_projects(workspace.id)
        item = workspace.to_dict()
        item["projects"] = [project.to_dict() for project in projects]
        workspaces.append(item)
    return workspaces


@router.post("/workspaces/{workspace_id}/projects", status_code=201)
async def create_project(workspace_id: str, payload: ProjectCreateRequest):
    _ensure_ready()
    workspace = _registry.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    project_path = Path(payload.path)
    if not project_path.exists() or not project_path.is_dir():
        raise HTTPException(status_code=400, detail="Project path does not exist or is not a directory")

    project = _registry.create_project(
        workspace_id=workspace_id,
        name=payload.name,
        path=str(project_path),
        project_type=payload.type if payload.type in {"backend", "frontend", "mobile", "other"} else "other",
    )
    await _supervisor.add_project(project)
    return project.to_dict()


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: str):
    _ensure_ready()
    await _supervisor.remove_project(project_id)
    deleted = _registry.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/projects/status")
async def get_project_statuses():
    _ensure_ready()
    return _supervisor.status()


@router.get("/workspaces/{workspace_id}/analysis/4d-blast-radius")
async def analysis_4d_blast_radius(
    workspace_id: str,
    symbol: str = Query(..., min_length=1),
    max_hops: int = Query(8, ge=1, le=15),
):
    _ensure_ready()
    workspace = _registry.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if _analysis_4d_engine is None:
        raise HTTPException(status_code=503, detail="4D analysis engine not initialized")

    return _analysis_4d_engine.simulate_blast_radius(workspace_id=workspace_id, symbol=symbol, max_hops=max_hops)


@router.get("/workspaces/{workspace_id}/analysis/god-symbols")
async def analysis_god_symbols(
    workspace_id: str,
    limit: int = Query(5, ge=1, le=20),
):
    _ensure_ready()
    workspace = _registry.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if _analysis_4d_engine is None:
        raise HTTPException(status_code=503, detail="4D analysis engine not initialized")

    return _analysis_4d_engine.get_god_symbols(workspace_id=workspace_id, limit=limit)


@router.get("/events/stream")
async def events_stream(workspace_id: Optional[str] = Query(default=None)):
    _ensure_ready()
    if _event_stream is None:
        raise HTTPException(status_code=503, detail="Event stream is not initialized")

    allowed_project_ids: Optional[set[str]] = None
    if workspace_id:
        workspace = _registry.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")
        allowed_project_ids = {project.id for project in _registry.list_projects(workspace_id)}

    queue = await _event_stream.subscribe()

    async def _iter_events():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue

                if allowed_project_ids is not None:
                    payload = event.payload if isinstance(event.payload, dict) else {}
                    event_workspace = payload.get("workspace_id")
                    event_project = payload.get("project_id") or payload.get("origin_project_id")
                    if event_workspace != workspace_id and event_project not in allowed_project_ids:
                        cross_payload = payload.get("cross_project")
                        if isinstance(cross_payload, dict):
                            cross_origin = cross_payload.get("origin_project_id")
                            if cross_origin not in allowed_project_ids:
                                continue
                        else:
                            continue

                envelope = {
                    "type": event.type,
                    "timestamp": event.timestamp,
                    "payload": event.payload,
                }
                yield f"data: {json.dumps(envelope, ensure_ascii=False)}\\n\\n"
        finally:
            await _event_stream.unsubscribe(queue)

    return StreamingResponse(
        _iter_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
