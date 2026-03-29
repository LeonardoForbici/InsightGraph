import { useState } from 'react';

interface TopBarProps {
    workspaces: string[];
    onAddWorkspace: (path: string) => void;
    onRemoveWorkspace: (path: string) => void;
    onScan: () => void;
    scanStatus: string;
    scanStats: { files: number; nodes: number; rels: number; progress: number; currentFile: string };
    askOpen: boolean;
    onAsk: () => void;
    dashboardOpen: boolean;
    onToggleDashboard: () => void;
    simulationOpen: boolean;
    onToggleSimulation: () => void;
    codeQLOpen: boolean;
    onToggleCodeQL: () => void;
    semanticSearchEnabled: boolean;
    onToggleSemanticSearchMode: () => void;
    onRebuildRagIndex: () => void;
    ragReindexing: boolean;
    savedViewsOpen: boolean;
    onToggleSavedViews: () => void;
    inventoryOpen: boolean;
    onToggleInventory: () => void;
    onOpenSearchPanel: () => void;
    securityOpen: boolean;
    onToggleSecurity: () => void;
    selectedNodeName: string | null;
    lastScanLabel: string;
}

export default function TopBar({
    workspaces,
    onAddWorkspace,
    onScan,
    scanStatus,
    scanStats,
    askOpen,
    onAsk,
    dashboardOpen,
    onToggleDashboard,
    simulationOpen,
    onToggleSimulation,
    codeQLOpen,
    onToggleCodeQL,
    semanticSearchEnabled,
    onToggleSemanticSearchMode,
    onRebuildRagIndex,
    ragReindexing,
    savedViewsOpen,
    onToggleSavedViews,
    inventoryOpen,
    onToggleInventory,
    onOpenSearchPanel,
    securityOpen,
    onToggleSecurity,
    selectedNodeName,
    lastScanLabel,
}: TopBarProps) {
    const [inputPath, setInputPath] = useState('');

    const handleAdd = () => {
        const trimmed = inputPath.trim();
        if (trimmed && !workspaces.includes(trimmed)) {
            onAddWorkspace(trimmed);
            setInputPath('');
        }
    };

    const handleBrowseFolder = async () => {
        try {
            const response = await fetch('/api/system/browse-folder');
            const data = await response.json();
            if (data.path) setInputPath(data.path);
        } catch (error) {
            console.error('Failed to open folder picker:', error);
        }
    };

    const isScanning = scanStatus === 'scanning';
    const shortNodeLabel =
        selectedNodeName && selectedNodeName.length > 18
            ? `${selectedNodeName.slice(0, 18)}…`
            : selectedNodeName;
    const aiLabel = shortNodeLabel ? `Ask about ${shortNodeLabel}` : 'AI Assistant';

    const navItems = [
        {
            id: 'dashboard',
            label: 'Dashboard',
            active: dashboardOpen,
            onClick: onToggleDashboard,
            icon: (
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <rect x="1" y="1" width="6" height="6" rx="1.5" fill="currentColor" opacity="0.9"/>
                    <rect x="9" y="1" width="6" height="6" rx="1.5" fill="currentColor" opacity="0.9"/>
                    <rect x="1" y="9" width="6" height="6" rx="1.5" fill="currentColor" opacity="0.9"/>
                    <rect x="9" y="9" width="6" height="6" rx="1.5" fill="currentColor" opacity="0.9"/>
                </svg>
            ),
        },
        {
            id: 'security',
            label: 'Security',
            active: securityOpen,
            onClick: onToggleSecurity,
            icon: (
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M8 1L2 3.5v3.75C2 10.5 5 13.75 8 15c3-1.25 6-4.5 6-7.75V3.5L8 1z" fill="currentColor" opacity="0.9"/>
                </svg>
            ),
        },
        {
            id: 'codeql',
            label: 'CodeQL',
            active: codeQLOpen,
            onClick: onToggleCodeQL,
            icon: (
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <polyline points="4,6 1,8 4,10" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
                    <polyline points="12,6 15,8 12,10" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
                    <line x1="9" y1="2" x2="7" y2="14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
            ),
        },
        {
            id: 'inventory',
            label: 'API Inventory',
            active: inventoryOpen,
            onClick: onToggleInventory,
            icon: (
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <rect x="1" y="1" width="14" height="3.5" rx="1" fill="currentColor" opacity="0.9"/>
                    <rect x="1" y="6.25" width="14" height="3.5" rx="1" fill="currentColor" opacity="0.7"/>
                    <rect x="1" y="11.5" width="14" height="3.5" rx="1" fill="currentColor" opacity="0.5"/>
                </svg>
            ),
        },
        {
            id: 'views',
            label: 'Views',
            active: savedViewsOpen,
            onClick: onToggleSavedViews,
            icon: (
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M8 3C4 3 1 8 1 8s3 5 7 5 7-5 7-5-3-5-7-5z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round"/>
                    <circle cx="8" cy="8" r="2" fill="currentColor"/>
                </svg>
            ),
        },
        {
            id: 'search',
            label: 'Search',
            active: false,
            onClick: onOpenSearchPanel,
            icon: (
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <circle cx="6.5" cy="6.5" r="4.5" stroke="currentColor" strokeWidth="1.5" fill="none"/>
                    <line x1="10" y1="10" x2="14" y2="14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
            ),
        },
        {
            id: 'semantic',
            label: semanticSearchEnabled ? 'Semantic ON' : 'Semantic OFF',
            active: semanticSearchEnabled,
            onClick: onToggleSemanticSearchMode,
            title: 'Toggle semantic embeddings in search',
            icon: (
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <circle cx="4" cy="8" r="2.5" fill="currentColor" opacity="0.9"/>
                    <circle cx="12" cy="4" r="2.5" fill="currentColor" opacity="0.7"/>
                    <circle cx="12" cy="12" r="2.5" fill="currentColor" opacity="0.7"/>
                    <line x1="6" y1="7" x2="10" y2="5" stroke="currentColor" strokeWidth="1" opacity="0.5"/>
                    <line x1="6" y1="9" x2="10" y2="11" stroke="currentColor" strokeWidth="1" opacity="0.5"/>
                </svg>
            ),
        },
        {
            id: 'reindex',
            label: ragReindexing ? 'Reindexing…' : 'Reindex RAG',
            active: false,
            onClick: onRebuildRagIndex,
            disabled: ragReindexing,
            icon: (
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M13.5 2.5C12 1 10 0.5 8 0.5A7.5 7.5 0 0 0 0.5 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" fill="none"/>
                    <polyline points="0.5,4 0.5,8 4.5,8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
                    <path d="M2.5 13.5C4 15 6 15.5 8 15.5A7.5 7.5 0 0 0 15.5 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" fill="none"/>
                    <polyline points="15.5,12 15.5,8 11.5,8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
                </svg>
            ),
        },
    ];

    return (
        <div className="topbar-wrapper">
            {/* Row 1: Logo + Workspace Input + Primary Actions */}
            <div className="topbar topbar-main">
                <div className="topbar-logo">
                    <div className="icon">
                        <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
                            <circle cx="10" cy="10" r="3" fill="white"/>
                            <circle cx="3" cy="4" r="2" fill="white" opacity="0.7"/>
                            <circle cx="17" cy="4" r="2" fill="white" opacity="0.7"/>
                            <circle cx="3" cy="16" r="2" fill="white" opacity="0.7"/>
                            <circle cx="17" cy="16" r="2" fill="white" opacity="0.7"/>
                            <line x1="5" y1="5.5" x2="8.5" y2="8.5" stroke="white" strokeWidth="1" opacity="0.6"/>
                            <line x1="15" y1="5.5" x2="11.5" y2="8.5" stroke="white" strokeWidth="1" opacity="0.6"/>
                            <line x1="5" y1="14.5" x2="8.5" y2="11.5" stroke="white" strokeWidth="1" opacity="0.6"/>
                            <line x1="15" y1="14.5" x2="11.5" y2="11.5" stroke="white" strokeWidth="1" opacity="0.6"/>
                        </svg>
                    </div>
                    <span>InsightGraph</span>
                </div>

                <div className="topbar-input-group">
                    <input
                        className="topbar-input"
                        type="text"
                        value={inputPath}
                        onChange={(e) => setInputPath(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                        placeholder="C:\\path\\to\\project ..."
                        disabled={isScanning}
                    />
                    <button className="btn btn-secondary" onClick={handleBrowseFolder} disabled={isScanning}>
                        Browse
                    </button>
                    <button className="btn btn-secondary" onClick={handleAdd} disabled={isScanning || !inputPath.trim()}>
                        Add
                    </button>
                </div>

                <div className="topbar-primary-actions">
                    <button
                        className={`btn btn-primary scan-btn ${isScanning ? 'scanning' : ''}`}
                        onClick={onScan}
                        disabled={isScanning || workspaces.length === 0}
                    >
                        {isScanning ? (
                            <>
                                <span className="scan-spinner" />
                                Scanning…
                            </>
                        ) : (
                            <>
                                <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                                    <path d="M8 1v7M8 1L5 4M8 1l3 3" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                                    <path d="M2 10v3a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-3" stroke="white" strokeWidth="1.5" strokeLinecap="round" fill="none"/>
                                </svg>
                                Run new scan
                            </>
                        )}
                    </button>

                    <button
                        className={`btn ${simulationOpen ? 'btn-accent active' : 'btn-secondary'}`}
                        onClick={onToggleSimulation}
                        title="Run architecture simulation"
                    >
                        <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                            <path d="M14 5.5c0 5-7 9-7 9s-7-4-7-9a7 7 0 0 1 14 0z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round"/>
                            <circle cx="7" cy="5.5" r="2.5" fill="currentColor"/>
                        </svg>
                        Simulate
                    </button>

                    <button
                        className={`btn ${askOpen ? 'btn-accent active' : 'btn-accent'}`}
                        onClick={onAsk}
                        disabled={isScanning}
                        title={isScanning ? 'Wait for scan to finish' : aiLabel}
                    >
                        <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                            <path d="M14 9.5a1 1 0 0 1-1 1H5l-3 3V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6.5z" fill="currentColor" opacity="0.9"/>
                            <circle cx="5.5" cy="6.5" r="0.8" fill="white"/>
                            <circle cx="8" cy="6.5" r="0.8" fill="white"/>
                            <circle cx="10.5" cy="6.5" r="0.8" fill="white"/>
                        </svg>
                        {aiLabel}
                    </button>
                </div>

                <div className="topbar-status">
                    <div className={`status-indicator ${isScanning ? 'scanning' : ''}`}>
                        <span className={`status-dot ${isScanning ? 'scanning' : ''} ${scanStatus === 'error' ? 'error' : ''}`} />
                        {scanStatus === 'idle' && <span>Ready</span>}
                        {isScanning && (
                            <span>
                                {scanStats.progress > 0
                                    ? `${scanStats.progress.toFixed(0)}% · ${scanStats.files} files`
                                    : `Scanning… ${scanStats.files} files`}
                            </span>
                        )}
                        {scanStatus === 'completed' && <span>{scanStats.nodes.toLocaleString()} nodes · {scanStats.rels.toLocaleString()} edges</span>}
                        {scanStatus === 'error' && <span>Error</span>}
                    </div>
                    <div className="topbar-scan-info">{lastScanLabel}</div>
                </div>

                {isScanning && (
                    <div className="scan-progress">
                        <div className="scan-progress-bar" style={{ width: `${scanStats.progress || 2}%` }} />
                    </div>
                )}
            </div>

            {/* Row 2: Navigation Tabs */}
            <div className="topbar-nav">
                <nav className="nav-tabs">
                    {navItems.map((item) => (
                        <button
                            key={item.id}
                            className={`nav-tab ${item.active ? 'active' : ''} ${(item as any).disabled ? 'disabled' : ''}`}
                            onClick={item.onClick}
                            title={(item as any).title ?? item.label}
                            disabled={(item as any).disabled}
                        >
                            <span className="nav-tab-icon">{item.icon}</span>
                            <span className="nav-tab-label">{item.label}</span>
                        </button>
                    ))}
                </nav>
            </div>
        </div>
    );
}
