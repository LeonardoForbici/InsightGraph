"""
AlertEngine — Fase 3: Sistema de alertas proativos.

O sistema vivo não espera ser perguntado — ele avisa antes.

Funcionalidades:
  - Regras configuráveis por threshold (coupling_increase, new_hotspot, etc.)
  - Disparo automático após cada scan
  - Notificação via: SSE (UI em tempo real) + Slack webhook (opcional)
  - Histórico persistido no SQLite

Exemplo de alert gerado:
  "Esse PR aumenta acoplamento em 23%"
  "Esse módulo virou hotspot — 5 mudanças nos últimos 3 dias"
  "3 novos antipadrões detectados neste scan"
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Literal, Optional

import httpx

logger = logging.getLogger("insightgraph.alert_engine")

# ──────────────────────────────────────────────
# Alert data models
# ──────────────────────────────────────────────

AlertSeverity = Literal["critical", "high", "medium", "info"]
AlertChannel  = Literal["ui", "slack", "both"]

BUILTIN_RULES: list[dict] = [
    {
        "id": "coupling_spike",
        "name": "Coupling Spike",
        "description": "Fires when coupling increases by more than the threshold between two scans.",
        "metric": "total_edges",
        "condition": "increase_pct",
        "threshold": 15.0,
        "severity": "high",
        "channel": "both",
        "enabled": True,
        "message_template": "Coupling increased by {delta_pct:.1f}% ({before} → {after} edges). Architectural degradation detected.",
    },
    {
        "id": "god_class_new",
        "name": "New God Class",
        "description": "Fires when the number of god classes increases.",
        "metric": "god_classes",
        "condition": "increase_abs",
        "threshold": 1.0,
        "severity": "high",
        "channel": "both",
        "enabled": True,
        "message_template": "{delta:.0f} new god class(es) detected (total: {after}). Consider breaking them apart.",
    },
    {
        "id": "circular_dep_new",
        "name": "New Circular Dependency",
        "description": "Fires when the number of circular dependencies increases.",
        "metric": "circular_deps",
        "condition": "increase_abs",
        "threshold": 1.0,
        "severity": "critical",
        "channel": "both",
        "enabled": True,
        "message_template": "{delta:.0f} new circular dependency(ies) detected (total: {after}). This is a critical architectural risk.",
    },
    {
        "id": "dead_code_spike",
        "name": "Dead Code Increase",
        "description": "Fires when dead code count increases significantly.",
        "metric": "dead_code",
        "condition": "increase_abs",
        "threshold": 5.0,
        "severity": "medium",
        "channel": "ui",
        "enabled": True,
        "message_template": "{delta:.0f} new dead code elements detected (total: {after}).",
    },
    {
        "id": "node_count_drop",
        "name": "Large Node Removal",
        "description": "Fires when the total node count drops significantly (possible accidental deletion).",
        "metric": "total_nodes",
        "condition": "decrease_pct",
        "threshold": 10.0,
        "severity": "critical",
        "channel": "both",
        "enabled": True,
        "message_template": "Node count dropped by {delta_pct:.1f}% ({before} → {after}). Was this intentional?",
    },
]


@dataclass
class FiredAlert:
    id: str
    rule_id: str
    rule_name: str
    severity: AlertSeverity
    message: str
    metric: str
    value_before: float
    value_after: float
    delta: float
    snapshot_id: str
    commit_hash: Optional[str]
    branch: Optional[str]
    fired_at: float = field(default_factory=time.time)
    channels_notified: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────
# AlertEngine
# ──────────────────────────────────────────────

class AlertEngine:
    """
    Evaluates alert rules after each scan and dispatches notifications.

    Call evaluate_scan() after every scan completes, passing the new snapshot
    and the previous one. The engine compares metrics, fires matching rules,
    persists the alerts, and notifies via SSE and/or Slack.
    """

    def __init__(
        self,
        state_store,
        event_stream=None,
        slack_webhook_url: Optional[str] = None,
    ):
        self._store = state_store
        self._event_stream = event_stream
        self._slack_url = slack_webhook_url

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    async def evaluate_scan(
        self,
        current_snapshot: dict,
        previous_snapshot: Optional[dict],
    ) -> list[FiredAlert]:
        """
        Compare current_snapshot against previous_snapshot and fire matching rules.

        Args:
            current_snapshot: The snapshot just captured (with metrics + git info).
            previous_snapshot: The last snapshot before this one. Pass None for the
                               first scan — builtin rules won't fire without a baseline.

        Returns:
            List of FiredAlert objects for all rules that fired.
        """
        if not previous_snapshot:
            logger.info("AlertEngine: no previous snapshot — skipping comparison")
            return []

        rules = self._load_rules()
        fired: list[FiredAlert] = []

        for rule in rules:
            if not rule.get("enabled", True):
                continue
            alert = self._evaluate_rule(rule, current_snapshot, previous_snapshot)
            if alert:
                fired.append(alert)

        if fired:
            self._persist_alerts(fired)
            await self._dispatch_alerts(fired)
            logger.info(
                "AlertEngine fired %d alert(s) for snapshot %s",
                len(fired),
                current_snapshot.get("id"),
            )

        return fired

    def get_alert_history(self, page: int = 1, limit: int = 50) -> dict:
        """Return paginated alert history."""
        return self._store.get_alert_history(page=page, limit=limit)

    def get_active_rules(self) -> list[dict]:
        """Return all rules (builtin + custom)."""
        return self._load_rules()

    def upsert_rule(self, rule: dict) -> dict:
        """Create or update a custom alert rule."""
        rule.setdefault("id", str(uuid.uuid4()))
        rule.setdefault("enabled", True)
        rule.setdefault("channel", "ui")
        rule.setdefault("severity", "medium")
        self._store.upsert_alert_rule(rule)
        return rule

    def delete_rule(self, rule_id: str) -> bool:
        """Delete a custom rule. Builtin rules cannot be deleted — only disabled."""
        builtin_ids = {r["id"] for r in BUILTIN_RULES}
        if rule_id in builtin_ids:
            return False
        return self._store.delete_alert_rule(rule_id)

    # ──────────────────────────────────────────────
    # Rule evaluation
    # ──────────────────────────────────────────────

    async def emit_runtime_alert(
        self,
        *,
        rule_id: str,
        rule_name: str,
        severity: AlertSeverity,
        message: str,
        metric: str,
        value_before: float,
        value_after: float,
        snapshot_id: str = "",
        commit_hash: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> FiredAlert:
        """Emit an alert generated outside of snapshot comparison logic."""
        alert = FiredAlert(
            id=str(uuid.uuid4()),
            rule_id=rule_id,
            rule_name=rule_name,
            severity=severity,
            message=message,
            metric=metric,
            value_before=value_before,
            value_after=value_after,
            delta=value_after - value_before,
            snapshot_id=snapshot_id,
            commit_hash=commit_hash,
            branch=branch,
        )
        self._persist_alerts([alert])
        await self._dispatch_alerts([alert])
        return alert

    def _evaluate_rule(
        self, rule: dict, current: dict, previous: dict
    ) -> Optional[FiredAlert]:
        metric = rule.get("metric")
        condition = rule.get("condition")
        threshold = float(rule.get("threshold", 0))

        val_before = float(current.get(metric) or previous.get(metric) or 0)
        val_after  = float(current.get(metric) or 0)

        # Use previous for 'before' correctly
        val_before = float(previous.get(metric) or 0)

        delta = val_after - val_before
        delta_pct = (delta / val_before * 100) if val_before else 0.0

        triggered = False
        if condition == "increase_abs" and delta >= threshold:
            triggered = True
        elif condition == "decrease_abs" and delta <= -threshold:
            triggered = True
        elif condition == "increase_pct" and delta_pct >= threshold:
            triggered = True
        elif condition == "decrease_pct" and delta_pct <= -threshold:
            triggered = True
        elif condition == "equals" and val_after == threshold:
            triggered = True
        elif condition == "above" and val_after > threshold:
            triggered = True

        if not triggered:
            return None

        template = rule.get("message_template", "Alert: {metric} changed from {before} to {after}")
        try:
            message = template.format(
                metric=metric,
                before=val_before,
                after=val_after,
                delta=abs(delta),
                delta_pct=abs(delta_pct),
            )
        except Exception:
            message = f"{rule.get('name', metric)}: {val_before} → {val_after}"

        return FiredAlert(
            id=str(uuid.uuid4()),
            rule_id=rule["id"],
            rule_name=rule.get("name", rule["id"]),
            severity=rule.get("severity", "medium"),
            message=message,
            metric=metric,
            value_before=val_before,
            value_after=val_after,
            delta=delta,
            snapshot_id=current.get("id", ""),
            commit_hash=current.get("commit_hash"),
            branch=current.get("branch"),
        )

    # ──────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────

    def _load_rules(self) -> list[dict]:
        """Merge builtin rules with custom rules from the DB."""
        try:
            custom = self._store.list_alert_rules()
            custom_ids = {r["id"] for r in custom}
            # Builtin rules not overridden by custom
            merged = list(BUILTIN_RULES)
            for rule in custom:
                if rule["id"] not in {r["id"] for r in BUILTIN_RULES}:
                    merged.append(rule)
                else:
                    # Custom overrides builtin (by id)
                    for i, r in enumerate(merged):
                        if r["id"] == rule["id"]:
                            merged[i] = rule
                            break
            return merged
        except Exception as exc:
            logger.warning("Could not load custom rules: %s — using builtins", exc)
            return list(BUILTIN_RULES)

    def _persist_alerts(self, alerts: list[FiredAlert]) -> None:
        try:
            for alert in alerts:
                self._store.save_fired_alert(asdict(alert))
        except Exception as exc:
            logger.warning("Failed to persist alerts: %s", exc)

    # ──────────────────────────────────────────────
    # Notifications
    # ──────────────────────────────────────────────

    async def _dispatch_alerts(self, alerts: list[FiredAlert]) -> None:
        tasks = []
        for alert in alerts:
            channel = self._get_rule_channel(alert.rule_id)
            if channel in ("ui", "both") and self._event_stream:
                tasks.append(self._notify_ui(alert))
            if channel in ("slack", "both") and self._slack_url:
                tasks.append(self._notify_slack(alert))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.warning("Alert dispatch error: %s", r)

    async def _notify_ui(self, alert: FiredAlert) -> None:
        """Push alert to all connected frontend clients via SSE."""
        try:
            from event_stream import SSEEvent
            event = SSEEvent(
                type="audit_alert",
                payload={
                    "alert_id": alert.id,
                    "rule_id": alert.rule_id,
                    "severity": alert.severity,
                    "message": alert.message,
                    "metric": alert.metric,
                    "delta": alert.delta,
                    "commit_hash": alert.commit_hash,
                    "branch": alert.branch,
                    "fired_at": alert.fired_at,
                },
                timestamp=alert.fired_at,
            )
            await self._event_stream.publish(event)
            alert.channels_notified.append("ui")
        except Exception as exc:
            logger.warning("UI notification failed: %s", exc)

    async def _notify_slack(self, alert: FiredAlert) -> None:
        """Send alert to Slack via incoming webhook."""
        if not self._slack_url:
            return
        severity_emoji = {
            "critical": ":rotating_light:",
            "high": ":warning:",
            "medium": ":large_yellow_circle:",
            "info": ":information_source:",
        }.get(alert.severity, ":bell:")

        commit_info = ""
        if alert.commit_hash:
            branch = alert.branch or "unknown"
            commit_info = f"\n*Commit:* `{alert.commit_hash[:8]}` on `{branch}`"

        payload = {
            "text": f"{severity_emoji} *InsightGraph Alert — {alert.rule_name}*\n{alert.message}{commit_info}",
            "attachments": [
                {
                    "color": {"critical": "danger", "high": "warning", "medium": "#ffcc00", "info": "good"}.get(alert.severity, "#cccccc"),
                    "fields": [
                        {"title": "Severity", "value": alert.severity.upper(), "short": True},
                        {"title": "Metric", "value": alert.metric, "short": True},
                        {"title": "Before → After", "value": f"{alert.value_before:.0f} → {alert.value_after:.0f}", "short": True},
                        {"title": "Delta", "value": f"{alert.delta:+.0f}", "short": True},
                    ],
                }
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self._slack_url, json=payload)
                resp.raise_for_status()
            alert.channels_notified.append("slack")
            logger.info("Slack alert sent: %s", alert.rule_name)
        except Exception as exc:
            logger.warning("Slack notification failed: %s", exc)

    def _get_rule_channel(self, rule_id: str) -> str:
        for rule in self._load_rules():
            if rule["id"] == rule_id:
                return rule.get("channel", "ui")
        return "ui"
