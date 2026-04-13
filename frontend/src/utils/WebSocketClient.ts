export type WebSocketEventPayload = Record<string, any>;
export type WebSocketEventHandler = (payload: any) => void;

export interface WebSocketClientOptions {
  url: string;
  token?: string;
  heartbeatInterval?: number;
  maxBackoffMs?: number;
  maxReconnectAttempts?: number;
  protocols?: string | string[];
}

export class WebSocketClient {
  private url: string;
  private token?: string;
  private heartbeatInterval: number;
  private maxBackoffMs: number;
  private maxReconnectAttempts: number;
  private protocols?: string | string[];

  private socket: WebSocket | null = null;
  private eventQueue: any[] = [];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private shouldReconnect = true;
  private reconnectAttempts = 0;

  private listeners: Map<string, Set<WebSocketEventHandler>> = new Map();

  constructor(options: WebSocketClientOptions) {
    this.url = options.url;
    this.token = options.token;
    this.heartbeatInterval = options.heartbeatInterval ?? 30000;
    this.maxBackoffMs = options.maxBackoffMs ?? 30000;
    this.maxReconnectAttempts = options.maxReconnectAttempts ?? Number.POSITIVE_INFINITY;
    this.protocols = options.protocols;
  }

  connect(): void {
    if (typeof window === 'undefined') return;

    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      return;
    }

    this.clearReconnectTimer();
    this.shouldReconnect = true;

    const endpoint = new URL(this.url, window.location.origin);
    if (this.token) {
      endpoint.searchParams.set('token', this.token);
    }

    this.socket = new WebSocket(endpoint.toString(), this.protocols ?? undefined);
    this.emit('connecting', null);

    this.socket.addEventListener('open', () => {
      this.reconnectAttempts = 0;
    this.emit('open', null);
    this.flushQueue();
      this.startHeartbeat();
    });

    this.socket.addEventListener('message', (event) => {
      this.handleMessage(event);
    });

    this.socket.addEventListener('close', (event) => {
      this.emit('close', event);
      this.stopHeartbeat();
      this.socket = null;
      if (this.shouldReconnect) {
        this.scheduleReconnect();
      }
    });

    this.socket.addEventListener('error', (event) => {
      this.emit('error', event);
    });
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.close(1000, 'client_disconnect');
    }
    this.stopHeartbeat();
    this.clearReconnectTimer();
  }

  send(payload: any): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      const data = typeof payload === 'string' ? payload : JSON.stringify(payload);
      this.socket.send(data);
      return;
    }
    this.eventQueue.push(payload);
  }

  addEventListener(eventType: string, handler: WebSocketEventHandler): void {
    const handlers = this.listeners.get(eventType) ?? new Set();
    handlers.add(handler);
    this.listeners.set(eventType, handlers);
  }

  removeEventListener(eventType: string, handler: WebSocketEventHandler): void {
    const handlers = this.listeners.get(eventType);
    if (!handlers) return;
    handlers.delete(handler);
    if (handlers.size === 0) {
      this.listeners.delete(eventType);
    }
  }

  getReconnectAttempts(): number {
    return this.reconnectAttempts;
  }

  destroy(): void {
    this.disconnect();
    this.listeners.clear();
    this.eventQueue = [];
  }

  private emit(eventType: string, payload: any): void {
    const handlers = this.listeners.get(eventType);
    if (!handlers) return;
    handlers.forEach((handler) => {
      try {
        handler(payload);
      } catch (err) {
        // swallow
      }
    });
  }

  private flushQueue(): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    while (this.eventQueue.length > 0) {
      const queued = this.eventQueue.shift();
      if (queued === undefined) continue;
      const message = typeof queued === 'string' ? queued : JSON.stringify(queued);
      this.socket.send(message);
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this.send({ type: 'ping', timestamp: Date.now() });
    }, this.heartbeatInterval);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.emit('failed', null);
      return;
    }

    this.reconnectAttempts += 1;
    const delay = Math.min(this.maxBackoffMs, 1000 * 2 ** Math.min(this.reconnectAttempts, 6));
    this.reconnectTimer = setTimeout(() => {
      this.emit('reconnect', { attempt: this.reconnectAttempts });
      this.connect();
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private handleMessage(event: MessageEvent): void {
    let data: any;
    try {
      data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
    } catch {
      data = event.data;
    }

    if (!data || typeof data !== 'object') {
      this.emit('message', data);
      return;
    }

    const { type, event_type: eventType, payload, timestamp } = data;

    if (type === 'event' && eventType) {
      this.emit(eventType, payload);
      this.emit('message', data);
      return;
    }

    if (type === 'ping') {
      this.send({ type: 'pong', timestamp: timestamp ?? Date.now() });
      return;
    }

    if (type === 'pong' && typeof timestamp === 'number') {
      this.emit('latency', Date.now() - timestamp);
      return;
    }

    this.emit(type ?? 'message', data);
  }
}
