import type { ImpactData, BlastRadiusData, GraphNode } from '../api';

interface NodeDetailProps {
    node: GraphNode | null;
    impact: ImpactData | null;
    blastRadius?: BlastRadiusData | null;
    onClose: () => void;
}

function getTypeIcon(labels: string[]): { icon: string; bg: string; color: string } {
    if (labels.includes('Java_Class')) return { icon: '☕', bg: 'rgba(249,115,22,0.12)', color: '#fb923c' };
    if (labels.includes('Java_Method')) return { icon: 'ƒ', bg: 'rgba(249,115,22,0.08)', color: '#fdba74' };
    if (labels.includes('TS_Component')) return { icon: '⚛', bg: 'rgba(79,143,247,0.12)', color: '#60a5fa' };
    if (labels.includes('TS_Function')) return { icon: 'λ', bg: 'rgba(79,143,247,0.08)', color: '#93c5fd' };
    if (labels.includes('SQL_Table')) return { icon: '🗄', bg: 'rgba(52,211,153,0.12)', color: '#34d399' };
    if (labels.includes('SQL_Procedure')) return { icon: '⚙', bg: 'rgba(52,211,153,0.08)', color: '#6ee7b7' };
    if (labels.includes('Mobile_Component')) return { icon: '📱', bg: 'rgba(167,139,250,0.12)', color: '#a78bfa' };
    return { icon: '◇', bg: 'rgba(139,147,176,0.08)', color: '#8b93b0' };
}

export default function NodeDetail({ node, impact, blastRadius, onClose }: NodeDetailProps) {
    if (!node) return null;

    const mainLabel = node.labels.find((l) => l !== 'Entity') || 'Entity';
    const typeInfo = getTypeIcon(node.labels);

    return (
        <div className="node-detail">
            <div className="node-detail-header">
                <div className="node-detail-header-left">
                    <div
                        className="node-detail-type-badge"
                        style={{ background: typeInfo.bg, color: typeInfo.color }}
                    >
                        {typeInfo.icon}
                    </div>
                    <div>
                        <div className="node-detail-title">{node.name}</div>
                        <div className="node-detail-subtitle">{mainLabel.replace('_', ' ')}</div>
                    </div>
                </div>
                <span className="node-detail-close" onClick={onClose}>
                    ✕
                </span>
            </div>

            {node.project && (
                <div className="node-detail-row">
                    <span className="node-detail-label">Projeto</span>
                    <span className="node-detail-value">{node.project}</span>
                </div>
            )}
            {node.file && (
                <div className="node-detail-row">
                    <span className="node-detail-label">Arquivo</span>
                    <span className="node-detail-value" title={node.file}>
                        {node.file}
                    </span>
                </div>
            )}
            {node.layer && (
                <div className="node-detail-row">
                    <span className="node-detail-label">Camada</span>
                    <span className="node-detail-value">{node.layer}</span>
                </div>
            )}
            {node.decorators && (
                <div className="node-detail-row">
                    <span className="node-detail-label">Decorators</span>
                    <span className="node-detail-value">{node.decorators}</span>
                </div>
            )}
            {node.loc !== undefined && (
                <div className="node-detail-row" style={{ marginTop: 8 }}>
                    <span className="node-detail-label">Linhas de Código</span>
                    <span className="node-detail-value">{node.loc}</span>
                </div>
            )}
            {node.complexity !== undefined && (
                <div className="node-detail-row">
                    <span className="node-detail-label">Complexidade</span>
                    <span className="node-detail-value">
                        {node.complexity}
                        {node.complexity > 10 && <span style={{ marginLeft: 6, color: '#ef4444' }}>⚠️ Alta</span>}
                    </span>
                </div>
            )}
            {blastRadius && (
                <div className="node-detail-row">
                    <span className="node-detail-label">Score de Risco Multihop</span>
                    <span className="node-detail-value" style={{ 
                        color: blastRadius.risk_score > 50 ? '#ef4444' : blastRadius.risk_score > 20 ? '#eab308' : '#22c55e',
                        fontWeight: 'bold'
                    }}>
                        {blastRadius.risk_score}/100
                        <span style={{ fontSize: '0.8em', marginLeft: 6, color: 'var(--text-muted)', fontWeight: 'normal' }}>
                            ({(blastRadius.nodes || []).length} nós acoplados)
                        </span>
                    </span>
                </div>
            )}

            {impact && (
                <>
                    {(impact.upstream || []).length > 0 && (
                        <div className="impact-section">
                            <div className="impact-title upstream">
                                ↑ Origem (Upstream)
                                <span className="impact-count upstream">{(impact.upstream || []).length}</span>
                            </div>
                            <div className="impact-list">
                                {(impact.upstream || []).map((item, i) => (
                                    <div key={i} className="impact-item">
                                        <span className="rel-badge">{item.rel_type}</span>
                                        {item.name}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                    {(impact.downstream || []).length > 0 && (
                        <div className="impact-section">
                            <div className="impact-title downstream">
                                ↓ Destino (Downstream)
                                <span className="impact-count downstream">{(impact.downstream || []).length}</span>
                            </div>
                            <div className="impact-list">
                                {(impact.downstream || []).map((item, i) => (
                                    <div key={i} className="impact-item">
                                        <span className="rel-badge">{item.rel_type}</span>
                                        {item.name}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                    {(impact.upstream || []).length === 0 && (impact.downstream || []).length === 0 && (
                        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 14, textAlign: 'center' }}>
                            Nenhuma conexão encontrada para este componente
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
