import { useState, useCallback, useMemo, useEffect, useRef, forwardRef, useImperativeHandle, ForwardedRef } from 'react';
import {
    ReactFlow,
    Controls,
    Background,
    useNodesState,
    useEdgesState,
    Handle,
    Position,
    MarkerType,
    BackgroundVariant,
    ReactFlowProvider,
} from '@xyflow/react';
import type { Node, Edge, NodeProps, ReactFlowInstance } from '@xyflow/react';
import type { Viewport } from '@xyflow/system';
import '@xyflow/react/dist/style.css';
import dagre from '@dagrejs/dagre';
import type { GraphNode, GraphEdge } from '../api';
import { fetchGraphPath, fetchInheritance } from '../api';
import GraphCanvas3D from './GraphCanvas3D';
import { getHeatmapColor, hotspotColorScale } from '../utils/graphColors';

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
                    background: '#0f172a',
                    color: '#e2e8f0',
                    fontSize: '0.9rem',
                    padding: '18px',
                    borderRadius: '14px',
                    textAlign: 'center',
                    border: `2px dashed ${data.hotspotColor || '#475569'}`,
                    boxShadow: '0 10px 28px rgba(0,0,0,0.45)',
                    minWidth: '170px',
                    cursor: 'pointer',
                    position: 'relative',
                  }}
                >
                    <div style={{ fontWeight: '700', letterSpacing: '0.04em' }}>
                        {String(data.clusterLabel || data.label)}
                    </div>
                    <div style={{ marginTop: 6, fontSize: '0.75rem', opacity: 0.75 }}>
                        {Number(data.count)} nós agrupados
                    </div>
                    <div style={{ marginTop: 6, display: 'flex', justifyContent: 'center', gap: 8, alignItems: 'center' }}>
                        <span
                          style={{
                              width: 10,
                              height: 10,
                              borderRadius: 6,
                              background: data.hotspotColor || '#475569',
                              boxShadow: `0 0 10px ${data.hotspotColor || '#475569'}`,
                          }}
                        />
                        <span style={{ fontSize: '0.7rem', opacity: 0.7 }}>hotspot médio</span>
                    </div>
                    <div style={{ fontSize: '0.7rem', color: '#60a5fa', marginTop: '6px' }}>Clique para expandir</div>
                </div>
                <Handle type="source" position={Position.Bottom} style={hiddenHandleStyle} isConnectable={false} />
            </>
        );
    }

    const nodeClass = data.nodeClass as string;
    const highlightClass = data.highlightClass as string;

    let inlineStyle: React.CSSProperties = {};
    if (data.isHeatmap) {
        const color = getHeatmapColor(data.complexity);
        inlineStyle = {
            ...inlineStyle,
            boxShadow: `0 0 18px ${color}80`,
            borderColor: `${color}`,
        };
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
                {data.hasAnnotation && (
                    <span
                        className="annotation-dot"
                        style={{ background: data.annotationColor || '#60a5fa' }}
                        title={data.annotationTag ? `Tag: ${data.annotationTag}` : 'Anotação disponível'}
                    />
                )}
            </div>
            <Handle type="source" position={Position.Bottom} style={hiddenHandleStyle} isConnectable={false} />
        </>
    );
}

const nodeTypes = { custom: CustomNode };

export interface SavedNodeState {
    id: string;
    position: { x: number; y: number };
}

export interface SavedViewState {
    nodes: SavedNodeState[];
    viewport: Viewport;
}

export interface GraphCanvasHandle {
    captureViewState: () => SavedViewState;
    applyViewState: (state: SavedViewState) => void;
}

/* ─── Inner Canvas Component ─── */
interface GraphCanvasProps {
    graphNodes: GraphNode[];
    graphEdges: GraphEdge[];
    highlightedUpstream: Set<string>;
    highlightedDownstream: Set<string>;
    aiHighlightedNodes: string[];
    selectedNodeKey: string | null;
    onNodeClick: (nodeKey: string, nodeData: GraphNode, screenPosition?: { x: number; y: number }) => void;
    onClearAiHighlights?: () => void;
    searchTerm: string;
    nodeAnnotations?: Map<string, { tag?: string; color?: string | null }>;
    selectedTag?: string | null;
    tagFilterNodes?: Set<string>;
    onCanvasClick?: () => void;
}

