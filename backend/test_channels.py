"""
Test suite for Redis pub/sub channels implementation.

Tests the channel constants, helper functions, and event serialization
for the Living Impact System's real-time event propagation.

Requirements: Req 1 (Real-time reactivity), Req 5 (Collaboration)
"""

import pytest
import asyncio
from datetime import datetime

from channels import (
    ChannelManager,
    CommitEvent,
    ImpactEvent,
    CursorEvent,
    SelectionEvent,
    AnnotationEvent,
    AffectedNode,
    serialize_event,
    deserialize_event,
    get_channel_manager,
)
from redis_client import (
    IMPACT_EVENTS_CHANNEL,
    COLLABORATION_EVENTS_CHANNEL,
    RedisClient,
)


class TestChannelConstants:
    """Test channel name constants."""
    
    def test_impact_events_channel_name(self):
        """Verify impact_events channel constant."""
        assert IMPACT_EVENTS_CHANNEL == "impact_events"
    
    def test_collaboration_events_channel_name(self):
        """Verify collaboration_events channel constant."""
        assert COLLABORATION_EVENTS_CHANNEL == "collaboration_events"


class TestEventSerialization:
    """Test event serialization and deserialization."""
    
    def test_serialize_commit_event(self):
        """Test CommitEvent serialization."""
        event = CommitEvent(
            commit_hash="abc123",
            author="test_user",
            timestamp=1234567890.0,
            changed_files=["file1.py", "file2.py"],
            affected_nodes=["node1", "node2"],
        )
        
        serialized = serialize_event(event)
        assert isinstance(serialized, str)
        assert "abc123" in serialized
        assert "test_user" in serialized
    
    def test_deserialize_commit_event(self):
        """Test CommitEvent deserialization."""
        event = CommitEvent(
            commit_hash="abc123",
            author="test_user",
            timestamp=1234567890.0,
            changed_files=["file1.py"],
            affected_nodes=["node1"],
        )
        
        serialized = serialize_event(event)
        deserialized = deserialize_event(serialized)
        
        assert isinstance(deserialized, CommitEvent)
        assert deserialized.commit_hash == "abc123"
        assert deserialized.author == "test_user"
        assert deserialized.changed_files == ["file1.py"]
    
    def test_serialize_impact_event(self):
        """Test ImpactEvent serialization."""
        event = ImpactEvent(
            origin_node="node1",
            affected_nodes=[
                AffectedNode(node_key="node2", distance=1, risk_score=0.5),
                AffectedNode(node_key="node3", distance=2, risk_score=0.3),
            ],
            timestamp=1234567890.0,
        )
        
        serialized = serialize_event(event)
        assert isinstance(serialized, str)
        assert "node1" in serialized
        assert "node2" in serialized
    
    def test_deserialize_impact_event(self):
        """Test ImpactEvent deserialization."""
        event = ImpactEvent(
            origin_node="node1",
            affected_nodes=[
                AffectedNode(node_key="node2", distance=1, risk_score=0.5),
            ],
            timestamp=1234567890.0,
        )
        
        serialized = serialize_event(event)
        deserialized = deserialize_event(serialized)
        
        assert isinstance(deserialized, ImpactEvent)
        assert deserialized.origin_node == "node1"
        assert len(deserialized.affected_nodes) == 1
        assert deserialized.affected_nodes[0].node_key == "node2"
    
    def test_serialize_cursor_event(self):
        """Test CursorEvent serialization."""
        event = CursorEvent(
            user_id="user1",
            session_id="session1",
            position={"x": 100.0, "y": 200.0, "z": 0.0},
            timestamp=1234567890.0,
        )
        
        serialized = serialize_event(event)
        assert isinstance(serialized, str)
        assert "user1" in serialized
        assert "session1" in serialized
    
    def test_deserialize_cursor_event(self):
        """Test CursorEvent deserialization."""
        event = CursorEvent(
            user_id="user1",
            session_id="session1",
            position={"x": 100.0, "y": 200.0},
            timestamp=1234567890.0,
        )
        
        serialized = serialize_event(event)
        deserialized = deserialize_event(serialized)
        
        assert isinstance(deserialized, CursorEvent)
        assert deserialized.user_id == "user1"
        assert deserialized.session_id == "session1"
        assert deserialized.position["x"] == 100.0


