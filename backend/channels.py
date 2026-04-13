"""
Channels — Type-safe pub/sub channel management for real-time events.

Provides strongly-typed event models and helper functions for publishing
and subscribing to Redis pub/sub channels with automatic JSON serialization.

Requirements: Req 1 (Real-time reactivity), Req 5 (Collaboration)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Literal, Any, Optional, Callable, Awaitable
from datetime import datetime

from redis_client import (
    RedisClient,
    get_redis_client,
    IMPACT_EVENTS_CHANNEL,
    COLLABORATION_EVENTS_CHANNEL,
)

logger = logging.getLogger("insightgraph.channels")


# ──────────────────────────────────────────────
# Event Type Definitions
# ──────────────────────────────────────────────

EventType = Literal["commit", "impact", "cursor", "selection", "annotation"]


# ──────────────────────────────────────────────
# Event Models
# ──────────────────────────────────────────────

@dataclass
class CommitEvent:
    """
    Event triggered when a commit is detected.
    
    Requirements: Req 1.1 (Real-time reactivity)
    """
    type: Literal["commit"] = "commit"
    commit_hash: str = ""
    author: str = ""
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    changed_files: list[str] = field(default_factory=list)
    affected_nodes: list[str] = field(default_factory=list)


@dataclass
class AffectedNode:
    """Node affected by an impact event."""
    node_key: str
    distance: int
    risk_score: float


@dataclass
class ImpactEvent:
    """
    Event triggered when code changes propagate through the graph.
    
    Requirements: Req 1.1 (Real-time reactivity)
    """
    type: Literal["impact"] = "impact"
    origin_node: str = ""
    affected_nodes: list[AffectedNode] = field(default_factory=list)
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())


@dataclass
class CursorEvent:
    """
    Event for collaborative cursor position updates.
    
    Requirements: Req 5 (Collaboration)
    """
    type: Literal["cursor"] = "cursor"
    user_id: str = ""
    session_id: str = ""
    position: dict[str, float] = field(default_factory=dict)  # {x, y, z}
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())


@dataclass
class SelectionEvent:
    """
    Event for collaborative node selection.
    
    Requirements: Req 5 (Collaboration)
    """
    type: Literal["selection"] = "selection"
    user_id: str = ""
    session_id: str = ""
    selected_nodes: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())


@dataclass
class AnnotationEvent:
    """
    Event for collaborative annotations on nodes.
    
    Requirements: Req 5 (Collaboration)
    """
    type: Literal["annotation"] = "annotation"
    user_id: str = ""
    session_id: str = ""
    node_key: str = ""
    text: str = ""
    annotation_id: str = ""
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())


# Union type for all events
Event = CommitEvent | ImpactEvent | CursorEvent | SelectionEvent | AnnotationEvent


# ──────────────────────────────────────────────
# Serialization Helpers
# ──────────────────────────────────────────────

def serialize_event(event: Event) -> str:
    """
    Serialize an event to JSON string.
    
    Args:
        event: Event object to serialize
    
    Returns:
        JSON string representation
    
    Requirements: Req 1.1, Req 5
    """
    try:
        # Convert dataclass to dict, handling nested dataclasses
        event_dict = asdict(event)
        return json.dumps(event_dict)
    except Exception as exc:
        logger.error("Failed to serialize event: %s", exc)
        raise


def deserialize_event(data: str) -> Optional[Event]:
    """
    Deserialize JSON string to an event object.
    
    Args:
        data: JSON string to deserialize
    
    Returns:
        Event object or None if deserialization fails
    
    Requirements: Req 1.1, Req 5
    """
    try:
        event_dict = json.loads(data)
        event_type = event_dict.get("type")
        
        if event_type == "commit":
            return CommitEvent(**event_dict)
        elif event_type == "impact":
            # Handle nested AffectedNode objects
            affected_nodes = [
                AffectedNode(**node) if isinstance(node, dict) else node
                for node in event_dict.get("affected_nodes", [])
            ]
            event_dict["affected_nodes"] = affected_nodes
            return ImpactEvent(**event_dict)
        elif event_type == "cursor":
            return CursorEvent(**event_dict)
        elif event_type == "selection":
            return SelectionEvent(**event_dict)
        elif event_type == "annotation":
            return AnnotationEvent(**event_dict)
        else:
            logger.warning("Unknown event type: %s", event_type)
            return None
    
    except Exception as exc:
        logger.error("Failed to deserialize event: %s", exc)
        return None


# ──────────────────────────────────────────────
# Channel Management
# ──────────────────────────────────────────────

class ChannelManager:
    """
    High-level manager for pub/sub channels with type-safe event handling.
    
    Provides convenience methods for publishing and subscribing to events
    with automatic serialization/deserialization.
    
    Requirements: Req 1.1, Req 5
    """
    
    def __init__(self, redis_client: Optional[RedisClient] = None):
        """
        Initialize channel manager.
        
        Args:
            redis_client: Redis client instance (uses global if None)
        """
        self._redis = redis_client or get_redis_client()
    
    # ──────────────────────────────────────────────
    # Impact Events Channel
    # ──────────────────────────────────────────────
    
    async def publish_commit_event(self, event: CommitEvent) -> int:
        """
        Publish a commit event to the impact_events channel.
        
        Args:
            event: CommitEvent to publish
        
        Returns:
            Number of subscribers that received the event
        
        Requirements: Req 1.1
        """
        message = serialize_event(event)
        result = await self._redis.publish(IMPACT_EVENTS_CHANNEL, message)
        logger.debug("Published CommitEvent: commit=%s, subscribers=%d", event.commit_hash, result)
        return result
    
    async def publish_impact_event(self, event: ImpactEvent) -> int:
        """
        Publish an impact event to the impact_events channel.
        
        Args:
            event: ImpactEvent to publish
        
        Returns:
            Number of subscribers that received the event
        
        Requirements: Req 1.1
        """
        message = serialize_event(event)
        result = await self._redis.publish(IMPACT_EVENTS_CHANNEL, message)
        logger.debug(
            "Published ImpactEvent: origin=%s, affected=%d, subscribers=%d",
            event.origin_node,
            len(event.affected_nodes),
            result,
        )
        return result
    
    async def subscribe_impact_events(
        self,
        handler: Callable[[Event], Awaitable[None]],
    ) -> None:
        """
        Subscribe to impact events with a handler function.
        
        Args:
            handler: Async function to handle received events
        
        Requirements: Req 1.1
        """
        async with self._redis.subscribe(IMPACT_EVENTS_CHANNEL) as pubsub:
            if pubsub is None:
                logger.warning("Redis not available — impact events subscription skipped")
                return
            
            logger.info("Subscribed to impact_events channel")
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    event = deserialize_event(data)
                    
                    if event is not None:
                        try:
                            await handler(event)
                        except Exception as exc:
                            logger.error("Error in impact event handler: %s", exc)
    
    # ──────────────────────────────────────────────
    # Collaboration Events Channel
    # ──────────────────────────────────────────────
    
    async def publish_cursor_event(self, event: CursorEvent) -> int:
        """
        Publish a cursor event to the collaboration_events channel.
        
        Args:
            event: CursorEvent to publish
        
        Returns:
            Number of subscribers that received the event
        
        Requirements: Req 5
        """
        message = serialize_event(event)
        result = await self._redis.publish(COLLABORATION_EVENTS_CHANNEL, message)
        logger.debug("Published CursorEvent: user=%s, session=%s", event.user_id, event.session_id)
        return result
    
    async def publish_selection_event(self, event: SelectionEvent) -> int:
        """
        Publish a selection event to the collaboration_events channel.
        
        Args:
            event: SelectionEvent to publish
        
        Returns:
            Number of subscribers that received the event
        
        Requirements: Req 5
        """
        message = serialize_event(event)
        result = await self._redis.publish(COLLABORATION_EVENTS_CHANNEL, message)
        logger.debug(
            "Published SelectionEvent: user=%s, nodes=%d",
            event.user_id,
            len(event.selected_nodes),
        )
        return result
    
    async def publish_annotation_event(self, event: AnnotationEvent) -> int:
        """
        Publish an annotation event to the collaboration_events channel.
        
        Args:
            event: AnnotationEvent to publish
        
        Returns:
            Number of subscribers that received the event
        
        Requirements: Req 5
        """
        message = serialize_event(event)
        result = await self._redis.publish(COLLABORATION_EVENTS_CHANNEL, message)
        logger.debug(
            "Published AnnotationEvent: user=%s, node=%s",
            event.user_id,
            event.node_key,
        )
        return result
    
    async def subscribe_collaboration_events(
        self,
        handler: Callable[[Event], Awaitable[None]],
    ) -> None:
        """
        Subscribe to collaboration events with a handler function.
        
        Args:
            handler: Async function to handle received events
        
        Requirements: Req 5
        """
        async with self._redis.subscribe(COLLABORATION_EVENTS_CHANNEL) as pubsub:
            if pubsub is None:
                logger.warning("Redis not available — collaboration events subscription skipped")
                return
            
            logger.info("Subscribed to collaboration_events channel")
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    event = deserialize_event(data)
                    
                    if event is not None:
                        try:
                            await handler(event)
                        except Exception as exc:
                            logger.error("Error in collaboration event handler: %s", exc)


# ──────────────────────────────────────────────
# Global instance (lazy initialization)
# ──────────────────────────────────────────────

_channel_manager: Optional[ChannelManager] = None


def get_channel_manager() -> ChannelManager:
    """
    Get the global ChannelManager instance.
    
    Returns:
        ChannelManager instance
    """
    global _channel_manager
    if _channel_manager is None:
        _channel_manager = ChannelManager()
    return _channel_manager
