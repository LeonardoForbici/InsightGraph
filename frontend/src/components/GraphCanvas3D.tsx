import { useEffect, useMemo, useRef, useCallback, useState } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import * as THREE from 'three';
import type { GraphNode, GraphEdge } from '../api';
import { getHeatmapColor, hotspotColorScale, getTypeColor } from '../utils/graphColors';
import { getRiskColor, getNodeSize, getBrightness, shouldPulse, applyBrightness } from '../utils/visualEncoding';
import { WaveAnimationManager } from '../utils/WaveAnimationManager';

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
    // NEW: Real-time event handling
    recentChanges?: Map<string, number>; // nodeKey -> timestamp
    // NEW: Wave animation trigger
    waveAnimationTrigger?: {
        originNodeKey: string;
        affectedNodes: string[];
        timestamp: number;
    } | null;
}

type ClusterNode = {
    id: string;
    name: string;
    color: string;
    val: number;
    raw: GraphNode;
    group: string;
    hotspot: number;
    x?: number;
    y?: number;
    z?: number;
    vx?: number;
    vy?: number;
    vz?: number;
};

type ClusterLink = {
    source: string;
    target: string;
    color: string;
    type: string;
};

type ClusterCenter = {
    x: number;
    y: number;
    z: number;
};

const easeInOutQuad = (t: number): number => (t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t);

const getClusterGroup = (node: GraphNode): string => node.project || node.layer || 'System';

const createTextSprite = (text: string, fill: string): THREE.Sprite => {
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    canvas.width = 256;
    canvas.height = 64;
    if (context) {
        context.fillStyle = 'rgba(8, 12, 29, 0.9)';
        context.fillRect(0, 0, canvas.width, canvas.height);
        context.font = '600 20px Inter, Arial';
        context.fillStyle = fill;
        context.textBaseline = 'middle';
        context.fillText(text, 12, canvas.height / 2);
    }
    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false });
    const sprite = new THREE.Sprite(material);
    sprite.scale.set(120, 30, 1);
    return sprite;
};

