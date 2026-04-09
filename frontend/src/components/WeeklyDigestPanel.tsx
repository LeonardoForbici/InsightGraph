import React, { useState, useEffect } from 'react';
import { fetchWeeklyDigests, generateWeeklyDigest } from '../api';
import type { WeeklyDigest } from '../api';

interface WeeklyDigestPanelProps {
    onClose: () => void;
}

export const WeeklyDigestPanel: React.FC<WeeklyDigestPanelProps> = ({ onClose }) => {
    const [digests, setDigests] = useState<WeeklyDigest[]>([]);
    const [loading, setLoading] = useState(false);
    const [generating, setGenerating] = useState(false);

    useEffect(() => {
        loadDigests();
    }, []);

    const loadDigests = async () => {
        try {
            setLoading(true);
            const res = await fetchWeeklyDigests(12);
            setDigests(res);
        } catch (err) {
            console.error('Failed to load digests:', err);
        } finally {
            setLoading(false);
        }
    };

    const handleGenerate = async () => {
        try {
            setGenerating(true);
            await generateWeeklyDigest(1);
            // Poll for new digest
            await new Promise((resolve) => setTimeout(resolve, 2000));
            await loadDigests();
        } catch (err) {
            console.error('Failed to generate digest:', err);
        } finally {
            setGenerating(false);
        }
    };

    const trendIcon = (trend?: string) => {
        switch (trend) {
            case 'improving':
                return '⬆️';
            case 'degrading':
                return '⬇️';
            default:
                return '➡️';
        }
    };

    return (
        <div style={styles.overlay} onClick={onClose}>
            <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
                <div style={styles.header}>
                    <h2>📋 Weekly Architecture Digest</h2>
                    <button onClick={onClose} style={styles.closeBtn}>✕</button>
                </div>

                <div style={styles.toolbar}>
                    <button
                        onClick={handleGenerate}
                        disabled={generating}
                        style={styles.generateBtn}
                    >
                        {generating ? 'Generating...' : '+ Generate New'}
                    </button>
                </div>

                <div style={styles.content}>
                    {loading ? (
                        <div style={styles.loading}>Loading digests...</div>
                    ) : digests.length === 0 ? (
                        <div style={styles.empty}>
                            No digests yet. Click "Generate New" to create one.
                        </div>
                    ) : (
                        digests.map((digest) => (
                            <div key={digest.id} style={styles.digestCard}>
                                <div style={styles.digestHeader}>
                                    <h4 style={styles.digestWeek}>
                                        {digest.week_start} — {digest.week_end}
                                    </h4>
                                    <span style={styles.digestTime}>
                                        {new Date(digest.generated_at! * 1000).toLocaleDateString()}
                                    </span>
                                </div>

                                {/* Metrics Summary */}
                                {digest.summary?.metrics && (
                                    <div style={styles.metrics}>
                                        {Object.entries(digest.summary.metrics).map(([key, val]: [string, any]) => (
                                            <div key={key} style={styles.metricRow}>
                                                <span>{key}:</span>
                                                <span style={styles.metricValue}>
                                                    {val.before} → {val.after}
                                                    <span style={styles.metricDelta}>
                                                        {val.delta_pct > 0 ? '+' : ''}{val.delta_pct.toFixed(1)}%
                                                    </span>
                                                    <span>{trendIcon(val.trend)}</span>
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Narrative */}
                                {digest.narrative && (
                                    <div style={styles.narrative}>
                                        <strong>Summary:</strong>
                                        <p>{digest.narrative}</p>
                                    </div>
                                )}

                                {/* Stats */}
                                {digest.summary && (
                                    <div style={styles.stats}>
                                        {digest.summary.scan_count && (
                                            <span>{digest.summary.scan_count} scans</span>
                                        )}
                                        {digest.summary.commit_count && (
                                            <>
                                                {' · '}
                                                <span>{digest.summary.commit_count} commits</span>
                                            </>
                                        )}
                                        {digest.summary.alert_count && (
                                            <>
                                                {' · '}
                                                <span>{digest.summary.alert_count} alerts</span>
                                            </>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))
                    )}
                </div>
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
        width: '90%',
        maxWidth: '650px',
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
    toolbar: {
        padding: '12px 20px',
        borderBottom: '1px solid #eee',
    },
    generateBtn: {
        padding: '8px 16px',
        backgroundColor: '#4caf50',
        color: '#fff',
        border: 'none',
        borderRadius: '4px',
        cursor: 'pointer',
        fontSize: '12px',
        fontWeight: '500',
    },
    content: {
        overflowY: 'auto',
        flex: 1,
        padding: '20px',
    },
    loading: {
        textAlign: 'center',
        color: '#999',
        padding: '40px',
    },
    empty: {
        textAlign: 'center',
        color: '#999',
        fontSize: '14px',
        padding: '40px',
    },
    digestCard: {
        border: '1px solid #ddd',
        borderRadius: '6px',
        padding: '16px',
        marginBottom: '16px',
    },
    digestHeader: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        marginBottom: '12px',
    },
    digestWeek: {
        margin: 0,
        fontSize: '14px',
        fontWeight: '600',
    },
    digestTime: {
        fontSize: '11px',
        color: '#999',
    },
    metrics: {
        backgroundColor: '#f9f9f9',
        padding: '12px',
        borderRadius: '4px',
        marginBottom: '12px',
    },
    metricRow: {
        display: 'flex',
        justifyContent: 'space-between',
        fontSize: '12px',
        marginBottom: '6px',
    },
    metricValue: {
        display: 'flex',
        gap: '8px',
        alignItems: 'center',
        fontFamily: 'monospace',
    },
    metricDelta: {
        fontSize: '11px',
        color: '#666',
    },
    narrative: {
        backgroundColor: '#f5f5f5',
        padding: '12px',
        borderRadius: '4px',
        fontSize: '13px',
        marginBottom: '12px',
        lineHeight: '1.5',
    },
    stats: {
        fontSize: '11px',
        color: '#999',
    },
};
