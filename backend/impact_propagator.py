"""
ImpactPropagator â€” real-time impact broadcasting powered by the ImpactEngine.

Propagates code changes over WebSocket clients, publishes to Redis channels,
and batches events to avoid visual overload while keeping latency under 100ms.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict
from typing import Any, Awaitable, Callable, Dict, List, Optional

from impact_engine import ChangeDescriptor, ImpactEngine, AffectedItem, AffectedSet
from redis_client import IMPACT_EVENTS_CHANNEL, RedisClient
from websocket_manager import BroadcastEvent, WebSocketManager
from event_batcher import EventBatcher
from monitoring import observe_event_batch, record_event_latency

logger = logging.getLogger("insightgraph.impact_propagator")


class ImpactPropagator:
    """Coordinates impact BFS runs, batching, and broadcasting to clients."""

    def __init__(
        self,
        impact_engine_factory: Callable[[], ImpactEngine],
        websocket_manager: WebSocketManager,
        redis_client: RedisClient,
        batch_window_ms: int = 100,
        max_depth: int = 5,
    ):
        self._impact_engine_factory = impact_engine_factory
        self._websocket_manager = websocket_manager
        self._redis_client = redis_client
        self._max_depth = max_depth
        self._batcher = EventBatcher(batch_window_ms, self._flush_events)

    async def propagate_change(
        self,
        node_key: str,
        change_type: str = "code_change",
        context: Optional[Dict[str, Any]] = None,
        target_users: Optional[List[str]] = None,
        max_depth: Optional[int] = None,
    ) -> None:
        if not node_key:
            logger.debug("Skipping propagation â€” no node_key provided")
            return

        depth = max_depth or self._max_depth
        change = ChangeDescriptor(
            change_type=change_type,
            target_key=node_key,
            max_depth=depth,
        )

        affected_set = await asyncio.to_thread(self.calculate_affected_nodes, node_key, depth)
        payload = self._build_payload(
            node_key=node_key,
            change_type=change_type,
            affected_set=affected_set,
            context=context,
        )

        event = BroadcastEvent(
            event_type="impact",
            payload=payload,
            target_users=target_users,
        )

        await self._batcher.add_event(event)

    def calculate_affected_nodes(
        self,
        node_key: str,
        max_depth: Optional[int] = None,
    ) -> AffectedSet:
        depth = max_depth or self._max_depth
        change = ChangeDescriptor(
            change_type="code_change",
            target_key=node_key,
            max_depth=depth,
        )
        engine = self._impact_engine_factory()
        return engine.analyze(change)

    def _build_payload(
        self,
        node_key: str,
        change_type: str,
        affected_set: AffectedSet,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        scores = [item.confidence_score for item in affected_set.items]
        max_score = max(scores) if scores else 0

        return {
            "origin_node": node_key,
            "change_type": change_type,
            "context": context or {},
            "max_risk_score": max_score,
            "affected_nodes": [self._serialize_item(item) for item in affected_set.items],
            "analysis_metadata": asdict(affected_set.analysis_metadata),
            "timestamp": time.time(),
            "total_affected": len(affected_set.items),
        }

    @staticmethod
    def _serialize_item(item: AffectedItem) -> Dict[str, Any]:
        distance = max(0, len(item.call_chain) - 1)
        return {
            "node_key": item.namespace_key,
            "name": item.name,
            "labels": item.labels,
            "category": item.category,
            "confidence": item.confidence_score,
            "distance": distance,
            "call_chain": item.call_chain,
            "requires_manual_review": item.requires_manual_review,
            "resolution_method": item.resolution_method,
            "predicted_risk": getattr(item, "predicted_risk", 0.0),
        }

    async def _flush_events(self, events: List[BroadcastEvent]) -> None:
        if not events:
            return

        observe_event_batch(len(events))

        if len(events) == 1:
            event = events[0]
            await self._log_and_broadcast(event.event_type, event.payload, event.target_users)
        else:
            target_users = (
                None
                if any(event.target_users is None for event in events)
                else list({user for event in events if event.target_users for user in event.target_users})
            )
            payload = {
                "batch": [event.payload for event in events],
                "batch_size": len(events),
                "timestamp": time.time(),
            }
            await self._log_and_broadcast("impact_batch", payload, target_users)

    async def _broadcast(
        self,
        event_type: str,
        payload: Dict[str, Any],
        target_users: Optional[List[str]],
    ) -> None:
        event = BroadcastEvent(
            event_type=event_type,
            payload=payload,
            target_users=target_users,
            timestamp=time.time(),
        )

        await self._websocket_manager.broadcast(event, target_users=target_users)
        await self._publish_to_redis(event)

    async def _log_and_broadcast(
        self,
        event_type: str,
        payload: Dict[str, Any],
        target_users: Optional[List[str]],
    ) -> None:
        target_desc = f"{len(target_users)} users" if target_users else "all users"
        batch_size = None
        if isinstance(payload, dict):
            batch_size = payload.get("batch_size")

        logger.info(
            "Propagating event '%s' to %s%s",
            event_type,
            target_desc,
            f" (batch={batch_size})" if batch_size is not None else "",
        )
        start = time.monotonic()
        try:
            await self._broadcast(event_type, payload, target_users)
        finally:
            record_event_latency(event_type, time.monotonic() - start)

    async def _publish_to_redis(self, event: BroadcastEvent) -> None:
        if not self._redis_client.is_available:
            return
        try:
            message = json.dumps(
                {
                    "event_type": event.event_type,
                    "payload": event.payload,
                    "timestamp": event.timestamp,
                }
            )
            await self._redis_client.publish(IMPACT_EVENTS_CHANNEL, message)
        except Exception as exc:
            logger.debug("Redis publish failed: %s", exc)
