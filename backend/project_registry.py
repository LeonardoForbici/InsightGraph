from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger("insightgraph.project_registry")

ProjectType = Literal["backend", "frontend", "mobile", "other"]
ProjectStatus = Literal["idle", "watching", "scanning", "error"]


@dataclass(slots=True)
class Workspace:
    id: str
    name: str
    root_path: str
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class Project:
    id: str
    workspace_id: str
    name: str
    path: str
    type: ProjectType = "other"
    status: ProjectStatus = "idle"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_error: Optional[str] = None
    exported_symbols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class ProjectRegistry:
    def __init__(self, db_path: str = "insightgraph_state.db") -> None:
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'idle',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_error TEXT,
                    exported_symbols TEXT NOT NULL DEFAULT '[]'
                );
                CREATE INDEX IF NOT EXISTS idx_projects_workspace_id ON projects(workspace_id);
                """
            )

    def create_workspace(self, name: str, root_path: str) -> Workspace:
        workspace = Workspace(id=str(uuid.uuid4()), name=name, root_path=root_path)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO workspaces (id, name, root_path, created_at) VALUES (?, ?, ?, ?)",
                (workspace.id, workspace.name, workspace.root_path, workspace.created_at),
            )
        return workspace

    def list_workspaces(self) -> list[Workspace]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, root_path, created_at FROM workspaces ORDER BY created_at DESC"
            ).fetchall()
        return [
            Workspace(
                id=row["id"],
                name=row["name"],
                root_path=row["root_path"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, name, root_path, created_at FROM workspaces WHERE id = ?",
                (workspace_id,),
            ).fetchone()
        if not row:
            return None
        return Workspace(
            id=row["id"],
            name=row["name"],
            root_path=row["root_path"],
            created_at=row["created_at"],
        )

    def delete_workspace(self, workspace_id: str) -> bool:
        with self._lock, self._connect() as conn:
            deleted = conn.execute(
                "DELETE FROM workspaces WHERE id = ?",
                (workspace_id,),
            ).rowcount
        return deleted > 0

    def create_project(
        self,
        workspace_id: str,
        name: str,
        path: str,
        project_type: ProjectType,
    ) -> Project:
        now = time.time()
        project = Project(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            name=name,
            path=path,
            type=project_type,
            created_at=now,
            updated_at=now,
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    id, workspace_id, name, path, type, status, created_at, updated_at, last_error, exported_symbols
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.workspace_id,
                    project.name,
                    project.path,
                    project.type,
                    project.status,
                    project.created_at,
                    project.updated_at,
                    project.last_error,
                    json.dumps(project.exported_symbols),
                ),
            )
        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return None
        return self._project_from_row(row)

    def list_projects(self, workspace_id: Optional[str] = None) -> list[Project]:
        with self._connect() as conn:
            if workspace_id:
                rows = conn.execute(
                    "SELECT * FROM projects WHERE workspace_id = ? ORDER BY created_at",
                    (workspace_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM projects ORDER BY created_at").fetchall()
        return [self._project_from_row(row) for row in rows]

    def update_project_status(
        self,
        project_id: str,
        status: ProjectStatus,
        last_error: Optional[str] = None,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE projects
                SET status = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, last_error, time.time(), project_id),
            )

    def update_exported_symbols(self, project_id: str, symbols: list[str]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE projects
                SET exported_symbols = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(symbols), time.time(), project_id),
            )

    def delete_project(self, project_id: str) -> bool:
        with self._lock, self._connect() as conn:
            deleted = conn.execute(
                "DELETE FROM projects WHERE id = ?",
                (project_id,),
            ).rowcount
        return deleted > 0

    def get_sibling_projects(self, project_id: str) -> list[Project]:
        origin = self.get_project(project_id)
        if not origin:
            return []
        return [p for p in self.list_projects(origin.workspace_id) if p.id != project_id]

    @staticmethod
    def _project_from_row(row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            workspace_id=row["workspace_id"],
            name=row["name"],
            path=row["path"],
            type=row["type"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_error=row["last_error"],
            exported_symbols=json.loads(row["exported_symbols"] or "[]"),
        )
