const BASE = '/api';

/* ─── Types ─── */

export interface GraphNode {
    namespace_key: string;
    name: string;
    labels: string[];
    file?: string;
    project?: string;
    layer?: string;
    decorators?: string;
    parent_class?: string;
    loc?: number;
    complexity?: number;
    status?: 'deleted' | 'impacted';
}

export interface GraphEdge {
    source: string;
    target: string;
    type: string;
}

export interface GraphData {
    nodes: GraphNode[];
    edges: GraphEdge[];
}

export interface ImpactData {
    upstream: { key: string; name: string; labels: string[]; rel_type: string }[];
    downstream: { key: string; name: string; labels: string[]; rel_type: string }[];
}

export interface ScanStatus {
    status: string;
    scanned_files: number;
    total_files: number;
    total_nodes: number;
    total_relationships: number;
    progress_percent: number;
    current_file: string;
    errors: string[];
}

export interface BlastRadiusData {
    nodes: GraphNode[];
    edges: GraphEdge[];
    risk_score: number;
}

export interface AntipatternData {
    circular_dependencies: { path: string[]; length: number }[];
    god_classes: { key: string; name: string; layer: string; out_degree: number; in_degree: number; complexity: number }[];
    dead_code: { key: string; name: string; layer: string; file: string }[];
}

export interface GraphStats {
    total_nodes: number;
    total_edges: number;
    nodes_by_type: Record<string, number>;
    edges_by_type: Record<string, number>;
    layers: Record<string, number>;
    projects: string[];
}

export interface AskResponse {
    answer: string;
    relevant_nodes: string[];
    model: string;
    context_used: number;
}

export interface SimulateResponse {
    nodes: GraphNode[];
    edges: GraphEdge[];
    risk_score: number;
    affected_count: number;
    impact_insights?: string[];
}

export interface HealthStatus {
    neo4j: string;
    ollama_scanner: string;
    ollama_chat: string;
    scanner_model: string;
    chat_model: string;
    complex_model: string;
}

export interface HistorySnapshot {
    timestamp: string;
    total_nodes: number;
    total_edges: number;
    god_classes: number;
    circular_deps: number;
    dead_code: number;
}

/* ─── API Functions ─── */

export async function scanProjects(paths: string[]): Promise<ScanStatus> {
    const res = await fetch(`${BASE}/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function getScanStatus(): Promise<ScanStatus> {
    const res = await fetch(`${BASE}/scan/status`);
    return res.json();
}

export async function fetchGraph(project?: string, layer?: string): Promise<GraphData> {
    const params = new URLSearchParams();
    if (project) params.set('project', project);
    if (layer) params.set('layer', layer);
    const res = await fetch(`${BASE}/graph?${params}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchImpact(nodeKey: string): Promise<ImpactData> {
    const res = await fetch(`${BASE}/impact/${encodeURIComponent(nodeKey)}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchBlastRadius(nodeKey: string): Promise<BlastRadiusData> {
    const res = await fetch(`${BASE}/impact/blast-radius/${encodeURIComponent(nodeKey)}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchAntipatterns(): Promise<AntipatternData> {
    const res = await fetch(`${BASE}/antipatterns`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchProjects(): Promise<string[]> {
    const res = await fetch(`${BASE}/projects`);
    const data = await res.json();
    return data.projects || [];
}

export async function fetchGraphStats(): Promise<GraphStats> {
    const res = await fetch(`${BASE}/graph/stats`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function askQuestion(question: string, contextNode?: string): Promise<AskResponse> {
    const res = await fetch(`${BASE}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, context_node: contextNode }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function simulateChanges(deletedNodes: string[], addedEdges: any[] = []): Promise<SimulateResponse> {
    const res = await fetch(`${BASE}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deleted_nodes: deletedNodes, added_edges: addedEdges }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function requestSimulationReview(simData: SimulateResponse): Promise<{ report: string }> {
    const res = await fetch(`${BASE}/simulate/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(simData),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchHealth(): Promise<HealthStatus> {
    const res = await fetch(`${BASE}/health`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchHistory(): Promise<HistorySnapshot[]> {
    const res = await fetch(`${BASE}/history`);
    if (!res.ok) return []; // fail gracefully for history
    return res.json();
}
