import { useState } from 'react';
import type { SavedView } from '../api';

interface SavedViewsPanelProps {
    isOpen: boolean;
    onClose: () => void;
    views: SavedView[];
    loading: boolean;
    saving: boolean;
    error?: string | null;
    onRefresh: () => void;
    onSave: (name: string, description?: string) => Promise<void>;
    onLoad: (view: SavedView) => void;
}

export default function SavedViewsPanel({
    isOpen,
    onClose,
    views,
    loading,
    saving,
    error,
    onRefresh,
    onSave,
    onLoad,
}: SavedViewsPanelProps) {
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [localError, setLocalError] = useState<string | null>(null);

    if (!isOpen) return null;

    const handleSave = async () => {
        const trimmed = name.trim();
        if (!trimmed) {
            setLocalError('Nome da view é obrigatório');
            return;
        }
        setLocalError(null);
        try {
            await onSave(trimmed, description.trim() || undefined);
            setName('');
            setDescription('');
        } catch (saveError: any) {
            setLocalError(saveError?.message || 'Falha ao salvar a view.');
        }
    };

    return (
        <div className="modal-overlay" style={{ zIndex: 2200 }}>
            <div className="ask-panel" style={{ width: 'min(900px, 90vw)', height: 'min(80vh, 700px)', display: 'flex', flexDirection: 'column' }}>
                <div className="ask-header">
                    <h3>Saved Views</h3>
                    <span className="close-btn" onClick={onClose}>×</span>
                </div>
                <div style={{ padding: 16, display: 'flex', gap: 16, flex: 1, overflow: 'hidden' }}>
                    <section style={{ flex: 1, border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 12, overflowY: 'auto' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                            <div style={{ fontSize: 12, fontWeight: 700 }}>Create new view</div>
                            <button className="btn btn-secondary" onClick={handleSave} disabled={saving}>
                                {saving ? 'Saving...' : 'Save current graph'}
                            </button>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            <input
                                className="search-input"
                                placeholder="View name"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                disabled={saving}
                            />
                            <textarea
                                className="search-input"
                                placeholder="Description (optional)"
                                value={description}
                                onChange={(e) => setDescription(e.target.value)}
                                rows={3}
                                disabled={saving}
                            />
                            {(error || localError) && (
                                <div style={{ color: '#ef4444', fontSize: 12 }}>
                                    {error || localError}
                                </div>
                            )}
                        </div>
                    </section>
                    <section style={{ flex: 1, border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 12, display: 'flex', flexDirection: 'column' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                            <div style={{ fontSize: 12, fontWeight: 700 }}>Available saved views</div>
                            <button className="btn btn-secondary" onClick={onRefresh} disabled={loading}>
                                Refresh
                            </button>
                        </div>
                        {loading ? (
                            <div style={{ fontSize: 12, opacity: 0.7 }}>Carregando...</div>
                        ) : views.length === 0 ? (
                            <div style={{ fontSize: 12, opacity: 0.7 }}>Nenhuma view salva ainda.</div>
                        ) : (
                            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
                                {views.map((view) => (
                                    <div key={view.id} style={{ border: '1px solid rgba(148,163,184,0.3)', borderRadius: 8, padding: 10 }}>
                                        <div style={{ fontSize: 13, fontWeight: 600 }}>{view.name}</div>
                                        {view.description && (
                                            <div style={{ fontSize: 11, marginBottom: 6 }}>{view.description}</div>
                                        )}
                                        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>
                                            Atualizado em {view.updated_at ? new Date(view.updated_at * 1000).toLocaleString() : 'desconhecido'}
                                        </div>
                                        <button className="btn btn-secondary" onClick={() => onLoad(view)}>
                                            Load view
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </section>
                </div>
            </div>
        </div>
    );
}
