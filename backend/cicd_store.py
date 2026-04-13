"""PostgreSQL persistence for CI/CD build status."""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from typing import Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("insightgraph.cicd_store")


@contextmanager
def _cursor(conn):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        yield cur


class CICDStore:
    def __init__(self, dsn: Optional[str] = None):
        self._dsn = dsn or os.getenv("POSTGRES_URL", "postgresql://postgres:password@localhost:5432/insightgraph")
        self._conn: Optional[psycopg2.extensions.connection] = None
        self._connect()

    def _connect(self) -> None:
        try:
            self._conn = psycopg2.connect(self._dsn, connect_timeout=5)
            self._conn.autocommit = True
            self._ensure_schema()
            logger.info("CICDStore connected to PostgreSQL")
        except Exception as exc:
            logger.warning("CICDStore unavailable: %s", exc)
            self._conn = None

    @property
    def available(self) -> bool:
        return self._conn is not None

    def _ensure_schema(self) -> None:
        if not self._conn:
            return
        with _cursor(self._conn) as cur:
            cur.execute(
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
                    coverage DOUBLE PRECISION,
                    duration_seconds DOUBLE PRECISION,
                    web_url TEXT,
                    stack_trace TEXT,
                    failed_files_json JSONB,
                    raw_payload_json JSONB,
                    created_at DOUBLE PRECISION NOT NULL
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cicd_builds_commit ON cicd_builds(commit_hash);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cicd_builds_created ON cicd_builds(created_at);")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cicd_build_nodes (
                    build_id TEXT NOT NULL,
                    node_key TEXT NOT NULL,
                    PRIMARY KEY (build_id, node_key)
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cicd_build_nodes_node ON cicd_build_nodes(node_key);")

    def save_build(self, build: dict[str, Any]) -> None:
        if not self._conn:
            return
        try:
            with _cursor(self._conn) as cur:
                cur.execute(
                    """
                    INSERT INTO cicd_builds(
                        id, provider, status, commit_hash, branch, build_id, pipeline_id, author,
                        coverage, duration_seconds, web_url, stack_trace, failed_files_json,
                        raw_payload_json, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                    ON CONFLICT(id) DO UPDATE SET
                        status = EXCLUDED.status,
                        coverage = EXCLUDED.coverage,
                        duration_seconds = EXCLUDED.duration_seconds,
                        web_url = EXCLUDED.web_url,
                        stack_trace = EXCLUDED.stack_trace,
                        failed_files_json = EXCLUDED.failed_files_json,
                        raw_payload_json = EXCLUDED.raw_payload_json
                    ;
                    """,
                    (
                        build.get("id"),
                        build.get("provider"),
                        build.get("status"),
                        build.get("commit_hash"),
                        build.get("branch"),
                        build.get("build_id"),
                        build.get("pipeline_id"),
                        build.get("author"),
                        build.get("coverage"),
                        build.get("duration_seconds"),
                        build.get("web_url"),
                        build.get("stack_trace"),
                        json.dumps(build.get("failed_files") or []),
                        json.dumps(build.get("raw_payload") or {}),
                        build.get("created_at"),
                    ),
                )
                cur.execute("DELETE FROM cicd_build_nodes WHERE build_id = %s", (build.get("id"),))
                for node_key in build.get("failed_nodes") or []:
                    cur.execute(
                        "INSERT INTO cicd_build_nodes(build_id, node_key) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (build.get("id"), node_key),
                    )
        except Exception as exc:
            logger.debug("Failed to persist CI/CD build in PostgreSQL: %s", exc)
