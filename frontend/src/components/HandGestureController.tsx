import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import NeonRenderer from './NeonRenderer';

type GestureName =
  | 'none'
  | 'pinch'
  | 'open_hand'
  | 'fist'
  | 'v_sign'
  | 'closing_v'
  | 'palm_forward';

export interface GestureCommand {
  type:
    | 'select'
    | 'drag'
    | 'pan'
    | 'zoom_in'
    | 'zoom_out'
    | 'fit_view'
    | 'expand_all_clusters'
    | 'collapse_all_clusters'
    | 'deselect'
    | 'pause'
    | 'resume';
  x?: number;
  y?: number;
  dx?: number;
  dy?: number;
}

interface HandGestureControllerProps {
  onGestureCommand?: (command: GestureCommand) => void;
  onCursorUpdate?: (cursor: { x: number; y: number; active: boolean }) => void;
}

const STORAGE_KEY = 'insightgraph.gesture.config.v1';
const WS_HAND_GRACE_MS = 450;
const LOCAL_PINCH_THRESHOLD = 0.06;
const LOCAL_FIST_THRESHOLD = 0.19;
const LOCAL_ZOOM_DELTA_THRESHOLD = 0.015;
const LOCAL_PAN_SCALE = 2.2;
const LOCAL_ACTION_HOLD_MS = 900;
const LOCAL_ACTION_COOLDOWN_MS = 2200;
const LOCAL_ZOOM_COOLDOWN_MS = 120;
type SensitivityPreset = 'suave' | 'normal' | 'agressivo';

const SENSITIVITY_PROFILES: Record<SensitivityPreset, {
  movementScale: number;
  pinchThreshold: number;
  fistThreshold: number;
  zoomDeltaThreshold: number;
}> = {
  suave: {
    movementScale: 0.78,
    pinchThreshold: 0.052,
    fistThreshold: 0.175,
    zoomDeltaThreshold: 0.019,
  },
  normal: {
    movementScale: 1,
    pinchThreshold: LOCAL_PINCH_THRESHOLD,
    fistThreshold: LOCAL_FIST_THRESHOLD,
    zoomDeltaThreshold: LOCAL_ZOOM_DELTA_THRESHOLD,
  },
  agressivo: {
    movementScale: 1.35,
    pinchThreshold: 0.069,
    fistThreshold: 0.208,
    zoomDeltaThreshold: 0.011,
  },
};

type MpHandsInstance = {
  setOptions: (options: Record<string, unknown>) => void;
  onResults: (cb: (results: { multiHandLandmarks?: Array<Array<{ x: number; y: number }> > }) => void) => void;
  send: (input: { image: HTMLVideoElement }) => Promise<void>;
  close: () => void;
};

