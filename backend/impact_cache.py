"""
Impact Calculation Cache for performance optimization.

Caches impact calculation results with TTL and LRU eviction
to avoid redundant graph traversals.

Requirements:
    - 14.4: Cache impact results
    - 14.5: LRU eviction with max 1000 entries
"""

import time
import logging
from typing import Optional, Dict, Any
from collections import OrderedDict

logger = logging.getLogger(__name__)


class ImpactCache:
    """
    LRU cache for impact calculation results.
    
    Features:
    - TTL (Time To Live) for cache entries
    - LRU eviction when cache is full
    - Automatic invalidation on node changes
    """
    
    def __init__(self, max_size: int = 1000, ttl: int = 300):
        """
        Initialize ImpactCache.
        
        Args:
            max_size: Maximum number of cache entries (default: 1000)
            ttl: Time to live in seconds (default: 300 = 5 minutes)
        """
        self.max_size = max_size
        self.ttl = ttl
        self.cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.timestamps: Dict[str, float] = {}
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get cached impact result.
        
        Args:
            key: Cache key (typically node_key:max_depth)
        
        Returns:
            Cached result or None if not found/expired
        """
        if key not in self.cache:
            self.misses += 1
            return None
        
        # Check if expired
        timestamp = self.timestamps.get(key, 0)
        if time.time() - timestamp > self.ttl:
            # Expired - remove from cache
            del self.cache[key]
            del self.timestamps[key]
            self.misses += 1
            return None
        
        # Move to end (most recently used)
        self.cache.move_to_end(key)
        self.hits += 1
        
        return self.cache[key]
    
    def set(self, key: str, value: Any) -> None:
        """
        Store impact result in cache.
        
        Args:
            key: Cache key
            value: Impact result to cache
        """
        # Check if cache is full
        if len(self.cache) >= self.max_size and key not in self.cache:
            # Evict least recently used entry
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            del self.timestamps[oldest_key]
            logger.debug(f"Evicted cache entry: {oldest_key}")
        
        # Store value
        self.cache[key] = value
        self.timestamps[key] = time.time()
        
        # Move to end (most recently used)
        if key in self.cache:
            self.cache.move_to_end(key)
    
    def invalidate(self, node_key: str) -> int:
        """
        Invalidate all cache entries related to a node.
        
        Called when a node changes to ensure cache consistency.
        
        Args:
            node_key: Node that changed
        
        Returns:
            Number of entries invalidated
        """
        invalidated = 0
        keys_to_remove = []
        
        # Find all cache entries that include this node
        for cache_key in self.cache.keys():
            # Cache key format: "node_key:max_depth"
            if cache_key.startswith(f"{node_key}:"):
                keys_to_remove.append(cache_key)
        
        # Remove invalidated entries
        for cache_key in keys_to_remove:
            del self.cache[cache_key]
            del self.timestamps[cache_key]
            invalidated += 1
        
        if invalidated > 0:
            logger.debug(f"Invalidated {invalidated} cache entries for node: {node_key}")
        
        return invalidated
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
        self.timestamps.clear()
        self.hits = 0
        self.misses = 0
        logger.info("Impact cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache stats
        """
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(hit_rate, 2),
            "ttl": self.ttl
        }
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.
        
        Returns:
            Number of entries removed
        """
        current_time = time.time()
        expired_keys = []
        
        for key, timestamp in self.timestamps.items():
            if current_time - timestamp > self.ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
            del self.timestamps[key]
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
        
        return len(expired_keys)


# Global cache instance
_impact_cache = ImpactCache()


def get_impact_cache() -> ImpactCache:
    """Get the global impact cache instance."""
    return _impact_cache
