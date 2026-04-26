import React, { useState, useEffect, useCallback } from 'react';

interface SettingsData {
  neo4jUri: string;
  neo4jUser: string;
  ollamaUrl: string;
  ollamaFastModel: string;
  ollamaChatModel: string;
  ollamaComplexModel: string;
  ollamaEmbedModel: string;
  ollamaSmallModel: string;
  sseEnabled: boolean;
  maxReconnectAttempts: number;
  initialRetryDelay: number;
  cacheTtl: number;
  scanInterval: number;
  auditInterval: number;
  maxCommits: number;
  githubRepository: string;
  githubBranch: string;
  githubToken: string;
  githubShallowClone: boolean;
  pollerPath: string;
  pollerInterval: number;
  enableAnalytics: boolean;
  theme: 'dark' | 'light' | 'auto';
  language: string;
}

const DEFAULT_SETTINGS: SettingsData = {
  neo4jUri: 'bolt://localhost:7687',
  neo4jUser: 'neo4j',
  ollamaUrl: 'http://localhost:11434',
  ollamaFastModel: 'qwen2.5-coder:1.5b',
  ollamaChatModel: 'qwen3.5:4b',
  ollamaComplexModel: 'qwen2.5:7b',
  ollamaEmbedModel: 'nomic-embed-text',
  ollamaSmallModel: 'qwen2.5-coder:7b',
  sseEnabled: true,
  maxReconnectAttempts: 5,
  initialRetryDelay: 1000,
  cacheTtl: 60,
  scanInterval: 300,
  auditInterval: 1800,
  maxCommits: 100,
  githubRepository: '',
  githubBranch: 'main',
  githubToken: '',
  githubShallowClone: true,
  pollerPath: '',
  pollerInterval: 60,
  enableAnalytics: false,
  theme: 'dark',
  language: 'pt-BR',
};

type Section = 'github' | 'ai' | 'poller' | 'database' | 'performance' | 'interface';

interface StatusBadgeProps { ok: boolean | null; label: string }
const StatusBadge: React.FC<StatusBadgeProps> = ({ ok, label }) => {
  const color = ok === null ? '#8b93b0' : ok ? '#22c55e' : '#ef4444';
  const dot = ok === null ? '○' : ok ? '●' : '●';
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color, fontWeight: 500 }}>
      <span style={{ fontSize: 8 }}>{dot}</span>{label}
    </span>
  );
};

