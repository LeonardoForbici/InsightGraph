// InsightGraph API Client
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
    impact_distance?: number;
    git_churn?: number;
    hotspot_score?: number;
    wmc?: number;
    cbo?: number;
    rfc?: number;
    lcom?: number;
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

export interface TransactionLane {
    layer: string;
    nodes: Array<{
        namespace_key: string;
        name: string;
        labels: string[];
        layer: string;
        project?: string;
        file?: string;
        depth: number;
        via_rel?: string | null;
    }>;
}

export interface TransactionViewData {
    origin: {
        namespace_key: string;
        name: string;
        labels: string[];
        layer: string;
        project?: string;
        file?: string;
    };
    max_depth: number;
    nodes_visited: number;
    lanes: TransactionLane[];
    edges: GraphEdge[];
    terminal_paths: Array<{
        target_key: string;
        target_name: string;
        target_layer: string;
        depth: number;
        path: string[];
    }>;
}

export interface TransactionExplainData {
    explanation: string;
    model?: string | null;
    origin: TransactionViewData["origin"];
    layers: string[];
    terminal_paths: TransactionViewData["terminal_paths"];
}

export interface PathFinderData {
    found: boolean;
    source: string;
    target: string;
    max_depth?: number;
    hops?: number;
    path: string[];
    nodes: GraphNode[];
    edges: GraphEdge[];
}

export interface SavedViewPayload {
    name: string;
    description?: string;
    project?: string;
    filters?: Record<string, unknown>;
    reactflow_state?: Record<string, unknown>;
}

export interface SavedView extends SavedViewPayload {
    id: string;
    created_at: number;
    updated_at: number;
}

export interface AnnotationPayload {
    node_key: string;
    title?: string;
    content: string;
    severity?: string;
    tag?: string;
    tag_id?: string;
    tag_color?: string;
}

export interface AnnotationRecord {
    id: string;
    node_key: string;
    title?: string | null;
    content: string;
    severity?: string | null;
    tag?: string | null;
    tag_color?: string | null;
    tag_id?: string | null;
    created_at: number;
    updated_at: number;
}

export interface ApiInventoryResponseItem {
    namespace_key?: string | null;
    name?: string | null;
    route_path?: string | null;
    http_method?: string | null;
    project?: string | null;
    file?: string | null;
    layer?: string | null;
    labels?: string[];
}

export interface Tag {
    id: string;
    name: string;
    color?: string | null;
    created_at: number;
}

export interface AntipatternData {
    circular_dependencies: { path: string[]; length: number }[];
    god_classes: { key: string; name: string; layer: string; out_degree: number; in_degree: number; complexity: number }[];
    dead_code: { key: string; name: string; layer: string; file: string }[];
    cloud_blockers: { key: string; name: string; layer: string; file: string }[];
    hardcoded_secrets: { key: string; name: string; layer: string; file: string }[];
    fat_controllers: { key: string; name: string; layer: string; complexity: number; out_degree: number; in_degree: number }[];
    top_external_deps: { package_name: string; usage_count: number }[];
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
    ollama_embed?: string;
    scanner_model: string;
    chat_model: string;
    complex_model: string;
    embed_model?: string;
    rag_index_nodes?: number;
}

export interface RagStatus {
    entries: number;
    with_embeddings: number;
    embedding_coverage: number;
    stale: boolean;
    embed_model: string;
    index_file: string;
    metadata?: Record<string, unknown>;
}

export interface HistorySnapshot {
    timestamp: string;
    total_nodes: number;
    total_edges: number;
    god_classes: number;
    circular_deps: number;
    dead_code: number;
}

export type ChangeType =
    | 'rename_parameter'
    | 'change_column_type'
    | 'change_method_signature'
    | 'change_procedure_param';

export interface ChangeDescriptor {
    change_type: ChangeType;
    target_key: string;
    parameter_name?: string;
    old_type?: string;
    new_type?: string;
    max_depth?: number;
}

