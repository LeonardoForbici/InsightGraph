"""
Parallel Impact Engine for concurrent impact calculations.

Uses ThreadPoolExecutor to calculate impact for multiple nodes
concurrently, improving throughput for batch operations.

Requirements:
    - 14.5: Parallel impact calculation
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ImpactResult:
    """Result of impact calculation for a single node."""
    node_key: str
    affected_nodes: List[str]
    depth: int
    success: bool
    error: str = ""


class ParallelImpactEngine:
    """
    Engine for parallel impact calculations.
    
    Calculates impact for multiple nodes concurrently using
    a thread pool to improve throughput.
    """
    
    def __init__(self, impact_engine, max_workers: int = 4):
        """
        Initialize ParallelImpactEngine.
        
        Args:
            impact_engine: ImpactEngine instance for calculations
            max_workers: Maximum number of concurrent workers (default: 4)
        """
        self.impact_engine = impact_engine
        self.max_workers = max_workers
    
    def calculate_batch(
        self,
        node_keys: List[str],
        max_depth: int = 5
    ) -> List[ImpactResult]:
        """
        Calculate impact for multiple nodes in parallel.
        
        Args:
            node_keys: List of node keys to analyze
            max_depth: Maximum traversal depth
        
        Returns:
            List of impact results
        """
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_key = {
                executor.submit(
                    self._calculate_single,
                    node_key,
                    max_depth
                ): node_key
                for node_key in node_keys
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_key):
                node_key = future_to_key[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Impact calculation failed for {node_key}: {e}")
                    results.append(ImpactResult(
                        node_key=node_key,
                        affected_nodes=[],
                        depth=0,
                        success=False,
                        error=str(e)
                    ))
        
        return results
    
    def _calculate_single(
        self,
        node_key: str,
        max_depth: int
    ) -> ImpactResult:
        """
        Calculate impact for a single node.
        
        Args:
            node_key: Node to analyze
            max_depth: Maximum traversal depth
        
        Returns:
            Impact result
        """
        try:
            # Use the existing impact engine
            affected = self.impact_engine.calculate_impact(
                node_key=node_key,
                max_depth=max_depth
            )
            
            return ImpactResult(
                node_key=node_key,
                affected_nodes=affected.get('affected_nodes', []),
                depth=affected.get('max_depth', 0),
                success=True
            )
        except Exception as e:
            logger.error(f"Impact calculation error for {node_key}: {e}")
            return ImpactResult(
                node_key=node_key,
                affected_nodes=[],
                depth=0,
                success=False,
                error=str(e)
            )
    
    def calculate_batch_with_progress(
        self,
        node_keys: List[str],
        max_depth: int = 5,
        progress_callback=None
    ) -> List[ImpactResult]:
        """
        Calculate impact for multiple nodes with progress reporting.
        
        Args:
            node_keys: List of node keys to analyze
            max_depth: Maximum traversal depth
            progress_callback: Optional callback(completed, total)
        
        Returns:
            List of impact results
        """
        results = []
        total = len(node_keys)
        completed = 0
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_key = {
                executor.submit(
                    self._calculate_single,
                    node_key,
                    max_depth
                ): node_key
                for node_key in node_keys
            }
            
            # Collect results with progress
            for future in as_completed(future_to_key):
                node_key = future_to_key[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Impact calculation failed for {node_key}: {e}")
                    results.append(ImpactResult(
                        node_key=node_key,
                        affected_nodes=[],
                        depth=0,
                        success=False,
                        error=str(e)
                    ))
                
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about parallel execution.
        
        Returns:
            Dictionary with stats
        """
        return {
            "max_workers": self.max_workers
        }
