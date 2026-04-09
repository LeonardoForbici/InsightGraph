import React, { useState, useEffect } from 'react';
import {
    fetchAlertHistory,
    fetchAlertRules,
    fetchPollerStatus,
    deleteAlertRule,
} from '../api';
import type {
    FiredAlert,
    AlertRule,
    PollerStatus,
} from '../api';
import { useRealtimeEvents } from '../hooks/useRealtimeEvents';
import '../styles/Modal.css';

interface LiveAlertFeedProps {
    onClose: () => void;
}

export const LiveAlertFeed: React.FC<LiveAlertFeedProps> = ({ onClose }) => {
    const [alerts, setAlerts] = useState<FiredAlert[]>([]);
    const [rules, setRules] = useState<AlertRule[]>([]);
    const [poller, setPoller] = useState<PollerStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [showRules, setShowRules] = useState(false);

    useRealtimeEvents({
        url: '/api/events',
        handlers: {
            audit_alert: (payload: any) => {
                const newAlert: FiredAlert = {
                    id: payload.alert_id || crypto.randomUUID(),
                    rule_id: payload.rule_id,
                    rule_name: payload.rule_name || 'Unknown',
                    severity: payload.severity || 'info',
                    message: payload.message || '',
                    metric: payload.metric,
                    delta: payload.delta,
                    commit_hash: payload.commit_hash,
                    branch: payload.branch,
                    fired_at: payload.fired_at || Date.now(),
                };
                setAlerts((prev) => [newAlert, ...prev]);
            },
        },
    });

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        try {
            setLoading(true);
            const [histRes, rulesRes, pollerRes] = await Promise.all([
                fetchAlertHistory(1, 50),
                fetchAlertRules(),
                fetchPollerStatus(),
            ]);
            setAlerts(histRes.items);
            setRules(rulesRes);
            setPoller(pollerRes);
        } catch (err) {
            console.error('Failed to load alert data:', err);
        } finally {
            setLoading(false);
        }
    };

    const severityColor = (sev: string) => {
        switch (sev) {
            case 'critical': return '#d32f2f';
            case 'high': return '#f57c00';
            case 'medium': return '#fbc02d';
            default: return '#1976d2';
        }
    };

    const timeAgo = (ts: number) => {
        const s = Math.floor((Date.now() - ts) / 1000);
        if (s < 60) return `${s}s ago`;
        if (s < 3600) return `${Math.floor(s / 60)}m ago`;
        if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
        return `${Math.floor(s / 86400)}d ago`;
    };

    const pollerTime = poller?.last_scan_at ? timeAgo(poller.last_scan_at * 1000) : 'never';

    return (
        <div style={styles.overlay} onClick={onClose}>
            <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
                <div style={styles.header}>
                    <h2>🔔 Live Alerts</h2>
                    <button onClick={onClose} style={styles.closeBtn}>✕</button>
                </div>

                {/* Poller Status */}
                {poller && (
                    <div style={styles.pollerBadge}>
                        <span style={styles.pollerDot}></span>
                        <strong>Monitoring:</strong> {poller.last_commit_short || '—'}
                        <br />
                        <small>Last scan: {pollerTime} · Interval: {poller.interval_seconds}s</small>
                    </div>
                )}

                {/* Tabs */}
                <div style={styles.tabs}>
                    <button
                        style={{
                            ...styles.tab,
                            borderBottom: !showRules ? '3px solid #1976d2' : '3px solid transparent',
                        }}
                        onClick={() => setShowRules(false)}
                    >
                        Alerts ({alerts.length})
                    </button>
                    <button
                        style={{
                            ...styles.tab,
                            borderBottom: showRules ? '3px solid #1976d2' : '3px solid transparent',
                        }}
                        onClick={() => setShowRules(true)}
                    >
                        Rules ({rules.length})
                    </button>
                </div>

                {/* Alerts List */}
                {!showRules && (
                    <div style={styles.alertsList}>
                        {loading ? (
                            <div style={styles.loading}>Loading...</div>
                        ) : alerts.length === 0 ? (
                            <div style={styles.empty}>No alerts yet. Keep monitoring!</div>
                        ) : (
                            alerts.map((alert) => (
                                <div key={alert.id} style={styles.alertCard}>
                                    <div style={{ ...styles.severityBadge, backgroundColor: severityColor(alert.severity) }}>
                                        {alert.severity.toUpperCase()[0]}
                                    </div>
                                    <div style={styles.alertContent}>
                                        <div style={styles.alertTitle}>
                                            {alert.rule_name}
                                            {alert.commit_hash && (
                                                <code style={styles.commitHash}>{alert.commit_hash.slice(0, 8)}</code>
                                            )}
                                        </div>
                                        <div style={styles.alertMsg}>{alert.message}</div>
                                        {alert.delta !== undefined && alert.metric && (
                                            <div style={styles.alertDelta}>
                                                {alert.metric}: {alert.delta > 0 ? '+' : ''}{alert.delta.toFixed(1)}
                                            </div>
                                        )}
                                        <div style={styles.alertTime}>{timeAgo(alert.fired_at * 1000)}</div>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                )}

                {/* Rules List */}
                {showRules && (
                    <div style={styles.rulesList}>
                        {rules.length === 0 ? (
                            <div style={styles.empty}>No rules configured.</div>
                        ) : (
                            rules.map((rule) => (
                                <div key={rule.id} style={styles.ruleCard}>
                                    <div style={styles.ruleName}>{rule.name}</div>
                                    <div style={styles.ruleDetails}>
                                        {rule.metric} {rule.condition} {rule.threshold} ({rule.severity})
                                    </div>
                                    <button
                                        style={styles.deleteBtn}
                                        onClick={() => {
                                            deleteAlertRule(rule.id);
                                            setRules((prev) => prev.filter((r) => r.id !== rule.id));
                                        }}
                                    >
                                        Remove
                                    </button>
                                </div>
                            ))
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

const styles: Record<string, React.CSSProperties> = {
    overlay: {
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 10000,
    },
    modal: {
        backgroundColor: '#fff',
        borderRadius: '8px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        width: '90%',
        maxWidth: '600px',
        maxHeight: '80vh',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
    },
    header: {
        padding: '20px',
        borderBottom: '1px solid #eee',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
    },
    closeBtn: {
        background: 'none',
        border: 'none',
        fontSize: '20px',
        cursor: 'pointer',
        color: '#666',
    },
    pollerBadge: {
        padding: '12px 20px',
        backgroundColor: '#e3f2fd',
        borderLeft: '4px solid #1976d2',
        fontSize: '12px',
        color: '#333',
    },
    pollerDot: {
        display: 'inline-block',
        width: '8px',
        height: '8px',
        borderRadius: '50%',
        backgroundColor: '#4caf50',
        marginRight: '6px',
    },
    tabs: {
        display: 'flex',
        borderBottom: '1px solid #eee',
    },
    tab: {
        flex: 1,
        padding: '12px',
        border: 'none',
        background: 'none',
        cursor: 'pointer',
        fontSize: '14px',
        fontWeight: '500',
    },
    alertsList: {
        overflowY: 'auto',
        flex: 1,
    },
    loading: {
        padding: '40px',
        textAlign: 'center',
        color: '#999',
    },
    empty: {
        padding: '40px',
        textAlign: 'center',
        color: '#999',
        fontSize: '14px',
    },
    alertCard: {
        padding: '16px 20px',
        borderBottom: '1px solid #eee',
        display: 'flex',
        gap: '12px',
        alignItems: 'flex-start',
    },
    severityBadge: {
        width: '32px',
        height: '32px',
        borderRadius: '50%',
        color: '#fff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontWeight: 'bold',
        fontSize: '12px',
        flexShrink: 0,
    },
    alertContent: {
        flex: 1,
    },
    alertTitle: {
        fontWeight: '600',
        fontSize: '14px',
        marginBottom: '4px',
        display: 'flex',
        gap: '8px',
        alignItems: 'center',
    },
    commitHash: {
        fontFamily: 'monospace',
        fontSize: '11px',
        backgroundColor: '#f5f5f5',
        padding: '2px 6px',
        borderRadius: '3px',
    },
    alertMsg: {
        fontSize: '13px',
        color: '#333',
        marginBottom: '4px',
    },
    alertDelta: {
        fontSize: '12px',
        color: '#666',
        marginBottom: '4px',
    },
    alertTime: {
        fontSize: '11px',
        color: '#999',
    },
    rulesList: {
        padding: '20px',
        overflowY: 'auto',
        flex: 1,
    },
    ruleCard: {
        padding: '12px',
        border: '1px solid #ddd',
        borderRadius: '4px',
        marginBottom: '8px',
    },
    ruleName: {
        fontWeight: '600',
        fontSize: '13px',
        marginBottom: '4px',
    },
    ruleDetails: {
        fontSize: '12px',
        color: '#666',
        marginBottom: '8px',
    },
    deleteBtn: {
        padding: '4px 8px',
        fontSize: '11px',
        backgroundColor: '#ffebee',
        border: '1px solid #ffcdd2',
        borderRadius: '3px',
        cursor: 'pointer',
        color: '#d32f2f',
    },
};
