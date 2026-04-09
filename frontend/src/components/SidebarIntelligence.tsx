import React, { useEffect, useState, useCallback, useRef } from 'react';

interface RiskItem {
  node_key: string;
  name: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  score: number;
  trend: 'improving' | 'worsening' | 'stable';
  reason: string;
}

interface HotspotItem {
  node_key: string;
  name: string;
  hotspot_score: number;
  complexity: number;
  change_frequency: number;
}

interface InstabilityItem {
  node_key: string;
  name: string;
  change_count: number;
  impact_radius: number;
  last_changed: string;
}

interface IntelligenceData {
  risks: RiskItem[];
  hotspots: HotspotItem[];
  instabilities: InstabilityItem[];
}

interface SidebarIntelligenceProps {
  onNodeClick: (nodeKey: string) => void;
  refreshTrigger?: number; // Optional trigger to force refresh
}

const SidebarIntelligence: React.FC<SidebarIntelligenceProps> = ({ 
  onNodeClick,
  refreshTrigger 
}) => {
  const [data, setData] = useState<IntelligenceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchIntelligence = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetch('/api/intelligence/summary');
      if (!response.ok) {
        throw new Error(`Failed to fetch intelligence: ${response.statusText}`);
      }
      
      const result = await response.json();
      setData(result);
    } catch (err) {
      console.error('Failed to fetch intelligence summary:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounced refresh function (500ms delay)
  const debouncedRefresh = useCallback(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    
    debounceTimerRef.current = setTimeout(() => {
      fetchIntelligence();
    }, 500);
  }, [fetchIntelligence]);

  // Initial load
  useEffect(() => {
    fetchIntelligence();
  }, [fetchIntelligence]);

  // Refresh when trigger changes (debounced)
  useEffect(() => {
    if (refreshTrigger !== undefined && refreshTrigger > 0) {
      debouncedRefresh();
    }
  }, [refreshTrigger, debouncedRefresh]);

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  const getSeverityColor = (severity: string): string => {
    switch (severity) {
      case 'critical':
        return 'var(--accent-rose)';
      case 'high':
        return 'var(--accent-orange)';
      case 'medium':
        return 'var(--accent-amber)';
      case 'low':
        return 'var(--accent-emerald)';
      default:
        return 'var(--text-secondary)';
    }
  };

  const getTrendIcon = (trend: string): string => {
    switch (trend) {
      case 'worsening':
        return '↑';
      case 'improving':
        return '↓';
      case 'stable':
      default:
        return '→';
    }
  };

  const getTrendColor = (trend: string): string => {
    switch (trend) {
      case 'worsening':
        return 'var(--accent-rose)';
      case 'improving':
        return 'var(--accent-emerald)';
      case 'stable':
      default:
        return 'var(--text-muted)';
    }
  };

  if (loading && !data) {
    return (
      <div className="sidebar-intelligence">
        <div className="intelligence-loading">
          <div className="spinner" />
          <p>Carregando inteligência...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="sidebar-intelligence">
        <div className="intelligence-error">
          <p>Erro ao carregar: {error}</p>
          <button onClick={fetchIntelligence} className="btn btn-secondary">
            Tentar novamente
          </button>
        </div>
      </div>
    );
  }

  if (!data) {
    return null;
  }

  return (
    <div className="sidebar-intelligence">
      {/* Critical Risks Section */}
      <div className="intelligence-section">
        <h3 className="intelligence-section-title">
          <span className="intelligence-icon">⚠️</span>
          Riscos Críticos
        </h3>
        {data.risks.length === 0 ? (
          <p className="intelligence-empty">Nenhum risco crítico detectado</p>
        ) : (
          <div className="intelligence-list">
            {data.risks.map((risk) => (
              <div
                key={risk.node_key}
                className="intelligence-item"
                onClick={() => onNodeClick(risk.node_key)}
              >
                <div className="intelligence-item-header">
                  <span
                    className="intelligence-badge"
                    style={{ backgroundColor: getSeverityColor(risk.severity) }}
                  >
                    {risk.severity}
                  </span>
                  <span
                    className="intelligence-trend"
                    style={{ color: getTrendColor(risk.trend) }}
                    title={`Tendência: ${risk.trend}`}
                  >
                    {getTrendIcon(risk.trend)}
                  </span>
                </div>
                <p className="intelligence-item-name" title={risk.name}>
                  {risk.name}
                </p>
                <p className="intelligence-item-detail">
                  Score: {risk.score.toFixed(1)} • {risk.reason}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Hotspots Section */}
      <div className="intelligence-section">
        <h3 className="intelligence-section-title">
          <span className="intelligence-icon">🔥</span>
          Hotspots
        </h3>
        {data.hotspots.length === 0 ? (
          <p className="intelligence-empty">Nenhum hotspot detectado</p>
        ) : (
          <div className="intelligence-list">
            {data.hotspots.map((hotspot) => (
              <div
                key={hotspot.node_key}
                className="intelligence-item"
                onClick={() => onNodeClick(hotspot.node_key)}
              >
                <p className="intelligence-item-name" title={hotspot.name}>
                  {hotspot.name}
                </p>
                <p className="intelligence-item-detail">
                  Score: {hotspot.hotspot_score.toFixed(1)} • 
                  Complexidade: {hotspot.complexity} • 
                  Mudanças: {hotspot.change_frequency}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Instabilities Section */}
      <div className="intelligence-section">
        <h3 className="intelligence-section-title">
          <span className="intelligence-icon">⚡</span>
          Instabilidades
        </h3>
        {data.instabilities.length === 0 ? (
          <p className="intelligence-empty">Nenhuma instabilidade detectada</p>
        ) : (
          <div className="intelligence-list">
            {data.instabilities.map((instability) => (
              <div
                key={instability.node_key}
                className="intelligence-item"
                onClick={() => onNodeClick(instability.node_key)}
              >
                <p className="intelligence-item-name" title={instability.name}>
                  {instability.name}
                </p>
                <p className="intelligence-item-detail">
                  {instability.change_count} mudanças • 
                  Impacto: {instability.impact_radius} nós
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default SidebarIntelligence;
