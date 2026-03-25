import { useEffect, useMemo, useRef } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import type { GraphNode, GraphEdge } from '../api';

interface GraphCanvas3DProps {
    graphNodes: GraphNode[];
    graphEdges: GraphEdge[];
    highlightedUpstream: Set<string>;
    highlightedDownstream: Set<string>;
    aiHighlightedNodes: string[];
    selectedNodeKey: string | null;
    onNodeClick: (nodeKey: string, nodeData: GraphNode) => void;
    searchTerm: string;
    heatmapEnabled: boolean;
    clustered: boolean;
    focusNodeKey: string | null;
    focusRequestId: number;
}

type FgNode = {
    id: string;
    name: string;
    color: string;
    val: number;
    raw: GraphNode;
    x?: number;
    y?: number;
    z?: number;
};

type FgLink = {
    source: string;
    target: string;
    color: string;
    type: string;
};

function getHeatmapColor(complexity: number): string {
    if (complexity > 20) return '#ef4444';
    if (complexity >= 10) return '#f59e0b';
    if (complexity >= 5) return '#eab308';
    if (complexity >= 1) return '#3b82f6';
    return '#64748b';
}

function getTypeColor(labels: string[]): string {
    if (labels.includes('Java_Class')) return '#fb923c';
    if (labels.includes('Java_Method')) return '#fdba74';
    if (labels.includes('API_Endpoint')) return '#67e8f9';
    if (labels.includes('TS_Component')) return '#60a5fa';
    if (labels.includes('TS_Function')) return '#93c5fd';
    if (labels.includes('SQL_Table')) return '#34d399';
    if (labels.includes('SQL_Procedure')) return '#6ee7b7';
    if (labels.includes('Mobile_Component')) return '#a78bfa';
    if (labels.includes('External_Dependency')) return '#cbd5e1';
    return '#60a5fa';
}

