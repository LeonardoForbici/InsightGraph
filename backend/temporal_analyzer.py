"""
TemporalAnalyzer — captures and queries analysis snapshots stored in SQLite.
"""

import time
import uuid
import logging
from typing import Literal

from state_store import LocalStateStore

logger = logging.getLogger("insightgraph.temporal")

MAX_SNAPSHOTS = 50

# Metrics where a higher value is *worse*
_WORSE_WHEN_HIGHER = {"god_classes", "circular_deps", "dead_code"}
# Metrics where a higher value is *better*
_BETTER_WHEN_HIGHER = {"call_resolution_rate"}

_NUMERIC_METRICS = {
    "total_nodes",
    "total_edges",
    "god_classes",
    "circular_deps",
    "dead_code",
    "call_resolution_rate",
}


class TemporalAnalyzer:
    def __init__(self, state_store: LocalStateStore):
        self._store = state_store

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    async def capture_snapshot(self, graph_stats: dict) -> dict:
        """Persist a new snapshot derived from *graph_stats* and enforce the limit."""
        snapshot = {
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "total_nodes": graph_stats.get("total_nodes", 0),
            "total_edges": graph_stats.get("total_edges", 0),
            "god_classes": graph_stats.get("god_classes", 0),
            "circular_deps": graph_stats.get("circular_deps", 0),
            "dead_code": graph_stats.get("dead_code", 0),
            "call_resolution_rate": float(graph_stats.get("call_resolution_rate", 0.0) or 0.0),
            "metrics": graph_stats.get("metrics", {}),
        }
        try:
            saved = self._store.save_snapshot(snapshot)
            self._enforce_limit()
            return saved
        except Exception as exc:
            logger.error("Failed to capture snapshot: %s", exc)
            return snapshot

    def get_history(self, page: int = 1, limit: int = 20) -> dict:
        """Return paginated snapshot history."""
        snapshots = self._store.get_snapshots(page=page, limit=limit)
        total = self._store.count_snapshots()
        return {
            "items": snapshots,
            "total": total,
            "page": page,
            "limit": limit,
        }

    def get_diff(self, from_id: str, to_id: str) -> dict:
        """Return delta between two snapshots plus per-metric trend classification."""
        snap_from = self._store.get_snapshot_by_id(from_id)
        snap_to = self._store.get_snapshot_by_id(to_id)

        if snap_from is None:
            raise ValueError(f"Snapshot not found: {from_id}")
        if snap_to is None:
            raise ValueError(f"Snapshot not found: {to_id}")

        deltas: dict[str, float | int] = {}
        trends: dict[str, str] = {}

        for metric in _NUMERIC_METRICS:
            val_from = snap_from.get(metric) or 0
            val_to = snap_to.get(metric) or 0
            delta = (val_to or 0) - (val_from or 0)
            deltas[f"delta_{metric}"] = delta
            trends[metric] = self._classify_trend(delta, metric)

        return {
            "from_id": from_id,
            "to_id": to_id,
            "from_snapshot": snap_from,
            "to_snapshot": snap_to,
            **deltas,
            "metrics_trend": trends,
        }

    def get_trend(self, metric: str, window: int = 10) -> dict:
        """Return a time-series for *metric* over the last *window* snapshots."""
        snapshots = self._store.get_snapshots(page=1, limit=window)
        # get_snapshots returns newest-first; reverse for chronological order
        snapshots = list(reversed(snapshots))

        series = [
            {
                "id": s["id"],
                "timestamp": s["timestamp"],
                "value": s.get(metric),
            }
            for s in snapshots
        ]

        return {
            "metric": metric,
            "window": window,
            "series": series,
        }

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────

    def _classify_trend(self, delta: float, metric: str) -> Literal["melhorou", "piorou", "estavel"]:
        """Classify a numeric delta as 'melhorou', 'piorou', or 'estavel'."""
        if delta == 0:
            return "estavel"
        if metric in _WORSE_WHEN_HIGHER:
            return "piorou" if delta > 0 else "melhorou"
        if metric in _BETTER_WHEN_HIGHER:
            return "melhorou" if delta > 0 else "piorou"
        # Neutral metrics (total_nodes, total_edges) — treat increase as neutral/piorou
        return "piorou" if delta > 0 else "melhorou"

    def _enforce_limit(self) -> None:
        """Keep only the MAX_SNAPSHOTS most recent snapshots."""
        try:
            deleted = self._store.delete_oldest_snapshots(keep=MAX_SNAPSHOTS)
            if deleted:
                logger.debug("Pruned %d old snapshots (limit=%d)", deleted, MAX_SNAPSHOTS)
        except Exception as exc:
            logger.warning("Failed to enforce snapshot limit: %s", exc)
