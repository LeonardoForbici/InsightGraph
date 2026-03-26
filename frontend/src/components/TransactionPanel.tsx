import { useEffect, useMemo, useState } from 'react';
import {
    fetchGraphPath,
    fetchTransactionExplain,
    fetchTransactionView,
    type GraphNode,
    type PathFinderData,
    type TransactionViewData,
} from '../api';

interface TransactionPanelProps {
    isOpen: boolean;
    initialSourceKey?: string | null;
    graphNodes: GraphNode[];
    onClose: () => void;
}

export default function TransactionPanel({ isOpen, initialSourceKey, graphNodes, onClose }: TransactionPanelProps) {
    const [sourceKey, setSourceKey] = useState('');
    const [targetKey, setTargetKey] = useState('');
    const [maxDepth, setMaxDepth] = useState(10);
    const [txLoading, setTxLoading] = useState(false);
    const [pathLoading, setPathLoading] = useState(false);
    const [txError, setTxError] = useState<string | null>(null);
    const [pathError, setPathError] = useState<string | null>(null);
    const [transaction, setTransaction] = useState<TransactionViewData | null>(null);
    const [pathData, setPathData] = useState<PathFinderData | null>(null);
    const [summary, setSummary] = useState<string | null>(null);
    const [summaryModel, setSummaryModel] = useState<string | null>(null);
    const [summaryLoading, setSummaryLoading] = useState(false);
    const [summaryError, setSummaryError] = useState<string | null>(null);

    const nodeByKey = useMemo(() => {
        const map = new Map<string, GraphNode>();
        for (const node of graphNodes) {
            map.set(node.namespace_key, node);
        }
        return map;
    }, [graphNodes]);

    useEffect(() => {
        if (!isOpen) return;
        setSourceKey(initialSourceKey || '');
        setTargetKey('');
        setTransaction(null);
        setPathData(null);
        setTxError(null);
        setPathError(null);
    }, [isOpen, initialSourceKey]);

    useEffect(() => {
        setSummary(null);
        setSummaryModel(null);
        setSummaryError(null);
    }, [transaction?.origin?.namespace_key, maxDepth]);

    if (!isOpen) return null;

    const runTransaction = async () => {
        if (!sourceKey.trim()) {
            setTxError('Informe um source node key.');
            return;
        }
        setTxError(null);
        setTxLoading(true);
        try {
            const data = await fetchTransactionView(sourceKey.trim(), maxDepth);
            setTransaction(data);
        } catch (error: any) {
            setTransaction(null);
            setTxError(error?.message || 'Falha ao montar transaction view.');
        } finally {
            setTxLoading(false);
        }
    };

    const runPathFinder = async () => {
        if (!sourceKey.trim() || !targetKey.trim()) {
            setPathError('Informe source e target node key.');
            return;
        }
        setPathError(null);
        setPathLoading(true);
        try {
            const data = await fetchGraphPath(sourceKey.trim(), targetKey.trim(), maxDepth);
            setPathData(data);
        } catch (error: any) {
            setPathData(null);
            setPathError(error?.message || 'Falha ao buscar caminho.');
        } finally {
            setPathLoading(false);
        }
    };

    const runAiSummary = async () => {
        if (!transaction) return;
        setSummaryLoading(true);
        setSummaryError(null);
        try {
            const data = await fetchTransactionExplain(transaction.origin.namespace_key, maxDepth);
            setSummary(data.explanation);
            setSummaryModel(data.model || null);
        } catch (error: any) {
            setSummary(null);
            setSummaryModel(null);
            setSummaryError(error?.message || 'Falha ao gerar explicação da transação.');
        } finally {
            setSummaryLoading(false);
        }
    };

    const keyOptions = graphNodes.slice(0, 3000);

    return (
        <div className="modal-overlay" style={{ zIndex: 1500 }}>
            <div
                className="ask-panel"
                style={{
                    width: 'min(1100px, 94vw)',
                    height: 'min(86vh, 900px)',
                    display: 'flex',
                    flexDirection: 'column',
                }}
            >
                <div className="ask-header">
                    <h3>Transaction View and Path Finder</h3>
                    <span className="close-btn" onClick={onClose}>x</span>
                </div>

                <div style={{ padding: 16, borderBottom: '1px solid var(--border-subtle)', display: 'grid', gridTemplateColumns: '1fr 1fr auto auto', gap: 10 }}>
                    <div>
                        <div style={{ fontSize: 11, marginBottom: 6, opacity: 0.8 }}>Source node key</div>
                        <input
                            list="node-key-options"
                            value={sourceKey}
                            onChange={(e) => setSourceKey(e.target.value)}
                            placeholder="project:file:Class.method"
                            style={{ width: '100%' }}
                            className="search-input"
                        />
                    </div>
                    <div>
                        <div style={{ fontSize: 11, marginBottom: 6, opacity: 0.8 }}>Target node key (Path Finder)</div>
                        <input
                            list="node-key-options"
                            value={targetKey}
                            onChange={(e) => setTargetKey(e.target.value)}
                            placeholder="project:file:TargetClass.method"
                            style={{ width: '100%' }}
                            className="search-input"
                        />
                    </div>
                    <div>
                        <div style={{ fontSize: 11, marginBottom: 6, opacity: 0.8 }}>Max depth</div>
                        <input
                            type="number"
                            min={1}
                            max={30}
                            value={maxDepth}
                            onChange={(e) => setMaxDepth(Math.max(1, Number(e.target.value) || 1))}
                            className="search-input"
                            style={{ width: 90 }}
                        />
                    </div>
                    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
                        <button className="btn btn-primary" onClick={runTransaction} disabled={txLoading}>
                            {txLoading ? 'Loading...' : 'Run Transaction'}
                        </button>
                        <button className="btn btn-secondary" onClick={runPathFinder} disabled={pathLoading}>
                            {pathLoading ? 'Loading...' : 'Find Path'}
                        </button>
                    </div>
                    <datalist id="node-key-options">
                        {keyOptions.map((n) => (
                            <option key={n.namespace_key} value={n.namespace_key}>
                                {n.name}
                            </option>
                        ))}
                    </datalist>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 14, padding: 16, overflow: 'auto' }}>
                    <section style={{ border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 12 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>Transaction View</div>
                        {txError && <div style={{ color: '#ef4444', fontSize: 12, marginBottom: 8 }}>{txError}</div>}
                        {!transaction && !txError && (
                            <div style={{ fontSize: 12, opacity: 0.75 }}>Execute "Run Transaction" para ver as swimlanes.</div>
                        )}
                        {transaction && (
                            <>
                                <div style={{ fontSize: 11, opacity: 0.8, marginBottom: 10 }}>
                                    Origin: <b>{transaction.origin.name}</b> ({transaction.origin.layer}) | visited: {transaction.nodes_visited}
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.max(transaction.lanes.length, 1)}, minmax(180px, 1fr))`, gap: 10 }}>
                                    {transaction.lanes.map((lane) => (
                                        <div key={lane.layer} style={{ background: 'rgba(15,23,42,0.35)', border: '1px solid rgba(148,163,184,0.2)', borderRadius: 8, padding: 8 }}>
                                            <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 6 }}>{lane.layer} ({lane.nodes.length})</div>
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 320, overflowY: 'auto' }}>
                                                {lane.nodes.map((n) => (
                                                    <button
                                                        key={n.namespace_key}
                                                        onClick={() => setTargetKey(n.namespace_key)}
                                                        title={n.namespace_key}
                                                        style={{
                                                            textAlign: 'left',
                                                            fontSize: 11,
                                                            borderRadius: 6,
                                                            border: '1px solid rgba(148,163,184,0.22)',
                                                            background: 'rgba(30,41,59,0.7)',
                                                            color: 'var(--text-primary)',
                                                            padding: '6px 8px',
                                                            cursor: 'pointer',
                                                        }}
                                                    >
                                                        <div>{n.name || n.namespace_key}</div>
                                                        <div style={{ opacity: 0.65, fontSize: 10 }}>d={n.depth} {n.via_rel ? `via ${n.via_rel}` : ''}</div>
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                                {transaction.terminal_paths.length > 0 && (
                                    <div style={{ marginTop: 10, borderTop: '1px solid var(--border-subtle)', paddingTop: 10 }}>
                                        <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 6 }}>Terminal paths</div>
                                        <div style={{ maxHeight: 130, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 5 }}>
                                            {transaction.terminal_paths.slice(0, 30).map((p) => (
                                                <button
                                                    key={p.target_key}
                                                    onClick={() => setTargetKey(p.target_key)}
                                                    style={{
                                                        textAlign: 'left',
                                                        fontSize: 11,
                                                        border: '1px solid rgba(148,163,184,0.18)',
                                                        background: 'transparent',
                                                        color: 'var(--text-secondary)',
                                                        padding: '5px 6px',
                                                        borderRadius: 6,
                                                        cursor: 'pointer',
                                                    }}
                                                >
                                                    [{p.target_layer}] {p.target_name} (depth {p.depth})
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                <div style={{ marginTop: 12, borderTop: '1px solid var(--border-subtle)', paddingTop: 12 }}>
                                    <button
                                        className="btn btn-primary"
                                        style={{ fontSize: 11, padding: '6px 12px', display: 'inline-flex', alignItems: 'center', gap: 6 }}
                                        onClick={runAiSummary}
                                        disabled={summaryLoading}
                                    >
                                        {summaryLoading ? 'Explicando...' : 'Explicar esta transação'}
                                    </button>
                                    {summaryModel && (
                                        <div style={{ fontSize: 10, opacity: 0.8, marginTop: 6 }}>Modelo usado: {summaryModel}</div>
                                    )}
                                    {summaryError && (
                                        <div style={{ color: '#ef4444', fontSize: 11, marginTop: 6 }}>{summaryError}</div>
                                    )}
                                    {summary && (
                                        <div
                                            style={{
                                                marginTop: 10,
                                                fontSize: 12,
                                                lineHeight: 1.5,
                                                whiteSpace: 'pre-wrap',
                                                color: 'var(--text-secondary)',
                                            }}
                                        >
                                            {summary}
                                        </div>
                                    )}
                                </div>
                            </>
                        )}
                    </section>

                    <section style={{ border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 12 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>Path Finder</div>
                        {pathError && <div style={{ color: '#ef4444', fontSize: 12, marginBottom: 8 }}>{pathError}</div>}
                        {!pathData && !pathError && (
                            <div style={{ fontSize: 12, opacity: 0.75 }}>Defina target e execute "Find Path".</div>
                        )}
                        {pathData && !pathData.found && (
                            <div style={{ fontSize: 12, color: '#f59e0b' }}>Nenhum caminho encontrado dentro do max depth.</div>
                        )}
                        {pathData && pathData.found && (
                            <>
                                <div style={{ fontSize: 11, marginBottom: 10, opacity: 0.8 }}>Hops: {pathData.hops}</div>
                                <ol style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 6 }}>
                                    {pathData.path.map((key, index) => {
                                        const node = nodeByKey.get(key);
                                        return (
                                            <li key={`${key}-${index}`} style={{ fontSize: 12 }}>
                                                <span>{node?.name || key}</span>
                                                <span style={{ opacity: 0.65, marginLeft: 6, fontSize: 10 }}>{key}</span>
                                            </li>
                                        );
                                    })}
                                </ol>
                                <div style={{ marginTop: 10, borderTop: '1px solid var(--border-subtle)', paddingTop: 8 }}>
                                    <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 4 }}>Edge chain</div>
                                    {pathData.edges.map((edge, index) => (
                                        <div key={`${edge.source}-${edge.target}-${index}`} style={{ fontSize: 11, opacity: 0.85 }}>
                                            {index + 1}. {edge.type}: {edge.source}{' -> '}{edge.target}
                                        </div>
                                    ))}
                                </div>
                            </>
                        )}
                    </section>
                </div>
            </div>
        </div>
    );
}
