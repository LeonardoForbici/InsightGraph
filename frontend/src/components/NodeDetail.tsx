import { useState, useCallback } from 'react';
import type { ImpactData, BlastRadiusData, GraphNode } from '../api';
import { fetchFileContent, explainComponent } from '../api';

interface NodeDetailProps {
    node: GraphNode | null;
    impact: ImpactData | null;
    blastRadius?: BlastRadiusData | null;
    onClose: () => void;
    onViewUsages?: (nodeKey: string, nodeName: string) => void;
    onQuickImpactScenario?: (scenario: 'delete' | 'signature' | 'data_type', node: GraphNode) => void;
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

export default function NodeDetail({ node, impact, blastRadius, onClose, onViewUsages, onQuickImpactScenario }: NodeDetailProps) {
    // Todos os hooks DEVEM ser chamados ANTES de qualquer condicional
    const [activeTab, setActiveTab] = useState<'details' | 'code'>('details');
    const [fileContent, setFileContent] = useState<string>('');
    const [loadingCode, setLoadingCode] = useState(false);
    const [explanation, setExplanation] = useState<string>('');
    const [explaining, setExplaining] = useState(false);

    const handleLoadCode = useCallback(async () => {
        if (!node?.file || fileContent) return;
        setLoadingCode(true);
        try {
            const res = await fetchFileContent(node.file, node.project);
            setFileContent(res.content);
            setActiveTab('code');
        } catch (err) {
            console.error('Failed to load code:', err);
            alert('Não foi possível carregar o código do arquivo.');
        } finally {
            setLoadingCode(false);
        }
    }, [node?.file, node?.project, fileContent]);

    const handleExplainComponent = useCallback(async () => {
        if (!fileContent || explaining) return;
        setExplaining(true);
        try {
            const res = await explainComponent(fileContent);
            setExplanation(res.answer);
        } catch (err) {
            console.error('Failed to explain component:', err);
            alert('Não foi possível gerar a explicação da IA.');
        } finally {
            setExplaining(false);
        }
    }, [fileContent, explaining]);

    // Condicional APÓS todos os hooks
    if (!node) return null;

    const mainLabel = node.labels.find((l) => l !== 'Entity') || 'Entity';
    const typeInfo = getTypeIcon(node.labels);
    const methodLikeLabels = new Set(['Java_Method', 'TS_Function', 'API_Endpoint', 'SQL_Procedure']);
    const canViewUsages = Boolean(
        onViewUsages &&
        node.namespace_key &&
        !node.namespace_key.startsWith('cluster:') &&
        node.labels?.some((l) => methodLikeLabels.has(l)),
    );
    const upstreamCount = impact?.upstream?.length || 0;
    const downstreamCount = impact?.downstream?.length || 0;
    const blastNodeCount = blastRadius?.nodes?.length || 0;
    const quickImpact = upstreamCount + downstreamCount + blastNodeCount;

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

            {/* Tab Navigation */}
            {node.file && (
                <div style={{ display: 'flex', gap: 8, padding: '8px 0', borderBottom: '1px solid var(--border-subtle)', marginBottom: 12 }}>
                    <button
                        onClick={() => setActiveTab('details')}
                        style={{
                            padding: '6px 12px',
                            background: activeTab === 'details' ? 'rgba(79,143,247,0.15)' : 'transparent',
                            color: activeTab === 'details' ? 'var(--accent-blue)' : 'var(--text-secondary)',
                            border: `1px solid ${activeTab === 'details' ? 'var(--accent-blue)' : 'transparent'}`,
                            borderRadius: 'var(--radius-xs)',
                            cursor: 'pointer',
                            fontSize: 12,
                            fontWeight: 500,
                            transition: 'all var(--transition-fast)',
                        }}
                    >
                        Detalhes
                    </button>
                    <button
                        onClick={() => setActiveTab('code')}
                        style={{
                            padding: '6px 12px',
                            background: activeTab === 'code' ? 'rgba(79,143,247,0.15)' : 'transparent',
                            color: activeTab === 'code' ? 'var(--accent-blue)' : 'var(--text-secondary)',
                            border: `1px solid ${activeTab === 'code' ? 'var(--accent-blue)' : 'transparent'}`,
                            borderRadius: 'var(--radius-xs)',
                            cursor: 'pointer',
                            fontSize: 12,
                            fontWeight: 500,
                            transition: 'all var(--transition-fast)',
                        }}
                    >
                        Código
                    </button>
                </div>
            )}

            {/* Details Tab */}
            {activeTab === 'details' && (
                <>
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
                    {node.labels && node.labels.includes('Sensitive_Data') && (
                        <div className="node-detail-row" style={{ marginTop: 8, padding: '8px 12px', background: 'rgba(239, 68, 68, 0.08)', borderRadius: 'var(--radius-xs)', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
                            <span style={{ color: '#ef4444', fontWeight: 600, fontSize: '13px' }}>🔐 Dados Sensíveis (GDPR/LGPD)</span>
                            <span style={{ display: 'block', color: 'var(--text-secondary)', fontSize: '12px', marginTop: 4 }}>Este nó contém informações sensíveis. Requere conformidade de segurança.</span>
                        </div>
                    )}
                    {node.decorators && (
                        <div className="node-detail-row">
                            <span className="node-detail-label">Decorators</span>
                            <span className="node-detail-value">{node.decorators}</span>
                        </div>
                    )}
                    {canViewUsages && (
                        <button
                            className="btn btn-secondary"
                            style={{ width: '100%', margin: '8px 0 10px', fontSize: 12 }}
                            onClick={() => onViewUsages?.(node.namespace_key, node.name)}
                        >
                            🔍 Ver usos do método
                        </button>
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
                    {typeof node.hotspot_score === 'number' && (
                        <div className="node-detail-row">
                            <span className="node-detail-label">Hotspot Score</span>
                            <span className="node-detail-value" style={{ color: node.hotspot_score > 70 ? '#ef4444' : node.hotspot_score > 40 ? '#f59e0b' : '#22c55e' }}>
                                {node.hotspot_score.toFixed(2)}
                            </span>
                        </div>
                    )}
                    {typeof node.git_churn === 'number' && (
                        <div className="node-detail-row">
                            <span className="node-detail-label">Git Churn</span>
                            <span className="node-detail-value">{node.git_churn}</span>
                        </div>
                    )}
                    {(typeof node.wmc === 'number' || typeof node.cbo === 'number' || typeof node.rfc === 'number' || typeof node.lcom === 'number') && (
                        <>
                            <div className="node-detail-row">
                                <span className="node-detail-label">CK WMC</span>
                                <span className="node-detail-value">{node.wmc ?? 0}</span>
                            </div>
                            <div className="node-detail-row">
                                <span className="node-detail-label">CK CBO</span>
                                <span className="node-detail-value">{node.cbo ?? 0}</span>
                            </div>
                            <div className="node-detail-row">
                                <span className="node-detail-label">CK RFC</span>
                                <span className="node-detail-value">{node.rfc ?? 0}</span>
                            </div>
                            <div className="node-detail-row">
                                <span className="node-detail-label">CK LCOM</span>
                                <span className="node-detail-value">{typeof node.lcom === 'number' ? node.lcom.toFixed(2) : '0.00'}</span>
                            </div>
                        </>
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

                    <div style={{
                        marginTop: 10,
                        padding: '10px 12px',
                        border: '1px solid rgba(148,163,184,0.22)',
                        borderRadius: 8,
                        background: 'rgba(15,23,42,0.38)',
                    }}>
                        <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>Leitura Rápida de Impacto</div>
                        <div style={{ fontSize: 11, opacity: 0.9, lineHeight: 1.45 }}>
                            Se você apagar este nó, a alteração pode atingir cerca de <b>{quickImpact}</b> dependências
                            (upstream: {upstreamCount}, downstream: {downstreamCount}, multihop: {blastNodeCount}).
                        </div>
                        <div style={{ fontSize: 11, opacity: 0.75, marginTop: 6 }}>
                            Se você alterar assinatura/parâmetro aqui, priorize revisar primeiro os nós downstream.
                        </div>
                        {onQuickImpactScenario && (
                            <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
                                <button
                                    className="btn btn-secondary"
                                    style={{ fontSize: 11, padding: '5px 8px' }}
                                    onClick={() => onQuickImpactScenario('delete', node)}
                                    title="Destaca o impacto típico de remoção deste nó"
                                >
                                    Se apagar
                                </button>
                                <button
                                    className="btn btn-secondary"
                                    style={{ fontSize: 11, padding: '5px 8px' }}
                                    onClick={() => onQuickImpactScenario('signature', node)}
                                    title="Destaca impacto em contratos/chamadas"
                                >
                                    Se mudar assinatura
                                </button>
                                <button
                                    className="btn btn-secondary"
                                    style={{ fontSize: 11, padding: '5px 8px' }}
                                    onClick={() => onQuickImpactScenario('data_type', node)}
                                    title="Destaca impacto em tipos e fluxo de dados"
                                >
                                    Se mudar tipo
                                </button>
                            </div>
                        )}
                    </div>

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
                </>
            )}

            {/* Code Tab */}
            {activeTab === 'code' && (
                <>
                    {!fileContent && (
                        <button
                            onClick={handleLoadCode}
                            disabled={loadingCode}
                            style={{
                                width: '100%',
                                padding: '8px 12px',
                                background: 'var(--bg-card)',
                                color: 'var(--text-primary)',
                                border: '1px solid var(--border-subtle)',
                                borderRadius: 'var(--radius-xs)',
                                cursor: loadingCode ? 'not-allowed' : 'pointer',
                                fontSize: 12,
                                fontWeight: 500,
                                opacity: loadingCode ? 0.6 : 1,
                                transition: 'all var(--transition-fast)',
                            }}
                        >
                            {loadingCode ? 'Carregando...' : '📄 Ver Código'}
                        </button>
                    )}

                    {fileContent && (
                        <>
                            <pre style={{
                                background: 'var(--bg-card)',
                                color: 'var(--text-secondary)',
                                padding: '12px',
                                borderRadius: 'var(--radius-xs)',
                                fontSize: '11px',
                                lineHeight: '1.4',
                                maxHeight: '300px',
                                overflowY: 'auto',
                                fontFamily: 'var(--font-mono)',
                                marginBottom: 12,
                                border: '1px solid var(--border-subtle)',
                            }}>
                                <code>{fileContent}</code>
                            </pre>

                            <button
                                onClick={handleExplainComponent}
                                disabled={explaining}
                                style={{
                                    width: '100%',
                                    padding: '8px 12px',
                                    background: 'linear-gradient(135deg, rgba(34, 211, 238, 0.15), rgba(167, 139, 250, 0.15))',
                                    color: 'var(--accent-cyan)',
                                    border: '1px solid rgba(34, 211, 238, 0.2)',
                                    borderRadius: 'var(--radius-xs)',
                                    cursor: explaining ? 'not-allowed' : 'pointer',
                                    fontSize: 12,
                                    fontWeight: 500,
                                    opacity: explaining ? 0.6 : 1,
                                    transition: 'all var(--transition-fast)',
                                    marginBottom: explanation ? 12 : 0,
                                }}
                            >
                                {explaining ? '⏳ Explicando...' : '💡 Explicar Componente'}
                            </button>

                            {explanation && (
                                <div style={{
                                    background: 'rgba(34, 211, 238, 0.08)',
                                    border: '1px solid rgba(34, 211, 238, 0.2)',
                                    borderRadius: 'var(--radius-xs)',
                                    padding: '12px',
                                    fontSize: '12px',
                                    lineHeight: '1.6',
                                    color: 'var(--text-secondary)',
                                }}>
                                    <div style={{ color: 'var(--accent-cyan)', fontWeight: 600, marginBottom: 6 }}>✨ Explicação da IA:</div>
                                    {explanation}
                                </div>
                            )}
                        </>
                    )}
                </>
            )}
        </div>
    );
}