const GraphCanvasInnerImpl = (props: GraphCanvasProps, ref: ForwardedRef<GraphCanvasHandle>) => {
    const {
        graphNodes,
        graphEdges,
        highlightedUpstream,
        highlightedDownstream,
        aiHighlightedNodes,
        selectedNodeKey,
        onNodeClick,
        onClearAiHighlights,
        searchTerm,
        nodeAnnotations,
        selectedTag,
        tagFilterNodes,
    } = props;
    const [heatmapEnabled, setHeatmapEnabled] = useState(false);
    const [viewMode, setViewMode] = useState<'2d' | '3d'>('2d');
    const [autoMode, setAutoMode] = useState(true);
    const [clustered3D, setClustered3D] = useState(true);
    const [focusRequestId, setFocusRequestId] = useState(0);
    const [pathFinderMode, setPathFinderMode] = useState(false);
    const [pathFinderOrigin, setPathFinderOrigin] = useState<string | null>(null);
    const [pathFinderTarget, setPathFinderTarget] = useState<string | null>(null);
    const [pathFinderPaths, setPathFinderPaths] = useState<string[][]>([]);
    const [pathFinderEdgeKeys, setPathFinderEdgeKeys] = useState<Set<string>>(new Set());
    const [pathFinderLoading, setPathFinderLoading] = useState(false);
    const [pathFinderError, setPathFinderError] = useState<string | null>(null);
    const [pathFinderDepth, setPathFinderDepth] = useState(12);
    const [inheritanceMode, setInheritanceMode] = useState(false);
    const [inheritanceData, setInheritanceData] = useState<{
        nodes: Array<{ namespace_key?: string; name?: string; layer?: string; project?: string }>;
        edges: Array<{ source?: string; target?: string }>;
    } | null>(null);
    const [inheritanceLoading, setInheritanceLoading] = useState(false);
    const [inheritanceError, setInheritanceError] = useState<string | null>(null);
    
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

    useEffect(() => {
        if (!graphNodes.length && !graphEdges.length) return;
        setPathFinderPaths([]);
        setPathFinderEdgeKeys(new Set());
        setPathFinderOrigin(null);
        setPathFinderTarget(null);
        setPathFinderError(null);
    }, [graphNodes, graphEdges]);

    useEffect(() => {
        if (!inheritanceMode) {
            setInheritanceData(null);
            setInheritanceError(null);
            setInheritanceLoading(false);
            return;
        }

        if (!selectedNodeKey) {
            setInheritanceError('Selecione uma classe para ver a árvore de herança.');
            setInheritanceData(null);
            setInheritanceLoading(false);
            return;
        }

        setInheritanceLoading(true);
        setInheritanceError(null);
        fetchInheritance(undefined, selectedNodeKey)
            .then((data) => {
                setInheritanceData(data);
            })
            .catch((err) => {
                console.error('Failed to load inheritance tree:', err);
                setInheritanceError('Não foi possível recuperar a hierarquia.');
                setInheritanceData(null);
            })
            .finally(() => {
                setInheritanceLoading(false);
            });
    }, [inheritanceMode, selectedNodeKey]);

    const pathFinderNodeSet = useMemo(() => {
        const set = new Set<string>();
        pathFinderPaths.forEach((path) => {
            path.forEach((key) => set.add(key));
        });
        return set;
    }, [pathFinderPaths]);

    const nodeNameMap = useMemo(() => {
        const map = new Map<string, string>();
        graphNodes.forEach((n) => {
            if (n.namespace_key) map.set(n.namespace_key, n.name);
        });
        return map;
    }, [graphNodes]);

    const graphNodeMap = useMemo(() => {
        const map = new Map<string, GraphNode>();
        graphNodes.forEach((n) => {
            if (n.namespace_key) map.set(n.namespace_key, n);
        });
        return map;
    }, [graphNodes]);

    const inheritancePayload = useMemo(() => {
        if (!inheritanceData?.nodes?.length) {
            return null;
        }
        const resolvedNodes = inheritanceData.nodes
            .map((row) => {
                if (!row.namespace_key) return null;
                const existing = graphNodeMap.get(row.namespace_key);
                return (
                    existing || {
                        namespace_key: row.namespace_key,
                        name: row.name || row.namespace_key,
                        labels: ['Java_Class'],
                        layer: row.layer || 'Java_Class',
                        project: row.project || 'local',
                    }
                );
            })
            .filter((n): n is GraphNode => Boolean(n));

        const resolvedEdges =
            inheritanceData.edges?.map((edge, idx) => ({
                id: `inherit-${idx}`,
                source: edge.source || '',
                target: edge.target || '',
                type: 'INHERITS',
            })) || [];

        return { nodes: resolvedNodes, edges: resolvedEdges };
    }, [inheritanceData, graphNodeMap]);

    // Build the graph payload dynamically observing expanded clusters
    const { baseNodes, baseEdges, clusterSummaries, laneMeta } = useMemo(() => {
        if (viewMode === '3d') {
            return { baseNodes: [], baseEdges: [], clusterSummaries: [], laneMeta: [] };
        }

        if (inheritanceMode && inheritancePayload) {
            const treeNodes: Node[] = inheritancePayload.nodes
                .filter((node) => Boolean(node.namespace_key))
                .map((node) => {
                    const labels = (node as GraphNode).labels || ['Java_Class'];
                    const highlightClass = node.namespace_key === selectedNodeKey ? 'selected-node' : '';
                    return {
                        id: node.namespace_key ?? `inherit-${Math.random()}`,
                        type: 'custom',
                        position: { x: 0, y: 0 },
                        data: {
                            label: node.name || node.namespace_key,
                            icon: getNodeIcon(labels),
                            nodeClass: getNodeClass(labels),
                            sublabel: node.project || node.layer || '',
                            highlightClass,
                        },
                    } as Node;
                });

            const treeEdges: Edge[] = inheritancePayload.edges
                .filter((edge) => edge.source && edge.target)
                .map((edge, idx) => ({
                    id: `inherit-edge-${idx}`,
                    source: edge.source!,
                    target: edge.target!,
                    type: 'smoothstep',
                    label: 'INHERITS',
                    animated: true,
                    pathOptions: { offset: 18, borderRadius: 16 },
                    style: {
                        stroke: '#22c55e',
                        strokeWidth: 2,
                        opacity: 0.9,
                    },
                    markerEnd: { type: MarkerType.ArrowClosed, color: '#22c55e', width: 12, height: 12 },
                }));

            const laid = layoutGraph(treeNodes, treeEdges, 'LR');
            return { baseNodes: laid.nodes, baseEdges: laid.edges, clusterSummaries: [], laneMeta: [] };
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

        if (filteredNodes.length === 0) return { baseNodes: [], baseEdges: [], clusterSummaries: [], laneMeta: [] };

        const layerBuckets = new Map<string, GraphNode[]>();
        const nodeLayerLookup = new Map<string, string>();
        filteredNodes.forEach((node) => {
            const layerName = normalizeLayer(node.layer || node.labels?.[0]);
            nodeLayerLookup.set(node.namespace_key, layerName);
            if (!layerBuckets.has(layerName)) layerBuckets.set(layerName, []);
            layerBuckets.get(layerName)!.push(node);
        });

        const orderedLayers = [
            ...LAYER_ORDER_PRIORITIES.filter((layer) => layerBuckets.has(layer)),
            ...[...layerBuckets.keys()].filter((layer) => !LAYER_ORDER_PRIORITIES.includes(layer)),
        ];

        const layerIndexLookup = new Map<string, number>();
        orderedLayers.forEach((layerName, index) => layerIndexLookup.set(layerName, index));

        const collapsibleLayers = new Set<string>();
        layerBuckets.forEach((nodes, layerName) => {
            if (nodes.length > CLUSTER_THRESHOLD) collapsibleLayers.add(layerName);
        });

        const forceExpandAll = expandedClusters.has('*ALL*');

        const clusterSummaries = orderedLayers.map((layerName) => {
            const nodes = layerBuckets.get(layerName) || [];
            const sumHotspot = nodes.reduce((acc, node) => acc + (node.hotspot_score || 0), 0);
            return {
                layer: layerName,
                count: nodes.length,
                avgHotspot: nodes.length ? sumHotspot / nodes.length : 0,
            };
        });

        const summaryLookup = new Map(clusterSummaries.map((summary) => [summary.layer, summary]));
        const laneMeta = orderedLayers.map((layerName, index) => {
            const nodes = layerBuckets.get(layerName) || [];
            const summary = summaryLookup.get(layerName);
            const isCollapsible = collapsibleLayers.has(layerName);
            const isCollapsed = isCollapsible && !forceExpandAll && !expandedClusters.has(layerName);
            return {
                layer: layerName,
                index,
                count: nodes.length,
                avgHotspot: summary?.avgHotspot ?? 0,
                isCollapsible,
                isCollapsed,
            };
        });
        const laneMetaLookup = new Map(laneMeta.map((lane) => [lane.layer, lane]));

        const nsNodes: Node[] = [];
        const nsEdges: Edge[] = [];
        const clusterMap = new Map<string, Node>();

        const pushNode = (gn: GraphNode, layerName: string, layerIndex: number) => {
            const annotationMeta = nodeAnnotations?.get(gn.namespace_key);
            const matchesTagFilter = selectedTag ? (tagFilterNodes?.has(gn.namespace_key) ?? false) : false;
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
            const tagDim = selectedTag && !matchesTagFilter ? 0.2 : false;
            const dimmedValue = tagDim !== false ? tagDim : dimsOther;
            const highlightTagClass = selectedTag && matchesTagFilter ? 'highlighted-tag' : '';

            nsNodes.push({
                id: gn.namespace_key,
                type: 'custom',
                position: { x: 0, y: layerIndex * LANE_SPACING },
                data: {
                    label: gn.name,
                    icon: getNodeIcon(gn.labels),
                    sublabel: gn.file || '',
                    nodeClass: getNodeClass(gn.labels),
                    highlightClass: [highlightClass, highlightTagClass].filter(Boolean).join(' '),
                    isHeatmap: heatmapEnabled,
                    complexity: gn.complexity,
                    dimmed: dimmedValue,
                    status: gn.status,
                    impact_distance: gn.impact_distance,
                    impactOpacity,
                    annotationColor: annotationMeta ? (annotationMeta.color || '#60a5fa') : undefined,
                    annotationTag: annotationMeta?.tag,
                    hasAnnotation: Boolean(annotationMeta),
                    matchesTagFilter,
                    layerCanonical: layerName,
                    clusterLayer: layerName,
                },
            });
        };

        orderedLayers.forEach((layerName) => {
            const nodesInLayer = layerBuckets.get(layerName) || [];
            const layerIndex = layerIndexLookup.get(layerName) ?? 0;
            const laneInfo = laneMetaLookup.get(layerName);
            const isCollapsed = laneInfo ? laneInfo.isCollapsed : false;

            if (isCollapsed) {
                const representative = nodesInLayer.reduce((prev, curr) => {
                    if (!prev) return curr;
                    return (curr.hotspot_score || 0) > (prev.hotspot_score || 0) ? curr : prev;
                }, nodesInLayer[0]);
                const summary = clusterSummaries.find((cs) => cs.layer === layerName);
                clusterMap.set(`cluster:${layerName}`, {
                    id: `cluster:${layerName}`,
                    type: 'custom',
                    position: { x: 0, y: layerIndex * LANE_SPACING },
                    data: {
                        label: representative?.name || layerName,
                        clusterLabel: layerName,
                        isCluster: true,
                        count: nodesInLayer.length,
                        clusterId: layerName,
                        hotspotColor: hotspotColorScale(summary?.avgHotspot),
                        layerCanonical: layerName,
                        clusterLayer: layerName,
                        status: representative?.status,
                    },
                });
            } else {
                nodesInLayer.forEach((node) => pushNode(node, layerName, layerIndex));
            }
        });

        clusterMap.forEach((v) => nsNodes.push(v));

        // Maps edges down safely mapping intra-cluster to themselves (which we drop)
        const dedupByType = new Map<string, { source: string; target: string; relType: string }>();
        graphEdges.forEach((ge) => {
            if (!nodeLayerLookup.has(ge.source) || !nodeLayerLookup.has(ge.target)) return;
            const srcLayer = nodeLayerLookup.get(ge.source) ?? 'Other';
            const tgtLayer = nodeLayerLookup.get(ge.target) ?? 'Other';
            const srcExpanded = forceExpandAll || !collapsibleLayers.has(srcLayer) || expandedClusters.has(srcLayer);
            const tgtExpanded = forceExpandAll || !collapsibleLayers.has(tgtLayer) || expandedClusters.has(tgtLayer);

            const srcId = srcExpanded ? ge.source : `cluster:${srcLayer}`;
            const tgtId = tgtExpanded ? ge.target : `cluster:${tgtLayer}`;

            if (srcId === tgtId) return;

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
            const adjusted = laid.nodes.map((node) => {
                const laneName = node.data.clusterLayer || node.data.layerCanonical || 'Other';
                const laneIndex = layerIndexLookup.get(laneName) ?? 0;
                return {
                    ...node,
                    position: { x: node.position.x, y: laneIndex * LANE_SPACING + node.position.y },
                };
            });
            return {
                baseNodes: adjusted,
                baseEdges: laid.edges,
                clusterSummaries,
                laneMeta,
            };
        }
        return { baseNodes: nsNodes, baseEdges: nsEdges, clusterSummaries, laneMeta };

    }, [
        graphNodes,
        graphEdges,
        expandedClusters,
        searchTerm,
        viewMode,
        inheritanceMode,
        inheritancePayload,
        selectedNodeKey,
        nodeAnnotations,
        selectedTag,
        tagFilterNodes,
        aiHighlightedNodes,
        highlightedUpstream,
        highlightedDownstream,
        heatmapEnabled,
    ]);

    const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
    const reactFlowInstanceRef = useRef<ReactFlowInstance | null>(null);
    const canvasRef = useRef<HTMLDivElement>(null);
    const [viewportState, setViewportState] = useState<Viewport>({ x: 0, y: 0, zoom: 1 });

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
            if (pathFinderNodeSet.has(bn.id)) highlightClass = 'highlighted-path';

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
                const isPathEdge = pathFinderEdgeKeys.has(`${be.source}::${be.target}`);
                
                const existing = currentEdges.find(e => e.id === be.id);
                const pathStyle = isPathEdge
                    ? { stroke: '#38bdf8', strokeWidth: 3, opacity: 1 }
                    : {};
                if (existing) {
                    if (existing.style?.opacity === opacity && !isPathEdge) return existing;
                    return { ...existing, style: { ...(existing.style || {}), opacity, ...pathStyle } };
                }
                
                return { ...be, style: { ...(be.style || {}), opacity, ...pathStyle } };
            });
        });
    }, [baseNodes, baseEdges, selectedNodeKey, aiHighlightedNodes, highlightedUpstream, highlightedDownstream, heatmapEnabled, pathFinderNodeSet, pathFinderEdgeKeys, setNodes, setEdges]);
    
