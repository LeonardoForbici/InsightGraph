import { useEffect, useMemo, useRef, useState } from 'react';

interface GestureControllerProps {
    enabled: boolean;
    onSelectNode?: (x: number, y: number) => void;
    onDragNode?: (dx: number, dy: number) => void;
    onRotateCamera?: (delta: number) => void;
    onReset?: () => void;
}

type GestureName = 'pinch' | 'drag' | 'rotate' | 'open_hand' | 'none';

export default function GestureController({
    enabled,
    onSelectNode,
    onDragNode,
    onRotateCamera,
    onReset,
}: GestureControllerProps) {
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const [active, setActive] = useState(false);
    const [status, setStatus] = useState('Inativo');
    const [gesture, setGesture] = useState<GestureName>('none');
    const [cursor, setCursor] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
    const streamRef = useRef<MediaStream | null>(null);
    const frameRef = useRef<number | null>(null);
    const prevCursorRef = useRef<{ x: number; y: number } | null>(null);
    const [sensitivity, setSensitivity] = useState(1);

    const supportsMediaPipe = useMemo(() => enabled, [enabled]);

    const getFriendlyMediaError = (err: unknown) => {
        const e = err as { name?: string; message?: string };
        const name = e?.name || '';
        const message = (e?.message || '').toLowerCase();
        const host = window.location.hostname;
        const isLocalhost = host === 'localhost' || host === '127.0.0.1';

        if (!window.isSecureContext && !isLocalhost) return 'Acesso a webcam exige HTTPS ou localhost';
        if (name === 'NotAllowedError' || name === 'SecurityError') return 'Permissao de webcam necessaria';
        if (name === 'NotFoundError' || name === 'DevicesNotFoundError') return 'Webcam nao encontrada';
        if (name === 'NotReadableError' || name === 'TrackStartError') return 'Webcam ocupada por outro aplicativo';
        if (name === 'OverconstrainedError' || name === 'ConstraintNotSatisfiedError') return 'Configuracao de video nao suportada pela webcam';
        if (name === 'AbortError') return 'A inicializacao da webcam foi interrompida';
        if (name === 'TypeError' && message.includes('secure')) return 'Acesso a webcam exige HTTPS ou localhost';
        return 'Falha ao acessar webcam';
    };

    const requestCameraStream = async () => {
        const preferredConstraints: MediaStreamConstraints = {
            video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30, max: 30 } },
            audio: false,
        };
        const fallbackConstraints: MediaStreamConstraints = { video: true, audio: false };

        try {
            return await navigator.mediaDevices.getUserMedia(preferredConstraints);
        } catch (firstError) {
            const firstName = (firstError as { name?: string })?.name || '';
            if (firstName === 'OverconstrainedError' || firstName === 'ConstraintNotSatisfiedError') {
                return navigator.mediaDevices.getUserMedia(fallbackConstraints);
            }
            throw firstError;
        }
    };

    useEffect(() => {
        if (!enabled) {
            stopController();
        }
        return () => stopController();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [enabled]);

    const stopController = () => {
        if (frameRef.current) {
            cancelAnimationFrame(frameRef.current);
            frameRef.current = null;
        }
        if (streamRef.current) {
            streamRef.current.getTracks().forEach((track) => track.stop());
            streamRef.current = null;
        }
        setActive(false);
        setStatus('Inativo');
        setGesture('none');
    };

    const drawSkeleton = (x: number, y: number) => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        const w = canvas.width;
        const h = canvas.height;
        ctx.clearRect(0, 0, w, h);
        ctx.beginPath();
        ctx.arc(x, y, 18, 0, Math.PI * 2);
        ctx.strokeStyle = '#4ade80';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#4ade80';
        ctx.fill();
    };

    const simulateGestureRecognition = () => {
        const video = videoRef.current;
        if (!video) return;
        const x = (Math.sin(Date.now() / 700) * 0.25 + 0.5) * (video.videoWidth || 640);
        const y = (Math.cos(Date.now() / 900) * 0.2 + 0.5) * (video.videoHeight || 360);
        setCursor({ x, y });
        drawSkeleton(x, y);

        const phase = Math.floor((Date.now() / 1400) % 4);
        const g: GestureName = phase === 0 ? 'pinch' : phase === 1 ? 'drag' : phase === 2 ? 'rotate' : 'open_hand';
        setGesture(g);
        if (g === 'pinch') onSelectNode?.(x, y);
        if (g === 'drag' && prevCursorRef.current) {
            const dx = (x - prevCursorRef.current.x) * sensitivity;
            const dy = (y - prevCursorRef.current.y) * sensitivity;
            onDragNode?.(dx, dy);
        }
        if (g === 'rotate' && prevCursorRef.current) {
            const delta = (x - prevCursorRef.current.x) * 0.002 * sensitivity;
            onRotateCamera?.(delta);
        }
        if (g === 'open_hand') onReset?.();
        prevCursorRef.current = { x, y };
        frameRef.current = requestAnimationFrame(simulateGestureRecognition);
    };

    const startController = async () => {
        if (!enabled) return;
        try {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                setStatus('Navegador nao suporta getUserMedia');
                setActive(false);
                return;
            }
            const host = window.location.hostname;
            const isLocalhost = host === 'localhost' || host === '127.0.0.1';
            if (!window.isSecureContext && !isLocalhost) {
                setStatus('Acesso a webcam exige HTTPS ou localhost');
                setActive(false);
                return;
            }
            setStatus('Solicitando camera...');
            const stream = await requestCameraStream();
            streamRef.current = stream;
            if (videoRef.current) {
                videoRef.current.srcObject = stream;
                await videoRef.current.play();
            }
            setActive(true);
            setStatus(supportsMediaPipe ? 'Ativo (processamento local)' : 'Mediapipe indisponivel');
            frameRef.current = requestAnimationFrame(simulateGestureRecognition);
        } catch (err) {
            setStatus(getFriendlyMediaError(err));
            setActive(false);
        }
    };

    if (!enabled) return null;

    return (
        <div className="gesture-controller">
            <div className="gesture-header">
                <strong>Gesture Controller</strong>
                <span>{status}</span>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <button className="btn btn-secondary" onClick={startController} disabled={active}>
                    Ativar camera
                </button>
                <button className="btn btn-ghost" onClick={stopController}>Desativar</button>
                <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    Sensibilidade
                    <input
                        type="range"
                        min={0.4}
                        max={2}
                        step={0.1}
                        value={sensitivity}
                        onChange={(e) => setSensitivity(Number(e.target.value))}
                    />
                </label>
                <span style={{ fontSize: 12 }}>Gesto: {gesture}</span>
            </div>
            <div style={{ position: 'relative', width: 320, height: 180, marginTop: 8 }}>
                <video ref={videoRef} width={320} height={180} muted playsInline style={{ borderRadius: 8, background: '#111827' }} />
                <canvas ref={canvasRef} width={320} height={180} style={{ position: 'absolute', top: 0, left: 0 }} />
                <div style={{ position: 'absolute', left: `${(cursor.x / 640) * 100}%`, top: `${(cursor.y / 360) * 100}%`, transform: 'translate(-50%, -50%)' }}>
                    <span style={{ color: '#4ade80' }}>*</span>
                </div>
            </div>
        </div>
    );
}
