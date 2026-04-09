import React, { useState, useEffect } from 'react';
import { fetchGraphSnapshots } from '../api';
import type { GraphSnapshot } from '../api';
import { GraphDiffViewer } from './GraphDiffViewer';

interface CommitTimelineProps {
    onClose: () => void;
}

export const CommitTimeline: React.FC<CommitTimelineProps> = ({ onClose }) => {
    const [snapshots, setSnapshots] = useState<GraphSnapshot[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedDiff, setSelectedDiff] = useState<{ from: string; to: string } | null>(null);

    useEffect(() => {
        loadSnapshots();
    }, []);

    const loadSnapshots = async () => {
        try {
            setLoading(true);
            const res = await fetchGraphSnapshots(1, 50);
            setSnapshots(res.items);
        } catch (err) {
            console.error('Failed to load snapshots:', err);
        } finally {
            setLoading(false);
        }
    };

    const healthColor = (index: number): string => {
        if (index === 0) return '#999';
        const prev = snapshots[index - 1];
        const curr = snapshots[index];
        const edgeDelta = (curr.total_edges || 0) - (prev.total_edges || 0);
        const gcDelta = (curr.god_classes || 0) - (prev.god_classes || 0);
        const cdDelta = (curr.circular_deps || 0) - (prev.circular_deps || 0);

        if (edgeDelta > 10 || gcDelta > 0 || cdDelta > 0) return '#d32f2f';
        if (edgeDelta < -10 && gcDelta <= 0 && cdDelta <= 0) return '#4caf50';
        return '#fbc02d';
    };

    if (selectedDiff) {
        return (
            <GraphDiffViewer
                fromCommit={selectedDiff.from}
                toCommit={selectedDiff.to}
                onClose={() => setSelectedDiff(null)}
            />
        );
    }

    return (
        <div style={styles.overlay} onClick={onClose}>
            <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
                <div style={styles.header}>
                    <h2>🕐 Commit Timeline</h2>
                    <button onClick={onClose} style={styles.closeBtn}>✕</button>
                </div>

                <div style={styles.content}>
                    {loading ? (
                        <div style={styles.loading}>Loading snapshots...</div>
                    ) : snapshots.length === 0 ? (
                        <div style={styles.empty}>
                            No snapshots yet. Run a scan to start monitoring architecture changes.
                        </div>
                    ) : (
                        <div style={styles.timeline}>
                            {snapshots.map((snap, idx) => (
                                <div key={snap.id} style={styles.timelineItem}>
                                    <div
                                        style={{
                                            ...styles.timelineDot,
                                            backgroundColor: healthColor(idx),
                                        }}
                                    ></div>
                                    <div style={styles.itemContent}>
                                        <div style={styles.itemHash}>
                                            <code>{snap.commit_hash?.slice(0, 8) || '—'}</code>
                                            <span style={styles.branch}>{snap.branch || '?'}</span>
                                        </div>
                                        <div style={styles.itemAuthor}>{snap.author || 'unknown'}</div>
                                        <div style={styles.itemMsg}>{snap.commit_message || '(no message)'}</div>
                                        <div style={styles.itemMetrics}>
                                            nodes: {snap.total_nodes} · edges: {snap.total_edges} · god: {snap.god_classes} · circular: {snap.circular_deps}
                                        </div>
                                        {idx > 0 && (
                                            <button
                                                style={styles.diffBtn}
                                                onClick={() =>
                                                    setSelectedDiff({
                                                        from: snapshots[idx - 1].commit_hash || '',
                                                        to: snap.commit_hash || '',
                                                    })
                                                }
                                            >
                                                View Diff
                                            </button>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
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
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        width: '90%',
        maxWidth: '700px',
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
    timeline: {
        position: 'relative',
    },
    timelineItem: {
        display: 'flex',
        gap: '16px',
        marginBottom: '20px',
        paddingBottom: '20px',
        borderBottom: '1px solid #eee',
    },
    timelineDot: {
        width: '12px',
        height: '12px',
        borderRadius: '50%',
        marginTop: '4px',
        flexShrink: 0,
    },
    itemContent: {
        flex: 1,
    },
    itemHash: {
        fontFamily: 'monospace',
        fontSize: '13px',
        fontWeight: '600',
        marginBottom: '4px',
        display: 'flex',
        gap: '8px',
        alignItems: 'center',
    },
    branch: {
        fontFamily: 'inherit',
        fontSize: '11px',
        backgroundColor: '#e3f2fd',
        padding: '2px 6px',
        borderRadius: '3px',
        color: '#1976d2',
    },
    itemAuthor: {
        fontSize: '12px',
        color: '#666',
        marginBottom: '2px',
    },
    itemMsg: {
        fontSize: '13px',
        color: '#333',
        marginBottom: '6px',
    },
    itemMetrics: {
        fontSize: '11px',
        color: '#999',
        marginBottom: '8px',
    },
    diffBtn: {
        padding: '6px 12px',
        fontSize: '12px',
        backgroundColor: '#1976d2',
        color: '#fff',
        border: 'none',
        borderRadius: '4px',
        cursor: 'pointer',
    },
};
