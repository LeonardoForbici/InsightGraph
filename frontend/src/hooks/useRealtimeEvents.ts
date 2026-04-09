/**
 * useRealtimeEvents - Hook React para eventos em tempo real via SSE
 * 
 * Conecta ao endpoint /api/events e recebe atualizações em tempo real
 * do backend usando Server-Sent Events (SSE).
 * 
 * Features:
 * - Conexão automática ao montar
 * - Reconexão automática com backoff exponencial
 * - Suporte a múltiplos tipos de eventos
 * - Handlers customizáveis por tipo de evento
 * - Cleanup automático ao desmontar
 * 
 * Validação: Requirements 1.5, 13.5
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { SSEConnectionManager } from '../utils/SSEConnectionManager';
import type { SSEEventType, SSEEventData } from '../utils/sse-types';

export interface UseRealtimeEventsOptions {
    /**
     * URL do endpoint SSE (padrão: /api/events)
     */
    url?: string;
    
    /**
     * Conectar automaticamente ao montar (padrão: true)
     */
    autoConnect?: boolean;
    
    /**
     * Handlers para tipos de eventos específicos
     */
    handlers?: Partial<Record<SSEEventType, (data: SSEEventData) => void>>;
}

export interface UseRealtimeEventsReturn {
    /**
     * Estado da conexão SSE
     */
    connected: boolean;
    
    /**
     * Número de tentativas de reconexão
     */
    reconnectAttempts: number;
    
    /**
     * Último evento recebido
     */
    lastEvent: SSEEventData | null;
    
    /**
     * Conectar manualmente ao SSE
     */
    connect: () => void;
    
    /**
     * Desconectar do SSE
     */
    disconnect: () => void;
    
    /**
     * Adicionar handler para tipo de evento
     */
    addEventListener: (eventType: SSEEventType, handler: (data: SSEEventData) => void) => void;
    
    /**
     * Remover handler para tipo de evento
     */
    removeEventListener: (eventType: SSEEventType, handler: (data: SSEEventData) => void) => void;
}

/**
 * Hook para gerenciar conexão SSE e receber eventos em tempo real
 */
export function useRealtimeEvents(
    options: UseRealtimeEventsOptions = {}
): UseRealtimeEventsReturn {
    const {
        url = '/api/events',
        autoConnect = true,
        handlers = {}
    } = options;
    
    const [connected, setConnected] = useState(false);
    const [reconnectAttempts, setReconnectAttempts] = useState(0);
    const [lastEvent, setLastEvent] = useState<SSEEventData | null>(null);
    
    const managerRef = useRef<SSEConnectionManager | null>(null);
    const handlersRef = useRef<Map<SSEEventType, Set<(data: SSEEventData) => void>>>(new Map());
    
    // Inicializar SSEConnectionManager
    useEffect(() => {
        console.log('[useRealtimeEvents] Inicializando SSEConnectionManager');
        
        managerRef.current = new SSEConnectionManager({ url });
        
        // Registrar handler de mudança de estado de conexão
        managerRef.current.onConnectionStateChange((isConnected) => {
            console.log('[useRealtimeEvents] Estado de conexão:', isConnected);
            setConnected(isConnected);
            
            if (isConnected) {
                setReconnectAttempts(0);
            } else {
                const attempts = managerRef.current?.getReconnectAttempts() || 0;
                setReconnectAttempts(attempts);
            }
        });
        
        // Conectar automaticamente se habilitado
        if (autoConnect) {
            managerRef.current.connect();
        }
        
        // Cleanup ao desmontar
        return () => {
            console.log('[useRealtimeEvents] Cleanup - destruindo SSEConnectionManager');
            if (managerRef.current) {
                managerRef.current.destroy();
                managerRef.current = null;
            }
        };
    }, [url, autoConnect]);
    
    // Registrar handlers iniciais
    useEffect(() => {
        if (!managerRef.current) return;
        
        Object.entries(handlers).forEach(([eventType, handler]) => {
            if (handler) {
                const wrappedHandler = (data: SSEEventData) => {
                    setLastEvent(data);
                    handler(data);
                };
                
                managerRef.current!.addEventListener(eventType as SSEEventType, wrappedHandler);
                
                // Armazenar referência para cleanup
                if (!handlersRef.current.has(eventType as SSEEventType)) {
                    handlersRef.current.set(eventType as SSEEventType, new Set());
                }
                handlersRef.current.get(eventType as SSEEventType)!.add(wrappedHandler);
            }
        });
        
        // Cleanup handlers ao desmontar ou quando handlers mudarem
        return () => {
            if (!managerRef.current) return;
            
            handlersRef.current.forEach((handlerSet, eventType) => {
                handlerSet.forEach(handler => {
                    managerRef.current!.removeEventListener(eventType, handler);
                });
            });
            handlersRef.current.clear();
        };
    }, [handlers]);
    
    // Conectar manualmente
    const connect = useCallback(() => {
        if (managerRef.current) {
            console.log('[useRealtimeEvents] Conectando manualmente');
            managerRef.current.connect();
        }
    }, []);
    
    // Desconectar
    const disconnect = useCallback(() => {
        if (managerRef.current) {
            console.log('[useRealtimeEvents] Desconectando');
            managerRef.current.disconnect();
        }
    }, []);
    
    // Adicionar handler dinamicamente
    const addEventListener = useCallback((
        eventType: SSEEventType, 
        handler: (data: SSEEventData) => void
    ) => {
        if (!managerRef.current) {
            console.warn('[useRealtimeEvents] Manager não inicializado');
            return;
        }
        
        const wrappedHandler = (data: SSEEventData) => {
            setLastEvent(data);
            handler(data);
        };
        
        managerRef.current.addEventListener(eventType, wrappedHandler);
        
        // Armazenar referência
        if (!handlersRef.current.has(eventType)) {
            handlersRef.current.set(eventType, new Set());
        }
        handlersRef.current.get(eventType)!.add(wrappedHandler);
    }, []);
    
    // Remover handler dinamicamente
    const removeEventListener = useCallback((
        eventType: SSEEventType, 
        handler: (data: SSEEventData) => void
    ) => {
        if (!managerRef.current) {
            console.warn('[useRealtimeEvents] Manager não inicializado');
            return;
        }
        
        managerRef.current.removeEventListener(eventType, handler);
        
        // Remover referência
        const handlerSet = handlersRef.current.get(eventType);
        if (handlerSet) {
            handlerSet.delete(handler);
        }
    }, []);
    
    return {
        connected,
        reconnectAttempts,
        lastEvent,
        connect,
        disconnect,
        addEventListener,
        removeEventListener
    };
}
