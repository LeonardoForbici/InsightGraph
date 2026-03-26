import { useState, useCallback, useEffect } from 'react';
import type {
    ChangeDescriptor,
    AffectedSet,
    AffectedItem,
    DataFlowChain,
    ImpactData,
    FieldLevelNode,
    ContractBreak,
    FragilityDetail,
    TaintPath,
    TaintPoint,
    ResolvedSymbol,
    SideEffect,
    BidirectionalResult,
    PropagationChainItem,
    SecurityIssue,
} from '../api';
import {
    analyzeImpact,
    fetchDataFlow,
    fetchImpact,
    fetchContractBreaks,
    fetchFieldNodes,
    fetchFragility,
    fetchFragilityRanking,
    fetchTaintPropagation,
    resolveSymbol,
    fetchSideEffects,
    fetchBidirectionalImpact,
    fetchNodeVulnerabilities,
} from '../api';

export interface ImpactAnalysisPanelProps {
    nodeKey: string;
    nodeName: string;
    onClose: () => void;
    onHighlightNodes: (keys: string[]) => void;
    initialTab?: ImpactTab;
}

export type ImpactTab = 'analyze' | 'dataflow' | 'contracts' | 'fields' | 'taint' | 'symbols' | 'sideeffects' | 'fragility' | 'bidirectional' | 'security';

const CHANGE_TYPES: { value: ChangeDescriptor['change_type']; label: string }[] = [
    { value: 'rename_parameter', label: 'Renomear Parâmetro' },
    { value: 'change_column_type', label: 'Alterar Tipo de Coluna' },
    { value: 'change_method_signature', label: 'Alterar Assinatura de Método' },
    { value: 'change_procedure_param', label: 'Alterar Parâmetro de Procedure' },
];

const CATEGORY_COLORS: Record<string, string> = {
    DIRECT: '#f87171',
    TRANSITIVE: '#fb923c',
    INFERRED: '#facc15',
};

const RISK_COLORS: Record<string, string> = {
    LOW: '#34d399',
    MEDIUM: '#fb923c',
    HIGH: '#f87171',
    CRITICAL: '#e11d48',
};

