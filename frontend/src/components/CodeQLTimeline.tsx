import { useState, useEffect } from 'react';
import { fetchCodeQLHistory, type CodeQLHistoryEntry } from '../api';

interface CodeQLTimelineProps {
    onClose: () => void;
}

const STATUS_COLORS: Record<string, string> = {
    completed: '#22c55e',
    failed: '#ef4444',
    running: '#f97316',
    pending: '#8b93b0',
    cancelled: '#a78bfa',
    queued: '#60a5fa',
};

export default function CodeQLTimeline({ onClose }: CodeQLTimelineProps) {
    const [history, setHistory] = useState<CodeQLHistoryEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [selectedEntry, setSelectedEntry] = useState<CodeQLHistoryEntry | null>(null);

    useEffect(() => {
        loadHistory();
    }, []);

    const loadHistory = async () => {
        try {
            setLoading(true);
            const data = await fetchCodeQLHistory();
            // Sort by started_at descending (most recent first)
            const sorted = data.sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
            setHistory(sorted);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load CodeQL history');
        } finally {
            setLoading(false);
        }
    };

    const formatDuration = (entry: CodeQLHistoryEntry) => {
        if (entry.duration_seconds) {
            const hours = Math.floor(entry.duration_seconds / 3600);
            const minutes = Math.floor((entry.duration_seconds % 3600) / 60);
            const seconds = entry.duration_seconds % 60;

            if (hours > 0) return `${hours}h ${minutes}m`;
            if (minutes > 0) return `${minutes}m ${seconds}s`;
            return `${seconds}s`;
        }
        return 'N/A';
    };

    const formatDate = (dateString: string) => {
        return new Date(dateString).toLocaleString();
    };

    const getDaysSinceLastAnalysis = () => {
        if (!history.length) return null;
        const lastAnalysis = Math.max(...history.map(h => new Date(h.started_at).getTime()));
        const days = Math.floor((Date.now() - lastAnalysis) / (1000 * 60 * 60 * 24));
        return days;
    };

    const getStatusBadge = (status: string) => {
        const color = STATUS_COLORS[status] || '#8b93b0';
        return (
            <span
                style={{
                    background: `${color}20`,
                    color,
                    padding: '2px 8px',
                    borderRadius: '12px',
                    fontSize: '11px',
                    fontWeight: '600',
                }}
            >
                {status}
            </span>
        );
    };

    if (loading) {
        return (
            <div className="modal-overlay">
                <div className="modal-panel" style={{ width: '800px', maxHeight: '600px' }}>
                    <div className="modal-header">
                        <h2>CodeQL Analysis Timeline</h2>
                        <button className="btn" onClick={onClose}>×</button>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '400px' }}>
                        <div className="loading-spinner"></div>
                        <span style={{ marginLeft: 16 }}>Carregando histórico...</span>
                    </div>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="modal-overlay">
                <div className="modal-panel" style={{ width: '800px' }}>
                    <div className="modal-header">
                        <h2>CodeQL Analysis Timeline</h2>
                        <button className="btn" onClick={onClose}>×</button>
                    </div>
                    <div className="alert alert-warning">{error}</div>
                </div>
            </div>
        );
    }

    const daysSince = getDaysSinceLastAnalysis();

    return (
        <div className="modal-overlay">
            <div className="modal-panel" style={{ width: '900px', maxHeight: '700px' }}>
                <div className="modal-header">
                    <div>
                        <h2>CodeQL Analysis Timeline</h2>
                        <p className="section-desc">Histórico de análises de segurança CodeQL.</p>
                        {daysSince !== null && (
                            <div style={{
                                marginTop: 8,
                                padding: '4px 12px',
                                background: daysSince > 7 ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)',
                                border: `1px solid ${daysSince > 7 ? '#ef4444' : '#22c55e'}`,
                                borderRadius: '6px',
                                display: 'inline-block',
                                fontSize: '12px',
                                color: daysSince > 7 ? '#ef4444' : '#22c55e',
                            }}>
                                Última análise há {daysSince} dia{daysSince !== 1 ? 's' : ''} atrás
                            </div>
                        )}
                    </div>
                    <button className="btn" onClick={onClose}>×</button>
                </div>

                <div className="timeline-container">
                    <div className="timeline">
                        {history.map((entry, index) => (
                            <div key={entry.job_id} className="timeline-item">
                                <div className="timeline-marker">
                                    <div
                                        className="timeline-dot"
                                        style={{
                                            background: STATUS_COLORS[entry.status] || '#8b93b0',
                                            border: entry.status === 'failed' ? '2px solid #ef4444' : 'none',
                                        }}
                                    />
                                    {index < history.length - 1 && <div className="timeline-line" />}
                                </div>

                                <div className="timeline-content">
                                    <div className="timeline-header">
                                        <div>
                                            <h4>{entry.suite || 'Análise CodeQL'}</h4>
                                            <div className="timeline-meta">
                                                {formatDate(entry.started_at)}
                                                {entry.completed_at && (
                                                    <span> • {formatDuration(entry)}</span>
                                                )}
                                                {!entry.completed_at && entry.status === 'running' && (
                                                    <span> • Em andamento</span>
                                                )}
                                            </div>
                                        </div>
                                        {getStatusBadge(entry.status)}
                                    </div>

                                    <div className="timeline-details">
                                        <div className="timeline-stats">
                                            {entry.results_summary && (
                                                <>
                                                    <span className="stat-item">
                                                        <span className="stat-label">Vulnerabilidades:</span>
                                                        <span className="stat-value">{entry.results_summary.total_issues || 0}</span>
                                                    </span>
                                                    {entry.results_summary.vulnerabilities_by_severity && (
                                                        <>
                                                            <span className="stat-item" style={{ color: '#ef4444' }}>
                                                                {entry.results_summary.vulnerabilities_by_severity.error || 0} erros
                                                            </span>
                                                            <span className="stat-item" style={{ color: '#f97316' }}>
                                                                {entry.results_summary.vulnerabilities_by_severity.warning || 0} avisos
                                                            </span>
                                                            <span className="stat-item" style={{ color: '#8b93b0' }}>
                                                                {entry.results_summary.vulnerabilities_by_severity.note || 0} notas
                                                            </span>
                                                        </>
                                                    )}
                                                </>
                                            )}
                                        </div>

                                        <button
                                            className="btn btn-ghost"
                                            onClick={() => setSelectedEntry(entry)}
                                            style={{ fontSize: '12px', padding: '4px 8px' }}
                                        >
                                            Ver detalhes
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}

                        {history.length === 0 && (
                            <div className="empty-state" style={{ gridColumn: '1 / -1' }}>
                                Nenhuma análise CodeQL encontrada.
                            </div>
                        )}
                    </div>
                </div>

                {selectedEntry && (
                    <div className="timeline-modal-overlay" onClick={() => setSelectedEntry(null)}>
                        <div className="timeline-modal" onClick={(e) => e.stopPropagation()}>
                            <div className="timeline-modal-header">
                                <h3>Detalhes da Análise</h3>
                                <button className="btn" onClick={() => setSelectedEntry(null)}>×</button>
                            </div>

                            <div className="timeline-modal-content">
                                <div className="detail-row">
                                    <span className="detail-label">Suite:</span>
                                    <span>{selectedEntry.suite || 'N/A'}</span>
                                </div>

                                <div className="detail-row">
                                    <span className="detail-label">Status:</span>
                                    {getStatusBadge(selectedEntry.status)}
                                </div>

                                <div className="detail-row">
                                    <span className="detail-label">Início:</span>
                                    <span>{formatDate(selectedEntry.started_at)}</span>
                                </div>

                                {selectedEntry.completed_at && (
                                    <div className="detail-row">
                                        <span className="detail-label">Fim:</span>
                                        <span>{formatDate(selectedEntry.completed_at)}</span>
                                    </div>
                                )}

                                <div className="detail-row">
                                    <span className="detail-label">Duração:</span>
                                    <span>{formatDuration(selectedEntry)}</span>
                                </div>

                                {selectedEntry.results_summary && (
                                    <>
                                        <div className="detail-row">
                                            <span className="detail-label">Total de Resultados:</span>
                                            <span>{selectedEntry.results_summary.total_issues || 0}</span>
                                        </div>

                                        {selectedEntry.results_summary.vulnerabilities_by_severity && (
                                            <div className="detail-row">
                                                <span className="detail-label">Por Severidade:</span>
                                                <div style={{ display: 'flex', gap: '12px' }}>
                                                    <span style={{ color: '#ef4444' }}>
                                                        {selectedEntry.results_summary.vulnerabilities_by_severity.error || 0} erros
                                                    </span>
                                                    <span style={{ color: '#f97316' }}>
                                                        {selectedEntry.results_summary.vulnerabilities_by_severity.warning || 0} avisos
                                                    </span>
                                                    <span style={{ color: '#8b93b0' }}>
                                                        {selectedEntry.results_summary.vulnerabilities_by_severity.note || 0} notas
                                                    </span>
                                                </div>
                                            </div>
                                        )}

                                        <div className="detail-row">
                                            <span className="detail-label">Caminhos Tainted:</span>
                                            <span>{selectedEntry.results_summary.tainted_paths || 0}</span>
                                        </div>
                                    </>
                                )}

                                {selectedEntry.error_message && (
                                    <div className="detail-row">
                                        <span className="detail-label">Erro:</span>
                                        <div style={{ color: '#ef4444', fontSize: '12px', marginTop: '4px' }}>
                                            {selectedEntry.error_message}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
