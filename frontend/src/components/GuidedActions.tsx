const GUIDED_ITEMS = [
  {
    title: 'Selecione um nó para ver impacto',
    description: 'Explore dependências críticas e o que cada mudança afetaria.',
    action: 'Ver análise',
    icon: (
      <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="10" r="4" stroke="currentColor" strokeWidth="1.8" fill="none"/>
        <circle cx="10" cy="3" r="2" fill="currentColor" opacity="0.6"/>
        <circle cx="10" cy="17" r="2" fill="currentColor" opacity="0.6"/>
        <circle cx="3" cy="10" r="2" fill="currentColor" opacity="0.6"/>
        <circle cx="17" cy="10" r="2" fill="currentColor" opacity="0.6"/>
        <line x1="10" y1="5" x2="10" y2="6.2" stroke="currentColor" strokeWidth="1.5"/>
        <line x1="10" y1="13.8" x2="10" y2="15" stroke="currentColor" strokeWidth="1.5"/>
        <line x1="5" y1="10" x2="6.2" y2="10" stroke="currentColor" strokeWidth="1.5"/>
        <line x1="13.8" y1="10" x2="15" y2="10" stroke="currentColor" strokeWidth="1.5"/>
      </svg>
    ),
    accentColor: 'var(--accent-blue)',
  },
  {
    title: 'Execute o Path Finder',
    description: 'Trace rotas entre dois nós para entender fluxos de dependência.',
    action: 'Abrir path finder',
    icon: (
      <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
        <circle cx="3" cy="10" r="2.5" fill="currentColor" opacity="0.8"/>
        <circle cx="17" cy="10" r="2.5" fill="currentColor" opacity="0.8"/>
        <path d="M5.5 10 Q10 4 14.5 10" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round"/>
        <path d="M5.5 10 Q10 16 14.5 10" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" opacity="0.4"/>
        <polyline points="12,7.5 14.5,10 12,12.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ),
    accentColor: 'var(--accent-violet)',
  },
  {
    title: 'Simule uma mudança',
    description: 'Teste hipóteses sem tocar no código real.',
    action: 'Simular mudança',
    icon: (
      <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
        <path d="M10 2L12.5 7H17.5L13.5 10.5L15 16L10 13L5 16L6.5 10.5L2.5 7H7.5L10 2Z" fill="currentColor" opacity="0.85"/>
      </svg>
    ),
    accentColor: 'var(--accent-emerald)',
  },
];

interface GuidedActionsProps {
  selectedNodeName: string | null;
  onImpact: () => void;
  onRunPathFinder: () => void;
  onSimulate: () => void;
}

export default function GuidedActions({ selectedNodeName, onImpact, onRunPathFinder, onSimulate }: GuidedActionsProps) {
  const handleAction = (index: number) => {
    if (index === 0) {
      onImpact();
    } else if (index === 1) {
      onRunPathFinder();
    } else {
      onSimulate();
    }
  };

  return (
    <div className="guided-actions">
      {GUIDED_ITEMS.map((item, index) => (
        <div key={item.title} className="guided-card" style={{ '--guided-accent': item.accentColor } as React.CSSProperties}>
          <div className="guided-card-icon" style={{ color: item.accentColor }}>{item.icon}</div>
          <div className="guided-card-body">
            <div className="guided-card-title">{item.title}</div>
            <p className="guided-card-desc">{item.description}</p>
          </div>
          <button
            className={`btn guided-card-button ${index === 0 && selectedNodeName ? 'btn-accent' : 'btn-secondary'}`}
            onClick={() => handleAction(index)}
            disabled={index === 0 && !selectedNodeName}
            title={index === 0 && !selectedNodeName ? 'Selecione primeiro um nó do grafo' : undefined}
          >
            {index === 0 && selectedNodeName
              ? `Analisar ${selectedNodeName}`
              : item.action}
          </button>
        </div>
      ))}
    </div>
  );
}
