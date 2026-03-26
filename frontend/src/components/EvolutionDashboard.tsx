import { useEffect, useMemo, useState } from 'react';
import {
    fetchEvolutionSummary,
    fetchHistory,
    type EvolutionSummary,
    type HistorySnapshot,
} from '../api';

const WIDTH = 760;
const HEIGHT = 320;
const PADDING = 36;
const WEEKS = 12;
const DAYS_IN_WEEK = 7;

const formatDate = (value: Date) => {
    return new Intl.DateTimeFormat('pt-BR', {
        day: '2-digit',
        month: 'short',
    }).format(value);
};

const computeRiskScore = (entry: EvolutionSummary['series'][number]) => {
    return entry?.risk_score ?? entry?.god_classes * 5 + entry?.circular_deps * 5 + (entry?.dead_code ?? 0);
};

const heatmapColor = (value: number | null) => {
    if (value === null) return 'rgba(255,255,255,0.04)';
    if (value > 80) return '#ef4444';
    if (value > 60) return '#fb923c';
    if (value > 40) return '#facc15';
    if (value > 20) return '#34d399';
    if (value > 0) return '#60a5fa';
    return 'rgba(255,255,255,0.08)';
};

const labelForTrend = (delta: number | undefined) => {
    if (delta === undefined) return '0%';
    return `${delta > 0 ? '+' : ''}${delta}%`;
};

type ChartPoint = {
    entry: EvolutionSummary['series'][number];
    x: number;
    yNodes: number;
    yEdges: number;
    yRisk: number;
    yCall: number;
    riskValue: number;
};

type ChartData = {
    points: ChartPoint[];
    nodesPath: string;
    edgesPath: string;
    riskPath: string;
    callPath: string;
};

const getTrendCards = (
    summary: EvolutionSummary,
    latestPoint: ChartPoint | null,
    previousPoint: ChartPoint | null,
) => {
    if (!latestPoint) return [];
    const godClasses = latestPoint.entry.god_classes ?? 0;
    const prevGod = previousPoint?.entry.god_classes ?? godClasses;
    const godDelta = godClasses - prevGod;
    const callRate = latestPoint.entry.call_resolution_rate ?? 0;
    return [
        {
            title: 'Débito Técnico',
            label: labelForTrend(summary.trend.risk_delta),
            description: 'Delta de risco (meta < 0)',
            icon: summary.trend.risk_delta >= 0 ? '↑' : '↓',
            accent: summary.trend.risk_delta >= 0 ? '#ef4444' : '#22c55e',
        },
        {
            title: 'God Classes',
            label: `${godClasses}`,
            description: `${godDelta >= 0 ? '+' : ''}${godDelta} vs scan anterior`,
            icon: godDelta > 0 ? '↑' : godDelta < 0 ? '↓' : '→',
            accent: '#facc15',
        },
        {
            title: 'Taxa de Resolução',
            label: `${callRate.toFixed(1)}%`,
            description: 'Meta > 70%',
            icon: callRate >= 70 ? '✔' : '!',
            accent: callRate >= 70 ? '#22c55e' : '#ef4444',
        },
    ];
};

