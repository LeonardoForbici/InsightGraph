"""
Feature Flags for Code Intelligence OS.

Provides centralized feature flag management for gradual rollout
and easy rollback of new features.

Requirements:
    - All phases: Feature flag support
"""

import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class FeatureFlags:
    """
    Feature flag manager for Code Intelligence OS.
    
    Supports environment variable-based configuration with
    sensible defaults.
    """
    
    def __init__(self):
        """Initialize feature flags from environment variables."""
        # Backend feature flags
        self.ENABLE_SSE = self._get_bool_flag("ENABLE_SSE", True)
        self.ENABLE_GIT = self._get_bool_flag("ENABLE_GIT", True)
        self.ENABLE_AI_QUERY = self._get_bool_flag("ENABLE_AI_QUERY", True)
        self.ENABLE_TIMELINE = self._get_bool_flag("ENABLE_TIMELINE", True)
        self.ENABLE_INVESTIGATION = self._get_bool_flag("ENABLE_INVESTIGATION", True)
        self.ENABLE_PERFORMANCE_MONITORING = self._get_bool_flag("ENABLE_PERFORMANCE_MONITORING", True)
        self.ENABLE_IMPACT_CACHE = self._get_bool_flag("ENABLE_IMPACT_CACHE", True)
        self.ENABLE_CONNECTION_POOL = self._get_bool_flag("ENABLE_CONNECTION_POOL", False)
        
        # Frontend feature flags (for documentation)
        self.REACT_APP_ENABLE_SSE = self._get_bool_flag("REACT_APP_ENABLE_SSE", True)
        self.REACT_APP_ENABLE_TIMELINE = self._get_bool_flag("REACT_APP_ENABLE_TIMELINE", True)
        self.REACT_APP_ENABLE_AI_QUERY = self._get_bool_flag("REACT_APP_ENABLE_AI_QUERY", True)
        self.REACT_APP_ENABLE_INVESTIGATION = self._get_bool_flag("REACT_APP_ENABLE_INVESTIGATION", True)
        
        self._log_flags()
    
    def _get_bool_flag(self, name: str, default: bool) -> bool:
        """
        Get boolean flag from environment.
        
        Args:
            name: Environment variable name
            default: Default value if not set
        
        Returns:
            Boolean flag value
        """
        value = os.getenv(name)
        if value is None:
            return default
        return value.lower() in ("1", "true", "yes", "on")
    
    def _log_flags(self):
        """Log all feature flags for debugging."""
        logger.info("Feature Flags Configuration:")
        logger.info(f"  ENABLE_SSE: {self.ENABLE_SSE}")
        logger.info(f"  ENABLE_GIT: {self.ENABLE_GIT}")
        logger.info(f"  ENABLE_AI_QUERY: {self.ENABLE_AI_QUERY}")
        logger.info(f"  ENABLE_TIMELINE: {self.ENABLE_TIMELINE}")
        logger.info(f"  ENABLE_INVESTIGATION: {self.ENABLE_INVESTIGATION}")
        logger.info(f"  ENABLE_PERFORMANCE_MONITORING: {self.ENABLE_PERFORMANCE_MONITORING}")
        logger.info(f"  ENABLE_IMPACT_CACHE: {self.ENABLE_IMPACT_CACHE}")
        logger.info(f"  ENABLE_CONNECTION_POOL: {self.ENABLE_CONNECTION_POOL}")
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Export feature flags as dictionary.
        
        Returns:
            Dictionary with all flags
        """
        return {
            "backend": {
                "sse": self.ENABLE_SSE,
                "git": self.ENABLE_GIT,
                "ai_query": self.ENABLE_AI_QUERY,
                "timeline": self.ENABLE_TIMELINE,
                "investigation": self.ENABLE_INVESTIGATION,
                "performance_monitoring": self.ENABLE_PERFORMANCE_MONITORING,
                "impact_cache": self.ENABLE_IMPACT_CACHE,
                "connection_pool": self.ENABLE_CONNECTION_POOL
            },
            "frontend": {
                "sse": self.REACT_APP_ENABLE_SSE,
                "timeline": self.REACT_APP_ENABLE_TIMELINE,
                "ai_query": self.REACT_APP_ENABLE_AI_QUERY,
                "investigation": self.REACT_APP_ENABLE_INVESTIGATION
            }
        }


# Global feature flags instance
_feature_flags = FeatureFlags()


def get_feature_flags() -> FeatureFlags:
    """Get the global feature flags instance."""
    return _feature_flags
