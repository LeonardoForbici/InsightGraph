"""
Redis Client — Connection pool for pub/sub messaging and caching.

Provides centralized Redis connection management with connection pooling
for the Living Impact System's real-time event propagation and caching.

Requirements: Req 1 (Real-time reactivity), Req 10 (Performance)
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Any
from contextlib import asynccontextmanager


# ──────────────────────────────────────────────
# Pub/Sub Channel Constants
# ──────────────────────────────────────────────

# Channel for propagating code change impacts in real-time
# Used by: Impact_Propagator
# Purpose: Broadcasts impact events when code changes are detected,
#          enabling real-time visualization of change propagation
# Requirements: Req 1 (Real-time reactivity)
IMPACT_EVENTS_CHANNEL = "impact_events"

# Channel for multi-user collaboration features
# Used by: Collaboration_Manager
# Purpose: Broadcasts collaboration events like cursor positions,
#          node selections, and shared annotations
# Requirements: Req 5 (Collaboration)
COLLABORATION_EVENTS_CHANNEL = "collaboration_events"

try:
    import redis.asyncio as redis
    from redis.asyncio.connection import ConnectionPool
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    ConnectionPool = None

logger = logging.getLogger("insightgraph.redis_client")


class RedisClient:
    """
    Redis client with connection pooling for pub/sub and caching.
    
    Supports:
    - Connection pooling for performance
    - Pub/sub for real-time event broadcasting
    - Key-value caching with TTL
    - Graceful degradation when Redis is unavailable
    
    Requirements: Req 1.1, Req 10.4
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        max_connections: int = 50,
        decode_responses: bool = True,
    ):
        """
        Initialize Redis client with connection pool.
        
        Args:
            url: Redis connection URL (redis://host:port/db)
            max_connections: Maximum connections in pool
            decode_responses: Auto-decode bytes to strings
        """
        if not REDIS_AVAILABLE:
            logger.warning("redis package not installed — Redis features disabled")
            self._pool = None
            self._client = None
            self._pubsub = None
            return
        
        self._url = url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._max_connections = max_connections
        self._decode_responses = decode_responses
        
        # Connection pool (lazy initialization)
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        
        logger.info(
            "RedisClient initialized: url=%s, max_connections=%d",
            self._url,
            self._max_connections,
        )
    
    @property
    def is_available(self) -> bool:
        """Check if Redis is available and connected."""
        return REDIS_AVAILABLE and self._client is not None
    
    @property
    def is_connected(self) -> bool:
        """Check if Redis client is connected (alias for is_available)."""
        return self.is_available
    
    async def connect(self) -> bool:
        """
        Establish connection pool and client.
        
        Returns:
            True if connected successfully, False otherwise
        
        Requirements: Req 10.4
        """
        if not REDIS_AVAILABLE:
            logger.warning("Cannot connect: redis package not installed")
            return False
        
        if self._client is not None:
            logger.debug("Redis client already connected")
            return True
        
        try:
            # Create connection pool
            self._pool = ConnectionPool.from_url(
                self._url,
                max_connections=self._max_connections,
                decode_responses=self._decode_responses,
            )
            
            # Create client from pool
            self._client = redis.Redis(connection_pool=self._pool)
            
            # Test connection
            await self._client.ping()
            
            logger.info("Redis connection pool established: %s", self._url)
            return True
        
        except Exception as exc:
            logger.error("Failed to connect to Redis: %s", exc)
            self._pool = None
            self._client = None
            return False
    
    async def disconnect(self) -> None:
        """
        Close all connections and cleanup resources.
        
        Requirements: Req 10.4
        """
        if not self.is_available:
            return
        
        try:
            # Close pubsub if active
            if self._pubsub is not None:
                await self._pubsub.close()
                self._pubsub = None
            
            # Close client
            if self._client is not None:
                await self._client.close()
                self._client = None
            
            # Close pool
            if self._pool is not None:
                await self._pool.disconnect()
                self._pool = None
            
            logger.info("Redis connection pool closed")
        
        except Exception as exc:
            logger.error("Error during Redis disconnect: %s", exc)
    
    # ──────────────────────────────────────────────
    # Pub/Sub Operations
    # ──────────────────────────────────────────────
    
    async def publish(self, channel: str, message: str) -> int:
        """
        Publish message to a channel.
        
        Args:
            channel: Channel name
            message: Message to publish
        
        Returns:
            Number of subscribers that received the message
        
        Requirements: Req 1.1 (Real-time event propagation)
        """
        if not self.is_available:
            logger.warning("Redis not available — publish skipped")
            return 0
        
        try:
            result = await self._client.publish(channel, message)
            logger.debug("Published to %s: %d subscribers", channel, result)
            return result
        
        except Exception as exc:
            logger.error("Failed to publish to %s: %s", channel, exc)
            return 0

    async def publish_collaboration(self, message: str) -> int:
        """Publish a message to the collaboration channel."""
        return await self.publish(COLLABORATION_EVENTS_CHANNEL, message)
    
    @asynccontextmanager
    async def subscribe(self, *channels: str):
        """
        Subscribe to channels (context manager).
        
        Usage:
            async with redis_client.subscribe("events") as pubsub:
                async for message in pubsub.listen():
                    print(message)
        
        Args:
            channels: Channel names to subscribe to
        
        Yields:
            PubSub instance for listening
        
        Requirements: Req 1.1 (Real-time event propagation)
        """
        if not self.is_available:
            logger.warning("Redis not available — subscribe skipped")
            yield None
            return
        
        pubsub = self._client.pubsub()
        try:
            await pubsub.subscribe(*channels)
            logger.info("Subscribed to channels: %s", channels)
            yield pubsub
        finally:
            await pubsub.unsubscribe(*channels)
            await pubsub.close()
            logger.info("Unsubscribed from channels: %s", channels)
    
    # ──────────────────────────────────────────────
    # Caching Operations
    # ──────────────────────────────────────────────
    
    async def get(self, key: str) -> Optional[str]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
        
        Returns:
            Cached value or None if not found
        
        Requirements: Req 10.4 (Performance - caching)
        """
        if not self.is_available:
            return None
        
        try:
            value = await self._client.get(key)
            return value
        
        except Exception as exc:
            logger.error("Failed to get key %s: %s", key, exc)
            return None
    
    async def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None,
    ) -> bool:
        """
        Set value in cache with optional TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ex: Expiration time in seconds (None = no expiration)
        
        Returns:
            True if successful, False otherwise
        
        Requirements: Req 10.4 (Performance - caching)
        """
        if not self.is_available:
            return False
        
        try:
            await self._client.set(key, value, ex=ex)
            return True
        
        except Exception as exc:
            logger.error("Failed to set key %s: %s", key, exc)
            return False
    
    async def delete(self, *keys: str) -> int:
        """
        Delete keys from cache.
        
        Args:
            keys: Keys to delete
        
        Returns:
            Number of keys deleted
        
        Requirements: Req 10.4 (Performance - caching)
        """
        if not self.is_available:
            return 0
        
        try:
            result = await self._client.delete(*keys)
            return result
        
        except Exception as exc:
            logger.error("Failed to delete keys %s: %s", keys, exc)
            return 0
    
    async def exists(self, *keys: str) -> int:
        """
        Check if keys exist.
        
        Args:
            keys: Keys to check
        
        Returns:
            Number of existing keys
        """
        if not self.is_available:
            return 0
        
        try:
            result = await self._client.exists(*keys)
            return result
        
        except Exception as exc:
            logger.error("Failed to check existence of keys %s: %s", keys, exc)
            return 0
    
    async def expire(self, key: str, ttl: int) -> bool:
        """
        Set TTL on existing key.
        
        Args:
            key: Cache key
            ttl: Time-to-live in seconds
        
        Returns:
            True if TTL was set, False otherwise
        """
        if not self.is_available:
            return False
        
        try:
            result = await self._client.expire(key, ttl)
            return bool(result)
        
        except Exception as exc:
            logger.error("Failed to set TTL on key %s: %s", key, exc)
            return False

    async def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """Atomically increment a key and return the new value."""
        if not self.is_available:
            return None

        try:
            return await self._client.incrby(key, amount)
        except Exception as exc:
            logger.error("Failed to increment key %s: %s", key, exc)
            return None

    async def ttl(self, key: str) -> Optional[int]:
        """Read the remaining TTL for a key."""
        if not self.is_available:
            return None

        try:
            ttl = await self._client.ttl(key)
            if ttl is None or ttl < 0:
                return None
            return int(ttl)
        except Exception as exc:
            logger.error("Failed to read TTL for key %s: %s", key, exc)
            return None
    
    # ──────────────────────────────────────────────
    # Session Management
    # ──────────────────────────────────────────────
    
    async def set_session(
        self,
        session_id: str,
        session_data: dict,
        ttl: int = 3600,
    ) -> bool:
        """
        Store session data with TTL.
        
        Args:
            session_id: Session identifier
            session_data: Session data dictionary
            ttl: Time-to-live in seconds (default: 1 hour)
        
        Returns:
            True if successful, False otherwise
        
        Requirements: Req 5 (Collaboration - session management)
        """
        if not self.is_available:
            return False
        
        try:
            import json
            session_key = f"session:{session_id}"
            session_json = json.dumps(session_data)
            await self._client.set(session_key, session_json, ex=ttl)
            return True
        
        except Exception as exc:
            logger.error("Failed to set session %s: %s", session_id, exc)
            return False
    
    async def get_session(self, session_id: str) -> Optional[dict]:
        """
        Retrieve session data.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Session data dictionary or None if not found
        
        Requirements: Req 5 (Collaboration - session management)
        """
        if not self.is_available:
            return None
        
        try:
            import json
            session_key = f"session:{session_id}"
            session_json = await self._client.get(session_key)
            if session_json:
                return json.loads(session_json)
            return None
        
        except Exception as exc:
            logger.error("Failed to get session %s: %s", session_id, exc)
            return None
    
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete session data.
        
        Args:
            session_id: Session identifier
        
        Returns:
            True if deleted, False otherwise
        
        Requirements: Req 5 (Collaboration - session management)
        """
        if not self.is_available:
            return False
        
        try:
            session_key = f"session:{session_id}"
            result = await self._client.delete(session_key)
            return result > 0
        
        except Exception as exc:
            logger.error("Failed to delete session %s: %s", session_id, exc)
            return False
    
    # ──────────────────────────────────────────────
    # Advanced Operations
    # ──────────────────────────────────────────────
    
    async def ping(self) -> bool:
        """
        Ping Redis server to check connectivity.
        
        Returns:
            True if connected, False otherwise
        """
        if not self.is_available:
            return False
        
        try:
            await self._client.ping()
            return True
        
        except Exception as exc:
            logger.error("Redis ping failed: %s", exc)
            return False
    
    async def flushdb(self) -> bool:
        """
        Clear all keys in current database (use with caution!).
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available:
            return False
        
        try:
            await self._client.flushdb()
            logger.warning("Redis database flushed")
            return True
        
        except Exception as exc:
            logger.error("Failed to flush database: %s", exc)
            return False


# ──────────────────────────────────────────────
# Global instance (lazy initialization)
# ──────────────────────────────────────────────

_redis_client: Optional[RedisClient] = None


def get_redis_client() -> RedisClient:
    """
    Get the global Redis client instance.
    
    Returns:
        RedisClient instance (may not be connected)
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client


async def init_redis() -> bool:
    """
    Initialize and connect the global Redis client.
    
    Returns:
        True if connected successfully, False otherwise
    
    Requirements: Req 10.4
    """
    client = get_redis_client()
    return await client.connect()


async def close_redis() -> None:
    """
    Close the global Redis client connection.
    
    Requirements: Req 10.4
    """
    global _redis_client
    if _redis_client is not None:
        await _redis_client.disconnect()
        _redis_client = None
