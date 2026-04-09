"""
InsightGraph Watch Service
Monitors file system changes and triggers incremental reprocessing.

Supports: .java, .ts, .tsx, .sql, .prc, .fnc, .pkg

Requirements: 1.1, 1.2, 1.3, 14.1, 14.2
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

import httpx
from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEvent,
    FileSystemEventHandler,
    FileCreatedEvent,
    FileModifiedEvent,
    FileDeletedEvent,
    FileMovedEvent,
)

logger = logging.getLogger("insightgraph.watch")

WATCHED_EXTENSIONS = {".java", ".ts", ".tsx", ".sql", ".prc", ".fnc", ".pkg"}


def _is_watched(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in WATCHED_EXTENSIONS


class _EventBridge(FileSystemEventHandler):
    """Bridges synchronous watchdog callbacks to the async WatchService."""

    def __init__(self, loop: asyncio.AbstractEventLoop, service: "WatchService"):
        super().__init__()
        self._loop = loop
        self._service = service

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory or not _is_watched(event.src_path):
            return
        asyncio.run_coroutine_threadsafe(
            self._service._on_file_changed(event), self._loop
        )

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory or not _is_watched(event.src_path):
            return
        asyncio.run_coroutine_threadsafe(
            self._service._on_file_changed(event), self._loop
        )

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory or not _is_watched(event.src_path):
            return
        asyncio.run_coroutine_threadsafe(
            self._service._on_file_deleted(event), self._loop
        )

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if not _is_watched(event.src_path) and not _is_watched(event.dest_path):
            return
        asyncio.run_coroutine_threadsafe(
            self._service._on_file_renamed(event), self._loop
        )


class WatchService:
    """
    Watches one or more directories for file changes and triggers incremental
    reprocessing via the InsightGraph API.

    Debounce: 500 ms per file — multiple rapid changes collapse into one scan.
    
    Requirements:
        - 1.1: Detect file changes within 500ms
        - 1.2: Trigger incremental reprocessing including direct dependents
        - 1.3: Publish graph_updated event after scan completes
        - 14.1: Identify affected nodes in modified file
        - 14.2: Query Impact_Engine for direct dependents
    """

    def __init__(self, paths: list[str], api_url: str, event_stream=None):
        self.paths = paths
        self.api_url = api_url.rstrip("/")
        self.event_stream = event_stream
        # pending debounce tasks keyed by file path
        self._pending: dict[str, asyncio.Task] = {}
        self._observer: Optional[Observer] = None

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    async def start(self) -> None:
        """Start watching all configured paths. Runs until cancelled."""
        loop = asyncio.get_running_loop()
        handler = _EventBridge(loop, self)

        self._observer = Observer()
        for path in self.paths:
            self._observer.schedule(handler, path, recursive=True)
            logger.info("Watching path: %s", path)

        self._observer.start()
        logger.info("WatchService started — monitoring %d path(s)", len(self.paths))

        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            self._observer.stop()
            self._observer.join()
            logger.info("WatchService stopped")

    # ──────────────────────────────────────────────
    # Event handlers
    # ──────────────────────────────────────────────

    async def _on_file_changed(self, event: FileSystemEvent) -> None:
        """Handle file created/modified events with debounce."""
        file_path = str(event.src_path)
        logger.debug("File changed: %s", file_path)

        # Cancel any pending task for this file
        existing = self._pending.get(file_path)
        if existing and not existing.done():
            existing.cancel()

        task = asyncio.create_task(self._debounced_reprocess(file_path))
        self._pending[file_path] = task

    async def _on_file_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion — remove nodes from graph and RAG store."""
        file_path = str(event.src_path)
        logger.info("File deleted: %s", file_path)

        # Cancel any pending debounce for this file
        existing = self._pending.pop(file_path, None)
        if existing and not existing.done():
            existing.cancel()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.delete(
                    f"{self.api_url}/api/nodes",
                    params={"file": file_path},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    removed = data.get("removed", 0)
                    logger.info("Deleted %d node(s) for file: %s", removed, file_path)
                else:
                    logger.warning(
                        "DELETE /api/nodes returned %d for file: %s",
                        resp.status_code,
                        file_path,
                    )
        except Exception as exc:
            logger.error("Error removing nodes for deleted file %s: %s", file_path, exc)

        # Publish graph_updated event
        await self._publish_graph_updated_event(
            file_path=file_path,
            affected_nodes=[],
            nodes_updated=0
        )

    async def _on_file_renamed(self, event: FileSystemEvent) -> None:
        """Handle file rename — update namespace_key while preserving edges."""
        src_path = str(event.src_path)
        dest_path = str(event.dest_path)
        logger.info("File renamed: %s → %s", src_path, dest_path)

        # Cancel any pending debounce for the old path
        existing = self._pending.pop(src_path, None)
        if existing and not existing.done():
            existing.cancel()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.api_url}/api/nodes/rename",
                    json={"old_file": src_path, "new_file": dest_path},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    updated = data.get("updated", 0)
                    logger.info(
                        "Renamed %d node(s): %s → %s", updated, src_path, dest_path
                    )
                else:
                    logger.warning(
                        "POST /api/nodes/rename returned %d for %s → %s",
                        resp.status_code,
                        src_path,
                        dest_path,
                    )
        except Exception as exc:
            logger.error(
                "Error renaming nodes %s → %s: %s", src_path, dest_path, exc
            )

        # Publish graph_updated event
        await self._publish_graph_updated_event(
            file_path=dest_path,
            affected_nodes=[],
            nodes_updated=0
        )

    # ──────────────────────────────────────────────
    # Debounce + incremental reprocessing
    # ──────────────────────────────────────────────

    async def _debounced_reprocess(self, file_path: str) -> None:
        """Wait 500 ms then trigger incremental reprocessing for the changed file."""
        try:
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.debug("Debounce cancelled for: %s", file_path)
            return

        logger.info("Reprocessing file: %s", file_path)
        try:
            await self._incremental_scan(file_path)
        except Exception as exc:
            logger.error("Reprocessing failed for %s: %s", file_path, exc)
        finally:
            self._pending.pop(file_path, None)

    async def _incremental_scan(self, file_path: str) -> None:
        """
        Perform incremental scan:
        1. Scan the modified file.
        2. Query direct dependents and include them in the scan.
        3. Log the number of nodes updated.
        4. Trigger audit check for new antipatterns.
        5. Fetch change metadata for affected nodes.
        6. Publish graph_updated event with affected nodes and change metadata.
        
        Requirements: 1.2, 1.3, 14.1, 14.2
        """
        files_to_scan = [file_path]
        affected_nodes = []

        # Fetch direct dependents from the graph (Requirement 14.2)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self.api_url}/api/impact",
                    params={"node": file_path},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    downstream = data.get("downstream", [])
                    for dep in downstream:
                        dep_file = dep.get("file") or dep.get("key")
                        if dep_file and dep_file not in files_to_scan:
                            files_to_scan.append(dep_file)
                        # Track affected node keys (Requirement 14.1)
                        dep_key = dep.get("key")
                        if dep_key and dep_key not in affected_nodes:
                            affected_nodes.append(dep_key)
                    logger.debug(
                        "Incremental scope: %d file(s) (1 modified + %d dependents)",
                        len(files_to_scan),
                        len(files_to_scan) - 1,
                    )
        except Exception as exc:
            logger.warning("Could not fetch dependents for %s: %s", file_path, exc)

        # Trigger scan for the collected files
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.api_url}/api/scan",
                    json={"paths": files_to_scan},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    nodes_updated = data.get("total_nodes", 0)
                    logger.info(
                        "Incremental scan complete — %d node(s) updated", nodes_updated
                    )
                    
                    # Trigger audit check for new antipatterns
                    await self._trigger_audit_check()
                    
                    # Fetch change metadata for affected nodes
                    change_metadata = await self._fetch_change_metadata(affected_nodes)
                    
                    # Publish graph_updated event (Requirement 1.3)
                    await self._publish_graph_updated_event(
                        file_path=file_path,
                        affected_nodes=affected_nodes,
                        nodes_updated=nodes_updated,
                        change_metadata=change_metadata
                    )
                else:
                    logger.warning(
                        "POST /api/scan returned %d for files: %s",
                        resp.status_code,
                        files_to_scan,
                    )
        except Exception as exc:
            logger.error("Scan request failed for %s: %s", file_path, exc)

    async def _trigger_audit_check(self) -> None:
        """Trigger audit job to check for new antipatterns after scan."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.api_url}/api/audit/check")
                if resp.status_code == 200:
                    data = resp.json()
                    new_alerts = data.get("new_alerts", 0)
                    if new_alerts > 0:
                        logger.info("Audit check detected %d new alert(s)", new_alerts)
                else:
                    logger.debug("Audit check returned %d", resp.status_code)
        except Exception as exc:
            logger.debug("Audit check failed (non-critical): %s", exc)

    async def _fetch_change_metadata(self, node_keys: list[str]) -> dict[str, dict]:
        """
        Fetch temporal tracking metadata for affected nodes.
        
        Returns a dictionary mapping node_key to metadata:
        {
            "node_key": {
                "last_modified": timestamp,
                "change_frequency": int,
                "first_seen": timestamp
            }
        }
        
        Requirements: 2.1, 2.2, 2.3
        """
        if not node_keys:
            return {}
            
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.api_url}/api/nodes/metadata",
                    json={"node_keys": node_keys},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    metadata = data.get("metadata", {})
                    logger.debug(
                        "Fetched change metadata for %d node(s)", len(metadata)
                    )
                    return metadata
                else:
                    logger.warning(
                        "POST /api/nodes/metadata returned %d", resp.status_code
                    )
                    return {}
        except Exception as exc:
            logger.warning("Could not fetch change metadata: %s", exc)
            return {}

    # ──────────────────────────────────────────────
    # Event publishing (SSE)
    # ──────────────────────────────────────────────

    async def _publish_graph_updated_event(
        self, 
        file_path: str, 
        affected_nodes: list[str],
        nodes_updated: int,
        change_metadata: dict[str, dict] = None
    ) -> None:
        """
        Publish graph_updated event to EventStream after incremental scan completes.
        
        Event payload includes:
        - affected_nodes: List of node keys that were affected
        - file_path: Path to the modified file
        - timestamp: Unix timestamp when event was created
        - nodes_updated: Total number of nodes updated in the scan
        - change_metadata: Dictionary mapping node_key to temporal tracking data
          (last_modified, change_frequency, first_seen)
        
        Requirements: 1.3, 14.1, 14.2, 2.1, 2.2, 2.3
        """
        if self.event_stream is None:
            logger.debug("EventStream not available, skipping event publish")
            return
            
        try:
            from event_stream import SSEEvent
            
            payload = {
                "affected_nodes": affected_nodes,
                "file_path": file_path,
                "timestamp": time.time(),
                "nodes_updated": nodes_updated
            }
            
            # Include change metadata if available
            if change_metadata:
                payload["change_metadata"] = change_metadata
            
            event = SSEEvent(
                type="graph_updated",
                payload=payload,
                timestamp=time.time()
            )
            
            await self.event_stream.publish(event)
            logger.debug(
                "Published graph_updated event: %s (%d affected nodes, %d with metadata)",
                file_path,
                len(affected_nodes),
                len(change_metadata) if change_metadata else 0
            )
        except Exception as exc:
            logger.warning("Could not publish graph_updated event: %s", exc)

    async def _notify_frontend(self, update_type: str) -> None:
        """
        Legacy method for backward compatibility.
        Publishes a simple event without detailed payload.
        
        Deprecated: Use _publish_graph_updated_event instead.
        """
        try:
            # Import here to avoid circular imports when used standalone
            from main import sse_queue  # noqa: PLC0415
            await sse_queue.put(update_type)
            logger.debug("SSE event queued (legacy): %s", update_type)
        except Exception as exc:
            logger.warning("Could not push SSE event '%s': %s", update_type, exc)
