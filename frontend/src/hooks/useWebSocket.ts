import { useEffect, useRef, useState, useCallback } from 'react';
import { useRealtimeEvents } from './useRealtimeEvents';
import { WebSocketClient } from '../utils/WebSocketClient';

export interface UseWebSocketOptions {
  url?: string;
  token?: string;
  autoConnect?: boolean;
  handlers?: Record<string, (payload: any) => void>;
  fallbackToSSE?: boolean;
  sseUrl?: string;
  heartbeatInterval?: number;
}

export interface UseWebSocketReturn {
  connected: boolean;
  reconnectAttempts: number;
  lastEvent: any;
  latency: number | null;
  send: (payload: any) => void;
  addEventListener: (eventType: string, handler: (payload: any) => void) => void;
  removeEventListener: (eventType: string, handler: (payload: any) => void) => void;
  connect: () => void;
  disconnect: () => void;
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    url = '/ws',
    token,
    autoConnect = true,
    handlers = {},
    fallbackToSSE = true,
    sseUrl = '/api/events',
    heartbeatInterval,
  } = options;

  const clientRef = useRef<WebSocketClient | null>(null);
  const [connected, setConnected] = useState(false);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [lastEvent, setLastEvent] = useState<any>(null);
  const [latency, setLatency] = useState<number | null>(null);

  const { connect: connectFallback, disconnect: disconnectFallback, lastEvent: fallbackLastEvent } =
    useRealtimeEvents({
      url: sseUrl,
      autoConnect: false,
      handlers,
    });

  useEffect(() => {
    if (fallbackLastEvent) {
      setLastEvent(fallbackLastEvent);
    }
  }, [fallbackLastEvent]);

  useEffect(() => {
    clientRef.current = new WebSocketClient({
      url,
      token,
      heartbeatInterval,
    });

    const client = clientRef.current;

    const handleOpen = () => setConnected(true);
    const handleClose = () => setConnected(false);
    const handleLatency = (value: number) => setLatency(value);
    const handleReconnect = (payload: any) => setReconnectAttempts(payload?.attempt ?? client.getReconnectAttempts());
    const handleMessage = (payload: any) => {
      setLastEvent(payload);
    };

    client.addEventListener('open', handleOpen);
    client.addEventListener('close', handleClose);
    client.addEventListener('latency', handleLatency);
    client.addEventListener('reconnect', handleReconnect);
    client.addEventListener('message', handleMessage);

    if (autoConnect) {
      client.connect();
    }

    return () => {
      client.removeEventListener('open', handleOpen);
      client.removeEventListener('close', handleClose);
      client.removeEventListener('latency', handleLatency);
      client.removeEventListener('reconnect', handleReconnect);
      client.removeEventListener('message', handleMessage);
      client.destroy();
    };
  }, [url, token, autoConnect, heartbeatInterval]);

  useEffect(() => {
    if (!fallbackToSSE) {
      return;
    }

    if (!connected) {
      connectFallback();
    } else {
      disconnectFallback();
    }
  }, [connected, fallbackToSSE, connectFallback, disconnectFallback]);

  useEffect(() => {
    const client = clientRef.current;
    if (!client) return;

    const registered: (() => void)[] = [];
    Object.entries(handlers).forEach(([eventType, handler]) => {
      const wrapped = (payload: any) => {
        setLastEvent(payload);
        handler(payload);
      };
      client.addEventListener(eventType, wrapped);
      registered.push(() => client.removeEventListener(eventType, wrapped));
    });

    return () => {
      registered.forEach((cleanup) => cleanup());
    };
  }, [handlers]);

  const send = useCallback((payload: any) => {
    clientRef.current?.send(payload);
  }, []);

  const addEventListener = useCallback((eventType: string, handler: (payload: any) => void) => {
    clientRef.current?.addEventListener(eventType, handler);
  }, []);

  const removeEventListener = useCallback((eventType: string, handler: (payload: any) => void) => {
    clientRef.current?.removeEventListener(eventType, handler);
  }, []);

  const connect = useCallback(() => {
    clientRef.current?.connect();
  }, []);

  const disconnect = useCallback(() => {
    clientRef.current?.disconnect();
  }, []);

  return {
    connected,
    reconnectAttempts,
    lastEvent,
    latency,
    send,
    addEventListener,
    removeEventListener,
    connect,
    disconnect,
  };
}
