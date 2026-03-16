import { useState } from 'react';
import { simulateChanges, requestSimulationReview, type GraphNode, type SimulateResponse } from '../api';

interface SimulationPanelProps {
    availableNodes: GraphNode[];
    onSimulationComplete: (simData: SimulateResponse) => void;
    onClose: () => void;
}

export default function SimulationPanel({ availableNodes, onSimulationComplete, onClose }: SimulationPanelProps) {
    const [deletedNodes, setDeletedNodes] = useState<Set<string>>(new Set());
    const [searchTerm, setSearchTerm] = useState('');
    const [isSimulating, setIsSimulating] = useState(false);
    const [simResult, setSimResult] = useState<SimulateResponse | null>(null);
    const [aiReport, setAiReport] = useState<string | null>(null);
    const [isReviewing, setIsReviewing] = useState(false);

    const directImpactCount = simResult
        ? simResult.nodes.filter((n) => n.impact_distance === 1).length
        : 0;
    const indirectImpactCount = simResult
        ? simResult.nodes.filter((n) => typeof n.impact_distance === 'number' && n.impact_distance > 1).length
        : 0;
    const totalImpactCount = directImpactCount + indirectImpactCount;
    const estimatedRepairHours = Math.round(totalImpactCount * 2.5 * 10) / 10; // 1 decimal

    const handleToggleDelete = (namespaceKey: string) => {
        setDeletedNodes((prev) => {
            const next = new Set(prev);
            if (next.has(namespaceKey)) next.delete(namespaceKey);
            else next.add(namespaceKey);
            return next;
        });
    };

    const handleSimulate = async () => {
        if (deletedNodes.size === 0) return;
        setIsSimulating(true);
        try {
            const res = await simulateChanges(Array.from(deletedNodes));
            setSimResult(res);
            onSimulationComplete(res);
        } catch (err) {
            console.error("Erro na simulação", err);
            alert("A simulação falhou. Verifique o console.");
        } finally {
            setIsSimulating(false);
        }
    };

    const handleRequestReview = async () => {
        if (!simResult) return;
        setIsReviewing(true);
        setAiReport(null);
        try {
            const res = await requestSimulationReview(simResult);
            setAiReport(res.report);
        } catch (err) {
            console.error("Erro na consultoria IA", err);
            setAiReport("Desculpe, não foi possível gerar a consultoria de arquitetura no momento. Tente novamente mais tarde.");
        } finally {
            setIsReviewing(false);
        }
    };

    const filteredNodes = searchTerm
        ? availableNodes.filter(n => n.name.toLowerCase().includes(searchTerm.toLowerCase()))
        : availableNodes.slice(0, 100); // just show top 100 if no search

    return (
        <div className="ask-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            <div className="ask-header" style={{ flexShrink: 0 }}>
                <h3>🧪 Simulação de Cenários</h3>
                <span className="close-btn" onClick={onClose}>
                    ✕
                </span>
            </div>

            <div className="ask-content" style={{ display: 'flex', flexDirection: 'column', gap: '12px', padding: '16px', flex: 1, minHeight: 0, overflow: 'hidden' }}>
                <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-muted)', flexShrink: 0 }}>
                    Selecione nós para deletar ou modificar, então rode uma simulação para visualizar o impacto estrutural e o raio de explosão sem alterar seu código real.
                </p>

                <input
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    placeholder="Buscar por nome de nó"
                    style={{
                        width: '100%',
                        padding: '8px 10px',
                        borderRadius: 6,
                        border: '1px solid rgba(148, 163, 184, 0.5)',
                        background: 'rgba(0,0,0,0.05)',
                        color: 'var(--text)',
                    }}
                />

                <div className="simulation-selection" style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
                    <div style={{ marginBottom: 16, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '12px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div style={{ flex: 1 }}>
                                <h4 style={{ margin: '0 0 8px 0' }}>
                                    Neste cenário, apagaríamos: ({deletedNodes.size})
                                </h4>

                                {deletedNodes.size > 0 ? (
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                        {Array.from(deletedNodes).map((key) => (
                                            <span
                                                key={key}
                                                className="dead-code-chip"
                                                style={{
                                                    cursor: 'pointer',
                                                    background: 'rgba(239, 68, 68, 0.2)',
                                                    color: '#ef4444',
                                                    border: '1px solid #ef4444',
                                                }}
                                                onClick={() => handleToggleDelete(key)}
                                            >
                                                {availableNodes.find((n) => n.namespace_key === key)?.name || key} ✕
                                            </span>
                                        ))}
                                    </div>
                                ) : (
                                    <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                                        Nenhum nó selecionado. Pesquise abaixo e clique para adicionar.
                                    </div>
                                )}
                            </div>

                            <button
                                className="btn btn-primary"
                                style={{ padding: '8px 16px', flexShrink: 0, marginLeft: '12px', alignSelf: 'center' }}
                                onClick={handleSimulate}
                                disabled={isSimulating || deletedNodes.size === 0}
                            >
                                {isSimulating ? 'Simulando...' : 'Rodar Simulação'}
                            </button>
                        </div>

                        {simResult && (
                            <div style={{ marginTop: 12, padding: 12, borderRadius: 8, background: 'rgba(30, 41, 59, 0.6)', border: '1px solid rgba(100, 116, 139, 0.6)' }}>
                                <div style={{ fontWeight: 'bold', marginBottom: 6 }}>Resultados da Simulação</div>
                                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                                    <div style={{ flex: 1, minWidth: 180 }}>
                                        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                                            Impacto Direto (Quebra Imediata)
                                        </div>
                                        <div style={{ fontSize: '1.1rem', fontWeight: 600, color: '#f97316' }}>
                                            {directImpactCount} nós
                                        </div>
                                    </div>

                                    <div style={{ flex: 1, minWidth: 180 }}>
                                        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                                            Impacto Indireto (Efeito Cascata)
                                        </div>
                                        <div style={{ fontSize: '1.1rem', fontWeight: 600, color: '#eab308' }}>
                                            {indirectImpactCount} nós
                                        </div>
                                    </div>

                                    <div style={{ flex: 1, minWidth: 180 }}>
                                        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                                            Estimativa de reparo
                                        </div>
                                        <div style={{ fontSize: '1.1rem', fontWeight: 600, color: '#7dd3fc' }}>
                                            {estimatedRepairHours} horas
                                        </div>
                                    </div>
                                </div>

                                <div style={{ marginTop: 16 }}>
                                    <button 
                                        onClick={handleRequestReview} 
                                        disabled={isReviewing} 
                                        className="btn btn-accent"
                                        style={{ marginBottom: 12 }}
                                    >
                                        {isReviewing ? '🔄 Consultando IA...' : '✨ Consultar IA Arquiteta'}
                                    </button>

                                    {isReviewing && (
                                        <div style={{ padding: 12, background: 'rgba(0,0,0,0.3)', borderRadius: 6, marginBottom: 12 }}>
                                            A IA está a analisar a arquitetura...
                                        </div>
                                    )}

                                    {aiReport !== null && (
                                        <div style={{ 
                                            padding: 12, 
                                            background: 'rgba(0,0,0,0.5)', 
                                            borderRadius: 6, 
                                            border: '1px solid rgba(100, 116, 139, 0.6)',
                                            whiteSpace: 'pre-wrap',
                                            fontFamily: 'var(--font-mono)',
                                            fontSize: '0.9rem',
                                            lineHeight: 1.5,
                                            color: 'var(--text)',
                                            maxHeight: 300,
                                            overflowY: 'auto'
                                        }}>
                                            {aiReport || "⚠️ A IA processou o pedido, mas o modelo retornou um texto vazio. Tente clicar no botão novamente ou verifique os logs do Ollama."}
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    <div style={{ flex: 1, overflowY: 'auto', border: '1px solid var(--border-color)', borderRadius: 6, marginTop: 12, padding: 8, background: 'rgba(0,0,0,0.1)' }}>
                        {filteredNodes.length > 0 ? (
                            filteredNodes.map((n) => {
                                const isSelected = deletedNodes.has(n.namespace_key);
                                return (
                                    <div
                                        key={n.namespace_key}
                                        style={{
                                            padding: '8px 12px',
                                            cursor: 'pointer',
                                            borderRadius: 4,
                                            background: isSelected ? 'rgba(239, 68, 68, 0.15)' : 'transparent',
                                            borderBottom: '1px solid rgba(255,255,255,0.05)',
                                            display: 'flex',
                                            justifyContent: 'space-between',
                                            transition: 'background 0.2s',
                                            alignItems: 'center',
                                        }}
                                        onClick={() => handleToggleDelete(n.namespace_key)}
                                        title="Clique para adicionar ou remover da simulação de exclusão"
                                    >
                                        <div>
                                            <div style={{ color: isSelected ? '#ef4444' : '#e2e8f0', fontWeight: isSelected ? 'bold' : 'normal' }}>
                                                {n.name}
                                            </div>
                                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                                {n.layer}
                                            </div>
                                        </div>
                                        <div style={{ color: isSelected ? '#ef4444' : 'var(--text-muted)', fontSize: '1.2rem' }}>
                                            {isSelected ? '⊖' : '⊕'}
                                        </div>
                                    </div>
                                );
                            })
                        ) : (
                            <div style={{ color: 'var(--text-muted)', textAlign: 'center', marginTop: 20 }}>
                                Nenhum resultado encontrado.
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
