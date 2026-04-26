import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Sidebar from './components/Sidebar';
import GraphCanvas from './components/GraphCanvas';
import type { GraphCanvasHandle } from './components/GraphCanvas';
import NodeDetail from './components/NodeDetail';
import WorkspaceHub from './components/WorkspaceHub';
import SecurityDashboard from './components/SecurityDashboard';
import Timeline4D from './components/Timeline4D';
import CollaborationUI from './components/CollaborationUI';
import AutoHealerPanel from './components/AutoHealerPanel';
import AskPanel from './components/AskPanel';
import HandGestureController, { type GestureCommand } from './components/HandGestureController';
import { LiveAlertFeed } from './components/LiveAlertFeed';
import { CommitTimeline } from './components/CommitTimeline';
import { WeeklyDigestPanel } from './components/WeeklyDigestPanel';
import SettingsScreen from './components/SettingsScreen';
import WatchModePanel from './components/WatchModePanel';
import ImpactAnalysisPanel from './components/ImpactAnalysisPanel';
import ProjectManagement from './components/ProjectManagement';
import ImpactNotification, { type ImpactNotificationEntry } from './components/ImpactNotification';
import { useWatchMode } from './hooks/useWatchMode';
import {
  fetchBlastRadius,
  fetchGraph,
  fetchImpact,
  fetchProjects,
  cancelScan,
  getScanStatus,
  listAnnotations,
  listTags,
  startScan,
  type StartScanRequest,
  type AnnotationRecord,
  type GraphNode,
  type Tag,
} from './api';
import './index.css';

const NODE_TYPE_OPTIONS = [
  { value: 'Java_Class', label: 'Classe Java' },
  { value: 'Java_Method', label: 'Método Java' },
  { value: 'API_Endpoint', label: 'API Endpoint' },
  { value: 'TS_Component', label: 'Componente TS' },
  { value: 'TS_Function', label: 'Função TS' },
  { value: 'SQL_Table', label: 'Tabela SQL' },
  { value: 'SQL_Procedure', label: 'Procedure SQL' },
];

const ensureArray = <T,>(value: T[] | Record<string, T> | null | undefined): T[] => {
  if (Array.isArray(value)) return value;
  if (!value) return [];
  return Object.values(value) as T[];
};

interface LiveChangeState {
  source: 'watch' | 'sse' | 'fallback';
  file?: string;
  changedNodes: string[];
  impactedNodes: string[];
  newNodes: string[];
  removedNodes: string[];
  riskScore: number;
  summary?: string;
  timestamp: number;
}

const uniqueKeys = (values: string[]): string[] => {
  const seen = new Set<string>();
  const result: string[] = [];
  values.forEach((value) => {
    const key = value.trim();
    if (!key || seen.has(key)) return;
    seen.add(key);
    result.push(key);
  });
  return result;
};

