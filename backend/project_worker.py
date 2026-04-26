from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from event_stream import SSEEvent

logger = logging.getLogger("insightgraph.project_worker")

WATCHED_EXTENSIONS = {
    ".py",
    ".java",
    ".kt",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".sql",
    ".go",
    ".cs",
    ".swift",
    ".dart",
}
DEBOUNCE_SECONDS = 0.8


class _WatchdogHandler:
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[str]):
        from watchdog.events import FileSystemEventHandler

        class _Handler(FileSystemEventHandler):
            def __init__(self, event_loop: asyncio.AbstractEventLoop, event_queue: asyncio.Queue[str]):
                self._loop = event_loop
                self._queue = event_queue

            def _enqueue(self, file_path: str) -> None:
                suffix = Path(file_path).suffix.lower()
                if suffix not in WATCHED_EXTENSIONS:
                    return
                asyncio.run_coroutine_threadsafe(self._queue.put(file_path), self._loop)

            def on_modified(self, event):
                if not event.is_directory:
                    self._enqueue(event.src_path)

            def on_created(self, event):
                if not event.is_directory:
                    self._enqueue(event.src_path)

            def on_moved(self, event):
                if not event.is_directory:
                    self._enqueue(event.dest_path)

        self.handler = _Handler(loop, queue)


class ProjectWorker:
    def __init__(
        self,
        project,
        registry,
        incremental_scanner,
        cross_impact_engine,
        memory_nodes: list[dict],
        event_stream=None,
    ) -> None:
        self._project = project
        self._registry = registry
        self._scanner = incremental_scanner
        self._cross_engine = cross_impact_engine
        self._memory_nodes = memory_nodes
        self._event_stream = event_stream

        self._event_queue: asyncio.Queue[str] = asyncio.Queue()
        self._pending_files: dict[str, float] = {}
        self._stop = asyncio.Event()
        self._runner_task: Optional[asyncio.Task] = None
        self._observer = None

    async def start(self) -> None:
        if self._runner_task and not self._runner_task.done():
            return

        self._stop.clear()
        self._start_watchdog()
        self._registry.update_project_status(self._project.id, "watching")
        self._runner_task = asyncio.create_task(self._run(), name=f"project-worker-{self._project.id}")

    async def stop(self) -> None:
        self._stop.set()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=3)
            self._observer = None

        if self._runner_task:
            self._runner_task.cancel()
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass
            self._runner_task = None

        self._registry.update_project_status(self._project.id, "idle")

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._drain_events()
                await self._flush_debounced_files()
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Project worker loop failed for %s: %s", self._project.name, exc)
                self._registry.update_project_status(self._project.id, "error", str(exc))
                await asyncio.sleep(0.5)

    async def _drain_events(self) -> None:
        while True:
            try:
                file_path = self._event_queue.get_nowait()
                self._pending_files[file_path] = time.monotonic()
            except asyncio.QueueEmpty:
                return

    async def _flush_debounced_files(self) -> None:
        now = time.monotonic()
        ready_files = [
            file_path
            for file_path, last_event in self._pending_files.items()
            if now - last_event >= DEBOUNCE_SECONDS
        ]

        for file_path in ready_files:
            self._pending_files.pop(file_path, None)
            await self._process_file(file_path)

    async def _process_file(self, file_path: str) -> None:
        self._registry.update_project_status(self._project.id, "scanning")

        try:
            result = await self._scanner.process_file(file_path, self._project.path)
            changed_nodes = list(result.changed_nodes or []) if result else []

            if changed_nodes:
                self._tag_changed_nodes(changed_nodes)

            cross_result = await self._cross_engine.analyze(
                origin_project_id=self._project.id,
                changed_file=file_path,
                changed_nodes=changed_nodes,
            )

            await self._publish_graph_updated(file_path, result, cross_result)
            self._registry.update_project_status(self._project.id, "watching")
        except Exception as exc:
            logger.exception("Failed processing %s for project %s: %s", file_path, self._project.name, exc)
            self._registry.update_project_status(self._project.id, "error", str(exc))

    def _tag_changed_nodes(self, changed_nodes: list[str]) -> None:
        changed_set = set(changed_nodes)
        project_root = Path(self._project.path).resolve()

        for node in self._memory_nodes:
            key = node.get("namespace_key")
            if key not in changed_set:
                continue
            node["project_id"] = self._project.id
            node["workspace_id"] = self._project.workspace_id
            node_file = node.get("file")
            if node_file:
                try:
                    node_path = Path(str(node_file)).resolve()
                    if node_path.is_relative_to(project_root):
                        node["project_id"] = self._project.id
                except Exception:
                    pass

    async def _publish_graph_updated(self, file_path: str, scan_result, cross_result) -> None:
        if not self._event_stream:
            return

        changed_nodes = list(scan_result.changed_nodes or []) if scan_result else []
        affected_nodes = list(scan_result.affected_nodes or []) if scan_result else []
        cross_payload = cross_result.to_payload() if cross_result else None
        if isinstance(cross_payload, dict):
            for affected in cross_payload.get("affected", []):
                node_key = affected.get("node_key")
                if isinstance(node_key, str) and node_key and node_key not in affected_nodes:
                    affected_nodes.append(node_key)

        payload = {
            "workspace_id": self._project.workspace_id,
            "project_id": self._project.id,
            "project_name": self._project.name,
            "file": file_path,
            "changed_nodes": changed_nodes,
            "affected_nodes": affected_nodes,
            "risk_score": float(getattr(scan_result, "risk_score", 0.0) or 0.0),
            "coupling_delta": float(getattr(scan_result, "coupling_delta", 0.0) or 0.0),
            "summary": getattr(scan_result, "summary", "") if scan_result else "",
            "timestamp": time.time(),
            "cross_project": cross_payload,
        }

        await self._event_stream.publish(
            SSEEvent(type="graph_updated", payload=payload, timestamp=time.time())
        )

    def _start_watchdog(self) -> None:
        try:
            from watchdog.observers import Observer

            loop = asyncio.get_running_loop()
            bridge = _WatchdogHandler(loop, self._event_queue)
            observer = Observer()
            observer.schedule(bridge.handler, str(self._project.path), recursive=True)
            observer.daemon = True
            observer.start()
            self._observer = observer
        except Exception as exc:
            logger.warning("Watchdog unavailable for project %s: %s", self._project.name, exc)
