import { useEffect, useState, useMemo } from 'react';
import { fetchHistory, type HistorySnapshot } from '../api';

export default function EvolutionTimeline() {
    const [history, setHistory] = useState<HistorySnapshot[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchHistory().then(data => {
            setHistory(data || []);
            setLoading(false);
        });
    }, []);

    const chartData = useMemo(() => {
        if (!history || history.length === 0) return null;
        
        // Take up to last 15 scans
        const data = history.slice(-15);
        
        const maxNodes = Math.max(...data.map(d => d.total_nodes), 1);
        const maxRisk = Math.max(...data.map(d => (d.god_classes * 5) + (d.circular_deps * 10) + d.dead_code), 1);
        
        const width = 600;
        const height = 180;
        const padding = 20;
        
        const xStep = (width - padding * 2) / Math.max(data.length - 1, 1);
        
        const points = data.map((d, i) => {
            const risk = (d.god_classes * 5) + (d.circular_deps * 10) + d.dead_code;
            return {
                x: padding + i * xStep,
                yNodes: height - padding - ((d.total_nodes / maxNodes) * (height - padding * 2)),
                yRisk: height - padding - ((risk / maxRisk) * (height - padding * 2)),
                nodes: d.total_nodes,
                riskScore: risk,
                date: new Date(d.timestamp).toLocaleDateString() + ' ' + new Date(d.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})
            };
        });

        const nodePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.yNodes}`).join(' ');
        const riskPath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.yRisk}`).join(' ');

        return { points, nodePath, riskPath, width, height };
    }, [history]);

    if (loading) return <div style={{ color: 'var(--text-muted)' }}>Loading timeline...</div>;
    
    if (!chartData || chartData.points.length < 2) {
        return (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem', fontStyle: 'italic', padding: 16, background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                Not enough historical data to construct a timeline. Try running multiple scans over time to see the architectural evolution.
            </div>
        );
    }

    return (
        <div style={{ background: 'rgba(12, 16, 36, 0.4)', border: '1px solid var(--border-color)', borderRadius: 8, padding: 20 }}>
            <h4 style={{ margin: '0 0 16px', color: 'var(--text-bright)' }}>Architectural Evolution (Last Scans)</h4>
            
            <div style={{ position: 'relative', width: '100%', overflowX: 'auto' }}>
                <svg width={chartData.width} height={chartData.height} style={{ overflow: 'visible' }}>
                    {/* Grid lines */}
                    {[0, 0.5, 1].map(ratio => {
                        const y = 20 + ratio * (chartData.height - 40);
                        return <line key={ratio} x1={20} y1={y} x2={chartData.width - 20} y2={y} stroke="rgba(255,255,255,0.05)" strokeDasharray="4 4" />;
                    })}

                    {/* Node Count Line */}
                    <path d={chartData.nodePath} fill="none" stroke="#60a5fa" strokeWidth="2.5" />
                    
                    {/* Risk Score Line */}
                    <path d={chartData.riskPath} fill="none" stroke="#ef4444" strokeWidth="2.5" />

                    {/* Points & Tooltips */}
                    {chartData.points.map((p, i) => (
                        <g key={i}>
                            <circle cx={p.x} cy={p.yNodes} r={4} fill="#60a5fa" stroke="#000" strokeWidth={2}>
                                <title>{p.date}&#10;Total Nodes: {p.nodes}</title>
                            </circle>
                            <circle cx={p.x} cy={p.yRisk} r={4} fill="#ef4444" stroke="#000" strokeWidth={2}>
                                <title>{p.date}&#10;Risk Score: {p.riskScore}</title>
                            </circle>
                        </g>
                    ))}
                </svg>
            </div>
            
            <div style={{ display: 'flex', gap: 24, marginTop: 16, fontSize: '0.85rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ width: 12, height: 12, borderRadius: 2, background: '#60a5fa' }} />
                    <span style={{ color: 'var(--text-muted)' }}>Total Size (Nodes)</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ width: 12, height: 12, borderRadius: 2, background: '#ef4444' }} />
                    <span style={{ color: 'var(--text-muted)' }}>Tech Debt Risk Score</span>
                </div>
            </div>
        </div>
    );
}
