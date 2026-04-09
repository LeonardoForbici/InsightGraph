"""
Neo4j Connection Pool for improved performance.

Maintains a pool of reusable connections to reduce connection
overhead and improve query throughput.

Requirements:
    - 14.5: Connection pooling for Neo4j
"""

import logging
from typing import Optional
from queue import Queue, Empty
from contextlib import contextmanager
from py2neo import Graph

logger = logging.getLogger(__name__)


class Neo4jConnectionPool:
    """
    Connection pool for Neo4j database.
    
    Maintains a pool of reusable connections to improve performance
    by avoiding connection overhead.
    """
    
    def __init__(
        self,
        uri: str,
        auth: tuple[str, str],
        pool_size: int = 5,
        timeout: float = 30.0
    ):
        """
        Initialize connection pool.
        
        Args:
            uri: Neo4j connection URI
            auth: Tuple of (username, password)
            pool_size: Number of connections in pool
            timeout: Connection timeout in seconds
        """
        self.uri = uri
        self.auth = auth
        self.pool_size = pool_size
        self.timeout = timeout
        
        self.pool: Queue[Graph] = Queue(maxsize=pool_size)
        self.active_connections = 0
        self._initialized = False
    
    def initialize(self):
        """
        Initialize the connection pool.
        
        Creates initial connections and adds them to the pool.
        """
        if self._initialized:
            logger.warning("Connection pool already initialized")
            return
        
        logger.info(f"Initializing Neo4j connection pool with {self.pool_size} connections")
        
        for i in range(self.pool_size):
            try:
                connection = self._create_connection()
                self.pool.put(connection)
                logger.debug(f"Created connection {i + 1}/{self.pool_size}")
            except Exception as e:
                logger.error(f"Failed to create connection {i + 1}: {e}")
        
        self._initialized = True
        logger.info(f"Connection pool initialized with {self.pool.qsize()} connections")
    
    def _create_connection(self) -> Graph:
        """
        Create a new Neo4j connection.
        
        Returns:
            Graph connection instance
        """
        try:
            graph = Graph(self.uri, auth=self.auth)
            # Test connection
            graph.run("RETURN 1").data()
            return graph
        except Exception as e:
            logger.error(f"Failed to create Neo4j connection: {e}")
            raise
    
    @contextmanager
    def acquire(self):
        """
        Acquire a connection from the pool.
        
        Usage:
            with pool.acquire() as conn:
                result = conn.run("MATCH (n) RETURN n LIMIT 10")
        
        Yields:
            Graph connection
        """
        connection = None
        
        try:
            # Try to get connection from pool
            try:
                connection = self.pool.get(timeout=self.timeout)
                self.active_connections += 1
            except Empty:
                logger.warning("Connection pool exhausted, creating new connection")
                connection = self._create_connection()
                self.active_connections += 1
            
            # Verify connection is still alive
            try:
                connection.run("RETURN 1").data()
            except Exception:
                logger.warning("Connection dead, creating new one")
                connection = self._create_connection()
            
            yield connection
            
        except Exception as e:
            logger.error(f"Error using connection: {e}")
            raise
        finally:
            # Return connection to pool
            if connection:
                try:
                    # Only return to pool if pool not full
                    if self.pool.qsize() < self.pool_size:
                        self.pool.put_nowait(connection)
                    self.active_connections -= 1
                except Exception as e:
                    logger.error(f"Failed to return connection to pool: {e}")
                    self.active_connections -= 1
    
    def get_stats(self) -> dict:
        """
        Get connection pool statistics.
        
        Returns:
            Dictionary with pool stats
        """
        return {
            "pool_size": self.pool_size,
            "available": self.pool.qsize(),
            "active": self.active_connections,
            "initialized": self._initialized
        }
    
    def close_all(self):
        """
        Close all connections in the pool.
        
        Should be called during application shutdown.
        """
        logger.info("Closing all connections in pool")
        
        closed = 0
        while not self.pool.empty():
            try:
                connection = self.pool.get_nowait()
                # py2neo Graph doesn't have explicit close, connections are managed automatically
                closed += 1
            except Empty:
                break
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
        
        logger.info(f"Closed {closed} connections")
        self._initialized = False
