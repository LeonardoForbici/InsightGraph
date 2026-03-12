import { useState } from 'react';
import { simulateChanges, type GraphNode, type SimulateResponse } from '../api';

interface SimulationPanelProps {
    availableNodes: GraphNode[];
    onSimulationComplete: (simData: SimulateResponse) => void;
    onClose: () => void;
}

export default function SimulationPanel({ availableNodes, onSimulationComplete, onClose }: SimulationPanelProps) {
    const [deletedNodes, setDeletedNodes] = useState<Set<string>>(new Set());
    const [searchTerm, setSearchTerm] = useState('');
    const [isSimulating, setIsSimulating] = useState(false);

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
            onSimulationComplete(res);
        } catch (err) {
            console.error("Erro na simulação", err);
            alert("A simulação falhou. Verifique o console.");
        } finally {
            setIsSimulating(false);
        }
    };

    const filteredNodes = searchTerm
        ? availableNodes.filter(n => n.name.toLowerCase().includes(searchTerm.toLowerCase()))
        : availableNodes.slice(0, 100); // just show top 100 if no search

    return (
        <div className="ask-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            <div className="ask-header" style={{ flexShrink: 0 }}>
                <h3>🧪 Simulação de Cenários</h3>
                <span className="close-btn" onClick={onClose}>✕</span>
            </div>
            
            <div className="ask-content" style={{ display: 'flex', flexDirection: 'column', gap: '12px', padding: '16px', flex: 1, minHeight: 0, overflow: 'hidden' }}>
                <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-muted)', flexShrink: 0 }}>
                    Selecione nós para deletar ou modificar, então rode uma simulação para visualizar o impacto estrutural e o raio de explosão sem alterar seu código real.
                </p>

                <div className="simulation-selection" style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
                    <div style={{ marginBottom: 16, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '12px' }}>
                        
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div style={{ flex: 1 }}>
                                <h4 style={{ margin: '0 0 8px 0' }}>Neste cenário, apagaríamos: ({deletedNodes.size})</h4>
                                {deletedNodes.size > 0 ? (
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                        {Array.from(deletedNodes).map(k => (
                                            <span key={k} className="dead-code-chip" style={{ cursor: 'pointer', background: 'rgba(239, 68, 68, 0.2)', color: '#ef4444', border: '1px solid #ef4444' }} onClick={() => handleToggleDelete(k)}>
                                                {availableNodes.find(n => n.namespace_key === k)?.name || k} ✕
                                            </span>
                                        ))}
                                    </div>
                                ) : (
                                    <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Nenhum nó selecionado. Pesquise abaixo e clique para adicionar.</div>
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
                    </div>

                    <div style={{ fontWeight: 'bold', marginBottom: 6, flexShrink: 0 }}>Procurar nós no sistema</div>
                    <input 
                        type="text" 
                        placeholder="Ex: TenantEntityListener.java" 
                        value={searchTerm} 
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="ask-input"
                        style={{ border: '1px solid #3d4560', flexShrink: 0, width: '100%' }}
                    />

                    <div style={{ flex: 1, overflowY: 'auto', border: '1px solid var(--border-color)', borderRadius: 6, marginTop: 12, padding: 8, background: 'rgba(0,0,0,0.1)' }}>
                        {filteredNodes.length > 0 ? filteredNodes.map(n => {
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
                                        display: 'flex', justifyContent: 'space-between',
                                        transition: 'background 0.2s',
                                        alignItems: 'center'
                                    }}
                                    onClick={() => handleToggleDelete(n.namespace_key)}
                                    title="Clique para adicionar ou remover da simulação de exclusão"
                                >
                                    <div>
                                        <div style={{ color: isSelected ? '#ef4444' : '#e2e8f0', fontWeight: isSelected ? 'bold' : 'normal' }}>
                                            {n.name}
                                        </div>
                                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{n.layer}</div>
                                    </div>
                                    <div style={{ color: isSelected ? '#ef4444' : 'var(--text-muted)', fontSize: '1.2rem' }}>
                                        {isSelected ? '⊖' : '⊕'}
                                    </div>
                                </div>
                            );
                        }) : <div style={{ color: 'var(--text-muted)', textAlign: 'center', marginTop: 20 }}>Nenhum resultado encontrado.</div>}
                    </div>
                </div>
            </div>
        </div>
    );
}
