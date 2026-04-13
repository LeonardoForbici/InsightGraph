"""
TimescaleDB-backed store for capturing time series metrics.

Provides helper methods for creating the required hypertable and emitting
measurements that later dashboards can rely on.

Requirements: Sprint 3.2
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("insightgraph.timeseries_store")


@contextmanager
def _cursor(conn):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        yield cur


@dataclass
class TimeseriesOptions:
    dsn: str
    connect_timeout: int = 5


class TimeseriesStore:
    def __init__(self, options: Optional[TimeseriesOptions] = None):
        self._options = options or TimeseriesOptions(
            dsn=os.getenv("POSTGRES_URL", "postgresql://postgres:password@localhost:5432/insightgraph")
        )
        self._conn: Optional[psycopg2.extensions.connection] = None
        self._ensure_connection()

    def _ensure_connection(self) -> None:
        if self._conn is not None:
            return
        try:
            self._conn = psycopg2.connect(
                self._options.dsn,
                connect_timeout=self._options.connect_timeout,
            )
            self._conn.autocommit = True
            self._ensure_schema()
            logger.info("TimeseriesStore connected: %s", self._options.dsn)
        except Exception as exc:
            logger.warning("Failed to connect to TimescaleDB: %s", exc)
            self._conn = None

    def _ensure_schema(self) -> None:
        if self._conn is None:
            return
        try:
            with _cursor(self._conn) as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS metrics_timeseries (
                        time TIMESTAMPTZ NOT NULL,
                        metric_type TEXT NOT NULL,
                        value DOUBLE PRECISION NOT NULL,
                        metadata JSONB
                    );
                    """
                )
                cur.execute(
                    "SELECT create_hypertable('metrics_timeseries', 'time', if_not_exists => TRUE);"
                )
        except Exception as exc:
            logger.warning("Unable to prepare TimescaleDB schema: %s", exc)

    def record(
        self,
        metric_type: str,
        value: float,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        if self._conn is None:
            return
        ts = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
        try:
            with _cursor(self._conn) as cur:
                cur.execute(
                    """
                    INSERT INTO metrics_timeseries (time, metric_type, value, metadata)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (ts, metric_type, value, metadata or {}),
                )
        except Exception as exc:
            logger.debug("Failed to insert timeseries metric %s: %s", metric_type, exc)

    def close(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None
