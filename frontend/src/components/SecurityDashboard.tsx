import { useEffect, useMemo, useState } from 'react';
import {
    fetchProjects,
    fetchSecuritySummary,
    fetchSecurityVulnerabilities,
    type SecuritySummary,
    type SecurityVulnerabilityRecord,
    type SecurityFileSummary,
} from '../api';

interface SecurityDashboardProps {
    onClose: () => void;
    onFocusNode?: (nodeKey: string) => void;
    onOpenImpactAnalysis?: (nodeKey: string) => void;
}

const SEVERITY_COLORS: Record<string, string> = {
    error: '#ef4444',
    warning: '#f97316',
    note: '#8b93b0',
};

const SEVERITY_KEYS = ['error', 'warning', 'note'];

export default function SecurityDashboard({
    onClose,
    onFocusNode,
    onOpenImpactAnalysis,
}: SecurityDashboardProps) {
    const [summary, setSummary] = useState<SecuritySummary | null>(null);
    const [projects, setProjects] = useState<string[]>([]);
    const [vulnerabilities, setVulnerabilities] = useState<SecurityVulnerabilityRecord[]>([]);
    const [filterSeverity, setFilterSeverity] = useState<string>('');
    const [filterProject, setFilterProject] = useState<string>('');
    const [filterRule, setFilterRule] = useState<string>('');
    const [loadingVulns, setLoadingVulns] = useState(true);
    const [summaryError, setSummaryError] = useState<string | null>(null);
    const [tableError, setTableError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        setSummaryError(null);
        fetchSecuritySummary()
            .then((data) => {
                if (!cancelled) setSummary(data);
            })
            .catch((err) => {
                if (!cancelled) setSummaryError(err.message || 'Falha ao carregar resumo de segurança');
            })
            .finally(() => {
                // Loading summary removed
            });

        fetchProjects()
            .then((items) => {
                if (!cancelled) setProjects(items);
            })
            .catch(() => {
                if (!cancelled) setProjects([]);
            });

        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        let cancelled = false;
        setLoadingVulns(true);
        setTableError(null);
        fetchSecurityVulnerabilities({
            severity: filterSeverity || undefined,
            project: filterProject || undefined,
            ruleId: filterRule || undefined,
            limit: 400,
        })
            .then((data) => {
                if (!cancelled) setVulnerabilities(data.items);
            })
            .catch((err) => {
                if (!cancelled) setTableError(err.message || 'Falha ao carregar vulnerabilidades');
            })
            .finally(() => {
                if (!cancelled) setLoadingVulns(false);
            });
        return () => {
            cancelled = true;
        };
    }, [filterSeverity, filterProject, filterRule]);

    const severityTotals = useMemo(() => {
        const totals: Record<string, number> = {};
        const data = summary?.severity_breakdown ?? {};
        SEVERITY_KEYS.forEach((key) => {
            totals[key] = data[key] ?? 0;
        });
        return totals;
    }, [summary]);

    const maxLoc = useMemo(() => {
        const files = summary?.top_files ?? [];
        if (!files.length) return 120;
        return Math.max(...files.map((file) => file.loc || 0), 120);
    }, [summary]);

    const heatmapItems = summary?.top_files ?? [];

    const handleExportVulnerabilities = () => {
        if (!vulnerabilities.length) return;
        const header = ['Rule ID', 'Severidade', 'Arquivo', 'Linha', 'Nó', 'Projeto', 'Mensagem'];
        const rows = vulnerabilities.map((item) => [
            item.rule_id,
            item.severity,
            item.file_path,
            item.start_line.toString(),
            item.entity_name || item.entity_key || '',
            item.project || '',
            item.message.replace(/"/g, '""'),
        ]);
        const csv = [header, ...rows]
            .map((line) => line.map((value) => `"${value}"`).join(','))
            .join('\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `vulnerabilidades-${new Date().toISOString()}.csv`;
        link.click();
        URL.revokeObjectURL(url);
    };

    const heatmapTooltip = (file: SecurityFileSummary) =>
        `${file.file_path}\nProjeto: ${file.project ?? 'local'}\nVulnerabilidades: ${file.vulnerability_count}\nRegras: ${file.rule_ids.slice(0, 5).join(', ')}`;

    return (
        <div className="modal-overlay security-dashboard-overlay">
            <div className="security-dashboard-panel">
                <div className="dashboard-header">
                    <div>
                        <h2>Security Intelligence</h2>
                        <p className="section-desc">Visão centralizada de vulnerabilidades e cobertura CodeQL.</p>
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <button className="btn btn-secondary" onClick={handleExportVulnerabilities} disabled={!vulnerabilities.length}>
                            Exportar CSV
                        </button>
                        <button className="btn" onClick={onClose}>
                            × Fechar
                        </button>
                    </div>
                </div>

                <div className="security-cards">
                    <div className="security-card">
                        <div className="card-label">Total de vulnerabilidades</div>
                        <div className="card-value">{summary?.total_vulnerabilities ?? 0}</div>
                        <div className="card-meta">
                            {SEVERITY_KEYS.map((key) => (
                                <span key={key} className="severity-pill" style={{ borderColor: SEVERITY_COLORS[key], color: SEVERITY_COLORS[key] }}>
                                    {key}: {severityTotals[key]}
                                </span>
                            ))}
                        </div>
                    </div>
                    <div className="security-card">
                        <div className="card-label">Cobertura CodeQL</div>
                        <div className="card-value">
                            {summary ? `${summary.coverage.coverage_percent.toFixed(1)}%` : '—'}
                        </div>
                        <div className="card-meta">
                            {summary
                                ? `${summary.coverage.analyzed_nodes}/${summary.coverage.total_nodes} nós analisados`
                                : 'Dados indisponíveis'}
                        </div>
                    </div>
                    <div className="security-card">
                        <div className="card-label">Nós tainted</div>
                        <div className="card-value">{summary?.tainted_nodes ?? 0}</div>
                        <div className="card-meta">Marcados como is_tainted = true</div>
                    </div>
                    <div className="security-card">
                        <div className="card-label">Arquivos críticos</div>
                        <div className="card-value">{heatmapItems.length}</div>
                        <div className="card-meta">Top files com maior concentração</div>
                    </div>
                </div>

                <div className="security-section">
                    <div className="section-title-row">
                        <div>
                            <h3>Mapa de calor</h3>
                            <p className="section-desc">Retângulos proporcionais às linhas de código, cor indica severidade máxima.</p>
                        </div>
                        <button className="btn btn-secondary" onClick={() => setFilterProject('')}>
                            Limpar destaque
                        </button>
                    </div>
                    {summaryError && <div className="alert alert-warning">{summaryError}</div>}
                    <div className="security-heatmap-grid">
                        {heatmapItems.map((file, index) => {
                            const sizeFactor = Math.min(1, (file.loc || 0) / maxLoc);
                            const height = 70 + sizeFactor * 80;
                            const width = 120 + sizeFactor * 60;
                            return (
                                <div
                                    key={`heatmap-${file.file_path}-${index}`}
                                    className="security-heatmap-item"
                                    style={{
                                        background: `${SEVERITY_COLORS[file.highest_severity] || '#8b93b0'}22`,
                                        borderColor: SEVERITY_COLORS[file.highest_severity] || '#8b93b0',
                                        minHeight: height,
                                        maxHeight: height,
                                        width,
                                    }}
                                    title={heatmapTooltip(file)}
                                    onClick={() => file.node_key && onFocusNode?.(file.node_key)}
                                >
                                    <div className="heatmap-file">{file.file_path}</div>
                                    <div className="heatmap-meta">
                                        <span>{file.project || 'local'}</span>
                                        <span>{file.vulnerability_count} vulns</span>
                                    </div>
                                    <div className="heatmap-badges">
                                        {file.rule_ids.slice(0, 3).map((rule) => (
                                            <span key={rule} className="heatmap-badge">
                                                {rule}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            );
                        })}
                        {!heatmapItems.length && (
                            <div className="empty-state">Nenhum arquivo com vulnerabilidades mapeado.</div>
                        )}
                    </div>
                </div>

                <div className="security-section">
                    <div className="section-title-row">
                        <div>
                            <h3>🔄 Risco Combinado</h3>
                            <p className="section-desc">Correlação entre fragilidade arquitetural e vulnerabilidades de segurança.</p>
                        </div>
                    </div>

                    <div className="risk-correlation-wrapper">
                        <div className="risk-scatter-plot">
                            <svg viewBox="0 0 400 300" className="scatter-svg">
                                {/* Eixos */}
                                <line x1="50" y1="250" x2="350" y2="250" stroke="rgba(255,255,255,0.2)" strokeWidth="1" />
                                <line x1="50" y1="250" x2="50" y2="50" stroke="rgba(255,255,255,0.2)" strokeWidth="1" />

                                {/* Labels dos eixos */}
                                <text x="200" y="275" textAnchor="middle" fill="var(--text-secondary)" fontSize="11">
                                    Fragilidade (fragility_score)
                                </text>
                                <text x="15" y="150" textAnchor="middle" fill="var(--text-secondary)" fontSize="11" transform="rotate(-90 15 150)">
                                    Vulnerabilidades
                                </text>

                                {/* Quadrante crítico */}
                                <rect x="200" y="50" width="150" height="100" fill="rgba(239,68,68,0.1)" stroke="#ef4444" strokeWidth="1" strokeDasharray="3 3" />
                                <text x="275" y="75" fill="#ef4444" fontSize="10" fontWeight="600">
                                    Zona Crítica
                                </text>

                                {/* Pontos do scatter plot */}
                                {summary?.top_files?.slice(0, 20).map((file, index) => {
                                    // Simular dados de fragilidade (em produção viria da API)
                                    const fragilityScore = Math.random() * 100; // Placeholder
                                    const vulnCount = file.vulnerability_count;

                                    // Escalar para coordenadas SVG
                                    const x = 50 + (fragilityScore / 100) * 300;
                                    const y = 250 - (Math.min(vulnCount, 10) / 10) * 200;

                                    // Cor baseada na camada (simulada)
                                    const colors = ['#60a5fa', '#a78bfa', '#34d399', '#f97316', '#ef4444'];
                                    const color = colors[index % colors.length];

                                    return (
                                        <circle
                                            key={`scatter-${file.file_path}`}
                                            cx={x}
                                            cy={y}
                                            r={Math.max(3, Math.min(8, vulnCount))}
                                            fill={color}
                                            stroke="#0c1024"
                                            strokeWidth="1"
                                            opacity="0.8"
                                        >
                                            <title>
                                                {file.file_path}
                                                {'\n'}Fragilidade: {fragilityScore.toFixed(1)}
                                                {'\n'}Vulnerabilidades: {vulnCount}
                                                {'\n'}Projeto: {file.project || 'local'}
                                            </title>
                                        </circle>
                                    );
                                })}
                            </svg>
                        </div>

                        <div className="risk-table">
                            <h4>Top 10 Nós de Maior Risco</h4>
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Arquivo</th>
                                        <th>Projeto</th>
                                        <th>Fragilidade</th>
                                        <th>Vulns</th>
                                        <th>Risco</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {summary?.top_files?.slice(0, 10).map((file) => {
                                        const fragilityScore = Math.random() * 100; // Placeholder
                                        const riskScore = (fragilityScore * file.vulnerability_count) / 100;

                                        return (
                                            <tr key={`risk-${file.file_path}`}>
                                                <td style={{ fontSize: '12px' }}>{file.file_path.split('/').pop()}</td>
                                                <td>{file.project || 'local'}</td>
                                                <td style={{ color: fragilityScore > 70 ? '#ef4444' : '#22c55e' }}>
                                                    {fragilityScore.toFixed(1)}
                                                </td>
                                                <td>{file.vulnerability_count}</td>
                                                <td style={{
                                                    fontWeight: 'bold',
                                                    color: riskScore > 50 ? '#ef4444' : riskScore > 25 ? '#f97316' : '#22c55e'
                                                }}>
                                                    {riskScore.toFixed(1)}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <div className="security-section">
                    <div className="section-title-row">
                        <div>
                            <h3>Tabela de vulnerabilidades</h3>
                            <p className="section-desc">Filtrar por severidade, projeto ou regra.</p>
                        </div>
                        <div className="filter-row">
                            <select value={filterSeverity} onChange={(event) => setFilterSeverity(event.target.value)}>
                                <option value="">Todas as severidades</option>
                                {SEVERITY_KEYS.map((key) => (
                                    <option key={key} value={key}>
                                        {key}
                                    </option>
                                ))}
                            </select>
                            <select value={filterProject} onChange={(event) => setFilterProject(event.target.value)}>
                                <option value="">Todos os projetos</option>
                                {projects.map((project) => (
                                    <option key={project} value={project}>
                                        {project}
                                    </option>
                                ))}
                            </select>
                            <input
                                placeholder="Regra (ex: sql-injection)"
                                value={filterRule}
                                onChange={(event) => setFilterRule(event.target.value)}
                            />
                            <button className="btn btn-secondary" onClick={() => {
                                setFilterSeverity('');
                                setFilterProject('');
                                setFilterRule('');
                            }}>
                                Limpar filtros
                            </button>
                        </div>
                    </div>

                    {tableError && <div className="alert alert-warning">{tableError}</div>}

                    <div className="security-table-wrapper">
                        <table className="security-table">
                            <thead>
                                <tr>
                                    <th>Rule ID</th>
                                    <th>Severidade</th>
                                    <th>Arquivo</th>
                                    <th>Linha</th>
                                    <th>Nó afetado</th>
                                    <th>Mensagem</th>
                                    <th>Ações</th>
                                </tr>
                            </thead>
                            <tbody>
                                {loadingVulns ? (
                                    <tr>
                                        <td colSpan={7} className="empty-state">
                                            Carregando vulnerabilidades...
                                        </td>
                                    </tr>
                                ) : vulnerabilities.length ? (
                                    vulnerabilities.map((item) => (
                                        <tr key={`${item.rule_id}-${item.file_path}-${item.start_line}`}>
                                            <td className="monospace">{item.rule_id}</td>
                                            <td style={{ color: SEVERITY_COLORS[item.severity] || '#8b93b0' }}>{item.severity}</td>
                                            <td>{item.file_path}</td>
                                            <td>{item.start_line}</td>
                                            <td>
                                                {item.entity_name || item.entity_key || '—'}
                                            </td>
                                            <td>{item.message}</td>
                                            <td className="action-cell">
                                                {item.entity_key && (
                                                    <>
                                                        <button
                                                            className="btn btn-ghost"
                                                            onClick={() => onFocusNode?.(item.entity_key!)}
                                                        >
                                                            Ver no grafo
                                                        </button>
                                                        <button
                                                            className="btn btn-ghost"
                                                            onClick={() => onOpenImpactAnalysis?.(item.entity_key!)}
                                                        >
                                                            Impacto
                                                        </button>
                                                    </>
                                                )}
                                            </td>
                                        </tr>
                                    ))
                                ) : (
                                    <tr>
                                        <td colSpan={7} className="empty-state">
                                            Nenhuma vulnerabilidade encontrada para os filtros atuais.
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>

                    {!loadingVulns && (
                        <div className="table-footer">
                            Exibindo {vulnerabilities.length} vulnerabilidades
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
