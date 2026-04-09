"""
Batch Query Executor for database query optimization.

Batches multiple queries into a single transaction to reduce
database round-trips and improve performance.

Requirements:
    - 14.5: Database query batching
"""

import logging
from typing import List, Any, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result of a single query in a batch."""
    query_id: int
    success: bool
    data: Any = None
    error: str = ""


class BatchQueryExecutor:
    """
    Executor for batching database queries.
    
    Collects multiple queries and executes them in a single
    transaction for improved performance.
    """
    
    def __init__(self, neo4j_service, batch_size: int = 10):
        """
        Initialize BatchQueryExecutor.
        
        Args:
            neo4j_service: Neo4j service instance
            batch_size: Execute batch when this many queries are queued
        """
        self.neo4j = neo4j_service
        self.batch_size = batch_size
        self.query_queue: List[tuple[int, str, dict]] = []
        self.next_query_id = 0
    
    def add_query(self, query: str, params: dict = None) -> int:
        """
        Add a query to the batch.
        
        Args:
            query: Cypher query string
            params: Query parameters
        
        Returns:
            Query ID for retrieving results
        """
        query_id = self.next_query_id
        self.next_query_id += 1
        
        self.query_queue.append((query_id, query, params or {}))
        
        return query_id
    
    def execute_batch(self) -> List[QueryResult]:
        """
        Execute all queued queries in a single transaction.
        
        Returns:
            List of query results in order
        """
        if not self.query_queue:
            return []
        
        if not self.neo4j.is_connected:
            logger.error("Neo4j not connected, cannot execute batch")
            return [
                QueryResult(
                    query_id=qid,
                    success=False,
                    error="Neo4j not connected"
                )
                for qid, _, _ in self.query_queue
            ]
        
        results = []
        
        try:
            # Execute all queries in a single transaction
            with self.neo4j.graph.begin() as tx:
                for query_id, query, params in self.query_queue:
                    try:
                        result = tx.run(query, **params)
                        data = result.data()
                        
                        results.append(QueryResult(
                            query_id=query_id,
                            success=True,
                            data=data
                        ))
                    except Exception as e:
                        logger.error(f"Query {query_id} failed: {e}")
                        results.append(QueryResult(
                            query_id=query_id,
                            success=False,
                            error=str(e)
                        ))
                
                # Commit transaction
                tx.commit()
                
        except Exception as e:
            logger.error(f"Batch execution failed: {e}")
            # Return error results for all queries
            results = [
                QueryResult(
                    query_id=qid,
                    success=False,
                    error=f"Batch failed: {str(e)}"
                )
                for qid, _, _ in self.query_queue
            ]
        finally:
            # Clear queue
            self.query_queue.clear()
        
        return results
    
    def should_execute(self) -> bool:
        """
        Check if batch should be executed.
        
        Returns:
            True if batch size reached
        """
        return len(self.query_queue) >= self.batch_size
    
    def get_queue_size(self) -> int:
        """Get number of queued queries."""
        return len(self.query_queue)
    
    def clear(self):
        """Clear all queued queries without executing."""
        self.query_queue.clear()


class AutoBatchQueryExecutor(BatchQueryExecutor):
    """
    Batch query executor with automatic execution.
    
    Automatically executes batch when size threshold is reached.
    """
    
    def add_query(self, query: str, params: dict = None) -> int:
        """
        Add query and auto-execute if batch size reached.
        
        Args:
            query: Cypher query string
            params: Query parameters
        
        Returns:
            Query ID
        """
        query_id = super().add_query(query, params)
        
        # Auto-execute if batch size reached
        if self.should_execute():
            self.execute_batch()
        
        return query_id
