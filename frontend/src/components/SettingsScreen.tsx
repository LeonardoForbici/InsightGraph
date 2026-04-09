import React, { useState, useEffect, useCallback } from 'react';

interface SettingsData {
  neo4jUri: string;
  neo4jUser: string;
  ollamaUrl: string;
  ollamaFastModel: string;
  ollamaComplexModel: string;
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
  enableAnalytics: boolean;
  theme: 'dark' | 'light' | 'auto';
  language: string;
}

const DEFAULT_SETTINGS: SettingsData = {
  neo4jUri: 'bolt://localhost:7687',
  neo4jUser: 'neo4j',
  ollamaUrl: 'http://localhost:11434',
  ollamaFastModel: 'qwen2.5-coder:1.5b',
  ollamaComplexModel: 'qwen3-coder-next:q4_K_M',
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
  enableAnalytics: false,
  theme: 'dark',
  language: 'pt-BR',
};

const SettingsScreen: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const [settings, setSettings] = useState<SettingsData>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Load settings on mount
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const response = await fetch('/api/config/settings');
        if (response.ok) {
          const data = await response.json();
          setSettings(data);
          // Also load GitHub config from localStorage
          const storedGithubRepo = localStorage.getItem('githubRepository');
          const storedGithubBranch = localStorage.getItem('githubBranch');
          const storedGithubToken = localStorage.getItem('githubToken');
          const storedGithubShallowClone = localStorage.getItem('githubShallowClone');
          if (storedGithubRepo) setSettings(prev => ({ ...prev, githubRepository: storedGithubRepo }));
          if (storedGithubBranch) setSettings(prev => ({ ...prev, githubBranch: storedGithubBranch }));
          if (storedGithubToken) setSettings(prev => ({ ...prev, githubToken: storedGithubToken }));
          if (storedGithubShallowClone !== null) setSettings(prev => ({ ...prev, githubShallowClone: storedGithubShallowClone === 'true' }));
        }
      } catch (err) {
        console.error('Failed to load settings:', err);
        // Use defaults if API fails
        setSettings(DEFAULT_SETTINGS);
      } finally {
        setLoading(false);
      }
    };
    loadSettings();
  }, []);

  const handleChange = useCallback((field: keyof SettingsData, value: any) => {
    setSettings(prev => ({ ...prev, [field]: value }));
    setError(null);
  }, []);

  const handleSave = useCallback(async () => {
    try {
      setSaving(true);
      setError(null);
      
      // Save GitHub config to localStorage
      localStorage.setItem('githubRepository', settings.githubRepository);
      localStorage.setItem('githubBranch', settings.githubBranch);
      localStorage.setItem('githubToken', settings.githubToken);
      localStorage.setItem('githubShallowClone', settings.githubShallowClone.toString());
      
      // Convert camelCase to snake_case for backend
      const payload = {
        neo4j_uri: settings.neo4jUri,
        neo4j_user: settings.neo4jUser,
        ollama_url: settings.ollamaUrl,
        ollama_fast_model: settings.ollamaFastModel,
        ollama_complex_model: settings.ollamaComplexModel,
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
      };
      
      const response = await fetch('/api/config/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      
      if (!response.ok) {
        throw new Error('Failed to save settings');
      }
      
      setSuccess(true);
      setTimeout(() => {
        setSuccess(false);
        onClose();
      }, 2000);
    } catch (err) {
      console.error('Failed to save settings:', err);
      setError(err instanceof Error ? err.message : 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  }, [settings, onClose]);

  const handleReset = useCallback(() => {
    setSettings({
      neo4jUri: DEFAULT_SETTINGS.neo4jUri,
      neo4jUser: DEFAULT_SETTINGS.neo4jUser,
      ollamaUrl: DEFAULT_SETTINGS.ollamaUrl,
      ollamaFastModel: DEFAULT_SETTINGS.ollamaFastModel,
      ollamaComplexModel: DEFAULT_SETTINGS.ollamaComplexModel,
      sseEnabled: DEFAULT_SETTINGS.sseEnabled,
      maxReconnectAttempts: DEFAULT_SETTINGS.maxReconnectAttempts,
      initialRetryDelay: DEFAULT_SETTINGS.initialRetryDelay,
      cacheTtl: DEFAULT_SETTINGS.cacheTtl,
      scanInterval: DEFAULT_SETTINGS.scanInterval,
      auditInterval: DEFAULT_SETTINGS.auditInterval,
      maxCommits: DEFAULT_SETTINGS.maxCommits,
      githubRepository: DEFAULT_SETTINGS.githubRepository,
      githubBranch: DEFAULT_SETTINGS.githubBranch,
      githubToken: DEFAULT_SETTINGS.githubToken,
      githubShallowClone: DEFAULT_SETTINGS.githubShallowClone,
      enableAnalytics: DEFAULT_SETTINGS.enableAnalytics,
      theme: DEFAULT_SETTINGS.theme,
      language: DEFAULT_SETTINGS.language,
    });
    setError(null);
  }, []);

  if (loading) {
    return (
      <div className="settings-screen">
        <div className="settings-loading">
          <div className="spinner" />
          <p>Carregando configurações...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="settings-screen">
      <div className="settings-header">
        <h3>⚙️ Configurações do Sistema</h3>
        <button className="close-btn" onClick={onClose}>✕</button>
      </div>

      <div className="settings-content">
        {error && (
          <div className="settings-error">
            <p>{error}</p>
          </div>
        )}

        {success && (
          <div className="settings-success">
            <p>Configurações salvas com sucesso!</p>
          </div>
        )}

        <div className="settings-section">
          <h4>Database (Neo4j)</h4>
          <div className="settings-form-group">
            <label>URI</label>
            <input
              type="text"
              value={settings.neo4jUri}
              onChange={(e) => handleChange('neo4jUri', e.target.value)}
              placeholder="bolt://localhost:7687"
            />
          </div>
          <div className="settings-form-group">
            <label>Usuário</label>
            <input
              type="text"
              value={settings.neo4jUser}
              onChange={(e) => handleChange('neo4jUser', e.target.value)}
              placeholder="neo4j"
            />
          </div>
        </div>

        <div className="settings-section">
          <h4>AI (Ollama)</h4>
          <div className="settings-form-group">
            <label>URL</label>
            <input
              type="text"
              value={settings.ollamaUrl}
              onChange={(e) => handleChange('ollamaUrl', e.target.value)}
              placeholder="http://localhost:11434"
            />
          </div>
          <div className="settings-form-group">
            <label>Modelo Rápido</label>
            <input
              type="text"
              value={settings.ollamaFastModel}
              onChange={(e) => handleChange('ollamaFastModel', e.target.value)}
              placeholder="qwen2.5-coder:1.5b"
            />
          </div>
          <div className="settings-form-group">
            <label>Modelo Complexo</label>
            <input
              type="text"
              value={settings.ollamaComplexModel}
              onChange={(e) => handleChange('ollamaComplexModel', e.target.value)}
              placeholder="qwen3-coder-next:q4_K_M"
            />
          </div>
        </div>

        <div className="settings-section">
          <h4>Real-time (SSE)</h4>
          <div className="settings-form-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={settings.sseEnabled}
                onChange={(e) => handleChange('sseEnabled', e.target.checked)}
              />
              <span>Habilitar SSE (Server-Sent Events)</span>
            </label>
          </div>
          <div className="settings-form-group">
            <label>Tentativas de Reconexão</label>
            <input
              type="number"
              value={settings.maxReconnectAttempts}
              onChange={(e) => handleChange('maxReconnectAttempts', parseInt(e.target.value))}
              min="1"
              max="20"
            />
          </div>
          <div className="settings-form-group">
            <label>Delay Inicial (ms)</label>
            <input
              type="number"
              value={settings.initialRetryDelay}
              onChange={(e) => handleChange('initialRetryDelay', parseInt(e.target.value))}
              min="100"
              max="10000"
            />
          </div>
        </div>

        <div className="settings-section">
          <h4>Performance</h4>
          <div className="settings-form-group">
            <label>TTL do Cache (segundos)</label>
            <input
              type="number"
              value={settings.cacheTtl}
              onChange={(e) => handleChange('cacheTtl', parseInt(e.target.value))}
              min="10"
              max="3600"
            />
          </div>
          <div className="settings-form-group">
            <label>Intervalo de Scan (segundos)</label>
            <input
              type="number"
              value={settings.scanInterval}
              onChange={(e) => handleChange('scanInterval', parseInt(e.target.value))}
              min="60"
              max="3600"
            />
          </div>
          <div className="settings-form-group">
            <label>Intervalo de Audit (segundos)</label>
            <input
              type="number"
              value={settings.auditInterval}
              onChange={(e) => handleChange('auditInterval', parseInt(e.target.value))}
              min="300"
              max="7200"
            />
          </div>
        </div>

        <div className="settings-section">
          <h4>Timeline 4D</h4>
          <div className="settings-form-group">
            <label>Máximo de Commits</label>
            <input
              type="number"
              value={settings.maxCommits}
              onChange={(e) => handleChange('maxCommits', parseInt(e.target.value))}
              min="10"
              max="1000"
            />
          </div>
        </div>

        <div className="settings-section">
          <h4>GitHub Repository</h4>
          <div className="settings-form-group">
            <label>Repository URL</label>
            <input
              type="text"
              value={settings.githubRepository || ''}
              onChange={(e) => handleChange('githubRepository', e.target.value)}
              placeholder="https://github.com/usuario/repo"
            />
            <p className="settings-hint">URL do repositório GitHub para análise temporal</p>
          </div>
          <div className="settings-form-group">
            <label>Branch</label>
            <input
              type="text"
              value={settings.githubBranch || 'main'}
              onChange={(e) => handleChange('githubBranch', e.target.value)}
              placeholder="main"
            />
            <p className="settings-hint">Branch a ser analisado (padrão: main)</p>
          </div>
          <div className="settings-form-group">
            <label>Personal Access Token (Opcional)</label>
            <input
              type="password"
              value={settings.githubToken || ''}
              onChange={(e) => handleChange('githubToken', e.target.value)}
              placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
              autoComplete="off"
            />
            <p className="settings-hint">
              Necessário para repositórios privados. 
              <a 
                href="https://github.com/settings/tokens/new?scopes=repo&description=InsightGraph%20Timeline%204D" 
                target="_blank" 
                rel="noopener noreferrer"
                style={{ marginLeft: '5px', color: '#4a9eff', textDecoration: 'underline' }}
              >
                Gerar token →
              </a>
            </p>
          </div>
          <div className="settings-form-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={settings.githubShallowClone !== false}
                onChange={(e) => handleChange('githubShallowClone', e.target.checked)}
              />
              <span>Usar shallow clone (mais rápido)</span>
            </label>
            <p className="settings-hint">Clona apenas o histórico recente para melhor performance</p>
          </div>
          <div className="settings-form-group">
            <button 
              className="btn btn-danger"
              onClick={() => {
                handleChange('githubRepository', '');
                handleChange('githubBranch', 'main');
                handleChange('githubToken', '');
                handleChange('githubShallowClone', true);
                localStorage.removeItem('githubRepository');
                localStorage.removeItem('githubBranch');
                localStorage.removeItem('githubToken');
                localStorage.removeItem('githubShallowClone');
              }}
              disabled={!settings.githubRepository}
            >
              🔓 Desconectar GitHub
            </button>
            <p className="settings-hint">
              {settings.githubRepository 
                ? 'Remove todas as credenciais e configurações do GitHub' 
                : 'Configure um repositório para habilitar esta opção'}
            </p>
          </div>
        </div>

        <div className="settings-section">
          <h4>Analytics & Privacy</h4>
          <div className="settings-form-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={settings.enableAnalytics}
                onChange={(e) => handleChange('enableAnalytics', e.target.checked)}
              />
              <span>Habilitar analytics anônimo</span>
            </label>
          </div>
        </div>

        <div className="settings-section">
          <h4>Interface</h4>
          <div className="settings-form-group">
            <label>Tema</label>
            <select
              value={settings.theme}
              onChange={(e) => handleChange('theme', e.target.value)}
            >
              <option value="dark">Escuro</option>
              <option value="light">Claro</option>
              <option value="auto">Automático</option>
            </select>
          </div>
          <div className="settings-form-group">
            <label>Idioma</label>
            <select
              value={settings.language}
              onChange={(e) => handleChange('language', e.target.value)}
            >
              <option value="pt-BR">Português (Brasil)</option>
              <option value="en-US">English (US)</option>
            </select>
          </div>
        </div>

        <div className="settings-actions">
          <button className="btn btn-secondary" onClick={handleReset}>
            Resetar Padrão
          </button>
          <button
            className={`btn btn-primary ${saving ? 'saving' : ''}`}
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Salvando...' : 'Salvar Configurações'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SettingsScreen;
