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
import HandGestureController, { type GestureCommand } from './components/HandGestureController';
import { LiveAlertFeed } from './components/LiveAlertFeed';
import { CommitTimeline } from './components/CommitTimeline';
import { WeeklyDigestPanel } from './components/WeeklyDigestPanel';
import SettingsScreen from './components/SettingsScreen';
import WatchModePanel from './components/WatchModePanel';
import ImpactAnalysisPanel from './components/ImpactAnalysisPanel';
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
  }, []);

  const loadGraph = useCallback(async () => {
    try {
      const projectFilter = selectedProjects.length === 1 ? selectedProjects[0] : undefined;
      const data = await fetchGraph(projectFilter, selectedLayer || undefined);
      setGraphNodes(ensureArray<GraphNode>(data.nodes));
      setGraphEdges(ensureArray(data.edges));
      setProjects(await fetchProjects());
    } catch (err) {
      console.error('Failed to load graph', err);
    }
  }, [selectedLayer, selectedProjects]);

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

  useEffect(() => {
    loadGraph();
    loadTags();
    loadAnnotations();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [loadGraph, loadTags, loadAnnotations]);

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
          loadGraph();
        }
      } catch {
        setScanStatus('error');
      }
    }, 1400);
  }, [workspaces, loadGraph]);

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

  const filteredGraphNodes = useMemo(() => {
    const [hotMin, hotMax] = hotspotRange;
    const [compMin, compMax] = complexityRange;
    const fileTerm = fileFilter.trim().toLowerCase();
    const q = searchTerm.trim().toLowerCase();
    return graphNodes.filter((node) => {
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
  }, [annotationsIndex, complexityRange, fileFilter, graphNodes, hotspotRange, impactOnly, searchTerm, selectedNodeTypes, selectedTagFilter]);

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
      />

      <div className="app-main">
        {homeViewOpen ? (
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
          />
        ) : (
          <div className="graph-layout">
            <GraphCanvas
              graphNodes={filteredGraphNodes}
              graphEdges={filteredGraphEdges}
              highlightedUpstream={highlightedUpstream}
              highlightedDownstream={highlightedDownstream}
              aiHighlightedNodes={aiHighlightedNodes}
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
      {watchModeOpen && <WatchModePanel />}
      {impactAnalysisOpen && selectedNode && (
        <ImpactAnalysisPanel
          nodeKey={selectedNode.namespace_key}
          nodeName={selectedNode.name}
          onClose={() => setImpactAnalysisOpen(false)}
          onHighlightNodes={setAiHighlightedNodes}
        />
      )}

      <div style={{ position: 'fixed', right: 18, bottom: 18, zIndex: 1200 }}>
        <HandGestureController
          onCursorUpdate={setGestureCursor}
          onGestureCommand={handleGestureCommand}
        />
      </div>
    </div>
  );
}
