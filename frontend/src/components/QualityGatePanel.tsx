import { useCallback, useEffect, useMemo, useState } from 'react';
import type { QualityGateResult, QualityThresholds } from '../api';
import { evaluateQualityGate, fetchQualityGateHistory } from '../api';

const PROFILE_PRESETS: Record<string, QualityThresholds> = {
  strict: { max_god_classes: 20, min_call_resolution: 0.85, max_hotspot_score: 55, min_iso5055: 90 },
  balanced: { max_god_classes: 45, min_call_resolution: 0.75, max_hotspot_score: 70, min_iso5055: 80 },
  relaxed: { max_god_classes: 80, min_call_resolution: 0.6, max_hotspot_score: 85, min_iso5055: 70 },
};

const SLIDER_CONFIG = [
  { key: 'max_god_classes', label: 'Máx. God Classes', min: 0, max: 200, step: 1 },
  { key: 'min_call_resolution', label: 'Min. Call Resolution (%)', min: 0, max: 100, step: 1, scale: 100 },
  { key: 'max_hotspot_score', label: 'Máx. Hotspot Score', min: 0, max: 100, step: 1 },
  { key: 'min_iso5055', label: 'Min. ISO 5055 (%)', min: 0, max: 100, step: 1 },
];

export default function QualityGatePanel() {
  const [thresholds, setThresholds] = useState<QualityThresholds>(PROFILE_PRESETS.balanced);
  const [activeProfile, setActiveProfile] = useState('balanced');
  const [result, setResult] = useState<QualityGateResult | null>(null);
  const [history, setHistory] = useState<QualityGateResult[]>([]);
  const [loading, setLoading] = useState(false);

  const loadHistory = useCallback(async () => {
    try {
      const payload = await fetchQualityGateHistory(8);
      setHistory(payload.entries.reverse());
    } catch (err) {
      console.error('Failed to fetch quality gate history', err);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const handleProfile = (profile: string) => {
    const preset = PROFILE_PRESETS[profile] || PROFILE_PRESETS.balanced;
    setThresholds(preset);
    setActiveProfile(profile);
  };

  const updateThreshold = (key: keyof QualityThresholds, value: number) => {
    setThresholds((prev) => ({
      ...prev,
      [key]: key === 'min_call_resolution' ? Number((value / 100).toFixed(2)) : value,
    }));
    setActiveProfile('custom');
  };

  const handleEvaluate = async () => {
    setLoading(true);
    try {
      const payload = await evaluateQualityGate(thresholds);
      setResult(payload);
      loadHistory();
    } catch (err) {
      console.error('Quality gate evaluation failed', err);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = () => {
    const payload = result || history[0];
    if (!payload) return;
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `quality-gate-${payload.timestamp || 'result'}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  const historySummary = useMemo(
    () =>
      history.map((entry) => ({
        ...entry,
        status: entry.passed ? 'PASS' : 'FAIL',
      })),
    [history]
  );

  return (
    <div className="quality-panel">
      <div className="quality-header">
        <div>
          <h3>Quality Gate</h3>
          <p className="section-desc">Configure limiares e registre o histórico para pipelines CI/CD.</p>
        </div>
        <div className="quality-actions">
          {Object.keys(PROFILE_PRESETS).map((profile) => (
            <button
              key={profile}
              className={`btn btn-secondary ${activeProfile === profile ? 'active' : ''}`}
              onClick={() => handleProfile(profile)}
            >
              {profile.charAt(0).toUpperCase() + profile.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="quality-sliders">
        {SLIDER_CONFIG.map((slider) => {
          const displayValue =
            slider.key === 'min_call_resolution'
              ? Math.round((thresholds[slider.key as keyof QualityThresholds] as number) * 100)
              : thresholds[slider.key as keyof QualityThresholds];
          return (
            <label key={slider.key} className="quality-slider">
              <span>
                {slider.label}: <strong>{displayValue}</strong>
              </span>
              <input
                type="range"
                min={slider.min}
                max={slider.max}
                step={slider.step}
                value={slider.key === 'min_call_resolution' ? displayValue : thresholds[slider.key as keyof QualityThresholds]}
                onChange={(event) => updateThreshold(slider.key as keyof QualityThresholds, Number(event.target.value))}
              />
            </label>
          );
        })}
      </div>

      <div className="quality-footer">
        <button className="btn btn-accent" onClick={handleEvaluate} disabled={loading}>
          {loading ? 'Avaliando...' : 'Avaliar Gate'}
        </button>
        <button className="btn btn-secondary" onClick={handleExport} disabled={!result && !history.length}>
          Exportar JSON
        </button>
        {result && (
          <span className={`quality-result badge ${result.passed ? 'passed' : 'failed'}`}>
            {result.passed ? 'PASS' : 'FAIL'} · Score {result.score}
          </span>
        )}
      </div>

      {historySummary.length > 0 && (
        <div className="quality-history">
          <h4>Histórico recente</h4>
          <div className="history-grid">
            {historySummary.map((entry) => (
              <div key={entry.timestamp} className={`history-card ${entry.passed ? 'pass' : 'fail'}`}>
                <div className="history-status">
                  <span>{entry.status}</span>
                  <span>{entry.score}</span>
                </div>
                <p>{entry.timestamp}</p>
                <small>{entry.violations.length ? entry.violations.join(' · ') : 'Nenhuma violação'}</small>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
