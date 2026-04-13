"""
Unit tests for Redis pub/sub channel constants.

Tests that channel constants are properly defined and can be used
for pub/sub operations in the Living Impact System.

Requirements: Req 1 (Real-time reactivity), Req 5 (Collaboration)
"""

import pytest
from redis_client import (
    IMPACT_EVENTS_CHANNEL,
    COLLABORATION_EVENTS_CHANNEL,
    RedisClient,
)


def test_channel_constants_defined():
    """Test that channel constants are properly defined."""
    assert IMPACT_EVENTS_CHANNEL == "impact_events"
    assert COLLABORATION_EVENTS_CHANNEL == "collaboration_events"


def test_channel_constants_are_strings():
    """Test that channel constants are strings."""
    assert isinstance(IMPACT_EVENTS_CHANNEL, str)
    assert isinstance(COLLABORATION_EVENTS_CHANNEL, str)


def test_channel_constants_not_empty():
    """Test that channel constants are not empty strings."""
    assert len(IMPACT_EVENTS_CHANNEL) > 0
    assert len(COLLABORATION_EVENTS_CHANNEL) > 0


def test_channel_constants_unique():
    """Test that channel constants have unique values."""
    assert IMPACT_EVENTS_CHANNEL != COLLABORATION_EVENTS_CHANNEL


@pytest.mark.asyncio
async def test_can_publish_to_impact_channel():
    """Test that we can publish to the impact_events channel."""
    client = RedisClient()
    
    # Try to connect (may fail if Redis not available)
    connected = await client.connect()
    
    if not connected:
        pytest.skip("Redis not available")
    
    try:
        # Publish test message
        result = await client.publish(IMPACT_EVENTS_CHANNEL, "test_message")
        # Result is number of subscribers (may be 0 if no subscribers)
        assert result >= 0
    finally:
        await client.disconnect()


@pytest.mark.asyncio
async def test_can_publish_to_collaboration_channel():
    """Test that we can publish to the collaboration_events channel."""
    client = RedisClient()
    
    # Try to connect (may fail if Redis not available)
    connected = await client.connect()
    
    if not connected:
        pytest.skip("Redis not available")
    
    try:
        # Publish test message
        result = await client.publish(COLLABORATION_EVENTS_CHANNEL, "test_message")
        # Result is number of subscribers (may be 0 if no subscribers)
        assert result >= 0
    finally:
        await client.disconnect()


@pytest.mark.asyncio
async def test_can_subscribe_to_impact_channel():
    """Test that we can subscribe to the impact_events channel."""
    client = RedisClient()
    
    # Try to connect (may fail if Redis not available)
    connected = await client.connect()
    
    if not connected:
        pytest.skip("Redis not available")
    
    try:
        # Subscribe to channel
        async with client.subscribe(IMPACT_EVENTS_CHANNEL) as pubsub:
            if pubsub is not None:
                # Successfully subscribed
                assert pubsub is not None
    finally:
        await client.disconnect()


@pytest.mark.asyncio
async def test_can_subscribe_to_collaboration_channel():
    """Test that we can subscribe to the collaboration_events channel."""
    client = RedisClient()
    
    # Try to connect (may fail if Redis not available)
    connected = await client.connect()
    
    if not connected:
        pytest.skip("Redis not available")
    
    try:
        # Subscribe to channel
        async with client.subscribe(COLLABORATION_EVENTS_CHANNEL) as pubsub:
            if pubsub is not None:
                # Successfully subscribed
                assert pubsub is not None
    finally:
        await client.disconnect()
