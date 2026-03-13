import { useState, useRef, useEffect, useCallback } from 'react';
import { askQuestion } from '../api';
import type { AskResponse } from '../api';

interface ChatMessage {
    role: 'user' | 'ai';
    content: string;
    model?: string;
}

interface AskPanelProps {
    onClose: () => void;
    selectedNodeKey?: string | null;
    onHighlightNodes?: (nodeKeys: string[]) => void;
    initialMessage?: string;
}

const SUGGESTIONS = [
    'Quais endpoints usam essa tabela?',
    'Qual tela chama essa API?',
    'O que acontece se eu remover essa coluna?',
    'Quais são os pontos críticos do sistema?',
    'Liste todas as dependências desse serviço.',
];

export default function AskPanel({ onClose, selectedNodeKey, onHighlightNodes, initialMessage }: AskPanelProps) {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const initialMessageSentRef = useRef(false);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, loading]);

    // Auto-send initial message when panel opens
    useEffect(() => {
        if (initialMessage && !initialMessageSentRef.current && !loading) {
            initialMessageSentRef.current = true;
            handleSend(initialMessage);
        }
    }, [initialMessage]);

    const handleSend = useCallback(async (text?: string) => {
        const question = text || input.trim();
        if (!question || loading) return;

        setInput('');
        setMessages((prev) => [...prev, { role: 'user', content: question }]);
        setLoading(true);

        try {
            const response: AskResponse = await askQuestion(
                question,
                selectedNodeKey || undefined,
            );
            
            if (response.relevant_nodes && response.relevant_nodes.length > 0) {
                onHighlightNodes?.(response.relevant_nodes);
            }

            setMessages((prev) => [
                ...prev,
                { role: 'ai', content: response.answer, model: response.model },
            ]);
        } catch (err) {
            setMessages((prev) => [
                ...prev,
                {
                    role: 'ai',
                    content: `Erro ao consultar a IA. Verifique se o Ollama está rodando e se os modelos necessários estão disponíveis.\n\n${err}`,
                },
            ]);
        } finally {
            setLoading(false);
        }
    }, [input, loading, selectedNodeKey]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <div className="ask-panel">
            <div className="ask-panel-header">
                <div className="ask-panel-header-left">
                    <div className="ask-panel-icon">🤖</div>
                    <div>
                    <div className="ask-panel-title">InsightGraph AI</div>
                    <div className="ask-panel-subtitle">Chat & Q&A · Interface Inteligente</div>
                    </div>
                </div>
                <span className="node-detail-close" onClick={onClose}>
                    ✕
                </span>
            </div>

            {messages.length === 0 && (
                <div className="ask-suggestions">
                    <div className="ask-suggestions-label">Sugestões</div>
                    {SUGGESTIONS.map((s, i) => (
                        <button
                            key={i}
                            className="ask-suggestion-btn"
                            onClick={() => handleSend(s)}
                        >
                            {s}
                        </button>
                    ))}
                </div>
            )}

            <div className="ask-panel-messages">
                {messages.map((msg, i) => (
                    <div key={i} className={`ask-message ${msg.role}`}>
                        {msg.content}
                        {msg.model && (
                            <span className="model-tag">via {msg.model}</span>
                        )}
                    </div>
                ))}
                {loading && (
                    <div className="ask-typing">
                        <div className="ask-typing-dot" />
                        <div className="ask-typing-dot" />
                        <div className="ask-typing-dot" />
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>

            <div className="ask-panel-input">
                <input
                    className="ask-input"
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Pergunte sobre a arquitetura (Ex: Como esse módulo funciona?)"
                    disabled={loading}
                />
                <button
                    className="ask-send-btn"
                    onClick={() => handleSend()}
                    disabled={loading || !input.trim()}
                >
                    ➤
                </button>
            </div>
        </div>
    );
}
