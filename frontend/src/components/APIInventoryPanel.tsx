import { useEffect, useMemo, useState } from 'react';
import { fetchApiInventory, type ApiInventoryResponseItem } from '../api';

interface APIInventoryPanelProps {
  onClose: () => void;
}

type InventoryRow = ApiInventoryResponseItem & { key: string };

export default function APIInventoryPanel({ onClose }: APIInventoryPanelProps) {
  const [items, setItems] = useState<InventoryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchApiInventory();
      setItems(
        (data.items || []).map((item) => ({
          key: String(item.namespace_key || `${item.name}-${item.route_path}`),
          ...item,
        }))
      );
    } catch (err) {
      console.error('Failed to load API inventory:', err);
      setError('Falha ao carregar o inventário de endpoints.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const term = search.trim().toLowerCase();
    return items.filter((item) =>
      `${item.name || ''} ${item.route_path || ''} ${item.project || ''}`.toLowerCase().includes(term)
    );
  }, [items, search]);

  return (
    <div className="dashboard-overlay">
      <div className="dashboard-panel" style={{ maxWidth: 960 }}>
        <div className="dashboard-header">
          <div>
            <h2>Inventário de APIs</h2>
            <p className="section-desc">Endpoints descobertos no grafo atual.</p>
          </div>
          <button className="btn btn-secondary" onClick={onClose}>✕ Fechar</button>
        </div>

        <div className="dashboard-section" style={{ padding: '0 24px 24px' }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
            <input
              className="topbar-input"
              placeholder="Buscar por nome, rota ou projeto"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              style={{ flex: 1 }}
            />
            <button className="btn btn-secondary" onClick={load} disabled={loading}>
              {loading ? 'Atualizando...' : 'Atualizar'}
            </button>
          </div>
          {error && <div style={{ color: '#fb7185', marginBottom: 12 }}>{error}</div>}
          <div style={{ maxHeight: '60vh', overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Nome</th>
                  <th>Projeto</th>
                  <th>HTTP</th>
                  <th>Rota</th>
                  <th>Arquivo</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => (
                  <tr key={item.key}>
                    <td>{item.name}</td>
                    <td>{item.project || '—'}</td>
                    <td>{item.http_method || '—'}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{item.route_path || '—'}</td>
                    <td style={{ fontSize: '11px' }}>{item.file || '—'}</td>
                  </tr>
                ))}
                {!filtered.length && !loading && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                      Nenhum endpoint encontrado com este filtro.
                    </td>
                  </tr>
                )}
                {loading && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                      Carregando inventário...
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
