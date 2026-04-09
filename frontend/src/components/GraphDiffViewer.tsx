import React, { useState, useEffect } from 'react';
import { fetchGraphDiff } from '../api';
import type { GraphDiffResult } from '../api';

interface GraphDiffViewerProps {
    fromCommit: string;
    toCommit: string;
    onClose: () => void;
}

export const GraphDiffViewer: React.FC<GraphDiffViewerProps> = ({ fromCommit, toCommit, onClose }) => {
    const [diff, setDiff] = useState<GraphDiffResult | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        loadDiff();
    }, [fromCommit, toCommit]);

    const loadDiff = async () => {
        try {
            setLoading(true);
            setError(null);
            const result = await fetchGraphDiff(fromCommit, toCommit);
            setDiff(result);
        } catch (err) {
            setError(String(err));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={styles.overlay} onClick={onClose}>
            <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
                <div style={styles.header}>
                    <h3 style={styles.title}>
                        {fromCommit.slice(0, 8)} → {toCommit.slice(0, 8)}
                    </h3>
                    <button onClick={onClose} style={styles.closeBtn}>✕</button>
                </div>

                <div style={styles.content}>
                    {loading && <div style={styles.loading}>Loading diff...</div>}
                    {error && <div style={styles.error}>Error: {error}</div>}
                    {diff && (
                        <>
                            {/* Summary */}
                            <div style={styles.summary}>
                                <span>+{diff.graph_diff.summary.added_count}</span>
                                <span> · </span>
                                <span style={{ color: '#d32f2f' }}>
                                    -{diff.graph_diff.summary.removed_count}
                                </span>
                                <span> · </span>
                                <span style={{ color: '#fbc02d' }}>
                                    ~{diff.graph_diff.summary.modified_count}
                                </span>
                                <span> · </span>
                                <span style={{ color: '#999' }}>
                                    {diff.graph_diff.summary.unchanged_count} unchanged
                                </span>
                            </div>

                            {/* Sections */}
                            {diff.graph_diff.added.length > 0 && (
                                <section style={styles.section}>
                                    <h4 style={styles.sectionTitle}>
                                        + Added ({diff.graph_diff.added.length})
                                    </h4>
                                    {diff.graph_diff.added.map((node) => (
                                        <div key={node.namespace_key} style={styles.node}>
                                            <strong>{node.name || node.namespace_key}</strong>
                                            <span style={styles.nodeType}>{node.type}</span>
                                            {node.file && <span style={styles.nodePath}>{node.file}</span>}
                                        </div>
                                    ))}
                                </section>
                            )}

                            {diff.graph_diff.removed.length > 0 && (
                                <section style={styles.section}>
                                    <h4 style={{ ...styles.sectionTitle, color: '#d32f2f' }}>
                                        - Removed ({diff.graph_diff.removed.length})
                                    </h4>
                                    {diff.graph_diff.removed.map((node) => (
                                        <div key={node.namespace_key} style={styles.node}>
                                            <strong>{node.name || node.namespace_key}</strong>
                                            <span style={styles.nodeType}>{node.type}</span>
                                        </div>
                                    ))}
                                </section>
                            )}

                            {diff.graph_diff.modified.length > 0 && (
                                <section style={styles.section}>
                                    <h4 style={{ ...styles.sectionTitle, color: '#fbc02d' }}>
                                        ~ Modified ({diff.graph_diff.modified.length})
                                    </h4>
                                    {diff.graph_diff.modified.map((node) => (
                                        <div key={node.namespace_key} style={styles.node}>
                                            <strong>{node.name || node.namespace_key}</strong>
                                            {Object.entries(node.changes).map(([field, change]: [string, any]) => (
                                                <div key={field} style={styles.change}>
                                                    {field}: {change.before} → {change.after}
                                                </div>
                                            ))}
                                        </div>
                                    ))}
                                </section>
                            )}
                        </>
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
        zIndex: 10001,
    },
    modal: {
        backgroundColor: '#fff',
        borderRadius: '8px',
        width: '90%',
        maxWidth: '800px',
        maxHeight: '80vh',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
    },
    header: {
        padding: '16px 20px',
        borderBottom: '1px solid #eee',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
    },
    title: {
        margin: 0,
        fontSize: '14px',
        fontFamily: 'monospace',
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
    error: {
        padding: '12px',
        backgroundColor: '#ffebee',
        color: '#d32f2f',
        borderRadius: '4px',
        fontSize: '12px',
    },
    summary: {
        padding: '12px',
        backgroundColor: '#f5f5f5',
        borderRadius: '4px',
        fontSize: '13px',
        marginBottom: '16px',
        fontWeight: '500',
    },
    section: {
        marginBottom: '20px',
    },
    sectionTitle: {
        fontSize: '13px',
        fontWeight: '600',
        margin: '0 0 8px 0',
        color: '#333',
    },
    node: {
        padding: '8px 12px',
        borderLeft: '3px solid #e0e0e0',
        marginBottom: '4px',
        fontSize: '12px',
    },
    nodeType: {
        marginLeft: '8px',
        backgroundColor: '#f5f5f5',
        padding: '2px 6px',
        borderRadius: '3px',
        fontSize: '11px',
        color: '#666',
    },
    nodePath: {
        marginLeft: '8px',
        color: '#999',
        fontSize: '11px',
    },
    change: {
        fontSize: '11px',
        color: '#666',
        marginTop: '4px',
        marginLeft: '8px',
    },
};