class TestChannelManager:
    """Test ChannelManager helper functions."""
    
    @pytest.fixture
    def channel_manager(self):
        """Create a ChannelManager instance for testing."""
        redis_client = RedisClient()
        return ChannelManager(redis_client)
    
    def test_channel_manager_initialization(self, channel_manager):
        """Test ChannelManager can be initialized."""
        assert channel_manager is not None
        assert channel_manager._redis is not None
    
    def test_get_channel_manager_singleton(self):
        """Test global ChannelManager instance."""
        manager1 = get_channel_manager()
        manager2 = get_channel_manager()
        
        assert manager1 is manager2  # Should be same instance
    
    @pytest.mark.asyncio
    async def test_publish_commit_event_without_redis(self, channel_manager):
        """Test publishing CommitEvent when Redis is unavailable."""
        event = CommitEvent(
            commit_hash="test123",
            author="test_user",
        )
        
        # Should not raise error even if Redis is unavailable
        result = await channel_manager.publish_commit_event(event)
        assert result == 0  # No subscribers when Redis unavailable
    
    @pytest.mark.asyncio
    async def test_publish_impact_event_without_redis(self, channel_manager):
        """Test publishing ImpactEvent when Redis is unavailable."""
        event = ImpactEvent(
            origin_node="node1",
            affected_nodes=[
                AffectedNode(node_key="node2", distance=1, risk_score=0.5),
            ],
        )
        
        # Should not raise error even if Redis is unavailable
        result = await channel_manager.publish_impact_event(event)
        assert result == 0  # No subscribers when Redis unavailable
    
    @pytest.mark.asyncio
    async def test_publish_cursor_event_without_redis(self, channel_manager):
        """Test publishing CursorEvent when Redis is unavailable."""
        event = CursorEvent(
            user_id="user1",
            session_id="session1",
            position={"x": 100.0, "y": 200.0},
        )
        
        # Should not raise error even if Redis is unavailable
        result = await channel_manager.publish_cursor_event(event)
        assert result == 0  # No subscribers when Redis unavailable
    
    @pytest.mark.asyncio
    async def test_publish_selection_event_without_redis(self, channel_manager):
        """Test publishing SelectionEvent when Redis is unavailable."""
        event = SelectionEvent(
            user_id="user1",
            session_id="session1",
            selected_nodes=["node1", "node2"],
        )
        
        # Should not raise error even if Redis is unavailable
        result = await channel_manager.publish_selection_event(event)
        assert result == 0  # No subscribers when Redis unavailable
    
    @pytest.mark.asyncio
    async def test_publish_annotation_event_without_redis(self, channel_manager):
        """Test publishing AnnotationEvent when Redis is unavailable."""
        event = AnnotationEvent(
            user_id="user1",
            session_id="session1",
            node_key="node1",
            text="Test annotation",
            annotation_id="ann1",
        )
        
        # Should not raise error even if Redis is unavailable
        result = await channel_manager.publish_annotation_event(event)
        assert result == 0  # No subscribers when Redis unavailable


class TestEventModels:
    """Test event model creation and defaults."""
    
    def test_commit_event_defaults(self):
        """Test CommitEvent with default values."""
        event = CommitEvent()
        
        assert event.type == "commit"
        assert event.commit_hash == ""
        assert event.author == ""
        assert isinstance(event.timestamp, float)
        assert event.changed_files == []
        assert event.affected_nodes == []
    
    def test_impact_event_defaults(self):
        """Test ImpactEvent with default values."""
        event = ImpactEvent()
        
        assert event.type == "impact"
        assert event.origin_node == ""
        assert event.affected_nodes == []
        assert isinstance(event.timestamp, float)
    
    def test_cursor_event_defaults(self):
        """Test CursorEvent with default values."""
        event = CursorEvent()
        
        assert event.type == "cursor"
        assert event.user_id == ""
        assert event.session_id == ""
        assert event.position == {}
        assert isinstance(event.timestamp, float)
    
    def test_affected_node_creation(self):
        """Test AffectedNode creation."""
        node = AffectedNode(
            node_key="test_node",
            distance=3,
            risk_score=0.75,
        )
        
        assert node.node_key == "test_node"
        assert node.distance == 3
        assert node.risk_score == 0.75


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