export interface AffectedItem {
    namespace_key: string;
    name: string;
    labels: string[];
    category: 'DIRECT' | 'TRANSITIVE' | 'INFERRED';
    confidence_score: number;
    call_chain: string[];
    requires_manual_review: boolean;
    resolution_method: 'exact_key' | 'qualified_name' | 'heuristic' | 'semantic';
}

export interface AnalysisMetadata {
    total_affected: number;
    high_confidence_count: number;
    low_confidence_count: number;
    parse_errors: string[];
    unresolved_links: string[];
    semantic_analysis_available: boolean;
    truncated: boolean;
    elapsed_seconds: number;
}

export interface SemanticImpact {
    summary: string;
    risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
    breaking_changes: string[];
    migration_steps: string[];
    estimated_effort: string;
}

export interface AffectedSet {
    items: AffectedItem[];
    analysis_metadata: AnalysisMetadata;
    semantic_analysis?: SemanticImpact | null;
}

export interface DataFlowLink {
    from_key: string;
    to_key: string;
    rel_type: string;
    resolved: boolean;
}

export interface DataFlowChain {
    column_key: string;
    links: DataFlowLink[];
}

export interface FieldLevelNode {
    namespace_key: string;
    name: string;
    kind?: string;
    data_type?: string;
    param_mode?: string;
    parent_key?: string;
    labels?: string[];
    relationship_type?: string;
}

export interface ContractBreak {
    namespace_key: string;
    name?: string;
    signature_hash?: string;
    previous_signature_hash?: string;
    contract_broken?: boolean;
    affected_set?: {
        total_affected: number;
    };
}

export interface FragilityDetail {
    node_key: string;
    name: string;
    fragility_score: number;
    previous_fragility_score: number | null;
    dependents_count: number;
    graph_depth: number;
    cyclomatic_complexity: number;
    is_god_class: boolean;
    refactoring_recommendation: string | null;
    vulnerability_count: number;
}

export interface TaintPoint {
    node_key: string;
    name: string;
    layer: string;
    data_type: string;
    precision_risk: boolean;
    precision_risk_description: string;
    resolved: boolean;
}

export interface TaintPath {
    origin_key: string;
    origin_layer: string;
    destination_layer: string;
    points: TaintPoint[];
    total_hops: number;
    unresolved_links: string[];
}

export interface TypeContext {
    declaring_class: string;
    param_types: string[];
    return_type: string;
    module: string;
}

export interface ResolvedSymbol {
    namespace_key: string;
    name: string;
    type_context: TypeContext;
    resolution_method: 'exact_key' | 'qualified_name' | 'heuristic' | 'semantic';
    confidence_score: number;
    semantic_conflicts: string[];
}

export interface SideEffect {
    artifact_key: string;
    artifact_name: string;
    effect_type: 'SILENT_LOGIC_FAILURE' | 'DOMAIN_RESTRICTION' | 'RETROACTIVE_RULE_VIOLATION';
    rule_violated: string;
    side_effect_risk: boolean;
    inferred: boolean;
    confidence_score: number;
}

export interface PropagationChainItem {
    node_key: string;
    name: string;
    layer: string;
    data_type: string;
    fragility_score: number;
    precision_risk: boolean;
    side_effect_risk: boolean;
}

export interface BidirectionalResult {
    origin_key: string;
    direction: 'BOTTOM_UP' | 'TOP_DOWN';
    chain: PropagationChainItem[];
    taint_path: TaintPath | null;
    side_effects: SideEffect[];
    total_hops: number;
    isolated: boolean;
    elapsed_seconds: number;
    truncated: boolean;
}

export interface SecurityIssue {
    rule_id: string;
    severity: 'error' | 'warning' | 'note' | string;
    message: string;
    file_path: string;
    start_line: number;
    end_line: number;
    entity_key?: string;
}

