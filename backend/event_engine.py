"""
EventEngine — Fase 2: Barramento central de eventos do sistema vivo.

Recebe eventos de fontes externas (GitHub webhooks, CI/CD, post-commit hook local)
e os processa de forma assíncrona:

  GitHub push  →  trigger incremental scan  →  snapshot vinculado ao commit
  GitHub PR    →  trigger PR analysis       →  comentário automático + alertas
  CI deploy    →  snapshot arquitetural     →  comparação com baseline

Uso:
    engine = EventEngine(api_url="http://localhost:8000")
    await engine.handle_github_event(event_type="push", payload={...})
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional

import httpx

logger = logging.getLogger("insightgraph.event_engine")

if TYPE_CHECKING:
    from impact_propagator import ImpactPropagator

# ──────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────

EventSource = Literal["github", "local_hook", "ci", "manual"]
EventKind   = Literal["push", "pull_request", "deployment", "ping"]


@dataclass
class IncomingEvent:
    source: EventSource
    kind: EventKind
    payload: dict
    received_at: float = field(default_factory=time.time)


@dataclass
class ProcessingResult:
    event_kind: EventKind
    actions_taken: list[str]
    commit_hash: Optional[str]
    pr_number: Optional[int]
    elapsed_seconds: float
    error: Optional[str] = None


# ──────────────────────────────────────────────
# EventEngine
# ──────────────────────────────────────────────

class EventEngine:
    """
    Central event bus for the living system.

    Processes incoming events from GitHub webhooks and local git hooks,
    routing them to the appropriate handlers (scan, PR analysis, snapshots).
    """

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        webhook_secret: Optional[str] = None,
        github_token: Optional[str] = None,
        github_repo: Optional[str] = None,
        impact_propagator: Optional["ImpactPropagator"] = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.webhook_secret = webhook_secret
        self.github_token = github_token
        self.github_repo = github_repo
        self._impact_propagator = impact_propagator
        self._queue: asyncio.Queue[IncomingEvent] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._processing = False

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    def start(self) -> None:
        """Start the background event processing worker."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.info("EventEngine worker started")

    async def stop(self) -> None:
        """Gracefully stop the event processing worker."""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("EventEngine worker stopped")

    def verify_github_signature(self, body: bytes, signature: str) -> bool:
        """
        Validate GitHub webhook HMAC-SHA256 signature.
        Returns True if valid or if no secret is configured.
        """
        if not self.webhook_secret:
            return True
        expected = "sha256=" + hmac.new(
            self.webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    async def enqueue_github_event(
        self, event_type: str, payload: dict, raw_body: bytes = b"", signature: str = ""
    ) -> bool:
        """
        Validate and enqueue a GitHub webhook event for processing.
        Returns False if the signature is invalid.
        """
        if not self.verify_github_signature(raw_body, signature):
            logger.warning("Invalid GitHub webhook signature — event rejected")
            return False

        kind = self._map_github_event(event_type)
        if kind is None:
            logger.debug("Ignoring unhandled GitHub event type: %s", event_type)
            return True  # Not an error — just not handled

        event = IncomingEvent(source="github", kind=kind, payload=payload)
        await self._queue.put(event)
        logger.info("Enqueued GitHub event: %s (queue_size=%d)", kind, self._queue.qsize())
        return True

    async def enqueue_local_push(self, commit_hash: str, project_path: str) -> None:
        """Enqueue a local post-commit event (from the git hook)."""
        event = IncomingEvent(
            source="local_hook",
            kind="push",
            payload={"commit_hash": commit_hash, "project_path": project_path},
        )
        await self._queue.put(event)
        logger.info("Enqueued local push event: %s", commit_hash)

    # ──────────────────────────────────────────────
    # Worker loop
    # ──────────────────────────────────────────────

    async def _worker_loop(self) -> None:
        logger.info("EventEngine worker loop running")
        while True:
            try:
                event = await self._queue.get()
                t0 = time.monotonic()
                result = await self._process_event(event)
                elapsed = time.monotonic() - t0
                logger.info(
                    "Event processed: %s | actions=%s | %.2fs",
                    result.event_kind,
                    result.actions_taken,
                    elapsed,
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Event processing error: %s", exc, exc_info=True)

    async def _process_event(self, event: IncomingEvent) -> ProcessingResult:
        t0 = time.monotonic()
        actions: list[str] = []
        commit_hash: Optional[str] = None
        pr_number: Optional[int] = None
        error: Optional[str] = None

        try:
            if event.kind == "push":
                commit_hash, pushed_actions = await self._handle_push(event)
                actions.extend(pushed_actions)

            elif event.kind == "pull_request":
                pr_number, pr_actions = await self._handle_pull_request(event)
                actions.extend(pr_actions)

            elif event.kind == "deployment":
                dep_actions = await self._handle_deployment(event)
                actions.extend(dep_actions)

            elif event.kind == "ping":
                actions.append("pong")

        except Exception as exc:
            error = str(exc)
            logger.error("Error handling %s event: %s", event.kind, exc)

        return ProcessingResult(
            event_kind=event.kind,
            actions_taken=actions,
            commit_hash=commit_hash,
            pr_number=pr_number,
            elapsed_seconds=time.monotonic() - t0,
            error=error,
        )

    # ──────────────────────────────────────────────
    # Event handlers
    # ──────────────────────────────────────────────

    async def _handle_push(self, event: IncomingEvent) -> tuple[Optional[str], list[str]]:
        """
        Handle a push event: trigger incremental scan for changed files.
        Returns (commit_hash, actions_taken).
        """
        payload = event.payload
        actions: list[str] = []

        # Extract commit info
        commit_hash = (
            payload.get("after")                          # GitHub push
            or payload.get("commit_hash")                  # local hook
        )
        project_path = payload.get("project_path") or payload.get("repository", {}).get("clone_url", "")

        # Collect changed files from GitHub push commits
        changed_files: list[str] = []
        if event.source == "github":
            for commit in payload.get("commits", []):
                changed_files.extend(commit.get("added", []))
                changed_files.extend(commit.get("modified", []))
            changed_files = list(set(changed_files))  # deduplicate

        async with httpx.AsyncClient(timeout=30.0) as client:
            scan_payload: dict = {
                "triggered_by": f"{event.source}_push",
                "commit_hash": commit_hash,
            }
            if changed_files:
                # Incremental: only changed files
                scan_payload["paths"] = changed_files
                logger.info(
                    "Triggering incremental scan for %d changed files (commit=%s)",
                    len(changed_files),
                    commit_hash,
                )
            elif project_path:
                scan_payload["paths"] = [project_path]
                logger.info("Triggering full scan for project: %s", project_path)
            else:
                logger.warning("Push event has no files or project path — skipping scan")
                return commit_hash, ["skipped_no_target"]

            try:
                resp = await client.post(f"{self.api_url}/api/scan", json=scan_payload)
                if resp.status_code == 200:
                    actions.append("scan_triggered")
                elif resp.status_code == 409:
                    actions.append("scan_already_running")
                else:
                    actions.append(f"scan_error_{resp.status_code}")
            except httpx.RequestError as exc:
                actions.append(f"scan_unreachable:{exc}")

        self._schedule_push_propagation(payload, changed_files, commit_hash)
        return commit_hash, actions

    def _select_push_node(
        self,
        payload: dict,
        changed_files: list[str],
        commit_hash: Optional[str],
    ) -> Optional[str]:
        candidates = [
            payload.get("target_node"),
            payload.get("node_key"),
            changed_files[0] if changed_files else None,
            payload.get("project_path"),
            commit_hash,
        ]
        for candidate in candidates:
            if candidate:
                return str(candidate)
        return None

    def _schedule_push_propagation(
        self,
        payload: dict,
        changed_files: list[str],
        commit_hash: Optional[str],
    ) -> None:
        if not self._impact_propagator:
            return

        node_key = self._select_push_node(payload, changed_files, commit_hash)
        if not node_key:
            return

        context = {
            "commit_hash": commit_hash,
            "changed_files": changed_files,
            "project_path": payload.get("project_path"),
        }
        change_type = payload.get("change_type", "code_change")

        async def _run_propagation() -> None:
            try:
                await self._impact_propagator.propagate_change(
                    node_key=node_key,
                    change_type=change_type,
                    context=context,
                )
            except Exception as exc:
                logger.warning(
                    "Impact propagation failed for %s: %s",
                    node_key,
                    exc,
                )

        asyncio.create_task(_run_propagation())

    async def _handle_pull_request(self, event: IncomingEvent) -> tuple[Optional[int], list[str]]:
        """
        Handle a PR event: trigger PR analysis bot.
        Only processes opened/synchronize actions (not closed/merged).
        """
        payload = event.payload
        actions: list[str] = []

        action = payload.get("action", "")
        if action not in ("opened", "synchronize", "reopened"):
            logger.debug("PR action '%s' — skipped", action)
            return None, ["pr_action_ignored"]

        pr = payload.get("pull_request", {})
        pr_number = pr.get("number")
        if not pr_number:
            return None, ["pr_number_missing"]

        # Collect changed files from the PR
        head_sha = pr.get("head", {}).get("sha")
        changed_files = await self._fetch_pr_changed_files(pr_number) if self.github_token else []

        if not changed_files:
            actions.append("pr_no_files_fetched")

        # Trigger PR bot analysis
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                resp = await client.post(
                    f"{self.api_url}/api/pr/analyze",
                    json={
                        "pr_number": pr_number,
                        "changed_files": changed_files,
                        "head_sha": head_sha,
                        "github_token": self.github_token,
                        "github_repo": self.github_repo,
                    },
                )
                if resp.status_code == 200:
                    actions.append("pr_analysis_triggered")
                else:
                    actions.append(f"pr_analysis_error_{resp.status_code}")
            except httpx.RequestError as exc:
                actions.append(f"pr_unreachable:{exc}")

        return pr_number, actions

    async def _handle_deployment(self, event: IncomingEvent) -> list[str]:
        """
        Handle a deployment event: capture an architectural snapshot
        tagged as a deployment milestone.
        """
        payload = event.payload
        actions: list[str] = []

        env = payload.get("deployment", {}).get("environment", "unknown")
        sha = payload.get("deployment", {}).get("sha")

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    f"{self.api_url}/api/graph/snapshots/deploy",
                    json={"environment": env, "commit_hash": sha},
                )
                if resp.status_code == 200:
                    actions.append(f"deploy_snapshot_captured:{env}")
                else:
                    actions.append(f"deploy_snapshot_error_{resp.status_code}")
            except httpx.RequestError:
                actions.append("deploy_snapshot_unreachable")

        return actions

    # ──────────────────────────────────────────────
    # GitHub API helpers
    # ──────────────────────────────────────────────

    async def _fetch_pr_changed_files(self, pr_number: int) -> list[str]:
        """Fetch the list of files changed in a PR from GitHub API."""
        if not self.github_token or not self.github_repo:
            return []
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        url = f"https://api.github.com/repos/{self.github_repo}/pulls/{pr_number}/files"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers, params={"per_page": 100})
                resp.raise_for_status()
                return [f["filename"] for f in resp.json() if f.get("status") != "removed"]
        except Exception as exc:
            logger.warning("Failed to fetch PR files: %s", exc)
            return []

    # ──────────────────────────────────────────────
    # Utilities
    # ──────────────────────────────────────────────

    @staticmethod
    def _map_github_event(event_type: str) -> Optional[EventKind]:
        mapping = {
            "push": "push",
            "pull_request": "pull_request",
            "deployment": "deployment",
            "ping": "ping",
        }
        return mapping.get(event_type)
