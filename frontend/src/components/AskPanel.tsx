import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { askQuestion } from '../api';
import type { AskResponse } from '../api';

interface ChatMessage {
  id: string;
  role: 'user' | 'ai';
  content: string;
  timestamp: number;
  model?: string;
  fallbackSummary?: string | null;
  fallbackSource?: string | null;
  relevantNodeKeys?: string[];
}

interface AskPanelProps {
  onClose: () => void;
  selectedNodeKey?: string | null;
  selectedNodeName?: string | null;
  selectedProject?: string | null;
  graphContext?: {
    totalNodes: number;
    totalEdges: number;
    visibleNodes: number;
    visibleEdges: number;
    selectedLayer?: string;
    liveChangedNodes?: number;
    liveImpactedNodes?: number;
    liveNewNodes?: number;
    liveRemovedNodes?: number;
    liveRiskScore?: number;
    liveSource?: string;
    liveFile?: string;
  };
  onHighlightNodes?: (nodeKeys: string[]) => void;
  onReferenceClick?: (nodeKey: string) => void;
  initialMessage?: string;
}

const HISTORY_STORAGE_KEY = 'insightgraph.ask.history.v2';

const BASE_SUGGESTIONS = [
  'o que acontece se eu deletar essa classe?',
  'quem usa isso?',
  'qual o impacto dessa mudanca?',
  'quais projetos dependem disso?',
  'quais endpoints dependem desse modulo?',
];

