import { useEffect, useMemo, useState } from 'react';
import {
    fetchAntipatterns,
    fetchGraphStats,
    fetchHotspots,
    fetchHotspotCochange,
    fetchCallResolutionSummary,
    fetchRagStatus,
    fetchIso5055,
    fetchOssExposure,
    type AntipatternData,
    type GraphStats,
    type HotspotItem,
    type CochangePair,
    type CallResolutionSummary,
    type RagStatus,
    type IsoQualityGrade,
    type OssExposureResponse,
} from '../api';
import EvolutionDashboard from './EvolutionDashboard';
import QualityGatePanel from './QualityGatePanel';
import DebtTrackerPanel from './DebtTrackerPanel';

interface DashboardProps {
    onClose: () => void;
    onRefactorRequest?: (nodeName: string, problemType: string) => void;
    onOpenInventory?: () => void;
    onFocusNode?: (nodeKey: string) => void;
    onOpenImpactAnalysis?: (nodeKey: string) => void;
}

const getGradeBucket = (grade: string | null | undefined) => {
    if (!grade) return 'unknown';
    const letter = grade.trim().charAt(0).toUpperCase();
    return letter.match(/[A-Z]/) ? letter : 'unknown';
};

export default function Dashboard({ onClose, onRefactorRequest, onOpenInventory, onFocusNode, onOpenImpactAnalysis }: DashboardProps) {
    const openUrl = (path: string) => {
        window.open(path, '_blank');
    };
    const exportButtons = [
        { label: 'Nodes CSV', path: '/api/export/nodes.csv' },
        { label: 'Edges CSV', path: '/api/export/edges.csv' },
        { label: 'Graph JSON', path: '/api/export/graph.json' },
        { label: 'GraphML', path: '/api/export/graph.graphml' },
        { label: 'Findings CSV', path: '/api/findings/export?format=csv' },
        { label: 'Findings JSON', path: '/api/findings/export?format=json' },
    ];
    const reportTypes = [
        { id: 'composition', label: 'Composition' },
        { id: 'hotspots', label: 'Hotspots' },
        { id: 'ck-metrics', label: 'CK Metrics' },
        { id: 'security', label: 'Segurança' },
        { id: 'iso5055', label: 'ISO 5055' },
    ];
    const [antipatterns, setAntipatterns] = useState<AntipatternData | null>(null);
    const [stats, setStats] = useState<GraphStats | null>(null);
    const [hotspots, setHotspots] = useState<HotspotItem[]>([]);
    const [cochange, setCochange] = useState<Record<string, CochangePair[]>>({});
    const [callResolution, setCallResolution] = useState<CallResolutionSummary | null>(null);
    const [ragStatus, setRagStatus] = useState<RagStatus | null>(null);
    const [isoGrade, setIsoGrade] = useState<IsoQualityGrade | null>(null);
    const [ossExposure, setOssExposure] = useState<OssExposureResponse | null>(null);
    const [hotspotSortField, setHotspotSortField] = useState<'name' | 'file' | 'project' | 'complexity' | 'git_churn' | 'hotspot_score'>('hotspot_score');
    const [hotspotSortDirection, setHotspotSortDirection] = useState<'asc' | 'desc'>('desc');
    const [hotspotProjectFilter, setHotspotProjectFilter] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [selectedHotspots, setSelectedHotspots] = useState<Set<string>>(() => new Set());

    useEffect(() => {
        const load = async () => {
            try {
                const [aData, sData, hData, cData, crData, rgData, isoData, ossData] = await Promise.all([
                    fetchAntipatterns(),
                    fetchGraphStats(),
                    fetchHotspots(50, 90),
                    fetchHotspotCochange(90, 12),
                    fetchCallResolutionSummary(undefined, 12),
                    fetchRagStatus(),
                    fetchIso5055(),
                    fetchOssExposure(30),
                ]);
                setAntipatterns(aData);
                setStats(sData);
                setHotspots(hData.hotspots || []);
                setCochange(cData.projects || {});
                setCallResolution(crData);
                setRagStatus(rgData);
                setIsoGrade(isoData);
                setOssExposure(ossData);
            } catch (err) {
                console.error("Failed to load dashboard data.", err);
            } finally {
                setLoading(false);
            }
        };
        load();
    }, []);

    const hotspotProjects = useMemo(() => {
        return Array.from(new Set(hotspots.map((h) => h.project).filter(Boolean)));
    }, [hotspots]);

    const sortedHotspots = useMemo(() => {
        const filtered = hotspotProjectFilter
            ? hotspots.filter((item) => item.project === hotspotProjectFilter)
            : hotspots;
        const sorted = [...filtered].sort((a, b) => {
            const getValue = (item: HotspotItem) => {
                switch (hotspotSortField) {
                    case 'name':
                        return (item.name || '').toLowerCase();
                    case 'file':
                        return (item.file || '').toLowerCase();
                    case 'project':
                        return (item.project || '').toLowerCase();
                    case 'complexity':
                        return item.complexity ?? 0;
                    case 'git_churn':
                        return item.git_churn ?? 0;
                    case 'hotspot_score':
                    default:
                        return item.hotspot_score ?? 0;
                }
            };
            const aValue = getValue(a);
            const bValue = getValue(b);
            if (typeof aValue === 'number' && typeof bValue === 'number') {
                return hotspotSortDirection === 'asc' ? aValue - bValue : bValue - aValue;
            }
            const aStr = String(aValue);
            const bStr = String(bValue);
            return hotspotSortDirection === 'asc' ? aStr.localeCompare(bStr) : bStr.localeCompare(aStr);
        });
        return sorted.slice(0, 50);
    }, [hotspots, hotspotProjectFilter, hotspotSortField, hotspotSortDirection]);

    useEffect(() => {
        setSelectedHotspots((prev) => {
            const valid = new Set(sortedHotspots.map((item) => item.namespace_key));
            const next = new Set([...prev].filter((key) => valid.has(key)));
            if (next.size === prev.size) return prev;
            return next;
        });
    }, [sortedHotspots]);

    const toggleHotspotSelection = (key: string) => {
        setSelectedHotspots((prev) => {
            const next = new Set(prev);
            if (next.has(key)) next.delete(key);
            else next.add(key);
            return next;
        });
    };

    const selectAllVisibleHotspots = () => {
        setSelectedHotspots(new Set(sortedHotspots.map((item) => item.namespace_key)));
    };

    const clearHotspotSelection = () => {
        setSelectedHotspots(new Set());
    };

    const handleHotspotSort = (field: 'name' | 'file' | 'project' | 'complexity' | 'git_churn' | 'hotspot_score') => {
        if (hotspotSortField === field) {
            setHotspotSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
            return;
        }
        setHotspotSortField(field);
        setHotspotSortDirection('desc');
    };

    const sortIndicator = (field: typeof hotspotSortField) =>
        hotspotSortField === field ? (hotspotSortDirection === 'asc' ? '↑' : '↓') : '';

    const selectionCount = selectedHotspots.size;
    const selectAllChecked = sortedHotspots.length > 0 && selectionCount === sortedHotspots.length;

    const maxChurn = Math.max(...sortedHotspots.map((h) => h.git_churn ?? 0), 1);
    const maxComplex = Math.max(...sortedHotspots.map((h) => h.complexity ?? 0), 1);

    const layerColor: Record<string, string> = {
        Database: '#34d399',
        Service: '#fbbf24',
        API: '#a78bfa',
        Frontend: '#60a5fa',
        Mobile: '#f472b6',
        External: '#c084fc',
        Other: '#94a3b8',
    };
    const scatterPoints = sortedHotspots.map((item) => {
        const dependents = ((item as unknown as { dependents_count?: number }).dependents_count) ?? 1;
        const layerName = item.layer ?? 'Other';
        return {
            key: item.namespace_key,
            name: item.name,
            complexity: item.complexity ?? 0,
            churn: item.git_churn ?? 0,
            hotspot: item.hotspot_score ?? 0,
            project: item.project || 'Local',
            layer: layerName,
            dependents,
            radius: 4 + Math.min(12, dependents / 4),
            color: layerColor[layerName] ?? layerColor.Other,
        };
    });

    const handleExportHotspots = () => {
        const candidates = selectedHotspots.size
            ? sortedHotspots.filter((item) => selectedHotspots.has(item.namespace_key))
            : sortedHotspots;
        const header = ['Namespace', 'Nome', 'Arquivo', 'Projeto', 'Hotspot', 'Complexidade', 'Churn'];
        const rows = candidates.map((item) => [
            item.namespace_key,
            item.name,
            item.file || '-',
            item.project || '-',
            String(item.hotspot_score ?? 0),
            String(item.complexity ?? 0),
            String(item.git_churn ?? 0),
        ]);
        const csv = [header, ...rows].map((line) => line.map((val) => `"${val.replace(/"/g, '""')}"`).join(',')).join('\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'hotspots.csv';
        link.click();
        URL.revokeObjectURL(url);
    };

    if (loading) {
        return (
            <div className="dashboard-overlay">
                <div className="dashboard-panel" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div className="loading-spinner"></div>
                    <span style={{ marginLeft: 16 }}>Carregando Métricas da Arquitetura...</span>
                </div>
            </div>
        );
    }

    return (
        <div className="dashboard-overlay">
            <div className="dashboard-panel">
                <div className="dashboard-header">
                    <h2>Métricas Arquiteturais e Antipatterns</h2>
                    <button className="btn" onClick={onClose}>✕ Fechar</button>
                </div>

                <div className="dashboard-content">
                    <div className="dashboard-section" style={{ paddingBottom: 8 }}>
                        <EvolutionDashboard />
                    </div>
                    <div className="dashboard-section hotspot-panel">
                        <div className="hotspot-panel-header">
                            <div>
                                <h3>Hotspot Deep Analysis</h3>
                                <p className="section-desc">Top 50 hotspots com filtros, seleção e visualização de dispersão.</p>
                            </div>
                            <div className="hotspot-controls">
                                <select
                                    value={hotspotProjectFilter ?? ''}
                                    onChange={(event) => setHotspotProjectFilter(event.target.value || null)}
                                >
                                    <option value="">Todos os projetos</option>
                                    {hotspotProjects.map((project) => (
                                        <option key={project} value={project}>{project}</option>
                                    ))}
                                </select>
                                <button className="btn btn-secondary" onClick={handleExportHotspots}>
                                    Export CSV
                                </button>
                            </div>
                        </div>
                        <div className="hotspot-selection-row">
                            <div className="selection-summary">
                                {selectionCount > 0 ? `${selectionCount} selecionado(s)` : 'Nenhuma seleção ativa'}
                            </div>
                            <div className="selection-actions">
                                <button
                                    className="btn btn-ghost"
                                    onClick={selectAllVisibleHotspots}
                                    disabled={!sortedHotspots.length}
                                >
                                    Selecionar visíveis
                                </button>
                                <button
                                    className="btn btn-secondary"
                                    onClick={clearHotspotSelection}
                                    disabled={!selectionCount}
                                >
                                    Limpar seleção
                                </button>
                            </div>
                        </div>
                        <div className="hotspot-panel-grid">
                            <div className="hotspot-table-wrapper">
                                <table className="data-table">
                                    <thead>
                                        <tr>
                                            <th className="select-column">
                                                <input
                                                    type="checkbox"
                                                    checked={selectAllChecked}
                                                    disabled={!sortedHotspots.length}
                                                    onChange={(event) => (event.target.checked ? selectAllVisibleHotspots() : clearHotspotSelection())}
                                                    title="Selecionar todos os hotspots visíveis"
                                                />
                                            </th>
                                            <th className="sortable-header" onClick={() => handleHotspotSort('name')}>
                                                Entidade {sortIndicator('name')}
                                            </th>
                                            <th className="sortable-header" onClick={() => handleHotspotSort('file')}>
                                                Arquivo {sortIndicator('file')}
                                            </th>
                                            <th className="sortable-header" onClick={() => handleHotspotSort('project')}>
                                                Projeto {sortIndicator('project')}
                                            </th>
                                            <th className="sortable-header" onClick={() => handleHotspotSort('complexity')}>
                                                Complexidade {sortIndicator('complexity')}
                                            </th>
                                            <th className="sortable-header" onClick={() => handleHotspotSort('git_churn')}>
                                                Churn {sortIndicator('git_churn')}
                                            </th>
                                            <th className="sortable-header" onClick={() => handleHotspotSort('hotspot_score')}>
                                                Hotspot {sortIndicator('hotspot_score')}
                                            </th>
                                            <th>Ações</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {sortedHotspots.map((h) => (
                                            <tr key={`hotspot-${h.namespace_key}`}>
                                                <td className="select-column">
                                                    <input
                                                        type="checkbox"
                                                        checked={selectedHotspots.has(h.namespace_key)}
                                                        onChange={() => toggleHotspotSelection(h.namespace_key)}
                                                        className="hotspot-checkbox"
                                                    />
                                                </td>
                                                <td>
                                                    <strong>{h.name}</strong><br />
                                                    <small style={{ color: 'var(--text-secondary)' }}>{h.namespace_key}</small>
                                                </td>
                                                <td style={{ fontSize: 12 }}>{h.file || '-'}</td>
                                                <td>{h.project || '-'}</td>
                                                <td>{h.complexity ?? 0}</td>
                                                <td>{h.git_churn ?? 0}</td>
                                                <td style={{ fontWeight: 600, color: '#f97316' }}>{h.hotspot_score ?? 0}</td>
                                                <td className="hotspot-action-col">
                                                    <button
                                                        className="btn btn-ghost"
                                                        onClick={() => onFocusNode?.(h.namespace_key)}
                                                    >
                                                        Ver no Grafo
                                                    </button>
                                                    <button
                                                        className="btn btn-ghost"
                                                        onClick={() => onOpenImpactAnalysis?.(h.namespace_key)}
                                                    >
                                                        Analisar Impacto
                                                    </button>
                                                </td>
                                            </tr>
                                        ))}
                                        {sortedHotspots.length === 0 && (
                                            <tr>
                                                <td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                                                    Nenhum hotspot corresponde aos filtros atuais.
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                            <div className="hotspot-scatter-wrapper">
                                <div className="hotspot-scatter-header">
                                    <h4>Scatter Plot (Git Churn × Complexidade)</h4>
                                    <span className="scatter-subtitle">Quadrante superior direito = Zona Crítica</span>
                                </div>
                                <div className="hotspot-scatter">
                                    <svg viewBox="0 0 320 240">
                                <rect x={170} y={20} width={130} height={90} fill="rgba(239,68,68,0.15)" stroke="#ef4444" strokeDasharray="4 3" />
                                <text x={182} y={40} fill="#f97316" fontSize={11} fontWeight="600">
                                    Zona Crítica
                                </text>
                                <line x1="50" y1="220" x2="310" y2="220" stroke="rgba(255,255,255,0.2)" />
                                <line x1="50" y1="220" x2="50" y2="20" stroke="rgba(255,255,255,0.2)" />
                                {scatterPoints.map((point) => {
                                    const x = 50 + (point.churn / maxChurn) * 250;
                                    const y = 220 - (point.complexity / maxComplex) * 200;
                                    return (
                                        <circle
                                            key={`scatter-${point.key}`}
                                            cx={x}
                                            cy={y}
                                            r={point.radius}
                                            fill={point.color}
                                            stroke="#0c1024"
                                            strokeWidth={1.5}
                                        >
                                            <title>
                                                {point.name} ({point.layer})
                                                {' | '}
                                                Churn: {point.churn}
                                                {' | '}
                                                Complexidade: {point.complexity}
                                                {' | '}
                                                Dependentes: {point.dependents}
                                            </title>
                                        </circle>
                                    );
                                })}
                                    </svg>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div className="dashboard-section">
                        <QualityGatePanel />
                    </div>
                    <div className="dashboard-section">
                        <DebtTrackerPanel />
                    </div>

                    {evolutionSummary && (
                        <div className="dashboard-section">
                            <h3>Tendência Arquitetural</h3>
                            <div className="stats-grid">
                                <div className="stat-card">
                                    <span className="stat-value" style={{ color: evolutionSummary.trend.risk_delta > 0 ? '#ef4444' : '#22c55e' }}>
                                        {evolutionSummary.trend.risk_delta > 0 ? '+' : ''}{evolutionSummary.trend.risk_delta}
                                    </span>
                                    <span className="stat-label">Variação de Risco</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value" style={{ color: '#60a5fa' }}>
                                        {evolutionSummary.trend.nodes_delta > 0 ? '+' : ''}{evolutionSummary.trend.nodes_delta}
                                    </span>
                                    <span className="stat-label">Variação de Nós</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value" style={{ color: '#a78bfa' }}>
                                        {evolutionSummary.trend.edges_delta > 0 ? '+' : ''}{evolutionSummary.trend.edges_delta}
                                    </span>
                                    <span className="stat-label">Variação de Arestas</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value" style={{ color: (evolutionSummary.trend.call_resolution_delta ?? 0) >= 0 ? '#22c55e' : '#ef4444' }}>
                                        {(evolutionSummary.trend.call_resolution_delta ?? 0) > 0 ? '+' : ''}{(evolutionSummary.trend.call_resolution_delta ?? 0)}%
                                    </span>
                                    <span className="stat-label">Delta Resolução de Calls</span>
                                </div>
                            </div>
                        </div>
                    )}

                    {callResolution && (
                        <div className="dashboard-section">
                            <h3>Precisão do Call Graph</h3>
                            <p className="section-desc">Qualidade da resolução de chamadas (`CALLS` → `CALLS_RESOLVED`) no scan atual.</p>
                            <div className="stats-grid">
                                <div className="stat-card">
                                    <span className="stat-value">{callResolution.total_calls}</span>
                                    <span className="stat-label">CALLS detectadas</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value" style={{ color: '#22c55e' }}>{callResolution.resolved_calls}</span>
                                    <span className="stat-label">Resolvidas</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value" style={{ color: '#f97316' }}>{callResolution.unresolved_calls}</span>
                                    <span className="stat-label">Não resolvidas</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value" style={{ color: callResolution.resolution_rate >= 70 ? '#22c55e' : '#ef4444' }}>
                                        {callResolution.resolution_rate}%
                                    </span>
                                    <span className="stat-label">Taxa de resolução</span>
                                </div>
                            </div>

                            {callResolution.by_project.length > 0 && (
                                <>
                                    <h4 style={{ marginTop: 16 }}>Taxa por Projeto</h4>
                                    <table className="data-table">
                                        <thead>
                                            <tr>
                                                <th>Projeto</th>
                                                <th>CALLS</th>
                                                <th>Resolvidas</th>
                                                <th>Não resolvidas</th>
                                                <th>Taxa</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {callResolution.by_project.map((p) => (
                                                <tr key={p.project}>
                                                    <td>{p.project}</td>
                                                    <td>{p.total_calls}</td>
                                                    <td>{p.resolved_calls}</td>
                                                    <td>{p.unresolved_calls}</td>
                                                    <td style={{ fontWeight: 'bold', color: p.resolution_rate >= 70 ? '#22c55e' : '#ef4444' }}>
                                                        {p.resolution_rate}%
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </>
                            )}

                            {callResolution.top_unresolved.length > 0 && (
                                <>
                                    <h4 style={{ marginTop: 16 }}>Top Chamadas Não Resolvidas</h4>
                                    <table className="data-table">
                                        <thead>
                                            <tr>
                                                <th>Owner Hint</th>
                                                <th>Método</th>
                                                <th>Ocorrências</th>
                                                <th>Exemplo</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {callResolution.top_unresolved.map((u, i) => (
                                                <tr key={`${u.owner_hint || '-'}:${u.method_hint}:${i}`}>
                                                    <td>{u.owner_hint || '-'}</td>
                                                    <td style={{ fontWeight: 'bold' }}>{u.method_hint}</td>
                                                    <td>{u.count}</td>
                                                    <td style={{ fontSize: 12 }}>
                                                        {u.examples?.[0]?.source_name || u.examples?.[0]?.source || '-'}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </>
                            )}
                        </div>
                    )}

                    {ragStatus && (
                        <div className="dashboard-section">
                            <h3>Status do RAG Local</h3>
                            <p className="section-desc">Saúde do índice semântico local usado na busca e Q&A.</p>
                            <div className="stats-grid">
                                <div className="stat-card">
                                    <span className="stat-value">{ragStatus.entries}</span>
                                    <span className="stat-label">Entradas Indexadas</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value">{ragStatus.with_embeddings}</span>
                                    <span className="stat-label">Com Embeddings</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value" style={{ color: ragStatus.embedding_coverage >= 70 ? '#22c55e' : '#f97316' }}>
                                        {ragStatus.embedding_coverage}%
                                    </span>
                                    <span className="stat-label">Cobertura Semântica</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value" style={{ color: ragStatus.stale ? '#ef4444' : '#22c55e' }}>
                                        {ragStatus.stale ? 'STALE' : 'OK'}
                                    </span>
                                    <span className="stat-label">Consistência do Índice</span>
                                </div>
                            </div>
                        </div>
                    )}

                    {isoGrade && (
                        <div className="dashboard-section">
                            <h3>ISO 5055 Quality Grade</h3>
                            <p className="section-desc">
                                Grade baseada em 20 regras críticas que avaliam confiabilidade, segurança e mantenibilidade.
                            </p>
                            <div className="stats-grid">
                                <div className="stat-card">
                                    <span className={`stat-value grade-pill grade-large grade-letter grade-${getGradeBucket(isoGrade.grade)}`}>
                                        {isoGrade.grade}
                                    </span>
                                    <span className="stat-label">Grade Geral</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value">{isoGrade.score_percent}%</span>
                                    <span className="stat-label">score (%)</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value">{isoGrade.score_obtained}</span>
                                    <span className="stat-label">Pontos obtidos</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value">{isoGrade.score_max}</span>
                                    <span className="stat-label">Pontos possíveis</span>
                                </div>
                            </div>
                            <div className="iso-rule-list">
                                {isoGrade.rules.map((rule) => (
                                    <div
                                        key={rule.rule_id}
                                        className={`rule-row ${rule.passed ? 'rule-passed' : 'rule-failed'}`}
                                    >
                                        <div>
                                            <span className="rule-id">{rule.rule_id}</span>
                                            <strong>{rule.name}</strong>
                                            <p className="rule-notes">{rule.notes}</p>
                                        </div>
                                        <span className="rule-pill">
                                            {rule.passed ? 'PASS' : 'FAIL'}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {ossExposure && (
                        <div className="dashboard-section">
                            <h3>OSS Exposure (Top {Math.min(ossExposure.items.length, 12)} dependências)</h3>
                            <p className="section-desc">
                                Dependências externas com vulnerabilidades conhecidas consultadas via OSV.dev.
                            </p>
                            {ossExposure.items.length === 0 ? (
                                <div style={{ color: 'var(--text-muted)' }}>Nenhuma vulnerabilidade exposta detectada.</div>
                            ) : (
                                <table className="data-table oss-table">
                                    <thead>
                                        <tr>
                                            <th>Dependência</th>
                                            <th>Versão</th>
                                            <th>Vulns</th>
                                            <th>Resumo</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {ossExposure.items.slice(0, 12).map((dep) => (
                                            <tr key={`${dep.ecosystem}:${dep.name}:${dep.version || 'latest'}`}>
                                                <td>
                                                    <strong>{dep.name}</strong>
                                                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{dep.ecosystem}</div>
                                                </td>
                                                <td>{dep.version || '–'}</td>
                                                <td style={{ fontWeight: 'bold', color: dep.vuln_count > 0 ? '#ef4444' : '#22c55e' }}>
                                                    {dep.vuln_count}
                                                </td>
                                                <td style={{ fontSize: 12 }}>
                                                    {dep.vulnerabilities.slice(0, 2).map((v, i) => (
                                                        <div key={v.id || i}>
                                                            <span style={{ fontWeight: 600 }}>{v.id || 'VULN'}</span>
                                                            : {v.summary || 'Sem resumo'}
                                                        </div>
                                                    ))}
                                                    {dep.vulnerabilities.length > 2 && (
                                                        <em style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                                                            +{dep.vulnerabilities.length - 2} outros
                                                        </em>
                                                    )}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    )}

                    <div className="dashboard-section export-section">
                        <h3>Fase 4 — Relatórios e Exportações</h3>
                        <p className="section-desc">Dados para compartilhar evidências e alimentar outras ferramentas.</p>
                        <div className="export-actions">
                            {exportButtons.map((btn) => (
                                <button key={btn.label} className="btn btn-secondary" onClick={() => openUrl(btn.path)}>
                                    {btn.label}
                                </button>
                            ))}
                        </div>
                        <div className="report-grid">
                            {reportTypes.map((rt) => (
                                <button
                                    key={rt.id}
                                    className="btn btn-primary"
                                    onClick={() => openUrl(`/api/reports/${rt.id}`)}
                                >
                                    {rt.label}
                                </button>
                            ))}
                        </div>
                        {onOpenInventory && (
                            <button className="btn btn-accent" style={{ marginTop: 12 }} onClick={onOpenInventory}>
                                Ver Inventário de APIs
                            </button>
                        )}
                    </div>

                    {/* General Stats */}
                    {stats && (
                        <div className="dashboard-section">
                            <h3>Visão Geral</h3>
                            <div className="stats-grid">
                                <div className="stat-card">
                                    <span className="stat-value">{stats.total_nodes}</span>
                                    <span className="stat-label">Total de Nós</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value">{stats.total_edges}</span>
                                    <span className="stat-label">Total de Dependências</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value">{stats.projects.length}</span>
                                    <span className="stat-label">Projetos Escaneados</span>
                                </div>
                            </div>
                        </div>
                    )}

                    {Object.keys(cochange).length > 0 && (
                        <div className="dashboard-section">
                            <h3>🔗 Co-change (Arquivos que quebram juntos)</h3>
                            <p className="section-desc">Pares de arquivos que mudam juntos com frequência (90 dias).</p>
                            {Object.entries(cochange).map(([project, pairs]) => (
                                <div key={project} style={{ marginBottom: 16 }}>
                                    <h4 style={{ margin: '8px 0', color: 'var(--text-bright)' }}>{project}</h4>
                                    <table className="data-table">
                                        <thead>
                                            <tr>
                                                <th>Arquivo A</th>
                                                <th>Arquivo B</th>
                                                <th>Co-change</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {pairs.slice(0, 8).map((p, i) => (
                                                <tr key={`${project}-${i}`}>
                                                    <td style={{ fontSize: 12 }}>{p.file_a}</td>
                                                    <td style={{ fontSize: 12 }}>{p.file_b}</td>
                                                    <td style={{ fontWeight: 'bold' }}>{p.cochange_count}</td>
                                                </tr>
                                            ))}
                                            {pairs.length === 0 && (
                                                <tr><td colSpan={3}>Sem dados de co-change para este projeto.</td></tr>
                                            )}
                                        </tbody>
                                    </table>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* God Classes */}
                    {antipatterns && (
                        <div className="dashboard-section">
                            <h3>⚠️ Classes Onipresentes (God Classes) & Hotspots</h3>
                            <p className="section-desc">Arquivos com acoplamento excessivo ou complexidade ciclomática crítica (&gt;20).</p>
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Nome da Entidade</th>
                                        <th>Camada</th>
                                        <th>Dependências Entrantes / Saintes</th>
                                        <th>Complexidade Ciclomática</th>
                                        <th style={{ width: '140px' }}>Ação</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {antipatterns.god_classes.map((item, i) => (
                                        <tr key={i}>
                                            <td style={{ fontWeight: 'bold', color: 'var(--text-bright)' }}>{item.name}</td>
                                            <td>{item.layer}</td>
                                            <td>{item.in_degree} chegando / {item.out_degree} saindo</td>
                                            <td style={{ color: item.complexity > 20 ? '#ef4444' : 'inherit', fontWeight: 'bold' }}>
                                                {item.complexity}
                                            </td>
                                            <td>
                                                <button
                                                    onClick={() => onRefactorRequest?.(item.name, 'God Class')}
                                                    style={{
                                                        padding: '4px 10px',
                                                        background: 'linear-gradient(135deg, rgba(34, 211, 238, 0.15), rgba(167, 139, 250, 0.15))',
                                                        color: 'var(--accent-cyan)',
                                                        border: '1px solid rgba(34, 211, 238, 0.2)',
                                                        borderRadius: 'var(--radius-xs)',
                                                        cursor: 'pointer',
                                                        fontSize: '11px',
                                                        fontWeight: 500,
                                                        transition: 'all var(--transition-fast)',
                                                        whiteSpace: 'nowrap',
                                                    }}
                                                    onMouseEnter={(e) => {
                                                        (e.target as HTMLButtonElement).style.background = 'linear-gradient(135deg, rgba(34, 211, 238, 0.25), rgba(167, 139, 250, 0.25))';
                                                        (e.target as HTMLButtonElement).style.boxShadow = '0 0 12px rgba(34, 211, 238, 0.15)';
                                                    }}
                                                    onMouseLeave={(e) => {
                                                        (e.target as HTMLButtonElement).style.background = 'linear-gradient(135deg, rgba(34, 211, 238, 0.15), rgba(167, 139, 250, 0.15))';
                                                        (e.target as HTMLButtonElement).style.boxShadow = 'none';
                                                    }}
                                                >
                                                    🔧 Como resolver?
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                    {antipatterns.god_classes.length === 0 && (
                                        <tr><td colSpan={5}>Nenhuma Classe Onipresente (God Class) crítica encontrada neste scan.</td></tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {/* Circular Dependencies */}
                    {antipatterns && (
                        <div className="dashboard-section">
                            <h3>🔄 Dependências Circulares</h3>
                            <p className="section-desc">Caminhos de arquitetura que eventualmente retornam para si mesmos (loop infinito / acoplamento forte).</p>
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th style={{ width: '80px' }}>Tamanho</th>
                                        <th>Caminho do Ciclo</th>
                                        <th style={{ width: '140px' }}>Ação</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {antipatterns.circular_dependencies.map((item, i) => {
                                        const depName = item.path[0] || `Ciclo-${i}`;
                                        return (
                                            <tr key={i}>
                                                <td>{item.length}</td>
                                                <td style={{ color: '#eab308' }}>{item.path.join(' ➔ ')}</td>
                                                <td>
                                                    <button
                                                        onClick={() => onRefactorRequest?.(depName, 'Dependência Circular')}
                                                        style={{
                                                            padding: '4px 10px',
                                                            background: 'linear-gradient(135deg, rgba(34, 211, 238, 0.15), rgba(167, 139, 250, 0.15))',
                                                            color: 'var(--accent-cyan)',
                                                            border: '1px solid rgba(34, 211, 238, 0.2)',
                                                            borderRadius: 'var(--radius-xs)',
                                                            cursor: 'pointer',
                                                            fontSize: '11px',
                                                            fontWeight: 500,
                                                            transition: 'all var(--transition-fast)',
                                                            whiteSpace: 'nowrap',
                                                        }}
                                                        onMouseEnter={(e) => {
                                                            (e.target as HTMLButtonElement).style.background = 'linear-gradient(135deg, rgba(34, 211, 238, 0.25), rgba(167, 139, 250, 0.25))';
                                                            (e.target as HTMLButtonElement).style.boxShadow = '0 0 12px rgba(34, 211, 238, 0.15)';
                                                        }}
                                                        onMouseLeave={(e) => {
                                                            (e.target as HTMLButtonElement).style.background = 'linear-gradient(135deg, rgba(34, 211, 238, 0.15), rgba(167, 139, 250, 0.15))';
                                                            (e.target as HTMLButtonElement).style.boxShadow = 'none';
                                                        }}
                                                    >
                                                        🔧 Como resolver?
                                                    </button>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                    {antipatterns.circular_dependencies.length === 0 && (
                                        <tr><td colSpan={3}>Nenhuma dependência circular detectada.</td></tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {/* Dead Code */}
                    {antipatterns && (
                        <div className="dashboard-section">
                            <h3>💀 Código Morto ou Órfão</h3>
                            <p className="section-desc">Entidades com ZERO dependências apontando para elas (que não são APIs ou Entradas Principais do sistema).</p>
                            <div className="dead-code-list" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                {antipatterns.dead_code.map((item, i) => (
                                    <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                                        <span 
                                            className="dead-code-chip" 
                                            title={`Camada: ${item.layer} | Arquivo: ${item.file}`}
                                            style={{ flex: 1 }}
                                        >
                                            {item.name}
                                        </span>
                                        <button
                                            onClick={() => onRefactorRequest?.(item.name, 'Código Morto')}
                                            style={{
                                                padding: '4px 10px',
                                                background: 'linear-gradient(135deg, rgba(34, 211, 238, 0.15), rgba(167, 139, 250, 0.15))',
                                                color: 'var(--accent-cyan)',
                                                border: '1px solid rgba(34, 211, 238, 0.2)',
                                                borderRadius: 'var(--radius-xs)',
                                                cursor: 'pointer',
                                                fontSize: '11px',
                                                fontWeight: 500,
                                                transition: 'all var(--transition-fast)',
                                                whiteSpace: 'nowrap',
                                                flexShrink: 0,
                                            }}
                                            onMouseEnter={(e) => {
                                                (e.target as HTMLButtonElement).style.background = 'linear-gradient(135deg, rgba(34, 211, 238, 0.25), rgba(167, 139, 250, 0.25))';
                                                (e.target as HTMLButtonElement).style.boxShadow = '0 0 12px rgba(34, 211, 238, 0.15)';
                                            }}
                                            onMouseLeave={(e) => {
                                                (e.target as HTMLButtonElement).style.background = 'linear-gradient(135deg, rgba(34, 211, 238, 0.15), rgba(167, 139, 250, 0.15))';
                                                (e.target as HTMLButtonElement).style.boxShadow = 'none';
                                            }}
                                        >
                                            🔧 Como resolver?
                                        </button>
                                    </div>
                                ))}
                                {antipatterns.dead_code.length === 0 && (
                                    <span style={{ color: 'var(--text-muted)' }}>Nenhum código órfão detectado.</span>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Cloud Blockers */}
                    {antipatterns && (
                        <div className="dashboard-section">
                            <h3>☁️ Bloqueadores de Nuvem</h3>
                            <p className="section-desc">Componentes com operações de disco local que impedem migração para nuvem (I/O baseado em arquivo).</p>
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Nome da Entidade</th>
                                        <th>Camada</th>
                                        <th>Arquivo</th>
                                        <th style={{ width: '140px' }}>Ação</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {antipatterns.cloud_blockers && antipatterns.cloud_blockers.map((item, i) => (
                                        <tr key={i}>
                                            <td style={{ fontWeight: 'bold', color: 'var(--text-bright)' }}>{item.name}</td>
                                            <td>{item.layer}</td>
                                            <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{item.file}</td>
                                            <td>
                                                <button
                                                    onClick={() => onRefactorRequest?.(item.name, 'Bloqueador de Nuvem')}
                                                    style={{
                                                        padding: '4px 10px',
                                                        background: 'linear-gradient(135deg, rgba(34, 211, 238, 0.15), rgba(167, 139, 250, 0.15))',
                                                        color: 'var(--accent-cyan)',
                                                        border: '1px solid rgba(34, 211, 238, 0.2)',
                                                        borderRadius: 'var(--radius-xs)',
                                                        cursor: 'pointer',
                                                        fontSize: '11px',
                                                        fontWeight: 500,
                                                        transition: 'all var(--transition-fast)',
                                                        whiteSpace: 'nowrap',
                                                    }}
                                                    onMouseEnter={(e) => {
                                                        (e.target as HTMLButtonElement).style.background = 'linear-gradient(135deg, rgba(34, 211, 238, 0.25), rgba(167, 139, 250, 0.25))';
                                                        (e.target as HTMLButtonElement).style.boxShadow = '0 0 12px rgba(34, 211, 238, 0.15)';
                                                    }}
                                                    onMouseLeave={(e) => {
                                                        (e.target as HTMLButtonElement).style.background = 'linear-gradient(135deg, rgba(34, 211, 238, 0.15), rgba(167, 139, 250, 0.15))';
                                                        (e.target as HTMLButtonElement).style.boxShadow = 'none';
                                                    }}
                                                >
                                                    🔧 Como resolver?
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                    {(!antipatterns.cloud_blockers || antipatterns.cloud_blockers.length === 0) && (
                                        <tr><td colSpan={4}>Nenhum bloqueador de nuvem detectado. Projeto está pronto para cloud! ✅</td></tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {/* Hardcoded Secrets */}
                    {antipatterns && (
                        <div className="dashboard-section">
                            <h3>🚨 Segredos Hardcoded (Crítico)</h3>
                            <p className="section-desc">Variáveis sensíveis (tokens, senhas, chaves) com valores literais chumbados no código. RISCO CRÍTICO DE SEGURANÇA!</p>
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Nome do Segredo</th>
                                        <th>Camada</th>
                                        <th>Arquivo</th>
                                        <th style={{ width: '140px' }}>Ação</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {antipatterns.hardcoded_secrets && antipatterns.hardcoded_secrets.map((item, i) => (
                                        <tr key={i} style={{ background: 'rgba(239, 68, 68, 0.05)' }}>
                                            <td style={{ fontWeight: 'bold', color: '#ef4444' }}>🚨 {item.name}</td>
                                            <td>{item.layer}</td>
                                            <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{item.file}</td>
                                            <td>
                                                <button
                                                    onClick={() => onRefactorRequest?.(item.name, 'Segredo Hardcoded')}
                                                    style={{
                                                        padding: '4px 10px',
                                                        background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(249, 115, 22, 0.2))',
                                                        color: '#ef4444',
                                                        border: '1px solid rgba(239, 68, 68, 0.4)',
                                                        borderRadius: 'var(--radius-xs)',
                                                        cursor: 'pointer',
                                                        fontSize: '11px',
                                                        fontWeight: 600,
                                                        transition: 'all var(--transition-fast)',
                                                        whiteSpace: 'nowrap',
                                                    }}
                                                    onMouseEnter={(e) => {
                                                        (e.target as HTMLButtonElement).style.background = 'linear-gradient(135deg, rgba(239, 68, 68, 0.35), rgba(249, 115, 22, 0.3))';
                                                        (e.target as HTMLButtonElement).style.boxShadow = '0 0 12px rgba(239, 68, 68, 0.3)';
                                                    }}
                                                    onMouseLeave={(e) => {
                                                        (e.target as HTMLButtonElement).style.background = 'linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(249, 115, 22, 0.2))';
                                                        (e.target as HTMLButtonElement).style.boxShadow = 'none';
                                                    }}
                                                >
                                                    🔧 Remover Agora
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                    {(!antipatterns.hardcoded_secrets || antipatterns.hardcoded_secrets.length === 0) && (
                                        <tr><td colSpan={4}>✅ Nenhum segredo hardcoded encontrado. Segurança OK!</td></tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {/* Fat Controllers */}
                    {antipatterns && (
                        <div className="dashboard-section">
                            <h3>💪 Fat Controllers (Anti-padrão API)</h3>
                            <p className="section-desc">Controladores da camada API que violam Single Responsibility Principle (complexidade &gt; 10).</p>
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Nome do Controller</th>
                                        <th>Complexidade</th>
                                        <th>Dependências (In/Out)</th>
                                        <th style={{ width: '140px' }}>Ação</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {antipatterns.fat_controllers && antipatterns.fat_controllers.map((item, i) => (
                                        <tr key={i}>
                                            <td style={{ fontWeight: 'bold', color: 'var(--text-bright)' }}>{item.name}</td>
                                            <td style={{ color: item.complexity > 15 ? '#ef4444' : '#eab308', fontWeight: 'bold' }}>
                                                {item.complexity}
                                            </td>
                                            <td>{item.in_degree} entrando / {item.out_degree} saindo</td>
                                            <td>
                                                <button
                                                    onClick={() => onRefactorRequest?.(item.name, 'Fat Controller')}
                                                    style={{
                                                        padding: '4px 10px',
                                                        background: 'linear-gradient(135deg, rgba(34, 211, 238, 0.15), rgba(167, 139, 250, 0.15))',
                                                        color: 'var(--accent-cyan)',
                                                        border: '1px solid rgba(34, 211, 238, 0.2)',
                                                        borderRadius: 'var(--radius-xs)',
                                                        cursor: 'pointer',
                                                        fontSize: '11px',
                                                        fontWeight: 500,
                                                        transition: 'all var(--transition-fast)',
                                                        whiteSpace: 'nowrap',
                                                    }}
                                                    onMouseEnter={(e) => {
                                                        (e.target as HTMLButtonElement).style.background = 'linear-gradient(135deg, rgba(34, 211, 238, 0.25), rgba(167, 139, 250, 0.25))';
                                                        (e.target as HTMLButtonElement).style.boxShadow = '0 0 12px rgba(34, 211, 238, 0.15)';
                                                    }}
                                                    onMouseLeave={(e) => {
                                                        (e.target as HTMLButtonElement).style.background = 'linear-gradient(135deg, rgba(34, 211, 238, 0.15), rgba(167, 139, 250, 0.15))';
                                                        (e.target as HTMLButtonElement).style.boxShadow = 'none';
                                                    }}
                                                >
                                                    🔧 Refatorar
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                    {(!antipatterns.fat_controllers || antipatterns.fat_controllers.length === 0) && (
                                        <tr><td colSpan={4}>Nenhum fat controller detectado. Controllers bem dimensionados! ✅</td></tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {/* Top 5 External Dependencies */}
                    {antipatterns && stats && (
                        <div className="dashboard-section">
                            <h3>📦 Top 5 Dependências Externas (SBOM)</h3>
                            <p className="section-desc">Bibliotecas e pacotes externos mais utilizados no sistema. Essencial para análise de Supply Chain Security.</p>
                            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                                {antipatterns.top_external_deps && antipatterns.top_external_deps.length > 0 ? (
                                    antipatterns.top_external_deps.map((dep, i) => (
                                        <div
                                            key={i}
                                            style={{
                                                flex: '1 1 calc(50% - 6px)',
                                                minWidth: '200px',
                                                padding: '12px',
                                                background: 'var(--bg-card)',
                                                border: '1px solid var(--border-subtle)',
                                                borderRadius: 'var(--radius-xs)',
                                            }}
                                        >
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                                                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>#{i + 1}</span>
                                                <span style={{ fontSize: '12px', background: 'rgba(79,143,247,0.15)', color: 'var(--accent-blue)', padding: '2px 8px', borderRadius: 'var(--radius-xs)' }}>
                                                    {dep.usage_count} uso(s)
                                                </span>
                                            </div>
                                            <span style={{ fontSize: '13px', color: 'var(--text-secondary)', wordBreak: 'break-word' }}>{dep.package_name}</span>
                                        </div>
                                    ))
                                ) : (
                                    <span style={{ color: 'var(--text-muted)' }}>Nenhuma dependência externa detectada.</span>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
