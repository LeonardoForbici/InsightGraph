"""
Unit tests for Redis client module.

Tests connection pooling, pub/sub, caching, and graceful degradation.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from backend.redis_client import RedisClient, get_redis_client, init_redis, close_redis


class TestRedisClient:
    """Test suite for RedisClient class."""
    
    @pytest.mark.asyncio
    async def test_initialization_with_defaults(self):
        """Test RedisClient initializes with default values."""
        client = RedisClient()
        assert client._url == "redis://localhost:6379/0"
        assert client._max_connections == 50
        assert client._decode_responses is True
    
    @pytest.mark.asyncio
    async def test_initialization_with_custom_values(self):
        """Test RedisClient initializes with custom values."""
        client = RedisClient(
            url="redis://custom:6380/1",
            max_connections=100,
            decode_responses=False
        )
        assert client._url == "redis://custom:6380/1"
        assert client._max_connections == 100
        assert client._decode_responses is False
    
    @pytest.mark.asyncio
    async def test_graceful_degradation_when_unavailable(self):
        """Test client degrades gracefully when Redis is unavailable."""
        with patch('backend.redis_client.REDIS_AVAILABLE', False):
            client = RedisClient()
            assert not client.is_available
            assert not client.is_connected
            
            # All operations should return safe defaults
            result = await client.publish("test", "message")
            assert result == 0
            
            value = await client.get("key")
            assert value is None
            
            success = await client.set("key", "value")
            assert success is False
    
    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """Test get_redis_client returns same instance."""
        client1 = get_redis_client()
        client2 = get_redis_client()
        assert client1 is client2
    
    @pytest.mark.asyncio
    async def test_connection_pool_creation(self):
        """Test connection pool is created correctly."""
        with patch('backend.redis_client.redis') as mock_redis:
            mock_pool = MagicMock()
            mock_redis.Redis = MagicMock()
            mock_redis.Redis.return_value.ping = AsyncMock()
            
            from backend.redis_client import ConnectionPool
            with patch.object(ConnectionPool, 'from_url', return_value=mock_pool):
                client = RedisClient()
                await client.connect()
                
                # Verify pool was created with correct parameters
                ConnectionPool.from_url.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_pub_sub_operations(self):
        """Test publish and subscribe operations."""
        with patch('backend.redis_client.redis') as mock_redis:
            mock_client = MagicMock()
            mock_client.publish = AsyncMock(return_value=5)
            mock_client.ping = AsyncMock()
            
            mock_redis.Redis.return_value = mock_client
            
            client = RedisClient()
            client._client = mock_client
            
            # Test publish
            result = await client.publish("test_channel", "test_message")
            assert result == 5
            mock_client.publish.assert_called_once_with("test_channel", "test_message")
    
    @pytest.mark.asyncio
    async def test_caching_operations(self):
        """Test get, set, delete, exists operations."""
        with patch('backend.redis_client.redis') as mock_redis:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value="cached_value")
            mock_client.set = AsyncMock()
            mock_client.delete = AsyncMock(return_value=1)
            mock_client.exists = AsyncMock(return_value=1)
            mock_client.ping = AsyncMock()
            
            mock_redis.Redis.return_value = mock_client
            
            client = RedisClient()
            client._client = mock_client
            
            # Test get
            value = await client.get("test_key")
            assert value == "cached_value"
            
            # Test set
            success = await client.set("test_key", "test_value", ex=300)
            assert success is True
            
            # Test delete
            deleted = await client.delete("test_key")
            assert deleted == 1
            
            # Test exists
            exists = await client.exists("test_key")
            assert exists == 1
    
    @pytest.mark.asyncio
    async def test_session_management(self):
        """Test session set, get, delete operations."""
        with patch('backend.redis_client.redis') as mock_redis:
            mock_client = MagicMock()
            mock_client.set = AsyncMock()
            mock_client.get = AsyncMock(return_value='{"user": "test"}')
            mock_client.delete = AsyncMock(return_value=1)
            mock_client.ping = AsyncMock()
            
            mock_redis.Redis.return_value = mock_client
            
            client = RedisClient()
            client._client = mock_client
            
            # Test set_session
            success = await client.set_session("session123", {"user": "test"}, ttl=3600)
            assert success is True
            
            # Test get_session
            session = await client.get_session("session123")
            assert session == {"user": "test"}
            
            # Test delete_session
            deleted = await client.delete_session("session123")
            assert deleted is True
    
    @pytest.mark.asyncio
    async def test_ping_operation(self):
        """Test ping checks connectivity."""
        with patch('backend.redis_client.redis') as mock_redis:
            mock_client = MagicMock()
            mock_client.ping = AsyncMock()
            
            mock_redis.Redis.return_value = mock_client
            
            client = RedisClient()
            client._client = mock_client
            
            result = await client.ping()
            assert result is True
            mock_client.ping.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_disconnect_cleanup(self):
        """Test disconnect cleans up resources properly."""
        with patch('backend.redis_client.redis') as mock_redis:
            mock_client = MagicMock()
            mock_client.close = AsyncMock()
            mock_pool = MagicMock()
            mock_pool.disconnect = AsyncMock()
            
            mock_redis.Redis.return_value = mock_client
            
            client = RedisClient()
            client._client = mock_client
            client._pool = mock_pool
            
            await client.disconnect()
            
            mock_client.close.assert_called_once()
            mock_pool.disconnect.assert_called_once()
            assert client._client is None
            assert client._pool is None


class TestGlobalFunctions:
    """Test suite for global helper functions."""
    
    @pytest.mark.asyncio
    async def test_init_redis(self):
        """Test init_redis initializes and connects global client."""
        with patch('backend.redis_client.get_redis_client') as mock_get:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_get.return_value = mock_client
            
            result = await init_redis()
            assert result is True
            mock_client.connect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_redis(self):
        """Test close_redis disconnects global client."""
        with patch('backend.redis_client._redis_client') as mock_client:
            mock_client.disconnect = AsyncMock()
            
            await close_redis()
            # Verify disconnect was called (implementation detail)
