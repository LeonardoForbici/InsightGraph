"""
Optimized Event Stream for improved SSE broadcasting performance.

Optimizations:
- Serialize events once before broadcasting
- Use non-blocking queue puts with timeout
- Automatic removal of slow/dead clients
- Track client IDs for better management

Requirements:
    - 13.3: Broadcast optimization
"""

from dataclasses import dataclass
from typing import Literal, Dict
import asyncio
import logging
import time
import json
import uuid

logger = logging.getLogger(__name__)

EventType = Literal[
    "graph_updated",
    "impact_detected",
    "audit_alert",
    "scan_complete"
]


@dataclass
class SSEEvent:
    """Server-Sent Event data structure."""
    type: EventType
    payload: dict
    timestamp: float


class OptimizedEventStream:
    """
    Optimized event streaming infrastructure.
    
    Improvements over basic EventStream:
    - Serializes events once before broadcasting (reduces CPU)
    - Tracks client IDs for better management
    - Automatically removes slow/dead clients
    - Non-blocking queue operations
    
    Requirements:
        - 13.3: Optimized SSE broadcasting
    """
    
    def __init__(self):
        """Initialize optimized event stream."""
        self.queue: asyncio.Queue = asyncio.Queue()
        self.clients: Dict[str, asyncio.Queue] = {}
        self._broadcast_task: asyncio.Task | None = None
        self._stats = {
            "events_published": 0,
            "events_broadcasted": 0,
            "clients_removed": 0,
            "broadcast_errors": 0
        }
        
    async def publish(self, event: SSEEvent):
        """
        Publish event to all connected clients.
        
        Args:
            event: SSEEvent to publish
        """
        await self.queue.put(event)
        self._stats["events_published"] += 1
        logger.debug(f"Published event: {event.type}")
        
    async def subscribe(self) -> tuple[str, asyncio.Queue]:
        """
        Subscribe a new client to the event stream.
        
        Returns:
            Tuple of (client_id, client_queue)
        """
        client_id = str(uuid.uuid4())
        client_queue = asyncio.Queue(maxsize=100)  # Limit queue size
        self.clients[client_id] = client_queue
        logger.info(f"Client {client_id} subscribed. Total: {len(self.clients)}")
        return client_id, client_queue
        
    async def unsubscribe(self, client_id: str):
        """
        Unsubscribe a client from the event stream.
        
        Args:
            client_id: Client identifier
        """
        if client_id in self.clients:
            del self.clients[client_id]
            self._stats["clients_removed"] += 1
            logger.info(f"Client {client_id} unsubscribed. Total: {len(self.clients)}")
            
    async def broadcast_loop(self):
        """
        Optimized background task for broadcasting events.
        
        Optimizations:
        - Serialize event once before broadcasting
        - Use non-blocking puts with timeout
        - Remove slow clients automatically
        """
        logger.info("Optimized broadcast loop started")
        
        while True:
            try:
                # Wait for next event
                event = await self.queue.get()
                
                # Serialize event once (optimization)
                try:
                    serialized_event = json.dumps({
                        "type": event.type,
                        "payload": event.payload,
                        "timestamp": event.timestamp
                    })
                except Exception as e:
                    logger.error(f"Failed to serialize event: {e}")
                    continue
                
                # Broadcast to all clients
                start_time = time.monotonic()
                slow_clients = []
                
                for client_id, client_queue in list(self.clients.items()):
                    try:
                        # Non-blocking put with timeout
                        await asyncio.wait_for(
                            client_queue.put(serialized_event),
                            timeout=0.05  # 50ms timeout
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Client {client_id} is slow, marking for removal")
                        slow_clients.append(client_id)
                    except asyncio.QueueFull:
                        logger.warning(f"Client {client_id} queue full, marking for removal")
                        slow_clients.append(client_id)
                    except Exception as e:
                        logger.error(f"Failed to send to client {client_id}: {e}")
                        slow_clients.append(client_id)
                        self._stats["broadcast_errors"] += 1
                
                # Remove slow/dead clients
                for client_id in slow_clients:
                    await self.unsubscribe(client_id)
                
                elapsed = (time.monotonic() - start_time) * 1000
                self._stats["events_broadcasted"] += 1
                
                logger.debug(
                    f"Broadcasted {event.type} to {len(self.clients)} clients "
                    f"in {elapsed:.2f}ms (removed {len(slow_clients)} slow clients)"
                )
                
            except asyncio.CancelledError:
                logger.info("Optimized broadcast loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in optimized broadcast loop: {e}")
                
    def start_broadcast_loop(self):
        """Start the background broadcast loop."""
        if self._broadcast_task is None or self._broadcast_task.done():
            self._broadcast_task = asyncio.create_task(self.broadcast_loop())
            logger.info("Optimized broadcast loop started")
        else:
            logger.warning("Broadcast loop already running")
            
    async def stop_broadcast_loop(self):
        """Stop the background broadcast loop."""
        if self._broadcast_task and not self._broadcast_task.done():
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
            logger.info("Optimized broadcast loop stopped")
    
    def get_stats(self) -> dict:
        """
        Get broadcasting statistics.
        
        Returns:
            Dictionary with stats
        """
        return {
            **self._stats,
            "active_clients": len(self.clients),
            "queue_size": self.queue.qsize()
        }
