import { useEffect, useState } from 'react';
import { fetchAntipatterns, fetchGraphStats, type AntipatternData, type GraphStats } from '../api';
import EvolutionTimeline from './EvolutionTimeline';

interface DashboardProps {
    onClose: () => void;
}

export default function Dashboard({ onClose }: DashboardProps) {
    const [antipatterns, setAntipatterns] = useState<AntipatternData | null>(null);
    const [stats, setStats] = useState<GraphStats | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const load = async () => {
            try {
                const [aData, sData] = await Promise.all([
                    fetchAntipatterns(),
                    fetchGraphStats()
                ]);
                setAntipatterns(aData);
                setStats(sData);
            } catch (err) {
                console.error("Failed to load dashboard data.", err);
            } finally {
                setLoading(false);
            }
        };
        load();
    }, []);

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
                    {/* Evolution Timeline */}
                    <div className="dashboard-section" style={{ paddingBottom: 16 }}>
                        <EvolutionTimeline />
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
                                        </tr>
                                    ))}
                                    {antipatterns.god_classes.length === 0 && (
                                        <tr><td colSpan={4}>Nenhuma Classe Onipresente (God Class) crítica encontrada neste scan.</td></tr>
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
                                    </tr>
                                </thead>
                                <tbody>
                                    {antipatterns.circular_dependencies.map((item, i) => (
                                        <tr key={i}>
                                            <td>{item.length}</td>
                                            <td style={{ color: '#eab308' }}>{item.path.join(' ➔ ')}</td>
                                        </tr>
                                    ))}
                                    {antipatterns.circular_dependencies.length === 0 && (
                                        <tr><td colSpan={2}>Nenhuma dependência circular detectada.</td></tr>
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
                            <div className="dead-code-list">
                                {antipatterns.dead_code.map((item, i) => (
                                    <span key={i} className="dead-code-chip" title={`Camada: ${item.layer} | Arquivo: ${item.file}`}>
                                        {item.name}
                                    </span>
                                ))}
                                {antipatterns.dead_code.length === 0 && (
                                    <span style={{ color: 'var(--text-muted)' }}>Nenhum código órfão detectado.</span>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
