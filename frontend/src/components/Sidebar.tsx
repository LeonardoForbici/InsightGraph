interface SidebarProps {
    workspaces: string[];
    onRemoveWorkspace: (path: string) => void;
    projects: string[];
    selectedProjects: string[];
    onToggleProject: (project: string) => void;
    selectedLayer: string;
    onLayerChange: (layer: string) => void;
    searchTerm: string;
    onSearchChange: (term: string) => void;
    nodeCount: number;
    edgeCount: number;
}

const LAYERS = [
    { key: '', label: 'Todas as Camadas', color: '#8b93b0' },
    { key: 'Frontend', label: 'Frontend', color: '#4f8ff7' },
    { key: 'API', label: 'API', color: '#a78bfa' },
    { key: 'Service', label: 'Service', color: '#fbbf24' },
    { key: 'Database', label: 'Banco de Dados', color: '#34d399' },
];

export default function Sidebar({
    workspaces,
    onRemoveWorkspace,
    projects,
    selectedProjects,
    onToggleProject,
    selectedLayer,
    onLayerChange,
    searchTerm,
    onSearchChange,
    nodeCount,
    edgeCount,
}: SidebarProps) {
    return (
        <div className="sidebar">
            {/* Workspaces */}
            <div className="sidebar-section">
                <div className="sidebar-section-title">
                    Workspaces
                    {workspaces.length > 0 && (
                        <span className="section-badge">{workspaces.length}</span>
                    )}
                </div>
                {workspaces.length === 0 ? (
                    <div className="sidebar-empty-hint">
                        Adicione o caminho de um diretório na barra superior para começar.
                    </div>
                ) : (
                    workspaces.map((ws) => (
                        <div key={ws} className="workspace-tag">
                            <span className="ws-path" title={ws}>
                                {ws.split(/[/\\]/).pop()}
                            </span>
                            <span className="remove" onClick={() => onRemoveWorkspace(ws)} title="Remover">
                                ✕
                            </span>
                        </div>
                    ))
                )}
            </div>

            {/* Search */}
            <div className="sidebar-section">
                <div className="sidebar-section-title">Busca</div>
                <input
                    className="search-input"
                    type="text"
                    placeholder="Filtrar componentes pelo nome..."
                    value={searchTerm}
                    onChange={(e) => onSearchChange(e.target.value)}
                />
            </div>

            {/* Project Filter */}
            {projects.length > 0 && (
                <div className="sidebar-section">
                    <div className="sidebar-section-title">
                        Projetos
                        <span className="section-badge">{projects.length}</span>
                    </div>
                    <div className="filter-group">
                        {projects.map((project) => (
                            <label
                                key={project}
                                className={`filter-item ${selectedProjects.includes(project) ? 'active' : ''}`}
                            >
                                <input
                                    type="checkbox"
                                    checked={selectedProjects.includes(project)}
                                    onChange={() => onToggleProject(project)}
                                />
                                {project}
                            </label>
                        ))}
                    </div>
                </div>
            )}

            {/* Layer Filter */}
            <div className="sidebar-section">
                <div className="sidebar-section-title">Camadas</div>
                <div className="filter-group">
                    {LAYERS.map((layer) => (
                        <div
                            key={layer.key}
                            className={`filter-item ${selectedLayer === layer.key ? 'active' : ''}`}
                            onClick={() => onLayerChange(layer.key)}
                        >
                            <div className="filter-dot" style={{ background: layer.color, boxShadow: `0 0 6px ${layer.color}40` }} />
                            {layer.label}
                        </div>
                    ))}
                </div>
            </div>

            {/* Node Types Legend */}
            <div className="sidebar-section" style={{ marginTop: 'auto' }}>
                <div className="sidebar-section-title">
                    Tipos de Nó
                    {nodeCount > 0 && (
                        <span className="section-badge">{nodeCount} nós · {edgeCount} conexões</span>
                    )}
                </div>
                <div className="filter-group">
                    <div className="legend-item">
                        <div className="legend-dot" style={{ background: '#fb923c', boxShadow: '0 0 6px rgba(249,115,22,0.3)' }} />
                        Classe / Método Java
                    </div>
                    <div className="legend-item">
                        <div className="legend-dot" style={{ background: '#60a5fa', boxShadow: '0 0 6px rgba(96,165,250,0.3)' }} />
                        Componente / Função TS
                    </div>
                    <div className="legend-item">
                        <div className="legend-dot" style={{ background: '#34d399', boxShadow: '0 0 6px rgba(52,211,153,0.3)' }} />
                        Tabela / Procedure SQL
                    </div>
                    <div className="legend-item">
                        <div className="legend-dot" style={{ background: '#a78bfa', boxShadow: '0 0 6px rgba(167,139,250,0.3)' }} />
                        Componente Mobile
                    </div>
                </div>
            </div>
        </div>
    );
}
