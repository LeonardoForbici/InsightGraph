"""
Event Stream Infrastructure for Real-Time Updates

This module provides Server-Sent Events (SSE) infrastructure for broadcasting
real-time updates to connected clients. It implements a publish/subscribe pattern
using asyncio.Queue for efficient event distribution.

Requirements: 13.1, 13.2, 13.3, 13.6
"""

from dataclasses import dataclass
from typing import Literal
import asyncio
import logging
import time

logger = logging.getLogger(__name__)

# Event types supported by the system
EventType = Literal[
    "graph_updated",
    "impact_detected",
    "audit_alert",
    "scan_complete"
]


@dataclass
class SSEEvent:
    """
    Server-Sent Event data structure.
    
    Attributes:
        type: Type of event (graph_updated, impact_detected, audit_alert, scan_complete)
        payload: Event-specific data as dictionary
        timestamp: Unix timestamp when event was created
    """
    type: EventType
    payload: dict
    timestamp: float


class EventStream:
    """
    Event streaming infrastructure for real-time updates.
    
    Manages a global event queue and broadcasts events to all connected clients
    using asyncio.Queue. Supports multiple concurrent subscribers with automatic
    cleanup on disconnection.
    
    Requirements:
        - 13.1: SSE for unidirectional server→client communication
        - 13.2: Asynchronous queue (asyncio.Queue) for pending events
        - 13.3: Broadcast to all clients in <100ms
        - 13.6: Support event types: graph_updated, impact_detected, audit_alert, scan_complete
    """
    
    def __init__(self):
        """Initialize event stream with empty queue and client list."""
        self.queue: asyncio.Queue = asyncio.Queue()
        self.clients: list[asyncio.Queue] = []
        self._broadcast_task: asyncio.Task | None = None
        
    async def publish(self, event: SSEEvent):
        """
        Publish event to all connected clients.
        
        Adds event to the global queue for broadcasting. The broadcast_loop
        background task will distribute it to all client queues.
        
        Args:
            event: SSEEvent to publish
            
        Requirements: 13.2, 13.3
        """
        await self.queue.put(event)
        logger.debug(f"Published event: {event.type} at {event.timestamp}")
        
    async def subscribe(self) -> asyncio.Queue:
        """
        Subscribe a new client to the event stream.
        
        Creates a new queue for the client and adds it to the client list.
        The client will receive all future events published to the stream.
        
        Returns:
            asyncio.Queue: Client-specific queue for receiving events
            
        Requirements: 13.1, 13.2
        """
        client_queue = asyncio.Queue()
        self.clients.append(client_queue)
        logger.info(f"Client subscribed. Total clients: {len(self.clients)}")
        return client_queue
        
    async def unsubscribe(self, client_queue: asyncio.Queue):
        """
        Unsubscribe a client from the event stream.
        
        Removes the client queue from the client list and performs cleanup.
        Should be called when a client disconnects.
        
        Args:
            client_queue: The client queue to remove
            
        Requirements: 13.5
        """
        if client_queue in self.clients:
            self.clients.remove(client_queue)
            logger.info(f"Client unsubscribed. Total clients: {len(self.clients)}")
            
    async def broadcast_loop(self):
        """
        Background task that broadcasts events to all clients.
        
        Continuously reads events from the global queue and distributes them
        to all connected client queues. Handles client errors gracefully by
        logging and continuing to serve other clients.
        
        This method should be run as a background task using asyncio.create_task().
        
        Requirements: 13.2, 13.3
        """
        logger.info("Event broadcast loop started")
        
        while True:
            try:
                # Wait for next event
                event = await self.queue.get()
                
                # Broadcast to all clients
                start_time = time.monotonic()
                failed_clients = []
                
                for client_queue in self.clients:
                    try:
                        # Non-blocking put with timeout to avoid slow clients blocking others
                        await asyncio.wait_for(
                            client_queue.put(event),
                            timeout=0.1  # 100ms timeout per requirement 13.3
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Client queue full, skipping event for slow client")
                        failed_clients.append(client_queue)
                    except Exception as e:
                        logger.error(f"Failed to send event to client: {e}")
                        failed_clients.append(client_queue)
                
                # Remove failed clients
                for failed_client in failed_clients:
                    await self.unsubscribe(failed_client)
                
                elapsed = (time.monotonic() - start_time) * 1000  # Convert to ms
                logger.debug(
                    f"Broadcasted {event.type} to {len(self.clients)} clients in {elapsed:.2f}ms"
                )
                
            except asyncio.CancelledError:
                logger.info("Broadcast loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in broadcast loop: {e}")
                # Continue serving despite errors
                
    def start_broadcast_loop(self):
        """
        Start the background broadcast loop.
        
        Creates and stores the broadcast task. Should be called once during
        application startup.
        """
        if self._broadcast_task is None or self._broadcast_task.done():
            self._broadcast_task = asyncio.create_task(self.broadcast_loop())
            logger.info("Broadcast loop task created")
        else:
            logger.warning("Broadcast loop already running")
            
    async def stop_broadcast_loop(self):
        """
        Stop the background broadcast loop.
        
        Cancels the broadcast task and waits for it to complete. Should be
        called during application shutdown.
        """
        if self._broadcast_task and not self._broadcast_task.done():
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
            logger.info("Broadcast loop stopped")
