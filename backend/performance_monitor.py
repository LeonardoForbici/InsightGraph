"""
Performance Monitor for tracking operation metrics.

Records metrics for all operations including duration, metadata,
and calculates statistics (avg, min, max, p95).

Requirements:
    - 14.7: Performance monitoring and metrics
"""

import time
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from functools import wraps

logger = logging.getLogger(__name__)


@dataclass
class OperationMetric:
    """Metric for a single operation."""
    operation: str
    duration_ms: float
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    success: bool = True


@dataclass
class OperationStats:
    """Statistics for an operation type."""
    operation: str
    count: int
    avg_duration_ms: float
    min_duration_ms: float
    max_duration_ms: float
    p95_duration_ms: float
    success_rate: float


class PerformanceMonitor:
    """
    Monitor for tracking operation performance.
    
    Records metrics for all operations and provides statistics
    for performance analysis and optimization.
    """
    
    def __init__(self, slow_threshold_ms: float = 1000.0):
        """
        Initialize PerformanceMonitor.
        
        Args:
            slow_threshold_ms: Threshold for logging slow operations (default: 1000ms)
        """
        self.slow_threshold_ms = slow_threshold_ms
        self.metrics: Dict[str, List[OperationMetric]] = defaultdict(list)
        self.max_metrics_per_operation = 1000  # Limit memory usage
    
    def record(
        self,
        operation: str,
        duration_ms: float,
        metadata: Dict[str, Any] = None,
        success: bool = True
    ):
        """
        Record a metric for an operation.
        
        Args:
            operation: Operation name
            duration_ms: Duration in milliseconds
            metadata: Optional metadata dictionary
            success: Whether operation succeeded
        """
        metric = OperationMetric(
            operation=operation,
            duration_ms=duration_ms,
            timestamp=time.time(),
            metadata=metadata or {},
            success=success
        )
        
        # Add to metrics list
        self.metrics[operation].append(metric)
        
        # Limit metrics per operation to prevent memory issues
        if len(self.metrics[operation]) > self.max_metrics_per_operation:
            self.metrics[operation].pop(0)
        
        # Log slow operations
        if duration_ms > self.slow_threshold_ms:
            logger.warning(
                f"Slow operation detected: {operation} took {duration_ms:.2f}ms "
                f"(threshold: {self.slow_threshold_ms}ms)"
            )
    
    def get_stats(self, operation: str) -> Optional[OperationStats]:
        """
        Get statistics for an operation.
        
        Args:
            operation: Operation name
        
        Returns:
            OperationStats or None if no metrics
        """
        if operation not in self.metrics or not self.metrics[operation]:
            return None
        
        metrics = self.metrics[operation]
        durations = [m.duration_ms for m in metrics]
        successes = [m.success for m in metrics]
        
        # Calculate statistics
        count = len(durations)
        avg = sum(durations) / count
        min_dur = min(durations)
        max_dur = max(durations)
        
        # Calculate p95
        sorted_durations = sorted(durations)
        p95_index = int(count * 0.95)
        p95 = sorted_durations[p95_index] if p95_index < count else max_dur
        
        # Calculate success rate
        success_rate = sum(successes) / count * 100
        
        return OperationStats(
            operation=operation,
            count=count,
            avg_duration_ms=round(avg, 2),
            min_duration_ms=round(min_dur, 2),
            max_duration_ms=round(max_dur, 2),
            p95_duration_ms=round(p95, 2),
            success_rate=round(success_rate, 2)
        )
    
    def get_all_stats(self) -> List[OperationStats]:
        """
        Get statistics for all operations.
        
        Returns:
            List of OperationStats
        """
        stats = []
        for operation in self.metrics.keys():
            op_stats = self.get_stats(operation)
            if op_stats:
                stats.append(op_stats)
        
        # Sort by average duration (slowest first)
        stats.sort(key=lambda s: s.avg_duration_ms, reverse=True)
        
        return stats
    
    def get_slow_operations(self, threshold_ms: float = None) -> List[OperationMetric]:
        """
        Get all operations that exceeded the threshold.
        
        Args:
            threshold_ms: Custom threshold (default: use instance threshold)
        
        Returns:
            List of slow operation metrics
        """
        threshold = threshold_ms or self.slow_threshold_ms
        slow_ops = []
        
        for metrics_list in self.metrics.values():
            for metric in metrics_list:
                if metric.duration_ms > threshold:
                    slow_ops.append(metric)
        
        # Sort by duration (slowest first)
        slow_ops.sort(key=lambda m: m.duration_ms, reverse=True)
        
        return slow_ops
    
    def clear(self, operation: str = None):
        """
        Clear metrics.
        
        Args:
            operation: Specific operation to clear (default: clear all)
        """
        if operation:
            if operation in self.metrics:
                self.metrics[operation].clear()
        else:
            self.metrics.clear()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Export all statistics as dictionary.
        
        Returns:
            Dictionary with all stats
        """
        return {
            "operations": [
                {
                    "operation": stats.operation,
                    "count": stats.count,
                    "avg_duration_ms": stats.avg_duration_ms,
                    "min_duration_ms": stats.min_duration_ms,
                    "max_duration_ms": stats.max_duration_ms,
                    "p95_duration_ms": stats.p95_duration_ms,
                    "success_rate": stats.success_rate
                }
                for stats in self.get_all_stats()
            ],
            "slow_threshold_ms": self.slow_threshold_ms,
            "total_operations": sum(len(m) for m in self.metrics.values())
        }


# Global performance monitor instance
_performance_monitor = PerformanceMonitor()


def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    return _performance_monitor


def monitor_performance(operation_name: str = None):
    """
    Decorator for monitoring function performance.
    
    Usage:
        @monitor_performance("my_operation")
        def my_function():
            pass
    
    Args:
        operation_name: Name for the operation (default: function name)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            start_time = time.monotonic()
            success = True
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                raise
            finally:
                duration_ms = (time.monotonic() - start_time) * 1000
                _performance_monitor.record(
                    operation=op_name,
                    duration_ms=duration_ms,
                    success=success
                )
        
        return wrapper
    return decorator


def monitor_async_performance(operation_name: str = None):
    """
    Decorator for monitoring async function performance.
    
    Usage:
        @monitor_async_performance("my_async_operation")
        async def my_async_function():
            pass
    
    Args:
        operation_name: Name for the operation (default: function name)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            start_time = time.monotonic()
            success = True
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                raise
            finally:
                duration_ms = (time.monotonic() - start_time) * 1000
                _performance_monitor.record(
                    operation=op_name,
                    duration_ms=duration_ms,
                    success=success
                )
        
        return wrapper
    return decorator
