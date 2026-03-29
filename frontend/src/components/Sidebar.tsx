import type { Tag } from '../api';
import type { RefObject } from 'react';

interface SidebarProps {
    workspaces: string[];
    onRemoveWorkspace: (path: string) => void;
    projects: string[];
    selectedProjects: string[];
    onToggleProject: (project: string) => void;
    onDeleteProject: (project: string) => void;
    selectedLayer: string;
    onLayerChange: (layer: string) => void;
    searchTerm: string;
    onSearchChange: (term: string) => void;
    searchInputRef?: RefObject<HTMLInputElement | null>;
    nodeCount: number;
    edgeCount: number;
    tags: Tag[];
    selectedTag: string | null;
    onTagSelect: (tagName: string | null) => void;
    nodeTypeOptions: { value: string; label: string }[];
    selectedNodeTypes: string[];
    onToggleNodeType: (type: string) => void;
    hotspotRange: [number, number];
    complexityRange: [number, number];
    onHotspotRangeChange: (index: 0 | 1, value: number) => void;
    onComplexityRangeChange: (index: 0 | 1, value: number) => void;
    availableFiles: string[];
    fileFilter: string;
    onFileFilterChange: (value: string) => void;
    impactOnly: boolean;
    onImpactOnlyToggle: () => void;
    visibleNodeCount: number;
    totalNodeCount: number;
    isCollapsed: boolean;
    onToggleCollapse: () => void;
}

const LAYERS = [
    { key: '', label: 'All', color: '#8b93b0' },
    { key: 'Frontend', label: 'Frontend', color: '#4f8ff7' },
    { key: 'API', label: 'API', color: '#a78bfa' },
    { key: 'Service', label: 'Service', color: '#fbbf24' },
    { key: 'Database', label: 'Database', color: '#34d399' },
];

const NODE_TYPE_COLORS: Record<string, string> = {
    Java_Class: 'rgba(251,146,60,',
    Java_Method: 'rgba(251,146,60,',
    API_Endpoint: 'rgba(167,139,250,',
    TS_Component: 'rgba(96,165,250,',
    TS_Function: 'rgba(96,165,250,',
    SQL_Table: 'rgba(52,211,153,',
    SQL_Procedure: 'rgba(52,211,153,',
};

const NODE_TYPE_ACCENT: Record<string, string> = {
    Java_Class: '#fb923c',
    Java_Method: '#fb923c',
    API_Endpoint: '#a78bfa',
    TS_Component: '#60a5fa',
    TS_Function: '#60a5fa',
    SQL_Table: '#34d399',
    SQL_Procedure: '#34d399',
};