export default function HandGestureController({
  onGestureCommand,
  onCursorUpdate,
}: HandGestureControllerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const frameTimerRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const prevCursorRef = useRef<{ x: number; y: number } | null>(null);
  const pausedRef = useRef(false);
  const trackingOnlyRef = useRef(false);
  const enabledRef = useRef(false);
  const localHandsRef = useRef<MpHandsInstance | null>(null);
  const localLoopRef = useRef<number | null>(null);
  const localInFlightRef = useRef(false);
  const backendHasRecentHandRef = useRef(false);
  const backendLastHandTsRef = useRef(0);
  const pinchActiveRef = useRef(false);
  const localReadyRef = useRef(false);
  const lastTwoHandCenterRef = useRef<{ x: number; y: number } | null>(null);
  const lastTwoHandDistanceRef = useRef<number | null>(null);
  const lastLocalZoomTsRef = useRef(0);
  const actionHoldStartRef = useRef<{ mode: 'expand' | 'collapse' | null; ts: number }>({ mode: null, ts: 0 });
  const lastActionTsRef = useRef(0);
  const lastDeselectTsRef = useRef(0);

  const [active, setActive] = useState(false);
  const [status, setStatus] = useState('Inativo');
  const [gesture, setGesture] = useState<GestureName>('none');
  const [landmarks, setLandmarks] = useState<Array<{ x: number; y: number }>>([]);
  const [fps, setFps] = useState(0);
  const [latency, setLatency] = useState(0);
  const [trackingOnly, setTrackingOnly] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [sensitivityPreset, setSensitivityPreset] = useState<SensitivityPreset>('normal');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [trackingSource, setTrackingSource] = useState<'none' | 'backend' | 'local'>('none');
  const [minimized, setMinimized] = useState(false);

  const previewSize = useMemo(() => ({ width: 320, height: 180 }), []);
  const sensitivity = useMemo(() => SENSITIVITY_PROFILES[sensitivityPreset], [sensitivityPreset]);

  useEffect(() => {
    trackingOnlyRef.current = trackingOnly;
  }, [trackingOnly]);

  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  const getFriendlyMediaError = useCallback((err: unknown) => {
    const e = err as { name?: string; message?: string };
    const name = e?.name || '';
    const message = (e?.message || '').toLowerCase();

    if (!window.isSecureContext && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
      return 'Acesso a webcam exige HTTPS ou localhost';
    }
    if (name === 'NotAllowedError' || name === 'SecurityError') {
      return 'Permissao de webcam necessaria';
    }
    if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
      return 'Webcam nao encontrada';
    }
    if (name === 'NotReadableError' || name === 'TrackStartError') {
      return 'Webcam ocupada por outro aplicativo';
    }
    if (name === 'OverconstrainedError' || name === 'ConstraintNotSatisfiedError') {
      return 'Configuracao de video nao suportada pela webcam';
    }
    if (name === 'AbortError') {
      return 'A inicializacao da webcam foi interrompida';
    }
    if (name === 'TypeError' && message.includes('secure')) {
      return 'Acesso a webcam exige HTTPS ou localhost';
    }
    return 'Falha ao acessar webcam';
  }, []);

  const requestCameraStream = useCallback(async () => {
    const preferredConstraints: MediaStreamConstraints = {
      video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30, max: 30 } },
      audio: false,
    };
    const fallbackConstraints: MediaStreamConstraints = {
      video: true,
      audio: false,
    };

    try {
      return await navigator.mediaDevices.getUserMedia(preferredConstraints);
    } catch (firstError) {
      const firstName = (firstError as { name?: string })?.name || '';
      if (firstName === 'OverconstrainedError' || firstName === 'ConstraintNotSatisfiedError') {
        return navigator.mediaDevices.getUserMedia(fallbackConstraints);
      }
      throw firstError;
    }
  }, []);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw);
        setEnabled(Boolean(saved.enabled));
        setDemoMode(Boolean(saved.demoMode));
        if (saved.sensitivityPreset === 'suave' || saved.sensitivityPreset === 'normal' || saved.sensitivityPreset === 'agressivo') {
          setSensitivityPreset(saved.sensitivityPreset);
        }
      }
    } catch {
      // ignore local storage errors
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ enabled, demoMode, sensitivityPreset })
      );
    } catch {
      // ignore local storage errors
    }
  }, [demoMode, enabled, sensitivityPreset]);

  const closeWebsocket = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const closeLocalTracker = useCallback(() => {
    if (localLoopRef.current) {
      window.cancelAnimationFrame(localLoopRef.current);
      localLoopRef.current = null;
    }
    if (localHandsRef.current) {
      try {
        localHandsRef.current.close();
      } catch {
        // ignore
      }
      localHandsRef.current = null;
    }
    localInFlightRef.current = false;
    localReadyRef.current = false;
    pinchActiveRef.current = false;
    lastTwoHandCenterRef.current = null;
    lastTwoHandDistanceRef.current = null;
    actionHoldStartRef.current = { mode: null, ts: 0 };
  }, []);

  const stop = useCallback(() => {
    enabledRef.current = false;
    setActive(false);
    setStatus('Inativo');
    setGesture('none');
    setLandmarks([]);
    setFps(0);
    setLatency(0);
    setTrackingSource('none');
    prevCursorRef.current = null;
    pausedRef.current = false;
    backendHasRecentHandRef.current = false;
    backendLastHandTsRef.current = 0;
    closeWebsocket();
    closeLocalTracker();
    if (frameTimerRef.current) {
      window.clearInterval(frameTimerRef.current);
      frameTimerRef.current = null;
    }
    const stream = videoRef.current?.srcObject as MediaStream | null;
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      if (videoRef.current) videoRef.current.srcObject = null;
    }
    onCursorUpdate?.({ x: 0, y: 0, active: false });
  }, [closeLocalTracker, closeWebsocket, onCursorUpdate]);

  const updateFromLocal = useCallback((rawLandmarks: Array<{ x: number; y: number }>) => {
    const now = Date.now();
    const backendStillActive = backendHasRecentHandRef.current && (now - backendLastHandTsRef.current) < WS_HAND_GRACE_MS;
    if (backendStillActive) return;

    if (!rawLandmarks.length) {
      setTrackingSource('none');
      setLandmarks([]);
      setGesture('none');
      pinchActiveRef.current = false;
      prevCursorRef.current = null;
      onCursorUpdate?.({ x: 0, y: 0, active: false });
      return;
    }

    const points = rawLandmarks.map((pt) => ({
      x: Math.max(0, Math.min(1, pt.x)) * previewSize.width,
      y: Math.max(0, Math.min(1, pt.y)) * previewSize.height,
    }));
    setLandmarks(points);
    setTrackingSource('local');

    const idx = rawLandmarks[8];
    const thumb = rawLandmarks[4];
    if (!idx || !thumb) return;

    const cursor = {
      x: Math.max(0, Math.min(1, idx.x)),
      y: Math.max(0, Math.min(1, idx.y)),
      active: true,
    };
    onCursorUpdate?.(cursor);

    const pinchDistance = Math.hypot(thumb.x - idx.x, thumb.y - idx.y);
    const isPinching = pinchDistance < sensitivity.pinchThreshold;
    const wrist = rawLandmarks[0];
    const tips = [8, 12, 16, 20].map((i) => rawLandmarks[i]).filter(Boolean) as Array<{ x: number; y: number }>;
    const fistScore = wrist && tips.length
      ? tips.reduce((acc, pt) => acc + Math.hypot(pt.x - wrist.x, pt.y - wrist.y), 0) / tips.length
      : Number.POSITIVE_INFINITY;
    const isFist = fistScore < sensitivity.fistThreshold;
    setGesture(isPinching ? 'pinch' : isFist ? 'fist' : 'open_hand');

    const prev = prevCursorRef.current;
    if (isPinching && !pausedRef.current) {
      if (!pinchActiveRef.current || !prev) {
        onGestureCommand?.({ type: 'select', x: cursor.x, y: cursor.y });
      } else {
        onGestureCommand?.({
          type: 'drag',
          dx: (cursor.x - prev.x) * previewSize.width * sensitivity.movementScale,
          dy: (cursor.y - prev.y) * previewSize.height * sensitivity.movementScale,
          x: cursor.x,
          y: cursor.y,
        });
      }
    }
    if (isFist && (now - lastDeselectTsRef.current) > 700) {
      onGestureCommand?.({ type: 'deselect' });
      lastDeselectTsRef.current = now;
    }

    pinchActiveRef.current = isPinching;
    prevCursorRef.current = { x: cursor.x, y: cursor.y };
  }, [onCursorUpdate, onGestureCommand, previewSize.height, previewSize.width, sensitivity.fistThreshold, sensitivity.movementScale, sensitivity.pinchThreshold]);

  const getPalmCenter = useCallback((hand: Array<{ x: number; y: number }>) => {
    const anchor = hand[9] || hand[0] || hand[5];
    if (!anchor) return { x: 0.5, y: 0.5 };
    return {
      x: Math.max(0, Math.min(1, anchor.x)),
      y: Math.max(0, Math.min(1, anchor.y)),
    };
  }, []);

  const getPinchDistance = useCallback((hand: Array<{ x: number; y: number }>) => {
    const thumb = hand[4];
    const idx = hand[8];
    if (!thumb || !idx) return Number.POSITIVE_INFINITY;
    return Math.hypot(thumb.x - idx.x, thumb.y - idx.y);
  }, []);

  const getFistScore = useCallback((hand: Array<{ x: number; y: number }>) => {
    const wrist = hand[0];
    if (!wrist) return Number.POSITIVE_INFINITY;
    const tips = [8, 12, 16, 20].map((i) => hand[i]).filter(Boolean) as Array<{ x: number; y: number }>;
    if (!tips.length) return Number.POSITIVE_INFINITY;
    const avg = tips.reduce((acc, pt) => acc + Math.hypot(pt.x - wrist.x, pt.y - wrist.y), 0) / tips.length;
    return avg;
  }, []);

  const updateFromLocalMulti = useCallback((hands: Array<Array<{ x: number; y: number }>>) => {
    const now = Date.now();
    const backendStillActive = backendHasRecentHandRef.current && (now - backendLastHandTsRef.current) < WS_HAND_GRACE_MS;
    if (backendStillActive || hands.length < 2) return;

    const [h1, h2] = hands;
    if (!h1?.length || !h2?.length) return;

    const c1 = getPalmCenter(h1);
    const c2 = getPalmCenter(h2);
    const center = { x: (c1.x + c2.x) / 2, y: (c1.y + c2.y) / 2 };
    const pairDistance = Math.hypot(c1.x - c2.x, c1.y - c2.y);
    const pinch1 = getPinchDistance(h1) < sensitivity.pinchThreshold;
    const pinch2 = getPinchDistance(h2) < sensitivity.pinchThreshold;
    const fist1 = getFistScore(h1) < sensitivity.fistThreshold;
    const fist2 = getFistScore(h2) < sensitivity.fistThreshold;
    const open1 = !pinch1 && !fist1;
    const open2 = !pinch2 && !fist2;

    if (open1 && open2) {
      const prevCenter = lastTwoHandCenterRef.current;
      if (prevCenter) {
        onGestureCommand?.({
          type: 'pan',
          dx: (center.x - prevCenter.x) * previewSize.width * LOCAL_PAN_SCALE * sensitivity.movementScale,
          dy: (center.y - prevCenter.y) * previewSize.height * LOCAL_PAN_SCALE * sensitivity.movementScale,
        });
      }
      setGesture('open_hand');
    }

    if (pinch1 && pinch2) {
      const prevDistance = lastTwoHandDistanceRef.current;
      if (typeof prevDistance === 'number' && (now - lastLocalZoomTsRef.current) > LOCAL_ZOOM_COOLDOWN_MS) {
        const delta = pairDistance - prevDistance;
        if (delta > sensitivity.zoomDeltaThreshold) {
          onGestureCommand?.({ type: 'zoom_in' });
          lastLocalZoomTsRef.current = now;
        } else if (delta < -sensitivity.zoomDeltaThreshold) {
          onGestureCommand?.({ type: 'zoom_out' });
          lastLocalZoomTsRef.current = now;
        }
      }
      setGesture('pinch');
    }

    const canFireAction = (now - lastActionTsRef.current) > LOCAL_ACTION_COOLDOWN_MS;
    const wantedMode: 'expand' | 'collapse' | null =
      (open1 && open2) ? 'expand' : (fist1 && fist2) ? 'collapse' : null;

    if (!wantedMode) {
      actionHoldStartRef.current = { mode: null, ts: 0 };
    } else if (actionHoldStartRef.current.mode !== wantedMode) {
      actionHoldStartRef.current = { mode: wantedMode, ts: now };
    } else if (canFireAction && (now - actionHoldStartRef.current.ts) >= LOCAL_ACTION_HOLD_MS) {
      if (wantedMode === 'expand') {
        onGestureCommand?.({ type: 'expand_all_clusters' });
      } else {
        onGestureCommand?.({ type: 'collapse_all_clusters' });
        onGestureCommand?.({ type: 'fit_view' });
      }
      lastActionTsRef.current = now;
      actionHoldStartRef.current = { mode: null, ts: 0 };
    }

    lastTwoHandCenterRef.current = center;
    lastTwoHandDistanceRef.current = pairDistance;
  }, [getFistScore, getPalmCenter, getPinchDistance, onGestureCommand, previewSize.height, previewSize.width, sensitivity.fistThreshold, sensitivity.movementScale, sensitivity.pinchThreshold, sensitivity.zoomDeltaThreshold]);

  const startLocalTracker = useCallback(async () => {
    if (localReadyRef.current || !videoRef.current) return;

    try {
      const module = await import('@mediapipe/hands');
      const HandsCtor = (module as unknown as { Hands: new (config: { locateFile: (file: string) => string }) => MpHandsInstance }).Hands;
      const detector = new HandsCtor({
        locateFile: (file: string) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`,
      });

      detector.setOptions({
        maxNumHands: 2,
        modelComplexity: 0,
        minDetectionConfidence: 0.6,
        minTrackingConfidence: 0.6,
      });
      detector.onResults((results) => {
        const detected = (results.multiHandLandmarks || []).map((hand) => hand.map((pt) => ({ x: pt.x, y: pt.y })));
        if (detected.length >= 2) {
          updateFromLocalMulti(detected);
        }
        const first = detected[0] || [];
        updateFromLocal(first);
      });

      localHandsRef.current = detector;
      localReadyRef.current = true;

      const tick = async () => {
        if (!enabledRef.current || !videoRef.current || !localHandsRef.current) return;
        if (videoRef.current.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
          localLoopRef.current = window.requestAnimationFrame(() => {
            void tick();
          });
          return;
        }

        if (localInFlightRef.current) {
          localLoopRef.current = window.requestAnimationFrame(() => {
            void tick();
          });
          return;
        }

        localInFlightRef.current = true;
        try {
          await localHandsRef.current.send({ image: videoRef.current });
        } catch {
          // ignore local inference frame errors
        } finally {
          localInFlightRef.current = false;
        }
        localLoopRef.current = window.requestAnimationFrame(() => {
          void tick();
        });
      };

      localLoopRef.current = window.requestAnimationFrame(() => {
        void tick();
      });
    } catch {
      // keep backend-only mode if local tracker cannot load
    }
  }, [updateFromLocal, updateFromLocalMulti]);

  const connectWs = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/hand-tracking`;
    const socket = new WebSocket(wsUrl);
    wsRef.current = socket;

    socket.onopen = () => {
      reconnectAttemptsRef.current = 0;
      setStatus('Ativo');
      setErrorMessage(null);
    };

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === 'error') {
          setErrorMessage(payload.message || 'Erro no rastreamento');
          return;
        }
        if (payload.type !== 'tracking') return;

        setFps(Number(payload.fps || 0));
        setLatency(Number(payload.latency_ms || 0));
        const hand = payload.primary_hand;
        const points = (hand?.landmarks || []).map((pt: { x: number; y: number }) => ({
          x: Math.max(0, Math.min(1, pt.x)) * previewSize.width,
          y: Math.max(0, Math.min(1, pt.y)) * previewSize.height,
        }));
        if (points.length >= 21) {
          backendHasRecentHandRef.current = true;
          backendLastHandTsRef.current = Date.now();
          setTrackingSource('backend');
          setLandmarks(points);
        } else if (!localReadyRef.current) {
          setTrackingSource('none');
          setLandmarks([]);
        } else if (Date.now() - backendLastHandTsRef.current > WS_HAND_GRACE_MS) {
          backendHasRecentHandRef.current = false;
        }

        const idx = hand?.landmarks?.[8];
        if (idx) {
          const cursor = {
            x: Math.max(0, Math.min(1, idx.x)),
            y: Math.max(0, Math.min(1, idx.y)),
            active: true,
          };
          onCursorUpdate?.(cursor);

          const prev = prevCursorRef.current;
          const g = (payload.gesture || 'none') as GestureName;
          setGesture(g);
          pinchActiveRef.current = g === 'pinch';
          if (g === 'pinch' && !pausedRef.current) {
            if (!prev) {
              onGestureCommand?.({ type: 'select', x: cursor.x, y: cursor.y });
            } else {
              onGestureCommand?.({
                type: 'drag',
                dx: (cursor.x - prev.x) * previewSize.width,
                dy: (cursor.y - prev.y) * previewSize.height,
                x: cursor.x,
                y: cursor.y,
              });
            }
          } else if (g === 'v_sign') {
            onGestureCommand?.({ type: 'zoom_in' });
          } else if (g === 'closing_v') {
            onGestureCommand?.({ type: 'zoom_out' });
          } else if (g === 'fist') {
            onGestureCommand?.({ type: 'deselect' });
          } else if (g === 'palm_forward') {
            if (!pausedRef.current) {
              pausedRef.current = true;
              onGestureCommand?.({ type: 'pause' });
            } else {
              pausedRef.current = false;
              onGestureCommand?.({ type: 'resume' });
            }
          }

          prevCursorRef.current = { x: cursor.x, y: cursor.y };
        } else {
          if (!localReadyRef.current) {
            onCursorUpdate?.({ x: 0, y: 0, active: false });
            prevCursorRef.current = null;
            pinchActiveRef.current = false;
            setGesture('none');
          }
        }
      } catch {
        // ignore malformed payload
      }
    };

    socket.onerror = () => {
      setErrorMessage('Falha de conexao WebSocket');
    };

    socket.onclose = () => {
      if (!enabledRef.current) return;
      if (reconnectAttemptsRef.current >= 3) {
        setErrorMessage('Backend indisponivel. Usando tracking local.');
        closeWebsocket();
        return;
      }
      const attempts = reconnectAttemptsRef.current + 1;
      reconnectAttemptsRef.current = attempts;
      const delay = Math.min(4000, 500 * (2 ** attempts));
      setStatus(`Reconectando... (${attempts}/3)`);
      window.setTimeout(connectWs, delay);
    };
  }, [closeWebsocket, onCursorUpdate, onGestureCommand, previewSize.height, previewSize.width]);

  const start = useCallback(async () => {
    try {
      enabledRef.current = true;
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setErrorMessage('Navegador nao suporta getUserMedia');
        return;
      }
      if (!window.isSecureContext && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
        setErrorMessage('Acesso a webcam exige HTTPS ou localhost');
        return;
      }
      setStatus('Solicitando webcam...');
      setErrorMessage(null);
      const stream = await requestCameraStream();
      if (!videoRef.current) return;
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      setActive(true);
      setTrackingSource('none');
      void startLocalTracker();
      connectWs();
      frameTimerRef.current = window.setInterval(() => {
        if (!videoRef.current || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        const isTrackingOnly = trackingOnlyRef.current;
        const canvas = document.createElement('canvas');
        canvas.width = isTrackingOnly ? 320 : 640;
        canvas.height = isTrackingOnly ? 240 : 480;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
        const jpeg = canvas.toDataURL('image/jpeg', 0.7);
        const imageBase64 = jpeg.split(',')[1];
        wsRef.current.send(
          JSON.stringify({
            type: 'frame',
            image_base64: imageBase64,
            width: canvas.width,
            height: canvas.height,
            client_ts: Date.now(),
          })
        );
      }, 33);
    } catch (err: unknown) {
      setErrorMessage(getFriendlyMediaError(err));
      stop();
    }
  }, [connectWs, getFriendlyMediaError, requestCameraStream, startLocalTracker, stop]);

  useEffect(() => {
    if (!enabled) {
      stop();
      return;
    }
    start();
    return () => stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  useEffect(() => {
    if (fps < 15 && active) {
      setTrackingOnly(true);
    }
  }, [active, fps]);

  return (
    <div className="gesture-controller">
      <div className="gesture-header">
        <strong>Controle por Gestos</strong>
        <span className="ai-badge-featured">Beta</span>
        <button
          className="btn btn-ghost"
          onClick={() => setMinimized((v) => !v)}
          style={{ marginLeft: 8, padding: '4px 8px', fontSize: 11 }}
          title={minimized ? 'Expandir painel de gestos' : 'Minimizar painel de gestos'}
          type="button"
        >
          {minimized ? 'Expandir' : 'Minimizar'}
        </button>
      </div>

      {!minimized && (
      <>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <button className={`btn ${enabled ? 'btn-accent' : 'btn-secondary'}`} onClick={() => setEnabled((v) => !v)}>
          {enabled ? 'Desativar' : 'Ativar'} Controle por Gestos
        </button>
        <button className={`btn ${demoMode ? 'btn-accent' : 'btn-ghost'}`} onClick={() => setDemoMode((v) => !v)}>
          Demo
        </button>
        <button className={`btn ${trackingOnly ? 'btn-accent' : 'btn-ghost'}`} onClick={() => setTrackingOnly((v) => !v)}>
          Tracking-only
        </button>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: '#93a0c3' }}>Sensibilidade</span>
          <button
            className={`btn ${sensitivityPreset === 'suave' ? 'btn-accent' : 'btn-ghost'}`}
            onClick={() => setSensitivityPreset('suave')}
            style={{ padding: '4px 8px', fontSize: 11 }}
          >
            Suave
          </button>
          <button
            className={`btn ${sensitivityPreset === 'normal' ? 'btn-accent' : 'btn-ghost'}`}
            onClick={() => setSensitivityPreset('normal')}
            style={{ padding: '4px 8px', fontSize: 11 }}
          >
            Normal
          </button>
          <button
            className={`btn ${sensitivityPreset === 'agressivo' ? 'btn-accent' : 'btn-ghost'}`}
            onClick={() => setSensitivityPreset('agressivo')}
            style={{ padding: '4px 8px', fontSize: 11 }}
          >
            Agressivo
          </button>
        </div>
        <span title="pinch, fist, v_sign, closing_v, palm_forward" style={{ fontSize: 12, color: '#93a0c3' }}>
          Gestos: {gesture}
        </span>
      </div>

      <div style={{ marginTop: 8, fontSize: 12, color: '#93a0c3', display: 'flex', gap: 10 }}>
        <span>Status: {status}</span>
        <span>FPS: {fps.toFixed(1)}</span>
        <span>Latencia: {latency.toFixed(1)}ms</span>
        <span>Fonte: {trackingSource}</span>
        <span>Sens: {sensitivityPreset}</span>
      </div>
      <div style={{ marginTop: 6, fontSize: 11, color: '#7f8db3' }}>
        1 mÃ£o: pinch seleciona/arrasta, punho fecha limpa seleÃ§Ã£o. 2 mÃ£os: abertas movem (pan), pinches afastam/aproximam (zoom), abertas seguradas expandem, punhos segurados colapsam.
      </div>
      <div
        style={{
          marginTop: 8,
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 8,
          fontSize: 11,
          color: '#b9c5e5',
        }}
      >
        <div style={{ border: '1px solid rgba(125,211,252,0.2)', borderRadius: 8, padding: 8, background: 'rgba(2,6,23,0.55)' }}>
          <div style={{ fontWeight: 600, marginBottom: 5 }}>1 mÃ£o</div>
          <div className="gesture-demo gesture-demo-one">
            <span className="g-hand">{'\u{1F90F}'}</span>
            <span className="g-tip">Selecionar / Arrastar</span>
          </div>
          <div className="gesture-demo gesture-demo-two">
            <span className="g-hand">{'\u270A'}</span>
            <span className="g-tip">Limpar seleÃ§Ã£o</span>
          </div>
        </div>
        <div style={{ border: '1px solid rgba(134,239,172,0.2)', borderRadius: 8, padding: 8, background: 'rgba(2,6,23,0.55)' }}>
          <div style={{ fontWeight: 600, marginBottom: 5 }}>2 mÃ£os</div>
          <div className="gesture-demo gesture-demo-three">
            <span className="g-hands">{'\u{1F590}\u{FE0F} \u2194\u{FE0F} \u{1F590}\u{FE0F}'}</span>
            <span className="g-tip">Pan / Zoom</span>
          </div>
          <div className="gesture-demo gesture-demo-four">
            <span className="g-hands">{'\u270A\u270A / \u{1F590}\u{FE0F}\u{1F590}\u{FE0F}'}</span>
            <span className="g-tip">Colapsar / Expandir</span>
          </div>
        </div>
      </div>
      <style>{`
        .gesture-demo { display: flex; align-items: center; gap: 6px; }
        .gesture-demo + .gesture-demo { margin-top: 6px; }
        .g-hand, .g-hands { display: inline-block; font-size: 15px; min-width: 54px; animation: igPulse 1.5s ease-in-out infinite; }
        .gesture-demo-three .g-hands { animation: igStretch 1.6s ease-in-out infinite; }
        .gesture-demo-four .g-hands { animation: igBlink 1.9s ease-in-out infinite; }
        .g-tip { color: #8ea0c8; }
        @keyframes igPulse {
          0%,100% { transform: scale(1); opacity: 0.75; }
          50% { transform: scale(1.1); opacity: 1; }
        }
        @keyframes igStretch {
          0%,100% { transform: translateX(0); opacity: 0.7; }
          50% { transform: translateX(3px); opacity: 1; }
        }
        @keyframes igBlink {
          0%,100% { opacity: 0.7; }
          50% { opacity: 1; }
        }
      `}</style>
      {(fps > 0 && fps < 15) || latency > 100 ? (
        <div style={{ marginTop: 6, color: '#f59e0b', fontSize: 12 }}>
          Performance baixa detectada
        </div>
      ) : null}
      {errorMessage ? (
        <div style={{ marginTop: 6, color: '#fda4af', fontSize: 12 }}>
          {errorMessage}
        </div>
      ) : null}

      <div style={{ position: 'relative', width: previewSize.width, height: previewSize.height, marginTop: 8, borderRadius: 8, overflow: 'hidden' }}>
        <video
          ref={videoRef}
          width={previewSize.width}
          height={previewSize.height}
          muted
          playsInline
          style={{ width: '100%', height: '100%', background: '#020617', objectFit: 'cover' }}
        />
        <NeonRenderer
          width={previewSize.width}
          height={previewSize.height}
          landmarks={landmarks}
          enabled={enabled && active}
          trackingOnly={trackingOnly}
        />
        {demoMode && (
          <div style={{ position: 'absolute', left: 8, top: 8, padding: '3px 7px', borderRadius: 6, background: 'rgba(0,0,0,0.55)', color: '#7dd3fc', fontSize: 12 }}>
            {gesture}
          </div>
        )}
      </div>
      </>
      )}
    </div>
  );
}
