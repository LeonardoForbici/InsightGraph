import { useState, useEffect } from 'react';
import { fetchCodeQLHistory, fetchCodeQLProjects, type CodeQLHistoryEntry, type CodeQLProject } from '../api';

/* ─── Types ─── */

interface AnalysisHistoryProps {
    onClose: () => void;
}

interface Filters {
    projectId: string;
    startDate: string;
    endDate: string;
}

/* ─── Constants ─── */

const ITEMS_PER_PAGE = 10;

const SEVERITY_COLORS: Record<string, string> = {
    error: '#ef4444',
    warning: '#fb923c',
    note: '#8b93b0',
};

/* ─── Component ─── */

function AnalysisHistory({ onClose }: AnalysisHistoryProps) {
    const [history, setHistory] = useState<CodeQLHistoryEntry[]>([]);
    const [filteredHistory, setFilteredHistory] = useState<CodeQLHistoryEntry[]>([]);
    const [projects, setProjects] = useState<CodeQLProject[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [selectedEntry, setSelectedEntry] = useState<CodeQLHistoryEntry | null>(null);
    const [currentPage, setCurrentPage] = useState(1);
    const [filters, setFilters] = useState<Filters>({
        projectId: '',
        startDate: '',
        endDate: '',
    });

    // Load history and projects on mount
    useEffect(() => {
        loadData();
    }, []);

    // Apply filters whenever history or filters change
    useEffect(() => {
        applyFilters();
    }, [history, filters]);

    const loadData = async () => {
        setLoading(true);
        setError('');
        try {
            const [historyData, projectsData] = await Promise.all([
                fetchCodeQLHistory(),
                fetchCodeQLProjects(),
            ]);
            setHistory(historyData);
            setProjects(projectsData);
        } catch (err: any) {
            setError(err.message || 'Erro ao carregar histórico');
        } finally {
            setLoading(false);
        }
    };

    const applyFilters = () => {
        let filtered = [...history];

        // Filter by project
        if (filters.projectId) {
            filtered = filtered.filter((entry) => entry.project_id === filters.projectId);
        }

        // Filter by date range
        if (filters.startDate) {
            const startTime = new Date(filters.startDate).getTime();
            filtered = filtered.filter((entry) => new Date(entry.started_at).getTime() >= startTime);
        }

        if (filters.endDate) {
            const endTime = new Date(filters.endDate).getTime();
            filtered = filtered.filter((entry) => new Date(entry.started_at).getTime() <= endTime);
        }

        setFilteredHistory(filtered);
        setCurrentPage(1); // Reset to first page when filters change
    };

    const handleFilterChange = (key: keyof Filters, value: string) => {
        setFilters((prev) => ({ ...prev, [key]: value }));
    };

    const clearFilters = () => {
        setFilters({ projectId: '', startDate: '', endDate: '' });
    };

    // Pagination
    const totalPages = Math.ceil(filteredHistory.length / ITEMS_PER_PAGE);
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    const endIndex = startIndex + ITEMS_PER_PAGE;
    const currentItems = filteredHistory.slice(startIndex, endIndex);

    const goToPage = (page: number) => {
        setCurrentPage(Math.max(1, Math.min(page, totalPages)));
    };

    return (
        <div
            style={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                background: 'rgba(0, 0, 0, 0.7)',
                backdropFilter: 'blur(4px)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 2000,
            }}
            onClick={onClose}
        >
            <div
                style={{
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius)',
                    width: '90vw',
                    maxWidth: 1200,
                    maxHeight: '85vh',
                    display: 'flex',
                    flexDirection: 'column',
                    overflow: 'hidden',
                    boxShadow: 'var(--shadow-float)',
                }}
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div
                    style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '20px 24px',
                        borderBottom: '1px solid var(--border-subtle)',
                        background: 'var(--bg-glass)',
                    }}
                >
                    <div>
                        <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                            📊 Histórico de Análises CodeQL
                        </h2>
                        <p style={{ margin: '4px 0 0', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                            Visualize análises anteriores e seus resultados
                        </p>
                    </div>
                    <button onClick={onClose} className="btn btn-ghost">
                        ✕ Fechar
                    </button>
                </div>

                {/* Content */}
                <div style={{ padding: 24, overflowY: 'auto', flex: 1 }}>
                    {error && (
                        <div
                            style={{
                                padding: 12,
                                background: 'rgba(239, 68, 68, 0.1)',
                                border: '1px solid rgba(239, 68, 68, 0.3)',
                                borderRadius: 'var(--radius-sm)',
                                color: '#ef4444',
                                marginBottom: 16,
                                fontSize: '0.9rem',
                            }}
                        >
                            ⚠ {error}
                        </div>
                    )}

                    {loading ? (
                        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                            Carregando histórico...
                        </div>
                    ) : (
                        <>
                            {/* Filters */}
                            <div
                                style={{
                                    display: 'flex',
                                    gap: 12,
                                    marginBottom: 20,
                                    padding: 16,
                                    background: 'var(--bg-card)',
                                    border: '1px solid var(--border-subtle)',
                                    borderRadius: 'var(--radius-sm)',
                                    flexWrap: 'wrap',
                                }}
                            >
                                <div style={{ flex: '1 1 200px' }}>
                                    <label
                                        style={{
                                            display: 'block',
                                            fontSize: '0.85rem',
                                            fontWeight: 600,
                                            color: 'var(--text-primary)',
                                            marginBottom: 6,
                                        }}
                                    >
                                        Projeto
                                    </label>
                                    <select
                                        value={filters.projectId}
                                        onChange={(e) => handleFilterChange('projectId', e.target.value)}
                                        style={{
                                            width: '100%',
                                            padding: '8px 12px',
                                            background: 'var(--bg-secondary)',
                                            border: '1px solid var(--border-subtle)',
                                            borderRadius: 'var(--radius-xs)',
                                            color: 'var(--text-primary)',
                                            fontSize: '0.9rem',
                                        }}
                                    >
                                        <option value="">Todos os projetos</option>
                                        {projects.map((project) => (
                                            <option key={project.id} value={project.id}>
                                                {project.name}
                                            </option>
                                        ))}
                                    </select>
                                </div>

                                <div style={{ flex: '1 1 150px' }}>
                                    <label
                                        style={{
                                            display: 'block',
                                            fontSize: '0.85rem',
                                            fontWeight: 600,
                                            color: 'var(--text-primary)',
                                            marginBottom: 6,
                                        }}
                                    >
                                        Data Inicial
                                    </label>
                                    <input
                                        type="date"
                                        value={filters.startDate}
                                        onChange={(e) => handleFilterChange('startDate', e.target.value)}
                                        style={{
                                            width: '100%',
                                            padding: '8px 12px',
                                            background: 'var(--bg-secondary)',
                                            border: '1px solid var(--border-subtle)',
                                            borderRadius: 'var(--radius-xs)',
                                            color: 'var(--text-primary)',
                                            fontSize: '0.9rem',
                                        }}
                                    />
                                </div>

                                <div style={{ flex: '1 1 150px' }}>
                                    <label
                                        style={{
                                            display: 'block',
                                            fontSize: '0.85rem',
                                            fontWeight: 600,
                                            color: 'var(--text-primary)',
                                            marginBottom: 6,
                                        }}
                                    >
                                        Data Final
                                    </label>
                                    <input
                                        type="date"
                                        value={filters.endDate}
                                        onChange={(e) => handleFilterChange('endDate', e.target.value)}
                                        style={{
                                            width: '100%',
                                            padding: '8px 12px',
                                            background: 'var(--bg-secondary)',
                                            border: '1px solid var(--border-subtle)',
                                            borderRadius: 'var(--radius-xs)',
                                            color: 'var(--text-primary)',
                                            fontSize: '0.9rem',
                                        }}
                                    />
                                </div>

                                <div style={{ display: 'flex', alignItems: 'flex-end' }}>
                                    <button
                                        onClick={clearFilters}
                                        className="btn btn-ghost"
                                        style={{ fontSize: '0.85rem', padding: '8px 16px' }}
                                    >
                                        Limpar Filtros
                                    </button>
                                </div>
                            </div>

                            {/* Results Summary */}
                            <div
                                style={{
                                    marginBottom: 16,
                                    fontSize: '0.9rem',
                                    color: 'var(--text-muted)',
                                }}
                            >
                                Exibindo {currentItems.length} de {filteredHistory.length} análises
                            </div>

                            {/* History Table */}
                            {filteredHistory.length === 0 ? (
                                <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                                    Nenhuma análise encontrada
                                </div>
                            ) : (
                                <>
                                    <div
                                        style={{
                                            overflowX: 'auto',
                                            marginBottom: 20,
                                        }}
                                    >
                                        <table
                                            style={{
                                                width: '100%',
                                                borderCollapse: 'collapse',
                                                fontSize: '0.9rem',
                                            }}
                                        >
                                            <thead>
                                                <tr
                                                    style={{
                                                        background: 'var(--bg-card)',
                                                        borderBottom: '2px solid var(--border-subtle)',
                                                    }}
                                                >
                                                    <th style={tableHeaderStyle}>Data/Hora</th>
                                                    <th style={tableHeaderStyle}>Projeto</th>
                                                    <th style={tableHeaderStyle}>Duração</th>
                                                    <th style={tableHeaderStyle}>Status</th>
                                                    <th style={tableHeaderStyle}>Vulnerabilidades</th>
                                                    <th style={tableHeaderStyle}>Ações</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {currentItems.map((entry) => (
                                                    <HistoryRow
                                                        key={entry.job_id}
                                                        entry={entry}
                                                        onViewDetails={() => setSelectedEntry(entry)}
                                                    />
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>

                                    {/* Pagination */}
                                    {totalPages > 1 && (
                                        <div
                                            style={{
                                                display: 'flex',
                                                justifyContent: 'center',
                                                alignItems: 'center',
                                                gap: 8,
                                            }}
                                        >
                                            <button
                                                onClick={() => goToPage(currentPage - 1)}
                                                disabled={currentPage === 1}
                                                className="btn btn-ghost"
                                                style={{ fontSize: '0.85rem', padding: '6px 12px' }}
                                            >
                                                ← Anterior
                                            </button>
                                            <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                                                Página {currentPage} de {totalPages}
                                            </span>
                                            <button
                                                onClick={() => goToPage(currentPage + 1)}
                                                disabled={currentPage === totalPages}
                                                className="btn btn-ghost"
                                                style={{ fontSize: '0.85rem', padding: '6px 12px' }}
                                            >
                                                Próxima →
                                            </button>
                                        </div>
                                    )}
                                </>
                            )}
                        </>
                    )}
                </div>
            </div>

            {/* Detail Modal */}
            {selectedEntry && (
                <DetailModal entry={selectedEntry} onClose={() => setSelectedEntry(null)} />
            )}
        </div>
    );
}

/* ─── Table Styles ─── */

const tableHeaderStyle: React.CSSProperties = {
    padding: '12px 16px',
    textAlign: 'left',
    fontWeight: 600,
    color: 'var(--text-primary)',
    fontSize: '0.85rem',
};

const tableCellStyle: React.CSSProperties = {
    padding: '12px 16px',
    borderBottom: '1px solid var(--border-subtle)',
    color: 'var(--text-secondary)',
};

/* ─── History Row Component ─── */

interface HistoryRowProps {
    entry: CodeQLHistoryEntry;
    onViewDetails: () => void;
}

function HistoryRow({ entry, onViewDetails }: HistoryRowProps) {
    const formatDate = (dateString: string): string => {
        const date = new Date(dateString);
        return date.toLocaleString('pt-BR', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    };

    const formatDuration = (seconds: number): string => {
        if (seconds < 60) return `${seconds}s`;
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        return `${minutes}m ${remainingSeconds}s`;
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'completed':
                return '#34d399';
            case 'failed':
                return '#ef4444';
            case 'cancelled':
                return '#8b93b0';
            default:
                return '#4f8ff7';
        }
    };

    return (
        <tr style={{ transition: 'background var(--transition-fast)' }}>
            <td style={tableCellStyle}>{formatDate(entry.started_at)}</td>
            <td style={tableCellStyle}>
                <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{entry.project_name}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    {entry.suite}
                </div>
            </td>
            <td style={tableCellStyle}>{formatDuration(entry.duration_seconds)}</td>
            <td style={tableCellStyle}>
                <span
                    style={{
                        padding: '4px 8px',
                        borderRadius: 'var(--radius-xs)',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        background: `${getStatusColor(entry.status)}22`,
                        color: getStatusColor(entry.status),
                    }}
                >
                    {entry.status.toUpperCase()}
                </span>
            </td>
            <td style={tableCellStyle}>
                {entry.results_summary ? (
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        {Object.entries(entry.results_summary.vulnerabilities_by_severity).map(([severity, count]) => (
                            <span
                                key={severity}
                                style={{
                                    padding: '2px 6px',
                                    borderRadius: 'var(--radius-xs)',
                                    fontSize: '0.75rem',
                                    fontWeight: 600,
                                    background: `${SEVERITY_COLORS[severity] || '#8b93b0'}22`,
                                    color: SEVERITY_COLORS[severity] || '#8b93b0',
                                }}
                            >
                                {severity}: {count}
                            </span>
                        ))}
                    </div>
                ) : (
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>—</span>
                )}
            </td>
            <td style={tableCellStyle}>
                <button
                    onClick={onViewDetails}
                    className="btn btn-ghost"
                    style={{ fontSize: '0.8rem', padding: '4px 12px' }}
                >
                    Ver Detalhes
                </button>
            </td>
        </tr>
    );
}

/* ─── Detail Modal Component ─── */

interface DetailModalProps {
    entry: CodeQLHistoryEntry;
    onClose: () => void;
}

function DetailModal({ entry, onClose }: DetailModalProps) {
    const formatDate = (dateString: string): string => {
        const date = new Date(dateString);
        return date.toLocaleString('pt-BR', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });
    };

    const formatDuration = (seconds: number): string => {
        if (seconds < 60) return `${seconds} segundos`;
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        return `${minutes} minutos e ${remainingSeconds} segundos`;
    };

    const formatFileSize = (bytes: number | null): string => {
        if (!bytes) return 'N/A';
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
    };

    return (
        <div
            style={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                background: 'rgba(0, 0, 0, 0.8)',
                backdropFilter: 'blur(4px)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 2100,
            }}
            onClick={onClose}
        >
            <div
                style={{
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius)',
                    width: '90vw',
                    maxWidth: 700,
                    maxHeight: '80vh',
                    display: 'flex',
                    flexDirection: 'column',
                    overflow: 'hidden',
                    boxShadow: 'var(--shadow-float)',
                }}
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div
                    style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '16px 20px',
                        borderBottom: '1px solid var(--border-subtle)',
                        background: 'var(--bg-glass)',
                    }}
                >
                    <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                        Detalhes da Análise
                    </h3>
                    <button onClick={onClose} className="btn btn-ghost" style={{ fontSize: '0.9rem' }}>
                        ✕
                    </button>
                </div>

                {/* Content */}
                <div style={{ padding: 20, overflowY: 'auto', flex: 1 }}>
                    {/* Basic Info */}
                    <div style={{ marginBottom: 20 }}>
                        <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>
                            Informações Gerais
                        </h4>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            <DetailRow label="Projeto" value={entry.project_name} />
                            <DetailRow label="Job ID" value={entry.job_id} mono />
                            <DetailRow label="Suite" value={entry.suite} />
                            <DetailRow label="Status" value={entry.status.toUpperCase()} />
                            <DetailRow label="Início" value={formatDate(entry.started_at)} />
                            <DetailRow label="Conclusão" value={formatDate(entry.completed_at)} />
                            <DetailRow label="Duração" value={formatDuration(entry.duration_seconds)} />
                        </div>
                    </div>

                    {/* Results Summary */}
                    {entry.results_summary && (
                        <div style={{ marginBottom: 20 }}>
                            <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>
                                Resumo dos Resultados
                            </h4>
                            <div
                                style={{
                                    padding: 16,
                                    background: 'var(--bg-card)',
                                    border: '1px solid var(--border-subtle)',
                                    borderRadius: 'var(--radius-sm)',
                                }}
                            >
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                    <DetailRow label="Total de Vulnerabilidades" value={entry.results_summary.total_issues.toString()} />
                                    <DetailRow label="Ingeridas no Neo4j" value={entry.results_summary.ingested.toString()} />
                                    <DetailRow label="Ignoradas" value={entry.results_summary.skipped.toString()} />
                                    <DetailRow label="Caminhos Contaminados" value={entry.results_summary.tainted_paths.toString()} />
                                </div>

                                {/* Vulnerabilities by Severity */}
                                <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>
                                        Por Severidade:
                                    </div>
                                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                                        {Object.entries(entry.results_summary.vulnerabilities_by_severity).map(([severity, count]) => (
                                            <div
                                                key={severity}
                                                style={{
                                                    padding: '8px 12px',
                                                    borderRadius: 'var(--radius-xs)',
                                                    background: `${SEVERITY_COLORS[severity] || '#8b93b0'}22`,
                                                    border: `1px solid ${SEVERITY_COLORS[severity] || '#8b93b0'}44`,
                                                }}
                                            >
                                                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 2 }}>
                                                    {severity.toUpperCase()}
                                                </div>
                                                <div
                                                    style={{
                                                        fontSize: '1.2rem',
                                                        fontWeight: 700,
                                                        color: SEVERITY_COLORS[severity] || '#8b93b0',
                                                    }}
                                                >
                                                    {count}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* SARIF File Info */}
                    {entry.sarif_path && (
                        <div style={{ marginBottom: 20 }}>
                            <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>
                                Arquivo SARIF
                            </h4>
                            <div
                                style={{
                                    padding: 16,
                                    background: 'var(--bg-card)',
                                    border: '1px solid var(--border-subtle)',
                                    borderRadius: 'var(--radius-sm)',
                                }}
                            >
                                <DetailRow label="Caminho" value={entry.sarif_path} mono />
                                <DetailRow label="Tamanho" value={formatFileSize(entry.sarif_size_bytes)} />
                            </div>
                        </div>
                    )}

                    {/* Error Message */}
                    {entry.error_message && (
                        <div style={{ marginBottom: 20 }}>
                            <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: '#ef4444', marginBottom: 12 }}>
                                Mensagem de Erro
                            </h4>
                            <div
                                style={{
                                    padding: 16,
                                    background: 'rgba(239, 68, 68, 0.08)',
                                    border: '1px solid rgba(239, 68, 68, 0.2)',
                                    borderRadius: 'var(--radius-sm)',
                                    fontFamily: 'var(--font-mono)',
                                    fontSize: '0.85rem',
                                    color: '#fca5a5',
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-word',
                                    maxHeight: 200,
                                    overflowY: 'auto',
                                }}
                            >
                                {entry.error_message}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

/* ─── Detail Row Component ─── */

interface DetailRowProps {
    label: string;
    value: string;
    mono?: boolean;
}

function DetailRow({ label, value, mono }: DetailRowProps) {
    return (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{label}:</span>
            <span
                style={{
                    fontSize: '0.85rem',
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                    fontFamily: mono ? 'var(--font-mono)' : 'inherit',
                    maxWidth: '60%',
                    textAlign: 'right',
                    wordBreak: 'break-word',
                }}
            >
                {value}
            </span>
        </div>
    );
}

/* ─── Export ─── */

export default AnalysisHistory;