export default function Sidebar({
    workspaces,
    onRemoveWorkspace,
    projects,
    selectedProjects,
    onToggleProject,
    onDeleteProject,
    selectedLayer,
    onLayerChange,
    searchTerm,
    onSearchChange,
    searchInputRef,
    tags,
    selectedTag,
    onTagSelect,
    nodeCount,
    edgeCount,
    nodeTypeOptions,
    selectedNodeTypes,
    onToggleNodeType,
    hotspotRange,
    complexityRange,
    onHotspotRangeChange,
    onComplexityRangeChange,
    availableFiles,
    fileFilter,
    onFileFilterChange,
    impactOnly,
    onImpactOnlyToggle,
    visibleNodeCount,
    totalNodeCount,
    isCollapsed,
    onToggleCollapse,
}: SidebarProps) {
    return (
        <>
            {/* Collapse Toggle Tab */}
            <button
                className={`sidebar-collapse-tab ${isCollapsed ? 'collapsed' : ''}`}
                onClick={onToggleCollapse}
                title={isCollapsed ? 'Expandir sidebar' : 'Minimizar sidebar'}
                aria-label={isCollapsed ? 'Expandir sidebar' : 'Minimizar sidebar'}
            >
                <svg
                    width="14"
                    height="14"
                    viewBox="0 0 14 14"
                    fill="none"
                    style={{ transition: 'transform 0.3s ease', transform: isCollapsed ? 'rotate(180deg)' : 'rotate(0deg)' }}
                >
                    <polyline points="9,2 4,7 9,12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
                </svg>
            </button>

            <div className={`sidebar ${isCollapsed ? 'sidebar-hidden' : ''}`}>
                {/* Workspaces */}
                <div className="sidebar-section">
                    <div className="sidebar-section-title">
                        <span className="sidebar-section-label">
                            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" style={{opacity:0.7}}>
                                <rect x="1" y="3" width="14" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.5" fill="none"/>
                                <path d="M1 6h14" stroke="currentColor" strokeWidth="1.2"/>
                                <path d="M5 3V1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                                <path d="M11 3V1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                            </svg>
                            Workspaces
                        </span>
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
                                <span className="remove" onClick={() => onRemoveWorkspace(ws)} title="Remover">✕</span>
                            </div>
                        ))
                    )}
                </div>

                {/* Search */}
                <div className="sidebar-section">
                    <div className="sidebar-section-title">
                        <span className="sidebar-section-label">Busca</span>
                    </div>
                    <div className="search-input-wrapper">
                        <svg className="search-input-icon" width="13" height="13" viewBox="0 0 16 16" fill="none">
                            <circle cx="6.5" cy="6.5" r="4.5" stroke="currentColor" strokeWidth="1.5"/>
                            <line x1="10" y1="10" x2="14" y2="14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                        </svg>
                        <input
                            className="search-input search-input-with-icon"
                            type="text"
                            placeholder="Filtrar pelo nome..."
                            value={searchTerm}
                            onChange={(e) => onSearchChange(e.target.value)}
                            ref={searchInputRef}
                        />
                    </div>
                </div>

                {/* Advanced Filters */}
                <div className="sidebar-section">
                    <div className="sidebar-section-title">
                        <span className="sidebar-section-label">
                            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" style={{opacity:0.7}}>
                                <path d="M2 4h12M4 8h8M6 12h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                            </svg>
                            Filtros
                        </span>
                        <span className="section-badge">{visibleNodeCount}/{totalNodeCount}</span>
                    </div>

                    <div className="range-control">
                        <div className="range-row">
                            <span>Hotspot</span>
                            <span className="range-value">{hotspotRange[0]}–{hotspotRange[1]}</span>
                        </div>
                        <div className="range-inputs">
                            <input type="range" min={0} max={100} value={hotspotRange[0]} onChange={(e) => onHotspotRangeChange(0, Number(e.target.value) || 0)} />
                            <input type="range" min={0} max={100} value={hotspotRange[1]} onChange={(e) => onHotspotRangeChange(1, Number(e.target.value) || 0)} />
                        </div>
                    </div>

                    <div className="range-control">
                        <div className="range-row">
                            <span>Complexidade</span>
                            <span className="range-value">{complexityRange[0]}–{complexityRange[1]}</span>
                        </div>
                        <div className="range-inputs">
                            <input type="range" min={0} max={80} value={complexityRange[0]} onChange={(e) => onComplexityRangeChange(0, Number(e.target.value) || 0)} />
                            <input type="range" min={0} max={80} value={complexityRange[1]} onChange={(e) => onComplexityRangeChange(1, Number(e.target.value) || 0)} />
                        </div>
                    </div>

                    {/* Node Type Pills */}
                    <div className="node-type-pill-grid">
                        {nodeTypeOptions.map((option) => {
                            const colorBase = NODE_TYPE_COLORS[option.value] ?? 'rgba(139,147,176,';
                            const accent = NODE_TYPE_ACCENT[option.value] ?? '#8b93b0';
                            const isActive = selectedNodeTypes.includes(option.value);
                            return (
                                <button
                                    key={option.value}
                                    type="button"
                                    className={`node-type-pill ${isActive ? 'active' : ''}`}
                                    onClick={() => onToggleNodeType(option.value)}
                                    style={isActive ? {
                                        background: `${colorBase}0.14)`,
                                        borderColor: `${colorBase}0.5)`,
                                        color: accent,
                                        boxShadow: `0 0 8px ${colorBase}0.15)`,
                                    } : undefined}
                                >
                                    {option.label}
                                </button>
                            );
                        })}
                    </div>

                    <div className="file-filter-row">
                        <input
                            list="files-datalist"
                            className="search-input file-filter-input"
                            type="text"
                            placeholder="Filtrar por arquivo..."
                            value={fileFilter}
                            onChange={(e) => onFileFilterChange(e.target.value)}
                        />
                        <datalist id="files-datalist">
                            {availableFiles.map((file) => <option key={file} value={file} />)}
                        </datalist>
                    </div>

                    <button
                        type="button"
                        className={`btn impact-toggle-btn ${impactOnly ? 'btn-accent active' : 'btn-secondary'}`}
                        onClick={onImpactOnlyToggle}
                    >
                        {impactOnly ? (
                            <><span className="impact-on-dot" /> Apenas Impactados ON</>
                        ) : 'Mostrar apenas impactados'}
                    </button>
                </div>

                {/* Projects */}
                {projects.length > 0 && (
                    <div className="sidebar-section">
                        <div className="sidebar-section-title">
                            <span className="sidebar-section-label">
                                <svg width="11" height="11" viewBox="0 0 16 16" fill="none" style={{opacity:0.7}}>
                                    <path d="M2 13V5a1 1 0 0 1 1-1h3l2-2h5a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1z" stroke="currentColor" strokeWidth="1.5" fill="none"/>
                                </svg>
                                Projetos
                            </span>
                            <span className="section-badge">{projects.length}</span>
                        </div>
                        <div className="filter-group">
                            {projects.map((project) => (
                                <div key={project} className="project-item">
                                    <label className={`filter-item ${selectedProjects.includes(project) ? 'active' : ''}`}>
                                        <input type="checkbox" checked={selectedProjects.includes(project)} onChange={() => onToggleProject(project)} />
                                        {project}
                                    </label>
                                    <span className="remove project-remove" onClick={() => onDeleteProject(project)} title="Deletar projeto">✕</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Layers */}
                <div className="sidebar-section">
                    <div className="sidebar-section-title">
                        <span className="sidebar-section-label">Camadas</span>
                    </div>
                    <div className="layer-pill-grid">
                        {LAYERS.map((layer) => (
                            <button
                                key={layer.key}
                                type="button"
                                className={`layer-pill ${selectedLayer === layer.key ? 'active' : ''}`}
                                onClick={() => onLayerChange(layer.key)}
                                style={selectedLayer === layer.key ? {
                                    borderColor: layer.color,
                                    color: layer.color,
                                    background: `${layer.color}18`,
                                    boxShadow: `0 0 8px ${layer.color}30`,
                                } : undefined}
                            >
                                <span className="filter-dot" style={{ background: layer.color, boxShadow: `0 0 4px ${layer.color}` }} />
                                {layer.label}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Tags */}
                {tags.length > 0 && (
                    <div className="sidebar-section">
                        <div className="sidebar-section-title">
                            <span className="sidebar-section-label">Tags</span>
                            {selectedTag && <span className="section-badge" style={{ background: 'rgba(79,143,247,0.1)', color: '#60a5fa' }}>ativo</span>}
                        </div>
                        <div className="filter-group tag-filter-group">
                            {tags.map((tag) => (
                                <div key={tag.id} className={`filter-item tag-filter ${selectedTag === tag.name ? 'active' : ''}`} onClick={() => onTagSelect(tag.name)}>
                                    <div className="filter-dot" style={{ background: tag.color || '#cbd5f5' }} />
                                    {tag.name}
                                </div>
                            ))}
                            {selectedTag && (
                                <button type="button" className="tag-clear-btn" onClick={() => onTagSelect(null)}>Limpar filtro</button>
                            )}
                        </div>
                    </div>
                )}

                {/* Legend */}
                <div className="sidebar-section sidebar-legend" style={{ marginTop: 'auto' }}>
                    <div className="sidebar-section-title">
                        <span className="sidebar-section-label">Tipos de Nó</span>
                        {nodeCount > 0 && (
                            <span className="section-badge">{nodeCount.toLocaleString()} · {edgeCount.toLocaleString()}</span>
                        )}
                    </div>
                    <div className="sidebar-legend-grid">
                        <div className="legend-item"><div className="legend-dot" style={{ background: '#fb923c', boxShadow: '0 0 5px #fb923c60' }} /><span>Java</span></div>
                        <div className="legend-item"><div className="legend-dot" style={{ background: '#60a5fa', boxShadow: '0 0 5px #60a5fa60' }} /><span>TypeScript</span></div>
                        <div className="legend-item"><div className="legend-dot" style={{ background: '#34d399', boxShadow: '0 0 5px #34d39960' }} /><span>SQL</span></div>
                        <div className="legend-item"><div className="legend-dot" style={{ background: '#a78bfa', boxShadow: '0 0 5px #a78bfa60' }} /><span>API</span></div>
                    </div>
                </div>
            </div>
        </>
    );
}
