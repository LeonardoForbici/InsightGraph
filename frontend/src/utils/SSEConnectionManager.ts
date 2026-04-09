/**
 * SSEConnectionManager - Gerenciador de conexão Server-Sent Events (SSE)
 * 
 * Gerencia conexão EventSource com o endpoint /api/events para receber
 * atualizações em tempo real do backend.
 * 
 * Features:
 * - Reconexão automática com backoff exponencial (1s, 2s, 4s, 8s, 16s)
 * - Limite de 5 tentativas de reconexão
 * - Tratamento de erros robusto
 * - Suporte a múltiplos tipos de eventos
 * - Cleanup automático de recursos
 * 
 * Validação: Requirements 13.4, 13.5
 */

import type { SSEEventType, SSEEventData, SSEEventHandler } from './sse-types';

interface SSEConnectionManagerOptions {
    url?: string;
    maxReconnectAttempts?: number;
    initialRetryDelay?: number;
}

const DEFAULT_URL = '/api/events';
const MAX_RECONNECT_ATTEMPTS = 5;
const INITIAL_RETRY_DELAY = 1000; // 1 second
const BACKOFF_MULTIPLIER = 2;

export class SSEConnectionManager {
    private eventSource: EventSource | null = null;
    private url: string;
    private maxReconnectAttempts: number;
    private initialRetryDelay: number;
    private reconnectAttempts: number = 0;
    private retryDelay: number;
    private retryTimeout: number | null = null;
    private shouldReconnect: boolean = false;
    private eventHandlers: Map<SSEEventType, Set<SSEEventHandler>> = new Map();
    private connectionStateHandlers: Set<(connected: boolean) => void> = new Set();

    constructor(options: SSEConnectionManagerOptions = {}) {
        this.url = options.url || DEFAULT_URL;
        this.maxReconnectAttempts = options.maxReconnectAttempts || MAX_RECONNECT_ATTEMPTS;
        this.initialRetryDelay = options.initialRetryDelay || INITIAL_RETRY_DELAY;
        this.retryDelay = this.initialRetryDelay;
    }

    /**
     * Conecta ao endpoint SSE
     */
    connect(): void {
        if (this.eventSource) {
            console.warn('[SSEConnectionManager] Já existe uma conexão ativa');
            return;
        }

        console.log('[SSEConnectionManager] Conectando ao SSE:', this.url);
        this.shouldReconnect = true;
        this.createEventSource();
    }

    /**
     * Desconecta do endpoint SSE
     */
    disconnect(): void {
        console.log('[SSEConnectionManager] Desconectando do SSE');
        this.shouldReconnect = false;
        this.reconnectAttempts = 0;
        this.retryDelay = this.initialRetryDelay;

        if (this.retryTimeout !== null) {
            clearTimeout(this.retryTimeout);
            this.retryTimeout = null;
        }

        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
            this.notifyConnectionState(false);
        }
    }

    /**
     * Registra handler para tipo de evento específico
     */
    addEventListener(eventType: SSEEventType, handler: SSEEventHandler): void {
        if (!this.eventHandlers.has(eventType)) {
            this.eventHandlers.set(eventType, new Set());
        }
        this.eventHandlers.get(eventType)!.add(handler);
    }

    /**
     * Remove handler para tipo de evento específico
     */
    removeEventListener(eventType: SSEEventType, handler: SSEEventHandler): void {
        const handlers = this.eventHandlers.get(eventType);
        if (handlers) {
            handlers.delete(handler);
        }
    }

    /**
     * Registra handler para mudanças no estado de conexão
     */
    onConnectionStateChange(handler: (connected: boolean) => void): void {
        this.connectionStateHandlers.add(handler);
    }

    /**
     * Remove handler de mudanças no estado de conexão
     */
    offConnectionStateChange(handler: (connected: boolean) => void): void {
        this.connectionStateHandlers.delete(handler);
    }

    /**
     * Retorna se está conectado
     */
    isConnected(): boolean {
        return this.eventSource !== null && this.eventSource.readyState === EventSource.OPEN;
    }

    /**
     * Retorna número de tentativas de reconexão
     */
    getReconnectAttempts(): number {
        return this.reconnectAttempts;
    }

    /**
     * Cria nova instância do EventSource
     */
    private createEventSource(): void {
        try {
            this.eventSource = new EventSource(this.url);

            this.eventSource.onopen = () => {
                console.log('[SSEConnectionManager] Conexão SSE estabelecida');
                this.reconnectAttempts = 0;
                this.retryDelay = this.initialRetryDelay;
                this.notifyConnectionState(true);
            };

            this.eventSource.onerror = (error) => {
                console.error('[SSEConnectionManager] Erro na conexão SSE:', error);
                
                if (this.eventSource) {
                    this.eventSource.close();
                    this.eventSource = null;
                }

                this.notifyConnectionState(false);
                this.handleReconnect();
            };

            // Registrar listeners para cada tipo de evento
            const eventTypes: SSEEventType[] = [
                'graph_updated',
                'impact_detected',
                'audit_alert',
                'scan_complete',
                'node_changed'
            ];

            eventTypes.forEach(eventType => {
                this.eventSource!.addEventListener(eventType, (event: MessageEvent) => {
                    this.handleEvent(eventType, event);
                });
            });

        } catch (error) {
            console.error('[SSEConnectionManager] Erro ao criar EventSource:', error);
            this.handleReconnect();
        }
    }

    /**
     * Processa evento recebido
     */
    private handleEvent(eventType: SSEEventType, event: MessageEvent): void {
        try {
            const payload = JSON.parse(event.data);
            const eventData: SSEEventData = {
                type: eventType,
                payload,
                timestamp: Date.now()
            };

            console.log(`[SSEConnectionManager] Evento recebido: ${eventType}`, payload);

            // Notificar handlers registrados
            const handlers = this.eventHandlers.get(eventType);
            if (handlers) {
                handlers.forEach(handler => {
                    try {
                        handler(eventData);
                    } catch (error) {
                        console.error(`[SSEConnectionManager] Erro ao executar handler para ${eventType}:`, error);
                    }
                });
            }
        } catch (error) {
            console.error('[SSEConnectionManager] Erro ao processar evento:', error);
        }
    }

    /**
     * Gerencia lógica de reconexão com backoff exponencial
     */
    private handleReconnect(): void {
        if (!this.shouldReconnect) {
            console.log('[SSEConnectionManager] Reconexão desabilitada');
            return;
        }

        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error(
                `[SSEConnectionManager] Máximo de ${this.maxReconnectAttempts} tentativas de reconexão atingido`
            );
            this.shouldReconnect = false;
            return;
        }

        this.reconnectAttempts++;
        console.log(
            `[SSEConnectionManager] Tentativa de reconexão ${this.reconnectAttempts}/${this.maxReconnectAttempts} em ${this.retryDelay}ms`
        );

        this.retryTimeout = window.setTimeout(() => {
            this.createEventSource();
        }, this.retryDelay);

        // Backoff exponencial: 1s, 2s, 4s, 8s, 16s
        this.retryDelay = this.retryDelay * BACKOFF_MULTIPLIER;
    }

    /**
     * Notifica handlers sobre mudança no estado de conexão
     */
    private notifyConnectionState(connected: boolean): void {
        this.connectionStateHandlers.forEach(handler => {
            try {
                handler(connected);
            } catch (error) {
                console.error('[SSEConnectionManager] Erro ao notificar mudança de estado:', error);
            }
        });
    }

    /**
     * Cleanup de recursos
     */
    destroy(): void {
        this.disconnect();
        this.eventHandlers.clear();
        this.connectionStateHandlers.clear();
    }
}
