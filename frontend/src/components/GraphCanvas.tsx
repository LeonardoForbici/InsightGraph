import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import {
    ReactFlow,
    Controls,
    MiniMap,
    Background,
    useNodesState,
    useEdgesState,
    Handle,
    Position,
    MarkerType,
    BackgroundVariant,
    ReactFlowProvider,
} from '@xyflow/react';
import type { Node, Edge, NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from '@dagrejs/dagre';
import type { GraphNode, GraphEdge } from '../api';
import GraphCanvas3D from './GraphCanvas3D';

/* ─── Helpers ─── */
function getNodeClass(labels: string[]): string {
    if (labels.includes('Java_Class')) return 'java-class';
    if (labels.includes('Java_Method')) return 'java-method';
    if (labels.includes('API_Endpoint')) return 'api-endpoint';
    if (labels.includes('TS_Component')) return 'ts-component';
    if (labels.includes('TS_Function')) return 'ts-function';
    if (labels.includes('SQL_Table')) return 'sql-table';
    if (labels.includes('SQL_Procedure')) return 'sql-procedure';
    if (labels.includes('Mobile_Component')) return 'mobile-component';
    if (labels.includes('External_Dependency')) return 'external-dependency';
    return 'ts-function';
}

function getNodeIcon(labels: string[]): string {
    if (labels.includes('Java_Class')) return '☕';
    if (labels.includes('Java_Method')) return 'ƒ';
    if (labels.includes('API_Endpoint')) return '🌐';
    if (labels.includes('TS_Component')) return '⚛';
    if (labels.includes('TS_Function')) return 'λ';
    if (labels.includes('SQL_Table')) return '🗄';
    if (labels.includes('SQL_Procedure')) return '⚙';
    if (labels.includes('Mobile_Component')) return '📱';
    if (labels.includes('External_Dependency')) return '📦';
    return '◇';
}

function getEdgeColor(type: string): string {
    switch (type) {
        case 'CALLS': return '#a78bfa';
        case 'DEPENDS_ON': return '#4f8ff7';
        case 'READS_FROM': return '#34d399';
        case 'WRITES_TO': return '#fb7185';
        case 'HAS_METHOD': return '#5a6380';
        case 'IMPORTS': return '#5a6380';
        default: return '#3d4560';
    }
}

function edgeTypeRank(type: string): number {
    switch (type) {
        case 'CALLS': return 0;
        case 'CALLS_RESOLVED': return 1;
        case 'CALLS_NHOP': return 2;
        case 'DEPENDS_ON': return 3;
        case 'HAS_METHOD': return 4;
        case 'READS_FROM': return 5;
        case 'WRITES_TO': return 6;
        case 'IMPORTS': return 7;
        default: return 10;
    }
}

/* ─── Dagre Layout ─── */
function layoutGraph(nodes: Node[], edges: Edge[], direction = 'TB'): { nodes: Node[]; edges: Edge[] } {
    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: direction, nodesep: 70, ranksep: 90, marginx: 50, marginy: 50 });

    nodes.forEach((node) => {
        g.setNode(node.id, { width: 170, height: 60 });
    });
    edges.forEach((edge) => {
        g.setEdge(edge.source, edge.target);
    });

    dagre.layout(g);

    const laidOut = nodes.map((node) => {
        const pos = g.node(node.id);
        return {
            ...node,
            position: { x: pos.x - 85, y: pos.y - 30 },
        };
    });

    return { nodes: laidOut, edges };
}

