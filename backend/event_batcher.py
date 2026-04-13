"""
EventBatcher â€“ windowed batching helper that keeps broadcasts under control.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Generic, List, Optional, TypeVar

logger = logging.getLogger("insightgraph.event_batcher")

EventType = TypeVar("EventType")
FlushCallback = Callable[[List[EventType]], Awaitable[None]]


class EventBatcher(Generic[EventType]):
    """Accumulates events and flushes them after a time window."""

    def __init__(
        self,
        window_ms: int,
        flush_callback: FlushCallback[EventType],
    ) -> None:
        self.window = window_ms / 1000
        self._flush_callback = flush_callback
        self._buffer: List[EventType] = []
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None

    async def add_event(self, event: EventType) -> None:
        async with self._lock:
            self._buffer.append(event)
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(self._flush_after_window())

    async def _flush_after_window(self) -> None:
        await asyncio.sleep(self.window)
        async with self._lock:
            batch = list(self._buffer)
            self._buffer.clear()
        if not batch:
            self._task = None
            return
        try:
            await self._flush_callback(batch)
        except Exception as exc:
            logger.error("Failed to flush event batch: %s", exc)
        finally:
            self._task = None
