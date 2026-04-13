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
                        created_at REAL,
                        commit_hash TEXT,
                        branch TEXT,
                        author TEXT,
                        commit_message TEXT
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON analysis_snapshots(timestamp)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_snapshots_commit ON analysis_snapshots(commit_hash)"
                )
                # Stores the node-level state at each snapshot for graph diffing
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS snapshot_nodes (
                        snapshot_id TEXT NOT NULL,
                        namespace_key TEXT NOT NULL,
                        name TEXT,
                        node_type TEXT,
                        file TEXT,
                        layer TEXT,
                        complexity INTEGER,
                        coupling INTEGER,
                        extra_json TEXT,
                        PRIMARY KEY (snapshot_id, namespace_key),
                        FOREIGN KEY (snapshot_id) REFERENCES analysis_snapshots(id)
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_snap_nodes_snapshot ON snapshot_nodes(snapshot_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_snap_nodes_key ON snapshot_nodes(namespace_key)"
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
                # Fase 3 — Alert system: custom rules + fired alert history
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alert_rules (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT,
                        metric TEXT NOT NULL,
                        condition TEXT NOT NULL,
                        threshold REAL NOT NULL,
                        severity TEXT NOT NULL DEFAULT 'medium',
                        channel TEXT NOT NULL DEFAULT 'ui',
                        enabled INTEGER NOT NULL DEFAULT 1,
                        message_template TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(enabled)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS fired_alerts (
                        id TEXT PRIMARY KEY,
                        rule_id TEXT NOT NULL,
                        rule_name TEXT,
                        severity TEXT NOT NULL,
                        message TEXT NOT NULL,
                        metric TEXT,
                        value_before REAL,
                        value_after REAL,
                        delta REAL,
                        snapshot_id TEXT,
                        commit_hash TEXT,
                        branch TEXT,
                        channels_notified TEXT,
                        fired_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_fired_alerts_fired_at ON fired_alerts(fired_at)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_fired_alerts_severity ON fired_alerts(severity)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_fired_alerts_rule ON fired_alerts(rule_id)"
                )
                # Fase 2 - CI/CD build status tracking
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cicd_builds (
                        id TEXT PRIMARY KEY,
                        provider TEXT NOT NULL,
                        status TEXT NOT NULL,
                        commit_hash TEXT NOT NULL,
                        branch TEXT,
                        build_id TEXT,
                        pipeline_id TEXT,
                        author TEXT,
                        coverage REAL,
                        duration_seconds REAL,
                        web_url TEXT,
                        stack_trace TEXT,
                        failed_files_json TEXT,
                        raw_payload_json TEXT,
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cicd_builds_commit ON cicd_builds(commit_hash)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cicd_builds_status ON cicd_builds(status)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cicd_builds_created ON cicd_builds(created_at)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cicd_build_nodes (
                        build_id TEXT NOT NULL,
                        node_key TEXT NOT NULL,
                        PRIMARY KEY (build_id, node_key),
                        FOREIGN KEY(build_id) REFERENCES cicd_builds(id)
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cicd_build_nodes_node ON cicd_build_nodes(node_key)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS collaboration_sessions (
                        session_id TEXT PRIMARY KEY,
                        created_by TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        active_node TEXT,
                        participants_json TEXT NOT NULL,
                        is_active INTEGER DEFAULT 1
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_collab_sessions_active ON collaboration_sessions(is_active)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS collaboration_annotations (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        node_key TEXT NOT NULL,
                        text TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        visibility TEXT NOT NULL DEFAULT 'public',
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_collab_annotations_node ON collaboration_annotations(node_key)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS collaboration_chat_messages (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        text TEXT NOT NULL,
                        context_json TEXT,
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_collab_chat_session ON collaboration_chat_messages(session_id, created_at)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS collaboration_session_events (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_collab_events_session ON collaboration_session_events(session_id, created_at)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS config_versions (
                        id TEXT PRIMARY KEY,
                        format TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_by TEXT,
                        source TEXT,
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_config_versions_created ON config_versions(created_at)"
                )
                # Fase 4 — Weekly digest history
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS weekly_digests (
                        id TEXT PRIMARY KEY,
                        week_start TEXT NOT NULL,
                        week_end TEXT NOT NULL,
                        summary_json TEXT NOT NULL,
                        narrative TEXT,
                        generated_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_digests_week ON weekly_digests(week_start)"
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
                    call_resolution_rate, metrics_json, created_at,
                    commit_hash, branch, author, commit_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    snapshot.get("commit_hash"),
                    snapshot.get("branch"),
                    snapshot.get("author"),
                    snapshot.get("commit_message"),
                ),
            )
            conn.commit()
        return self.get_snapshot_by_id(snapshot["id"]) or snapshot

    def get_snapshot_by_commit(self, commit_hash: str) -> dict | None:
        """Return the most recent snapshot taken at a specific commit, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM analysis_snapshots WHERE commit_hash = ? ORDER BY timestamp DESC LIMIT 1",
                (commit_hash,),
            ).fetchone()
        return self._decode_snapshot_row(row) if row else None

    def save_snapshot_nodes(self, snapshot_id: str, nodes: list[dict]) -> None:
        """Persist the node-level state for a snapshot (enables graph diffing)."""
        with self._connect() as conn:
            for node in nodes:
                ns_key = node.get("namespace_key")
                if not ns_key:
                    continue
                extra = {k: v for k, v in node.items()
                         if k not in {"namespace_key", "name", "type", "file", "layer", "complexity", "coupling"}}
                conn.execute(
                    """
                    INSERT OR REPLACE INTO snapshot_nodes(
                        snapshot_id, namespace_key, name, node_type,
                        file, layer, complexity, coupling, extra_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        ns_key,
                        node.get("name"),
                        node.get("type") or node.get("labels", [""])[0] if node.get("labels") else node.get("type"),
                        node.get("file"),
                        node.get("layer"),
                        node.get("complexity"),
                        node.get("coupling"),
                        json.dumps(extra, ensure_ascii=False, default=str),
                    ),
                )
            conn.commit()

    def get_snapshot_nodes(self, snapshot_id: str) -> list[dict]:
        """Return all nodes stored for a snapshot."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM snapshot_nodes WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchall()
        return [self._decode_snapshot_node_row(r) for r in rows]

    def diff_snapshot_nodes(self, from_id: str, to_id: str) -> dict:
        """
        Compare two snapshots at node level.
        Returns: added, removed, modified (node keys with changes), unchanged counts.
        """
        from_nodes = {n["namespace_key"]: n for n in self.get_snapshot_nodes(from_id)}
        to_nodes = {n["namespace_key"]: n for n in self.get_snapshot_nodes(to_id)}

        from_keys = set(from_nodes)
        to_keys = set(to_nodes)

        added_keys = to_keys - from_keys
        removed_keys = from_keys - to_keys
        common_keys = from_keys & to_keys

        modified = []
        unchanged = 0
        for key in common_keys:
            old = from_nodes[key]
            new = to_nodes[key]
            changes = {}
            for field in ("complexity", "coupling", "file", "layer"):
                if old.get(field) != new.get(field):
                    changes[field] = {"before": old.get(field), "after": new.get(field)}
            if changes:
                modified.append({"namespace_key": key, "name": new.get("name"), "changes": changes})
            else:
                unchanged += 1

        return {
            "added": [to_nodes[k] for k in added_keys],
            "removed": [from_nodes[k] for k in removed_keys],
            "modified": modified,
            "unchanged": unchanged,
            "summary": {
                "added_count": len(added_keys),
                "removed_count": len(removed_keys),
                "modified_count": len(modified),
                "unchanged_count": unchanged,
            },
        }

    def _decode_snapshot_node_row(self, row: sqlite3.Row) -> dict:
        extra = {}
        try:
            extra = json.loads(row["extra_json"] or "{}")
        except Exception:
            pass
        return {
            "namespace_key": row["namespace_key"],
            "name": row["name"],
            "type": row["node_type"],
            "file": row["file"],
            "layer": row["layer"],
            "complexity": row["complexity"],
            "coupling": row["coupling"],
            **extra,
        }

    # ──────────────────────────────────────────────
    # Fase 3 — Alert rules & fired alerts
    # ──────────────────────────────────────────────

    def upsert_alert_rule(self, rule: dict) -> None:
        """Create or update a custom alert rule."""
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alert_rules(
                    id, name, description, metric, condition, threshold,
                    severity, channel, enabled, message_template, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    metric = excluded.metric,
                    condition = excluded.condition,
                    threshold = excluded.threshold,
                    severity = excluded.severity,
                    channel = excluded.channel,
                    enabled = excluded.enabled,
                    message_template = excluded.message_template,
                    updated_at = excluded.updated_at
                """,
                (
                    rule["id"],
                    rule.get("name", rule["id"]),
                    rule.get("description"),
                    rule["metric"],
                    rule["condition"],
                    float(rule.get("threshold", 0)),
                    rule.get("severity", "medium"),
                    rule.get("channel", "ui"),
                    1 if rule.get("enabled", True) else 0,
                    rule.get("message_template"),
                    now,
                    now,
                ),
            )
            conn.commit()

    def list_alert_rules(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM alert_rules ORDER BY created_at DESC"
            ).fetchall()
        return [self._decode_alert_rule_row(r) for r in rows]

    def delete_alert_rule(self, rule_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
            conn.commit()
        return cur.rowcount > 0

    def save_fired_alert(self, alert: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO fired_alerts(
                    id, rule_id, rule_name, severity, message, metric,
                    value_before, value_after, delta, snapshot_id,
                    commit_hash, branch, channels_notified, fired_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert["id"],
                    alert["rule_id"],
                    alert.get("rule_name"),
                    alert["severity"],
                    alert["message"],
                    alert.get("metric"),
                    alert.get("value_before"),
                    alert.get("value_after"),
                    alert.get("delta"),
                    alert.get("snapshot_id"),
                    alert.get("commit_hash"),
                    alert.get("branch"),
                    json.dumps(alert.get("channels_notified", []), ensure_ascii=False),
                    alert.get("fired_at", self._now()),
                ),
            )
            conn.commit()

    def get_alert_history(self, page: int = 1, limit: int = 50) -> dict:
        offset = (max(page, 1) - 1) * limit
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM fired_alerts ORDER BY fired_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) AS cnt FROM fired_alerts").fetchone()["cnt"]
        return {
            "items": [self._decode_fired_alert_row(r) for r in rows],
            "total": total,
            "page": page,
            "limit": limit,
        }

    def _decode_alert_rule_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "metric": row["metric"],
            "condition": row["condition"],
            "threshold": row["threshold"],
            "severity": row["severity"],
            "channel": row["channel"],
            "enabled": bool(row["enabled"]),
            "message_template": row["message_template"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _decode_fired_alert_row(self, row: sqlite3.Row) -> dict:
        channels = []
        try:
            channels = json.loads(row["channels_notified"] or "[]")
        except Exception:
            pass
        return {
            "id": row["id"],
            "rule_id": row["rule_id"],
            "rule_name": row["rule_name"],
            "severity": row["severity"],
            "message": row["message"],
            "metric": row["metric"],
            "value_before": row["value_before"],
            "value_after": row["value_after"],
            "delta": row["delta"],
            "snapshot_id": row["snapshot_id"],
            "commit_hash": row["commit_hash"],
            "branch": row["branch"],
            "channels_notified": channels,
            "fired_at": row["fired_at"],
        }

    # ──────────────────────────────────────────────
    # Fase 4 — Weekly digest
    # ──────────────────────────────────────────────

    # CI/CD - Build status tracking

    def save_cicd_build(self, build: dict) -> dict:
        build_id = build.get("id") or str(uuid.uuid4())
        created_at = float(build.get("created_at") or self._now())
        failed_files = build.get("failed_files") or []
        failed_nodes = build.get("failed_nodes") or []

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cicd_builds(
                    id, provider, status, commit_hash, branch, build_id, pipeline_id, author,
                    coverage, duration_seconds, web_url, stack_trace, failed_files_json,
                    raw_payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    build_id,
                    build["provider"],
                    build["status"],
                    build["commit_hash"],
                    build.get("branch"),
                    build.get("build_id"),
                    build.get("pipeline_id"),
                    build.get("author"),
                    build.get("coverage"),
                    build.get("duration_seconds"),
                    build.get("web_url"),
                    build.get("stack_trace"),
                    json.dumps(failed_files, ensure_ascii=False),
                    json.dumps(build.get("raw_payload") or {}, ensure_ascii=False),
                    created_at,
                ),
            )

            conn.execute("DELETE FROM cicd_build_nodes WHERE build_id = ?", (build_id,))
            for node_key in failed_nodes:
                conn.execute(
                    "INSERT OR REPLACE INTO cicd_build_nodes(build_id, node_key) VALUES (?, ?)",
                    (build_id, node_key),
                )
            conn.commit()

        return self.get_cicd_build_by_id(build_id) or {"id": build_id}

    def get_cicd_build_by_id(self, build_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM cicd_builds WHERE id = ?",
                (build_id,),
            ).fetchone()
        if not row:
            return None
        return self._decode_cicd_build_row(row)

    def get_cicd_status(self, commit_hash: str) -> dict:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM cicd_builds WHERE commit_hash = ? ORDER BY created_at DESC",
                (commit_hash,),
            ).fetchall()
        items = [self._decode_cicd_build_row(r) for r in rows]
        latest = items[0] if items else None
        return {
            "commit_hash": commit_hash,
            "latest": latest,
            "history": items,
            "total": len(items),
        }

    def list_cicd_builds(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM cicd_builds ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [self._decode_cicd_build_row(r) for r in rows]

    def list_failed_nodes_latest(self) -> dict[str, dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT n.node_key, b.id, b.status, b.commit_hash, b.stack_trace, b.created_at
                FROM cicd_build_nodes n
                JOIN cicd_builds b ON b.id = n.build_id
                ORDER BY b.created_at DESC
                """
            ).fetchall()

        latest_by_node: dict[str, dict] = {}
        for row in rows:
            node_key = row["node_key"]
            if node_key in latest_by_node:
                continue
            latest_by_node[node_key] = {
                "build_record_id": row["id"],
                "status": row["status"],
                "commit_hash": row["commit_hash"],
                "stack_trace": row["stack_trace"],
                "created_at": row["created_at"],
            }
        return latest_by_node

    def _decode_cicd_build_row(self, row: sqlite3.Row) -> dict:
        failed_files: list[str] = []
        raw_payload: dict[str, Any] = {}
        try:
            failed_files = json.loads(row["failed_files_json"] or "[]")
        except Exception:
            pass
        try:
            raw_payload = json.loads(row["raw_payload_json"] or "{}")
        except Exception:
            pass
        return {
            "id": row["id"],
            "provider": row["provider"],
            "status": row["status"],
            "commit_hash": row["commit_hash"],
            "branch": row["branch"],
            "build_id": row["build_id"],
            "pipeline_id": row["pipeline_id"],
            "author": row["author"],
            "coverage": row["coverage"],
            "duration_seconds": row["duration_seconds"],
            "web_url": row["web_url"],
            "stack_trace": row["stack_trace"],
            "failed_files": failed_files,
            "raw_payload": raw_payload,
            "created_at": row["created_at"],
        }

    def save_weekly_digest(self, digest: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO weekly_digests(
                    id, week_start, week_end, summary_json, narrative, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    digest["id"],
                    digest["week_start"],
                    digest["week_end"],
                    json.dumps(digest.get("summary", {}), ensure_ascii=False, default=str),
                    digest.get("narrative"),
                    digest.get("generated_at", self._now()),
                ),
            )
            conn.commit()

    def list_weekly_digests(self, limit: int = 12) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM weekly_digests ORDER BY week_start DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._decode_digest_row(r) for r in rows]

    def _decode_digest_row(self, row: sqlite3.Row) -> dict:
        summary = {}
        try:
            summary = json.loads(row["summary_json"] or "{}")
        except Exception:
            pass
        return {
            "id": row["id"],
            "week_start": row["week_start"],
            "week_end": row["week_end"],
            "summary": summary,
            "narrative": row["narrative"],
            "generated_at": row["generated_at"],
        }

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
        keys = row.keys()
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
            "commit_hash": row["commit_hash"] if "commit_hash" in keys else None,
            "branch": row["branch"] if "branch" in keys else None,
            "author": row["author"] if "author" in keys else None,
            "commit_message": row["commit_message"] if "commit_message" in keys else None,
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

    # Collaboration manager persistence
    def create_collab_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        participants_json = json.dumps(payload.get("participants") or [], ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO collaboration_sessions(
                    session_id, created_by, created_at, active_node, participants_json, is_active
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["session_id"],
                    payload.get("created_by"),
                    float(payload.get("created_at", self._now())),
                    payload.get("active_node"),
                    participants_json,
                    1 if payload.get("is_active", True) else 0,
                ),
            )
            conn.commit()
        return self.get_collab_session(payload["session_id"]) or payload

    def get_collab_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM collaboration_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return self._decode_collab_session_row(row)

    def list_collab_sessions(self, active_only: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM collaboration_sessions"
        params: tuple[Any, ...] = ()
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._decode_collab_session_row(r) for r in rows]

    def update_collab_participants(self, session_id: str, participants: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE collaboration_sessions SET participants_json = ? WHERE session_id = ?",
                (json.dumps(participants, ensure_ascii=False), session_id),
            )
            conn.commit()

    def update_collab_active_node(self, session_id: str, node_key: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE collaboration_sessions SET active_node = ? WHERE session_id = ?",
                (node_key, session_id),
            )
            conn.commit()

    def close_collab_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE collaboration_sessions SET is_active = 0 WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()

    def create_collab_annotation(self, payload: dict[str, Any]) -> dict[str, Any]:
        annotation_id = str(uuid.uuid4())
        created_at = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO collaboration_annotations(
                    id, session_id, node_key, text, user_id, visibility, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    annotation_id,
                    payload["session_id"],
                    payload["node_key"],
                    payload["text"],
                    payload["user_id"],
                    payload.get("visibility", "public"),
                    created_at,
                ),
            )
            conn.commit()
        return {
            "id": annotation_id,
            "session_id": payload["session_id"],
            "node_key": payload["node_key"],
            "text": payload["text"],
            "user_id": payload["user_id"],
            "visibility": payload.get("visibility", "public"),
            "created_at": created_at,
        }

    def list_collab_annotations(self, node_key: str, user_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM collaboration_annotations WHERE node_key = ?"
        params: list[Any] = [node_key]
        if user_id:
            query += " AND (visibility = 'public' OR user_id = ?)"
            params.append(user_id)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._decode_collab_annotation_row(r) for r in rows]

    def save_chat_message(self, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO collaboration_chat_messages(
                    id, session_id, user_id, text, context_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"],
                    payload["session_id"],
                    payload["user_id"],
                    payload["text"],
                    json.dumps(payload.get("context") or {}, ensure_ascii=False),
                    float(payload.get("created_at", self._now())),
                ),
            )
            conn.commit()

    def list_chat_messages(self, session_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM collaboration_chat_messages
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, int(limit)),
            ).fetchall()
        return [self._decode_chat_message_row(r) for r in rows]

    def save_session_event(self, session_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event_id = str(uuid.uuid4())
        created_at = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO collaboration_session_events(id, session_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, session_id, event_type, json.dumps(payload, ensure_ascii=False), created_at),
            )
            conn.commit()
        return {
            "id": event_id,
            "session_id": session_id,
            "event_type": event_type,
            "payload": payload,
            "created_at": created_at,
        }

    def list_session_events(self, session_id: str, limit: int = 1000) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM collaboration_session_events
                WHERE session_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (session_id, int(limit)),
            ).fetchall()
        return [self._decode_collab_event_row(r) for r in rows]

    def save_config_version(
        self,
        content: str,
        fmt: str = "yaml",
        created_by: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        config_id = str(uuid.uuid4())
        created_at = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO config_versions(id, format, content, created_by, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (config_id, fmt, content, created_by, source, created_at),
            )
            conn.commit()
        return self.get_config_version(config_id) or {"id": config_id}

    def get_latest_config_version(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM config_versions ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return self._decode_config_row(row)

    def get_config_version(self, config_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM config_versions WHERE id = ?",
                (config_id,),
            ).fetchone()
        if not row:
            return None
        return self._decode_config_row(row)

    def _decode_collab_session_row(self, row: sqlite3.Row) -> dict[str, Any]:
        try:
            participants = json.loads(row["participants_json"] or "[]")
        except Exception:
            participants = []
        return {
            "session_id": row["session_id"],
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "active_node": row["active_node"],
            "participants": participants,
            "is_active": bool(row["is_active"]),
        }

    def _decode_collab_annotation_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "node_key": row["node_key"],
            "text": row["text"],
            "user_id": row["user_id"],
            "visibility": row["visibility"],
            "created_at": row["created_at"],
        }

    def _decode_chat_message_row(self, row: sqlite3.Row) -> dict[str, Any]:
        try:
            context = json.loads(row["context_json"] or "{}")
        except Exception:
            context = {}
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "user_id": row["user_id"],
            "text": row["text"],
            "context": context,
            "created_at": row["created_at"],
        }

    def _decode_collab_event_row(self, row: sqlite3.Row) -> dict[str, Any]:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except Exception:
            payload = {}
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "event_type": row["event_type"],
            "payload": payload,
            "created_at": row["created_at"],
        }

    def _decode_config_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "format": row["format"],
            "content": row["content"],
            "created_by": row["created_by"],
            "source": row["source"],
            "created_at": row["created_at"],
        }