export default function ImpactAnalysisPanel({
    nodeKey,
    nodeName,
    onClose,
    onHighlightNodes,
    initialTab = 'analyze',
}: ImpactAnalysisPanelProps) {
    const [activeTab, setActiveTab] = useState<ImpactTab>(initialTab);

    // Analyze tab state
    const [changeType, setChangeType] = useState<ChangeDescriptor['change_type']>('rename_parameter');
    const [paramName, setParamName] = useState('');
    const [oldType, setOldType] = useState('');
    const [newType, setNewType] = useState('');
    const [maxDepth, setMaxDepth] = useState(5);
    const [analyzing, setAnalyzing] = useState(false);
    const [affectedSet, setAffectedSet] = useState<AffectedSet | null>(null);
    const [analyzeError, setAnalyzeError] = useState('');
    const [expandedChains, setExpandedChains] = useState<Set<string>>(new Set());

    // Data flow tab state
    const [loadingFlow, setLoadingFlow] = useState(false);
    const [dataFlow, setDataFlow] = useState<DataFlowChain | null>(null);
    const [flowFallback, setFlowFallback] = useState<ImpactData | null>(null);
    const [flowError, setFlowError] = useState('');

    // Contracts tab state
    const [loadingContracts, setLoadingContracts] = useState(false);
    const [contracts, setContracts] = useState<ContractBreak[] | null>(null);
    const [contractsError, setContractsError] = useState('');

    // Field nodes tab state
    const [loadingFields, setLoadingFields] = useState(false);
    const [fieldNodes, setFieldNodes] = useState<FieldLevelNode[] | null>(null);
    const [fieldsError, setFieldsError] = useState('');

    // Fragility header state
    const [fragility, setFragility] = useState<FragilityDetail | null>(null);

    // Taint tab state
    const [taintOrigin, setTaintOrigin] = useState(nodeKey);
    const [taintChangeType, setTaintChangeType] = useState('change_column_type');
    const [taintOldType, setTaintOldType] = useState('');
    const [taintNewType, setTaintNewType] = useState('');
    const [loadingTaint, setLoadingTaint] = useState(false);
    const [taintPath, setTaintPath] = useState<TaintPath | null>(null);
    const [taintError, setTaintError] = useState('');

    // Symbols tab state
    const [symbolName, setSymbolName] = useState('');
    const [loadingSymbols, setLoadingSymbols] = useState(false);
    const [resolvedSymbols, setResolvedSymbols] = useState<ResolvedSymbol[] | null>(null);
    const [symbolsError, setSymbolsError] = useState('');

    // Side effects tab state
    const [loadingSideEffects, setLoadingSideEffects] = useState(false);
    const [sideEffects, setSideEffects] = useState<SideEffect[] | null>(null);
    const [sideEffectsError, setSideEffectsError] = useState('');

    // Fragility tab state
    const [loadingFragilityTab, setLoadingFragilityTab] = useState(false);
    const [fragilityDetail, setFragilityDetail] = useState<FragilityDetail | null>(null);
    const [fragilityRanking, setFragilityRanking] = useState<FragilityDetail[] | null>(null);
    const [fragilityTabError, setFragilityTabError] = useState('');

    // Bidirectional tab state
    const [biDirection, setBiDirection] = useState<'BOTTOM_UP' | 'TOP_DOWN'>('BOTTOM_UP');
    const [loadingBi, setLoadingBi] = useState(false);
    const [biResult, setBiResult] = useState<BidirectionalResult | null>(null);
    const [biImpactFallback, setBiImpactFallback] = useState<ImpactData | null>(null);
    const [biError, setBiError] = useState('');

    // Security tab state
    const [loadingSecurity, setLoadingSecurity] = useState(false);
    const [vulnerabilities, setVulnerabilities] = useState<SecurityIssue[] | null>(null);
    const [securityError, setSecurityError] = useState('');
    const [vulnerabilityCount, setVulnerabilityCount] = useState<number>(0);

    useEffect(() => {
        setActiveTab(initialTab);
    }, [initialTab]);

    const handleAnalyze = useCallback(async () => {
        setAnalyzing(true);
        setAnalyzeError('');
        setAffectedSet(null);
        try {
            const change: ChangeDescriptor = {
                change_type: changeType,
                target_key: nodeKey,
                parameter_name: paramName || undefined,
                old_type: oldType || undefined,
                new_type: newType || undefined,
                max_depth: maxDepth,
            };
            const result = await analyzeImpact(change);
            setAffectedSet(result);
            onHighlightNodes(result.items.map((i) => i.namespace_key));
        } catch (err: any) {
            setAnalyzeError(err.message || 'Erro ao analisar impacto');
        } finally {
            setAnalyzing(false);
        }
    }, [changeType, nodeKey, paramName, oldType, newType, maxDepth, onHighlightNodes]);

    const handleLoadDataFlow = useCallback(async () => {
        setLoadingFlow(true);
        setFlowError('');
        setFlowFallback(null);
        try {
            const result = await fetchDataFlow(nodeKey);
            const resolvedLinks = (result.links ?? []).filter(l => l.resolved && l.to_key !== 'unresolved');
            if (resolvedLinks.length === 0) {
                // Node is not a DB column — fall back to upstream/downstream impact
                const impact = await fetchImpact(nodeKey);
                setFlowFallback(impact);
                setDataFlow(null);
            } else {
                setDataFlow(result);
            }
        } catch (err: any) {
            setFlowError(err.message || 'Erro ao carregar fluxo de dados');
        } finally {
            setLoadingFlow(false);
        }
    }, [nodeKey]);

    const handleLoadContracts = useCallback(async () => {
        setLoadingContracts(true);
        setContractsError('');
        try {
            const result = await fetchContractBreaks();
            setContracts(result.broken_contracts);
        } catch (err: any) {
            setContractsError(err.message || 'Erro ao carregar quebras de contrato');
        } finally {
            setLoadingContracts(false);
        }
    }, []);

    const handleLoadFields = useCallback(async () => {
        setLoadingFields(true);
        setFieldsError('');
        try {
            const result = await fetchFieldNodes(nodeKey);
            setFieldNodes(result.field_nodes);
        } catch (err: any) {
            setFieldsError(err.message || 'Erro ao carregar field nodes');
        } finally {
            setLoadingFields(false);
        }
    }, [nodeKey]);

    // Load fragility score for header thermometer on mount / nodeKey change
    useEffect(() => {
        setFragility(null);
        fetchFragility(nodeKey).then(setFragility).catch(() => {/* silent */});
    }, [nodeKey]);

    // Load vulnerability count for header badge on mount / nodeKey change
    useEffect(() => {
        setVulnerabilityCount(0);
        fetchNodeVulnerabilities(nodeKey)
            .then((vulns) => setVulnerabilityCount(vulns.length))
            .catch(() => {/* silent */});
    }, [nodeKey]);

    const handleTrackTaint = useCallback(async () => {
        setLoadingTaint(true);
        setTaintError('');
        setTaintPath(null);
        try {
            const result = await fetchTaintPropagation({
                origin_key: taintOrigin || nodeKey,
                change_type: taintChangeType,
                old_type: taintOldType || undefined,
                new_type: taintNewType || undefined,
            });
            setTaintPath(result);
        } catch (err: any) {
            setTaintError(err.message || 'Erro ao rastrear taint');
        } finally {
            setLoadingTaint(false);
        }
    }, [taintOrigin, nodeKey, taintChangeType, taintOldType, taintNewType]);

    const handleResolveSymbol = useCallback(async () => {
        if (!symbolName.trim()) return;
        setLoadingSymbols(true);
        setSymbolsError('');
        setResolvedSymbols(null);
        try {
            const result = await resolveSymbol(symbolName.trim(), nodeKey);
            setResolvedSymbols(result);
        } catch (err: any) {
            setSymbolsError(err.message || 'Erro ao resolver símbolo');
        } finally {
            setLoadingSymbols(false);
        }
    }, [symbolName, nodeKey]);

    const handleDetectSideEffects = useCallback(async () => {
        setLoadingSideEffects(true);
        setSideEffectsError('');
        setSideEffects(null);
        try {
            const result = await fetchSideEffects({
                change: {
                    change_type: 'change_method_signature',
                    target_key: nodeKey,
                },
                include_inferred: true,
            });
            setSideEffects(result);
        } catch (err: any) {
            setSideEffectsError(err.message || 'Erro ao detectar efeitos colaterais');
        } finally {
            setLoadingSideEffects(false);
        }
    }, [nodeKey]);

    const handleLoadFragilityTab = useCallback(async () => {
        setLoadingFragilityTab(true);
        setFragilityTabError('');
        try {
            const [detail, ranking] = await Promise.all([
                fetchFragility(nodeKey),
                fetchFragilityRanking(20),
            ]);
            setFragilityDetail(detail);
            setFragilityRanking(ranking);
        } catch (err: any) {
            setFragilityTabError(err.message || 'Erro ao carregar fragilidade');
        } finally {
            setLoadingFragilityTab(false);
        }
    }, [nodeKey]);

    const handleBidirectional = useCallback(async () => {
        setLoadingBi(true);
        setBiError('');
        setBiResult(null);
        setBiImpactFallback(null);
        try {
            const result = await fetchBidirectionalImpact({
                origin_key: nodeKey,
                direction: biDirection,
            });
            setBiResult(result);
            // If isolated, load upstream/downstream as fallback
            if (result.isolated) {
                try {
                    const impact = await fetchImpact(nodeKey);
                    setBiImpactFallback(impact);
                } catch {/* silent */}
            }
        } catch (err: any) {
            setBiError(err.message || 'Erro ao analisar impacto bidirecional');
        } finally {
            setLoadingBi(false);
        }
    }, [nodeKey, biDirection]);

    const handleLoadSecurity = useCallback(async () => {
        setLoadingSecurity(true);
        setSecurityError('');
        setVulnerabilities(null);
        try {
            const result = await fetchNodeVulnerabilities(nodeKey);
            setVulnerabilities(result);
        } catch (err: any) {
            setSecurityError(err.message || 'Erro ao carregar vulnerabilidades');
        } finally {
            setLoadingSecurity(false);
        }
    }, [nodeKey]);

    const toggleChain = (key: string) => {
        setExpandedChains((prev) => {
            const next = new Set(prev);
            next.has(key) ? next.delete(key) : next.add(key);
            return next;
        });
    };

    return (
        <div style={{
            position: 'fixed', top: 0, right: 0, width: 480, height: '100vh',
            background: '#1a1d2e', borderLeft: '1px solid rgba(139,147,176,0.15)',
            display: 'flex', flexDirection: 'column', zIndex: 1000,
            fontFamily: 'system-ui, sans-serif', color: '#c9d1d9',
        }}>
            {/* Header */}
            <div style={{
                padding: '16px 20px', borderBottom: '1px solid rgba(139,147,176,0.15)',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                background: '#161929',
            }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, color: '#8b93b0', marginBottom: 2 }}>Análise de Impacto</div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: '#e6edf3', display: 'flex', alignItems: 'center', gap: 8 }}>
                        {nodeName}
                        {fragility?.is_god_class && (
                            <span style={{
                                fontSize: 10, padding: '2px 6px', borderRadius: 4,
                                background: 'rgba(248,113,113,0.15)', color: '#f87171',
                                fontWeight: 700, whiteSpace: 'nowrap',
                            }}>⚠ God Class</span>
                        )}
                        {vulnerabilityCount > 0 && (
                            <span style={{
                                fontSize: 10, padding: '2px 6px', borderRadius: 4,
                                background: 'rgba(239,68,68,0.15)', color: '#ef4444',
                                fontWeight: 700, whiteSpace: 'nowrap',
                            }}>🔒 {vulnerabilityCount} vuln{vulnerabilityCount > 1 ? 's' : ''}</span>
                        )}
                    </div>
                    {/* Fragility thermometer */}
                    {fragility && (
                        <div style={{ marginTop: 6 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#8b93b0', marginBottom: 3 }}>
                                <span>Fragilidade</span>
                                <span style={{ color: fragilityColor(fragility.fragility_score), fontWeight: 600 }}>
                                    {Math.round(fragility.fragility_score)}/100
                                </span>
                            </div>
                            <div style={{ height: 5, borderRadius: 3, background: 'rgba(139,147,176,0.15)', overflow: 'hidden' }}>
                                <div style={{
                                    height: '100%',
                                    width: `${fragility.fragility_score}%`,
                                    background: fragilityColor(fragility.fragility_score),
                                    borderRadius: 3,
                                    transition: 'width 0.4s ease',
                                }} />
                            </div>
                        </div>
                    )}
                </div>
                <button onClick={onClose} style={{
                    background: 'none', border: 'none', color: '#8b93b0',
                    cursor: 'pointer', fontSize: 20, lineHeight: 1, marginLeft: 12,
                }}>✕</button>
            </div>

            {/* Tabs */}
            <div style={{
                display: 'flex', borderBottom: '1px solid rgba(139,147,176,0.15)',
                background: '#161929', overflowX: 'auto',
            }}>
                {([
                    { id: 'analyze', label: '🔍 Analisar' },
                    { id: 'dataflow', label: '🔗 Fluxo' },
                    { id: 'contracts', label: '⚠ Contratos' },
                    { id: 'fields', label: '📋 Fields' },
                    { id: 'taint', label: '🧪 Taint' },
                    { id: 'symbols', label: '🔍 Símbolos' },
                    { id: 'sideeffects', label: '⚡ Side Effects' },
                    { id: 'fragility', label: '🌡 Fragilidade' },
                    { id: 'bidirectional', label: '↕ Bidirecional' },
                    { id: 'security', label: '🔒 Segurança' },
                ] as { id: Tab; label: string }[]).map((tab) => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        style={{
                            flexShrink: 0, padding: '10px 8px', background: 'none',
                            border: 'none', borderBottom: activeTab === tab.id
                                ? '2px solid #4f8ff7' : '2px solid transparent',
                            color: activeTab === tab.id ? '#4f8ff7' : '#8b93b0',
                            cursor: 'pointer', fontSize: 11, fontWeight: 500, whiteSpace: 'nowrap',
                        }}
                    >
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Content */}
            <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>

                {/* ── Analyze Tab ── */}
                {activeTab === 'analyze' && (
                    <div>
                        <div style={{ marginBottom: 12 }}>
                            <label style={labelStyle}>Tipo de Mudança</label>
                            <select
                                value={changeType}
                                onChange={(e) => setChangeType(e.target.value as ChangeDescriptor['change_type'])}
                                style={selectStyle}
                            >
                                {CHANGE_TYPES.map((ct) => (
                                    <option key={ct.value} value={ct.value}>{ct.label}</option>
                                ))}
                            </select>
                        </div>

                        <div style={{ marginBottom: 12 }}>
                            <label style={labelStyle}>Nome do Parâmetro (opcional)</label>
                            <input
                                value={paramName}
                                onChange={(e) => setParamName(e.target.value)}
                                placeholder="ex: userId"
                                style={inputStyle}
                            />
                        </div>

                        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                            <div style={{ flex: 1 }}>
                                <label style={labelStyle}>Tipo Antigo</label>
                                <input value={oldType} onChange={(e) => setOldType(e.target.value)} placeholder="ex: String" style={inputStyle} />
                            </div>
                            <div style={{ flex: 1 }}>
                                <label style={labelStyle}>Tipo Novo</label>
                                <input value={newType} onChange={(e) => setNewType(e.target.value)} placeholder="ex: Long" style={inputStyle} />
                            </div>
                        </div>

                        <div style={{ marginBottom: 16 }}>
                            <label style={labelStyle}>Profundidade Máxima: {maxDepth}</label>
                            <input
                                type="range" min={1} max={10} value={maxDepth}
                                onChange={(e) => setMaxDepth(Number(e.target.value))}
                                style={{ width: '100%', accentColor: '#4f8ff7' }}
                            />
                        </div>

                        <button onClick={handleAnalyze} disabled={analyzing} style={primaryBtnStyle}>
                            {analyzing ? '⏳ Analisando...' : '🔍 Analisar Impacto'}
                        </button>

                        {analyzeError && <div style={errorStyle}>{analyzeError}</div>}

                        {affectedSet && (
                            <div style={{ marginTop: 16 }}>
                                {/* Metadata */}
                                <div style={metaBoxStyle}>
                                    <span>Total: <b>{affectedSet.analysis_metadata.total_affected}</b></span>
                                    <span style={{ color: '#34d399' }}>Alta confiança: <b>{affectedSet.analysis_metadata.high_confidence_count}</b></span>
                                    <span style={{ color: '#fb923c' }}>Baixa confiança: <b>{affectedSet.analysis_metadata.low_confidence_count}</b></span>
                                    {affectedSet.analysis_metadata.truncated && <span style={{ color: '#f87171' }}>⚠ Truncado</span>}
                                </div>

                                {/* Semantic Analysis */}
                                {affectedSet.semantic_analysis && (
                                    <div style={{ ...cardStyle, marginBottom: 12 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                                            <span style={{ fontSize: 13, fontWeight: 600 }}>Análise Semântica</span>
                                            <span style={{
                                                fontSize: 11, padding: '2px 8px', borderRadius: 4,
                                                background: RISK_COLORS[affectedSet.semantic_analysis.risk_level] + '22',
                                                color: RISK_COLORS[affectedSet.semantic_analysis.risk_level],
                                                fontWeight: 600,
                                            }}>
                                                {affectedSet.semantic_analysis.risk_level}
                                            </span>
                                        </div>
                                        <p style={{ fontSize: 12, color: '#c9d1d9', margin: '0 0 8px' }}>
                                            {affectedSet.semantic_analysis.summary}
                                        </p>
                                        {affectedSet.semantic_analysis.breaking_changes.length > 0 && (
                                            <div style={{ marginBottom: 6 }}>
                                                <div style={{ fontSize: 11, color: '#f87171', fontWeight: 600, marginBottom: 4 }}>Quebras de Contrato</div>
                                                {affectedSet.semantic_analysis.breaking_changes.map((bc, i) => (
                                                    <div key={i} style={{ fontSize: 11, color: '#fca5a5', paddingLeft: 8 }}>• {bc}</div>
                                                ))}
                                            </div>
                                        )}
                                        {affectedSet.semantic_analysis.migration_steps.length > 0 && (
                                            <div style={{ marginBottom: 6 }}>
                                                <div style={{ fontSize: 11, color: '#34d399', fontWeight: 600, marginBottom: 4 }}>Passos de Migração</div>
                                                {affectedSet.semantic_analysis.migration_steps.map((step, i) => (
                                                    <div key={i} style={{ fontSize: 11, color: '#6ee7b7', paddingLeft: 8 }}>{i + 1}. {step}</div>
                                                ))}
                                            </div>
                                        )}
                                        <div style={{ fontSize: 11, color: '#8b93b0' }}>
                                            Esforço estimado: <b style={{ color: '#c9d1d9' }}>{affectedSet.semantic_analysis.estimated_effort}</b>
                                        </div>
                                    </div>
                                )}

                                {/* Affected items */}
                                {affectedSet.items.map((item) => (
                                    <AffectedItemCard
                                        key={item.namespace_key}
                                        item={item}
                                        expanded={expandedChains.has(item.namespace_key)}
                                        onToggle={() => toggleChain(item.namespace_key)}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* ── Data Flow Tab ── */}
                {activeTab === 'dataflow' && (
                    <div>
                        <p style={{ fontSize: 12, color: '#8b93b0', marginBottom: 12 }}>
                            Rastreia o caminho do dado desde a coluna até o componente Angular.
                            Para outros artefatos, exibe dependências upstream/downstream.
                        </p>
                        <button onClick={handleLoadDataFlow} disabled={loadingFlow} style={primaryBtnStyle}>
                            {loadingFlow ? '⏳ Carregando...' : '🔗 Carregar Fluxo de Dados'}
                        </button>
                        {flowError && <div style={errorStyle}>{flowError}</div>}

                        {/* Column data flow chain */}
                        {dataFlow && (
                            <div style={{ marginTop: 16 }}>
                                {(dataFlow.links ?? []).filter(l => l.resolved && l.to_key !== 'unresolved').map((link, i) => (
                                    <div key={i} style={{ ...cardStyle, marginBottom: 8 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                            <span style={{ fontSize: 11, color: '#8b93b0', flex: 1, wordBreak: 'break-all' }}>
                                                {link.from_key}
                                            </span>
                                            <span style={{
                                                fontSize: 10, padding: '2px 6px', borderRadius: 4,
                                                background: 'rgba(79,143,247,0.15)', color: '#4f8ff7',
                                            }}>{link.rel_type}</span>
                                            <span style={{ fontSize: 11, color: '#8b93b0', flex: 1, wordBreak: 'break-all', textAlign: 'right' }}>
                                                {link.to_key}
                                            </span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Fallback: upstream/downstream for non-column nodes */}
                        {flowFallback && (
                            <div style={{ marginTop: 16 }}>
                                <div style={{ fontSize: 11, color: '#fb923c', marginBottom: 8 }}>
                                    ℹ Este artefato não é uma coluna de banco de dados. Exibindo dependências upstream/downstream.
                                </div>
                                {flowFallback.upstream.length > 0 && (
                                    <div style={{ marginBottom: 12 }}>
                                        <div style={{ fontSize: 12, fontWeight: 600, color: '#34d399', marginBottom: 6 }}>
                                            ↑ Upstream ({flowFallback.upstream.length})
                                        </div>
                                        {flowFallback.upstream.map((item, i) => (
                                            <div key={i} style={{ ...cardStyle, marginBottom: 6 }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                                    <span style={{ fontSize: 11, color: '#e6edf3', flex: 1, wordBreak: 'break-all' }}>{item.name}</span>
                                                    <span style={{
                                                        fontSize: 10, padding: '2px 6px', borderRadius: 4,
                                                        background: 'rgba(52,211,153,0.15)', color: '#34d399',
                                                    }}>{item.rel_type}</span>
                                                </div>
                                                <div style={{ fontSize: 10, color: '#8b93b0', marginTop: 2, wordBreak: 'break-all' }}>{item.key}</div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                {flowFallback.downstream.length > 0 && (
                                    <div>
                                        <div style={{ fontSize: 12, fontWeight: 600, color: '#f87171', marginBottom: 6 }}>
                                            ↓ Downstream ({flowFallback.downstream.length})
                                        </div>
                                        {flowFallback.downstream.map((item, i) => (
                                            <div key={i} style={{ ...cardStyle, marginBottom: 6 }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                                    <span style={{ fontSize: 11, color: '#e6edf3', flex: 1, wordBreak: 'break-all' }}>{item.name}</span>
                                                    <span style={{
                                                        fontSize: 10, padding: '2px 6px', borderRadius: 4,
                                                        background: 'rgba(248,113,113,0.15)', color: '#f87171',
                                                    }}>{item.rel_type}</span>
                                                </div>
                                                <div style={{ fontSize: 10, color: '#8b93b0', marginTop: 2, wordBreak: 'break-all' }}>{item.key}</div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                {flowFallback.upstream.length === 0 && flowFallback.downstream.length === 0 && (
                                    <div style={{ color: '#8b93b0', fontSize: 12 }}>Nenhuma dependência encontrada para este artefato.</div>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {/* ── Contracts Tab ── */}
                {activeTab === 'contracts' && (
                    <div>
                        <p style={{ fontSize: 12, color: '#8b93b0', marginBottom: 12 }}>
                            Artefatos com assinatura alterada desde o último scan (quebra de contrato global).
                        </p>
                        <button onClick={handleLoadContracts} disabled={loadingContracts} style={primaryBtnStyle}>
                            {loadingContracts ? '⏳ Carregando...' : '⚠ Carregar Quebras de Contrato'}
                        </button>
                        {contractsError && <div style={errorStyle}>{contractsError}</div>}
                        {contracts && (
                            <div style={{ marginTop: 16 }}>
                                {contracts.length === 0 && (
                                    <div style={{ color: '#34d399', fontSize: 12 }}>
                                        ✅ Nenhuma quebra de contrato detectada.<br />
                                        <span style={{ color: '#8b93b0', fontSize: 11 }}>
                                            Quebras são detectadas quando a assinatura de um artefato muda entre scans.
                                        </span>
                                    </div>
                                )}
                                {contracts.map((c) => (
                                    <div key={c.namespace_key} style={{ ...cardStyle, marginBottom: 8 }}>
                                        <div style={{ fontSize: 13, fontWeight: 600, color: '#f87171', marginBottom: 4 }}>{c.name}</div>
                                        <div style={{ fontSize: 11, color: '#8b93b0', wordBreak: 'break-all', marginBottom: 4 }}>{c.namespace_key}</div>
                                        {c.previous_signature_hash && (
                                            <div style={{ fontSize: 10, color: '#8b93b0' }}>
                                                Hash anterior: <code style={{ color: '#c9d1d9' }}>{c.previous_signature_hash.slice(0, 16)}…</code>
                                            </div>
                                        )}
                                        {c.affected_set && (
                                            <div style={{ fontSize: 11, color: '#fb923c', marginTop: 4 }}>
                                                {c.affected_set.total_affected} artefatos impactados
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* ── Field Nodes Tab ── */}
                {activeTab === 'fields' && (
                    <div>
                        <p style={{ fontSize: 12, color: '#8b93b0', marginBottom: 12 }}>
                            Parâmetros, campos e colunas associados a este artefato.
                        </p>
                        <button onClick={handleLoadFields} disabled={loadingFields} style={primaryBtnStyle}>
                            {loadingFields ? '⏳ Carregando...' : '📋 Carregar Field Nodes'}
                        </button>
                        {fieldsError && <div style={errorStyle}>{fieldsError}</div>}
                        {fieldNodes && (
                            <div style={{ marginTop: 16 }}>
                                {fieldNodes.length === 0 && (
                                    <div style={{ color: '#8b93b0', fontSize: 12 }}>
                                        Nenhum field node encontrado.<br />
                                        <span style={{ fontSize: 11 }}>
                                            Field nodes são gerados para procedures, stored procedures e entidades com colunas mapeadas.
                                            Classes Java comuns não possuem field nodes.
                                        </span>
                                    </div>
                                )}
                                {fieldNodes.length > 0 && (
                                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                                        <thead>
                                            <tr style={{ color: '#8b93b0', borderBottom: '1px solid rgba(139,147,176,0.2)' }}>
                                                <th style={thStyle}>Nome</th>
                                                <th style={thStyle}>Kind</th>
                                                <th style={thStyle}>Tipo</th>
                                                <th style={thStyle}>Modo</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {fieldNodes.map((fn) => (
                                                <tr key={fn.namespace_key} style={{ borderBottom: '1px solid rgba(139,147,176,0.08)' }}>
                                                    <td style={tdStyle}>{fn.name}</td>
                                                    <td style={{ ...tdStyle, color: '#4f8ff7' }}>{fn.kind}</td>
                                                    <td style={{ ...tdStyle, color: '#34d399' }}>{fn.data_type}</td>
                                                    <td style={{ ...tdStyle, color: '#fb923c' }}>{fn.param_mode || '—'}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {/* ── Taint Tab ── */}
                {activeTab === 'taint' && (
                    <div>
                        <div style={{ marginBottom: 12 }}>
                            <label style={labelStyle}>Chave de Origem</label>
                            <input
                                value={taintOrigin}
                                onChange={(e) => setTaintOrigin(e.target.value)}
                                placeholder={nodeKey}
                                style={inputStyle}
                            />
                        </div>
                        <div style={{ marginBottom: 12 }}>
                            <label style={labelStyle}>Tipo de Mudança</label>
                            <input
                                value={taintChangeType}
                                onChange={(e) => setTaintChangeType(e.target.value)}
                                placeholder="ex: change_column_type"
                                style={inputStyle}
                            />
                        </div>
                        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                            <div style={{ flex: 1 }}>
                                <label style={labelStyle}>Tipo Antigo</label>
                                <input value={taintOldType} onChange={(e) => setTaintOldType(e.target.value)} placeholder="ex: NUMBER" style={inputStyle} />
                            </div>
                            <div style={{ flex: 1 }}>
                                <label style={labelStyle}>Tipo Novo</label>
                                <input value={taintNewType} onChange={(e) => setTaintNewType(e.target.value)} placeholder="ex: DECIMAL" style={inputStyle} />
                            </div>
                        </div>
                        <button onClick={handleTrackTaint} disabled={loadingTaint} style={primaryBtnStyle}>
                            {loadingTaint ? '⏳ Rastreando...' : '🧪 Rastrear Taint'}
                        </button>
                        {taintError && <div style={errorStyle}>{taintError}</div>}
                        {taintPath && (
                            <div style={{ marginTop: 16 }}>
                                <div style={{ ...metaBoxStyle, marginBottom: 12 }}>
                                    <span>Saltos: <b>{taintPath.total_hops}</b></span>
                                    <span>Origem: <b>{taintPath.origin_layer}</b></span>
                                    <span>Destino: <b>{taintPath.destination_layer}</b></span>
                                    {taintPath.unresolved_links.length > 0 && (
                                        <span style={{ color: '#fb923c' }}>⚠ {taintPath.unresolved_links.length} elos não resolvidos</span>
                                    )}
                                </div>
                                {taintPath.points.map((pt: TaintPoint, i: number) => (
                                    <TaintPointCard key={i} point={pt} index={i} />
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* ── Symbols Tab ── */}
                {activeTab === 'symbols' && (
                    <div>
                        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                            <input
                                value={symbolName}
                                onChange={(e) => setSymbolName(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleResolveSymbol()}
                                placeholder="Nome do símbolo (ex: save)"
                                style={{ ...inputStyle, flex: 1 }}
                            />
                            <button onClick={handleResolveSymbol} disabled={loadingSymbols} style={{ ...primaryBtnStyle, width: 'auto', marginBottom: 0, whiteSpace: 'nowrap' }}>
                                {loadingSymbols ? '⏳' : 'Resolver'}
                            </button>
                        </div>
                        {symbolsError && <div style={errorStyle}>{symbolsError}</div>}
                        {resolvedSymbols && (
                            <div style={{ marginTop: 8 }}>
                                {resolvedSymbols.length === 0 && (
                                    <div style={{ color: '#8b93b0', fontSize: 12 }}>Nenhum símbolo encontrado.</div>
                                )}
                                {resolvedSymbols.map((sym, i) => (
                                    <div key={i} style={{
                                        ...cardStyle, marginBottom: 8,
                                        borderColor: sym.semantic_conflicts.length > 0
                                            ? 'rgba(251,146,60,0.4)' : 'rgba(139,147,176,0.12)',
                                    }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                                            <span style={{ fontSize: 13, fontWeight: 600, color: '#e6edf3', flex: 1 }}>{sym.name}</span>
                                            <span style={{
                                                fontSize: 10, padding: '2px 6px', borderRadius: 4,
                                                background: sym.confidence_score >= 70 ? 'rgba(52,211,153,0.15)' : 'rgba(251,146,60,0.15)',
                                                color: sym.confidence_score >= 70 ? '#34d399' : '#fb923c',
                                                fontWeight: 600,
                                            }}>{sym.confidence_score}%</span>
                                        </div>
                                        <div style={{ fontSize: 10, color: '#8b93b0', marginBottom: 4, wordBreak: 'break-all' }}>{sym.namespace_key}</div>
                                        <div style={{ fontSize: 11, color: '#8b93b0' }}>
                                            Classe: <span style={{ color: '#c9d1d9' }}>{sym.type_context.declaring_class || '—'}</span>
                                            {' · '}Módulo: <span style={{ color: '#c9d1d9' }}>{sym.type_context.module || '—'}</span>
                                            {' · '}Retorno: <span style={{ color: '#34d399' }}>{sym.type_context.return_type || '—'}</span>
                                        </div>
                                        <div style={{ fontSize: 10, color: '#8b93b0', marginTop: 2 }}>
                                            Método: <span style={{ color: '#4f8ff7' }}>{sym.resolution_method}</span>
                                        </div>
                                        {sym.semantic_conflicts.length > 0 && (
                                            <div style={{ marginTop: 6, padding: '4px 8px', background: 'rgba(251,146,60,0.08)', borderRadius: 4 }}>
                                                <div style={{ fontSize: 10, color: '#fb923c', fontWeight: 600, marginBottom: 2 }}>⚠ Conflitos Semânticos</div>
                                                {sym.semantic_conflicts.map((c, j) => (
                                                    <div key={j} style={{ fontSize: 10, color: '#fcd34d', wordBreak: 'break-all' }}>• {c}</div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* ── Side Effects Tab ── */}
                {activeTab === 'sideeffects' && (
                    <div>
                        <p style={{ fontSize: 12, color: '#8b93b0', marginBottom: 12 }}>
                            Detecta efeitos colaterais silenciosos de lógica de negócio para o artefato selecionado.
                        </p>
                        <button onClick={handleDetectSideEffects} disabled={loadingSideEffects} style={primaryBtnStyle}>
                            {loadingSideEffects ? '⏳ Detectando...' : '⚡ Detectar Efeitos Colaterais'}
                        </button>
                        {sideEffectsError && <div style={errorStyle}>{sideEffectsError}</div>}
                        {sideEffects && (
                            <div style={{ marginTop: 16 }}>
                                {sideEffects.length === 0 && (
                                    <div style={{ color: '#34d399', fontSize: 12 }}>✅ Nenhum efeito colateral detectado.</div>
                                )}
                                {sideEffects.map((effect, i) => (
                                    <div key={i} style={{ ...cardStyle, marginBottom: 8 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                                            {effect.effect_type === 'SILENT_LOGIC_FAILURE' && (
                                                <span style={{ fontSize: 14 }}>🔴</span>
                                            )}
                                            <span style={{ fontSize: 12, fontWeight: 600, color: '#e6edf3', flex: 1 }}>{effect.artifact_name}</span>
                                            {effect.inferred && (
                                                <span style={{
                                                    fontSize: 10, padding: '2px 6px', borderRadius: 4,
                                                    background: 'rgba(139,147,176,0.15)', color: '#8b93b0', fontWeight: 600,
                                                }}>Inferido (IA)</span>
                                            )}
                                        </div>
                                        <div style={{ fontSize: 11, color: '#fb923c', marginBottom: 4 }}>{effect.effect_type}</div>
                                        {effect.rule_violated && (
                                            <div style={{ fontSize: 11, color: '#c9d1d9', marginBottom: 2 }}>
                                                Regra violada: <span style={{ color: '#fca5a5' }}>{effect.rule_violated}</span>
                                            </div>
                                        )}
                                        <div style={{ fontSize: 10, color: '#8b93b0' }}>
                                            Confiança: <span style={{ color: effect.confidence_score >= 70 ? '#34d399' : '#fb923c' }}>{effect.confidence_score}%</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* ── Fragility Tab ── */}
                {activeTab === 'fragility' && (
                    <div>
                        <button onClick={handleLoadFragilityTab} disabled={loadingFragilityTab} style={primaryBtnStyle}>
                            {loadingFragilityTab ? '⏳ Carregando...' : '🌡 Carregar Fragilidade'}
                        </button>
                        {fragilityTabError && <div style={errorStyle}>{fragilityTabError}</div>}
                        {fragilityDetail && (
                            <div style={{ ...cardStyle, marginTop: 12, marginBottom: 16 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                                    <span style={{ fontSize: 13, fontWeight: 600, color: '#e6edf3' }}>{fragilityDetail.name}</span>
                                    {fragilityDetail.is_god_class && (
                                        <span style={{
                                            fontSize: 10, padding: '2px 6px', borderRadius: 4,
                                            background: 'rgba(248,113,113,0.15)', color: '#f87171', fontWeight: 700,
                                        }}>⚠ God Class</span>
                                    )}
                                    <span style={{
                                        marginLeft: 'auto', fontSize: 18, fontWeight: 700,
                                        color: fragilityColor(fragilityDetail.fragility_score),
                                    }}>{Math.round(fragilityDetail.fragility_score)}</span>
                                </div>
                                <div style={{ height: 6, borderRadius: 3, background: 'rgba(139,147,176,0.15)', marginBottom: 10, overflow: 'hidden' }}>
                                    <div style={{
                                        height: '100%', width: `${fragilityDetail.fragility_score}%`,
                                        background: fragilityColor(fragilityDetail.fragility_score), borderRadius: 3,
                                    }} />
                                </div>
                                <div style={{ display: 'flex', gap: 16, fontSize: 11, color: '#8b93b0', flexWrap: 'wrap' }}>
                                    <span>Dependentes: <b style={{ color: '#c9d1d9' }}>{fragilityDetail.dependents_count}</b></span>
                                    <span>Profundidade: <b style={{ color: '#c9d1d9' }}>{fragilityDetail.graph_depth}</b></span>
                                    <span>Complexidade: <b style={{ color: '#c9d1d9' }}>{fragilityDetail.cyclomatic_complexity}</b></span>
                                </div>
                                {fragilityDetail.previous_fragility_score !== null && (
                                    <div style={{ fontSize: 10, color: '#8b93b0', marginTop: 6 }}>
                                        Score anterior: <span style={{ color: '#c9d1d9' }}>{Math.round(fragilityDetail.previous_fragility_score)}</span>
                                    </div>
                                )}
                                {fragilityDetail.refactoring_recommendation && (
                                    <div style={{ marginTop: 8, padding: '6px 8px', background: 'rgba(79,143,247,0.08)', borderRadius: 4, fontSize: 11, color: '#93c5fd' }}>
                                        💡 {fragilityDetail.refactoring_recommendation}
                                    </div>
                                )}
                            </div>
                        )}
                        {fragilityRanking && (
                            <div>
                                <div style={{ fontSize: 12, fontWeight: 600, color: '#8b93b0', marginBottom: 8 }}>Top 20 Mais Frágeis</div>
                                {fragilityRanking.map((item, i) => (
                                    <div key={item.node_key} style={{ ...cardStyle, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
                                        <span style={{ fontSize: 11, color: '#8b93b0', width: 20, flexShrink: 0 }}>#{i + 1}</span>
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                                <span style={{ fontSize: 12, color: '#e6edf3', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</span>
                                                {item.is_god_class && (
                                                    <span style={{
                                                        fontSize: 9, padding: '1px 5px', borderRadius: 3,
                                                        background: 'rgba(248,113,113,0.15)', color: '#f87171', fontWeight: 700, flexShrink: 0,
                                                    }}>God Class</span>
                                                )}
                                            </div>
                                            <div style={{ height: 3, borderRadius: 2, background: 'rgba(139,147,176,0.1)', marginTop: 4, overflow: 'hidden' }}>
                                                <div style={{
                                                    height: '100%', width: `${item.fragility_score}%`,
                                                    background: fragilityColor(item.fragility_score), borderRadius: 2,
                                                }} />
                                            </div>
                                        </div>
                                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2, flexShrink: 0 }}>
                                            <span style={{ fontSize: 12, fontWeight: 700, color: fragilityColor(item.fragility_score) }}>
                                                {Math.round(item.fragility_score)}
                                            </span>
                                            <button
                                                onClick={() => onHighlightNodes([item.node_key])}
                                                style={{
                                                    background: 'none', border: 'none', color: '#4f8ff7',
                                                    cursor: 'pointer', fontSize: 10, padding: 0,
                                                }}
                                                title="Abrir no grafo"
                                            >↗</button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* ── Bidirectional Tab ── */}
                {activeTab === 'bidirectional' && (
                    <div>
                        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                            {(['BOTTOM_UP', 'TOP_DOWN'] as const).map((dir) => (
                                <button
                                    key={dir}
                                    onClick={() => setBiDirection(dir)}
                                    style={{
                                        flex: 1, padding: '8px', borderRadius: 6,
                                        border: biDirection === dir ? '1px solid #4f8ff7' : '1px solid rgba(139,147,176,0.2)',
                                        background: biDirection === dir ? 'rgba(79,143,247,0.12)' : 'transparent',
                                        color: biDirection === dir ? '#4f8ff7' : '#8b93b0',
                                        cursor: 'pointer', fontSize: 12, fontWeight: 600,
                                    }}
                                >
                                    {dir === 'BOTTOM_UP' ? '⬆ Bottom-Up' : '⬇ Top-Down'}
                                </button>
                            ))}
                        </div>
                        <button onClick={handleBidirectional} disabled={loadingBi} style={primaryBtnStyle}>
                            {loadingBi ? '⏳ Analisando...' : '↕ Analisar'}
                        </button>
                        {biError && <div style={errorStyle}>{biError}</div>}
                        {biResult && (
                            <div style={{ marginTop: 16 }}>
                                {biResult.isolated ? (
                                    <div>
                                        <div style={{
                                            padding: '12px', background: 'rgba(139,147,176,0.08)',
                                            border: '1px solid rgba(139,147,176,0.2)', borderRadius: 8,
                                            fontSize: 12, color: '#8b93b0', textAlign: 'center', marginBottom: 12,
                                        }}>
                                            🔒 Nenhuma cadeia de propagação encontrada via relações diretas.
                                            Exibindo dependências upstream/downstream.
                                        </div>
                                        {biImpactFallback && (
                                            <>
                                                {biImpactFallback.upstream.length > 0 && (
                                                    <div style={{ marginBottom: 12 }}>
                                                        <div style={{ fontSize: 12, fontWeight: 600, color: '#34d399', marginBottom: 6 }}>
                                                            ↑ Upstream ({biImpactFallback.upstream.length})
                                                        </div>
                                                        {biImpactFallback.upstream.map((item, i) => (
                                                            <div key={i} style={{ ...cardStyle, marginBottom: 6 }}>
                                                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                                                    <span style={{ fontSize: 11, color: '#e6edf3', flex: 1, wordBreak: 'break-all' }}>{item.name}</span>
                                                                    <span style={{
                                                                        fontSize: 10, padding: '2px 6px', borderRadius: 4,
                                                                        background: 'rgba(52,211,153,0.15)', color: '#34d399',
                                                                    }}>{item.rel_type}</span>
                                                                </div>
                                                                <div style={{ fontSize: 10, color: '#8b93b0', marginTop: 2, wordBreak: 'break-all' }}>{item.key}</div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                                {biImpactFallback.downstream.length > 0 && (
                                                    <div>
                                                        <div style={{ fontSize: 12, fontWeight: 600, color: '#f87171', marginBottom: 6 }}>
                                                            ↓ Downstream ({biImpactFallback.downstream.length})
                                                        </div>
                                                        {biImpactFallback.downstream.map((item, i) => (
                                                            <div key={i} style={{ ...cardStyle, marginBottom: 6 }}>
                                                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                                                    <span style={{ fontSize: 11, color: '#e6edf3', flex: 1, wordBreak: 'break-all' }}>{item.name}</span>
                                                                    <span style={{
                                                                        fontSize: 10, padding: '2px 6px', borderRadius: 4,
                                                                        background: 'rgba(248,113,113,0.15)', color: '#f87171',
                                                                    }}>{item.rel_type}</span>
                                                                </div>
                                                                <div style={{ fontSize: 10, color: '#8b93b0', marginTop: 2, wordBreak: 'break-all' }}>{item.key}</div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                                {biImpactFallback.upstream.length === 0 && biImpactFallback.downstream.length === 0 && (
                                                    <div style={{ color: '#8b93b0', fontSize: 12 }}>Nenhuma dependência encontrada para este artefato.</div>
                                                )}
                                            </>
                                        )}
                                    </div>
                                ) : (
                                    <>
                                        <div style={{ ...metaBoxStyle, marginBottom: 12 }}>
                                            <span>Saltos: <b>{biResult.total_hops}</b></span>
                                            <span>Direção: <b>{biResult.direction}</b></span>
                                            {biResult.truncated && <span style={{ color: '#fb923c' }}>⚠ Truncado</span>}
                                        </div>
                                        {biResult.chain.map((item: PropagationChainItem, i: number) => (
                                            <div key={i} style={{
                                                ...cardStyle, marginBottom: 6,
                                                borderColor: item.precision_risk
                                                    ? 'rgba(251,146,60,0.4)'
                                                    : 'rgba(139,147,176,0.12)',
                                                background: item.precision_risk
                                                    ? 'rgba(251,146,60,0.05)'
                                                    : 'rgba(255,255,255,0.03)',
                                            }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                                    <span style={{ fontSize: 11, color: '#8b93b0', width: 20, flexShrink: 0 }}>{i + 1}.</span>
                                                    <span style={{ fontSize: 12, color: '#e6edf3', flex: 1 }}>{item.name}</span>
                                                    {item.side_effect_risk && <span title="Risco de efeito colateral">⚡</span>}
                                                    {item.precision_risk && (
                                                        <span style={{ fontSize: 10, color: '#fb923c' }} title="Risco de precisão">⚠</span>
                                                    )}
                                                </div>
                                                <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: 10, color: '#8b93b0' }}>
                                                    <span>Camada: <span style={{ color: '#4f8ff7' }}>{item.layer}</span></span>
                                                    <span>Tipo: <span style={{ color: '#34d399' }}>{item.data_type || '—'}</span></span>
                                                    <span>Fragilidade: <span style={{ color: fragilityColor(item.fragility_score) }}>{Math.round(item.fragility_score)}</span></span>
                                                </div>
                                            </div>
                                        ))}
                                    </>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {/* ── Security Tab ── */}
                {activeTab === 'security' && (
                    <div>
                        <p style={{ fontSize: 12, color: '#8b93b0', marginBottom: 12 }}>
                            Vulnerabilidades de segurança detectadas pelo CodeQL para este artefato.
                        </p>
                        <button onClick={handleLoadSecurity} disabled={loadingSecurity} style={primaryBtnStyle}>
                            {loadingSecurity ? '⏳ Carregando...' : '🔒 Carregar Vulnerabilidades'}
                        </button>
                        {securityError && <div style={errorStyle}>{securityError}</div>}
                        {vulnerabilities && (
                            <div style={{ marginTop: 16 }}>
                                {vulnerabilities.length === 0 && (
                                    <div style={{ color: '#34d399', fontSize: 12 }}>
                                        ✅ Nenhuma vulnerabilidade detectada para este artefato.
                                    </div>
                                )}
                                {vulnerabilities.map((vuln, i) => (
                                    <VulnerabilityCard key={i} vulnerability={vuln} />
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

function AffectedItemCard({ item, expanded, onToggle }: {
    item: AffectedItem;
    expanded: boolean;
    onToggle: () => void;
}) {
    const catColor = CATEGORY_COLORS[item.category] || '#8b93b0';
    return (
        <div style={{ ...cardStyle, marginBottom: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <span style={{
                    fontSize: 10, padding: '2px 6px', borderRadius: 4,
                    background: catColor + '22', color: catColor, fontWeight: 600,
                }}>{item.category}</span>
                <span style={{ fontSize: 12, flex: 1, color: '#e6edf3', wordBreak: 'break-all' }}>{item.name}</span>
                <span style={{
                    fontSize: 11, color: item.confidence_score >= 70 ? '#34d399' : '#fb923c',
                    fontWeight: 600,
                }}>{item.confidence_score}%</span>
                {item.requires_manual_review && (
                    <span title="Revisão manual recomendada" style={{ color: '#f87171', fontSize: 12 }}>⚠</span>
                )}
            </div>
            <div style={{ fontSize: 10, color: '#8b93b0', wordBreak: 'break-all', marginBottom: 4 }}>
                {item.namespace_key}
            </div>
            {item.call_chain.length > 1 && (
                <button onClick={onToggle} style={{
                    background: 'none', border: 'none', color: '#4f8ff7',
                    cursor: 'pointer', fontSize: 11, padding: 0,
                }}>
                    {expanded ? '▲ Ocultar cadeia' : `▼ Ver cadeia (${item.call_chain.length} nós)`}
                </button>
            )}
            {expanded && (
                <div style={{ marginTop: 6, paddingLeft: 8, borderLeft: '2px solid rgba(79,143,247,0.3)' }}>
                    {item.call_chain.map((key, i) => (
                        <div key={i} style={{ fontSize: 10, color: '#8b93b0', marginBottom: 2 }}>
                            {i > 0 && <span style={{ color: '#4f8ff7', marginRight: 4 }}>→</span>}
                            {key}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

/* ─── Helper: fragility color ─── */
function fragilityColor(score: number): string {
    if (score < 40) return '#34d399';   // green
    if (score <= 70) return '#facc15';  // yellow
    if (score <= 80) return '#fb923c';  // orange
    return '#f87171';                   // red
}

/* ─── TaintPointCard ─── */
function TaintPointCard({ point, index }: { point: TaintPoint; index: number }) {
    const [showTooltip, setShowTooltip] = useState(false);
    const bg = point.precision_risk
        ? 'rgba(251,146,60,0.08)'
        : !point.resolved
            ? 'rgba(139,147,176,0.06)'
            : 'rgba(255,255,255,0.03)';
    const border = point.precision_risk
        ? 'rgba(251,146,60,0.35)'
        : !point.resolved
            ? 'rgba(139,147,176,0.2)'
            : 'rgba(139,147,176,0.12)';
    return (
        <div style={{ ...cardStyle, marginBottom: 6, background: bg, borderColor: border, position: 'relative' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 10, color: '#8b93b0', width: 18, flexShrink: 0 }}>{index + 1}.</span>
                <span style={{ fontSize: 12, color: '#e6edf3', flex: 1 }}>{point.name}</span>
                {point.precision_risk && (
                    <span
                        style={{ fontSize: 10, color: '#fb923c', cursor: 'help' }}
                        onMouseEnter={() => setShowTooltip(true)}
                        onMouseLeave={() => setShowTooltip(false)}
                        title={point.precision_risk_description}
                    >⚠ Precisão</span>
                )}
                {!point.resolved && (
                    <span style={{ fontSize: 10, color: '#8b93b0' }}>⚠ Não resolvido</span>
                )}
            </div>
            <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: 10, color: '#8b93b0' }}>
                <span>Camada: <span style={{ color: '#4f8ff7' }}>{point.layer}</span></span>
                <span>Tipo: <span style={{ color: '#34d399' }}>{point.data_type || '—'}</span></span>
            </div>
            {showTooltip && point.precision_risk_description && (
                <div style={{
                    position: 'absolute', bottom: '100%', right: 0, zIndex: 10,
                    background: '#1a1d2e', border: '1px solid rgba(251,146,60,0.4)',
                    borderRadius: 6, padding: '6px 10px', fontSize: 11, color: '#fcd34d',
                    maxWidth: 260, whiteSpace: 'normal', marginBottom: 4,
                }}>
                    {point.precision_risk_description}
                </div>
            )}
        </div>
    );
}

/* ─── VulnerabilityCard ─── */
function VulnerabilityCard({ vulnerability }: { vulnerability: SecurityIssue }) {
    const severityColors: Record<string, { bg: string; text: string; border: string }> = {
        error: { bg: 'rgba(239,68,68,0.08)', text: '#ef4444', border: 'rgba(239,68,68,0.3)' },
        warning: { bg: 'rgba(251,146,60,0.08)', text: '#fb923c', border: 'rgba(251,146,60,0.3)' },
        note: { bg: 'rgba(59,130,246,0.08)', text: '#3b82f6', border: 'rgba(59,130,246,0.3)' },
    };
    
    const colors = severityColors[vulnerability.severity] || severityColors.note;
    
    return (
        <div style={{
            ...cardStyle,
            marginBottom: 8,
            background: colors.bg,
            borderColor: colors.border,
        }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <span style={{
                    fontSize: 10,
                    padding: '2px 6px',
                    borderRadius: 4,
                    background: colors.text + '22',
                    color: colors.text,
                    fontWeight: 600,
                    textTransform: 'uppercase',
                }}>
                    {vulnerability.severity}
                </span>
                <span style={{
                    fontSize: 11,
                    color: '#8b93b0',
                    fontFamily: 'monospace',
                }}>
                    {vulnerability.rule_id}
                </span>
            </div>
            
            <div style={{
                fontSize: 12,
                color: '#e6edf3',
                marginBottom: 6,
                lineHeight: 1.4,
            }}>
                {vulnerability.message}
            </div>
            
            <div style={{
                fontSize: 10,
                color: '#8b93b0',
                marginBottom: 4,
            }}>
                📄 {vulnerability.file_path}
            </div>
            
            <div style={{
                fontSize: 10,
                color: '#8b93b0',
            }}>
                📍 Linhas {vulnerability.start_line}–{vulnerability.end_line}
            </div>
            
            {vulnerability.entity_key && (
                <div style={{
                    fontSize: 10,
                    color: '#4f8ff7',
                    marginTop: 4,
                    wordBreak: 'break-all',
                }}>
                    🔗 {vulnerability.entity_key}
                </div>
            )}
        </div>
    );
}

/* ─── Shared styles ─── */
const labelStyle: React.CSSProperties = {
    display: 'block', fontSize: 11, color: '#8b93b0', marginBottom: 4, fontWeight: 500,
};
const inputStyle: React.CSSProperties = {
    width: '100%', padding: '7px 10px', background: '#0d1117',
    border: '1px solid rgba(139,147,176,0.2)', borderRadius: 6,
    color: '#e6edf3', fontSize: 12, boxSizing: 'border-box',
};
const selectStyle: React.CSSProperties = {
    ...inputStyle, cursor: 'pointer',
};
const primaryBtnStyle: React.CSSProperties = {
    width: '100%', padding: '9px 16px', background: '#4f8ff7',
    border: 'none', borderRadius: 6, color: '#fff',
    cursor: 'pointer', fontSize: 13, fontWeight: 600, marginBottom: 4,
};
const errorStyle: React.CSSProperties = {
    marginTop: 8, padding: '8px 12px', background: 'rgba(248,113,113,0.1)',
    border: '1px solid rgba(248,113,113,0.3)', borderRadius: 6,
    color: '#f87171', fontSize: 12,
};
const cardStyle: React.CSSProperties = {
    padding: '10px 12px', background: 'rgba(255,255,255,0.03)',
    border: '1px solid rgba(139,147,176,0.12)', borderRadius: 8,
};
const metaBoxStyle: React.CSSProperties = {
    display: 'flex', gap: 12, flexWrap: 'wrap',
    padding: '8px 12px', background: 'rgba(79,143,247,0.06)',
    border: '1px solid rgba(79,143,247,0.15)', borderRadius: 6,
    fontSize: 12, marginBottom: 12,
};
const thStyle: React.CSSProperties = {
    textAlign: 'left', padding: '6px 8px', fontWeight: 500, fontSize: 11,
};
const tdStyle: React.CSSProperties = {
    padding: '6px 8px', color: '#c9d1d9',
};
