import { useState, useEffect, useRef, useCallback } from 'react';

export interface ImpactResult {
  type: 'impact';
  file: string;
  changed_nodes: string[];
  affected_nodes: string[];
  risk_score: number;
  coupling_delta: number;
  summary: string;
  timestamp: string;
}

interface HeartbeatMessage {
  type: 'heartbeat';
  timestamp: string;
}

type WatchMessage = ImpactResult | HeartbeatMessage;

export interface UseWatchModeReturn {
  connected: boolean;
  watching: boolean;
  watchedPath: string | null;
  lastImpact: ImpactResult | null;
  impactHistory: ImpactResult[];
  startWatch: (path: string) => Promise<void>;
  stopWatch: () => Promise<void>;
  clearHistory: () => void;
}

const MAX_HISTORY = 20;
const INITIAL_RETRY_DELAY = 1000;
const MAX_RETRY_DELAY = 30000;
const BACKOFF_MULTIPLIER = 2;

export function useWatchMode(): UseWatchModeReturn {
  const [connected, setConnected] = useState(false);
  const [watching, setWatching] = useState(false);
  const [watchedPath, setWatchedPath] = useState<string | null>(null);
  const [lastImpact, setLastImpact] = useState<ImpactResult | null>(null);
  const [impactHistory, setImpactHistory] = useState<ImpactResult[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const projectPathRef = useRef<string | null>(null);
  const retryDelayRef = useRef(INITIAL_RETRY_DELAY);
  const retryTimeoutRef = useRef<number | null>(null);
  const shouldReconnectRef = useRef(false);

  const clearHistory = useCallback(() => {
    setImpactHistory([]);
    setLastImpact(null);
  }, []);

  const connectWebSocket = useCallback((projectPath: string) => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    const encodedPath = encodeURIComponent(projectPath);
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/watch/ws/${encodedPath}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      retryDelayRef.current = INITIAL_RETRY_DELAY;
    };

    ws.onmessage = (event) => {
      try {
        const message: WatchMessage = JSON.parse(event.data);
        if (message.type !== 'impact') return;
        setLastImpact(message);
        setImpactHistory((prev) => [message, ...prev].slice(0, MAX_HISTORY));
      } catch {
        // ignore malformed payloads
      }
    };

    ws.onerror = () => {
      setConnected(false);
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;

      if (shouldReconnectRef.current && projectPathRef.current) {
        const delay = retryDelayRef.current;
        retryTimeoutRef.current = window.setTimeout(() => {
          if (projectPathRef.current) {
            connectWebSocket(projectPathRef.current);
          }
        }, delay);

        retryDelayRef.current = Math.min(
          retryDelayRef.current * BACKOFF_MULTIPLIER,
          MAX_RETRY_DELAY
        );
      }
    };
  }, []);

  const startWatch = useCallback(async (path: string) => {
    const nextPath = path.trim();
    if (!nextPath) {
      throw new Error('Missing project path');
    }

    if (projectPathRef.current && projectPathRef.current !== nextPath) {
      await fetch('/api/watch/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: projectPathRef.current }),
      });
    }

    const response = await fetch('/api/watch/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: nextPath }),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to start watch: ${error}`);
    }

    projectPathRef.current = nextPath;
    setWatchedPath(nextPath);
    shouldReconnectRef.current = true;
    setWatching(true);
    connectWebSocket(nextPath);
  }, [connectWebSocket]);

  const stopWatch = useCallback(async () => {
    shouldReconnectRef.current = false;

    if (retryTimeoutRef.current !== null) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    if (projectPathRef.current) {
      await fetch('/api/watch/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: projectPathRef.current }),
      });
    }

    projectPathRef.current = null;
    setWatchedPath(null);
    setWatching(false);
    setConnected(false);
  }, []);

  useEffect(() => {
    return () => {
      shouldReconnectRef.current = false;
      if (retryTimeoutRef.current !== null) {
        clearTimeout(retryTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return {
    connected,
    watching,
    watchedPath,
    lastImpact,
    impactHistory,
    startWatch,
    stopWatch,
    clearHistory,
  };
}
