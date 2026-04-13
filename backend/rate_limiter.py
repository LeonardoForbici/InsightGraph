"""Rate limiter backed by Redis with an in-memory fallback."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, List

from redis_client import RedisClient, get_redis_client

logger = logging.getLogger("insightgraph.rate_limiter")


@dataclass(frozen=True)
class RateLimitStatus:
    """Describes the outcome of a rate limit check."""

    allowed: bool
    remaining: int
    reset_in: Optional[int]


class RateLimiter:
    """Rate limiter that prefers Redis and falls back to an in-memory window."""

    def __init__(
        self,
        redis_client: Optional[RedisClient] = None,
        max_requests: int = 100,
        window_seconds: int = 60,
        prefix: str = "rate",
    ):
        self._redis_client = redis_client or get_redis_client()
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._prefix = prefix
        self._local_windows: Dict[str, Deque[float]] = defaultdict(deque)
        self._local_lock = asyncio.Lock()

    async def check(self, user_id: str) -> RateLimitStatus:
        """Check whether the user may emit another message."""
        if self._redis_client.is_available and self._redis_client.is_connected:
            status = await self._redis_check(user_id)
            if status is not None:
                return status
        return await self._local_check(user_id)

    async def _redis_check(self, user_id: str) -> Optional[RateLimitStatus]:
        key = f"{self._prefix}:{user_id}"
        try:
            count = await self._redis_client.incr(key)
            if count is None:
                return None

            if count == 1:
                await self._redis_client.expire(key, self.window_seconds)

            remaining = max(self.max_requests - int(count), 0)
            ttl = await self._redis_client.ttl(key)
            reset_in = ttl if ttl is not None else self.window_seconds
            allowed = int(count) <= self.max_requests
            return RateLimitStatus(allowed=allowed, remaining=remaining, reset_in=reset_in)

        except Exception as exc:
            logger.warning("Redis rate limiter failed: %s", exc)
            return None

    async def _local_check(self, user_id: str) -> RateLimitStatus:
        now = time.time()
        async with self._local_lock:
            window = self._local_windows[user_id]
            while window and now - window[0] >= self.window_seconds:
                window.popleft()
            window.append(now)
            allowed = len(window) <= self.max_requests
            remaining = max(self.max_requests - len(window), 0)
            reset_in = None
            if window:
                reset_in = int(max(self.window_seconds - (now - window[0]), 0))
            return RateLimitStatus(allowed=allowed, remaining=remaining, reset_in=reset_in)
