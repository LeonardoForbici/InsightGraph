import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { scaleLinear } from 'd3-scale';
import { interpolateRdYlGn } from 'd3-scale-chromatic';

export interface WaveAnimatorTrigger {
  originNodeKey: string;
  affectedNodes: string[];
  timestamp: number;
  riskScore?: number;
}

interface WaveAnimatorProps {
  trigger: WaveAnimatorTrigger | null;
}

const BASE_DURATION = 1400;
const PULSE_COUNT = 4;

const WaveAnimator: React.FC<WaveAnimatorProps> = ({ trigger }) => {
  const [pulseId, setPulseId] = useState(0);
  const [speed, setSpeed] = useState(1);

  const duration = useMemo(() => BASE_DURATION / Math.max(speed, 0.3), [speed]);
  const pulseOffsets = useMemo(() => Array.from({ length: PULSE_COUNT }), []);
  const colorScale = useMemo(() => scaleLinear<number>().domain([0, 100]).clamp(true), []);

  useEffect(() => {
    if (trigger) {
      setPulseId((prev) => prev + 1);
    }
  }, [trigger]);

  if (!trigger) {
    return null;
  }

  const riskScore = Math.max(0, Math.min(100, trigger.riskScore ?? 0));
  const riskRatio = colorScale(riskScore);
  const waveColor = interpolateRdYlGn(1 - riskRatio);
  const severity =
    riskScore >= 70 ? 'Crítico' :
    riskScore >= 40 ? 'Alto' :
    riskScore >= 20 ? 'Médio' :
    'Baixo';

  const detailLabel =
    trigger.affectedNodes.length > 0
      ? `${trigger.affectedNodes.length} nód${trigger.affectedNodes.length === 1 ? 'o' : 'os'} impactado${trigger.affectedNodes.length === 1 ? '' : 's'}`
      : 'Nenhum nó visível';

  return (
    <div className="wave-animator-overlay" key={`wave-${trigger.timestamp}-${pulseId}`}>
      <div
        className="wave-animator-panel"
        style={{ '--wave-color': waveColor } as CSSProperties}
        role="status"
        aria-live="polite"
      >
        <div className="wave-animator-ring">
          {pulseOffsets.map((_, index) => (
            <span
              key={`wave-${pulseId}-${index}`}
              className="wave-animator__pulse"
              style={{
                animationDuration: `${duration}ms`,
                animationDelay: `${index * (duration / PULSE_COUNT)}ms`,
                borderColor: waveColor,
              }}
            />
          ))}
          <div className="wave-animator__center">
            <span className="wave-animator__severity">{severity}</span>
            <strong>{trigger.originNodeKey}</strong>
            <span className="wave-animator__detail">{detailLabel}</span>
          </div>
        </div>
        <div className="wave-animator__speed-controls">
          <label htmlFor="wave-speed-slider">Velocidade</label>
          <div className="wave-animator__speed-input">
            <input
              id="wave-speed-slider"
              type="range"
              min={0.5}
              max={2}
              step={0.1}
              value={speed}
              onChange={(event) => setSpeed(Number(event.target.value))}
            />
            <span>{speed.toFixed(1)}x</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default WaveAnimator;