export default function EvolutionDashboard() {
    const [summary, setSummary] = useState<EvolutionSummary | null>(null);
    const [history, setHistory] = useState<HistorySnapshot[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedIdx, setSelectedIdx] = useState<number | null>(null);

    useEffect(() => {
        Promise.all([fetchEvolutionSummary(20), fetchHistory()])
            .then(([summaryData, historyData]) => {
                setSummary(summaryData);
                setHistory(historyData || []);
                setSelectedIdx(summaryData.series.length ? summaryData.series.length - 1 : null);
            })
            .catch((err) => {
                console.error('Failed to load evolution dashboard data', err);
            })
            .finally(() => setLoading(false));
    }, []);

    const series = useMemo(() => summary?.series ?? [], [summary]);
    const historyMap = useMemo(() => {
        const map = new Map<string, number>();
        history.forEach((snapshot) => {
            const dateKey = snapshot.timestamp.slice(0, 10);
            const risk = (snapshot.god_classes * 5) + (snapshot.circular_deps * 5) + snapshot.dead_code;
            map.set(dateKey, risk);
        });
        return map;
    }, [history]);

    const heatmapCells = useMemo(() => {
        const cells: Array<{ date: Date; value: number | null }> = [];
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        for (let week = WEEKS - 1; week >= 0; week--) {
            for (let day = 0; day < DAYS_IN_WEEK; day++) {
                const cellDate = new Date(today);
                cellDate.setDate(today.getDate() - (week * DAYS_IN_WEEK + (DAYS_IN_WEEK - 1 - day)));
                const key = cellDate.toISOString().slice(0, 10);
                cells.push({ date: cellDate, value: historyMap.get(key) ?? null });
            }
        }
        return cells;
    }, [historyMap]);

    const chartData = useMemo<ChartData | null>(() => {
        if (!series.length) return null;
        const nodesMax = Math.max(...series.map((entry) => entry.total_nodes), 1);
        const edgesMax = Math.max(...series.map((entry) => entry.total_edges), 1);
        const riskMax = Math.max(...series.map((entry) => computeRiskScore(entry)), 1);
        const callMax = 100;

        const step = (WIDTH - PADDING * 2) / Math.max(series.length - 1, 1);
        const points = series.map((entry, index) => {
            const x = PADDING + index * step;
            const yNodes = HEIGHT - PADDING - ((entry.total_nodes / nodesMax) * (HEIGHT - PADDING * 2));
            const yEdges = HEIGHT - PADDING - ((entry.total_edges / edgesMax) * (HEIGHT - PADDING * 2));
            const riskValue = computeRiskScore(entry);
            const yRisk = HEIGHT - PADDING - ((riskValue / riskMax) * (HEIGHT - PADDING * 2));
            const callRes = entry.call_resolution_rate ?? 0;
            const yCall = HEIGHT - PADDING - ((callRes / callMax) * (HEIGHT - PADDING * 2));
            return {
                entry,
                x,
                yNodes,
                yEdges,
                yRisk,
                yCall,
                riskValue,
            };
        });
        const nodesPath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.yNodes}`).join(' ');
        const edgesPath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.yEdges}`).join(' ');
        const riskPath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.yRisk}`).join(' ');
        const callPath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.yCall}`).join(' ');
        return {
            points,
            nodesPath,
            edgesPath,
            riskPath,
            callPath,
        };
    }, [series]);

    const resolvedIndex = selectedIdx ?? (chartData ? chartData.points.length - 1 : null);
    const selectedPoint = resolvedIndex !== null && chartData ? chartData.points[resolvedIndex] : null;
    const previousPoint = resolvedIndex !== null && resolvedIndex > 0 && chartData ? chartData.points[resolvedIndex - 1] : chartData?.points?.at(-2) ?? null;
    const latestPoint = chartData?.points?.at(-1) ?? null;
    const trendCards = useMemo(() => {
        if (!summary) return [];
        return getTrendCards(summary, latestPoint, previousPoint);
    }, [summary, latestPoint, previousPoint]);

    const diffLines = selectedPoint && previousPoint
        ? {
            nodes: selectedPoint.entry.total_nodes - previousPoint.entry.total_nodes,
            edges: selectedPoint.entry.total_edges - previousPoint.entry.total_edges,
            risk: selectedPoint.riskValue - previousPoint.riskValue,
            call: (selectedPoint.entry.call_resolution_rate ?? 0) - (previousPoint.entry.call_resolution_rate ?? 0),
        }
        : null;

    if (loading) {
        return (
            <div className="evo-dashboard">
                <div className="dashboard-section">
                    <div className="loading-spinner" />
                    <p style={{ color: 'var(--text-muted)' }}>Carregando métricas evolutivas...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="evo-dashboard">
            <div className="evo-cards">
                {trendCards.map((card) => (
                    <div key={card.title} className="evo-card">
                        <div className="evo-card-title">
                            <span>{card.title}</span>
                            <span className="evo-card-icon">{card.icon}</span>
                        </div>
                        <div className="evo-card-value" style={{ color: card.accent }}>
                            {card.label}
                        </div>
                        <div className="evo-card-desc">{card.description}</div>
                    </div>
                ))}
            </div>

            {chartData && (
                <div className="evo-chart-section">
                    <div className="chart-header">
                        <div>
                            <h3>Evolution Line</h3>
                            <p className="section-desc">Eixo Y1 = nós/arestas · Y2 = risco/taxa de resolução</p>
                        </div>
                        <span className="chart-callout">Clique num scan para ver o diff completo</span>
                    </div>
                    <div className="chart-wrapper">
                        <svg width={WIDTH} height={HEIGHT} className="evo-chart-svg">
                            {[0.25, 0.5, 0.75, 1].map((ratio) => {
                                const y = PADDING + ratio * (HEIGHT - PADDING * 2);
                                return (
                                    <line
                                        key={`grid-${ratio}`}
                                        x1={PADDING}
                                        y1={y}
                                        x2={WIDTH - PADDING}
                                        y2={y}
                                        stroke="rgba(255,255,255,0.05)"
                                        strokeDasharray="4 4"
                                    />
                                );
                            })}
                            <path d={chartData.nodesPath} fill="none" stroke="#60a5fa" strokeWidth="2.6" />
                            <path d={chartData.edgesPath} fill="none" stroke="#a78bfa" strokeWidth="2" strokeDasharray="3 3" />
                            <path d={chartData.riskPath} fill="none" stroke="#ef4444" strokeWidth="2.2" strokeDasharray="4 4" />
                            <path d={chartData.callPath} fill="none" stroke="#22c55e" strokeWidth="2.2" strokeDasharray="6 4" />
                            {chartData.points.map((p, idx) => (
                                <g key={`point-${idx}`}>
                                    <circle
                                        cx={p.x}
                                        cy={p.yNodes}
                                        r={selectedIdx === idx ? 6 : 4}
                                        fill={selectedIdx === idx ? '#60a5fa' : '#0c0f1f'}
                                        stroke="#60a5fa"
                                        strokeWidth={selectedIdx === idx ? 3 : 2}
                                        style={{ cursor: 'pointer' }}
                                        onClick={() => setSelectedIdx(idx)}
                                    >
                                        <title>
                                            {new Date(p.entry.timestamp).toLocaleString()}&#10;
                                            Nós: {p.entry.total_nodes}&#10;
                                            Arestas: {p.entry.total_edges}&#10;
                                            Risco: {p.riskValue}&#10;
                                            {p.entry.call_resolution_rate ?? 0}% resolução
                                        </title>
                                    </circle>
                                </g>
                            ))}
                        </svg>
                    </div>
                    {selectedPoint && (
                        <div className="chart-selected-info">
                            <strong>Diff do Scan ({new Date(selectedPoint.entry.timestamp).toLocaleString()})</strong>
                            <p style={{ margin: '4px 0', color: 'var(--text-muted)' }}>
                                {selectedPoint.entry.total_nodes} nós · {selectedPoint.entry.total_edges} arestas · risco {selectedPoint.riskValue} · taxa{' '}
                                {(selectedPoint.entry.call_resolution_rate ?? 0).toFixed(1)}%
                            </p>
                            {diffLines && (
                                <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                                    Mudança vs scan anterior: {diffLines.nodes >= 0 ? '+' : ''}
                                    {diffLines.nodes} nós, {diffLines.edges >= 0 ? '+' : ''}
                                    {diffLines.edges} arestas, risco {diffLines.risk >= 0 ? '+' : ''}
                                    {diffLines.risk}, taxa {diffLines.call >= 0 ? '+' : ''}
                                    {diffLines.call.toFixed(1)}%
                                </p>
                            )}
                        </div>
                    )}
                </div>
            )}

            <div className="evo-heatmap">
                <div className="heatmap-header">
                    <span>Heatmap de Scans (últimas {WEEKS} semanas)</span>
                    <span className="heatmap-legend">Risco acumulado</span>
                </div>
                <div className="heatmap-grid">
                    {heatmapCells.map((cell, idx) => (
                        <div
                            key={`heat-${idx}`}
                            className="heatmap-cell"
                            style={{ background: heatmapColor(cell.value) }}
                            title={`${formatDate(cell.date)} · risco ${cell.value ?? 'sem scan'}`}
                        />
                    ))}
                </div>
            </div>
        </div>
    );
}