export interface SecurityCoverage {
    analyzed_nodes: number;
    total_nodes: number;
    coverage_percent: number;
}

export interface SecurityFileSummary {
    file_path: string;
    project?: string | null;
    vulnerability_count: number;
    highest_severity: 'error' | 'warning' | 'note' | string;
    rule_ids: string[];
    loc: number;
    node_key?: string | null;
}

export interface SecuritySummary {
    total_vulnerabilities: number;
    severity_breakdown: Record<string, number>;
    coverage: SecurityCoverage;
    tainted_nodes: number;
    top_files: SecurityFileSummary[];
}

export interface SecurityVulnerabilityRecord {
    rule_id: string;
    severity: 'error' | 'warning' | 'note' | string;
    message: string;
    file_path: string;
    start_line: number;
    end_line: number;
    entity_key?: string | null;
    entity_name?: string | null;
    project?: string | null;
}

export interface SecurityVulnerabilityListResponse {
    items: SecurityVulnerabilityRecord[];
    total: number;
}

export interface TodoItem {
    type: string;
    text: string;
    file: string;
    line: number;
    node_key?: string | null;
    project?: string | null;
}

export interface TodoListResponse {
    items: TodoItem[];
    total: number;
}

export interface GitBlameInfo {
    file_path: string;
    project?: string | null;
    last_committer: string;
    last_commit_date?: string | null;
    author_count: number;
    bus_factor_one: boolean;
}

export interface MethodUsageItem {
    key: string;
    name: string;
    file?: string;
    layer?: string;
    type: string;
    confidence_score?: number;
    hop_distance?: number;
}

export interface MethodUsageResponse {
    node_key: string;
    callers: MethodUsageItem[];
    callees: MethodUsageItem[];
    total_callers: number;
    total_callees: number;
}

export interface ComplexityTrendPoint {
    date: string;
    complexity: number;
}

export interface ComplexityTrendResponse {
    node_key: string;
    current_complexity: number;
    trend: ComplexityTrendPoint[];
    trend_available: boolean;
}

export interface CkMetric {
    namespace_key: string;
    class_name: string;
    project?: string;
    file?: string;
    layer?: string;
    wmc: number;
    cbo: number;
    rfc: number;
    lcom: number;
    risk_score: number;
    is_god_class: boolean;
    hotspot_score: number;
}

export interface EvolutionSummary {
    series: Array<{
        timestamp: string;
        risk_score: number;
        total_nodes: number;
        total_edges: number;
        god_classes: number;
        circular_deps: number;
        dead_code: number;
        call_resolution_rate?: number;
    }>;
    trend: {
        risk_delta: number;
        nodes_delta: number;
        edges_delta: number;
        call_resolution_delta?: number;
    };
    top_hotspots_by_project: Record<string, Array<{
        namespace_key: string;
        name: string;
        file: string;
        complexity: number;
        git_churn: number;
        hotspot_score: number;
    }>>;
    window_size: number;
}

export interface HotspotItem extends GraphNode {
    git_churn: number;
    hotspot_score: number;
    category?: 'critical' | 'danger' | 'watch' | 'low' | string;
}

export interface CochangePair {
    file_a: string;
    file_b: string;
    cochange_count: number;
}

export interface CallResolutionProject {
    project: string;
    total_calls: number;
    resolved_calls: number;
    unresolved_calls: number;
    resolution_rate: number;
}

export interface CallResolutionUnresolved {
    owner_hint?: string | null;
    method_hint: string;
    count: number;
    examples: Array<{
        source: string;
        source_name?: string;
        source_file?: string;
        source_project?: string;
    }>;
}

