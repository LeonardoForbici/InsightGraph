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
            if (data.path) {
                setInputPath(data.path);
            }
        } catch (error) {
            console.error('Failed to open folder picker:', error);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') handleAdd();
    };

    const isScanning = scanStatus === 'scanning';

    return (
        <div className="topbar">
            <div className="topbar-logo">
                <div className="icon">◆</div>
                <span>InsightGraph</span>
            </div>

            <div className="topbar-input-group">
                <input
                    className="topbar-input"
                    type="text"
                    value={inputPath}
                    onChange={(e) => setInputPath(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="C:\caminho\do\projeto ..."
                    disabled={isScanning}
                />
                <button className="btn btn-secondary" onClick={handleBrowseFolder} disabled={isScanning}>
                    📁 Procurar Pasta
                </button>
                <button className="btn btn-secondary" onClick={handleAdd} disabled={isScanning || !inputPath.trim()}>
                    + Adicionar
                </button>
                <button
                    className="btn btn-primary"
                    onClick={onScan}
                    disabled={isScanning || workspaces.length === 0}
                >
                    {isScanning ? '⟳ Escaneando...' : '▶ Escanear Tudo'}
                </button>
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
                <button
                    className={`btn ${simulationOpen ? 'btn-accent' : 'btn-secondary'}`}
                    onClick={onToggleSimulation}
                    title="Simular adição ou remoção de componentes"
                >
                    🧪 Simular
                </button>

                <button
                    className={`btn btn-secondary ${dashboardOpen ? 'active' : ''}`}
                    onClick={onToggleDashboard}
                    title="Ver Métricas Arquiteturais e Dashboard de Antipatterns"
                >
                    📊 Dashboard
                </button>

                <button
                    className={`btn btn-accent ${askOpen ? 'active' : ''}`}
                    onClick={onToggleAsk}
                    disabled={isScanning}
                    title={isScanning ? 'Aguarde o scan terminar' : 'Pergunte à IA sobre sua arquitetura'}
                >
                    🤖 IA Assistente
                </button>
            </div>

            <div className="topbar-status">
                <div className="status-indicator">
                    <span
                        className={`status-dot ${isScanning ? 'scanning' : ''} ${scanStatus === 'error' ? 'error' : ''}`}
                    />
                    {scanStatus === 'idle' && <span>Pronto</span>}
                    {isScanning && (
                        <span>
                            {scanStats.progress > 0
                                ? `${scanStats.progress.toFixed(0)}% · ${scanStats.files} arquivos`
                                : `Escaneando... ${scanStats.files} arquivos`}
                        </span>
                    )}
                    {scanStatus === 'completed' && (
                        <span>
                            ✓ {scanStats.nodes} nós · {scanStats.rels} conexões
                        </span>
                    )}
                    {scanStatus === 'error' && <span>Erro</span>}
                </div>
            </div>

            {/* Scan progress bar */}
            {isScanning && (
                <div className="scan-progress">
                    <div
                        className="scan-progress-bar"
                        style={{ width: `${scanStats.progress || 2}%` }}
                    />
                </div>
            )}
        </div>
    );
}