// NOTE: Removed auto-fit behavior to preserve user viewport context.

const LAYER_ORDER_PRIORITIES = ['Database', 'Service', 'API', 'Frontend', 'Mobile', 'External', 'Other'];
const LANE_SPACING = 220;
const CLUSTER_THRESHOLD = 30;
const CLUSTER_OVERVIEW_LIMIT = 5;

const normalizeLayer = (layer?: string): string => {
    if (!layer) return 'Other';
    const normalized = layer.toLowerCase();
    if (normalized.includes('database') || normalized.includes('sql')) return 'Database';
    if (normalized.includes('service')) return 'Service';
    if (normalized.includes('api')) return 'API';
    if (normalized.includes('frontend') || normalized.includes('ui') || normalized.includes('web')) return 'Frontend';
    if (normalized.includes('mobile')) return 'Mobile';
    if (normalized.includes('external') || normalized.includes('third')) return 'External';
    return 'Other';
};

    const captureViewState = useCallback((): SavedViewState => ({
        nodes: nodes.map((node) => ({
            id: node.id,
            position: { x: node.position.x, y: node.position.y },
        })),
        viewport: viewportState,
    }), [nodes, viewportState]);

    const applyViewState = useCallback((state: SavedViewState) => {
        if (!state?.nodes?.length) return;
        setNodes((current) =>
            current.map((node) => {
                const saved = state.nodes.find((n) => n.id === node.id);
                if (!saved) return node;
                return { ...node, position: { x: saved.position.x, y: saved.position.y } };
            })
        );
        if (state.viewport && reactFlowInstanceRef.current) {
            reactFlowInstanceRef.current.setViewport(state.viewport, { duration: 400 });
            setViewportState(state.viewport);
        }
    }, [setNodes]);

    useImperativeHandle(ref, () => ({
        captureViewState,
        applyViewState,
    }), [captureViewState, applyViewState]);

    const toggleClusterLayer = useCallback((layerName: string) => {
        setExpandedClusters((prev) => {
            const next = new Set(prev);
            next.delete('*ALL*');
            if (next.has(layerName)) {
                next.delete(layerName);
            } else {
                next.add(layerName);
            }
            return next;
        });
    }, []);

    const expandAllClusters = useCallback(() => {
        setExpandedClusters(new Set(['*ALL*']));
    }, []);

    const collapseAllClusters = useCallback(() => {
        setExpandedClusters(new Set());
    }, []);

    const handleNodeDoubleClick = useCallback(
        (_: React.MouseEvent, node: Node) => {
            if (node.id.startsWith('cluster:')) {
                const clusterId = node.data.clusterId as string;
                if (clusterId) {
                    toggleClusterLayer(clusterId);
                }
            }
        },
        [toggleClusterLayer]
    );

    const handlePathFinderNode = useCallback(
        async (nodeId: string) => {
            if (!pathFinderOrigin) {
                setPathFinderOrigin(nodeId);
                setPathFinderError('Origem definida. Agora clique no destino.');
                setPathFinderPaths([]);
                setPathFinderEdgeKeys(new Set());
                return;
            }
            if (nodeId === pathFinderOrigin) {
                setPathFinderError('Destino deve ser diferente da origem.');
                return;
            }
            setPathFinderLoading(true);
            setPathFinderError(null);
            try {
                const data = await fetchGraphPath(pathFinderOrigin, nodeId, Math.max(1, pathFinderDepth));
                const newPaths = (data.paths || []).map((path) => path.map((node) => node.key));
                setPathFinderPaths(newPaths);
                const newEdges = new Set<string>();
                (data.edges || []).forEach((edge) => {
                    if (edge.source && edge.target) {
                        newEdges.add(`${edge.source}::${edge.target}`);
                    }
                });
                setPathFinderEdgeKeys(newEdges);
                setPathFinderTarget(nodeId);
                setPathFinderError(newPaths.length === 0 ? 'Nenhum caminho encontrado.' : null);
            } catch (error: any) {
                setPathFinderPaths([]);
                setPathFinderEdgeKeys(new Set());
                setPathFinderTarget(null);
                setPathFinderError(error?.message || 'Falha ao buscar trajetórias.');
            } finally {
                setPathFinderLoading(false);
                setPathFinderMode(false);
                setPathFinderOrigin(null);
            }
        },
        [pathFinderDepth, pathFinderOrigin]
    );

    const handleNodeClick = useCallback(
        (_: React.MouseEvent, node: Node) => {
            if (node.id.startsWith('cluster:')) {
                const clusterId = node.data.clusterId as string;
                if (clusterId) {
                    toggleClusterLayer(clusterId);
                }
                return;
            }
            if (pathFinderMode) {
                handlePathFinderNode(node.id);
                return;
            }
            const gn = graphNodes.find((n) => n.namespace_key === node.id);
            if (gn) {
                const screenPosition = reactFlowInstanceRef.current?.project(node.position);
                const canvasRect = canvasRef.current?.getBoundingClientRect();
                const absolutePosition = screenPosition && canvasRect
                    ? { x: canvasRect.left + screenPosition.x, y: canvasRect.top + screenPosition.y }
                    : screenPosition;
                onNodeClick(node.id, gn, absolutePosition ? { x: absolutePosition.x, y: absolutePosition.y } : undefined);
            }
        },
        [graphNodes, onNodeClick, pathFinderMode, handlePathFinderNode, toggleClusterLayer]
    );

    const topClusters = clusterSummaries.slice(0, CLUSTER_OVERVIEW_LIMIT);
    const maxClusterSize = topClusters.length ? Math.max(1, ...topClusters.map((summary) => summary.count)) : 1;
    const clusterableLanes = laneMeta.filter((lane) => lane.isCollapsible);
    const collapsedLanes = clusterableLanes.filter((lane) => lane.isCollapsed);
    const hasCollapsible = clusterableLanes.length > 0;
    const hasCollapsed = collapsedLanes.length > 0;
    const hasExpanded = clusterableLanes.some((lane) => !lane.isCollapsed);

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
        <div className="canvas-area" ref={canvasRef}>
            {clusterSummaries.length > 0 && (
            <div className="cluster-overview">
                <div className="cluster-map" aria-label="Mapa compacto de clusters">
                    {topClusters.map((summary) => (
                        <div key={`map-${summary.layer}`} className="cluster-map-row">
                            <div className="cluster-map-bar">
                                <div
                                    className="cluster-map-fill"
                                    style={{
                                        width: `${Math.min(100, (summary.count / maxClusterSize) * 100)}%`,
                                        background: hotspotColorScale(summary.avgHotspot),
                                    }}
                                />
                            </div>
                            <div className="cluster-map-meta">
                                <span>{summary.layer}</span>
                                <span>{summary.count} nós</span>
                            </div>
                        </div>
                    ))}
                </div>
                <div className="cluster-overview-cards">
                    {topClusters.map((summary) => (
                        <div key={summary.layer} className="cluster-overview-card">
                            <div className="cluster-overview-label">{summary.layer}</div>
                            <div className="cluster-overview-count">{summary.count} nós</div>
                            <div className="cluster-overview-hotspot" style={{ background: hotspotColorScale(summary.avgHotspot) }} />
                        </div>
                    ))}
                </div>
            </div>

            )}
            {viewMode === '2d' && laneMeta.length > 0 && (
                <div className="swimlane-overlay">
                    <div className="swimlane-header">
                        <span className="swimlane-title">Swimlanes</span>
                        <div className="swimlane-actions">
                            <button
                                className="btn btn-secondary swimlane-action"
                                onClick={collapseAllClusters}
                                disabled={!hasCollapsible || !hasExpanded}
                            >
                                Colapsar todos
                            </button>
                            <button
                                className="btn btn-accent swimlane-action"
                                onClick={expandAllClusters}
                                disabled={!hasCollapsible || !hasCollapsed}
                            >
                                Expandir todos
                            </button>
                        </div>
                    </div>
                    <div className="swimlane-rows">
                        {laneMeta.map((lane) => (
                            <div key={lane.layer} className="swimlane-row">
                                <div className="swimlane-labels">
                                    <span className="swimlane-name">{lane.layer}</span>
                                    <span className="swimlane-count">{lane.count} nós</span>
                                </div>
                                <div className="swimlane-heat" style={{ background: hotspotColorScale(lane.avgHotspot) }} />
                                {lane.isCollapsible ? (
                                    <button
                                        className={`btn swimlane-toggle ${lane.isCollapsed ? 'btn-secondary' : 'btn-accent'}`}
                                        onClick={() => toggleClusterLayer(lane.layer)}
                                    >
                                        {lane.isCollapsed ? 'Expandir' : 'Detalhar'}
                                    </button>
                                ) : (
                                    <span className="swimlane-detailed">Sempre detalhado</span>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
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
                    onMove={(vp) => setViewportState(vp)}
                    onInit={(instance) => {
                        reactFlowInstanceRef.current = instance;
                        setViewportState(instance.getViewport());
                    }}
                    onPaneClick={() => {
                        props.onCanvasClick?.();
                    }}
                >
                    <Controls />
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

                <button
                  className={`btn ${pathFinderMode ? 'btn-accent' : 'btn-secondary'}`}
                  onClick={() => {
                      if (pathFinderMode) {
                          setPathFinderOrigin(null);
                          setPathFinderError(null);
                      }
                      setPathFinderMode((prev) => !prev);
                      setPathFinderPaths([]);
                      setPathFinderEdgeKeys(new Set());
                  }}
                  disabled={pathFinderLoading}
                  style={{ boxShadow: '0 4px 12px rgba(0,0,0,0.2)' }}
                  title="Ative o modo path finder para selecionar dois nós"
                >
                    {pathFinderMode ? 'Cancelar Path Finder' : 'Path Finder'}
                </button>
                <input
                  type="number"
                  min={3}
                  max={30}
                  value={pathFinderDepth}
                  onChange={(event) => setPathFinderDepth(Math.max(3, Number(event.target.value) || 3))}
                  className="path-depth-input"
                  title="Profundidade máxima do path finder"
                />

                <button
                  className={`btn ${inheritanceMode ? 'btn-accent' : 'btn-secondary'}`}
                  onClick={() => setInheritanceMode((prev) => !prev)}
                  style={{ boxShadow: '0 4px 12px rgba(0,0,0,0.2)' }}
                  title="Visualização de herança (Reingold-Tilford)"
                >
                    {inheritanceMode ? 'Sair da Herança' : 'Vista de Herança'}
                </button>
                {inheritanceLoading && (
                    <span className="path-finder-status" style={{ marginTop: 8 }}>Carregando herança...</span>
                )}
                {inheritanceError && (
                    <span className="path-finder-error" style={{ marginTop: 8 }}>{inheritanceError}</span>
                )}

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

            {(pathFinderMode || pathFinderPaths.length > 0 || pathFinderError) && (
                <div className="path-finder-panel">
                    <div className="path-finder-header">
                        <span className="path-finder-title">Path Finder</span>
                        {pathFinderLoading && <span className="path-finder-status">Buscando...</span>}
                    </div>
                    <div className="path-finder-body">
                        {pathFinderMode && !pathFinderOrigin && (
                            <div>Clique no nó de origem.</div>
                        )}
                        {pathFinderMode && pathFinderOrigin && (
                            <div>Origem: <b>{nodeNameMap.get(pathFinderOrigin) || pathFinderOrigin}</b>. Agora clique no destino.</div>
                        )}
                        {pathFinderPaths.length > 0 && (
                            <>
                                <div>Paths encontrados: {pathFinderPaths.length}</div>
                                <div className="path-finder-path-list">
                                    {pathFinderPaths.slice(0, 3).map((path, idx) => (
                                        <div key={`path-${idx}`} className="path-finder-path">
                                            <span className="path-finder-path-label">#{idx + 1}</span>
                                            <span>{path.map((key) => nodeNameMap.get(key) || key).join(' → ')}</span>
                                        </div>
                                    ))}
                                    {pathFinderPaths.length > 3 && (
                                        <div className="path-finder-path-ellipsis">... e mais {pathFinderPaths.length - 3} caminho(s)</div>
                                    )}
                                </div>
                            </>
                        )}
                        {pathFinderTarget && (
                            <div>Último destino: <b>{nodeNameMap.get(pathFinderTarget) || pathFinderTarget}</b></div>
                        )}
                        {pathFinderError && (
                            <div className="path-finder-error">{pathFinderError}</div>
                        )}
                    </div>
                    <div className="path-finder-footer">
                        <button
                            className="btn btn-secondary"
                            onClick={() => {
                                setPathFinderPaths([]);
                                setPathFinderEdgeKeys(new Set());
                                setPathFinderTarget(null);
                                setPathFinderError(null);
                            }}
                        >
                            Limpar destaque
                        </button>
                    </div>
                </div>
            )}

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
                <div className="legend-group">
                    <div className="legend-title">Tipos de Conexão</div>
                    <div className="legend-body">
                        {[
                            { type: 'CALLS', color: '#a78bfa' },
                            { type: 'DEPENDS_ON', color: '#4f8ff7' },
                            { type: 'READS_FROM', color: '#34d399' },
                            { type: 'WRITES_TO', color: '#fb7185' },
                            { type: 'HAS_METHOD', color: '#5a6380' },
                        ].map((e) => (
                            <div key={e.type} className="legend-item">
                                <div className="legend-line" style={{ background: e.color }} />
                                {e.type}
                            </div>
                        ))}
                    </div>
                </div>
                <div className="legend-group">
                    <div className="legend-title">Tipos de Nó</div>
                    <div className="legend-body">
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
                                <div className="legend-dot" style={{ background: e.color }} />
                                {e.type}
                            </div>
                        ))}
                    </div>
                </div>
                <div className="legend-group">
                    <div className="legend-title">Cores de Impacto</div>
                    <div className="legend-body">
                        {[
                            { type: 'Selecionado', color: '#facc15' },
                            { type: 'Upstream', color: '#22c55e' },
                            { type: 'Downstream', color: '#f97316' },
                            { type: 'Destaque IA/Simulação', color: '#f472b6' },
                            { type: 'Deletado', color: '#ef4444' },
                        ].map((e) => (
                            <div key={e.type} className="legend-item">
                                <div className="legend-dot" style={{ background: e.color }} />
                                {e.type}
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}

/* ─── Main Export Component with Provider ─── */
const GraphCanvasInner = forwardRef<GraphCanvasHandle, GraphCanvasProps>(GraphCanvasInnerImpl);

const GraphCanvas = forwardRef<GraphCanvasHandle, GraphCanvasProps>((props, ref) => (
    <ReactFlowProvider>
        <GraphCanvasInner {...props} ref={ref} />
    </ReactFlowProvider>
));

export default GraphCanvas;
