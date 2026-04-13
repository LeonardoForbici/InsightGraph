import { useCallback, useEffect, useMemo, useState } from 'react';
import {
    ResponsiveContainer,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    Tooltip,
    ReferenceLine,
    CartesianGrid,
} from 'recharts';
import { fetchPulseMetrics, type PulseMetrics } from '../api';

const ALERT_THRESHOLD = 80;
const TEMPERATURE_MAX = 60;

interface DashboardPulseProps {
    onClose: () => void;
}

const formatHour = (iso: string) => {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return '';
    return dt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
};

const computeRiskScore = (maxCount: number) => {
    return Math.min(100, Math.round((maxCount / TEMPERATURE_MAX) * 100));
};

const tooltipFormatter = (value: number, _name: string) => [`${value}`, 'Commits/h'];

export default function DashboardPulse({ onClose }: DashboardPulseProps) {
    const [metrics, setMetrics] = useState<PulseMetrics | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [refreshing, setRefreshing] = useState(false);

    const loadMetrics = useCallback(async () => {
        setRefreshing(true);
        try {
            const data = await fetchPulseMetrics();
            setMetrics(data);
            setError(null);
        } catch (err: any) {
            setError(err?.message ?? 'Erro ao buscar métricas.');
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, []);

    useEffect(() => {
        loadMetrics();
        const interval = setInterval(loadMetrics, 30000);
        return () => clearInterval(interval);
    }, [loadMetrics]);

    const chartData = useMemo(() => {
        if (!metrics) return [];
        return metrics.commits_per_hour.map((bucket) => ({
            ...bucket,
            label: formatHour(bucket.start),
        }));
    }, [metrics]);

    const maxCount = useMemo(() => {
        return chartData.reduce((max, bucket) => Math.max(max, bucket.count), 0);
    }, [chartData]);

    const riskScore = useMemo(() => computeRiskScore(maxCount), [maxCount]);

    const hotspots = useMemo(() => {
        return [...chartData]
            .sort((a, b) => b.count - a.count)
            .slice(0, 3);
    }, [chartData]);

    const alerts = useMemo(() => {
        const list: string[] = [];
        if (riskScore >= ALERT_THRESHOLD) {
            list.push(`Risk score estimado superior a ${ALERT_THRESHOLD} (hora mais quente com ${maxCount} commits).`);
        }
        if (metrics && metrics.active_developers.count >= 10) {
            list.push('Mais de 10 desenvolvedores ativos nos últimos 15 minutos.');
        }
        return list;
    }, [riskScore, metrics, maxCount]);

    const temperaturePercent = Math.min(1, maxCount / TEMPERATURE_MAX);
    const temperatureColor = `hsl(${(1 - temperaturePercent) * 120}, 75%, 50%)`;

    return (
        <div className="dashboard-pulse-shell" role="dialog" aria-modal="true">
            <div className="dashboard-pulse-card">
                <header className="dashboard-pulse-header">
                    <div>
                        <h2>Dashboard de Pulso</h2>
                        <p>
                            {metrics
                                ? `Última atualização em ${new Date(metrics.last_updated).toLocaleString('pt-BR')}`
                                : 'Carregando métricas...'}
                        </p>
                    </div>
                    <div className="dashboard-pulse-header-actions">
                        <button
                            type="button"
                            className="btn btn-secondary"
                            onClick={loadMetrics}
                            disabled={refreshing}
                        >
                            {refreshing ? 'Atualizando...' : 'Atualizar'}
                        </button>
                        <button type="button" className="btn btn-ghost" onClick={onClose} aria-label="Fechar dashboard">
                            ✕
                        </button>
                    </div>
                </header>

                <div className="dashboard-pulse-metric-grid">
                    <div className="dashboard-pulse-metric">
                        <span className="dashboard-pulse-metric-label">Commits (últimas 24h)</span>
                        <strong>{metrics?.total_commits_24h ?? '—'}</strong>
                    </div>
                    <div className="dashboard-pulse-metric">
                        <span className="dashboard-pulse-metric-label">Desenvolvedores ativos (15m)</span>
                        <strong>{metrics?.active_developers.count ?? '—'}</strong>
                    </div>
                    <div className="dashboard-pulse-metric">
                        <span className="dashboard-pulse-metric-label">Temperatura do código</span>
                        <strong>{riskScore}%</strong>
                        <div className="temperature-bar">
                            <span
                                className="temperature-bar__fill"
                                style={{ width: `${temperaturePercent * 100}%`, background: temperatureColor }}
                            />
                        </div>
                    </div>
                </div>

                <section className="dashboard-pulse-chart">
                    <ResponsiveContainer width="100%" height={280}>
                        <BarChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
                            <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                            <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                            <Tooltip formatter={tooltipFormatter} labelFormatter={(label) => `Hora: ${label}`} />
                            <ReferenceLine y={Math.round(maxCount * 0.75)} stroke="#f97316" strokeDasharray="3 3" label={{ value: 'Hotspot', position: 'top', fill: '#f97316' }} />
                            <Bar dataKey="count" fill="#38bdf8">
                                {/* optional */}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </section>

                <section className="dashboard-pulse-details">
                    <div className="dashboard-pulse-panel">
                        <h3>Hotspots</h3>
                        {hotspots.length === 0 ? (
                            <p className="muted">Ainda não há dados suficientes.</p>
                        ) : (
                            <ul>
                                {hotspots.map((bucket) => (
                                    <li key={bucket.start}>
                                        <span>{bucket.label || 'Hora desconhecida'}</span>
                                        <strong>{bucket.count} commits</strong>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                    <div className="dashboard-pulse-panel">
                        <h3>Alertas </h3>
                        {error && <p className="alert alert-error">{error}</p>}
                        {!error && alerts.length === 0 && <p className="muted">Nenhum alerta crítico no momento.</p>}
                        <ul>
                            {alerts.map((message) => (
                                <li key={message} className="alert-item">
                                    {message}
                                </li>
                            ))}
                        </ul>
                    </div>
                    <div className="dashboard-pulse-panel">
                        <h3>Desenvolvedores ativos</h3>
                        {metrics?.active_developers.names.length ? (
                            <ul className="active-developers">
                                {metrics.active_developers.names.slice(0, 6).map((author) => (
                                    <li key={author}>{author}</li>
                                ))}
                                {metrics.active_developers.names.length > 6 && (
                                    <li className="muted">+{metrics.active_developers.names.length - 6} outros</li>
                                )}
                            </ul>
                        ) : (
                            <p className="muted-empty">Sem atividade recente.</p>
                        )}
                    </div>
                </section>

                {loading && (
                    <div className="dashboard-pulse-loading">
                        <span>Carregando métricas...</span>
                    </div>
                )}
            </div>
        </div>
    );
}