const makeId = (): string => `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

const normalizeRelevantKeys = (value: unknown): string[] => {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  const keys: string[] = [];
  for (const item of value) {
    if (typeof item !== 'string') continue;
    const key = item.trim();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    keys.push(key);
  }
  return keys;
};

const renderGraphContext = (context?: AskPanelProps['graphContext']): string => {
  if (!context) return '';
  const parts = [
    `visible_nodes=${context.visibleNodes}`,
    `visible_edges=${context.visibleEdges}`,
    `total_nodes=${context.totalNodes}`,
    `total_edges=${context.totalEdges}`,
  ];
  if (context.selectedLayer) {
    parts.push(`selected_layer=${context.selectedLayer}`);
  }
  if (typeof context.liveChangedNodes === 'number') parts.push(`live_changed=${context.liveChangedNodes}`);
  if (typeof context.liveImpactedNodes === 'number') parts.push(`live_impacted=${context.liveImpactedNodes}`);
  if (typeof context.liveNewNodes === 'number') parts.push(`live_new=${context.liveNewNodes}`);
  if (typeof context.liveRemovedNodes === 'number') parts.push(`live_removed=${context.liveRemovedNodes}`);
  if (typeof context.liveRiskScore === 'number') parts.push(`live_risk=${context.liveRiskScore}`);
  if (context.liveSource) parts.push(`live_source=${context.liveSource}`);
  if (context.liveFile) parts.push(`live_file=${context.liveFile}`);
  return parts.join(', ');
};

export default function AskPanel({
  onClose,
  selectedNodeKey,
  selectedNodeName,
  selectedProject,
  graphContext,
  onHighlightNodes,
  onReferenceClick,
  initialMessage,
}: AskPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try {
      const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  });
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failedQuestion, setFailedQuestion] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const lastAutoSentMessageRef = useRef<string | null>(null);

  const contextLabel = useMemo(() => {
    const parts: string[] = [];
    if (selectedProject) parts.push(`Projeto: ${selectedProject}`);
    if (selectedNodeName) parts.push(`No: ${selectedNodeName}`);
    return parts.join(' | ');
  }, [selectedNodeName, selectedProject]);

  const suggestions = useMemo(() => {
    if (!selectedNodeName) return BASE_SUGGESTIONS;
    return [
      `o que acontece se eu deletar ${selectedNodeName}?`,
      `quem usa ${selectedNodeName}?`,
      `qual o impacto de mudar ${selectedNodeName}?`,
      ...BASE_SUGGESTIONS.slice(2),
    ];
  }, [selectedNodeName]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, error]);

  useEffect(() => {
    try {
      localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(messages));
    } catch {
      // Ignore storage errors to keep chat usable.
    }
  }, [messages]);

  const handleSend = useCallback(
    async (text?: string, retry = false) => {
      const question = (text || input).trim();
      if (!question || loading) return;

      setError(null);
      setFailedQuestion(null);
      setInput('');
      setLoading(true);

      const outgoingUserMessage: ChatMessage = {
        id: makeId(),
        role: 'user',
        content: question,
        timestamp: Date.now(),
      };

      const baseHistory = retry ? messages : [...messages, outgoingUserMessage];
      if (!retry) {
        setMessages((prev) => [...prev, outgoingUserMessage]);
      }

      const conversation = baseHistory
        .slice(-8)
        .map((msg) => ({ role: msg.role, content: msg.content }));

      try {
        const response: AskResponse = await askQuestion(question, {
          contextNode: selectedNodeKey || undefined,
          project: selectedProject || undefined,
          graphContext: renderGraphContext(graphContext),
          conversation,
        });

        const relevantNodeKeys = normalizeRelevantKeys(response.relevant_nodes);
        if (relevantNodeKeys.length > 0) {
          onHighlightNodes?.(relevantNodeKeys);
        }

        const assistantMessage: ChatMessage = {
          id: makeId(),
          role: 'ai',
          content: response.answer,
          timestamp: Date.now(),
          model: response.model,
          fallbackSummary: response.fallback_summary,
          fallbackSource: response.fallback_source,
          relevantNodeKeys,
        };

        setMessages((prev) => [...prev, assistantMessage]);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setError(message || 'Falha ao consultar a IA local.');
        setFailedQuestion(question);
      } finally {
        setLoading(false);
      }
    },
    [
      graphContext,
      input,
      loading,
      messages,
      onHighlightNodes,
      selectedNodeKey,
      selectedProject,
    ]
  );

  useEffect(() => {
    if (!initialMessage || loading) return;
    if (lastAutoSentMessageRef.current === initialMessage) return;
    lastAutoSentMessageRef.current = initialMessage;
    void handleSend(initialMessage);
  }, [handleSend, initialMessage, loading]);

  const handleRetry = useCallback(() => {
    if (!failedQuestion) return;
    void handleSend(failedQuestion, true);
  }, [failedQuestion, handleSend]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };

  const handleClearHistory = () => {
    setMessages([]);
    setError(null);
    setFailedQuestion(null);
    localStorage.removeItem(HISTORY_STORAGE_KEY);
  };

  return (
    <div className="ask-panel">
      <div className="ask-panel-header">
        <div className="ask-panel-header-left">
          <div className="ask-panel-icon">AI</div>
          <div>
            <div className="ask-panel-title">InsightGraph AI</div>
            <div className="ask-panel-subtitle">Chat contextual local-first (Ollama)</div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {messages.length > 0 && (
            <button type="button" className="ask-suggestion-btn" onClick={handleClearHistory}>
              Limpar
            </button>
          )}
          <span className="node-detail-close" onClick={onClose}>
            X
          </span>
        </div>
      </div>

      {contextLabel && (
        <div style={{ padding: '8px 12px', borderBottom: '1px solid rgba(148, 163, 184, 0.2)', color: '#94a3b8', fontSize: 12 }}>
          {contextLabel}
        </div>
      )}

      {messages.length === 0 && (
        <div className="ask-suggestions">
          <div className="ask-suggestions-label">Perguntas sugeridas</div>
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              className="ask-suggestion-btn"
              onClick={() => void handleSend(suggestion)}
              disabled={loading}
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}

      <div className="ask-panel-messages">
        {messages.map((msg) => {
          const fallbackSummary = msg.fallbackSummary?.trim();
          const isFallback = Boolean(fallbackSummary);
          const showSummaryBlock = isFallback && fallbackSummary && !msg.content.startsWith(fallbackSummary);

          return (
            <div key={msg.id} className={`ask-message ${msg.role} ${isFallback ? 'fallback' : ''}`}>
              {isFallback && (
                <div className="fallback-badge">
                  Resumo local do grafo{msg.fallbackSource ? ` - ${msg.fallbackSource}` : ''}
                </div>
              )}
              {showSummaryBlock && <div className="fallback-summary-block">{fallbackSummary}</div>}
              <div className="ask-message-content">{msg.content}</div>
              {msg.model && <span className="model-tag">via {msg.model}</span>}

              {msg.role === 'ai' && msg.relevantNodeKeys && msg.relevantNodeKeys.length > 0 && (
                <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  <button
                    type="button"
                    className="ask-suggestion-btn"
                    onClick={() => onHighlightNodes?.(msg.relevantNodeKeys || [])}
                  >
                    Destacar no grafo
                  </button>
                  {msg.relevantNodeKeys.slice(0, 6).map((nodeKey) => (
                    <button
                      key={nodeKey}
                      type="button"
                      className="ask-suggestion-btn"
                      onClick={() => {
                        onHighlightNodes?.(msg.relevantNodeKeys || []);
                        onReferenceClick?.(nodeKey);
                      }}
                    >
                      {nodeKey}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}

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
        {error && (
          <div style={{ marginBottom: 8, color: '#fda4af', fontSize: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
            <span>{error}</span>
            <button type="button" className="ask-suggestion-btn" onClick={handleRetry} disabled={!failedQuestion || loading}>
              Retry
            </button>
          </div>
        )}
        <input
          className="ask-input"
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Pergunte sobre impacto, dependencias e risco arquitetural"
          disabled={loading}
          maxLength={600}
        />
        <button className="ask-send-btn" onClick={() => void handleSend()} disabled={loading || !input.trim()}>
          Enviar
        </button>
      </div>
    </div>
  );
}
