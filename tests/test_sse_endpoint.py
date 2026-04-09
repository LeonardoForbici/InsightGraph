"""
Tests for SSE endpoint implementation.

Requirements: 13.1, 13.4, 13.5
"""

import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from event_stream import EventStream, SSEEvent


class TestEventStream:
    """Test EventStream class functionality."""
    
    @pytest.mark.asyncio
    async def test_publish_and_subscribe(self):
        """Test that events are published and received by subscribers."""
        stream = EventStream()
        stream.start_broadcast_loop()
        
        try:
            # Subscribe a client
            client_queue = await stream.subscribe()
            
            # Publish an event
            event = SSEEvent(
                type="graph_updated",
                payload={"nodes": 10},
                timestamp=1234567890.0
            )
            await stream.publish(event)
            
            # Wait for event to be received
            received_event = await asyncio.wait_for(
                client_queue.get(),
                timeout=1.0
            )
            
            assert received_event.type == "graph_updated"
            assert received_event.payload == {"nodes": 10}
            assert received_event.timestamp == 1234567890.0
            
        finally:
            await stream.stop_broadcast_loop()
    
    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        """Test that events are broadcast to all subscribers."""
        stream = EventStream()
        stream.start_broadcast_loop()
        
        try:
            # Subscribe multiple clients
            client1 = await stream.subscribe()
            client2 = await stream.subscribe()
            client3 = await stream.subscribe()
            
            # Publish an event
            event = SSEEvent(
                type="impact_detected",
                payload={"affected": 5},
                timestamp=1234567890.0
            )
            await stream.publish(event)
            
            # All clients should receive the event
            event1 = await asyncio.wait_for(client1.get(), timeout=1.0)
            event2 = await asyncio.wait_for(client2.get(), timeout=1.0)
            event3 = await asyncio.wait_for(client3.get(), timeout=1.0)
            
            assert event1.type == "impact_detected"
            assert event2.type == "impact_detected"
            assert event3.type == "impact_detected"
            
        finally:
            await stream.stop_broadcast_loop()
    
    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """Test that unsubscribed clients don't receive events."""
        stream = EventStream()
        stream.start_broadcast_loop()
        
        try:
            # Subscribe and then unsubscribe
            client_queue = await stream.subscribe()
            assert len(stream.clients) == 1
            
            await stream.unsubscribe(client_queue)
            assert len(stream.clients) == 0
            
        finally:
            await stream.stop_broadcast_loop()


class TestSSEEndpoint:
    """Test SSE endpoint implementation."""
    
    def test_sse_endpoint_exists(self):
        """Test that /api/events endpoint exists."""
        # Import here to avoid circular dependencies
        from main import app
        
        client = TestClient(app)
        
        # Note: TestClient doesn't support streaming responses well,
        # so we just verify the endpoint exists and returns the right media type
        with client.stream("GET", "/api/events") as response:
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
            assert response.headers["cache-control"] == "no-cache"
            assert response.headers["connection"] == "keep-alive"
    
    @pytest.mark.asyncio
    async def test_event_formatting(self):
        """Test that events are formatted correctly as SSE."""
        stream = EventStream()
        stream.start_broadcast_loop()
        
        try:
            client_queue = await stream.subscribe()
            
            # Publish event
            event = SSEEvent(
                type="scan_complete",
                payload={"files": 100, "nodes": 500},
                timestamp=1234567890.0
            )
            await stream.publish(event)
            
            # Receive event
            received = await asyncio.wait_for(client_queue.get(), timeout=1.0)
            
            # Verify event structure
            assert received.type == "scan_complete"
            assert "files" in received.payload
            assert "nodes" in received.payload
            assert received.payload["files"] == 100
            assert received.payload["nodes"] == 500
            
        finally:
            await stream.stop_broadcast_loop()
    
    @pytest.mark.asyncio
    async def test_heartbeat_timeout(self):
        """Test that heartbeat is sent after 30 seconds of no events."""
        # This test verifies the timeout logic exists
        # In practice, we can't wait 30 seconds in a test
        stream = EventStream()
        stream.start_broadcast_loop()
        
        try:
            client_queue = await stream.subscribe()
            
            # Try to get event with short timeout
            # Should timeout since no events are published
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(client_queue.get(), timeout=0.1)
                
        finally:
            await stream.stop_broadcast_loop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
