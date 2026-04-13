import { useEffect, useRef } from 'react';

export interface NeonPoint {
  x: number;
  y: number;
}

interface NeonRendererProps {
  width: number;
  height: number;
  landmarks: NeonPoint[];
  enabled: boolean;
  trackingOnly?: boolean;
}

interface TrailParticle {
  x: number;
  y: number;
  life: number;
}

const FINGERTIPS = [4, 8, 12, 16, 20];

export default function NeonRenderer({
  width,
  height,
  landmarks,
  enabled,
  trackingOnly = false,
}: NeonRendererProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const particlesRef = useRef<TrailParticle[]>([]);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!enabled) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      const canvas = canvasRef.current;
      const ctx = canvas?.getContext('2d');
      if (ctx && canvas) ctx.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }

    const draw = () => {
      const canvas = canvasRef.current;
      const ctx = canvas?.getContext('2d');
      if (!ctx || !canvas) return;

      canvas.width = width;
      canvas.height = height;

      const now = performance.now();
      const cycle = (now % 3000) / 3000;
      const r = Math.round(80 + 140 * Math.sin(cycle * Math.PI * 2));
      const g = Math.round(180 + 70 * Math.sin((cycle + 0.33) * Math.PI * 2));
      const b = Math.round(230 + 25 * Math.sin((cycle + 0.66) * Math.PI * 2));
      const neon = `rgb(${r}, ${g}, ${b})`;

      ctx.clearRect(0, 0, width, height);
      if (!trackingOnly) {
        ctx.fillStyle = 'rgba(0,0,0,0.7)';
        ctx.fillRect(0, 0, width, height);
      }

      const particles = particlesRef.current;
      particles.forEach((p) => {
        p.life -= 0.02;
      });
      particlesRef.current = particles.filter((p) => p.life > 0);

      for (const p of particlesRef.current) {
        ctx.globalAlpha = Math.max(0, p.life);
        ctx.fillStyle = neon;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 2, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      if (landmarks.length >= 21) {
        const palm = landmarks[9];
        for (const tipIndex of FINGERTIPS) {
          const tip = landmarks[tipIndex];
          if (!tip) continue;

          particlesRef.current.push({ x: tip.x, y: tip.y, life: 0.8 });

          ctx.strokeStyle = neon;
          ctx.lineWidth = 1.2;
          ctx.shadowColor = neon;
          ctx.shadowBlur = 10;
          ctx.beginPath();
          ctx.moveTo(tip.x, tip.y);
          ctx.lineTo(palm.x, palm.y);
          ctx.stroke();

          ctx.beginPath();
          ctx.fillStyle = neon;
          ctx.arc(tip.x, tip.y, 8, 0, Math.PI * 2);
          ctx.fill();
        }

        // Adjacent fingertip threads
        const threadPairs = [
          [4, 8],
          [8, 12],
          [12, 16],
          [16, 20],
        ];
        ctx.lineWidth = 0.8;
        for (const [a, b] of threadPairs) {
          const p1 = landmarks[a];
          const p2 = landmarks[b];
          if (!p1 || !p2) continue;
          ctx.beginPath();
          ctx.moveTo(p1.x, p1.y);
          ctx.lineTo(p2.x, p2.y);
          ctx.stroke();
        }
        ctx.shadowBlur = 0;
      }

      rafRef.current = requestAnimationFrame(draw);
    };

    rafRef.current = requestAnimationFrame(draw);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [enabled, height, landmarks, trackingOnly, width]);

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
    />
  );
}

