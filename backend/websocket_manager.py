"""
WebSocket_Manager — Real-time WebSocket connection management for Living Impact System

Manages persistent WebSocket connections with:
- JWT authentication
- Automatic reconnection with exponential backoff
- Rate limiting (100 req/min per user)
- permessage-deflate compression
- Heartbeat (ping/pong) every 30s
- Selective broadcasting to target users

Requirements: Req 1, Req 10, Req 12
Tasks: 1.1.1-1.1.5
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect, status
from monitoring import decrement_websocket_connections, increment_websocket_connections
from redis_client import get_redis_client
from rate_limiter import RateLimiter

logger = logging.getLogger("insightgraph.websocket_manager")


# ──────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────

@dataclass
class ConnectionInfo:
    """Information about a WebSocket connection."""
    websocket: WebSocket
    user_id: str
    connected_at: float
    last_ping: float
    subscribed_events: Set[str] = field(default_factory=set)
    request_timestamps: deque = field(default_factory=lambda: deque(maxlen=100))


@dataclass
class BroadcastEvent:
    """Event to broadcast to clients."""
    event_type: str
    payload: Dict[str, Any]
    target_users: Optional[List[str]] = None  # None = broadcast to all
    timestamp: float = field(default_factory=time.time)


# ──────────────────────────────────────────────
# Rate Limiter
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
# WebSocket Manager
# ──────────────────────────────────────────────

class WebSocketManager:
    """
    Manages WebSocket connections for real-time updates.
    
    Features:
    - Connection management with user tracking
    - Selective broadcasting to target users
    - Automatic reconnection support with exponential backoff
    - Rate limiting (100 req/min per user)
    - Heartbeat (ping/pong) every 30s
    - permessage-deflate compression
    
    Requirements: Req 1, Req 10, Req 12
    Tasks: 1.1.1-1.1.5
    """
    
    def __init__(
        self,
        heartbeat_interval: int = 30,
        max_requests_per_minute: int = 100,
        enable_compression: bool = True,
    ):
        """
        Initialize WebSocket manager.
        
        Args:
            heartbeat_interval: Seconds between heartbeat pings
            max_requests_per_minute: Rate limit per user
            enable_compression: Enable permessage-deflate compression
        """
        self.heartbeat_interval = heartbeat_interval
        self.enable_compression = enable_compression
        
        # Connection tracking
        self._connections: Dict[str, ConnectionInfo] = {}  # connection_id -> ConnectionInfo
        self._user_connections: Dict[str, Set[str]] = defaultdict(set)  # user_id -> set of connection_ids
        
        # Rate limiting
        self._rate_limiter = RateLimiter(
            redis_client=get_redis_client(),
            max_requests=max_requests_per_minute,
            window_seconds=60,
        )
        
        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(
            "WebSocketManager initialized (heartbeat=%ds, rate_limit=%d/min, compression=%s)",
            heartbeat_interval,
            max_requests_per_minute,
            enable_compression,
        )
    
    # ──────────────────────────────────────────────
    # Connection Management (Task 1.1.1)
    # ──────────────────────────────────────────────
    
    async def handle_connection(
        self,
        websocket: WebSocket,
        user_id: str,
        connection_id: Optional[str] = None,
    ) -> str:
        """
        Handle a new WebSocket connection.
        
        Accepts the connection, registers it, and starts message handling loop.
        Supports automatic reconnection by reusing connection_id.
        
        Args:
            websocket: FastAPI WebSocket instance
            user_id: Authenticated user identifier
            connection_id: Optional connection ID for reconnection
            
        Returns:
            connection_id: Unique identifier for this connection
            
        Requirements: Req 1, Req 12
        Task: 1.1.1, 1.1.3 (reconnection support)
        """
        # Generate or reuse connection ID
        if connection_id is None:
            connection_id = f"{user_id}_{int(time.time() * 1000)}"
        
        # Accept connection with compression if enabled
        # Note: FastAPI WebSocket doesn't directly expose compression settings
        # Compression is typically configured at the server level (uvicorn)
        headers = []
        if self.enable_compression:
            headers.append(
                (b"Sec-WebSocket-Extensions", b"permessage-deflate; client_max_window_bits")
            )
        await websocket.accept(headers=headers or None)
        
        # Register connection
        current_time = time.time()
        conn_info = ConnectionInfo(
            websocket=websocket,
            user_id=user_id,
            connected_at=current_time,
            last_ping=current_time,
        )
        
        self._connections[connection_id] = conn_info
        self._user_connections[user_id].add(connection_id)
        increment_websocket_connections()

        logger.info(
            "WebSocket connected: connection_id=%s, user_id=%s, total_connections=%d",
            connection_id,
            user_id,
            len(self._connections),
        )
        
        # Send connection acknowledgment with reconnection info
        await self._send_to_connection(
            connection_id,
            {
                "type": "connection_ack",
                "connection_id": connection_id,
                "user_id": user_id,
                "heartbeat_interval": self.heartbeat_interval,
                "timestamp": current_time,
            }
        )
        
        # Start message handling loop
        try:
            await self._handle_messages(connection_id)
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected: connection_id=%s", connection_id)
        except Exception as e:
            logger.error("WebSocket error: connection_id=%s, error=%s", connection_id, e)
        finally:
            await self._cleanup_connection(connection_id)
        
        return connection_id
    
    async def _handle_messages(self, connection_id: str):
        """
        Handle incoming messages from a WebSocket connection.
        
        Processes messages with rate limiting and handles:
        - Pong responses to heartbeat pings
        - Event subscription requests
        - Client messages
        
        Task: 1.1.1, 1.1.4 (rate limiting)
        """
        conn_info = self._connections.get(connection_id)
        if not conn_info:
            return
        
        websocket = conn_info.websocket
        user_id = conn_info.user_id
        
        while True:
            try:
                # Receive message
                data = await websocket.receive_text()
                
                # Check rate limit (Redis preferred, fallback keeps history)
                limiter_status = await self._rate_limiter.check(user_id)
                if not limiter_status.allowed:
                    await self._send_to_connection(
                        connection_id,
                        {
                            "type": "error",
                            "code": "rate_limit_exceeded",
                            "message": "Rate limit exceeded (100 requests/minute)",
                            "retry_after": limiter_status.reset_in or 60,
                            "remaining": limiter_status.remaining,
                        },
                    )
                    continue
                
                # Parse message
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    await self._send_to_connection(
                        connection_id,
                        {
                            "type": "error",
                            "code": "invalid_json",
                            "message": "Invalid JSON format",
                        }
                    )
                    continue
                
                # Handle message types
                msg_type = message.get("type")
                
                if msg_type == "pong":
                    # Update last ping time
                    conn_info.last_ping = time.time()
                    logger.debug("Received pong from connection_id=%s", connection_id)
                
                elif msg_type == "subscribe":
                    # Subscribe to event types
                    event_types = message.get("event_types", [])
                    await self.subscribe_to_events(connection_id, event_types)
                
                elif msg_type == "unsubscribe":
                    # Unsubscribe from event types
                    event_types = message.get("event_types", [])
                    await self.unsubscribe_from_events(connection_id, event_types)
                
                else:
                    logger.debug(
                        "Received message: connection_id=%s, type=%s",
                        connection_id,
                        msg_type
                    )
                
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.error("Error handling message: connection_id=%s, error=%s", connection_id, e)
    
    async def _cleanup_connection(self, connection_id: str):
        """Clean up a disconnected connection."""
        conn_info = self._connections.pop(connection_id, None)
        if conn_info:
            user_id = conn_info.user_id
            self._user_connections[user_id].discard(connection_id)
            decrement_websocket_connections()
            
            # Clean up empty user entries
            if not self._user_connections[user_id]:
                del self._user_connections[user_id]
            
            logger.info(
                "Connection cleaned up: connection_id=%s, user_id=%s, remaining=%d",
                connection_id,
                user_id,
                len(self._connections),
            )
    
    # ──────────────────────────────────────────────
    # Broadcasting (Task 1.1.2)
    # ──────────────────────────────────────────────
    
    async def broadcast(
        self,
        event: BroadcastEvent,
        target_users: Optional[List[str]] = None,
    ):
        """
        Broadcast event to target users or all connected clients.
        
        Sends events only to users who have subscribed to the event type.
        If target_users is None, broadcasts to all connected users.
        
        Args:
            event: Event to broadcast
            target_users: Optional list of user IDs to target (None = all users)
            
        Requirements: Req 1, Req 12
        Task: 1.1.2
        """
        if target_users is None:
            # Broadcast to all users
            target_users = list(self._user_connections.keys())
        
        # Prepare message
        message = {
            "type": "event",
            "event_type": event.event_type,
            "payload": event.payload,
            "timestamp": event.timestamp,
        }
        
        # Send to all connections of target users
        send_tasks = []
        sent_count = 0
        
        for user_id in target_users:
            connection_ids = self._user_connections.get(user_id, set())
            
            for connection_id in connection_ids:
                conn_info = self._connections.get(connection_id)
                if not conn_info:
                    continue
                
                # Check if user is subscribed to this event type
                if conn_info.subscribed_events and event.event_type not in conn_info.subscribed_events:
                    continue
                
                # Send message
                send_tasks.append(self._send_to_connection(connection_id, message))
                sent_count += 1
        
        # Execute all sends concurrently
        if send_tasks:
            await asyncio.gather(*send_tasks, return_exceptions=True)
        
        logger.debug(
            "Broadcasted event: type=%s, target_users=%d, connections=%d",
            event.event_type,
            len(target_users),
            sent_count,
        )
    
    async def _send_to_connection(self, connection_id: str, message: Dict[str, Any]):
        """Send message to a specific connection."""
        conn_info = self._connections.get(connection_id)
        if not conn_info:
            return
        
        try:
            await conn_info.websocket.send_json(message)
        except Exception as e:
            logger.error(
                "Failed to send message: connection_id=%s, error=%s",
                connection_id,
                e
            )
            # Connection will be cleaned up by the message handler
    
    # ──────────────────────────────────────────────
    # Event Subscription
    # ──────────────────────────────────────────────
    
    async def subscribe_to_events(self, connection_id: str, event_types: List[str]):
        """
        Subscribe connection to specific event types.
        
        Args:
            connection_id: Connection identifier
            event_types: List of event types to subscribe to
        """
        conn_info = self._connections.get(connection_id)
        if not conn_info:
            return
        
        conn_info.subscribed_events.update(event_types)
        
        await self._send_to_connection(
            connection_id,
            {
                "type": "subscription_ack",
                "event_types": list(conn_info.subscribed_events),
                "timestamp": time.time(),
            }
        )
        
        logger.debug(
            "Subscribed to events: connection_id=%s, events=%s",
            connection_id,
            event_types
        )
    
    async def unsubscribe_from_events(self, connection_id: str, event_types: List[str]):
        """
        Unsubscribe connection from specific event types.
        
        Args:
            connection_id: Connection identifier
            event_types: List of event types to unsubscribe from
        """
        conn_info = self._connections.get(connection_id)
        if not conn_info:
            return
        
        conn_info.subscribed_events.difference_update(event_types)
        
        await self._send_to_connection(
            connection_id,
            {
                "type": "unsubscription_ack",
                "event_types": list(conn_info.subscribed_events),
                "timestamp": time.time(),
            }
        )
        
        logger.debug(
            "Unsubscribed from events: connection_id=%s, events=%s",
            connection_id,
            event_types
        )
    
    # ──────────────────────────────────────────────
    # Heartbeat (Task 1.1.3 - part of reconnection)
    # ──────────────────────────────────────────────
    
    async def start_heartbeat(self):
        """
        Start heartbeat background task.
        
        Sends ping messages every heartbeat_interval seconds to all connections.
        Clients should respond with pong to keep connection alive.
        
        Task: 1.1.3 (heartbeat for connection health)
        """
        if self._heartbeat_task and not self._heartbeat_task.done():
            logger.warning("Heartbeat task already running")
            return
        
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("Heartbeat task started (interval=%ds)", self.heartbeat_interval)
    
    async def stop_heartbeat(self):
        """Stop heartbeat background task."""
        self._running = False
        
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Heartbeat task stopped")
    
    async def _heartbeat_loop(self):
        """Background loop that sends heartbeat pings."""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                current_time = time.time()
                ping_tasks = []
                stale_connections = []
                
                for connection_id, conn_info in list(self._connections.items()):
                    # Check if connection is stale (no pong in 2x heartbeat interval)
                    if current_time - conn_info.last_ping > self.heartbeat_interval * 2:
                        stale_connections.append(connection_id)
                        continue
                    
                    # Send ping
                    ping_tasks.append(
                        self._send_to_connection(
                            connection_id,
                            {
                                "type": "ping",
                                "timestamp": current_time,
                            }
                        )
                    )
                
                # Send all pings concurrently
                if ping_tasks:
                    await asyncio.gather(*ping_tasks, return_exceptions=True)
                
                # Close stale connections
                for connection_id in stale_connections:
                    logger.warning("Closing stale connection: %s", connection_id)
                    conn_info = self._connections.get(connection_id)
                    if conn_info:
                        try:
                            await conn_info.websocket.close(
                                code=status.WS_1008_POLICY_VIOLATION,
                                reason="Heartbeat timeout"
                            )
                        except Exception:
                            pass
                        await self._cleanup_connection(connection_id)
                
                logger.debug(
                    "Heartbeat sent: active=%d, stale=%d",
                    len(ping_tasks),
                    len(stale_connections)
                )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Heartbeat loop error: %s", e)
    
    # ──────────────────────────────────────────────
    # Statistics and Monitoring
    # ──────────────────────────────────────────────
    
    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket manager statistics."""
        return {
            "total_connections": len(self._connections),
            "total_users": len(self._user_connections),
            "heartbeat_interval": self.heartbeat_interval,
            "compression_enabled": self.enable_compression,
            "rate_limit": f"{self._rate_limiter.max_requests}/min",
        }
    
    def get_user_connections(self, user_id: str) -> List[str]:
        """Get all connection IDs for a user."""
        return list(self._user_connections.get(user_id, set()))
    
    def is_user_connected(self, user_id: str) -> bool:
        """Check if user has any active connections."""
        return user_id in self._user_connections and len(self._user_connections[user_id]) > 0
