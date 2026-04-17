"""
ProjectRegistry — Registro central de Workspaces e Projetos vinculados.

Modelo:
  Workspace  →  agrupa N projetos de um mesmo produto
  Project    →  um sub-diretório monitorado (backend / frontend / mobile / etc.)

Um Workspace é a "PastaProduto" do usuário.  Todos os projetos dentro dele
compartilham o mesmo grafo de impacto cross-projeto.

Persistência: SQLite (insightgraph_state.db) — tabelas workspace / project.
"""

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

logger = logging.getLogger("insightgraph.registry")

ProjectStatus = Literal["idle", "watching", "scanning", "error"]
ProjectType   = Literal["backend", "frontend", "mobile", "shared", "other"]


# ─────────────────────────────────────────────
# Modelos
# ─────────────────────────────────────────────

@dataclass
class Project:
    id: str
    workspace_id: str
    name: str
    path: str                          # caminho absoluto no disco
    type: ProjectType = "other"
    status: ProjectStatus = "idle"
    watch_interval: int = 5            # segundos entre polls de arquivo
    git_poll_interval: int = 30        # segundos entre checagens de commit
    last_scanned_at: Optional[float] = None
    last_commit: Optional[str] = None
    error_message: Optional[str] = None
    # Nós exportados publicamente (cross-project boundary)
    exported_symbols: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: tuple) -> "Project":
        (id_, ws_id, name, path, ptype, status, watch_iv, git_iv,
         last_scan, last_commit, err_msg, exported, created_at) = row
        return cls(
            id=id_, workspace_id=ws_id, name=name, path=path,
            type=ptype, status=status, watch_interval=watch_iv,
            git_poll_interval=git_iv, last_scanned_at=last_scan,
            last_commit=last_commit, error_message=err_msg,
            exported_symbols=json.loads(exported or "[]"),
            created_at=created_at,
        )


@dataclass
class Workspace:
    id: str
    name: str
    root_path: str                     # PastaProduto
    description: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: tuple) -> "Workspace":
        id_, name, root_path, desc, created_at = row
        return cls(id=id_, name=name, root_path=root_path,
                   description=desc, created_at=created_at)


# ─────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────

class ProjectRegistry:
    """
    CRUD persistido de Workspaces e Projects.

    Thread-safe via _lock.  Inicializa tabelas no primeiro uso.
    """

    def __init__(self, db_path: str = "insightgraph_state.db"):
        self._db = Path(db_path)
        self._lock = threading.Lock()
        self._init_db()

    # ── Init ──────────────────────────────────

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS workspaces (
                    id          TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    root_path   TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    created_at  REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id               TEXT PRIMARY KEY,
                    workspace_id     TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    name             TEXT NOT NULL,
                    path             TEXT NOT NULL,
                    type             TEXT NOT NULL DEFAULT 'other',
                    status           TEXT NOT NULL DEFAULT 'idle',
                    watch_interval   INTEGER NOT NULL DEFAULT 5,
                    git_poll_interval INTEGER NOT NULL DEFAULT 30,
                    last_scanned_at  REAL,
                    last_commit      TEXT,
                    error_message    TEXT,
                    exported_symbols TEXT DEFAULT '[]',
                    created_at       REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_projects_workspace
                    ON projects(workspace_id);
            """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ── Workspaces ────────────────────────────

    def create_workspace(self, name: str, root_path: str, description: str = "") -> Workspace:
        ws = Workspace(id=str(uuid.uuid4()), name=name,
                       root_path=root_path, description=description)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO workspaces VALUES (?,?,?,?,?)",
                (ws.id, ws.name, ws.root_path, ws.description, ws.created_at),
            )
        logger.info("Workspace criado: %s (%s)", ws.name, ws.id)
        return ws

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id,name,root_path,description,created_at FROM workspaces WHERE id=?",
                (workspace_id,),
            ).fetchone()
        return Workspace.from_row(tuple(row)) if row else None

    def list_workspaces(self) -> list[Workspace]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id,name,root_path,description,created_at FROM workspaces ORDER BY created_at"
            ).fetchall()
        return [Workspace.from_row(tuple(r)) for r in rows]

    def delete_workspace(self, workspace_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM workspaces WHERE id=?", (workspace_id,))
        return cur.rowcount > 0

    # ── Projects ──────────────────────────────

    def create_project(
        self,
        workspace_id: str,
        name: str,
        path: str,
        type: ProjectType = "other",
        watch_interval: int = 5,
        git_poll_interval: int = 30,
    ) -> Project:
        p = Project(
            id=str(uuid.uuid4()), workspace_id=workspace_id,
            name=name, path=path, type=type,
            watch_interval=watch_interval, git_poll_interval=git_poll_interval,
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO projects
                   (id,workspace_id,name,path,type,status,watch_interval,
                    git_poll_interval,last_scanned_at,last_commit,
                    error_message,exported_symbols,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (p.id, p.workspace_id, p.name, p.path, p.type, p.status,
                 p.watch_interval, p.git_poll_interval, p.last_scanned_at,
                 p.last_commit, p.error_message,
                 json.dumps(p.exported_symbols), p.created_at),
            )
        logger.info("Project criado: %s (%s) em workspace %s", p.name, p.id, workspace_id)
        return p

    def get_project(self, project_id: str) -> Optional[Project]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id=?", (project_id,)
            ).fetchone()
        return Project.from_row(tuple(row)) if row else None

    def list_projects(self, workspace_id: str) -> list[Project]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM projects WHERE workspace_id=? ORDER BY created_at",
                (workspace_id,),
            ).fetchall()
        return [Project.from_row(tuple(r)) for r in rows]

    def update_project_status(
        self, project_id: str, status: ProjectStatus,
        error_message: Optional[str] = None,
    ):
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE projects SET status=?, error_message=? WHERE id=?",
                (status, error_message, project_id),
            )

    def update_project_commit(self, project_id: str, commit: str):
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE projects SET last_commit=?, last_scanned_at=? WHERE id=?",
                (commit, time.time(), project_id),
            )

    def update_exported_symbols(self, project_id: str, symbols: list[str]):
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE projects SET exported_symbols=? WHERE id=?",
                (json.dumps(symbols), project_id),
            )

    def delete_project(self, project_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        return cur.rowcount > 0

    def get_sibling_projects(self, project_id: str) -> list[Project]:
        """Retorna todos os projetos do mesmo workspace (exceto ele mesmo)."""
        p = self.get_project(project_id)
        if not p:
            return []
        siblings = self.list_projects(p.workspace_id)
        return [s for s in siblings if s.id != project_id]
