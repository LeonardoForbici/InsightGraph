"""
Metrics collector for the Living Impact System pulse dashboard.

Implements:
  - commit buckets (24h window, hourly)
  - active developer tracking (15m)
  - Redis caching and optional Timescale logging
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional

from redis_client import get_redis_client
from timeseries_store import TimeseriesStore, TimeseriesOptions

logger = logging.getLogger("insightgraph.metrics_collector")


@dataclass
class CommitRecord:
    hash: str
    author: str
    timestamp: datetime


class MetricsCollector:
    CACHE_KEY = "metrics:pulse"

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path(__file__).resolve().parents[1]
        self.redis_client = get_redis_client()
        self.timeseries = TimeseriesStore()

    async def get_pulse_metrics(self) -> Dict[str, object]:
        cached = await self.redis_client.get(self.CACHE_KEY)
        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

        metrics = await asyncio.to_thread(self._build_metrics)
        payload = json.dumps(metrics)
        await self.redis_client.set(self.CACHE_KEY, payload, ex=30)
        return metrics

    def _build_metrics(self) -> Dict[str, object]:
        records = self._collect_commits(hours=24)
        now = datetime.now(timezone.utc)
        buckets = self._bucket_commits(records, now)
        active = self._active_developers(records, now - timedelta(minutes=15))
        total_commits = len(records)

        for bucket in buckets:
            self.timeseries.record(
                metric_type="commits_per_hour",
                value=bucket["count"],
                metadata={"bucket_start": bucket["start"]},
                timestamp=datetime.fromisoformat(bucket["start"]),
            )
        self.timeseries.record(
            metric_type="active_developers",
            value=len(active["names"]),
            metadata={"developers": active["names"]},
        )

        return {
            "last_updated": now.isoformat(),
            "commits_per_hour": buckets,
            "total_commits_24h": total_commits,
            "active_developers": active,
        }

    def _collect_commits(self, hours: int) -> List[CommitRecord]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).astimezone(timezone.utc)
        cmd = [
            "git",
            "-C",
            str(self.repo_root),
            "log",
            f"--since={since.isoformat()}",
            "--no-pager",
            "--pretty=format:%H|%an|%ai",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                logger.warning("Git log failed: %s", result.stderr.strip())
                return []
        except Exception as exc:
            logger.warning("Failed to run git log: %s", exc)
            return []

        commits: List[CommitRecord] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("|", 2)
            if len(parts) != 3:
                continue
            hash_, author, timestr = parts
            try:
                timestamp = datetime.strptime(timestr.strip(), "%Y-%m-%d %H:%M:%S %z")
            except ValueError:
                try:
                    timestamp = datetime.fromisoformat(timestr.strip())
                except ValueError:
                    continue
            commits.append(CommitRecord(hash=hash_, author=author.strip(), timestamp=timestamp.astimezone(timezone.utc)))
        return commits

    def _bucket_commits(self, records: List[CommitRecord], now: datetime) -> List[Dict[str, object]]:
        start = (now - timedelta(hours=24)).replace(minute=0, second=0, microsecond=0)
        buckets = []

        for step in range(24):
            bucket_start = start + timedelta(hours=step)
            bucket_end = bucket_start + timedelta(hours=1)
            count = sum(1 for record in records if bucket_start <= record.timestamp < bucket_end)
            buckets.append({"start": bucket_start.isoformat(), "count": count})

        return buckets

    def _active_developers(self, records: List[CommitRecord], cutoff: datetime) -> Dict[str, object]:
        recent = [record for record in records if record.timestamp >= cutoff]
        authors = sorted({record.author for record in recent})
        return {
            "count": len(authors),
            "names": authors,
            "since": cutoff.isoformat(),
        }


metrics_collector = MetricsCollector()
