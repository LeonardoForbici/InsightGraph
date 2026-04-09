import React, { useState, useEffect, useRef } from 'react';

interface CodeReference {
  file: string;
  line: number;
  snippet: string;
  node_key: string;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  relevantNodes?: string[];
  references?: CodeReference[];
  confidence?: number;
}

interface AIQueryEngineProps {
  onNodesHighlight: (nodeKeys: string[]) => void;
  onReferenceClick?: (nodeKey: string) => void;
}

const AIQueryEngine: React.FC<AIQueryEngineProps> = ({
  onNodesHighlight,
  onReferenceClick
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load conversation history from localStorage on mount
  useEffect(() => {
    const savedHistory = localStorage.getItem('ai_query_history');
    if (savedHistory) {
      try {
        const parsed = JSON.parse(savedHistory);
        setMessages(parsed);
      } catch (e) {
        console.error('Failed to load conversation history:', e);
      }
    }
  }, []);

  // Save conversation history to localStorage
  useEffect(() => {
    if (messages.length > 0) {
      localStorage.setItem('ai_query_history', JSON.stringify(messages));
    }
  }, [messages]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const generateId = (): string => {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  };

  const handleSubmit = async (question: string) => {
    if (!question.trim() || isLoading) return;

    // Add user message
    const userMessage: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: question.trim(),
      timestamp: Date.now()
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/ai/query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ question: question.trim() })
      });

      if (!response.ok) {
        if (response.status === 429) {
          throw new Error('Rate limit exceeded. Please wait a moment and try again.');
        }
        throw new Error('Failed to get AI response');
      }

      const data = await response.json();

      // Add assistant message
      const assistantMessage: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: data.answer,
        timestamp: Date.now(),
        relevantNodes: data.relevant_nodes || [],
        references: data.references || [],
        confidence: data.confidence
      };

      setMessages(prev => [...prev, assistantMessage]);

      // Highlight relevant nodes in graph
      if (data.relevant_nodes && data.relevant_nodes.length > 0) {
        onNodesHighlight(data.relevant_nodes);
      }
    } catch (err: any) {
      console.error('AI query failed:', err);
      setError(err.message || 'Failed to process query');

      // Add error message
      const errorMessage: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: `Sorry, I encountered an error: ${err.message || 'Unknown error'}`,
        timestamp: Date.now()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSubmit(input);
    }
  };

  const handleClearHistory = () => {
    if (window.confirm('Clear conversation history?')) {
      setMessages([]);
      localStorage.removeItem('ai_query_history');
    }
  };

  const formatTimestamp = (timestamp: number): string => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
  };

  return (
    <div className="ai-query-engine">
      <div className="ai-header">
        <h3>AI Query Engine</h3>
        {messages.length > 0 && (
          <button onClick={handleClearHistory} className="clear-button">
            Clear History
          </button>
        )}
      </div>

      <div className="messages-container">
        {messages.length === 0 && (
          <div className="welcome-message">
            <p>Ask me anything about your code!</p>
            <div className="example-queries">
              <p>Try asking:</p>
              <ul>
                <li>"What are the most fragile components?"</li>
                <li>"Which classes have the highest complexity?"</li>
                <li>"Show me the dependencies of UserService"</li>
                <li>"What would happen if I change AuthController?"</li>
              </ul>
            </div>
          </div>
        )}

        {messages.map(msg => (
          <ChatMessageComponent
            key={msg.id}
            message={msg}
            onReferenceClick={onReferenceClick}
          />
        ))}

        {isLoading && (
          <div className="loading-indicator">
            <div className="typing-animation">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <p>Thinking...</p>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="input-container">
        {error && (
          <div className="error-banner">
            {error}
          </div>
        )}
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Ask about your code..."
          className="query-input"
          disabled={isLoading}
          maxLength={500}
        />
        <button
          onClick={() => handleSubmit(input)}
          disabled={isLoading || !input.trim()}
          className="submit-button"
        >
          Send
        </button>
      </div>
    </div>
  );
};

interface ChatMessageComponentProps {
  message: ChatMessage;
  onReferenceClick?: (nodeKey: string) => void;
}

const ChatMessageComponent: React.FC<ChatMessageComponentProps> = ({
  message,
  onReferenceClick
}) => {
  const formatTimestamp = (timestamp: number): string => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
  };

  return (
    <div className={`chat-message ${message.role}`}>
      <div className="message-header">
        <span className="role-badge">{message.role === 'user' ? 'You' : 'AI'}</span>
        <span className="timestamp">{formatTimestamp(message.timestamp)}</span>
        {message.confidence !== undefined && (
          <span className="confidence-badge">
            {Math.round(message.confidence * 100)}% confident
          </span>
        )}
      </div>

      <div className="message-content">
        <p>{message.content}</p>
      </div>

      {message.references && message.references.length > 0 && (
        <div className="message-references">
          <h5>Code References:</h5>
          <ul>
            {message.references.map((ref, index) => (
              <li
                key={index}
                className="reference-item"
                onClick={() => onReferenceClick && onReferenceClick(ref.node_key)}
              >
                <span className="reference-file">{ref.file}</span>
                {ref.line > 0 && (
                  <span className="reference-line">:{ref.line}</span>
                )}
                {ref.snippet && (
                  <pre className="reference-snippet">{ref.snippet}</pre>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {message.relevantNodes && message.relevantNodes.length > 0 && (
        <div className="message-nodes">
          <p className="nodes-info">
            Highlighted {message.relevantNodes.length} relevant node(s) in the graph
          </p>
        </div>
      )}
    </div>
  );
};

export default AIQueryEngine;
