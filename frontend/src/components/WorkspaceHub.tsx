import { useEffect, useMemo, useState } from 'react';
import { browseSystemFolder, type GraphNode, type StartScanRequest } from '../api';

interface WorkspaceHubProps {
    workspaces: string[];
    onAddWorkspace: (path: string) => void;
    onRemoveWorkspace: (path: string) => void;
    projects: string[];
    graphNodes: GraphNode[];
    selectedProjects: string[];
    scanStatus: string;
    scanStats: { files: number; nodes: number; rels: number; progress: number; currentFile: string };
    scanErrors?: string[];
    onScan: (payload: StartScanRequest) => void;
    onCancelScan?: () => void;
    onOpenProjectGraph: (project: string) => void;
    onOpenAllGraphs: () => void;
    onOpenTimeline: () => void;
    onOpenSecurity: () => void;
    onOpenCollaboration: () => void;
    onOpenAutoHealer: () => void;
    onOpenLiveAlerts: () => void;
    onOpenCommitTimeline: () => void;
    onOpenWeeklyDigest: () => void;
    onOpenSettings: () => void;
    onOpenProjectManagement: () => void;
}

export default function WorkspaceHub({
    workspaces,
    onAddWorkspace,
    onRemoveWorkspace,
    projects,
    graphNodes,
    selectedProjects,
    scanStatus,
    scanStats,
    scanErrors = [],
    onScan,
    onCancelScan,
    onOpenProjectGraph,
    onOpenAllGraphs,
    onOpenTimeline,
    onOpenSecurity,
    onOpenCollaboration,
    onOpenAutoHealer,
    onOpenLiveAlerts,
    onOpenCommitTimeline,
    onOpenWeeklyDigest,
    onOpenSettings,
    onOpenProjectManagement,
}: WorkspaceHubProps) {
    const [workspaceInput, setWorkspaceInput] = useState('');
    const [scanMode, setScanMode] = useState<'local' | 'github'>('local');
    const [ghRepo, setGhRepo] = useState('');
    const [ghBranch, setGhBranch] = useState('main');
    const [ghToken, setGhToken] = useState('');
    const [ghShallow, setGhShallow] = useState(true);
    const [pickingWorkspace, setPickingWorkspace] = useState(false);
    const [workspacePickerError, setWorkspacePickerError] = useState<string | null>(null);

    const STORAGE_KEY = 'insightgraph.scan.config.v1';

    useEffect(() => {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return;
            const parsed = JSON.parse(raw);
            if (parsed?.mode === 'github') {
                setScanMode('github');
                setGhRepo(String(parsed?.github_config?.repository || ''));
                setGhBranch(String(parsed?.github_config?.branch || 'main'));
                setGhToken(String(parsed?.github_config?.token || ''));
                setGhShallow(Boolean(parsed?.github_config?.shallow_clone ?? true));
            } else if (parsed?.mode === 'local') {
                setScanMode('local');
            }
        } catch {
            // ignore invalid persisted state
        }
    }, []);
    const projectCards = useMemo(() => {
        const counts = new Map<string, number>();
        graphNodes.forEach((node) => {
            const project = String(node.project || 'Sem Projeto');
            counts.set(project, (counts.get(project) || 0) + 1);
        });
        const source = projects.length > 0 ? projects : Array.from(counts.keys());
        return source.map((project) => ({
            project,
            nodes: counts.get(project) || 0,
            active: selectedProjects.includes(project),
        }));
    }, [graphNodes, projects, selectedProjects]);

    const moduleCards = [
        { title: 'Security Center', subtitle: 'Riscos, vulnerabilidades e compliance', action: onOpenSecurity, accent: 'emerald' },
        { title: 'Timeline 4D', subtitle: 'Replay temporal com diffs e heatmap', action: onOpenTimeline, accent: 'violet' },
        { title: 'War Rooms', subtitle: 'Colaboração com chat e cursores', action: onOpenCollaboration, accent: 'blue' },
        { title: 'Auto Healer', subtitle: 'Sugestões de correção e testes', action: onOpenAutoHealer, accent: 'amber' },
        { title: 'Live Alerts', subtitle: 'Alertas em tempo real do sistema', action: onOpenLiveAlerts, accent: 'rose' },
        { title: 'Commit Timeline', subtitle: 'Evolução de commits e mudanças', action: onOpenCommitTimeline, accent: 'cyan' },
        { title: 'Weekly Digest', subtitle: 'Resumo executivo semanal', action: onOpenWeeklyDigest, accent: 'slate' },
        { title: 'Live Projects', subtitle: 'Workspaces, watchers e impacto cross-project', action: onOpenProjectManagement, accent: 'indigo' },
        { title: 'Settings', subtitle: 'Configuração operacional e integrações', action: onOpenSettings, accent: 'orange' },
    ];

    return (
        <div className="workspace-hub ai-shell">
            <section className="ai-toolbar">
                <div className="ai-toolbar-search">
                    <input placeholder="Search components..." />
                    <span>⌘ K</span>
                </div>
                <div className="ai-toolbar-actions">
                    <button className="btn btn-ghost" onClick={onOpenSettings}>Settings</button>
                    <button className="btn btn-secondary" onClick={onOpenSecurity}>Security</button>
                </div>
            </section>

            <section className="ai-banner-card">
                <div>
                    <strong>InsightGraph Control Panel</strong>
                    <p>Planeje scans, organize grafos por projeto e navegue por módulos sem interface poluída.</p>
                </div>
                <span className="ai-badge-featured">Featured</span>
            </section>

            <section className="workspace-hero-card">
                <div className="workspace-hero-icon">◈</div>
                <div>
                    <h1>Dashboard</h1>
                    <p>Layout profissional, foco em módulos, scanner e grafos organizados.</p>
                    <div className="workspace-hero-tags">
                        <span>Real-time</span>
                        <span>Impacto</span>
                        <span>CI/CD</span>
                        <span>Colaboração</span>
                    </div>
                </div>
            </section>

            <section className="workspace-scan-card">
                <div className="workspace-scan-header">
                    <h3>Scanner Inteligente</h3>
                    <div style={{ display: 'flex', gap: 8 }}>
                        <button className="btn btn-secondary" onClick={onOpenAllGraphs}>Ver todos os grafos</button>
                        {scanStatus === 'scanning' ? (
                            <>
                                <button className="btn btn-secondary" onClick={onCancelScan} disabled={!onCancelScan}>
                                    Cancelar
                                </button>
                                <button className="btn btn-primary" disabled>
                                    Escaneando...
                                </button>
                            </>
                        ) : (
                            <button
                                className="btn btn-primary"
                                onClick={() => {
                                    const payload: StartScanRequest =
                                        scanMode === 'github'
                                            ? {
                                                mode: 'github',
                                                github_config: {
                                                    repository: ghRepo.trim(),
                                                    branch: (ghBranch || 'main').trim(),
                                                    token: ghToken || null,
                                                    shallow_clone: ghShallow,
                                                },
                                            }
                                            : { mode: 'local' };
                                    try {
                                        localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
                                    } catch {
                                        // ignore
                                    }
                                    onScan(payload);
                                }}
                                disabled={scanMode === 'github' && !ghRepo.trim()}
                            >
                                Iniciar Scan
                            </button>
                        )}
                    </div>
                </div>
                <div className="workspace-add-row" style={{ gap: 8, alignItems: 'center' }}>
                    <span style={{ color: '#a7b0cc', fontSize: 13 }}>Modo:</span>
                    <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => {
                            setScanMode('local');
                            try {
                                localStorage.setItem(STORAGE_KEY, JSON.stringify({ mode: 'local' }));
                            } catch {
                                // ignore
                            }
                        }}
                    >
                        Local
                    </button>
                    <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => {
                            setScanMode('github');
                            try {
                                localStorage.setItem(
                                    STORAGE_KEY,
                                    JSON.stringify({
                                        mode: 'github',
                                        github_config: {
                                            repository: ghRepo.trim(),
                                            branch: (ghBranch || 'main').trim(),
                                            token: ghToken || null,
                                            shallow_clone: ghShallow,
                                        },
                                    })
                                );
                            } catch {
                                // ignore
                            }
                        }}
                    >
                        GitHub
                    </button>
                </div>
                {scanMode === 'local' ? (
                    <>
                        <div className="workspace-add-row">
                    <input
                        className="input"
                        value={workspaceInput}
                        onChange={(e) => setWorkspaceInput(e.target.value)}
                        placeholder="Caminho do workspace (ex: C:\\git\\repo)"
                    />
                    <button
                        className="btn btn-secondary"
                        onClick={async () => {
                            setWorkspacePickerError(null);
                            setPickingWorkspace(true);
                            try {
                                const selected = await browseSystemFolder();
                                if (selected) {
                                    onAddWorkspace(selected);
                                    setWorkspaceInput('');
                                    return;
                                }
                                const fallback = workspaceInput.trim();
                                if (fallback) {
                                    onAddWorkspace(fallback);
                                    setWorkspaceInput('');
                                }
                            } catch {
                                const fallback = workspaceInput.trim();
                                if (fallback) {
                                    onAddWorkspace(fallback);
                                    setWorkspaceInput('');
                                } else {
                                    setWorkspacePickerError('Nao foi possivel abrir o seletor de pastas do Windows.');
                                }
                            } finally {
                                setPickingWorkspace(false);
                            }
                        }}
                        disabled={pickingWorkspace}
                    >
                        {pickingWorkspace ? 'Abrindo Explorer...' : 'Adicionar Workspace'}
                    </button>
                </div>
                {workspacePickerError && (
                    <div style={{ marginTop: 8, color: '#fda4af', fontSize: 12 }}>
                        {workspacePickerError}
                    </div>
                )}
                {workspaces.length > 0 && (
                    <div className="workspace-chip-row">
                        {workspaces.map((ws) => (
                            <button key={ws} className="workspace-chip" onClick={() => onRemoveWorkspace(ws)} title={ws}>
                                {ws.split(/[/\\]/).pop()} ×
                            </button>
                        ))}
                    </div>
                )}
                    </>
                ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 160px', gap: 10 }}>
                        <input
                            className="input"
                            value={ghRepo}
                            onChange={(e) => setGhRepo(e.target.value)}
                            placeholder="Repositorio (owner/repo)"
                        />
                        <input
                            className="input"
                            value={ghBranch}
                            onChange={(e) => setGhBranch(e.target.value)}
                            placeholder="Branch"
                        />
                        <input
                            className="input"
                            value={ghToken}
                            onChange={(e) => setGhToken(e.target.value)}
                            placeholder="Token (opcional)"
                            type="password"
                            style={{ gridColumn: '1 / span 2' }}
                        />
                        <label style={{ gridColumn: '1 / span 2', color: '#a7b0cc', fontSize: 13, display: 'flex', gap: 8, alignItems: 'center' }}>
                            <input type="checkbox" checked={ghShallow} onChange={(e) => setGhShallow(e.target.checked)} />
                            Shallow clone (depth=1)
                        </label>
                    </div>
                )}
                <div className="workspace-scan-progress">
                    <div className="workspace-progress-track">
                        <div
                            className="workspace-progress-fill"
                            style={{ width: `${Math.max(0, Math.min(100, scanStats.progress))}%` }}
                        />
                    </div>
                    <small>
                        {scanStats.currentFile
                            ? `Arquivo atual: ${scanStats.currentFile}`
                            : `Arquivos: ${scanStats.files} • Nós: ${scanStats.nodes} • Relações: ${scanStats.rels}`}
                    </small>
                </div>
                {scanErrors.length > 0 && (
                    <div style={{ marginTop: 10, background: 'rgba(244,63,94,0.06)', border: '1px solid rgba(244,63,94,0.15)', borderRadius: 10, padding: 10 }}>
                        <strong style={{ color: '#fda4af', fontSize: 13 }}>Erros do scan</strong>
                        <ul style={{ margin: '8px 0 0', paddingLeft: 18, color: '#fda4af', fontSize: 12 }}>
                            {scanErrors.slice(-5).map((err, idx) => (
                                <li key={`${idx}-${err.slice(0, 40)}`}>{err}</li>
                            ))}
                        </ul>
                    </div>
                )}
            </section>

            <section className="workspace-projects">
                <div className="workspace-section-head">
                    <h3>Módulos do Sistema</h3>
                </div>
                <div className="workspace-grid">
                    {moduleCards.map((card) => (
                        <button
                            key={card.title}
                            className={`workspace-module-card accent-${card.accent}`}
                            onClick={card.action}
                            type="button"
                        >
                            <strong>{card.title}</strong>
                            <p>{card.subtitle}</p>
                        </button>
                    ))}
                </div>
            </section>

            <section className="workspace-projects">
                <div className="workspace-section-head">
                    <h3>Grafos Organizados por Projeto</h3>
                    <button className="btn btn-secondary" onClick={onOpenAllGraphs}>Abrir visão geral</button>
                </div>
                <div className="workspace-grid">
                    {projectCards.length === 0 ? (
                        <div className="workspace-empty-card">
                            Rode o scanner para gerar os grafos por projeto.
                        </div>
                    ) : (
                        projectCards.map((card) => (
                            <div key={card.project} className={`workspace-project-card ${card.active ? 'active' : ''}`}>
                                <div>
                                    <strong>{card.project}</strong>
                                    <p>{card.nodes} nós mapeados</p>
                                </div>
                                <button className="btn btn-ghost" onClick={() => onOpenProjectGraph(card.project)}>
                                    Abrir grafo
                                </button>
                            </div>
                        ))
                    )}
                </div>
            </section>
        </div>
    );
}