type GraphStructure = {
    nodes: ClusterNode[];
    links: ClusterLink[];
    clusterGroupEntries: [string, ClusterNode[]][];
};

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
    recentChanges: externalRecentChanges,
    waveAnimationTrigger,
}: GraphCanvas3DProps) {
    const fgRef = useRef<any>(null);
    const pulseMeshes = useRef(new Map<string, THREE.Mesh>());
    const clusterBubbleRefs = useRef<THREE.Object3D[]>([]);
    
    // Track recent changes internally if not provided externally
    const [internalRecentChanges, setInternalRecentChanges] = useState<Map<string, number>>(new Map());
    const recentChanges = externalRecentChanges ?? internalRecentChanges;
    
    // NEW: Wave animation manager
    const waveManagerRef = useRef<WaveAnimationManager | null>(null);
    
    // Initialize wave animation manager
    useEffect(() => {
        waveManagerRef.current = new WaveAnimationManager({
            levelDelay: 200,
            nodeDuration: 600,
            waveColor: '#60a5fa',
            scaleFrom: 1.0,
            scaleTo: 1.3,
            maxDepth: 5,
            maxNodes: 50,
        });
        
        return () => {
            if (waveManagerRef.current) {
                waveManagerRef.current.stopAllWaves();
            }
        };
    }, []);
    
    // NEW: Start wave animation when trigger changes
    useEffect(() => {
        if (!waveAnimationTrigger || !waveManagerRef.current) return;
        
        console.log('[GraphCanvas3D] Starting wave animation from', waveAnimationTrigger.originNodeKey);
        waveManagerRef.current.startWave(
            waveAnimationTrigger.originNodeKey,
            waveAnimationTrigger.affectedNodes
        );
    }, [waveAnimationTrigger]);

    const graphStructure = useMemo<GraphStructure>(() => {
        const term = searchTerm.trim().toLowerCase();
        const filteredNodes = term
            ? graphNodes.filter((node) => node.name.toLowerCase().includes(term))
            : graphNodes;
        const visibleKeys = new Set(filteredNodes.map((node) => node.namespace_key));
        const filteredEdges = graphEdges.filter((edge) => visibleKeys.has(edge.source) && visibleKeys.has(edge.target));

        const groups = new Map<string, ClusterNode[]>();
        const nodes = filteredNodes.map((node) => {
            const group = getClusterGroup(node);
            
            // Use visual encoding for color - risk-based when not in heatmap mode
            let baseColor: string;
            if (heatmapEnabled) {
                baseColor = getHeatmapColor(node.complexity ?? 0);
            } else {
                // Use risk color from visual encoding, fallback to type color
                baseColor = getRiskColor(node);
            }
            
            // Use visual encoding for size
            const val = getNodeSize(node);
            
            const clusterNode: ClusterNode = {
                id: node.namespace_key,
                name: node.name,
                raw: node,
                color: baseColor,
                val,
                group,
                hotspot: node.hotspot_score ?? 0,
            };
            const bucket = groups.get(group);
            if (bucket) {
                bucket.push(clusterNode);
            } else {
                groups.set(group, [clusterNode]);
            }
            return clusterNode;
        });

        const links: ClusterLink[] = filteredEdges.map((edge) => ({
            source: edge.source,
            target: edge.target,
            color: edge.type === 'CALLS' ? '#a78bfa' : '#4f8ff7',
            type: edge.type,
        }));

        return {
            nodes,
            links,
            clusterGroupEntries: Array.from(groups.entries()),
        };
    }, [graphNodes, graphEdges, searchTerm, heatmapEnabled]);
    
    // Update wave manager graph structure when edges change
    useEffect(() => {
        if (waveManagerRef.current) {
            waveManagerRef.current.updateGraphStructure(
                graphStructure.links.map(link => ({
                    source: link.source,
                    target: link.target,
                }))
            );
        }
    }, [graphStructure.links]);

    const clusterCenters = useMemo(() => {
        const entries = graphStructure.clusterGroupEntries;
        if (!entries.length) return new Map<string, ClusterCenter>();
        const radius = Math.max(160, entries.length * 28);
        const centers = new Map<string, ClusterCenter>();
        entries.forEach(([group], index) => {
            const angle = (index / entries.length) * Math.PI * 2;
            centers.set(group, {
                x: Math.cos(angle) * radius,
                y: 0,
                z: Math.sin(angle) * radius,
            });
        });
        return centers;
    }, [graphStructure.clusterGroupEntries]);

    const clusterForce = useMemo(() => {
        if (!clusterCenters.size) return null;
        const strength = 0.08;
        return (alpha: number) => {
            const k = alpha * strength;
            graphStructure.nodes.forEach((node) => {
                const center = clusterCenters.get(node.group);
                if (!center || node.x === undefined || node.y === undefined || node.z === undefined) return;
                node.vx = (node.vx ?? 0) - (node.x - center.x) * k;
                node.vy = (node.vy ?? 0) - (node.y - center.y) * k;
                node.vz = (node.vz ?? 0) - (node.z - center.z) * k;
            });
        };
    }, [clusterCenters, graphStructure.nodes]);

    useEffect(() => {
        if (!fgRef.current) return;
        fgRef.current.d3Force('cluster', clustered ? clusterForce : null);
    }, [clusterForce, clustered]);

    useEffect(() => {
        const scene = fgRef.current?.scene();
        if (!scene) return;
        clusterBubbleRefs.current.forEach((obj) => scene.remove(obj));
        clusterBubbleRefs.current = [];
        if (!clustered) return;
        graphStructure.clusterGroupEntries.forEach(([group, nodes]) => {
            const center = clusterCenters.get(group);
            if (!center) return;
            const avgHotspot = nodes.reduce((acc, node) => acc + node.hotspot, 0) / Math.max(1, nodes.length);
            const radius = Math.min(52, Math.max(22, nodes.length * 0.35 + 6));
            const bubble = new THREE.Group();
            const sphere = new THREE.Mesh(
                new THREE.SphereGeometry(1, 32, 32),
                new THREE.MeshBasicMaterial({
                    color: hotspotColorScale(avgHotspot),
                    transparent: true,
                    opacity: 0.12,
                    depthWrite: false,
                })
            );
            sphere.scale.set(radius, radius, radius);
            bubble.add(sphere);
            const label = createTextSprite(`${group} (${nodes.length})`, '#e0e7ff');
            label.position.set(0, radius + 12, 0);
            bubble.add(label);
            bubble.position.set(center.x, center.y, center.z);
            scene.add(bubble);
            clusterBubbleRefs.current.push(bubble);
        });
    }, [clustered, clusterCenters, graphStructure.clusterGroupEntries]);

    useEffect(() => {
        let frameId: number;
        const animate = () => {
            const now = performance.now();
            pulseMeshes.current.forEach((mesh, id) => {
                const scale = 1 + 0.15 * Math.sin(now / 300 + id.length);
                mesh.scale.setScalar(scale);
            });
            frameId = requestAnimationFrame(animate);
        };
        frameId = requestAnimationFrame(animate);
        return () => cancelAnimationFrame(frameId);
    }, []);
    
    // NEW: Animation loop for wave animations
    useEffect(() => {
        let frameId: number;
        const animateWaves = () => {
            // Trigger re-render if there are active waves
            if (waveManagerRef.current && waveManagerRef.current.getActiveWaves().length > 0) {
                if (fgRef.current) {
                    fgRef.current.refresh();
                }
            }
            frameId = requestAnimationFrame(animateWaves);
        };
        frameId = requestAnimationFrame(animateWaves);
        return () => cancelAnimationFrame(frameId);
    }, []);
    
    // Cleanup effect for brightness fade - trigger re-render when brightness changes
    useEffect(() => {
        if (recentChanges.size === 0) return;
        
        const interval = setInterval(() => {
            // Check if any nodes need brightness update
            let needsUpdate = false;
            recentChanges.forEach((timestamp, nodeKey) => {
                const elapsed = Date.now() - timestamp;
                if (elapsed < 10000) {
                    needsUpdate = true;
                }
            });
            
            if (needsUpdate && fgRef.current) {
                // Force re-render of node objects to update colors
                fgRef.current.refresh();
            }
        }, 100); // Check every 100ms for smooth fade
        
        return () => clearInterval(interval);
    }, [recentChanges]);

    const determineNodeColor = useCallback(
        (node: ClusterNode) => {
            // Check if node is part of active wave animation
            if (waveManagerRef.current && waveManagerRef.current.isAnimating(node.id)) {
                const animState = waveManagerRef.current.getAnimationState(node.id);
                if (animState) {
                    return animState.color; // Use wave color (#60a5fa)
                }
            }
            
            let color: string;
            
            // Priority-based color selection
            if (aiHighlightedNodes.includes(node.id)) {
                color = '#f472b6';
            } else if (node.id === selectedNodeKey) {
                color = '#facc15';
            } else if (highlightedUpstream.has(node.id)) {
                color = '#22c55e';
            } else if (highlightedDownstream.has(node.id)) {
                color = '#f97316';
            } else if (aiHighlightedNodes.length > 0) {
                color = '#475569';
            } else {
                color = node.color;
            }
            
            // Apply brightness boost for recently changed nodes
            const brightness = getBrightness(node.id, recentChanges);
            if (brightness > 0) {
                color = applyBrightness(color, brightness);
            }
            
            return color;
        },
        [aiHighlightedNodes, highlightedUpstream, highlightedDownstream, selectedNodeKey, recentChanges]
    );

    const createNodeObject = useCallback(
        (node: ClusterNode) => {
            const sphere = new THREE.Mesh(
                new THREE.SphereGeometry(1.2, 32, 32),
                new THREE.MeshStandardMaterial({
                    color: determineNodeColor(node),
                    transparent: true,
                    opacity: 0.92,
                    metalness: 0.3,
                    roughness: 0.4,
                })
            );
            const group = new THREE.Group();
            group.add(sphere);
            
            // Base scale from node size
            let scale = Math.min(2.4, 0.6 + node.val / 10);
            
            // Apply wave animation scale if active
            if (waveManagerRef.current && waveManagerRef.current.isAnimating(node.id)) {
                const waveScale = waveManagerRef.current.getCurrentScale(node.id);
                scale *= waveScale;
            }
            
            sphere.scale.setScalar(scale);
            
            // Apply pulse animation to high hotspot nodes using visual encoding
            if (node.raw && shouldPulse(node.raw)) {
                pulseMeshes.current.set(node.id, sphere);
            } else {
                pulseMeshes.current.delete(node.id);
            }
            
            return group;
        },
        [determineNodeColor]
    );

    const animateFocus = useCallback(
        (target: ClusterNode) => {
            if (!fgRef.current) return () => {};
            const start = fgRef.current.cameraPosition();
            const end = {
                x: (target.x ?? 0) * 1.1 + 20,
                y: (target.y ?? 0) + 40,
                z: (target.z ?? 0) * 1.1 + 20,
            };
            const duration = 900;
            let frameId = 0;
            const startTime = performance.now();
            const step = () => {
                const now = performance.now();
                const progress = Math.min(1, (now - startTime) / duration);
                const eased = easeInOutQuad(progress);
                const next = {
                    x: start.x + (end.x - start.x) * eased,
                    y: start.y + (end.y - start.y) * eased,
                    z: start.z + (end.z - start.z) * eased,
                };
                fgRef.current.cameraPosition(next, { x: target.x ?? 0, y: target.y ?? 0, z: target.z ?? 0 }, 0);
                if (progress < 1) {
                    frameId = requestAnimationFrame(step);
                }
            };
            frameId = requestAnimationFrame(step);
            return () => cancelAnimationFrame(frameId);
        },
        []
    );

    useEffect(() => {
        if (!focusNodeKey || focusRequestId <= 0) return;
        const target = graphStructure.nodes.find((node) => node.id === focusNodeKey);
        if (!target) return;
        const cancel = animateFocus(target);
        return cancel;
    }, [focusNodeKey, focusRequestId, graphStructure.nodes, animateFocus]);

    return (
        <div style={{ width: '100%', height: '100%' }}>
            <ForceGraph3D
                ref={fgRef}
                graphData={{ nodes: graphStructure.nodes, links: graphStructure.links }}
                backgroundColor="#06081a"
                nodeRelSize={6}
                nodeOpacity={graphStructure.nodes.length > 1200 ? 0.75 : 0.95}
                linkOpacity={graphStructure.nodes.length > 1200 ? 0.18 : 0.35}
                linkDirectionalParticles={graphStructure.nodes.length > 1200 ? 0 : graphStructure.nodes.length > 500 ? 1 : 2}
                linkDirectionalParticleWidth={graphStructure.nodes.length > 1200 ? 0.5 : 1.5}
                linkColor={(link: ClusterLink) => link.color}
                nodeThreeObject={createNodeObject}
                nodeLabel={(node: ClusterNode) => `${node.name}\nHotspot ${node.hotspot.toFixed(0)}`}
            nodeVal={(node: ClusterNode) => Math.max(node.val, 8)}
                onNodeClick={(node: ClusterNode) => {
                    if (node.raw?.namespace_key) {
                        onNodeClick(node.raw.namespace_key, node.raw);
                    }
                }}
                cooldownTicks={graphStructure.nodes.length > 1200 ? 60 : 120}
                enableNodeDrag
                linkWidth={(link: ClusterLink) => (link.type === 'CALLS' ? 2 : 1)}
            />
        </div>
    );
}
