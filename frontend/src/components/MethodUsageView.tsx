import { useEffect, useState } from 'react';
import { fetchMethodUsages, type MethodUsageResponse } from '../api';

interface MethodUsageViewProps {
    nodeKey: string;
    nodeName: string;
    onClose: () => void;
    onNavigateTo: (nodeKey: string) => void;
}

export default function MethodUsageView({ nodeKey, nodeName, onClose, onNavigateTo }: MethodUsageViewProps) {
    const [data, setData] = useState<MethodUsageResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        let active = true;
        const load = async () => {
            setLoading(true);
            setError('');
            try {
                const res = await fetchMethodUsages(nodeKey);
                if (active) setData(res);
            } catch (err: any) {
                if (active) setError(err?.message || 'Falha ao carregar usos do método');
            } finally {
                if (active) setLoading(false);
            }
        };
        load();
        return () => { active = false; };
    }, [nodeKey]);

    return (
        <div style={{
            position: 'fixed',
            top: 60,
            right: 0,
            bottom: 0,
            width: 460,
            background: 'rgba(15, 23, 42, 0.98)',
            borderLeft: '1px solid rgba(148,163,184,0.2)',
            zIndex: 50,
            display: 'flex',
            flexDirection: 'column',
        }}>
            <div style={{ padding: '14px 16px', borderBottom: '1px solid rgba(148,163,184,0.2)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <div style={{ fontSize: 14, fontWeight: 700 }}>Usos do método</div>
                        <div style={{ fontSize: 11, opacity: 0.75 }}>{nodeName}</div>
                    </div>
                    <button className="btn btn-secondary" onClick={onClose}>Fechar</button>
                </div>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
                {loading && <div style={{ opacity: 0.8 }}>Carregando...</div>}
                {error && <div style={{ color: '#ef4444' }}>{error}</div>}
                {!loading && !error && data && (
                    <>
                        <div style={{ marginBottom: 12, fontSize: 12, opacity: 0.8 }}>
                            {data.total_callers} callers · {data.total_callees} callees
                        </div>

                        <h4 style={{ margin: '0 0 8px 0', fontSize: 12 }}>Callers</h4>
                        {data.callers.length === 0 && <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 10 }}>Nenhum caller encontrado.</div>}
                        {data.callers.map((u) => (
                            <button
                                key={`c-${u.key}-${u.type}`}
                                onClick={() => onNavigateTo(u.key)}
                                style={{
                                    display: 'block',
                                    width: '100%',
                                    textAlign: 'left',
                                    marginBottom: 6,
                                    padding: '8px 10px',
                                    background: 'rgba(59,130,246,0.08)',
                                    border: '1px solid rgba(59,130,246,0.2)',
                                    borderRadius: 8,
                                    color: '#e2e8f0',
                                    cursor: 'pointer',
                                }}
                            >
                                <div style={{ fontSize: 12, fontWeight: 600 }}>{u.name}</div>
                                <div style={{ fontSize: 10, opacity: 0.75 }}>{u.file || u.key}</div>
                            </button>
                        ))}

                        <h4 style={{ margin: '14px 0 8px 0', fontSize: 12 }}>Callees</h4>
                        {data.callees.length === 0 && <div style={{ fontSize: 12, opacity: 0.7 }}>Nenhum callee encontrado.</div>}
                        {data.callees.map((u) => (
                            <button
                                key={`d-${u.key}-${u.type}`}
                                onClick={() => onNavigateTo(u.key)}
                                style={{
                                    display: 'block',
                                    width: '100%',
                                    textAlign: 'left',
                                    marginBottom: 6,
                                    padding: '8px 10px',
                                    background: 'rgba(34,197,94,0.08)',
                                    border: '1px solid rgba(34,197,94,0.2)',
                                    borderRadius: 8,
                                    color: '#e2e8f0',
                                    cursor: 'pointer',
                                }}
                            >
                                <div style={{ fontSize: 12, fontWeight: 600 }}>{u.name}</div>
                                <div style={{ fontSize: 10, opacity: 0.75 }}>{u.file || u.key}</div>
                            </button>
                        ))}
                    </>
                )}
            </div>
        </div>
    );
}

