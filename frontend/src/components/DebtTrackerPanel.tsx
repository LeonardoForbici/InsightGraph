import { useEffect, useState } from 'react';
import type { DebtTrackerPayload } from '../api';
import { fetchDebtTracker } from '../api';

export default function DebtTrackerPanel() {
  const [data, setData] = useState<DebtTrackerPayload | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const payload = await fetchDebtTracker();
      setData(payload);
    } catch (err) {
      console.error('Falha ao carregar debt tracker', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="debt-panel">
      <div className="debt-header">
        <div>
          <h3>Technical Debt Tracker</h3>
          <p className="section-desc">Score total, projeções e quick wins com alto impacto.</p>
        </div>
        <button className="btn btn-secondary" onClick={load} disabled={loading}>
          {loading ? 'Atualizando...' : 'Atualizar'}
        </button>
      </div>

      {!data && !loading && <div className="debt-empty">Nenhum scan disponível ainda.</div>}

      {data && (
        <>
          <div className="debt-cards">
            <div className="debt-card">
              <span>Debt Score</span>
              <strong>{data.score}</strong>
            </div>
            <div className="debt-card">
              <span>Projeção 30 dias</span>
              <strong>{data.projection}</strong>
            </div>
            <div className="debt-card">
              <span>Quick Wins</span>
              <strong>{data.quick_wins.length}</strong>
            </div>
          </div>

          <div className="debt-history">
            <h4>Histórico de risco</h4>
            <div className="history-chart">
              {data.history.map((point) => (
                <div key={point.timestamp} className="history-bar">
                  <span className="history-value">{point.risk}</span>
                  <span className="history-label">{point.timestamp?.split('T')[0] || '---'}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="debt-quick-wins">
            <h4>Quick Wins</h4>
            <div className="debt-table">
              <div className="debt-row header">
                <span>Nome</span>
                <span>Hotspot</span>
                <span>Dependentes</span>
              </div>
              {data.quick_wins.map((win) => (
                <div key={win.namespace_key} className="debt-row">
                  <span>{win.name || win.namespace_key}</span>
                  <span>{win.hotspot_score.toFixed(1)}</span>
                  <span>{win.dependents}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
