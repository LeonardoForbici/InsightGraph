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
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS demo_sessions (
                        session_id TEXT PRIMARY KEY,
                        repo_url TEXT,
                        temp_dir TEXT,
                        created_at REAL,
                        expires_at REAL,
                        ask_used INTEGER DEFAULT 0
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_demo_sessions_expires ON demo_sessions(expires_at)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS analysis_snapshots (
                        id TEXT PRIMARY KEY,
                        timestamp REAL NOT NULL,
                        total_nodes INTEGER,
                        total_edges INTEGER,
                        god_classes INTEGER,
                        circular_deps INTEGER,
                        dead_code INTEGER,
                        call_resolution_rate REAL,
                        metrics_json TEXT,
                        created_at REAL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON analysis_snapshots(timestamp)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS architectural_decisions (
                        id TEXT PRIMARY KEY,
                        node_key TEXT NOT NULL,
                        decision_type TEXT NOT NULL,
                        description TEXT,
                        author TEXT,
                        created_at REAL,
                        is_active INTEGER DEFAULT 1
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_decisions_node_key ON architectural_decisions(node_key)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_decisions_type ON architectural_decisions(decision_type)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS refactor_suggestions (
                        id TEXT PRIMARY KEY,
                        node_key TEXT NOT NULL,
                        original_code TEXT,
                        suggested_code TEXT,
                        test_code TEXT,
                        problems_json TEXT,
                        dependents_json TEXT,
                        effort_estimate TEXT,
                        created_at REAL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_refactor_node_key ON refactor_suggestions(node_key)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_alerts (
                        id TEXT PRIMARY KEY,
                        antipattern_type TEXT NOT NULL,
                        node_key TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        resolved INTEGER DEFAULT 0,
                        resolved_by TEXT,
                        resolved_at REAL,
                        created_at REAL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_alerts_resolved ON audit_alerts(resolved)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_alerts_severity ON audit_alerts(severity)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_alerts_node_key ON audit_alerts(node_key)"
                )
                # Task 12.5 — Tenants table for multi-tenant management
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tenants (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        display_name TEXT,
                        created_at REAL NOT NULL,
                        is_active INTEGER DEFAULT 1
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tenants_name ON tenants(name)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tenants_active ON tenants(is_active)"
                )
                # Task 13.6 — Report history table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS report_history (
                        id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        file_size INTEGER,
                        project TEXT,
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_report_history_project ON report_history(project)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_report_history_created ON report_history(created_at)"
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

    # ──────────────────────────────────────────────
    # Demo Sessions
    # ──────────────────────────────────────────────

    def create_demo_session(
        self,
        session_id: str,
        repo_url: str,
        temp_dir: str,
        expires_at: float,
    ) -> dict[str, Any]:
        """Insert a new demo session record."""
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO demo_sessions(session_id, repo_url, temp_dir, created_at, expires_at, ask_used)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (session_id, repo_url, temp_dir, now, expires_at),
            )
            conn.commit()
        return self.get_demo_session(session_id)

    def get_demo_session(self, session_id: str) -> dict[str, Any] | None:
        """Return a demo session by session_id, or None if not found."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM demo_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "session_id": row["session_id"],
            "repo_url": row["repo_url"],
            "temp_dir": row["temp_dir"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "ask_used": row["ask_used"],
        }

    def delete_demo_session(self, session_id: str) -> bool:
        """Delete a demo session record. Returns True if a row was deleted."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM demo_sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
        return cur.rowcount > 0

    def mark_ask_used(self, session_id: str) -> bool:
        """Set ask_used = 1 for the given session. Returns True if updated."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE demo_sessions SET ask_used = 1 WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
        return cur.rowcount > 0

    def get_expired_sessions(self) -> list[dict[str, Any]]:
        """Return all sessions whose expires_at is in the past."""
        now = self._now()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM demo_sessions WHERE expires_at < ?",
                (now,),
            ).fetchall()
        return [
            {
                "session_id": r["session_id"],
                "repo_url": r["repo_url"],
                "temp_dir": r["temp_dir"],
                "created_at": r["created_at"],
                "expires_at": r["expires_at"],
                "ask_used": r["ask_used"],
            }
            for r in rows
        ]

    # ──────────────────────────────────────────────
    # Analysis Snapshots
    # ──────────────────────────────────────────────

    def save_snapshot(self, snapshot: dict) -> dict:
        """Insert a new analysis snapshot and return it."""
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO analysis_snapshots(
                    id, timestamp, total_nodes, total_edges,
                    god_classes, circular_deps, dead_code,
                    call_resolution_rate, metrics_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot["id"],
                    snapshot.get("timestamp", now),
                    snapshot.get("total_nodes"),
                    snapshot.get("total_edges"),
                    snapshot.get("god_classes"),
                    snapshot.get("circular_deps"),
                    snapshot.get("dead_code"),
                    snapshot.get("call_resolution_rate"),
                    json.dumps(snapshot.get("metrics", {}), ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()
        return self.get_snapshot_by_id(snapshot["id"]) or snapshot

    def get_snapshots(self, page: int = 1, limit: int = 20) -> list[dict]:
        """Return paginated snapshots ordered by timestamp descending."""
        offset = (max(page, 1) - 1) * limit
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM analysis_snapshots
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [self._decode_snapshot_row(r) for r in rows]

    def get_snapshot_by_id(self, snapshot_id: str) -> dict | None:
        """Return a single snapshot by ID, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM analysis_snapshots WHERE id = ?",
                (snapshot_id,),
            ).fetchone()
        if not row:
            return None
        return self._decode_snapshot_row(row)

    def count_snapshots(self) -> int:
        """Return total number of snapshots."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM analysis_snapshots").fetchone()
        return row["cnt"] if row else 0

    def delete_oldest_snapshots(self, keep: int) -> int:
        """Delete oldest snapshots keeping only the `keep` most recent. Returns deleted count."""
        with self._connect() as conn:
            cur = conn.execute(
                """
                DELETE FROM analysis_snapshots
                WHERE id NOT IN (
                    SELECT id FROM analysis_snapshots
                    ORDER BY timestamp DESC
                    LIMIT ?
                )
                """,
                (keep,),
            )
            conn.commit()
        return cur.rowcount

    def _decode_snapshot_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "total_nodes": row["total_nodes"],
            "total_edges": row["total_edges"],
            "god_classes": row["god_classes"],
            "circular_deps": row["circular_deps"],
            "dead_code": row["dead_code"],
            "call_resolution_rate": row["call_resolution_rate"],
            "metrics": json.loads(row["metrics_json"] or "{}"),
            "created_at": row["created_at"],
        }

    # ──────────────────────────────────────────────
    # Architectural Decisions
    # ──────────────────────────────────────────────

    def save_decision(self, decision: dict) -> dict:
        """Insert a new architectural decision and return it."""
        decision_id = decision.get("id") or str(uuid.uuid4())
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO architectural_decisions(id, node_key, decision_type, description, author, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    decision_id,
                    decision["node_key"],
                    decision["decision_type"],
                    decision.get("description"),
                    decision.get("author"),
                    decision.get("created_at", now),
                ),
            )
            conn.commit()
        return self.get_decision_by_id(decision_id) or {**decision, "id": decision_id}

    def get_decisions(
        self,
        node_key: str | None = None,
        decision_type: str | None = None,
    ) -> list[dict]:
        """Return active decisions, optionally filtered by node_key and/or decision_type."""
        query = "SELECT * FROM architectural_decisions WHERE is_active = 1"
        params: list[Any] = []
        if node_key:
            query += " AND node_key = ?"
            params.append(node_key)
        if decision_type:
            query += " AND decision_type = ?"
            params.append(decision_type)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._decode_decision_row(r) for r in rows]

    def get_decision_by_id(self, decision_id: str) -> dict | None:
        """Return a single decision by ID, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM architectural_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
        if not row:
            return None
        return self._decode_decision_row(row)

    def delete_decision(self, decision_id: str) -> bool:
        """Soft-delete a decision (sets is_active = 0). Returns True if updated."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE architectural_decisions SET is_active = 0 WHERE id = ? AND is_active = 1",
                (decision_id,),
            )
            conn.commit()
        return cur.rowcount > 0

    def get_active_exceptions(self) -> list[str]:
        """Return list of node_keys that have an active 'excecao' decision."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT node_key FROM architectural_decisions WHERE decision_type = 'excecao' AND is_active = 1"
            ).fetchall()
        return [r["node_key"] for r in rows]

    def _decode_decision_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "node_key": row["node_key"],
            "decision_type": row["decision_type"],
            "description": row["description"],
            "author": row["author"],
            "created_at": row["created_at"],
            "is_active": bool(row["is_active"]),
        }

    # ──────────────────────────────────────────────
    # Refactor Suggestions
    # ──────────────────────────────────────────────

    def save_refactor_suggestion(self, suggestion: dict) -> dict:
        """Insert a new refactor suggestion and return it."""
        suggestion_id = suggestion.get("id") or str(uuid.uuid4())
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO refactor_suggestions(
                    id, node_key, original_code, suggested_code, test_code,
                    problems_json, dependents_json, effort_estimate, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    suggestion_id,
                    suggestion["node_key"],
                    suggestion.get("original_code"),
                    suggestion.get("suggested_code"),
                    suggestion.get("test_code"),
                    suggestion.get("problems_json") or json.dumps(suggestion.get("problems", [])),
                    suggestion.get("dependents_json") or json.dumps(suggestion.get("dependents_to_update", [])),
                    suggestion.get("effort_estimate"),
                    suggestion.get("created_at", now),
                ),
            )
            conn.commit()
        return self._get_refactor_suggestion_by_id(suggestion_id) or suggestion

    def get_refactor_suggestions(self, node_key: str | None = None) -> list[dict]:
        """Return refactor suggestions, optionally filtered by node_key."""
        query = "SELECT * FROM refactor_suggestions"
        params: list[Any] = []
        if node_key:
            query += " WHERE node_key = ?"
            params.append(node_key)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._decode_refactor_row(r) for r in rows]

    def _get_refactor_suggestion_by_id(self, suggestion_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM refactor_suggestions WHERE id = ?",
                (suggestion_id,),
            ).fetchone()
        if not row:
            return None
        return self._decode_refactor_row(row)

    def _decode_refactor_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "node_key": row["node_key"],
            "original_code": row["original_code"],
            "suggested_code": row["suggested_code"],
            "test_code": row["test_code"],
            "problems": json.loads(row["problems_json"] or "[]"),
            "dependents_to_update": json.loads(row["dependents_json"] or "[]"),
            "effort_estimate": row["effort_estimate"],
            "created_at": row["created_at"],
        }

    # ──────────────────────────────────────────────
    # Audit Alerts
    # ──────────────────────────────────────────────

    def save_alert(self, alert: dict) -> dict:
        """Insert a new audit alert and return it."""
        alert_id = alert.get("id") or str(uuid.uuid4())
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_alerts(
                    id, antipattern_type, node_key, severity,
                    resolved, resolved_by, resolved_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert_id,
                    alert["antipattern_type"],
                    alert["node_key"],
                    alert["severity"],
                    alert.get("resolved", 0),
                    alert.get("resolved_by"),
                    alert.get("resolved_at"),
                    alert.get("created_at", now),
                ),
            )
            conn.commit()
        return self.get_alert_by_id(alert_id) or alert

    def get_alert_by_id(self, alert_id: str) -> dict | None:
        """Return a single alert by ID, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM audit_alerts WHERE id = ?",
                (alert_id,),
            ).fetchone()
        if not row:
            return None
        return self._decode_alert_row(row)

    def get_unresolved_alerts(
        self,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return unresolved alerts, optionally filtered by severity."""
        query = "SELECT * FROM audit_alerts WHERE resolved = 0"
        params: list[Any] = []
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        query += " ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 WHEN 'low' THEN 4 ELSE 5 END, created_at DESC"
        query += " LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._decode_alert_row(r) for r in rows]

    def resolve_alert(self, alert_id: str, resolved_by: str) -> bool:
        """Mark an alert as resolved. Returns True if updated."""
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE audit_alerts
                SET resolved = 1, resolved_by = ?, resolved_at = ?
                WHERE id = ?
                """,
                (resolved_by, now, alert_id),
            )
            conn.commit()
        return cur.rowcount > 0

    def count_unresolved_alerts(self) -> int:
        """Return count of unresolved alerts."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM audit_alerts WHERE resolved = 0"
            ).fetchone()
        return row["cnt"] if row else 0

    def _decode_alert_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "antipattern_type": row["antipattern_type"],
            "node_key": row["node_key"],
            "severity": row["severity"],
            "resolved": bool(row["resolved"]),
            "resolved_by": row["resolved_by"],
            "resolved_at": row["resolved_at"],
            "created_at": row["created_at"],
        }

    # ──────────────────────────────────────────────
    # Tenants (Task 12.5)
    # ──────────────────────────────────────────────

    def create_tenant(self, name: str, display_name: str | None = None) -> dict:
        """Create a new tenant. Returns the created tenant record."""
        tenant_id = str(uuid.uuid4())
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tenants(id, name, display_name, created_at, is_active)
                VALUES (?, ?, ?, ?, 1)
                """,
                (tenant_id, name, display_name, now),
            )
            conn.commit()
        return self.get_tenant_by_id(tenant_id) or {"id": tenant_id, "name": name, "display_name": display_name}

    def get_tenant_by_id(self, tenant_id: str) -> dict | None:
        """Return a tenant by ID, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tenants WHERE id = ?",
                (tenant_id,),
            ).fetchone()
        if not row:
            return None
        return self._decode_tenant_row(row)

    def get_tenant_by_name(self, name: str) -> dict | None:
        """Return a tenant by name, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tenants WHERE name = ?",
                (name,),
            ).fetchone()
        if not row:
            return None
        return self._decode_tenant_row(row)

    def list_tenants(self, active_only: bool = True) -> list[dict]:
        """Return all tenants, optionally filtered by active status."""
        query = "SELECT * FROM tenants"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY name"
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()
        return [self._decode_tenant_row(r) for r in rows]

    def update_tenant(self, tenant_id: str, display_name: str | None = None, is_active: bool | None = None) -> dict | None:
        """Update tenant display_name and/or is_active status."""
        current = self.get_tenant_by_id(tenant_id)
        if not current:
            return None
        
        updates = []
        params = []
        if display_name is not None:
            updates.append("display_name = ?")
            params.append(display_name)
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if is_active else 0)
        
        if not updates:
            return current
        
        params.append(tenant_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE tenants SET {', '.join(updates)} WHERE id = ?",
                tuple(params),
            )
            conn.commit()
        return self.get_tenant_by_id(tenant_id)

    def delete_tenant(self, tenant_id: str) -> bool:
        """Soft-delete a tenant (sets is_active = 0). Returns True if updated."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE tenants SET is_active = 0 WHERE id = ?",
                (tenant_id,),
            )
            conn.commit()
        return cur.rowcount > 0

    def _decode_tenant_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "display_name": row["display_name"],
            "created_at": row["created_at"],
            "is_active": bool(row["is_active"]),
        }

    # ──────────────────────────────────────────────
    # Report History (Task 13.6)
    # ──────────────────────────────────────────────

    def save_report(self, filename: str, file_path: str, file_size: int, project: str | None = None) -> dict:
        """Save a report generation record."""
        report_id = str(uuid.uuid4())
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO report_history(id, filename, file_path, file_size, project, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (report_id, filename, file_path, file_size, project, now),
            )
            conn.commit()
        return self.get_report_by_id(report_id) or {"id": report_id, "filename": filename}

    def get_report_by_id(self, report_id: str) -> dict | None:
        """Return a report by ID, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM report_history WHERE id = ?",
                (report_id,),
            ).fetchone()
        if not row:
            return None
        return self._decode_report_row(row)

    def list_reports(self, project: str | None = None) -> list[dict]:
        """Return all reports, optionally filtered by project."""
        query = "SELECT * FROM report_history"
        params: tuple = ()
        if project:
            query += " WHERE project = ?"
            params = (project,)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._decode_report_row(r) for r in rows]

    def _decode_report_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "filename": row["filename"],
            "file_path": row["file_path"],
            "file_size": row["file_size"],
            "project": row["project"],
            "created_at": row["created_at"],
        }