/* ─── Custom Node Component ─── */
function CustomNode({ data }: NodeProps) {
    const hiddenHandleStyle: React.CSSProperties = {
        opacity: 0,
        pointerEvents: 'none',
        width: 1,
        height: 1,
        border: 'none',
        background: 'transparent',
    };

    if (data.isCluster) {
        return (
            <>
                <Handle type="target" position={Position.Top} style={hiddenHandleStyle} isConnectable={false} />
                <div 
                  className="custom-node cluster-node" 
                  style={{ 
                    background: '#1e293b', color: '#cbd5e1', fontSize: '1rem', 
                    padding: '16px', borderRadius: '12px', textAlign: 'center', 
                    border: '2px dashed #475569', boxShadow: '0 8px 16px rgba(0,0,0,0.4)',
                    minWidth: '150px',
                    cursor: 'pointer',
                  }}
                >
                    <div style={{ fontWeight: 'bold' }}>📦 {String(data.label)}</div>
                    <div style={{ fontSize: '0.8rem', opacity: 0.7, marginTop: '4px' }}>{Number(data.count)} items inside</div>
                    <div style={{ fontSize: '0.7rem', color: '#60a5fa', marginTop: '4px' }}>Double-click to expand</div>
                </div>
                <Handle type="source" position={Position.Bottom} style={hiddenHandleStyle} isConnectable={false} />
            </>
        );
    }

    const nodeClass = data.nodeClass as string;
    const highlightClass = data.highlightClass as string;

    let inlineStyle: React.CSSProperties = {};
    if (data.isHeatmap) {
        if (typeof data.complexity === 'number') {
            const c = data.complexity;
            if (c > 20) inlineStyle = { background: 'rgba(239,68,68,0.2)', borderColor: '#ef4444', color: '#fff' };
            else if (c >= 10) inlineStyle = { background: 'rgba(249,115,22,0.2)', borderColor: '#f97316', color: '#fff' };
            else if (c >= 5) inlineStyle = { background: 'rgba(234,179,8,0.2)', borderColor: '#eab308', color: '#fff' };
            else if (c >= 1) inlineStyle = { background: 'rgba(59,130,246,0.2)', borderColor: '#3b82f6', color: '#fff' };
            else inlineStyle = { background: 'rgba(100,116,139,0.2)', borderColor: '#64748b', color: '#fff' };
        } else {
            inlineStyle = { background: 'rgba(100,116,139,0.2)', borderColor: '#64748b', color: '#fff' };
        }
    }

    // AI Highlight style overrides everything
    if (highlightClass === 'highlighted-ai') {
        inlineStyle = { 
            background: 'rgba(244,114,182,0.2)', 
            borderColor: '#f472b6', 
            color: '#fff',
            boxShadow: '0 0 15px rgba(244,114,182,0.5)'
        };
    } else if (data.status === 'deleted') {
        inlineStyle = {
            background: 'rgba(239, 68, 68, 0.4)', // red-500 stronger
            borderColor: '#ef4444',
            color: '#fff',
            textDecoration: 'line-through',
            fontWeight: 'bold'
        };
    } else if (typeof data.impact_distance === 'number') {
        const impactOpacity = typeof data.impactOpacity === 'number' ? data.impactOpacity : 1;
        const backgroundAlpha = Math.min(0.5, 0.25 + (impactOpacity * 0.5));

        if (data.impact_distance === 1) {
            // Direct impact
            inlineStyle = {
                background: `rgba(249, 115, 22, ${backgroundAlpha})`,
                borderColor: '#f97316',
                color: '#1f2937',
                boxShadow: `0 0 15px rgba(249, 115, 22, ${backgroundAlpha})`,
                fontWeight: 'bold'
            };
        } else {
            // Indirect impact
            inlineStyle = {
                background: `rgba(234, 179, 8, ${backgroundAlpha})`,
                borderColor: '#eab308',
                color: '#1f2937',
                boxShadow: `0 0 12px rgba(234, 179, 8, ${backgroundAlpha})`,
                fontWeight: 'bold'
            };
        }
    }

    const nodeOpacity = typeof data.dimmed === 'number' ? data.dimmed : data.dimmed ? 0.2 : 1;
    if (nodeOpacity !== 1) {
        inlineStyle = { ...inlineStyle, opacity: nodeOpacity };
    }

    return (
        <>
            <Handle type="target" position={Position.Top} style={hiddenHandleStyle} isConnectable={false} />
            <div className={`custom-node ${nodeClass} ${highlightClass || ''}`} style={{ ...inlineStyle, cursor: 'pointer' }}>
                <div>
                    {String(data.icon || '')} {String(data.label || '')}
                </div>
                {data.sublabel ? <div className="node-sublabel">{String(data.sublabel)}</div> : null}
            </div>
            <Handle type="source" position={Position.Bottom} style={hiddenHandleStyle} isConnectable={false} />
        </>
    );
}

const nodeTypes = { custom: CustomNode };

/* ─── Inner Canvas Component ─── */
interface GraphCanvasProps {
    graphNodes: GraphNode[];
    graphEdges: GraphEdge[];
    highlightedUpstream: Set<string>;
    highlightedDownstream: Set<string>;
    aiHighlightedNodes: string[];
    selectedNodeKey: string | null;
    onNodeClick: (nodeKey: string, nodeData: GraphNode) => void;
    onClearAiHighlights?: () => void;
    searchTerm: string;
}

