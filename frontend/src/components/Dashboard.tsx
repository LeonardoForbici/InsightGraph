import { useEffect, useState } from 'react';
import { fetchAntipatterns, fetchGraphStats, type AntipatternData, type GraphStats } from '../api';
import EvolutionTimeline from './EvolutionTimeline';

interface DashboardProps {
    onClose: () => void;
    onRefactorRequest?: (nodeName: string, problemType: string) => void;
}

export default function Dashboard({ onClose, onRefactorRequest }: DashboardProps) {
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
