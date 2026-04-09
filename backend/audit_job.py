"""
AuditJob — Proactive monitoring for architectural antipatterns and technical debt.

Detects new antipatterns by comparing current graph state with previous snapshots,
registers alerts in SQLite, and provides endpoints for alert management.
"""

import time
import uuid
import logging
from typing import Literal

from state_store import LocalStateStore

logger = logging.getLogger("insightgraph.audit")


class AuditJob:
    """
    Proactive audit job that monitors graph changes and detects new antipatterns.
    
    Integrates with:
    - TemporalAnalyzer for snapshot comparison
    - LocalStateStore for alert persistence
    - WatchService for incremental change detection
    """

    def __init__(self, state_store: LocalStateStore):
        self._store = state_store
        self._last_check_time: float = 0.0

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    async def check_for_new_antipatterns(
        self,
        current_antipatterns: dict,
        previous_snapshot_id: str | None = None,
    ) -> list[dict]:
        """
        Compare current antipatterns with previous snapshot to detect new issues.
        
        Args:
            current_antipatterns: Dict with antipattern data from current scan
            previous_snapshot_id: ID of previous snapshot to compare against
            
        Returns:
            List of newly created alert records
        """
        new_alerts = []
        
        try:
            # Get previous antipatterns from snapshot if available
            previous_antipatterns = self._get_previous_antipatterns(previous_snapshot_id)
            
            # Detect new antipatterns
            new_issues = self._detect_new_issues(current_antipatterns, previous_antipatterns)
            
            # Register alerts for new issues
            for issue in new_issues:
                alert = self._create_alert(
                    antipattern_type=issue["type"],
                    node_key=issue["node_key"],
                    severity=issue["severity"],
                )
                new_alerts.append(alert)
                
            if new_alerts:
                logger.info("Detected %d new antipatterns", len(new_alerts))
            
            self._last_check_time = time.time()
            
        except Exception as exc:
            logger.error("Failed to check for new antipatterns: %s", exc)
            
        return new_alerts

    def get_unresolved_alerts(
        self,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get all unresolved alerts, optionally filtered by severity.
        
        Args:
            severity: Filter by severity level (low, medium, high, critical)
            limit: Maximum number of alerts to return
            
        Returns:
            List of unresolved alert records ordered by severity descending
        """
        try:
            alerts = self._store.get_unresolved_alerts(severity=severity, limit=limit)
            return alerts
        except Exception as exc:
            logger.error("Failed to get unresolved alerts: %s", exc)
            return []

    def resolve_alert(self, alert_id: str, resolved_by: str) -> bool:
        """
        Mark an alert as resolved.
        
        Args:
            alert_id: ID of the alert to resolve
            resolved_by: Username or identifier of who resolved it
            
        Returns:
            True if alert was resolved, False otherwise
        """
        try:
            success = self._store.resolve_alert(alert_id, resolved_by)
            if success:
                logger.info("Alert %s resolved by %s", alert_id, resolved_by)
            return success
        except Exception as exc:
            logger.error("Failed to resolve alert %s: %s", alert_id, exc)
            return False

    def get_alert_count(self) -> int:
        """
        Get count of unresolved alerts.
        
        Returns:
            Number of unresolved alerts
        """
        try:
            return self._store.count_unresolved_alerts()
        except Exception as exc:
            logger.error("Failed to count unresolved alerts: %s", exc)
            return 0

    def is_technical_debt_critical(self, threshold: int = 20) -> bool:
        """
        Check if technical debt is at critical level.
        
        Args:
            threshold: Number of unresolved alerts that indicates critical debt
            
        Returns:
            True if unresolved alerts exceed threshold
        """
        count = self.get_alert_count()
        return count > threshold

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────

    def _get_previous_antipatterns(self, snapshot_id: str | None) -> dict:
        """Retrieve antipatterns from a previous snapshot."""
        if not snapshot_id:
            return {}
            
        try:
            snapshot = self._store.get_snapshot_by_id(snapshot_id)
            if snapshot:
                metrics = snapshot.get("metrics", {})
                return metrics.get("antipatterns", {})
        except Exception as exc:
            logger.warning("Failed to get previous antipatterns: %s", exc)
            
        return {}

    def _detect_new_issues(
        self,
        current: dict,
        previous: dict,
    ) -> list[dict]:
        """
        Compare current and previous antipatterns to find new issues.
        
        Returns list of new issues with type, node_key, and severity.
        """
        new_issues = []
        
        # Extract antipattern lists from both snapshots
        current_god_classes = set(current.get("god_classes", []))
        previous_god_classes = set(previous.get("god_classes", []))
        
        current_circular = set(current.get("circular_dependencies", []))
        previous_circular = set(previous.get("circular_dependencies", []))
        
        current_dead_code = set(current.get("dead_code", []))
        previous_dead_code = set(previous.get("dead_code", []))
        
        # Detect new god classes
        for node_key in current_god_classes - previous_god_classes:
            new_issues.append({
                "type": "god_class",
                "node_key": node_key,
                "severity": "high",
            })
        
        # Detect new circular dependencies
        for node_key in current_circular - previous_circular:
            new_issues.append({
                "type": "circular_dependency",
                "node_key": node_key,
                "severity": "medium",
            })
        
        # Detect new dead code
        for node_key in current_dead_code - previous_dead_code:
            new_issues.append({
                "type": "dead_code",
                "node_key": node_key,
                "severity": "low",
            })
        
        return new_issues

    def _create_alert(
        self,
        antipattern_type: str,
        node_key: str,
        severity: str,
    ) -> dict:
        """Create and persist a new alert record."""
        alert_id = str(uuid.uuid4())
        now = time.time()
        
        alert = {
            "id": alert_id,
            "antipattern_type": antipattern_type,
            "node_key": node_key,
            "severity": severity,
            "resolved": False,
            "resolved_by": None,
            "resolved_at": None,
            "created_at": now,
        }
        
        try:
            self._store.save_alert(alert)
        except Exception as exc:
            logger.error("Failed to save alert: %s", exc)
            
        return alert

    def _classify_severity(self, antipattern_type: str) -> Literal["low", "medium", "high", "critical"]:
        """
        Classify severity based on antipattern type.
        
        This is a simple heuristic that can be enhanced with more sophisticated logic.
        """
        severity_map = {
            "god_class": "high",
            "circular_dependency": "medium",
            "dead_code": "low",
            "high_complexity": "medium",
            "high_coupling": "high",
            "security_vulnerability": "critical",
        }
        return severity_map.get(antipattern_type, "medium")
