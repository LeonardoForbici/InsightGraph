import { useState } from 'react';

interface TopBarProps {
    workspaces: string[];
    onAddWorkspace: (path: string) => void;
    onRemoveWorkspace: (path: string) => void;
    onScan: () => void;
    scanStatus: string;
    scanStats: { files: number; nodes: number; rels: number; progress: number; currentFile: string };
    askOpen: boolean;
    onToggleAsk: () => void;
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
}

export default function TopBar({
    workspaces,
    onAddWorkspace,
    onScan,
    scanStatus,
    scanStats,
    askOpen,
    onToggleAsk,
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

    return (
        <div className="topbar">
            <div className="topbar-logo">
                <div className="icon">IG</div>
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
                <button className="btn btn-primary" onClick={onScan} disabled={isScanning || workspaces.length === 0}>
                    {isScanning ? 'Scanning...' : 'Scan All'}
                </button>
            </div>

            <div className="topbar-actions">
                <button
                    className={`btn ${simulationOpen ? 'btn-accent' : 'btn-secondary'}`}
                    onClick={onToggleSimulation}
                    title="Run architecture simulation"
                >
                    Simulate
                </button>
                <button
                    className={`btn btn-secondary ${dashboardOpen ? 'active' : ''}`}
                    onClick={onToggleDashboard}
                    title="Open architectural dashboard"
                >
                    Dashboard
                </button>
                <button
                    className={`btn ${codeQLOpen ? 'btn-accent' : 'btn-secondary'}`}
                    onClick={onToggleCodeQL}
                    title="Open CodeQL security analysis"
                >
                    CodeQL
                </button>
                <button
                    className={`btn ${inventoryOpen ? 'btn-accent' : 'btn-secondary'}`}
                    onClick={onToggleInventory}
                    title="Explore API inventory"
                >
                    API Inventory
                </button>
                <button
                    className={`btn ${savedViewsOpen ? 'btn-accent' : 'btn-secondary'}`}
                    onClick={onToggleSavedViews}
                    title="Manage saved views"
                >
                    Saved Views
                </button>
                <button
                    className={`btn btn-accent ${askOpen ? 'active' : ''}`}
                    onClick={onToggleAsk}
                    disabled={isScanning}
                    title={isScanning ? 'Wait for scan to finish' : 'Ask the AI assistant'}
                >
                    AI Assistant
                </button>
                <button
                    className="btn btn-secondary"
                    onClick={onOpenSearchPanel}
                    title="Abrir busca semântica avançada"
                >
                    Buscar
                </button>
                <button
                    className="btn btn-secondary"
                    onClick={onToggleSemanticSearchMode}
                    title="Toggle semantic embeddings in search"
                >
                    {semanticSearchEnabled ? 'Semantic ON' : 'Semantic OFF'}
                </button>
                <button
                    className="btn btn-secondary"
                    onClick={onRebuildRagIndex}
                    disabled={ragReindexing}
                    title="Rebuild RAG index and embeddings locally"
                >
                    {ragReindexing ? 'Reindexing...' : 'Reindex RAG'}
                </button>
            </div>

            <div className="topbar-status">
                <div className="status-indicator">
                    <span className={`status-dot ${isScanning ? 'scanning' : ''} ${scanStatus === 'error' ? 'error' : ''}`} />
                    {scanStatus === 'idle' && <span>Ready</span>}
                    {isScanning && (
                        <span>
                            {scanStats.progress > 0
                                ? `${scanStats.progress.toFixed(0)}% · ${scanStats.files} files`
                                : `Scanning... ${scanStats.files} files`}
                        </span>
                    )}
                    {scanStatus === 'completed' && <span>{scanStats.nodes} nodes · {scanStats.rels} edges</span>}
                    {scanStatus === 'error' && <span>Error</span>}
                </div>
            </div>

            {isScanning && (
                <div className="scan-progress">
                    <div className="scan-progress-bar" style={{ width: `${scanStats.progress || 2}%` }} />
                </div>
            )}
        </div>
    );
}
