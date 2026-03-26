import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Sequence


class LocalStateStore:
    """SQLite-backed store for persistent app state and knowledge-layer entities."""

    def __init__(self, db_path: str = "insightgraph_state.db"):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_state (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at REAL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS saved_views (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT,
                        project TEXT,
                        filters_json TEXT NOT NULL,
                        reactflow_json TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tags (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        color TEXT,
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS annotations (
                        id TEXT PRIMARY KEY,
                        node_key TEXT NOT NULL,
                        title TEXT,
                        content TEXT NOT NULL,
                        severity TEXT,
                        tag_id TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        FOREIGN KEY(tag_id) REFERENCES tags(id)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_annotations_node_key ON annotations(node_key)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS object_embeddings (
                        object_key TEXT PRIMARY KEY,
                        object_type TEXT,
                        summary TEXT,
                        embedding_json TEXT,
                        model TEXT,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS codeql_jobs (
                        job_id TEXT PRIMARY KEY,
                        project_id TEXT,
                        suite TEXT,
                        status TEXT,
                        details_json TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_codeql_jobs_project ON codeql_jobs(project_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_codeql_jobs_status ON codeql_jobs(status)"
                )
                conn.commit()
            self._initialized = True

    def _now(self) -> float:
        return time.time()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def set_state(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        ts = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_state(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, payload, ts),
            )
            conn.commit()

    def get_state(self, key: str, default: Any = None) -> Any:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_state WHERE key = ?",
                (key,),
            ).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return default

    def persist_scan_status(self, payload: dict[str, Any]) -> None:
        """Persist the latest scan state so restarts can resume awareness."""
        self.set_state("scan_status", payload)

    def load_scan_status(self) -> dict[str, Any] | None:
        """Return the last scan status, if any."""
        return self.get_state("scan_status")

    def create_view(self, payload: dict[str, Any]) -> dict[str, Any]:
        view_id = str(uuid.uuid4())
        ts = self._now()
        record = {
            "id": view_id,
            "name": str(payload.get("name") or "").strip(),
            "description": payload.get("description"),
            "project": payload.get("project"),
            "filters_json": json.dumps(payload.get("filters") or {}, ensure_ascii=False),
            "reactflow_json": json.dumps(payload.get("reactflow_state") or {}, ensure_ascii=False),
            "created_at": ts,
            "updated_at": ts,
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO saved_views(id, name, description, project, filters_json, reactflow_json, created_at, updated_at)
                VALUES (:id, :name, :description, :project, :filters_json, :reactflow_json, :created_at, :updated_at)
                """,
                record,
            )
            conn.commit()
        return self.get_view(view_id)

    def list_views(self, project: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM saved_views"
        params: tuple[Any, ...] = ()
        if project:
            query += " WHERE project = ?"
            params = (project,)
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._decode_view_row(r) for r in rows]

    def get_view(self, view_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM saved_views WHERE id = ?",
                (view_id,),
            ).fetchone()
        if not row:
            return None
        return self._decode_view_row(row)

    def update_view(self, view_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        current = self.get_view(view_id)
        if not current:
            return None
        merged = {
            "name": patch.get("name", current["name"]),
            "description": patch.get("description", current.get("description")),
            "project": patch.get("project", current.get("project")),
            "filters": patch.get("filters", current.get("filters") or {}),
            "reactflow_state": patch.get("reactflow_state", current.get("reactflow_state") or {}),
        }
        ts = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE saved_views
                SET name = ?, description = ?, project = ?, filters_json = ?, reactflow_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    merged["name"],
                    merged["description"],
                    merged["project"],
                    json.dumps(merged["filters"], ensure_ascii=False),
                    json.dumps(merged["reactflow_state"], ensure_ascii=False),
                    ts,
                    view_id,
                ),
            )
            conn.commit()
        return self.get_view(view_id)

    def delete_view(self, view_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM saved_views WHERE id = ?", (view_id,))
            conn.commit()
        return cur.rowcount > 0

    def _decode_view_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "project": row["project"],
            "filters": json.loads(row["filters_json"] or "{}"),
            "reactflow_state": json.loads(row["reactflow_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def upsert_tag(self, name: str, color: str | None = None) -> dict[str, Any]:
        clean_name = name.strip()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tags WHERE name = ?", (clean_name,)).fetchone()
            if row:
                if color is not None:
                    conn.execute("UPDATE tags SET color = ? WHERE id = ?", (color, row["id"]))
                    conn.commit()
                return self.get_tag(row["id"]) or {"id": row["id"], "name": clean_name, "color": color}
            tag_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO tags(id, name, color, created_at) VALUES (?, ?, ?, ?)",
                (tag_id, clean_name, color, self._now()),
            )
            conn.commit()
        return self.get_tag(tag_id) or {"id": tag_id, "name": clean_name, "color": color}

    def get_tag(self, tag_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
        if not row:
            return None
        return {"id": row["id"], "name": row["name"], "color": row["color"], "created_at": row["created_at"]}

    def list_tags(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM tags ORDER BY name").fetchall()
        return [{"id": r["id"], "name": r["name"], "color": r["color"], "created_at": r["created_at"]} for r in rows]

    def create_annotation(self, payload: dict[str, Any]) -> dict[str, Any]:
        annotation_id = str(uuid.uuid4())
        tag_id = payload.get("tag_id")
        tag_name = payload.get("tag")
        if (not tag_id) and tag_name:
            tag = self.upsert_tag(str(tag_name), payload.get("tag_color"))
            tag_id = tag["id"]
        ts = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO annotations(id, node_key, title, content, severity, tag_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    annotation_id,
                    payload["node_key"],
                    payload.get("title"),
                    payload.get("content") or "",
                    payload.get("severity"),
                    tag_id,
                    ts,
                    ts,
                ),
            )
            conn.commit()
        return self.get_annotation(annotation_id) or {"id": annotation_id}

    def get_annotation(self, annotation_id: str) -> dict[str, Any] | None:
        query = """
        SELECT a.*, t.name AS tag_name, t.color AS tag_color
        FROM annotations a
        LEFT JOIN tags t ON t.id = a.tag_id
        WHERE a.id = ?
        """
        with self._connect() as conn:
            row = conn.execute(query, (annotation_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "node_key": row["node_key"],
            "title": row["title"],
            "content": row["content"],
            "severity": row["severity"],
            "tag_id": row["tag_id"],
            "tag": row["tag_name"],
            "tag_color": row["tag_color"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_annotations(self, node_key: str | None = None) -> list[dict[str, Any]]:
        query = """
        SELECT a.*, t.name AS tag_name, t.color AS tag_color
        FROM annotations a
        LEFT JOIN tags t ON t.id = a.tag_id
        """
        params: tuple[Any, ...] = ()
        if node_key:
            query += " WHERE a.node_key = ?"
            params = (node_key,)
        query += " ORDER BY a.updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": r["id"],
                "node_key": r["node_key"],
                "title": r["title"],
                "content": r["content"],
                "severity": r["severity"],
                "tag_id": r["tag_id"],
                "tag": r["tag_name"],
                "tag_color": r["tag_color"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    def update_annotation(self, annotation_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        current = self.get_annotation(annotation_id)
        if not current:
            return None
        tag_id = patch.get("tag_id", current.get("tag_id"))
        if (not tag_id) and patch.get("tag"):
            tag_id = self.upsert_tag(str(patch["tag"]), patch.get("tag_color")).get("id")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE annotations
                SET title = ?, content = ?, severity = ?, tag_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    patch.get("title", current.get("title")),
                    patch.get("content", current.get("content")),
                    patch.get("severity", current.get("severity")),
                    tag_id,
                    self._now(),
                    annotation_id,
                ),
            )
            conn.commit()
        return self.get_annotation(annotation_id)

    def delete_annotation(self, annotation_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM annotations WHERE id = ?", (annotation_id,))
            conn.commit()
        return cur.rowcount > 0

    def upsert_embedding(
        self,
        object_key: str,
        object_type: str | None,
        summary: str | None,
        embedding: list[float] | None,
        model: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO object_embeddings(object_key, object_type, summary, embedding_json, model, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(object_key) DO UPDATE SET
                    object_type = excluded.object_type,
                    summary = excluded.summary,
                    embedding_json = excluded.embedding_json,
                    model = excluded.model,
                    updated_at = excluded.updated_at
                """,
                (
                    object_key,
                    object_type,
                    summary,
                    json.dumps(embedding if embedding is not None else []),
                    model,
                    self._now(),
                ),
            )
            conn.commit()

    def get_embedding(self, object_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM object_embeddings WHERE object_key = ?",
                (object_key,),
            ).fetchone()
        if not row:
            return None
        return {
            "object_key": row["object_key"],
            "object_type": row["object_type"],
            "summary": row["summary"],
            "embedding": json.loads(row["embedding_json"] or "[]"),
            "model": row["model"],
            "updated_at": row["updated_at"],
        }

    def upsert_codeql_job(
        self,
        job_id: str,
        project_id: str | None = None,
        suite: str | None = None,
        status: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Keep a durable record of CodeQL jobs so long-running work survives restarts."""
        now = self._now()
        payload = json.dumps(details or {}, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO codeql_jobs(job_id, project_id, suite, status, details_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    project_id = excluded.project_id,
                    suite = excluded.suite,
                    status = excluded.status,
                    details_json = excluded.details_json,
                    updated_at = excluded.updated_at
                """,
                (job_id, project_id, suite, status, payload, now, now),
            )
            conn.commit()

    def get_codeql_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM codeql_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if not row:
            return None
        return self._decode_codeql_job_row(row)

    def list_codeql_jobs(
        self,
        project_id: str | None = None,
        statuses: Sequence[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM codeql_jobs"
        clauses: list[str] = []
        params: list[Any] = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if statuses:
            clauses.extend(["status = ?"] * len(statuses))
            params.extend(statuses)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._decode_codeql_job_row(r) for r in rows]

    def delete_codeql_job(self, job_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM codeql_jobs WHERE job_id = ?", (job_id,))
            conn.commit()
        return cur.rowcount > 0

    def _decode_codeql_job_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": row["job_id"],
            "project_id": row["project_id"],
            "suite": row["suite"],
            "status": row["status"],
            "details": json.loads(row["details_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