const SettingsScreen: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const [settings, setSettings] = useState<SettingsData>(DEFAULT_SETTINGS);
  const [activeSection, setActiveSection] = useState<Section>('github');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ollamaStatus, setOllamaStatus] = useState<boolean | null>(null);
  const [githubStatus, setGithubStatus] = useState<boolean | null>(null);
  const [pollerStatus, setPollerStatus] = useState<{ active: boolean; last_commit: string | null; last_scan_at: string | null } | null>(null);
  const [testingOllama, setTestingOllama] = useState(false);
  const [testingGithub, setTestingGithub] = useState(false);

  useEffect(() => {
    // Load from localStorage first (always available)
    const s = { ...DEFAULT_SETTINGS };
    s.githubRepository = localStorage.getItem('githubRepository') || '';
    s.githubBranch = localStorage.getItem('githubBranch') || 'main';
    s.githubToken = localStorage.getItem('githubToken') || '';
    s.githubShallowClone = localStorage.getItem('githubShallowClone') !== 'false';

    // Load from backend
    fetch('/api/config/settings')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) {
          setSettings({
            ...s,
            neo4jUri: data.neo4j_uri || s.neo4jUri,
            neo4jUser: data.neo4j_user || s.neo4jUser,
            ollamaUrl: data.ollama_url || s.ollamaUrl,
            ollamaFastModel: data.ollama_fast_model || s.ollamaFastModel,
            ollamaChatModel: data.ollama_chat_model || s.ollamaChatModel,
            ollamaComplexModel: data.ollama_complex_model || s.ollamaComplexModel,
            ollamaEmbedModel: data.ollama_embed_model || s.ollamaEmbedModel,
            ollamaSmallModel: data.ollama_small_model || s.ollamaSmallModel,
          });
        } else {
          setSettings(s);
        }
      })
      .catch(() => setSettings(s));

    // Load poller status
    fetch('/api/poller/status')
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setPollerStatus(data); })
      .catch(() => {});
  }, []);

  const set = useCallback((field: keyof SettingsData, value: unknown) => {
    setSettings(prev => ({ ...prev, [field]: value }));
    setError(null);
    setSaved(false);
  }, []);

  const testOllama = useCallback(async () => {
    setTestingOllama(true);
    try {
      const r = await fetch(`${settings.ollamaUrl}/api/tags`);
      setOllamaStatus(r.ok);
    } catch {
      setOllamaStatus(false);
    } finally {
      setTestingOllama(false);
    }
  }, [settings.ollamaUrl]);

  const testGithub = useCallback(async () => {
    if (!settings.githubRepository) return;
    setTestingGithub(true);
    try {
      const url = settings.githubRepository.replace('https://github.com/', 'https://api.github.com/repos/');
      const headers: Record<string, string> = {};
      if (settings.githubToken) headers['Authorization'] = `token ${settings.githubToken}`;
      const r = await fetch(url, { headers });
      setGithubStatus(r.ok);
    } catch {
      setGithubStatus(false);
    } finally {
      setTestingGithub(false);
    }
  }, [settings.githubRepository, settings.githubToken]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      localStorage.setItem('githubRepository', settings.githubRepository);
      localStorage.setItem('githubBranch', settings.githubBranch);
      localStorage.setItem('githubToken', settings.githubToken);
      localStorage.setItem('githubShallowClone', String(settings.githubShallowClone));

      await fetch('/api/config/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          neo4j_uri: settings.neo4jUri,
          neo4j_user: settings.neo4jUser,
          ollama_url: settings.ollamaUrl,
          ollama_fast_model: settings.ollamaFastModel,
          ollama_chat_model: settings.ollamaChatModel,
          ollama_complex_model: settings.ollamaComplexModel,
          ollama_embed_model: settings.ollamaEmbedModel,
          ollama_small_model: settings.ollamaSmallModel,
          sse_enabled: settings.sseEnabled,
          max_reconnect_attempts: settings.maxReconnectAttempts,
          initial_retry_delay: settings.initialRetryDelay,
          cache_ttl: settings.cacheTtl,
          scan_interval: settings.scanInterval,
          audit_interval: settings.auditInterval,
          max_commits: settings.maxCommits,
          github_repository: settings.githubRepository,
          github_branch: settings.githubBranch,
          github_token: settings.githubToken,
          github_shallow_clone: settings.githubShallowClone,
          enable_analytics: settings.enableAnalytics,
          theme: settings.theme,
          language: settings.language,
        }),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch {
      setError('Falha ao salvar. Verifique se o backend está rodando.');
    } finally {
      setSaving(false);
    }
  }, [settings]);

  const sections: { id: Section; label: string; icon: string; badge?: string }[] = [
    { id: 'github', label: 'GitHub', icon: '⬡', badge: settings.githubRepository ? '✓' : undefined },
    { id: 'ai', label: 'IA (Ollama)', icon: '◈', badge: ollamaStatus === true ? '✓' : ollamaStatus === false ? '!' : undefined },
    { id: 'poller', label: 'Git Poller', icon: '⟳', badge: pollerStatus?.active ? '✓' : undefined },
    { id: 'database', label: 'Database', icon: '⬡' },
    { id: 'performance', label: 'Performance', icon: '◈' },
    { id: 'interface', label: 'Interface', icon: '◻' },
  ];

  const s: React.CSSProperties = {
    position: 'fixed', inset: 0, zIndex: 2000,
    background: 'rgba(4,6,20,0.97)',
    backdropFilter: 'blur(24px)',
    display: 'flex', flexDirection: 'column',
    fontFamily: 'var(--font-sans)',
  };

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '9px 12px',
    background: 'rgba(255,255,255,0.04)',
    border: '1px solid rgba(139,147,176,0.14)',
    borderRadius: 8, color: 'var(--text-primary)',
    fontSize: 13, outline: 'none',
    transition: 'border-color 0.15s',
    boxSizing: 'border-box',
  };

  const labelStyle: React.CSSProperties = {
    fontSize: 11.5, fontWeight: 600,
    color: 'rgba(139,147,176,0.6)',
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
    marginBottom: 6, display: 'block',
  };

  const fieldStyle: React.CSSProperties = { marginBottom: 20 };

  const cardStyle: React.CSSProperties = {
    background: 'rgba(255,255,255,0.03)',
    border: '1px solid rgba(139,147,176,0.1)',
    borderRadius: 12, padding: '20px 24px',
    marginBottom: 16,
  };

  return (
    <div style={s}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 28px', height: 56,
        borderBottom: '1px solid rgba(139,147,176,0.1)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <svg width="18" height="18" viewBox="0 0 16 16" fill="none" style={{ opacity: 0.6 }}>
            <path d="M6.5 1.5A1 1 0 0 1 7.5 1h1a1 1 0 0 1 .992.886L9.63 2.8a5 5 0 0 1 .87.506l.883-.317a1 1 0 0 1 1.18.447l.5.866a1 1 0 0 1-.228 1.265l-.714.573a5 5 0 0 1 0 1.02l.714.573a1 1 0 0 1 .228 1.264l-.5.866a1 1 0 0 1-1.18.447l-.883-.317a5 5 0 0 1-.87.506l-.13.914A1 1 0 0 1 9.5 15h-1a1 1 0 0 1-.992-.886L7.37 13.2a5 5 0 0 1-.87-.506l-.883.317a1 1 0 0 1-1.18-.447l-.5-.866a1 1 0 0 1 .228-1.265l.714-.573a5 5 0 0 1 0-1.02l-.714-.573A1 1 0 0 1 3.937 7.1l.5-.866a1 1 0 0 1 1.18-.447l.883.317a5 5 0 0 1 .87-.506L7.5 4.5A1 1 0 0 1 6.5 1.5z" stroke="currentColor" strokeWidth="1.2" fill="none"/>
            <circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.4" fill="none"/>
          </svg>
          <span style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)' }}>Configurações</span>
        </div>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: 'rgba(139,147,176,0.5)', cursor: 'pointer', fontSize: 20, padding: '0 4px', lineHeight: 1 }}
        >×</button>
      </div>

      {/* Body */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* Sidebar */}
        <div style={{
          width: 200, flexShrink: 0,
          borderRight: '1px solid rgba(139,147,176,0.08)',
          padding: '20px 12px',
          display: 'flex', flexDirection: 'column', gap: 4,
          overflowY: 'auto',
        }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', color: 'rgba(139,147,176,0.35)', textTransform: 'uppercase', padding: '0 8px 12px' }}>
            Seções
          </div>
          {sections.map(sec => (
            <button
              key={sec.id}
              onClick={() => setActiveSection(sec.id)}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '9px 12px', borderRadius: 8, border: 'none',
                background: activeSection === sec.id ? 'rgba(79,143,247,0.12)' : 'transparent',
                color: activeSection === sec.id ? '#4f8ff7' : 'rgba(139,147,176,0.7)',
                cursor: 'pointer', fontSize: 13, fontWeight: activeSection === sec.id ? 600 : 400,
                textAlign: 'left', transition: 'all 0.12s',
                borderLeft: activeSection === sec.id ? '2px solid #4f8ff7' : '2px solid transparent',
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {sec.label}
              </span>
              {sec.badge && (
                <span style={{
                  fontSize: 10, fontWeight: 700,
                  color: sec.badge === '!' ? '#ef4444' : '#22c55e',
                  background: sec.badge === '!' ? 'rgba(239,68,68,0.12)' : 'rgba(34,197,94,0.12)',
                  padding: '1px 6px', borderRadius: 4,
                }}>
                  {sec.badge}
                </span>
              )}
            </button>
          ))}

          {/* Save button in sidebar */}
          <div style={{ marginTop: 'auto', paddingTop: 24 }}>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                width: '100%', padding: '10px 16px',
                background: saved ? 'rgba(34,197,94,0.15)' : 'rgba(79,143,247,0.15)',
                border: `1px solid ${saved ? 'rgba(34,197,94,0.3)' : 'rgba(79,143,247,0.3)'}`,
                borderRadius: 8, color: saved ? '#22c55e' : '#4f8ff7',
                cursor: saving ? 'wait' : 'pointer', fontSize: 13, fontWeight: 600,
                transition: 'all 0.15s',
              }}
            >
              {saving ? 'Salvando…' : saved ? '✓ Salvo' : 'Salvar'}
            </button>
            {error && <p style={{ fontSize: 11, color: '#ef4444', marginTop: 8, textAlign: 'center' }}>{error}</p>}
          </div>
              </div>

        {/* Main content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '28px 36px' }}>

          {/* ─── GITHUB ─── */}
          {activeSection === 'github' && (
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>GitHub</h2>
              <p style={{ fontSize: 13, color: 'rgba(139,147,176,0.6)', marginBottom: 24 }}>
                Configure o repositório GitHub para Timeline 4D, análise temporal e Commit Timeline.
              </p>

              <div style={cardStyle}>
                <div style={{ ...fieldStyle }}>
                  <label style={labelStyle}>URL do Repositório</label>
                  <input
                    style={inputStyle}
                    type="text"
                    value={settings.githubRepository}
                    onChange={e => set('githubRepository', e.target.value)}
                    placeholder="https://github.com/usuario/repo"
                  />
                  <p style={{ fontSize: 11.5, color: 'rgba(139,147,176,0.45)', marginTop: 5 }}>
                    URL completa do repositório público ou privado
                  </p>
                </div>

                <div style={fieldStyle}>
                  <label style={labelStyle}>Branch</label>
                  <input
                    style={{ ...inputStyle, maxWidth: 220 }}
                    type="text"
                    value={settings.githubBranch}
                    onChange={e => set('githubBranch', e.target.value)}
                    placeholder="main"
                  />
                </div>

                <div style={fieldStyle}>
                  <label style={labelStyle}>Personal Access Token</label>
                  <input
                    style={inputStyle}
                    type="password"
                    value={settings.githubToken}
                    onChange={e => set('githubToken', e.target.value)}
                    placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                    autoComplete="new-password"
                  />
                  <p style={{ fontSize: 11.5, color: 'rgba(139,147,176,0.45)', marginTop: 5 }}>
                    Necessário para repositórios privados.{' '}
                    <a
                      href="https://github.com/settings/tokens/new?scopes=repo&description=InsightGraph"
                      target="_blank" rel="noopener noreferrer"
                      style={{ color: '#4f8ff7', textDecoration: 'none' }}
                    >
                      Gerar token →
                    </a>
                  </p>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, color: 'var(--text-primary)' }}>
                    <input
                      type="checkbox"
                      checked={settings.githubShallowClone}
                      onChange={e => set('githubShallowClone', e.target.checked)}
                      style={{ accentColor: '#4f8ff7' }}
                    />
                    Shallow clone (mais rápido)
                  </label>
                </div>
              </div>

              {/* Test connection card */}
              <div style={{ ...cardStyle, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>Testar conexão</div>
                  <StatusBadge
                    ok={githubStatus}
                    label={githubStatus === null ? 'Não testado' : githubStatus ? 'Repositório acessível' : 'Falha na conexão'}
                  />
                </div>
                <button
                  onClick={testGithub}
                  disabled={testingGithub || !settings.githubRepository}
                  style={{
                    padding: '8px 18px', borderRadius: 8,
                    background: 'rgba(79,143,247,0.1)', border: '1px solid rgba(79,143,247,0.25)',
                    color: '#4f8ff7', cursor: 'pointer', fontSize: 13, fontWeight: 500,
                    opacity: !settings.githubRepository ? 0.4 : 1,
                  }}
                >
                  {testingGithub ? 'Testando…' : 'Testar'}
                </button>
              </div>

              {settings.githubRepository && (
                <button
                  onClick={() => {
                    set('githubRepository', '');
                    set('githubToken', '');
                    set('githubBranch', 'main');
                    localStorage.removeItem('githubRepository');
                    localStorage.removeItem('githubToken');
                    localStorage.removeItem('githubBranch');
                    setGithubStatus(null);
                  }}
                  style={{
                    background: 'none', border: '1px solid rgba(239,68,68,0.25)',
                    color: 'rgba(239,68,68,0.7)', padding: '7px 14px', borderRadius: 8,
                    cursor: 'pointer', fontSize: 12,
                  }}
                >
                  Desconectar GitHub
                </button>
              )}
            </div>
          )}

          {/* ─── AI ─── */}
          {activeSection === 'ai' && (
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>IA — Ollama</h2>
              <p style={{ fontSize: 13, color: 'rgba(139,147,176,0.6)', marginBottom: 24 }}>
                InsightGraph usa Ollama localmente para análise de código, Weekly Digest e AI Query.
                Baixe em <a href="https://ollama.com" target="_blank" rel="noopener noreferrer" style={{ color: '#4f8ff7' }}>ollama.com</a>.
              </p>

              <div style={cardStyle}>
                <div style={fieldStyle}>
                  <label style={labelStyle}>URL do Ollama</label>
                  <input style={inputStyle} type="text" value={settings.ollamaUrl}
                    onChange={e => set('ollamaUrl', e.target.value)} placeholder="http://localhost:11434" />
                </div>
                <div style={fieldStyle}>
                  <label style={labelStyle}>Modelo Rápido</label>
                  <input style={inputStyle} type="text" value={settings.ollamaFastModel}
                    onChange={e => set('ollamaFastModel', e.target.value)} placeholder="qwen2.5-coder:1.5b" />
                  <p style={{ fontSize: 11.5, color: 'rgba(139,147,176,0.45)', marginTop: 5 }}>
                    Usado para análises inline. Recomendado: <code>qwen2.5-coder:1.5b</code>
                  </p>
                </div>
                <div style={fieldStyle}>
                  <label style={labelStyle}>Modelo Chat</label>
                  <input style={inputStyle} type="text" value={settings.ollamaChatModel}
                    onChange={e => set('ollamaChatModel', e.target.value)} placeholder="qwen3.5:4b" />
                  <p style={{ fontSize: 11.5, color: 'rgba(139,147,176,0.45)', marginTop: 5 }}>
                    Usado para AskPanel, AI Query e explicacoes de impacto. Recomendado: <code>qwen3.5:4b</code>
                  </p>
                </div>
                <div style={{ marginBottom: 0 }}>
                  <label style={labelStyle}>Modelo Complexo</label>
                  <input style={inputStyle} type="text" value={settings.ollamaComplexModel}
                    onChange={e => set('ollamaComplexModel', e.target.value)} placeholder="qwen2.5:7b" />
                  <p style={{ fontSize: 11.5, color: 'rgba(139,147,176,0.45)', marginTop: 5 }}>
                    Usado para Weekly Digest e AI Query. Recomendado: <code>qwen2.5:7b</code>
                  </p>
                </div>
                <div style={fieldStyle}>
                  <label style={labelStyle}>Modelo Embedding</label>
                  <input style={inputStyle} type="text" value={settings.ollamaEmbedModel}
                    onChange={e => set('ollamaEmbedModel', e.target.value)} placeholder="nomic-embed-text" />
                  <p style={{ fontSize: 11.5, color: 'rgba(139,147,176,0.45)', marginTop: 5 }}>
                    Usado para indexacao semantica e contexto RAG. Recomendado: <code>nomic-embed-text</code>
                  </p>
                </div>
                <div style={{ marginBottom: 0 }}>
                  <label style={labelStyle}>Modelo Small (fallback)</label>
                  <input style={inputStyle} type="text" value={settings.ollamaSmallModel}
                    onChange={e => set('ollamaSmallModel', e.target.value)} placeholder="qwen2.5-coder:7b" />
                  <p style={{ fontSize: 11.5, color: 'rgba(139,147,176,0.45)', marginTop: 5 }}>
                    Usado como fallback local quando o modelo principal falha. Recomendado: <code>qwen2.5-coder:7b</code>
                  </p>
                </div>
              </div>

              <div style={{ ...cardStyle, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>Status do Ollama</div>
                  <StatusBadge
                    ok={ollamaStatus}
                    label={ollamaStatus === null ? 'Não verificado' : ollamaStatus ? 'Online e respondendo' : 'Offline — verifique se está rodando'}
                  />
                </div>
                <button
                  onClick={testOllama}
                  disabled={testingOllama}
                  style={{
                    padding: '8px 18px', borderRadius: 8,
                    background: 'rgba(79,143,247,0.1)', border: '1px solid rgba(79,143,247,0.25)',
                    color: '#4f8ff7', cursor: 'pointer', fontSize: 13, fontWeight: 500,
                  }}
                >
                  {testingOllama ? 'Verificando…' : 'Verificar'}
                </button>
              </div>

              <div style={{ ...cardStyle, background: 'rgba(99,102,241,0.05)', borderColor: 'rgba(99,102,241,0.15)' }}>
                <div style={{ fontSize: 12, color: 'rgba(139,147,176,0.6)', lineHeight: 1.7 }}>
                  <div style={{ fontWeight: 600, color: 'rgba(139,147,176,0.8)', marginBottom: 8 }}>Instalar modelos recomendados:</div>
                  <code style={{ display: 'block', background: 'rgba(0,0,0,0.3)', padding: '8px 12px', borderRadius: 6, fontSize: 12 }}>
                    ollama pull qwen2.5-coder:1.5b<br />
                    ollama pull qwen3.5:4b<br />
                    ollama pull qwen3-coder-next:q4_K_M<br />
                    ollama pull qwen2.5-coder:7b<br />
                    ollama pull nomic-embed-text
                  </code>
                </div>
              </div>
            </div>
          )}

          {/* ─── POLLER ─── */}
          {activeSection === 'poller' && (
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>Git Poller</h2>
              <p style={{ fontSize: 13, color: 'rgba(139,147,176,0.6)', marginBottom: 24 }}>
                O poller monitora commits no repositório local e dispara um scan automático a cada novo commit.
              </p>

              {pollerStatus && (
                <div style={{ ...cardStyle, display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>Status atual</span>
                    <StatusBadge ok={pollerStatus.active} label={pollerStatus.active ? 'Monitorando' : 'Inativo'} />
                  </div>
                  {pollerStatus.last_commit && (
                    <div style={{ fontSize: 12, color: 'rgba(139,147,176,0.5)' }}>
                      Último commit visto: <code style={{ color: '#4f8ff7' }}>{pollerStatus.last_commit.slice(0, 8)}</code>
                    </div>
                  )}
                  {pollerStatus.last_scan_at && (
                    <div style={{ fontSize: 12, color: 'rgba(139,147,176,0.5)' }}>
                      Último scan: {new Date(pollerStatus.last_scan_at).toLocaleString('pt-BR')}
                    </div>
                  )}
                </div>
              )}

              <div style={cardStyle}>
                <div style={{ ...fieldStyle, background: 'rgba(99,102,241,0.05)', border: '1px solid rgba(99,102,241,0.12)', borderRadius: 8, padding: '12px 16px' }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'rgba(139,147,176,0.7)', marginBottom: 8 }}>Configurar via variável de ambiente (backend)</div>
                  <code style={{ display: 'block', fontSize: 12, color: '#a5b4fc', lineHeight: 1.8 }}>
                    POLLER_PROJECT_PATH=C:/git/meu-projeto<br />
                    POLLER_INTERVAL_SECONDS=60
                  </code>
                  <p style={{ fontSize: 11.5, color: 'rgba(139,147,176,0.4)', marginTop: 8 }}>
                    Adicione ao arquivo <code>backend/.env</code> e reinicie o backend.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* ─── DATABASE ─── */}
          {activeSection === 'database' && (
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>Database</h2>
              <p style={{ fontSize: 13, color: 'rgba(139,147,176,0.6)', marginBottom: 24 }}>
                InsightGraph usa SQLite por padrão (sem configuração). Neo4j é opcional para grafos maiores.
              </p>

              <div style={cardStyle}>
                <div style={{ fontSize: 12, color: '#22c55e', background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.15)', borderRadius: 8, padding: '10px 14px', marginBottom: 20 }}>
                  ✓ SQLite ativo — nenhuma configuração necessária
                </div>

                <div style={{ fontSize: 13, fontWeight: 500, color: 'rgba(139,147,176,0.5)', marginBottom: 16 }}>Neo4j (opcional)</div>

                <div style={fieldStyle}>
                  <label style={labelStyle}>URI</label>
                  <input style={inputStyle} type="text" value={settings.neo4jUri}
                    onChange={e => set('neo4jUri', e.target.value)} placeholder="bolt://localhost:7687" />
                </div>
                <div style={{ marginBottom: 0 }}>
                  <label style={labelStyle}>Usuário</label>
                  <input style={inputStyle} type="text" value={settings.neo4jUser}
                    onChange={e => set('neo4jUser', e.target.value)} placeholder="neo4j" />
                </div>
              </div>
            </div>
          )}

          {/* ─── PERFORMANCE ─── */}
          {activeSection === 'performance' && (
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>Performance</h2>
              <p style={{ fontSize: 13, color: 'rgba(139,147,176,0.6)', marginBottom: 24 }}>
                Ajuste os intervalos de scan, cache e limites para seu hardware.
              </p>

              <div style={cardStyle}>
                {[
                  { field: 'scanInterval' as const, label: 'Intervalo de Scan (seg)', min: 60, max: 3600, hint: 'Com que frequência o sistema verifica mudanças' },
                  { field: 'auditInterval' as const, label: 'Intervalo de Audit (seg)', min: 300, max: 7200, hint: 'Com que frequência o audit de alertas roda' },
                  { field: 'cacheTtl' as const, label: 'TTL do Cache (seg)', min: 10, max: 3600, hint: 'Tempo de vida do cache de consultas' },
                  { field: 'maxCommits' as const, label: 'Máx. Commits na Timeline', min: 10, max: 1000, hint: 'Limita o histórico na Timeline 4D' },
                  { field: 'maxReconnectAttempts' as const, label: 'Tentativas de Reconexão SSE', min: 1, max: 20, hint: 'Tentativas antes de desistir do SSE' },
                ].map(({ field, label, min, max, hint }) => (
                  <div key={field} style={fieldStyle}>
                    <label style={labelStyle}>{label}</label>
                    <input style={{ ...inputStyle, maxWidth: 160 }} type="number"
                      value={(settings[field] as number)} min={min} max={max}
                      onChange={e => set(field, parseInt(e.target.value))} />
                    <p style={{ fontSize: 11.5, color: 'rgba(139,147,176,0.4)', marginTop: 4 }}>{hint}</p>
                  </div>
                ))}
              </div>
              </div>
          )}

          {/* ─── INTERFACE ─── */}
          {activeSection === 'interface' && (
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>Interface</h2>
              <p style={{ fontSize: 13, color: 'rgba(139,147,176,0.6)', marginBottom: 24 }}>
                Preferências visuais e de idioma.
              </p>

              <div style={cardStyle}>
                <div style={fieldStyle}>
                  <label style={labelStyle}>Tema</label>
                  <select style={{ ...inputStyle, maxWidth: 200 }} value={settings.theme}
                    onChange={e => set('theme', e.target.value)}>
                    <option value="dark">Escuro</option>
                    <option value="light">Claro</option>
                    <option value="auto">Automático</option>
                  </select>
                </div>
                <div style={fieldStyle}>
                  <label style={labelStyle}>Idioma</label>
                  <select style={{ ...inputStyle, maxWidth: 200 }} value={settings.language}
                    onChange={e => set('language', e.target.value)}>
                    <option value="pt-BR">Português (Brasil)</option>
                    <option value="en-US">English (US)</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, color: 'var(--text-primary)' }}>
                    <input type="checkbox" checked={settings.sseEnabled}
                      onChange={e => set('sseEnabled', e.target.checked)}
                      style={{ accentColor: '#4f8ff7' }} />
                    Habilitar Server-Sent Events (tempo real)
                  </label>
                  <p style={{ fontSize: 11.5, color: 'rgba(139,147,176,0.4)', marginTop: 5, marginLeft: 20 }}>
                    Desative se tiver problemas de conectividade com o backend
                  </p>
                </div>
              </div>
            </div>
          )}

        </div>
              </div>
    </div>
  );
};

export default SettingsScreen;




