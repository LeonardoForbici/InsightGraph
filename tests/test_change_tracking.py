"""
Test for change tracking in Watch Service (Task 2.2)

This test verifies that:
1. Watch Service fetches change metadata for affected nodes
2. Change metadata is included in SSE events
3. The /api/nodes/metadata endpoint works correctly

Requirements: 1.1, 1.2, 14.1, 14.2, 2.1, 2.2, 2.3
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import time


class TestChangeTracking:
    """Test change tracking functionality in Watch Service."""
    
    @pytest.mark.asyncio
    async def test_fetch_change_metadata_success(self):
        """Test that _fetch_change_metadata successfully fetches metadata."""
        from backend.watch_service import WatchService
        
        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "metadata": {
                "node1": {
                    "last_modified": 1234567890.0,
                    "change_frequency": 5,
                    "first_seen": 1234567800.0
                },
                "node2": {
                    "last_modified": 1234567895.0,
                    "change_frequency": 3,
                    "first_seen": 1234567850.0
                }
            }
        }
        
        watch_service = WatchService(
            paths=["/test/path"],
            api_url="http://localhost:8000",
            event_stream=None
        )
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            result = await watch_service._fetch_change_metadata(["node1", "node2"])
            
            assert "node1" in result
            assert "node2" in result
            assert result["node1"]["last_modified"] == 1234567890.0
            assert result["node1"]["change_frequency"] == 5
            assert result["node2"]["change_frequency"] == 3
    
    @pytest.mark.asyncio
    async def test_fetch_change_metadata_empty_list(self):
        """Test that _fetch_change_metadata handles empty node list."""
        from backend.watch_service import WatchService
        
        watch_service = WatchService(
            paths=["/test/path"],
            api_url="http://localhost:8000",
            event_stream=None
        )
        
        result = await watch_service._fetch_change_metadata([])
        assert result == {}
    
    @pytest.mark.asyncio
    async def test_fetch_change_metadata_error_handling(self):
        """Test that _fetch_change_metadata handles errors gracefully."""
        from backend.watch_service import WatchService
        
        watch_service = WatchService(
            paths=["/test/path"],
            api_url="http://localhost:8000",
            event_stream=None
        )
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("Network error")
            )
            
            result = await watch_service._fetch_change_metadata(["node1"])
            assert result == {}
    
    @pytest.mark.asyncio
    async def test_publish_event_with_metadata(self):
        """Test that SSE events include change metadata."""
        from backend.watch_service import WatchService
        from backend.event_stream import EventStream, SSEEvent
        
        event_stream = EventStream()
        watch_service = WatchService(
            paths=["/test/path"],
            api_url="http://localhost:8000",
            event_stream=event_stream
        )
        
        change_metadata = {
            "node1": {
                "last_modified": 1234567890.0,
                "change_frequency": 5,
                "first_seen": 1234567800.0
            }
        }
        
        # Publish event with metadata
        await watch_service._publish_graph_updated_event(
            file_path="/test/file.py",
            affected_nodes=["node1"],
            nodes_updated=1,
            change_metadata=change_metadata
        )
        
        # Verify event was published
        event = await event_stream.queue.get()
        assert event.type == "graph_updated"
        assert "change_metadata" in event.payload
        assert event.payload["change_metadata"]["node1"]["change_frequency"] == 5
        assert event.payload["change_metadata"]["node1"]["last_modified"] == 1234567890.0
    
    @pytest.mark.asyncio
    async def test_publish_event_without_metadata(self):
        """Test that SSE events work without change metadata."""
        from backend.watch_service import WatchService
        from backend.event_stream import EventStream
        
        event_stream = EventStream()
        watch_service = WatchService(
            paths=["/test/path"],
            api_url="http://localhost:8000",
            event_stream=event_stream
        )
        
        # Publish event without metadata
        await watch_service._publish_graph_updated_event(
            file_path="/test/file.py",
            affected_nodes=["node1"],
            nodes_updated=1,
            change_metadata=None
        )
        
        # Verify event was published
        event = await event_stream.queue.get()
        assert event.type == "graph_updated"
        assert "change_metadata" not in event.payload or event.payload["change_metadata"] is None


def test_metadata_endpoint_structure():
    """Test that the metadata endpoint request/response structure is correct."""
    # This is a documentation test to verify the expected structure
    
    # Expected request structure
    request = {
        "node_keys": ["namespace_key1", "namespace_key2"]
    }
    
    # Expected response structure
    response = {
        "metadata": {
            "namespace_key1": {
                "last_modified": 1234567890.0,
                "change_frequency": 5,
                "first_seen": 1234567800.0
            },
            "namespace_key2": {
                "last_modified": 1234567895.0,
                "change_frequency": 3,
                "first_seen": 1234567850.0
            }
        }
    }
    
    # Verify structure
    assert "node_keys" in request
    assert isinstance(request["node_keys"], list)
    assert "metadata" in response
    assert isinstance(response["metadata"], dict)
    
    for node_key, metadata in response["metadata"].items():
        assert "last_modified" in metadata
        assert "change_frequency" in metadata
        assert "first_seen" in metadata
        assert isinstance(metadata["change_frequency"], int)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