function GraphCanvasInner({
    graphNodes,
    graphEdges,
    highlightedUpstream,
    highlightedDownstream,
    aiHighlightedNodes,
    selectedNodeKey,
    onNodeClick,
    onClearAiHighlights,
    searchTerm,
}: GraphCanvasProps) {
    const [heatmapEnabled, setHeatmapEnabled] = useState(false);
    const [viewMode, setViewMode] = useState<'2d' | '3d'>('2d');
    const [autoMode, setAutoMode] = useState(true);
    const [clustered3D, setClustered3D] = useState(true);
    const [focusRequestId, setFocusRequestId] = useState(0);
    
    // Clustering state (set of expanded layer sizes). Auto-expand small graphs.
    const [expandedClusters, setExpandedClusters] = useState<Set<string>>(new Set());
    const initialLoadRef = useRef(false);

    useEffect(() => {
        if (graphNodes.length > 0 && !initialLoadRef.current) {
            initialLoadRef.current = true;
            if (graphNodes.length < 150) {
                setExpandedClusters(new Set(['*ALL*']));
            }
        }
    }, [graphNodes]);

    useEffect(() => {
        // Restore persisted preferences once
        try {
            const mode = localStorage.getItem('ig:viewMode');
            const auto = localStorage.getItem('ig:autoMode');
            const cluster3d = localStorage.getItem('ig:clustered3D');
            if (mode === '2d' || mode === '3d') setViewMode(mode);
            if (auto === 'true' || auto === 'false') setAutoMode(auto === 'true');
            if (cluster3d === 'true' || cluster3d === 'false') setClustered3D(cluster3d === 'true');
        } catch {
            // ignore storage errors
        }
    }, []);

    useEffect(() => {
        try {
            localStorage.setItem('ig:viewMode', viewMode);
            localStorage.setItem('ig:autoMode', String(autoMode));
            localStorage.setItem('ig:clustered3D', String(clustered3D));
        } catch {
            // ignore storage errors
        }
    }, [viewMode, autoMode, clustered3D]);

    useEffect(() => {
        if (!autoMode) return;
        // Auto switch: above 550 nodes prefer 3D, else keep 2D.
        if (graphNodes.length > 550 && viewMode !== '3d') setViewMode('3d');
        if (graphNodes.length <= 550 && viewMode !== '2d') setViewMode('2d');
    }, [graphNodes.length, autoMode, viewMode]);

    // Auto-expand clusters if AI points to them
    useEffect(() => {
        if (aiHighlightedNodes.length > 0) {
            setExpandedClusters(prev => {
                const next = new Set(prev);
                aiHighlightedNodes.forEach(nk => {
                    const node = graphNodes.find(n => n.namespace_key === nk);
                    if (node && node.layer) next.add(node.layer);
                });
                return next;
            });
        }
    }, [aiHighlightedNodes, graphNodes]);

    // Build the graph payload dynamically observing expanded clusters
    const { baseNodes, baseEdges } = useMemo(() => {
        if (viewMode === '3d') {
            return { baseNodes: [], baseEdges: [] };
        }
        const filteredNodes = searchTerm
            ? graphNodes.filter((n) => n.name.toLowerCase().includes(searchTerm.toLowerCase()))
            : graphNodes;

        const impactDistances = graphNodes
            .map((n) => (typeof n.impact_distance === 'number' ? n.impact_distance : undefined))
            .filter((d): d is number => typeof d === 'number');
        const hasImpactDistance = impactDistances.length > 0;
        const maxImpactDistance = hasImpactDistance ? Math.max(...impactDistances) : 0;

        const computeBlastOpacity = (distance: number) => {
            if (!hasImpactDistance || maxImpactDistance <= 1) return 1;
            const min = 0.25;
            const max = 1;
            const t = (maxImpactDistance - distance) / (maxImpactDistance - 1);
            return Math.max(min, Math.min(max, min + t * (max - min)));
        };

        if (filteredNodes.length === 0) return { baseNodes: [], baseEdges: [] };

        const nsNodes: Node[] = [];
        const nsEdges: Edge[] = [];
        const clusterMap = new Map<string, Node>();
        
        const forceExpandAll = expandedClusters.has('*ALL*');

        filteredNodes.forEach((gn) => {
            const clusterId = gn.layer || gn.project || 'System';
            
            let highlightClass = '';
            if (aiHighlightedNodes.includes(gn.namespace_key)) highlightClass = 'highlighted-ai';
            else if (gn.namespace_key === selectedNodeKey) highlightClass = 'selected-node';
            else if (highlightedUpstream.has(gn.namespace_key)) highlightClass = 'highlighted-upstream';
            else if (highlightedDownstream.has(gn.namespace_key)) highlightClass = 'highlighted-downstream';

            const isImpactedNode = typeof gn.impact_distance === 'number' && gn.impact_distance > 0;
            const impactOpacity = isImpactedNode ? computeBlastOpacity(gn.impact_distance!) : undefined;

            const dimsOther = aiHighlightedNodes.length > 0 && highlightClass === ''
                ? 0.4
                : hasImpactDistance && highlightClass === ''
                    ? (typeof impactOpacity === 'number' ? impactOpacity : 0.1)
                    : false;

            if (forceExpandAll || expandedClusters.has(clusterId)) {
                nsNodes.push({
                    id: gn.namespace_key,
                    type: 'custom',
                    position: { x: 0, y: 0 },
                    data: {
                        label: gn.name,
                        icon: getNodeIcon(gn.labels),
                        sublabel: gn.file || '',
                        nodeClass: getNodeClass(gn.labels),
                        highlightClass,
                        isHeatmap: heatmapEnabled,
                        complexity: gn.complexity,
                        dimmed: dimsOther,
                        status: gn.status,
                        impact_distance: gn.impact_distance,
                        impactOpacity,
                    },
                });
            } else {
                if (!clusterMap.has(clusterId)) {
                    clusterMap.set(clusterId, {
                        id: `cluster:${clusterId}`,
                        type: 'custom',
                        position: { x: 0, y: 0 },
                        data: {
                            label: clusterId,
                            isCluster: true,
                            count: 1,
                            clusterId: clusterId,
                            status: gn.status
                        }
                    });
                } else {
                    const c = clusterMap.get(clusterId)!;
                    c.data.count = (c.data.count as number) + 1;
                    if (gn.status === 'deleted' || (gn.status === 'impacted' && c.data.status !== 'deleted')) {
                        c.data.status = gn.status;
                    }
                }
            }
        });

        // Add cluster placeholders
        clusterMap.forEach(v => nsNodes.push(v));

        // Maps edges down safely mapping intra-cluster to themselves (which we drop)
        const dedupByType = new Map<string, { source: string; target: string; relType: string }>();
        graphEdges.forEach((ge) => {
            const srcNode = filteredNodes.find(n => n.namespace_key === ge.source);
            const tgtNode = filteredNodes.find(n => n.namespace_key === ge.target);
            if (!srcNode || !tgtNode) return;

            const srcCluster = srcNode.layer || srcNode.project || 'System';
            const tgtCluster = tgtNode.layer || tgtNode.project || 'System';

            const srcId = forceExpandAll || expandedClusters.has(srcCluster) ? ge.source : `cluster:${srcCluster}`;
            const tgtId = forceExpandAll || expandedClusters.has(tgtCluster) ? ge.target : `cluster:${tgtCluster}`;

            if (srcId === tgtId) return; // Drop self-loops

            const edgeKey = `${srcId}::${tgtId}::${ge.type}`;
            if (!dedupByType.has(edgeKey)) {
                dedupByType.set(edgeKey, { source: srcId, target: tgtId, relType: ge.type });
            }
        });

        // Spread parallel edges between same (source,target) so they don't overlap.
        const byPair = new Map<string, Array<{ source: string; target: string; relType: string }>>();
        for (const edge of dedupByType.values()) {
            const pair = `${edge.source}::${edge.target}`;
            if (!byPair.has(pair)) byPair.set(pair, []);
            byPair.get(pair)!.push(edge);
        }

        let edgeCounter = 0;
        for (const list of byPair.values()) {
            const ordered = [...list].sort((a, b) => edgeTypeRank(a.relType) - edgeTypeRank(b.relType));
            const total = ordered.length;
            ordered.forEach((e, idx) => {
                const centered = idx - (total - 1) / 2;
                const offset = 22 + Math.abs(centered) * 14;
                nsEdges.push({
                    id: `e-${edgeCounter++}`,
                    source: e.source,
                    target: e.target,
                    type: 'smoothstep',
                    label: e.relType,
                    animated: e.relType === 'CALLS' || e.relType === 'CALLS_RESOLVED',
                    pathOptions: {
                        offset,
                        borderRadius: 16,
                    } as any,
                    style: {
                        stroke: getEdgeColor(e.relType),
                        strokeWidth: e.relType === 'CALLS' || e.relType === 'CALLS_RESOLVED' ? 2.0 : 1.4,
                        opacity: 0.95,
                        strokeDasharray: e.relType === 'IMPORTS' ? '4 4' : undefined,
                    },
                    labelStyle: { fontSize: 9, fill: '#8b93b0' },
                    labelBgStyle: { fill: '#0c1024', fillOpacity: 0.88 },
                    labelBgPadding: [4, 2] as [number, number],
                    markerEnd: { type: MarkerType.ArrowClosed, color: getEdgeColor(e.relType), width: 14, height: 14 },
                } as Edge);
            });
        }

        if (nsNodes.length > 0) {
            const laid = layoutGraph(nsNodes, nsEdges);
            return { baseNodes: laid.nodes, baseEdges: laid.edges };
        }
        return { baseNodes: nsNodes, baseEdges: nsEdges };

    }, [graphNodes, graphEdges, expandedClusters, searchTerm, viewMode]); // ONLY structural dependencies

    const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

    // Visually update nodes and edges when soft properties change (bypassing heavy layout computation)
    useEffect(() => {
        setNodes((currentNodes) => {
            return baseNodes.map(bn => {
                const existing = currentNodes.find(n => n.id === bn.id);
                
                if (bn.data.isCluster) {
                    return existing && existing.position.x === bn.position.x && existing.position.y === bn.position.y 
                        ? existing 
                        : bn;
                }

                let highlightClass = '';
                if (aiHighlightedNodes.includes(bn.id)) highlightClass = 'highlighted-ai';
                else if (bn.id === selectedNodeKey) highlightClass = 'selected-node';
                else if (highlightedUpstream.has(bn.id)) highlightClass = 'highlighted-upstream';
                else if (highlightedDownstream.has(bn.id)) highlightClass = 'highlighted-downstream';

                const baseDimmed = bn.data.dimmed;
                const dimsOther = aiHighlightedNodes.length > 0 && highlightClass === ''
                    ? 0.4
                    : highlightClass === ''
                        ? baseDimmed
                        : false;

                const newData = { ...bn.data, highlightClass, isHeatmap: heatmapEnabled, dimmed: dimsOther };

                if (existing) {
                    // Se apenas os dados visuais mudaram, preserve o node inteiro (posição atual do drag, etc) e só mude 'data'
                    if (
                        existing.data.highlightClass === highlightClass && 
                        existing.data.isHeatmap === heatmapEnabled && 
                        existing.data.dimmed === dimsOther &&
                        existing.position.x === bn.position.x &&
                        existing.position.y === bn.position.y
                    ) {
                        return existing;
                    }
                    // Preserva a instância do React Flow, mas injeta o novo data
                    return { ...existing, data: newData, position: bn.position };
                }
                
                return { ...bn, data: newData };
            });
        });

        setEdges((currentEdges) => {
            return baseEdges.map(be => {
                let opacity = 1;
                if (aiHighlightedNodes.length > 0) {
                    opacity = aiHighlightedNodes.includes(be.source) || aiHighlightedNodes.includes(be.target) ? 1 : 0.4;
                }
                
                const existing = currentEdges.find(e => e.id === be.id);
                if (existing) {
                    if (existing.style?.opacity === opacity) return existing;
                    return { ...existing, style: { ...(existing.style || {}), opacity } };
                }
                
                return { ...be, style: { ...(be.style || {}), opacity } };
            });
        });
    }, [baseNodes, baseEdges, selectedNodeKey, aiHighlightedNodes, highlightedUpstream, highlightedDownstream, heatmapEnabled, setNodes, setEdges]);
    
    // NOTE: Removed auto-fit behavior to preserve user viewport context.

    const handleNodeDoubleClick = useCallback(
        (_: React.MouseEvent, node: Node) => {
            if (node.id.startsWith('cluster:')) {
                const clusterId = node.data.clusterId as string;
                setExpandedClusters(prev => {
                    const next = new Set(prev);
                    next.add(clusterId);
                    return next;
                });
            }
        },
        []
    );

    const handleNodeClick = useCallback(
        (_: React.MouseEvent, node: Node) => {
            if (!node.id.startsWith('cluster:')) {
                const gn = graphNodes.find((n) => n.namespace_key === node.id);
                if (gn) onNodeClick(node.id, gn);
            }
        },
        [graphNodes, onNodeClick]
    );

    if (graphNodes.length === 0) {
        return (
            <div className="canvas-area">
                <div className="empty-state">
                    <div className="empty-state-icon">◆</div>
                    <div className="empty-state-title">InsightGraph</div>
                    <div className="empty-state-text">
                        A plataforma de inteligência de arquitetura 100% local.
                        <br />
                        Utilize o campo de workspace para dar inicio ao rastreamento AST + Neo4j.
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="canvas-area">
            {viewMode === '2d' ? (
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onNodeClick={handleNodeClick}
                    onNodeDoubleClick={handleNodeDoubleClick}
                    nodeTypes={nodeTypes}
                    fitView
                    fitViewOptions={{ padding: 0.25 }}
                    minZoom={0.05}
                    maxZoom={2.5}
                    proOptions={{ hideAttribution: true }}
                >
                    <Controls />
                    <MiniMap
                        nodeColor={(n) => {
                            if (n.data.isCluster) return '#60a5fa';
                            if (n.data.highlightClass === 'highlighted-ai') return '#f472b6';
                            const cls = (n.data as Record<string, unknown>).nodeClass as string;
                            if (cls?.includes('java')) return '#fb923c';
                            if (cls?.includes('ts')) return '#60a5fa';
                            if (cls?.includes('sql')) return '#34d399';
                            if (cls?.includes('mobile')) return '#a78bfa';
                            return '#5a6380';
                        }}
                        maskColor="rgba(6, 8, 26, 0.75)"
                    />
                    <Background variant={BackgroundVariant.Dots} gap={28} size={1} color="rgba(139,147,176,0.04)" />
                </ReactFlow>
            ) : (
                <GraphCanvas3D
                    graphNodes={graphNodes}
                    graphEdges={graphEdges}
                    highlightedUpstream={highlightedUpstream}
                    highlightedDownstream={highlightedDownstream}
                    aiHighlightedNodes={aiHighlightedNodes}
                    selectedNodeKey={selectedNodeKey}
                    onNodeClick={onNodeClick}
                    searchTerm={searchTerm}
                    heatmapEnabled={heatmapEnabled}
                    clustered={clustered3D}
                    focusNodeKey={selectedNodeKey}
                    focusRequestId={focusRequestId}
                />
            )}

            {/* Overlays */}
            <div className="canvas-controls">
                <button
                  className={`btn ${viewMode === '3d' ? 'btn-accent' : 'btn-secondary'}`}
                  onClick={() => {
                      setAutoMode(false);
                      setViewMode(viewMode === '2d' ? '3d' : '2d');
                  }}
                  style={{ boxShadow: '0 4px 12px rgba(0,0,0,0.2)' }}
                >
                    {viewMode === '2d' ? '🌐 Modo 3D' : '🗺️ Modo 2D'}
                </button>
                <button
                  className={`btn ${autoMode ? 'btn-accent' : 'btn-secondary'}`}
                  onClick={() => setAutoMode((v) => !v)}
                  style={{ boxShadow: '0 4px 12px rgba(0,0,0,0.2)' }}
                  title="Alterna fallback automático 2D/3D por volume de nós"
                >
                    {autoMode ? '⚙️ Auto ON' : '⚙️ Auto OFF'}
                </button>
                {viewMode === '3d' && (
                    <button
                      className={`btn ${clustered3D ? 'btn-accent' : 'btn-secondary'}`}
                      onClick={() => setClustered3D((v) => !v)}
                      style={{ boxShadow: '0 4px 12px rgba(0,0,0,0.2)' }}
                      title="Agrupa nós por camada/projeto no modo 3D"
                    >
                        {clustered3D ? '🧩 Cluster 3D ON' : '🧩 Cluster 3D OFF'}
                    </button>
                )}
                {viewMode === '3d' && selectedNodeKey && (
                    <button
                      className="btn btn-secondary"
                      onClick={() => setFocusRequestId((v) => v + 1)}
                      style={{ boxShadow: '0 4px 12px rgba(0,0,0,0.2)' }}
                      title="Move a câmera para o nó selecionado"
                    >
                        🎯 Centrar Selecionado
                    </button>
                )}
                <button 
                  className={`btn ${heatmapEnabled ? 'btn-accent' : 'btn-secondary'}`}
                  onClick={() => setHeatmapEnabled(!heatmapEnabled)}
                  style={{ boxShadow: '0 4px 12px rgba(0,0,0,0.2)' }}
                >
                    🔥 Mapa de Risco (Heatmap)
                </button>

                {aiHighlightedNodes.length > 0 && onClearAiHighlights && (
                    <button
                      className="btn btn-secondary"
                      onClick={onClearAiHighlights}
                    >
                      Limpar Destaque
                    </button>
                )}

                {viewMode === '2d' && expandedClusters.size > 0 && !expandedClusters.has('*ALL*') && (
                    <button 
                      className="btn btn-secondary"
                      onClick={() => setExpandedClusters(new Set())}
                    >
                        Esconder Módulos
                    </button>
                )}
            </div>

            {heatmapEnabled && (
                <div className="legend-heatmap">
                    <div className="legend-heatmap-title">Níveis de Risco (Heatmap)</div>
                    <div className="legend-heatmap-item">
                        <div className="legend-heatmap-color" style={{ background: '#ef4444' }} />
                        <span>Crítico (Complexidade &gt; 20)</span>
                    </div>
                    <div className="legend-heatmap-item">
                        <div className="legend-heatmap-color" style={{ background: '#f59e0b' }} />
                        <span>Alto (10 - 20)</span>
                    </div>
                    <div className="legend-heatmap-item">
                        <div className="legend-heatmap-color" style={{ background: '#eab308' }} />
                        <span>Médio (5 - 9)</span>
                    </div>
                    <div className="legend-heatmap-item">
                        <div className="legend-heatmap-color" style={{ background: '#3b82f6' }} />
                        <span>Baixo (1 - 4)</span>
                    </div>
                    <div className="legend-heatmap-item">
                        <div className="legend-heatmap-color" style={{ background: '#9ca3af' }} />
                        <span>Desconhecido / N/A</span>
                    </div>
                </div>
            )}

            <div className="legend">
                <div className="legend-title">Tipos de Conexão</div>
                {[
                    { type: 'CALLS', color: '#a78bfa' },
                    { type: 'DEPENDS_ON', color: '#4f8ff7' },
                    { type: 'READS_FROM', color: '#34d399' },
                    { type: 'WRITES_TO', color: '#fb7185' },
                    { type: 'HAS_METHOD', color: '#5a6380' },
                ].map((e) => (
                    <div key={e.type} className="legend-item">
                        <div style={{ width: 18, height: 2, background: e.color, borderRadius: 1 }} />
                        {e.type}
                    </div>
                ))}
                <div className="legend-title" style={{ marginTop: 8 }}>Tipos de Nó</div>
                {[
                    { type: 'Classe Java', color: '#fb923c' },
                    { type: 'Método Java', color: '#fdba74' },
                    { type: 'API Endpoint', color: '#67e8f9' },
                    { type: 'Componente TS', color: '#60a5fa' },
                    { type: 'Função TS', color: '#93c5fd' },
                    { type: 'Tabela SQL', color: '#34d399' },
                    { type: 'Procedure SQL', color: '#6ee7b7' },
                ].map((e) => (
                    <div key={e.type} className="legend-item">
                        <div style={{ width: 10, height: 10, background: e.color, borderRadius: 999 }} />
                        {e.type}
                    </div>
                ))}
                <div className="legend-title" style={{ marginTop: 8 }}>Cores de Impacto</div>
                {[
                    { type: 'Selecionado', color: '#facc15' },
                    { type: 'Upstream', color: '#22c55e' },
                    { type: 'Downstream', color: '#f97316' },
                    { type: 'Destaque IA/Simulação', color: '#f472b6' },
                    { type: 'Deletado', color: '#ef4444' },
                ].map((e) => (
                    <div key={e.type} className="legend-item">
                        <div style={{ width: 10, height: 10, background: e.color, borderRadius: 999 }} />
                        {e.type}
                    </div>
                ))}
            </div>
        </div>
    );
}

/* ─── Main Export Component with Provider ─── */
export default function GraphCanvas(props: GraphCanvasProps) {
    return (
        <ReactFlowProvider>
            <GraphCanvasInner {...props} />
        </ReactFlowProvider>
    );
}
