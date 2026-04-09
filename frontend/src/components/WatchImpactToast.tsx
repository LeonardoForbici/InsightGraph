/**
 * WatchImpactToast — Notificação de impacto em tempo real
 * 
 * Aparece automaticamente quando lastImpact chega do WebSocket.
 * Mostra por 8 segundos e some.
 * Empilha múltiplas notificações se vierem rápido.
 */

import { useEffect, useState } from 'react';
import type { ImpactResult } from '../hooks/useWatchMode';

interface WatchImpactToastProps {
    impact: ImpactResult | null;
    onViewInGraph?: (impact: ImpactResult) => void;
}

interface ToastItem {
    id: string;
    impact: ImpactResult;
    expiresAt: number;
}

const TOAST_DURATION = 8000; // 8 segundos
const TOAST_STACK_LIMIT = 5;

export default function WatchImpactToast({ impact, onViewInGraph }: WatchImpactToastProps) {
    const [toasts, setToasts] = useState<ToastItem[]>([]);

    // Adicionar novo toast quando impact chega
    useEffect(() => {
        if (!impact) return;

        const id = `${impact.file}-${impact.timestamp}`;
        const expiresAt = Date.now() + TOAST_DURATION;

        setToasts((prev) => {
            // Evitar duplicatas
            if (prev.some((t) => t.id === id)) return prev;

            // Adicionar novo toast
            const updated = [{ id, impact, expiresAt }, ...prev];
            
            // Limitar stack
            return updated.slice(0, TOAST_STACK_LIMIT);
        });
    }, [impact]);

    // Remover toasts expirados
    useEffect(() => {
        if (toasts.length === 0) return;

        const interval = setInterval(() => {
            const now = Date.now();
            setToasts((prev) => prev.filter((t) => t.expiresAt > now));
        }, 1000);

        return () => clearInterval(interval);
    }, [toasts.length]);

    const handleViewInGraph = (toast: ToastItem) => {
        if (onViewInGraph) {
            onViewInGraph(toast.impact);
        }
        // Remover toast ao clicar
        setToasts((prev) => prev.filter((t) => t.id !== toast.id));
    };

    const handleDismiss = (id: string) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    };

    if (toasts.length === 0) return null;

    return (
        <div
            style={{
                position: 'fixed',
                top: '80px',
                right: '20px',
                zIndex: 9999,
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                maxWidth: '400px',
            }}
        >
            {toasts.map((toast) => (
                <ToastCard
                    key={toast.id}
                    toast={toast}
                    onViewInGraph={() => handleViewInGraph(toast)}
                    onDismiss={() => handleDismiss(toast.id)}
                />
            ))}
        </div>
    );
}

interface ToastCardProps {
    toast: ToastItem;
    onViewInGraph: () => void;
    onDismiss: () => void;
}

function ToastCard({ toast, onViewInGraph, onDismiss }: ToastCardProps) {
    const { impact } = toast;
    const fileName = impact.file.split('/').pop() || impact.file;
    const riskScore = Math.round(impact.risk_score);
    const couplingDelta = Math.round(impact.coupling_delta);

    // Cor baseada no risco
    let riskColor = '#22c55e'; // verde
    let riskBg = 'rgba(34, 197, 94, 0.1)';
    if (riskScore > 70) {
        riskColor = '#ef4444'; // vermelho
        riskBg = 'rgba(239, 68, 68, 0.1)';
    } else if (riskScore > 30) {
        riskColor = '#eab308'; // amarelo
        riskBg = 'rgba(234, 179, 8, 0.1)';
    }

    // Seta de coupling
    const couplingArrow = couplingDelta > 0 ? '↑' : couplingDelta < 0 ? '↓' : '→';
    const couplingColor = couplingDelta > 0 ? '#ef4444' : couplingDelta < 0 ? '#22c55e' : '#94a3b8';

    return (
        <div
            style={{
                background: '#1e293b',
                border: `2px solid ${riskColor}`,
                borderRadius: '12px',
                padding: '16px',
                boxShadow: `0 8px 24px rgba(0, 0, 0, 0.4), 0 0 0 1px ${riskColor}40`,
                color: '#e2e8f0',
                fontSize: '0.9rem',
                animation: 'slideInRight 0.3s ease-out',
                position: 'relative',
            }}
        >
            {/* Botão de fechar */}
            <button
                onClick={onDismiss}
                style={{
                    position: 'absolute',
                    top: '8px',
                    right: '8px',
                    background: 'transparent',
                    border: 'none',
                    color: '#94a3b8',
                    cursor: 'pointer',
                    fontSize: '1.2rem',
                    lineHeight: 1,
                    padding: '4px',
                }}
                title="Fechar"
            >
                ×
            </button>

            {/* Ícone + Nome do arquivo */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <span style={{ fontSize: '1.2rem' }}>📁</span>
                <span style={{ fontWeight: '600', fontSize: '0.95rem' }}>{fileName}</span>
            </div>

            {/* Resumo */}
            <div style={{ marginBottom: '12px', color: '#cbd5e1', fontSize: '0.85rem' }}>
                {impact.summary}
            </div>

            {/* Métricas */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '12px' }}>
                {/* Risk Score */}
                <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginBottom: '4px' }}>
                        Risco
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div
                            style={{
                                flex: 1,
                                height: '8px',
                                background: '#334155',
                                borderRadius: '4px',
                                overflow: 'hidden',
                            }}
                        >
                            <div
                                style={{
                                    width: `${riskScore}%`,
                                    height: '100%',
                                    background: riskColor,
                                    transition: 'width 0.3s ease',
                                }}
                            />
                        </div>
                        <span style={{ fontSize: '0.85rem', fontWeight: '600', color: riskColor }}>
                            {riskScore}%
                        </span>
                    </div>
                </div>

                {/* Coupling Delta */}
                {couplingDelta !== 0 && (
                    <div>
                        <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginBottom: '4px' }}>
                            Acoplamento
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <span style={{ fontSize: '1.2rem', color: couplingColor }}>
                                {couplingArrow}
                            </span>
                            <span style={{ fontSize: '0.85rem', fontWeight: '600', color: couplingColor }}>
                                {Math.abs(couplingDelta)}
                            </span>
                        </div>
                    </div>
                )}
            </div>

            {/* Botão Ver no Grafo */}
            <button
                onClick={onViewInGraph}
                style={{
                    width: '100%',
                    padding: '8px 12px',
                    background: riskBg,
                    border: `1px solid ${riskColor}`,
                    borderRadius: '6px',
                    color: riskColor,
                    fontSize: '0.85rem',
                    fontWeight: '600',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                }}
                onMouseEnter={(e) => {
                    e.currentTarget.style.background = `${riskColor}20`;
                }}
                onMouseLeave={(e) => {
                    e.currentTarget.style.background = riskBg;
                }}
            >
                Ver no grafo
            </button>
        </div>
    );
}

// Adicionar animação CSS
const style = document.createElement('style');
style.textContent = `
@keyframes slideInRight {
    from {
        transform: translateX(100%);
        opacity: 0;
    }
    to {
        transform: translateX(0);
        opacity: 1;
    }
}
`;
document.head.appendChild(style);