export default function GraphCanvas3D({
    graphNodes,
    graphEdges,
    highlightedUpstream,
    highlightedDownstream,
    aiHighlightedNodes,
    selectedNodeKey,
    onNodeClick,
    searchTerm,
    heatmapEnabled,
    clustered,
    focusNodeKey,
    focusRequestId,
}: GraphCanvas3DProps) {
    const fgRef = useRef<any>(null);
    const graphData = useMemo(() => {
        const filteredNodes = searchTerm
            ? graphNodes.filter((n) => n.name.toLowerCase().includes(searchTerm.toLowerCase()))
            : graphNodes;

        const keys = new Set(filteredNodes.map((n) => n.namespace_key));
        const filteredEdges = graphEdges.filter((e) => keys.has(e.source) && keys.has(e.target));

        if (clustered) {
            const groupFor = (n: GraphNode) => n.layer || n.project || 'System';
            const groups = new Map<string, GraphNode[]>();
            filteredNodes.forEach((n) => {
                const g = groupFor(n);
                if (!groups.has(g)) groups.set(g, []);
                groups.get(g)!.push(n);
            });

            const nodes: FgNode[] = Array.from(groups.entries()).map(([group, arr]) => {
                const avgComplexity = arr.reduce((acc, n) => acc + (n.complexity || 1), 0) / Math.max(1, arr.length);
                let color = '#60a5fa';
                if (heatmapEnabled) color = getHeatmapColor(avgComplexity);
                if (arr.some((n) => aiHighlightedNodes.includes(n.namespace_key))) color = '#f472b6';
                if (arr.some((n) => highlightedUpstream.has(n.namespace_key))) color = '#22c55e';
                if (arr.some((n) => highlightedDownstream.has(n.namespace_key))) color = '#f97316';
                if (arr.some((n) => n.namespace_key === selectedNodeKey)) color = '#facc15';

                return {
                    id: `cluster:${group}`,
                    name: `${group} (${arr.length})`,
                    color,
                    val: Math.max(5, Math.min(20, arr.length / 3)),
                    raw: {
                        namespace_key: `cluster:${group}`,
                        name: `${group} (${arr.length})`,
                        labels: ['Cluster'],
                    } as GraphNode,
                };
            });

            const linksByPair = new Map<string, number>();
            const keyToGroup = new Map<string, string>();
            filteredNodes.forEach((n) => keyToGroup.set(n.namespace_key, groupFor(n)));

            filteredEdges.forEach((e) => {
                const sg = keyToGroup.get(e.source);
                const tg = keyToGroup.get(e.target);
                if (!sg || !tg || sg === tg) return;
                const k = `${sg}::${tg}`;
                linksByPair.set(k, (linksByPair.get(k) || 0) + 1);
            });

            const links: FgLink[] = Array.from(linksByPair.entries()).map(([pair, weight]) => {
                const [sg, tg] = pair.split('::');
                return {
                    source: `cluster:${sg}`,
                    target: `cluster:${tg}`,
                    color: '#64748b',
                    type: `CLUSTER_${weight}`,
                };
            });

            return { nodes, links };
        }

        const nodes: FgNode[] = filteredNodes.map((n) => {
            let color = getTypeColor(n.labels || []);
            if (heatmapEnabled) color = getHeatmapColor(n.complexity || 0);
            if (highlightedUpstream.has(n.namespace_key)) color = '#22c55e';
            if (highlightedDownstream.has(n.namespace_key)) color = '#f97316';
            if (n.namespace_key === selectedNodeKey) color = '#facc15';
            if (aiHighlightedNodes.includes(n.namespace_key)) color = '#f472b6';

            if (aiHighlightedNodes.length > 0 && !aiHighlightedNodes.includes(n.namespace_key)) {
                color = '#475569';
            }

            return {
                id: n.namespace_key,
                name: n.name,
                color,
                val: Math.max(2, Math.min(14, (n.complexity || 1))),
                raw: n,
            };
        });

        const links: FgLink[] = filteredEdges.map((e) => ({
            source: e.source,
            target: e.target,
            color: e.type === 'CALLS' ? '#a78bfa' : '#4f8ff7',
            type: e.type,
        }));

        return { nodes, links };
    }, [
        graphNodes,
        graphEdges,
        searchTerm,
        clustered,
        heatmapEnabled,
        highlightedUpstream,
        highlightedDownstream,
        selectedNodeKey,
        aiHighlightedNodes,
    ]);

    const nodeCount = graphData.nodes.length;
    const isLarge = nodeCount > 500;
    const isHuge = nodeCount > 1200;

    useEffect(() => {
        if (!focusNodeKey || !fgRef.current || focusRequestId <= 0) return;
        const node = graphData.nodes.find((n: any) => n.id === focusNodeKey);
        if (!node) return;
        // Camera move adapted from force-graph examples
        const distRatio = 1 + 90 / Math.hypot(node.x || 1, node.y || 1, node.z || 1);
        fgRef.current.cameraPosition(
            {
                x: (node.x || 0) * distRatio,
                y: (node.y || 0) * distRatio,
                z: (node.z || 0) * distRatio,
            },
            { x: node.x || 0, y: node.y || 0, z: node.z || 0 },
            700,
        );
    }, [focusNodeKey, focusRequestId, graphData.nodes]);

    return (
        <div style={{ width: '100%', height: '100%' }}>
            <ForceGraph3D
                ref={fgRef}
                graphData={graphData as any}
                backgroundColor="#06081a"
                nodeRelSize={6}
                nodeOpacity={isHuge ? 0.75 : 0.95}
                linkOpacity={isHuge ? 0.18 : 0.35}
                linkDirectionalParticles={isHuge ? 0 : isLarge ? 1 : 2}
                linkDirectionalParticleWidth={isHuge ? 0.5 : 1.5}
                linkColor={(l: any) => l.color || '#64748b'}
                nodeColor={(n: any) => n.color || '#60a5fa'}
                nodeVal={(n: any) => n.val || 4}
                nodeLabel={(n: any) => (isHuge ? n.name : `${n.name}\n${n.id}`)}
                onNodeClick={(n: any) => {
                    if (n?.raw?.namespace_key) onNodeClick(n.raw.namespace_key, n.raw);
                }}
                cooldownTicks={isHuge ? 60 : 120}
                enableNodeDrag
            />
        </div>
    );
}