export interface CallResolutionSummary {
    total_calls: number;
    resolved_calls: number;
    unresolved_calls: number;
    resolution_rate: number;
    by_project: CallResolutionProject[];
    top_unresolved: CallResolutionUnresolved[];
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

export async function fetchTransactionView(nodeKey: string, maxDepth: number = 10): Promise<TransactionViewData> {
    const params = new URLSearchParams({ max_depth: String(maxDepth) });
    const res = await fetch(`${BASE}/transaction/${encodeURIComponent(nodeKey)}?${params.toString()}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchGraphPath(source: string, target: string, maxDepth: number = 12): Promise<PathFinderData> {
    const params = new URLSearchParams({
        source,
        target,
        max_depth: String(maxDepth),
    });
    const res = await fetch(`${BASE}/graph/paths?${params.toString()}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchTransactionExplain(nodeKey: string, maxDepth: number = 10): Promise<TransactionExplainData> {
    const params = new URLSearchParams({
        max_depth: String(maxDepth),
    });
    const res = await fetch(`${BASE}/transaction/${encodeURIComponent(nodeKey)}/explain?${params.toString()}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function listSavedViews(project?: string): Promise<{ items: SavedView[] }> {
    const params = new URLSearchParams();
    if (project) params.set('project', project);
    const suffix = params.toString();
    const res = await fetch(`${BASE}/views${suffix ? `?${suffix}` : ''}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function createSavedView(payload: SavedViewPayload): Promise<SavedView> {
    const res = await fetch(`${BASE}/views`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function updateSavedView(id: string, payload: Partial<SavedViewPayload>): Promise<SavedView> {
    const res = await fetch(`${BASE}/views/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function deleteSavedView(id: string): Promise<{ status: string; id: string }> {
    const res = await fetch(`${BASE}/views/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function listAnnotations(nodeKey?: string): Promise<{ items: any[] }> {
    const params = new URLSearchParams();
    if (nodeKey) params.set('node_key', nodeKey);
    const suffix = params.toString();
    const res = await fetch(`${BASE}/annotations${suffix ? `?${suffix}` : ''}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function createAnnotation(payload: AnnotationPayload): Promise<any> {
    const res = await fetch(`${BASE}/annotations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function updateAnnotation(id: string, payload: Partial<AnnotationPayload>): Promise<any> {
    const res = await fetch(`${BASE}/annotations/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function deleteAnnotation(id: string): Promise<{ status: string; id: string }> {
    const res = await fetch(`${BASE}/annotations/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function listTags(): Promise<{ items: Tag[] }> {
    const res = await fetch(`${BASE}/tags`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function upsertTag(name: string, color?: string): Promise<Tag> {
    const res = await fetch(`${BASE}/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, color }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export interface IsoRule {
    rule_id: string;
    name: string;
    weight: number;
    passed: boolean;
    notes: string;
    score: number;
}

export interface IsoQualityGrade {
    grade: string;
    score_percent: number;
    score_obtained: number;
    score_max: number;
    rules: IsoRule[];
}

export async function fetchIso5055(): Promise<IsoQualityGrade> {
    const res = await fetch(`${BASE}/quality/iso5055`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export interface OssVulnerability {
    id: string;
    aliases: string[];
    summary?: string;
    modified?: string;
}

export interface OssDependency {
    ecosystem: string;
    name: string;
    version?: string | null;
    source?: string | null;
    vulnerabilities: OssVulnerability[];
    vuln_count: number;
}

export interface OssExposureResponse {
    total_dependencies: number;
    total_vulnerabilities: number;
    items: OssDependency[];
}

export async function fetchOssExposure(limit: number = 120): Promise<OssExposureResponse> {
    const res = await fetch(`${BASE}/oss/exposure?limit=${encodeURIComponent(String(limit))}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchApiInventory(params?: { project?: string; method?: string; q?: string }): Promise<{ items: ApiInventoryResponseItem[] }> {
    const qs = new URLSearchParams();
    if (params?.project) qs.set('project', params.project);
    if (params?.method) qs.set('method', params.method);
    if (params?.q) qs.set('q', params.q);
    const suffix = qs.toString();
    const res = await fetch(`${BASE}/inventory/apis${suffix ? `?${suffix}` : ''}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchInheritance(project?: string, root?: string): Promise<any> {
    const qs = new URLSearchParams();
    if (project) qs.set('project', project);
    let url = '';
    if (root) {
        url = `${BASE}/inheritance/${encodeURIComponent(root)}`;
        const suffix = qs.toString();
        if (suffix) url += `?${suffix}`;
    } else {
        const suffix = qs.toString();
        url = `${BASE}/inheritance${suffix ? `?${suffix}` : ''}`;
    }
    const res = await fetch(url);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function exportFindings(format: 'json' | 'csv' = 'json'): Promise<any> {
    const res = await fetch(`${BASE}/findings/export?format=${format}`);
    if (!res.ok) throw new Error(await res.text());
    if (format === 'csv') return res.text();
    return res.json();
}

export async function triggerAdvancedCallResolver(maxCandidates: number = 5): Promise<any> {
    const res = await fetch(`${BASE}/calls/resolve/advanced?max_candidates=${encodeURIComponent(String(maxCandidates))}`, {
        method: 'POST',
    });
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

export interface QualityThresholds {
    max_god_classes: number;
    min_call_resolution: number;
    max_hotspot_score: number;
    min_iso5055: number;
}

export interface QualityGateResult {
    passed: boolean;
    violations: string[];
    score: number;
    metrics: {
        god_classes: number;
        call_resolution_rate: number;
        max_hotspot_score: number;
        iso_score_percent: number;
        iso_grade: string;
        rules: Array<{ rule_id: string; name: string; passed: boolean; notes: string; weight: number }>;
        snapshot_timestamp?: string;
    };
    thresholds: QualityThresholds;
    timestamp: string;
}

export async function evaluateQualityGate(thresholds: QualityThresholds): Promise<QualityGateResult> {
    const res = await fetch(`${BASE}/quality/gate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thresholds }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchQualityGateHistory(limit: number = 8): Promise<{ entries: QualityGateResult[] }> {
    const res = await fetch(`${BASE}/quality/history?limit=${encodeURIComponent(String(limit))}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export interface DebtQuickWin {
  namespace_key: string;
  name?: string;
  project?: string;
  file?: string;
  hotspot_score: number;
  dependents: number;
}

export interface DebtTrackerPayload {
  score: number;
  projection: number;
  history: Array<{ timestamp?: string; risk: number; nodes: number; edges: number }>;
  quick_wins: DebtQuickWin[];
}

export async function fetchDebtTracker(): Promise<DebtTrackerPayload> {
  const res = await fetch(`${BASE}/debt-tracker`);
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

export async function analyzeImpact(change: ChangeDescriptor): Promise<AffectedSet> {
    const res = await fetch(`${BASE}/impact/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(change),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchDataFlow(nodeKey: string): Promise<DataFlowChain> {
    const res = await fetch(`${BASE}/dataflow/${encodeURIComponent(nodeKey)}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchContractBreaks(): Promise<{ broken_contracts: ContractBreak[] }> {
    const res = await fetch(`${BASE}/contracts/broken`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchFieldNodes(nodeKey: string): Promise<{ field_nodes: FieldLevelNode[] }> {
    const res = await fetch(`${BASE}/fields/${encodeURIComponent(nodeKey)}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchFragility(nodeKey: string): Promise<FragilityDetail> {
    const res = await fetch(`${BASE}/fragility/${encodeURIComponent(nodeKey)}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchFragilityRanking(topN: number = 20): Promise<FragilityDetail[]> {
    const res = await fetch(`${BASE}/fragility/ranking?top_n=${encodeURIComponent(String(topN))}`);
    if (!res.ok) throw new Error(await res.text());
    const payload = await res.json();
    if (!Array.isArray(payload)) {
        throw new Error(`Ranking de fragilidade inválido: ${JSON.stringify(payload)}`);
    }
    return payload;
}

export async function fetchTaintPropagation(payload: {
    origin_key: string;
    change_type: string;
    old_type?: string;
    new_type?: string;
}): Promise<TaintPath> {
    const res = await fetch(`${BASE}/taint/propagate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function resolveSymbol(name: string, contextKey?: string): Promise<ResolvedSymbol[]> {
    const params = new URLSearchParams({ name });
    if (contextKey) params.set('context_key', contextKey);
    const res = await fetch(`${BASE}/symbol/resolve?${params.toString()}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchSideEffects(payload: {
    change: {
        change_type: string;
        target_key?: string;
        artifact_key?: string;
        old_type?: string;
        new_type?: string;
    };
    affected_set?: string[];
    include_inferred?: boolean;
}): Promise<SideEffect[]> {
    const res = await fetch(`${BASE}/side-effects/detect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchBidirectionalImpact(payload: {
    origin_key: string;
    direction: 'BOTTOM_UP' | 'TOP_DOWN';
    change?: Record<string, unknown>;
}): Promise<BidirectionalResult> {
    const res = await fetch(`${BASE}/bidirectional/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchNodeVulnerabilities(nodeKey: string): Promise<SecurityIssue[]> {
    const res = await fetch(`${BASE}/security/node/${encodeURIComponent(nodeKey)}/vulnerabilities`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchSecuritySummary(): Promise<SecuritySummary> {
    const res = await fetch(`${BASE}/security/summary`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchSecurityVulnerabilities(params?: {
    severity?: string;
    project?: string;
    ruleId?: string;
    limit?: number;
}): Promise<SecurityVulnerabilityListResponse> {
    const qs = new URLSearchParams();
    if (params?.severity) qs.set('severity', params.severity);
    if (params?.project) qs.set('project', params.project);
    if (params?.ruleId) qs.set('rule_id', params.ruleId);
    if (typeof params?.limit === 'number') qs.set('limit', String(params.limit));
    const suffix = qs.toString();
    const res = await fetch(`${BASE}/security/vulnerabilities${suffix ? `?${suffix}` : ''}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchTodos(params?: { type?: string; project?: string; file?: string }): Promise<TodoListResponse> {
    const qs = new URLSearchParams();
    if (params?.type) qs.set('type', params.type);
    if (params?.project) qs.set('project', params.project);
    if (params?.file) qs.set('file_path', params.file);
    const suffix = qs.toString();
    const res = await fetch(`${BASE}/todos${suffix ? `?${suffix}` : ''}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchGitBlame(params: { filePath?: string; nodeKey?: string }): Promise<GitBlameInfo> {
    const qs = new URLSearchParams();
    if (params.filePath) qs.set('file_path', params.filePath);
    if (params.nodeKey) qs.set('node_key', params.nodeKey);
    const suffix = qs.toString();
    const res = await fetch(`${BASE}/git/blame${suffix ? `?${suffix}` : ''}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchMethodUsages(nodeKey: string): Promise<MethodUsageResponse> {
    const res = await fetch(`${BASE}/method/${encodeURIComponent(nodeKey)}/usages`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchComplexityTrend(nodeKey: string): Promise<ComplexityTrendResponse> {
    const res = await fetch(`${BASE}/method/${encodeURIComponent(nodeKey)}/complexity-trend`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchHotspots(topN: number = 50, days?: number): Promise<{ hotspots: HotspotItem[]; window_days?: number | null }> {
    const params = new URLSearchParams({ top_n: String(topN) });
    if (typeof days === 'number' && days > 0) params.set('days', String(days));
    const res = await fetch(`${BASE}/hotspots?${params.toString()}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function ragSearch(
    query: string,
    nodeKey?: string,
    limit: number = 20,
    semantic: boolean = true,
): Promise<{ nodes: GraphNode[] }> {
    const params = new URLSearchParams({ q: query, limit: String(limit) });
    if (nodeKey) params.set('node_key', nodeKey);
    params.set('semantic', String(semantic));
    const res = await fetch(`${BASE}/rag/search?${params.toString()}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export type SemanticSearchMode = 'code' | 'arch' | 'impact';

export interface SemanticSearchResult extends GraphNode {
    preview: string;
    summary?: string;
    rag_score?: number;
    hotspot_score?: number;
    model?: string;
    highlight_terms: string[];
}

export interface SemanticSearchResponse {
    results: SemanticSearchResult[];
    query: string;
    mode: SemanticSearchMode;
    count: number;
    context_nodes: string[];
    context_summary: string;
}

export async function semanticSearch(
    query: string,
    mode: SemanticSearchMode = 'code',
    topK: number = 20,
    nodeKey?: string,
    semantic: boolean = true,
): Promise<SemanticSearchResponse> {
    const params = new URLSearchParams({
        q: query.trim(),
        mode,
        top_k: String(topK),
        semantic: semantic ? 'true' : 'false',
    });
    if (nodeKey) params.set('node_key', nodeKey);
    const res = await fetch(`${BASE}/search/semantic?${params.toString()}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function rebuildRagIndex(includeEmbeddings: boolean = false): Promise<{
    indexed_nodes: number;
    status: string;
    include_embeddings?: boolean;
    embedding_model?: string | null;
}> {
    const res = await fetch(`${BASE}/rag/index`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ include_embeddings: includeEmbeddings }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchCkMetrics(project?: string, minRisk: number = 0): Promise<{ metrics: CkMetric[]; total: number }> {
    const params = new URLSearchParams({ min_risk: String(minRisk) });
    if (project) params.set('project', project);
    const res = await fetch(`${BASE}/metrics/ck?${params.toString()}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function semanticGraphSearch(
    query: string,
    topK: number = 20,
    nodeKey?: string,
    semantic: boolean = true,
): Promise<{ results: GraphNode[]; query: string }> {
    const params = new URLSearchParams({ q: query, top_k: String(topK) });
    if (nodeKey) params.set('node_key', nodeKey);
    params.set('semantic', String(semantic));
    const res = await fetch(`${BASE}/graph/search?${params.toString()}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchEvolutionSummary(window: number = 20): Promise<EvolutionSummary> {
    const res = await fetch(`${BASE}/evolution/summary?window=${encodeURIComponent(String(window))}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchHotspotCochange(days: number = 90, topN: number = 30): Promise<{ projects: Record<string, CochangePair[]>; window_days: number }> {
    const params = new URLSearchParams({ days: String(days), top_n: String(topN) });
    const res = await fetch(`${BASE}/hotspots/cochange?${params.toString()}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchCallResolutionSummary(project?: string, topN: number = 20): Promise<CallResolutionSummary> {
    const params = new URLSearchParams({ top_n: String(topN) });
    if (project) params.set('project', project);
    const res = await fetch(`${BASE}/calls/resolution?${params.toString()}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchHealth(): Promise<HealthStatus> {
    const res = await fetch(`${BASE}/health`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchRagStatus(): Promise<RagStatus> {
    const res = await fetch(`${BASE}/rag/status`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchHistory(): Promise<HistorySnapshot[]> {
    const res = await fetch(`${BASE}/history`);
    if (!res.ok) return []; // fail gracefully for history
    return res.json();
}

export async function fetchFileContent(filePath: string, project?: string): Promise<{ content: string; file_path: string }> {
    let url = `${BASE}/file/content?file_path=${encodeURIComponent(filePath)}`;
    if (project) {
        url += `&project=${encodeURIComponent(project)}`;
    }
    const res = await fetch(url);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function explainComponent(code: string): Promise<{ answer: string }> {
    const prompt = `Explique em 3 ou 4 linhas simples o que este código faz e qual a sua responsabilidade no sistema:\n\n${code}`;
    const res = await fetch(`${BASE}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: prompt }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

// ============================================
// CodeQL API Functions
// ============================================

export interface CodeQLProject {
    id: string;
    name: string;
    source_path: string;
    language: string;
    database_path: string;
    created_at: string;
    last_analyzed: string | null;
}

export interface CodeQLJob {
    job_id: string;
    project_id: string;
    project_name: string;
    status: 'queued' | 'running' | 'completed' | 'failed';
    stage: string;
    progress: number;
    created_at: string;
    started_at: string | null;
    completed_at: string | null;
    error: string | null;
}

export interface CodeQLAnalysisResult {
    vulnerabilities_count: number;
    ingested_count: number;
    skipped_count: number;
    tainted_paths_count: number;
}

export interface CodeQLResultsSummary {
    total_issues: number;
    ingested: number;
    skipped: number;
    tainted_paths: number;
    vulnerabilities_by_severity: Record<string, number>;
}

export interface CodeQLHistoryEntry {
    job_id: string;
    project_id: string;
    project_name: string;
    started_at: string;
    completed_at: string;
    duration_seconds: number;
    suite: string;
    status: 'completed' | 'failed' | string;
    results_summary?: CodeQLResultsSummary | null;
    sarif_path?: string | null;
    sarif_size_bytes?: number | null;
    error_message?: string | null;
}

// Fetch all CodeQL projects
export async function fetchCodeQLProjects(): Promise<CodeQLProject[]> {
    const res = await fetch(`${BASE}/codeql/projects`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

// Create a new CodeQL project
export async function createCodeQLProject(
    name: string,
    sourcePath: string,
    language?: string
): Promise<CodeQLProject> {
    const res = await fetch(`${BASE}/codeql/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name,
            source_path: sourcePath,
            language,
        }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

// Update a CodeQL project
export async function updateCodeQLProject(
    projectId: string,
    sourcePath: string
): Promise<CodeQLProject> {
    const res = await fetch(`${BASE}/codeql/projects/${projectId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            source_path: sourcePath,
        }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

// Delete a CodeQL project
export async function deleteCodeQLProject(projectId: string): Promise<void> {
    const res = await fetch(`${BASE}/codeql/projects/${projectId}`, {
        method: 'DELETE',
    });
    if (!res.ok) throw new Error(await res.text());
}

// Delete a CodeQL project's database
export async function deleteCodeQLDatabase(projectId: string): Promise<void> {
    const res = await fetch(`${BASE}/codeql/projects/${projectId}/database`, {
        method: 'DELETE',
    });
    if (!res.ok) throw new Error(await res.text());
}

// Start CodeQL analysis
export async function startCodeQLAnalysis(
    projectId: string,
    suite: string = 'security-and-quality'
): Promise<{ job_id: string }> {
    const res = await fetch(`${BASE}/codeql/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            project_id: projectId,
            suite,
        }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

// Get CodeQL job status
export async function getCodeQLJobStatus(jobId: string): Promise<CodeQLJob> {
    const res = await fetch(`${BASE}/codeql/jobs/${jobId}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

// Get CodeQL analysis results
export async function getCodeQLResults(projectId: string): Promise<CodeQLAnalysisResult> {
    const res = await fetch(`${BASE}/codeql/results/${projectId}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function fetchCodeQLHistory(params?: {
    projectId?: string;
    startDate?: string;
    endDate?: string;
    limit?: number;
}): Promise<CodeQLHistoryEntry[]> {
    const qs = new URLSearchParams();
    if (params?.projectId) qs.set('project_id', params.projectId);
    if (params?.startDate) qs.set('start_date', params.startDate);
    if (params?.endDate) qs.set('end_date', params.endDate);
    if (typeof params?.limit === 'number') qs.set('limit', String(params.limit));
    const suffix = qs.toString();
    const url = suffix ? `${BASE}/codeql/history?${suffix}` : `${BASE}/codeql/history`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}
