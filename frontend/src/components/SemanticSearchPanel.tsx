import type { SemanticSearchResult, SemanticSearchMode } from '../api';

const MODE_OPTIONS: Array<{ value: SemanticSearchMode; label: string; description: string }> = [
  { value: 'code', label: 'Código', description: 'Foco em arquivos e implementações' },
  { value: 'arch', label: 'Arquitetura', description: 'Camadas e componentes principais' },
  { value: 'impact', label: 'Impacto', description: 'Nós com dependências/impactados' },
];

const highlightText = (text: string, tokens: string[]) => {
  if (!text) return text;
  const sanitized = tokens
    .map((token) => token.trim())
    .filter(Boolean)
    .map((token) => token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (!sanitized.length) {
    return text;
  }
  const splitRegex = new RegExp(`(${sanitized.join('|')})`, 'gi');
  const matchRegex = new RegExp(`^(${sanitized.join('|')})$`, 'i');
  const parts = text.split(splitRegex);
  return parts.map((part, index) => {
    if (matchRegex.test(part)) {
      return (
        <mark className="semantic-search-highlight" key={`${part}-${index}`}>
          {part}
        </mark>
      );
    }
    return part;
  });
};

interface SemanticSearchPanelProps {
  isOpen: boolean;
  query: string;
  onQueryChange: (value: string) => void;
  onSearch: () => void;
  loading: boolean;
  error?: string | null;
  mode: SemanticSearchMode;
  onModeChange: (mode: SemanticSearchMode) => void;
  results: SemanticSearchResult[];
  contextSummary?: string;
  contextNodes?: string[];
  onClose: () => void;
  onSelectResult: (nodeKey: string) => void;
  onImpactAction: (nodeKey: string) => void;
}

export default function SemanticSearchPanel({
  isOpen,
  query,
  onQueryChange,
  onSearch,
  loading,
  error,
  mode,
  onModeChange,
  results,
  contextSummary,
  contextNodes,
  onClose,
  onSelectResult,
  onImpactAction,
}: SemanticSearchPanelProps) {
  if (!isOpen) return null;

  return (
    <div className="semantic-search-overlay" role="dialog" aria-modal="true">
      <div className="semantic-search-panel">
        <div className="semantic-search-header">
          <div>
            <h3>Busca Semântica</h3>
            <p className="section-desc">Explorar código, arquitetura e impacto com contexto rápido.</p>
          </div>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Fechar busca">
            ✕
          </button>
        </div>

        <div className="semantic-mode-row">
          {MODE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`semantic-mode-btn ${mode === option.value ? 'active' : ''}`}
              onClick={() => onModeChange(option.value)}
            >
              <span>{option.label}</span>
              <small>{option.description}</small>
            </button>
          ))}
        </div>

        <div className="semantic-search-input">
          <input
            type="text"
            placeholder="Digite termos de busca..."
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                onSearch();
              }
            }}
          />
          <button className="btn btn-primary" onClick={onSearch} disabled={loading || !query.trim()}>
            {loading ? 'Buscando...' : 'Buscar'}
          </button>
        </div>

        {error && <div className="semantic-search-error">{error}</div>}

        <div className="semantic-search-results">
          {loading && !results.length && (
            <div className="semantic-search-empty">Buscando resultados semânticos...</div>
          )}
          {!loading && !results.length && <div className="semantic-search-empty">Nenhum resultado ainda.</div>}
          {results.map((result) => (
            <div key={result.namespace_key} className="semantic-search-result">
              <div className="result-header">
                <div>
                  <strong>{result.name || result.namespace_key}</strong>
                  <div className="result-meta">
                    {result.layer && <span>{result.layer}</span>}
                    {result.project && <span>{result.project}</span>}
                    {result.file && <span>{result.file}</span>}
                  </div>
                </div>
                <div className="result-score">
                  <span>{result.rag_score ? result.rag_score.toFixed(2) : '—'}</span>
                  <small>Hotspot {result.hotspot_score ?? 0}</small>
                </div>
              </div>
              <div className="result-preview">
                {highlightText(result.preview || result.summary || 'Sem snippet', result.highlight_terms)}
              </div>
              <div className="result-actions">
                <button className="btn btn-ghost" onClick={() => onSelectResult(result.namespace_key)}>
                  Ver no Grafo
                </button>
                <button className="btn btn-ghost" onClick={() => onImpactAction(result.namespace_key)}>
                  Analisar Impacto
                </button>
              </div>
            </div>
          ))}
        </div>

        {(contextNodes?.length || contextSummary) && (
          <div className="semantic-context-block">
            {contextNodes && contextNodes.length > 0 && (
              <div className="context-node-badges">
                {contextNodes.map((node) => (
                  <span key={node} className="context-badge">
                    {node}
                  </span>
                ))}
              </div>
            )}
            {contextSummary && <p className="context-summary">{contextSummary}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
