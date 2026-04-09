/**
 * useWatchMode — Hook React para Watch Mode em tempo real
 * 
 * Conecta ao WebSocket /api/watch/ws/{encodedPath} e recebe atualizações
 * de impacto quando arquivos são modificados.
 * 
 * Features:
 * - Reconexão automática com backoff exponencial
 * - Heartbeat para manter conexão viva
 * - Histórico de impactos
 * - Estado de conexão
 */

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
    lastImpact: ImpactResult | null;
    impactHistory: ImpactResult[];
    startWatch: (path: string) => Promise<void>;
    stopWatch: () => Promise<void>;
    clearHistory: () => void;
}

const MAX_HISTORY = 20;
const INITIAL_RETRY_DELAY = 1000; // 1s
const MAX_RETRY_DELAY = 30000; // 30s
const BACKOFF_MULTIPLIER = 2;

export function useWatchMode(): UseWatchModeReturn {
    const [connected, setConnected] = useState(false);
    const [watching, setWatching] = useState(false);
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
        // Fechar conexão existente
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }

        // Codificar path para URL
        const encodedPath = encodeURIComponent(projectPath);
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/watch/ws/${encodedPath}`;

        console.log('[useWatchMode] Conectando ao WebSocket:', wsUrl);

        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
            console.log('[useWatchMode] WebSocket conectado');
            setConnected(true);
            retryDelayRef.current = INITIAL_RETRY_DELAY; // Reset retry delay
        };

        ws.onmessage = (event) => {
            try {
                const message: WatchMessage = JSON.parse(event.data);

                if (message.type === 'heartbeat') {
                    console.log('[useWatchMode] Heartbeat recebido');
                    return;
                }

                if (message.type === 'impact') {
                    console.log('[useWatchMode] Impact recebido:', message);
                    setLastImpact(message);
                    setImpactHistory((prev) => {
                        const updated = [message, ...prev];
                        return updated.slice(0, MAX_HISTORY);
                    });
                }
            } catch (error) {
                console.error('[useWatchMode] Erro ao processar mensagem:', error);
            }
        };

        ws.onerror = (error) => {
            console.error('[useWatchMode] WebSocket error:', error);
        };

        ws.onclose = () => {
            console.log('[useWatchMode] WebSocket fechado');
            setConnected(false);
            wsRef.current = null;

            // Reconectar se necessário
            if (shouldReconnectRef.current && projectPathRef.current) {
                const delay = retryDelayRef.current;
                console.log(`[useWatchMode] Reconectando em ${delay}ms...`);
                
                retryTimeoutRef.current = window.setTimeout(() => {
                    if (projectPathRef.current) {
                        connectWebSocket(projectPathRef.current);
                    }
                }, delay);

                // Aumentar delay para próxima tentativa (backoff exponencial)
                retryDelayRef.current = Math.min(
                    retryDelayRef.current * BACKOFF_MULTIPLIER,
                    MAX_RETRY_DELAY
                );
            }
        };
    }, []);

    const startWatch = useCallback(async (path: string) => {
        try {
            // Chamar API REST para iniciar watch
            const response = await fetch('/api/watch/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path }),
            });

            if (!response.ok) {
                const error = await response.text();
                throw new Error(`Failed to start watch: ${error}`);
            }

            console.log('[useWatchMode] Watch iniciado para:', path);
            
            // Salvar path e habilitar reconexão
            projectPathRef.current = path;
            shouldReconnectRef.current = true;
            setWatching(true);

            // Conectar WebSocket
            connectWebSocket(path);

        } catch (error) {
            console.error('[useWatchMode] Erro ao iniciar watch:', error);
            throw error;
        }
    }, [connectWebSocket]);

    const stopWatch = useCallback(async () => {
        try {
            // Desabilitar reconexão
            shouldReconnectRef.current = false;

            // Cancelar retry pendente
            if (retryTimeoutRef.current !== null) {
                clearTimeout(retryTimeoutRef.current);
                retryTimeoutRef.current = null;
            }

            // Fechar WebSocket
            if (wsRef.current) {
                wsRef.current.close();
                wsRef.current = null;
            }

            // Chamar API REST para parar watch
            if (projectPathRef.current) {
                const response = await fetch('/api/watch/stop', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: projectPathRef.current }),
                });

                if (!response.ok) {
                    const error = await response.text();
                    console.warn('[useWatchMode] Erro ao parar watch:', error);
                }
            }

            console.log('[useWatchMode] Watch parado');
            projectPathRef.current = null;
            setWatching(false);
            setConnected(false);

        } catch (error) {
            console.error('[useWatchMode] Erro ao parar watch:', error);
            throw error;
        }
    }, []);

    // Cleanup ao desmontar
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
        lastImpact,
        impactHistory,
        startWatch,
        stopWatch,
        clearHistory,
    };
}
