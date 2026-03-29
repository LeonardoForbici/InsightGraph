import { useState } from 'react';
import type { GraphStats } from '../api';

interface ScanStats {
  files: number;
  nodes: number;
  rels: number;
  progress: number;
  currentFile: string;
}

interface InventoryPanelProps {
  stats: GraphStats | null;
  projects: string[];
  workspaces: string[];
  scanStatus: string;
  scanStats: ScanStats;
}

const LEGEND_GROUPS = [
  { title: 'Frontend', color: '#60a5fa' },
  { title: 'API', color: '#a78bfa' },
  { title: 'Service', color: '#fbbf24' },
  { title: 'Database', color: '#34d399' },
];

const formatNumber = (value: number | null | undefined) =>
  value == null ? '—' : value.toLocaleString('pt-BR');

export default function InventoryPanel({
  stats,
  projects,
  workspaces,
  scanStatus,
  scanStats,
}: InventoryPanelProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const progress = Math.min(100, Math.max(0, scanStats.progress));
  const isScanning = scanStatus === 'scanning';

  const density =
    stats && stats.total_nodes > 0
      ? `${(stats.total_edges / stats.total_nodes).toFixed(1)} conexões/nó`
      : '—';

  const cardData = [
    { label: 'Nós modelados', value: stats?.total_nodes, icon: '🧩' },
    { label: 'Conexões mapeadas', value: stats?.total_edges, icon: '🔗' },
    { label: 'Projetos existentes', value: projects.length, icon: '📦' },
    { label: 'Workspaces ativos', value: workspaces.length, icon: '🗂️' },
  ];

  return (
    <div className={`inventory-panel ${isCollapsed ? 'collapsed' : ''}`}>
      <div 
        className="inventory-panel-heading" 
        onClick={() => setIsCollapsed(!isCollapsed)}
        title={isCollapsed ? "Expandir insights" : "Esconder insights para ver mais do grafo"}
      >
        <div className="inventory-heading-left">
          <div className="inventory-heading-icon">
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
              <path d="M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16z" stroke="currentColor" strokeWidth="1.5" fill="none" opacity="0.8"/>
              <path d="M10 6v4l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <div>
            <strong>Insights atuais</strong>
            <p className="inventory-heading-subtitle">
              Métricas selecionadas para orientar o próximo movimento.
            </p>
          </div>
        </div>
        
        <div className="inventory-heading-right">
          <span className={`inventory-heading-pill ${isScanning ? 'scanning' : 'stable'}`}>
            {isScanning ? 'Scan em andamento' : 'Último scan estável'}
          </span>
          <button className={`btn-collapse-panel ${isCollapsed ? 'collapsed' : ''}`} aria-label="Toggle Insights">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <polyline points="4,10 8,6 12,10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
            </svg>
          </button>
        </div>
      </div>

      {!isCollapsed && (
        <div className="inventory-panel-body">
          <div className="inventory-panel-grid">
            {cardData.map((card) => (
              <div key={card.label} className="inventory-card">
                <div className="inventory-card-icon">{card.icon}</div>
                <div className="inventory-card-content">
                  <span className="inventory-card-label">{card.label}</span>
                  <strong className="inventory-card-value">
                    {formatNumber(card.value as number | undefined)}
                  </strong>
                </div>
              </div>
            ))}
          </div>

          <div className="inventory-panel-summary">
            <div className="inventory-summary-block">
              <p>Status do scan</p>
              <strong className="inventory-summary-value">
                {isScanning ? `Scaneando ${formatNumber(scanStats.files)} arquivos` : scanStatus}
              </strong>
              <div className="inventory-progress-bar">
                <div className="inventory-progress-fill" style={{ width: `${progress}%` }} />
              </div>
              {scanStats.currentFile && (
                <span className="inventory-summary-caption">Atual: {scanStats.currentFile}</span>
              )}
            </div>
            <div className="inventory-summary-block">
              <p>Camadas principais</p>
              <div className="inventory-panel-legend-list">
                {LEGEND_GROUPS.map((group) => (
                  <div key={group.title} className="legend-pill">
                    <span className="legend-dot" style={{ background: group.color }} />
                    <span>{group.title}</span>
                  </div>
                ))}
              </div>
              <span className="inventory-summary-caption">Densidade média: {density}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
