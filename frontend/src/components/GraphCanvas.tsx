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
    useReactFlow,
} from '@xyflow/react';
import type { Node, Edge, NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from '@dagrejs/dagre';
import type { GraphNode, GraphEdge } from '../api';

/* ─── Helpers ─── */
function getNodeClass(labels: string[]): string {
    if (labels.includes('Java_Class')) return 'java-class';
    if (labels.includes('Java_Method')) return 'java-method';
    if (labels.includes('TS_Component')) return 'ts-component';
    if (labels.includes('TS_Function')) return 'ts-function';
    if (labels.includes('SQL_Table')) return 'sql-table';
    if (labels.includes('SQL_Procedure')) return 'sql-procedure';
    if (labels.includes('Mobile_Component')) return 'mobile-component';
    return 'ts-function';
}

function getNodeIcon(labels: string[]): string {
    if (labels.includes('Java_Class')) return '☕';
    if (labels.includes('Java_Method')) return 'ƒ';
    if (labels.includes('TS_Component')) return '⚛';
    if (labels.includes('TS_Function')) return 'λ';
    if (labels.includes('SQL_Table')) return '🗄';
    if (labels.includes('SQL_Procedure')) return '⚙';
    if (labels.includes('Mobile_Component')) return '📱';
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
    if (data.isCluster) {
        return (
            <>
                <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
                <div 
                  className="custom-node cluster-node" 
                  style={{ 
                    background: '#1e293b', color: '#cbd5e1', fontSize: '1rem', 
                    padding: '16px', borderRadius: '12px', textAlign: 'center', 
                    border: '2px dashed #475569', boxShadow: '0 8px 16px rgba(0,0,0,0.4)',
                    minWidth: '150px'
                  }}
                >
                    <div style={{ fontWeight: 'bold' }}>📦 {String(data.label)}</div>
                    <div style={{ fontSize: '0.8rem', opacity: 0.7, marginTop: '4px' }}>{Number(data.count)} items inside</div>
                    <div style={{ fontSize: '0.7rem', color: '#60a5fa', marginTop: '4px' }}>Double-click to expand</div>
                </div>
                <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
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
    } else if (data.status === 'impacted') {
        inlineStyle = {
            background: 'rgba(249, 115, 22, 0.4)', // orange-500 stronger
            borderColor: '#f97316',
            color: '#fff',
            boxShadow: '0 0 15px rgba(249, 115, 22, 0.5)',
            fontWeight: 'bold'
        };
    } else if (data.dimmed && highlightClass === '') {
        inlineStyle = { opacity: 0.2 };
    }

    return (
        <>
            <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
            <div className={`custom-node ${nodeClass} ${highlightClass || ''}`} style={inlineStyle}>
                <div>
                    {String(data.icon || '')} {String(data.label || '')}
                </div>
                {data.sublabel ? <div className="node-sublabel">{String(data.sublabel)}</div> : null}
            </div>
            <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
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
    searchTerm,
}: GraphCanvasProps) {
    const rf = useReactFlow();
    const [heatmapEnabled, setHeatmapEnabled] = useState(false);
    
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
        const filteredNodes = searchTerm
            ? graphNodes.filter((n) => n.name.toLowerCase().includes(searchTerm.toLowerCase()))
            : graphNodes;

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

            const dimsOther = aiHighlightedNodes.length > 0 && highlightClass === '';

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
                        status: gn.status
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
        const builtEdges = new Set<string>();
        graphEdges.forEach((ge, i) => {
            const srcNode = filteredNodes.find(n => n.namespace_key === ge.source);
            const tgtNode = filteredNodes.find(n => n.namespace_key === ge.target);
            if (!srcNode || !tgtNode) return;

            const srcCluster = srcNode.layer || srcNode.project || 'System';
            const tgtCluster = tgtNode.layer || tgtNode.project || 'System';

            const srcId = forceExpandAll || expandedClusters.has(srcCluster) ? ge.source : `cluster:${srcCluster}`;
            const tgtId = forceExpandAll || expandedClusters.has(tgtCluster) ? ge.target : `cluster:${tgtCluster}`;

            if (srcId === tgtId) return; // Drop self-loops

            const edgeKey = `${srcId}-${tgtId}-${ge.type}`;
            if (!builtEdges.has(edgeKey)) {
                builtEdges.add(edgeKey);

                nsEdges.push({
                    id: `e-${i}`,
                    source: srcId,
                    target: tgtId,
                    label: ge.type,
                    animated: ge.type === 'CALLS',
                    style: { stroke: getEdgeColor(ge.type), strokeWidth: 1.5, opacity: 1 },
                    labelStyle: { fontSize: 9, fill: '#8b93b0' },
                    labelBgStyle: { fill: '#0c1024', fillOpacity: 0.9 },
                    markerEnd: { type: MarkerType.ArrowClosed, color: getEdgeColor(ge.type), width: 16, height: 16 },
                });
            }
        });

        if (nsNodes.length > 0) {
            const laid = layoutGraph(nsNodes, nsEdges);
            return { baseNodes: laid.nodes, baseEdges: laid.edges };
        }
        return { baseNodes: nsNodes, baseEdges: nsEdges };

    }, [graphNodes, graphEdges, expandedClusters, searchTerm]); // ONLY structural dependencies

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

                const dimsOther = aiHighlightedNodes.length > 0 && highlightClass === '';
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
                    opacity = aiHighlightedNodes.includes(be.source) || aiHighlightedNodes.includes(be.target) ? 1 : 0.15;
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
    
    // Auto-fit AI nodes
    useEffect(() => {
        if (aiHighlightedNodes.length > 0 && nodes.length > 0) {
            setTimeout(() => {
                const aiNodes = nodes.filter(n => aiHighlightedNodes.includes(n.id));
                if (aiNodes.length > 0) {
                    rf.fitView({ nodes: aiNodes, duration: 800, padding: 3 });
                }
            }, 100);
        }
    }, [aiHighlightedNodes, nodes, rf]);

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

            {/* Overlays */}
            <div style={{ position: 'absolute', top: 16, right: 16, zIndex: 5, display: 'flex', gap: '8px' }}>
                <button 
                  className={`btn ${heatmapEnabled ? 'btn-accent' : 'btn-secondary'}`}
                  onClick={() => setHeatmapEnabled(!heatmapEnabled)}
                  style={{ boxShadow: '0 4px 12px rgba(0,0,0,0.2)' }}
                >
                    🔥 Mapa de Risco (Heatmap)
                </button>
                {expandedClusters.size > 0 && !expandedClusters.has('*ALL*') && (
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
