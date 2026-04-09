/**
 * WatchModePanel — Painel de controle do Watch Mode
 * 
 * Permite iniciar/parar monitoramento de projetos e exibe status em tempo real.
 */

import { useState } from 'react';
import { useWatchMode } from '../hooks/useWatchMode';
import type { ImpactResult } from '../hooks/useWatchMode';

interface WatchModePanelProps {
    onViewImpact?: (impact: ImpactResult) => void;
}

export default function WatchModePanel({ onViewImpact }: WatchModePanelProps) {
    const { connected, watching, lastImpact, impactHistory, startWatch, stopWatch, clearHistory } = useWatchMode();
    const [projectPath, setProjectPath] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleStart = async () => {
        if (!projectPath.trim()) {
            setError('Digite o caminho do projeto');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            await startWatch(projectPath.trim());
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao iniciar watch');
        } finally {
            setLoading(false);
        }
    };

    const handleStop = async () => {
        setLoading(true);
        setError(null);

        try {
            await stopWatch();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao parar watch');
        } finally {
            setLoading(false);
        }
    };

    const formatTimestamp = (timestamp: string) => {
        try {
            const date = new Date(timestamp);
            return date.toLocaleTimeString('pt-BR');
        } catch {
            return timestamp;
        }
    };

    const getRiskColor = (score: number) => {
        if (score > 70) return '#ef4444';
        if (score > 30) return '#eab308';
        return '#22c55e';
    };

    return (
        <div style={{
            background: '#1e293b',
            borderRadius: '12px',
            padding: '20px',
            border: '1px solid #334155',
        }}>
            {/* Header */}
            <div style={{ marginBottom: '20px' }}>
                <h3 style={{ margin: 0, color: '#e2e8f0', fontSize: '1.1rem', fontWeight: '600' }}>
                    🔄 Watch Mode
                </h3>
                <p style={{ margin: '8px 0 0 0', color: '#94a3b8', fontSize: '0.85rem' }}>
                    Monitore mudanças em tempo real e receba notificações de impacto
                </p>
            </div>

            {/* Status */}
            <div style={{
                display: 'flex',
                gap: '12px',
                marginBottom: '20px',
                padding: '12px',
                background: '#0f172a',
                borderRadius: '8px',
            }}>
                <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '4px' }}>
                        Conexão
                    </div>
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        fontSize: '0.9rem',
                        fontWeight: '600',
                    }}>
                        <span style={{
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            background: connected ? '#22c55e' : '#ef4444',
                            boxShadow: connected ? '0 0 8px #22c55e' : '0 0 8px #ef4444',
                        }} />
                        <span style={{ color: connected ? '#22c55e' : '#ef4444' }}>
                            {connected ? 'Conectado' : 'Desconectado'}
                        </span>
                    </div>
                </div>

                <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '4px' }}>
                        Status
                    </div>
                    <div style={{
                        fontSize: '0.9rem',
                        fontWeight: '600',
                        color: watching ? '#60a5fa' : '#94a3b8',
                    }}>
                        {watching ? 'Monitorando' : 'Parado'}
                    </div>
                </div>

                <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '4px' }}>
                        Impactos
                    </div>
                    <div style={{
                        fontSize: '0.9rem',
                        fontWeight: '600',
                        color: '#e2e8f0',
                    }}>
                        {impactHistory.length}
                    </div>
                </div>
            </div>

            {/* Controls */}
            {!watching ? (
                <div style={{ marginBottom: '20px' }}>
                    <label style={{
                        display: 'block',
                        fontSize: '0.85rem',
                        color: '#cbd5e1',
                        marginBottom: '8px',
                    }}>
                        Caminho do Projeto
                    </label>
                    <input
                        type="text"
                        value={projectPath}
                        onChange={(e) => setProjectPath(e.target.value)}
                        placeholder="C:\caminho\do\projeto"
                        disabled={loading}
                        style={{
                            width: '100%',
                            padding: '10px 12px',
                            background: '#0f172a',
                            border: '1px solid #334155',
                            borderRadius: '6px',
                            color: '#e2e8f0',
                            fontSize: '0.9rem',
                            marginBottom: '12px',
                        }}
                    />
                    <button
                        onClick={handleStart}
                        disabled={loading || !projectPath.trim()}
                        style={{
                            width: '100%',
                            padding: '10px 16px',
                            background: loading || !projectPath.trim() ? '#334155' : '#3b82f6',
                            border: 'none',
                            borderRadius: '6px',
                            color: '#fff',
                            fontSize: '0.9rem',
                            fontWeight: '600',
                            cursor: loading || !projectPath.trim() ? 'not-allowed' : 'pointer',
                            transition: 'all 0.2s',
                        }}
                    >
                        {loading ? 'Iniciando...' : '▶ Iniciar Monitoramento'}
                    </button>
                </div>
            ) : (
                <button
                    onClick={handleStop}
                    disabled={loading}
                    style={{
                        width: '100%',
                        padding: '10px 16px',
                        background: loading ? '#334155' : '#ef4444',
                        border: 'none',
                        borderRadius: '6px',
                        color: '#fff',
                        fontSize: '0.9rem',
                        fontWeight: '600',
                        cursor: loading ? 'not-allowed' : 'pointer',
                        transition: 'all 0.2s',
                        marginBottom: '20px',
                    }}
                >
                    {loading ? 'Parando...' : '⏹ Parar Monitoramento'}
                </button>
            )}

            {/* Error */}
            {error && (
                <div style={{
                    padding: '12px',
                    background: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid #ef4444',
                    borderRadius: '6px',
                    color: '#ef4444',
                    fontSize: '0.85rem',
                    marginBottom: '20px',
                }}>
                    ⚠️ {error}
                </div>
            )}

            {/* Last Impact */}
            {lastImpact && (
                <div style={{
                    padding: '16px',
                    background: '#0f172a',
                    border: `2px solid ${getRiskColor(lastImpact.risk_score)}`,
                    borderRadius: '8px',
                    marginBottom: '20px',
                }}>
                    <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: '12px',
                    }}>
                        <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                            Último Impacto
                        </div>
                        <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                            {formatTimestamp(lastImpact.timestamp)}
                        </div>
                    </div>

                    <div style={{
                        fontSize: '0.9rem',
                        fontWeight: '600',
                        color: '#e2e8f0',
                        marginBottom: '8px',
                    }}>
                        📁 {lastImpact.file.split('/').pop() || lastImpact.file}
                    </div>

                    <div style={{
                        fontSize: '0.85rem',
                        color: '#cbd5e1',
                        marginBottom: '12px',
                    }}>
                        {lastImpact.summary}
                    </div>

                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr 1fr',
                        gap: '12px',
                        marginBottom: '12px',
                    }}>
                        <div>
                            <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginBottom: '4px' }}>
                                Alterados
                            </div>
                            <div style={{ fontSize: '1.1rem', fontWeight: '600', color: '#60a5fa' }}>
                                {lastImpact.changed_nodes.length}
                            </div>
                        </div>
                        <div>
                            <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginBottom: '4px' }}>
                                Impactados
                            </div>
                            <div style={{ fontSize: '1.1rem', fontWeight: '600', color: '#f59e0b' }}>
                                {lastImpact.affected_nodes.length}
                            </div>
                        </div>
                        <div>
                            <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginBottom: '4px' }}>
                                Risco
                            </div>
                            <div style={{
                                fontSize: '1.1rem',
                                fontWeight: '600',
                                color: getRiskColor(lastImpact.risk_score),
                            }}>
                                {Math.round(lastImpact.risk_score)}%
                            </div>
                        </div>
                    </div>

                    {onViewImpact && (
                        <button
                            onClick={() => onViewImpact(lastImpact)}
                            style={{
                                width: '100%',
                                padding: '8px 12px',
                                background: 'rgba(96, 165, 250, 0.1)',
                                border: '1px solid #60a5fa',
                                borderRadius: '6px',
                                color: '#60a5fa',
                                fontSize: '0.85rem',
                                fontWeight: '600',
                                cursor: 'pointer',
                                transition: 'all 0.2s',
                            }}
                        >
                            Ver no Grafo
                        </button>
                    )}
                </div>
            )}

            {/* History */}
            {impactHistory.length > 0 && (
                <div>
                    <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: '12px',
                    }}>
                        <div style={{ fontSize: '0.85rem', color: '#cbd5e1', fontWeight: '600' }}>
                            Histórico ({impactHistory.length})
                        </div>
                        <button
                            onClick={clearHistory}
                            style={{
                                padding: '4px 8px',
                                background: 'transparent',
                                border: '1px solid #475569',
                                borderRadius: '4px',
                                color: '#94a3b8',
                                fontSize: '0.75rem',
                                cursor: 'pointer',
                            }}
                        >
                            Limpar
                        </button>
                    </div>

                    <div style={{
                        maxHeight: '200px',
                        overflowY: 'auto',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '8px',
                    }}>
                        {impactHistory.map((impact, idx) => (
                            <div
                                key={`${impact.file}-${impact.timestamp}-${idx}`}
                                style={{
                                    padding: '10px',
                                    background: '#0f172a',
                                    borderLeft: `3px solid ${getRiskColor(impact.risk_score)}`,
                                    borderRadius: '4px',
                                    fontSize: '0.8rem',
                                }}
                            >
                                <div style={{
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    marginBottom: '4px',
                                }}>
                                    <span style={{ color: '#e2e8f0', fontWeight: '600' }}>
                                        {impact.file.split('/').pop()}
                                    </span>
                                    <span style={{ color: '#94a3b8' }}>
                                        {formatTimestamp(impact.timestamp)}
                                    </span>
                                </div>
                                <div style={{ color: '#94a3b8' }}>
                                    {impact.affected_nodes.length} impactados • Risco {Math.round(impact.risk_score)}%
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
