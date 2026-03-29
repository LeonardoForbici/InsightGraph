const LEGEND_ENTRIES = [
  { label: 'TS (Component)', color: '#c084fc', icon: 'TS' },
  { label: 'Java (Service)', color: '#4f8ff7', icon: 'Java' },
  { label: 'SQL (DB)', color: '#34d399', icon: 'SQL' },
];

const NODE_KEY_TYPES = [
  { label: 'Frontend', badge: 'Frontend', color: '#60a5fa' },
  { label: 'API Endpoint', badge: 'API', color: '#a78bfa' },
  { label: 'Service', badge: 'Service', color: '#fbbf24' },
  { label: 'Database', badge: 'DB', color: '#34d399' },
];

interface FloatingLegendProps {
  onClose?: () => void;
}

export default function FloatingLegend({ onClose }: FloatingLegendProps) {
  return (
    <div className="floating-legend">
      <div className="floating-legend-header">
        <span>Legenda</span>
        {onClose && (
          <button className="legend-close-btn" onClick={onClose} aria-label="Fechar legenda">
            ×
          </button>
        )}
      </div>
      <div className="floating-legend-section">
        <div className="floating-legend-title">Grupos visuais</div>
        <div className="floating-legend-groups">
          {LEGEND_ENTRIES.map((entry) => (
            <div key={entry.label} className="floating-legend-group">
              <span className="floating-legend-icon" style={{ background: entry.color }}>
                {entry.icon}
              </span>
              <span>{entry.label}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="floating-legend-section">
        <div className="floating-legend-title">Tipos de nós</div>
        <div className="floating-legend-groups">
          {NODE_KEY_TYPES.map((item) => (
            <div key={item.label} className="floating-legend-group">
              <span className="floating-legend-dot" style={{ background: item.color }} />
              <span>
                {item.badge} • {item.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