export default function App() {
  const graphCanvasRef = useRef<GraphCanvasHandle>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const [workspaces, setWorkspaces] = useState<string[]>([]);
  const [projects, setProjects] = useState<string[]>([]);
  const [selectedProjects, setSelectedProjects] = useState<string[]>([]);
  const [selectedLayer, setSelectedLayer] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [fileFilter, setFileFilter] = useState('');
  const [impactOnly, setImpactOnly] = useState(false);
  const [selectedNodeTypes, setSelectedNodeTypes] = useState<string[]>(NODE_TYPE_OPTIONS.map((item) => item.value));
  const [hotspotRange, setHotspotRange] = useState<[number, number]>([0, 100]);
  const [complexityRange, setComplexityRange] = useState<[number, number]>([0, 80]);
  const [selectedTagFilter, setSelectedTagFilter] = useState<string | null>(null);

  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<Array<{ source: string; target: string; type: string }>>([]);
  const [annotationsIndex, setAnnotationsIndex] = useState<Record<string, AnnotationRecord[]>>({});
  const [tagsForFilter, setTagsForFilter] = useState<Tag[]>([]);

  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedNodeKey, setSelectedNodeKey] = useState<string | null>(null);
  const [impactData, setImpactData] = useState<any | null>(null);
  const [blastRadius, setBlastRadius] = useState<any | null>(null);
  const [highlightedUpstream, setHighlightedUpstream] = useState<Set<string>>(new Set());
  const [highlightedDownstream, setHighlightedDownstream] = useState<Set<string>>(new Set());
  const [aiHighlightedNodes, setAiHighlightedNodes] = useState<string[]>([]);

  const [scanStatus, setScanStatus] = useState('idle');
  const [scanStats, setScanStats] = useState({ files: 0, nodes: 0, rels: 0, progress: 0, currentFile: '' });
  const [scanErrors, setScanErrors] = useState<string[]>([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [homeViewOpen, setHomeViewOpen] = useState(true);
  const [legendOpen, setLegendOpen] = useState(false);
  const [gestureCursor, setGestureCursor] = useState<{ x: number; y: number; active: boolean }>({ x: 0, y: 0, active: false });
  const [gestureCommand, setGestureCommand] = useState<(GestureCommand & { timestamp: number }) | null>(null);

  const [securityOpen, setSecurityOpen] = useState(false);
  const [timeline4DOpen, setTimeline4DOpen] = useState(false);
  const [collaborationOpen, setCollaborationOpen] = useState(false);
  const [autoHealerOpen, setAutoHealerOpen] = useState(false);
  const [liveAlertsOpen, setLiveAlertsOpen] = useState(false);
  const [commitTimelineOpen, setCommitTimelineOpen] = useState(false);
  const [weeklyDigestOpen, setWeeklyDigestOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [watchModeOpen, setWatchModeOpen] = useState(false);
  const [impactAnalysisOpen, setImpactAnalysisOpen] = useState(false);
  const [projectManagementOpen, setProjectManagementOpen] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  const [askInitialMessage, setAskInitialMessage] = useState<string | undefined>();
  const [liveChangeState, setLiveChangeState] = useState<LiveChangeState | null>(null);
  const [impactToasts, setImpactToasts] = useState<ImpactNotificationEntry[]>([]);
  const watchMode = useWatchMode();
  const graphNodesRef = useRef<GraphNode[]>([]);
  const refreshInFlightRef = useRef(false);
  const refreshPendingRef = useRef(false);

  const closeAllPanels = useCallback(() => {
    setSecurityOpen(false);
    setTimeline4DOpen(false);
    setCollaborationOpen(false);
    setAutoHealerOpen(false);
    setLiveAlertsOpen(false);
    setCommitTimelineOpen(false);
    setWeeklyDigestOpen(false);
    setSettingsOpen(false);
    setWatchModeOpen(false);
    setImpactAnalysisOpen(false);
    setProjectManagementOpen(false);
    setAskOpen(false);
  }, []);

  useEffect(() => {
    graphNodesRef.current = graphNodes;
  }, [graphNodes]);

  const registerLiveChange = useCallback((payload: {
    source: 'watch' | 'sse' | 'fallback';
    file?: string;
    changedNodes?: string[];
    impactedNodes?: string[];
    riskScore?: number;
    summary?: string;
  }, nextNodes: GraphNode[]) => {
    const prevNodeKeys = new Set(graphNodesRef.current.map((node) => node.namespace_key));
    const nextNodeKeys = new Set(nextNodes.map((node) => node.namespace_key));

    const newNodes = Array.from(nextNodeKeys).filter((key) => !prevNodeKeys.has(key));
    const removedNodes = Array.from(prevNodeKeys).filter((key) => !nextNodeKeys.has(key));

    const changedNodes = uniqueKeys(payload.changedNodes || []);
    const impactedNodes = uniqueKeys(payload.impactedNodes || []);

    const runtime: LiveChangeState = {
      source: payload.source,
      file: payload.file,
      changedNodes,
      impactedNodes,
      newNodes,
      removedNodes,
      riskScore: payload.riskScore || 0,
      summary: payload.summary,
      timestamp: Date.now(),
    };

    setLiveChangeState(runtime);

    const highlight = uniqueKeys([
      ...runtime.changedNodes,
      ...runtime.impactedNodes,
      ...runtime.newNodes,
    ]);
    if (highlight.length > 0) {
      setAiHighlightedNodes(highlight.slice(0, 120));
    }

    if (runtime.impactedNodes.length > 0 || runtime.changedNodes.length > 0) {
      const focusNode = runtime.changedNodes[0] || runtime.impactedNodes[0];
      if (focusNode) {
        const severity: ImpactNotificationEntry['severity'] =
          runtime.riskScore >= 70 ? 'high' : runtime.riskScore >= 35 ? 'medium' : 'low';
        setImpactToasts((prev) => [
          {
            id: `${runtime.timestamp}-${focusNode}`,
            nodeKey: focusNode,
            fileName: runtime.file || focusNode,
            affectedCount: Math.max(runtime.impactedNodes.length, runtime.changedNodes.length),
            severity,
            timestamp: runtime.timestamp,
            autoHide: true,
          },
          ...prev,
        ].slice(0, 6));
      }
    }
  }, []);

  const loadGraph = useCallback(async (livePayload?: {
    source: 'watch' | 'sse' | 'fallback';
    file?: string;
    changedNodes?: string[];
    impactedNodes?: string[];
    riskScore?: number;
    summary?: string;
  }) => {
    try {
      const projectFilter = selectedProjects.length === 1 ? selectedProjects[0] : undefined;
      const data = await fetchGraph(projectFilter, selectedLayer || undefined);
      const nextNodes = ensureArray<GraphNode>(data.nodes);
      setGraphNodes(nextNodes);
      setGraphEdges(ensureArray(data.edges));
      setProjects(await fetchProjects());
      if (livePayload) {
        registerLiveChange(livePayload, nextNodes);
      }
    } catch (err) {
      console.error('Failed to load graph', err);
    }
  }, [registerLiveChange, selectedLayer, selectedProjects]);

  const loadTags = useCallback(async () => {
    try {
      const payload = await listTags();
      setTagsForFilter(payload.items);
    } catch {
      setTagsForFilter([]);
    }
  }, []);

  const loadAnnotations = useCallback(async () => {
    try {
      const payload = await listAnnotations();
      const index: Record<string, AnnotationRecord[]> = {};
      payload.items.forEach((item: AnnotationRecord) => {
        if (!index[item.node_key]) index[item.node_key] = [];
        index[item.node_key].push(item);
      });
      setAnnotationsIndex(index);
    } catch {
      setAnnotationsIndex({});
    }
  }, []);

  const refreshGraphPredictably = useCallback(async (livePayload?: {
    source: 'watch' | 'sse' | 'fallback';
    file?: string;
    changedNodes?: string[];
    impactedNodes?: string[];
    riskScore?: number;
    summary?: string;
  }) => {
    if (refreshInFlightRef.current) {
      refreshPendingRef.current = true;
      return;
    }
    refreshInFlightRef.current = true;
    try {
      await loadGraph(livePayload);
    } finally {
      refreshInFlightRef.current = false;
      if (refreshPendingRef.current) {
        refreshPendingRef.current = false;
        await refreshGraphPredictably(livePayload);
      }
    }
  }, [loadGraph]);

  useEffect(() => {
    loadGraph();
    loadTags();
    loadAnnotations();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [loadGraph, loadTags, loadAnnotations]);

  useEffect(() => {
    const source = new EventSource('/api/events');

    const onGraphUpdated = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data || '{}');
        const changedNodes = Array.isArray(payload?.changed_nodes) ? payload.changed_nodes : [];
        const directImpacted = Array.isArray(payload?.affected_nodes) ? payload.affected_nodes : [];
        const crossImpacted = Array.isArray(payload?.cross_project?.affected)
          ? payload.cross_project.affected
            .map((item: any) => item?.node_key)
            .filter((item: unknown): item is string => typeof item === 'string' && item.length > 0)
          : [];
        void refreshGraphPredictably({
          source: 'sse',
          file: typeof payload?.file === 'string' ? payload.file : undefined,
          changedNodes,
          impactedNodes: [...directImpacted, ...crossImpacted],
          riskScore: typeof payload?.risk_score === 'number' ? payload.risk_score : 0,
          summary: typeof payload?.summary === 'string' ? payload.summary : undefined,
        });
      } catch {
        void refreshGraphPredictably({ source: 'sse' });
      }
    };
    const onScanComplete = () => {
      void refreshGraphPredictably({ source: 'sse' });
    };
    const onImpactDetected = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data);
        const affected = Array.isArray(payload?.affected) ? payload.affected : [];
        const impactedNodes = affected
          .map((item: any) => item?.node_key)
          .filter((value: unknown): value is string => typeof value === 'string' && value.length > 0);
        if (impactedNodes.length > 0) {
          void refreshGraphPredictably({
            source: 'sse',
            changedNodes: Array.isArray(payload?.changed_nodes) ? payload.changed_nodes : [],
            impactedNodes,
            riskScore: typeof payload?.breaking_count === 'number' ? Math.min(100, payload.breaking_count * 25) : 0,
          });
        }
      } catch {
        // ignore malformed payload
      }
    };

    source.addEventListener('graph_updated', onGraphUpdated);
    source.addEventListener('scan_complete', onScanComplete);
    source.addEventListener('impact_detected', onImpactDetected as EventListener);

    return () => {
      source.removeEventListener('graph_updated', onGraphUpdated);
      source.removeEventListener('scan_complete', onScanComplete);
      source.removeEventListener('impact_detected', onImpactDetected as EventListener);
      source.close();
    };
  }, [refreshGraphPredictably]);

  useEffect(() => {
    if (!watchMode.lastImpact) return;
    const impact = watchMode.lastImpact;
    void refreshGraphPredictably({
      source: 'watch',
      file: impact.file,
      changedNodes: impact.changed_nodes || [],
      impactedNodes: impact.affected_nodes || [],
      riskScore: impact.risk_score,
      summary: impact.summary,
    });
  }, [refreshGraphPredictably, watchMode.lastImpact]);

  useEffect(() => {
    if (watchMode.watching) return;
    const fallbackInterval = setInterval(() => {
      if (scanStatus === 'scanning') return;
      void refreshGraphPredictably({ source: 'fallback' });
    }, 20000);
    return () => clearInterval(fallbackInterval);
  }, [refreshGraphPredictably, scanStatus, watchMode.watching]);

  const handleScan = useCallback(async (payload: StartScanRequest) => {
    if ((payload.mode ?? 'local') === 'local' && workspaces.length === 0) return;
    setHomeViewOpen(true);
    const mode = payload.mode ?? 'local';
    const request: StartScanRequest =
      mode === 'github'
        ? payload
        : { ...payload, mode: 'local', paths: workspaces };
    await startScan(request);
    setScanStatus('scanning');
    setScanErrors([]);
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const status = await getScanStatus();
        setScanStats({
          files: status.scanned_files,
          nodes: status.total_nodes,
          rels: status.total_relationships,
          progress: status.progress_percent,
          currentFile: status.current_file,
        });
        setScanErrors(status.errors || []);
        if (status.status !== 'scanning') {
          setScanStatus(status.status);
          if (pollRef.current) clearInterval(pollRef.current);
          void refreshGraphPredictably({ source: 'sse' });
        }
      } catch {
        setScanStatus('error');
      }
    }, 1400);
  }, [refreshGraphPredictably, workspaces]);

  const handleCancelScan = useCallback(async () => {
    try {
      await cancelScan();
    } catch {
      // ignore
    }
  }, []);

  const handleGestureCommand = useCallback((command: GestureCommand) => {
    setGestureCommand({ ...command, timestamp: Date.now() });
  }, []);

  const handleNodeClick = useCallback(async (nodeKey: string, nodeData: GraphNode) => {
    setHomeViewOpen(false);
    setSelectedNodeKey(nodeKey);
    setSelectedNode(nodeData);
    try {
      const [impact, br] = await Promise.all([fetchImpact(nodeKey), fetchBlastRadius(nodeKey)]);
      setImpactData(impact);
      setBlastRadius(br);
      setHighlightedUpstream(new Set((impact.upstream || []).map((n: any) => n.key)));
      setHighlightedDownstream(new Set((impact.downstream || []).map((n: any) => n.key)));
    } catch {
      setImpactData(null);
      setBlastRadius(null);
      setHighlightedUpstream(new Set());
      setHighlightedDownstream(new Set());
    }
  }, []);

  const handleOpenAsk = useCallback(() => {
    if (selectedNode) {
      setAskInitialMessage(`Se eu alterar ${selectedNode.name}, o que pode quebrar nos projetos dependentes?`);
    } else {
      setAskInitialMessage(undefined);
    }
    setAskOpen(true);
  }, [selectedNode]);

  const liveChangedSet = useMemo(() => new Set(liveChangeState?.changedNodes || []), [liveChangeState?.changedNodes]);
  const liveNewSet = useMemo(() => new Set(liveChangeState?.newNodes || []), [liveChangeState?.newNodes]);
  const liveImpactedSet = useMemo(() => new Set(liveChangeState?.impactedNodes || []), [liveChangeState?.impactedNodes]);

  const runtimeGraphNodes = useMemo(() => {
    if (!liveChangeState) return graphNodes;
    return graphNodes.map((node) => {
      let liveChange: GraphNode['live_change_state'] | undefined;
      if (liveNewSet.has(node.namespace_key)) liveChange = 'new';
      else if (liveChangedSet.has(node.namespace_key)) liveChange = 'changed';
      else if (liveImpactedSet.has(node.namespace_key)) liveChange = 'impacted';
      return {
        ...node,
        live_change_state: liveChange,
      };
    });
  }, [graphNodes, liveChangeState, liveChangedSet, liveImpactedSet, liveNewSet]);

  const filteredGraphNodes = useMemo(() => {
    const [hotMin, hotMax] = hotspotRange;
    const [compMin, compMax] = complexityRange;
    const fileTerm = fileFilter.trim().toLowerCase();
    const q = searchTerm.trim().toLowerCase();
    return runtimeGraphNodes.filter((node) => {
      const hotspot = node.hotspot_score ?? 0;
      const complexity = node.complexity ?? 0;
      const labels = node.labels ?? [];
      if (hotspot < hotMin || hotspot > hotMax) return false;
      if (complexity < compMin || complexity > compMax) return false;
      if (selectedNodeTypes.length && !labels.some((label) => selectedNodeTypes.includes(label))) return false;
      if (fileTerm && !(node.file || '').toLowerCase().includes(fileTerm)) return false;
      if (q && !node.name.toLowerCase().includes(q)) return false;
      if (selectedTagFilter) {
        const anns = annotationsIndex[node.namespace_key] || [];
        const hasTag = anns.some((ann) => ann.tag === selectedTagFilter);
        if (!hasTag) return false;
      }
      if (impactOnly && !(typeof node.impact_distance === 'number' && node.impact_distance > 0)) return false;
      return true;
    });
  }, [annotationsIndex, complexityRange, fileFilter, hotspotRange, impactOnly, runtimeGraphNodes, searchTerm, selectedNodeTypes, selectedTagFilter]);

  const filteredGraphEdges = useMemo(() => {
    const visible = new Set(filteredGraphNodes.map((n) => n.namespace_key));
    return graphEdges.filter((edge) => visible.has(edge.source) && visible.has(edge.target));
  }, [filteredGraphNodes, graphEdges]);

  const availableFiles = useMemo(() => {
    const files = new Set<string>();
    graphNodes.forEach((node) => {
      if (node.file) files.add(node.file);
    });
    return Array.from(files).sort();
  }, [graphNodes]);

  const nodeAnnotationMeta = useMemo(() => {
    const map = new Map<string, { tag?: string; color?: string | null }>();
    Object.entries(annotationsIndex).forEach(([key, list]) => {
      const first = list[0];
      map.set(key, { tag: first?.tag ?? undefined, color: first?.tag_color ?? null });
    });
    return map;
  }, [annotationsIndex]);

  return (
    <div className={`app-layout no-topbar ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <Sidebar
        workspaces={workspaces}
        onRemoveWorkspace={(path) => setWorkspaces((prev) => prev.filter((p) => p !== path))}
        projects={projects}
        selectedProjects={selectedProjects}
        onToggleProject={(project) => setSelectedProjects((prev) => prev.includes(project) ? prev.filter((p) => p !== project) : [...prev, project])}
        onDeleteProject={() => undefined}
        selectedLayer={selectedLayer}
        onLayerChange={setSelectedLayer}
        searchTerm={searchTerm}
        onSearchChange={setSearchTerm}
        searchInputRef={searchInputRef}
        scanStatus={scanStatus}
        nodeCount={graphNodes.length}
        edgeCount={graphEdges.length}
        tags={tagsForFilter}
        selectedTag={selectedTagFilter}
        onTagSelect={setSelectedTagFilter}
        nodeTypeOptions={NODE_TYPE_OPTIONS}
        selectedNodeTypes={selectedNodeTypes}
        onToggleNodeType={(type) => setSelectedNodeTypes((prev) => prev.includes(type) ? prev.filter((x) => x !== type) : [...prev, type])}
        hotspotRange={hotspotRange}
        complexityRange={complexityRange}
        onHotspotRangeChange={(idx, value) => setHotspotRange((prev) => idx === 0 ? [Math.min(value, prev[1]), prev[1]] : [prev[0], Math.max(prev[0], value)])}
        onComplexityRangeChange={(idx, value) => setComplexityRange((prev) => idx === 0 ? [Math.min(value, prev[1]), prev[1]] : [prev[0], Math.max(prev[0], value)])}
        availableFiles={availableFiles}
        fileFilter={fileFilter}
        onFileFilterChange={setFileFilter}
        impactOnly={impactOnly}
        onImpactOnlyToggle={() => setImpactOnly((prev) => !prev)}
        visibleNodeCount={filteredGraphNodes.length}
        totalNodeCount={graphNodes.length}
        isCollapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((prev) => !prev)}
        onNodeClick={(nodeKey) => {
          const node = graphNodes.find((n) => n.namespace_key === nodeKey);
          if (node) handleNodeClick(nodeKey, node);
        }}
        homeOpen={homeViewOpen}
        onOpenHome={() => { closeAllPanels(); setHomeViewOpen(true); }}
        dashboardOpen={scanStatus === 'scanning'}
        onOpenDashboard={() => handleScan({ mode: 'local' })}
        securityOpen={securityOpen}
        onOpenSecurity={() => { closeAllPanels(); setSecurityOpen(true); }}
        timelineOpen={timeline4DOpen}
        onOpenTimeline={() => { closeAllPanels(); setTimeline4DOpen(true); }}
        collaborationOpen={collaborationOpen}
        onOpenCollaboration={() => { closeAllPanels(); setCollaborationOpen(true); }}
        autoHealerOpen={autoHealerOpen}
        onOpenAutoHealer={() => { closeAllPanels(); setAutoHealerOpen(true); }}
        liveAlertsOpen={liveAlertsOpen}
        onOpenLiveAlerts={() => { closeAllPanels(); setLiveAlertsOpen(true); }}
        settingsOpen={settingsOpen}
        onOpenSettings={() => { closeAllPanels(); setSettingsOpen(true); }}
        watchModeOpen={watchModeOpen}
        onOpenWatchMode={() => { closeAllPanels(); setWatchModeOpen(true); }}
        commitTimelineOpen={commitTimelineOpen}
        onOpenCommitTimeline={() => { closeAllPanels(); setCommitTimelineOpen(true); }}
        weeklyDigestOpen={weeklyDigestOpen}
        onOpenWeeklyDigest={() => { closeAllPanels(); setWeeklyDigestOpen(true); }}
        projectManagementOpen={projectManagementOpen}
        onOpenProjectManagement={() => { closeAllPanels(); setProjectManagementOpen(true); }}
      />

      <div className="app-main">
        {projectManagementOpen ? (
          <ProjectManagement />
        ) : homeViewOpen ? (
          <WorkspaceHub
            workspaces={workspaces}
            onAddWorkspace={(path) => setWorkspaces((prev) => prev.includes(path) ? prev : [...prev, path])}
            onRemoveWorkspace={(path) => setWorkspaces((prev) => prev.filter((p) => p !== path))}
            projects={projects}
            graphNodes={graphNodes}
            selectedProjects={selectedProjects}
            scanStatus={scanStatus}
            scanStats={scanStats}
            scanErrors={scanErrors}
            onScan={handleScan}
            onCancelScan={handleCancelScan}
            onOpenProjectGraph={(project) => { setSelectedProjects([project]); setHomeViewOpen(false); }}
            onOpenAllGraphs={() => { setSelectedProjects([]); setHomeViewOpen(false); }}
            onOpenTimeline={() => { closeAllPanels(); setTimeline4DOpen(true); }}
            onOpenSecurity={() => { closeAllPanels(); setSecurityOpen(true); }}
            onOpenCollaboration={() => { closeAllPanels(); setCollaborationOpen(true); }}
            onOpenAutoHealer={() => { closeAllPanels(); setAutoHealerOpen(true); }}
            onOpenLiveAlerts={() => { closeAllPanels(); setLiveAlertsOpen(true); }}
            onOpenCommitTimeline={() => { closeAllPanels(); setCommitTimelineOpen(true); }}
            onOpenWeeklyDigest={() => { closeAllPanels(); setWeeklyDigestOpen(true); }}
            onOpenSettings={() => { closeAllPanels(); setSettingsOpen(true); }}
            onOpenProjectManagement={() => { closeAllPanels(); setProjectManagementOpen(true); }}
          />
        ) : (
          <div className="graph-layout">
            <GraphCanvas
              graphNodes={filteredGraphNodes}
              graphEdges={filteredGraphEdges}
              highlightedUpstream={highlightedUpstream}
              highlightedDownstream={highlightedDownstream}
              aiHighlightedNodes={aiHighlightedNodes}
              changedNodes={liveChangedSet}
              newlyAddedNodes={liveNewSet}
              runtimeImpactedNodes={liveImpactedSet}
              selectedNodeKey={selectedNodeKey}
              onNodeClick={handleNodeClick}
              onClearAiHighlights={() => setAiHighlightedNodes([])}
              searchTerm={searchTerm}
              nodeAnnotations={nodeAnnotationMeta}
              selectedTag={selectedTagFilter}
              tagFilterNodes={undefined}
              onCanvasClick={() => {
                setSelectedNodeKey(null);
                setSelectedNode(null);
              }}
              gestureCursor={gestureCursor}
              gestureCommand={gestureCommand}
              ref={graphCanvasRef}
            />
            <div className="legend-region">
              <button className="legend-toggle" onClick={() => setLegendOpen((prev) => !prev)} type="button">
                {legendOpen ? 'Ocultar legenda' : 'Legenda'}
              </button>
            </div>
            <NodeDetail
              node={selectedNode}
              impact={impactData}
              blastRadius={blastRadius}
              onClose={() => setSelectedNode(null)}
              onViewUsages={() => undefined}
              onQuickImpactScenario={() => undefined}
              onOpenTransaction={() => undefined}
              onAnnotationsChanged={loadAnnotations}
              quickActions={[]}
            />
          </div>
        )}
      </div>

      {securityOpen && <SecurityDashboard onClose={() => setSecurityOpen(false)} onFocusNode={() => undefined} onOpenImpactAnalysis={() => setImpactAnalysisOpen(true)} />}
      {timeline4DOpen && <Timeline4D onCommitSelected={() => undefined} onReturnToPresent={loadGraph} onClose={() => setTimeline4DOpen(false)} repoPath="." />}
      {collaborationOpen && <CollaborationUI selectedNodeKey={selectedNodeKey} onClose={() => setCollaborationOpen(false)} />}
      {autoHealerOpen && <AutoHealerPanel selectedNode={selectedNode} onClose={() => setAutoHealerOpen(false)} />}
      {liveAlertsOpen && <LiveAlertFeed onClose={() => setLiveAlertsOpen(false)} />}
      {commitTimelineOpen && <CommitTimeline onClose={() => setCommitTimelineOpen(false)} />}
      {weeklyDigestOpen && <WeeklyDigestPanel onClose={() => setWeeklyDigestOpen(false)} />}
      {settingsOpen && <SettingsScreen onClose={() => setSettingsOpen(false)} />}
      {watchModeOpen && (
        <WatchModePanel
          connected={watchMode.connected}
          watching={watchMode.watching}
          watchedPath={watchMode.watchedPath}
          lastImpact={watchMode.lastImpact}
          impactHistory={watchMode.impactHistory}
          onStartWatch={watchMode.startWatch}
          onStopWatch={watchMode.stopWatch}
          onClearHistory={watchMode.clearHistory}
          onViewImpact={(impact) => {
            const focusNode = impact.changed_nodes[0] || impact.affected_nodes[0];
            if (focusNode) {
              setAiHighlightedNodes(uniqueKeys([...impact.changed_nodes, ...impact.affected_nodes]));
              const node = graphNodes.find((item) => item.namespace_key === focusNode);
              if (node) void handleNodeClick(focusNode, node);
            }
          }}
        />
      )}
      {impactAnalysisOpen && selectedNode && (
        <ImpactAnalysisPanel
          nodeKey={selectedNode.namespace_key}
          nodeName={selectedNode.name}
          onClose={() => setImpactAnalysisOpen(false)}
          onHighlightNodes={setAiHighlightedNodes}
        />
      )}

      <button
        type="button"
        onClick={handleOpenAsk}
        style={{
          position: 'fixed',
          left: 18,
          bottom: 18,
          zIndex: 1200,
          border: '1px solid #334155',
          background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
          color: '#e2e8f0',
          borderRadius: 999,
          padding: '10px 14px',
          fontWeight: 700,
          cursor: 'pointer',
          boxShadow: '0 10px 24px rgba(2, 6, 23, 0.45)',
        }}
      >
        AI Chat
      </button>

      {askOpen && (
        <div style={{ position: 'fixed', right: 18, bottom: 74, zIndex: 1200, width: 420, maxWidth: 'calc(100vw - 24px)' }}>
          <AskPanel
            onClose={() => {
              setAskOpen(false);
              setAskInitialMessage(undefined);
            }}
            selectedNodeKey={selectedNodeKey}
            selectedNodeName={selectedNode?.name ?? null}
            selectedProject={
              selectedProjects.length === 1
                ? selectedProjects[0]
                : selectedNode?.project || null
            }
            graphContext={{
              totalNodes: graphNodes.length,
              totalEdges: graphEdges.length,
              visibleNodes: filteredGraphNodes.length,
              visibleEdges: filteredGraphEdges.length,
              selectedLayer: selectedLayer || undefined,
              liveChangedNodes: liveChangeState?.changedNodes.length,
              liveImpactedNodes: liveChangeState?.impactedNodes.length,
              liveNewNodes: liveChangeState?.newNodes.length,
              liveRemovedNodes: liveChangeState?.removedNodes.length,
              liveRiskScore: liveChangeState?.riskScore,
              liveSource: liveChangeState?.source,
              liveFile: liveChangeState?.file,
            }}
            onHighlightNodes={setAiHighlightedNodes}
            onReferenceClick={(nodeKey) => {
              const node = graphNodes.find((item) => item.namespace_key === nodeKey);
              if (node) {
                handleNodeClick(nodeKey, node);
              }
            }}
            initialMessage={askInitialMessage}
          />
        </div>
      )}

      {liveChangeState && (
        <div style={{
          position: 'fixed',
          left: 18,
          top: 18,
          zIndex: 1100,
          minWidth: 360,
          maxWidth: 'calc(100vw - 36px)',
          border: '1px solid rgba(148, 163, 184, 0.35)',
          background: 'rgba(6, 8, 26, 0.9)',
          borderRadius: 10,
          padding: '10px 12px',
          color: '#e2e8f0',
          boxShadow: '0 12px 26px rgba(2,6,23,0.45)',
          backdropFilter: 'blur(8px)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
            <strong style={{ fontSize: 12 }}>
              Ciclo Vivo · {liveChangeState.source === 'watch' ? 'Watch' : liveChangeState.source === 'sse' ? 'Evento' : 'Fallback'}
            </strong>
            <span style={{ fontSize: 11, color: '#94a3b8' }}>
              {new Date(liveChangeState.timestamp).toLocaleTimeString('pt-BR')}
            </span>
          </div>
          <div style={{ marginTop: 6, fontSize: 12, color: '#cbd5e1' }}>
            {liveChangeState.file || 'Atualizacao de grafo'} · alterados {liveChangeState.changedNodes.length}
            {' '}· impactados {liveChangeState.impactedNodes.length}
            {' '}· novos {liveChangeState.newNodes.length}
            {' '}· removidos {liveChangeState.removedNodes.length}
            {' '}· risco {Math.round(liveChangeState.riskScore)}%
          </div>
          <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="ask-suggestion-btn"
              onClick={() => {
                setAskInitialMessage(
                  `Explique o que mudou em ${liveChangeState.file || 'meu sistema'}, o impacto em ${
                    liveChangeState.impactedNodes.length
                  } nos e o risco ${Math.round(liveChangeState.riskScore)}%.`
                );
                setAskOpen(true);
              }}
            >
              Perguntar para IA
            </button>
            <button
              type="button"
              className="ask-suggestion-btn"
              onClick={() => setAiHighlightedNodes(uniqueKeys([
                ...liveChangeState.changedNodes,
                ...liveChangeState.impactedNodes,
                ...liveChangeState.newNodes,
              ]))}
            >
              Destacar alteracoes
            </button>
          </div>
        </div>
      )}

      <ImpactNotification
        impacts={impactToasts}
        onToastClick={(nodeKey) => {
          const node = graphNodes.find((item) => item.namespace_key === nodeKey);
          if (node) {
            void handleNodeClick(nodeKey, node);
          }
        }}
        onDismiss={(id) => setImpactToasts((prev) => prev.filter((item) => item.id !== id))}
      />

      <div style={{ position: 'fixed', right: 18, bottom: 18, zIndex: 1200 }}>
        <HandGestureController
          onCursorUpdate={setGestureCursor}
          onGestureCommand={handleGestureCommand}
        />
      </div>
    </div>
  );
}
