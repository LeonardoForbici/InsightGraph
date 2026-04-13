"""
Tests for Redis client implementation.

Requirements: Req 1 (Real-time reactivity), Req 10 (Performance)
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))


class TestRedisClient:
    """Test RedisClient class functionality."""
    
    @pytest.mark.asyncio
    async def test_redis_client_initialization(self):
        """Test that RedisClient initializes correctly."""
        from redis_client import RedisClient
        
        client = RedisClient(
            url="redis://localhost:6379",
            max_connections=50,
            decode_responses=True,
        )
        
        assert client._url == "redis://localhost:6379"
        assert client._max_connections == 50
        assert client._decode_responses is True
        assert not client.is_connected
    
    @pytest.mark.asyncio
    async def test_redis_client_without_redis_package(self):
        """Test graceful degradation when redis package is not available."""
        with patch("redis_client.REDIS_AVAILABLE", False):
            from redis_client import RedisClient
            
            client = RedisClient()
            assert not client.is_connected
            
            # Operations should fail gracefully
            result = await client.publish("test", "message")
            assert result == 0
            
            value = await client.get("key")
            assert value is None
    
    @pytest.mark.asyncio
    async def test_connection_pool_creation(self):
        """Test that connection pool is created correctly."""
        from redis_client import RedisClient
        
        with patch("redis_client.REDIS_AVAILABLE", True):
            with patch("redis_client.redis") as mock_redis:
                # Mock ConnectionPool
                mock_pool = MagicMock()
                mock_redis.Redis = MagicMock()
                mock_redis_instance = AsyncMock()
                mock_redis_instance.ping = AsyncMock(return_value=True)
                mock_redis.Redis.return_value = mock_redis_instance
                
                mock_connection_pool = MagicMock()
                mock_connection_pool.from_url = MagicMock(return_value=mock_pool)
                
                with patch("redis_client.ConnectionPool", mock_connection_pool):
                    client = RedisClient(url="redis://localhost:6379", max_connections=50)
                    result = await client.connect()
                    
                    assert result is True
                    assert client.is_connected
    
    @pytest.mark.asyncio
    async def test_publish_message(self):
        """Test publishing messages to a channel."""
        from redis_client import RedisClient
        
        with patch("redis_client.REDIS_AVAILABLE", True):
            with patch("redis_client.redis") as mock_redis:
                # Setup mocks
                mock_redis_instance = AsyncMock()
                mock_redis_instance.ping = AsyncMock(return_value=True)
                mock_redis_instance.publish = AsyncMock(return_value=5)
                mock_redis.Redis.return_value = mock_redis_instance
                
                mock_pool = MagicMock()
                mock_connection_pool = MagicMock()
                mock_connection_pool.from_url = MagicMock(return_value=mock_pool)
                
                with patch("redis_client.ConnectionPool", mock_connection_pool):
                    client = RedisClient()
                    await client.connect()
                    
                    # Publish message
                    subscribers = await client.publish("test_channel", "test_message")
                    
                    assert subscribers == 5
                    mock_redis_instance.publish.assert_called_once_with("test_channel", "test_message")
    
    @pytest.mark.asyncio
    async def test_cache_operations(self):
        """Test cache get/set/delete operations."""
        from redis_client import RedisClient
        
        with patch("redis_client.REDIS_AVAILABLE", True):
            with patch("redis_client.redis") as mock_redis:
                # Setup mocks
                mock_redis_instance = AsyncMock()
                mock_redis_instance.ping = AsyncMock(return_value=True)
                mock_redis_instance.get = AsyncMock(return_value="cached_value")
                mock_redis_instance.set = AsyncMock(return_value=True)
                mock_redis_instance.delete = AsyncMock(return_value=1)
                mock_redis.Redis.return_value = mock_redis_instance
                
                mock_pool = MagicMock()
                mock_connection_pool = MagicMock()
                mock_connection_pool.from_url = MagicMock(return_value=mock_pool)
                
                with patch("redis_client.ConnectionPool", mock_connection_pool):
                    client = RedisClient()
                    await client.connect()
                    
                    # Test set
                    result = await client.set("test_key", "test_value", ex=300)
                    assert result is True
                    
                    # Test get
                    value = await client.get("test_key")
                    assert value == "cached_value"
                    
                    # Test delete
                    deleted = await client.delete("test_key")
                    assert deleted == 1
    
    @pytest.mark.asyncio
    async def test_session_management(self):
        """Test session storage and retrieval."""
        from redis_client import RedisClient
        
        with patch("redis_client.REDIS_AVAILABLE", True):
            with patch("redis_client.redis") as mock_redis:
                # Setup mocks
                session_data = {"user_id": "123", "name": "Test User"}
                mock_redis_instance = AsyncMock()
                mock_redis_instance.ping = AsyncMock(return_value=True)
                mock_redis_instance.set = AsyncMock(return_value=True)
                mock_redis_instance.get = AsyncMock(return_value=json.dumps(session_data))
                mock_redis_instance.delete = AsyncMock(return_value=1)
                mock_redis.Redis.return_value = mock_redis_instance
                
                mock_pool = MagicMock()
                mock_connection_pool = MagicMock()
                mock_connection_pool.from_url = MagicMock(return_value=mock_pool)
                
                with patch("redis_client.ConnectionPool", mock_connection_pool):
                    client = RedisClient()
                    await client.connect()
                    
                    # Test set session
                    result = await client.set_session("session_123", session_data, ttl=3600)
                    assert result is True
                    
                    # Test get session
                    retrieved = await client.get_session("session_123")
                    assert retrieved == session_data
                    
                    # Test delete session
                    deleted = await client.delete_session("session_123")
                    assert deleted is True
    
    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test that disconnect closes all connections."""
        from redis_client import RedisClient
        
        with patch("redis_client.REDIS_AVAILABLE", True):
            with patch("redis_client.redis") as mock_redis:
                # Setup mocks
                mock_redis_instance = AsyncMock()
                mock_redis_instance.ping = AsyncMock(return_value=True)
                mock_redis_instance.close = AsyncMock()
                mock_redis.Redis.return_value = mock_redis_instance
                
                mock_pool = MagicMock()
                mock_pool.disconnect = AsyncMock()
                mock_connection_pool = MagicMock()
                mock_connection_pool.from_url = MagicMock(return_value=mock_pool)
                
                with patch("redis_client.ConnectionPool", mock_connection_pool):
                    client = RedisClient()
                    await client.connect()
                    assert client.is_connected
                    
                    # Disconnect
                    await client.disconnect()
                    
                    assert not client.is_connected
                    mock_redis_instance.close.assert_called_once()
                    mock_pool.disconnect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_global_instance(self):
        """Test global instance factory functions."""
        from redis_client import get_redis_client, init_redis, close_redis
        
        with patch("redis_client.REDIS_AVAILABLE", True):
            with patch("redis_client.redis") as mock_redis:
                # Setup mocks
                mock_redis_instance = AsyncMock()
                mock_redis_instance.ping = AsyncMock(return_value=True)
                mock_redis_instance.close = AsyncMock()
                mock_redis.Redis.return_value = mock_redis_instance
                
                mock_pool = MagicMock()
                mock_pool.disconnect = AsyncMock()
                mock_connection_pool = MagicMock()
                mock_connection_pool.from_url = MagicMock(return_value=mock_pool)
                
                with patch("redis_client.ConnectionPool", mock_connection_pool):
                    # Get client
                    client1 = get_redis_client()
                    client2 = get_redis_client()
                    
                    # Should return same instance
                    assert client1 is client2
                    
                    # Initialize
                    result = await init_redis()
                    assert result is True
                    
                    # Close
                    await close_redis()
                    
                    # After close, should create new instance
                    client3 = get_redis_client()
                    assert client3 is not client1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
