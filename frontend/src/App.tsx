import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react';
import TopBar from './components/TopBar';
import Sidebar from './components/Sidebar';
import GraphCanvas from './components/GraphCanvas';
import type { GraphCanvasHandle, SavedViewState } from './components/GraphCanvas';
import NodeDetail from './components/NodeDetail';
import AskPanel from './components/AskPanel';
import ImpactAnalysisPanel, { type ImpactTab } from './components/ImpactAnalysisPanel';
import Dashboard from './components/Dashboard';
import SimulationPanel from './components/SimulationPanel';
import CodeQLModal from './components/CodeQLModal';
import MethodUsageView from './components/MethodUsageView';
import TransactionPanel from './components/TransactionPanel';
import SavedViewsPanel from './components/SavedViewsPanel';
import QuickActionToolbar, { type QuickActionConfig } from './components/QuickActionToolbar';
import InventoryPanel from './components/InventoryPanel';
import FloatingLegend from './components/FloatingLegend';
import GuidedActions from './components/GuidedActions';
import CommandPalette, { type CommandItem } from './components/CommandPalette';
import SemanticSearchPanel from './components/SemanticSearchPanel';
import {
  scanProjects,
  getScanStatus,
  fetchGraph,
  fetchImpact,
  fetchBlastRadius,
  fetchProjects,
  fetchGraphStats,
  requestSimulationReview,
  semanticSearch,
  rebuildRagIndex,
  listSavedViews,
  createSavedView,
  listAnnotations,
  listTags,
} from './api';
import type { SavedView } from './api';
import type {
  GraphNode,
  ImpactData,
  GraphStats,
  BlastRadiusData,
  Tag,
  AnnotationRecord,
  SemanticSearchResult,
  SemanticSearchMode,
} from './api';
import './index.css';

const NODE_QUICK_ACTION_IDS = new Set(['qa-impact', 'qa-taint', 'qa-fragility', 'qa-dataflow', 'qa-annotate']);

const ensureArray = <T,>(value: T[] | Record<string, T> | null | undefined): T[] => {
  if (Array.isArray(value)) return value;
  if (!value) return [];
  return Object.values(value) as T[];
};
const NODE_TYPE_OPTIONS = [
  { value: 'Java_Class', label: 'Classe Java' },
  { value: 'Java_Method', label: 'Método Java' },
  { value: 'API_Endpoint', label: 'API Endpoint' },
  { value: 'TS_Component', label: 'Componente TS' },
  { value: 'TS_Function', label: 'Função TS' },
  { value: 'SQL_Table', label: 'Tabela SQL' },
  { value: 'SQL_Procedure', label: 'Procedure SQL' },
];
import APIInventoryPanel from './components/APIInventoryPanel';
import SecurityDashboard from './components/SecurityDashboard';
import { useRealtimeEvents } from './hooks/useRealtimeEvents';
import ImpactToast, { type ImpactNotification } from './components/ImpactToast';
import SidebarIntelligence from './components/SidebarIntelligence';
import Timeline4D from './components/Timeline4D';
import InvestigationMode from './components/InvestigationMode';
import AIQueryEngine from './components/AIQueryEngine';
import WatchModePanel from './components/WatchModePanel';
import SettingsScreen from './components/SettingsScreen';

// Feature flag for SSE (default: true)
const SSE_ENABLED = import.meta.env.REACT_APP_ENABLE_SSE !== 'false';

export default function App() {
  // ─── Workspace State ───
  const [workspaces, setWorkspaces] = useState<string[]>([]);
  const [projects, setProjects] = useState<string[]>([]);

  // ─── Scan State ───
  const [scanStatus, setScanStatus] = useState('idle');
  const [scanStats, setScanStats] = useState({ files: 0, nodes: 0, rels: 0, progress: 0, currentFile: '' });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ─── Graph State ───
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<
    { source: string; target: string; type: string }[]
  >([]);
  const [selectedNodeTypes, setSelectedNodeTypes] = useState<string[]>(NODE_TYPE_OPTIONS.map((opt) => opt.value));
  const [fileFilter, setFileFilter] = useState('');
  const [impactOnly, setImpactOnly] = useState(false);
  const [hotspotRange, setHotspotRange] = useState<[number, number]>([0, 100]);
  const [complexityRange, setComplexityRange] = useState<[number, number]>([0, 80]);
  const graphCanvasRef = useRef<GraphCanvasHandle>(null);
  const [savedViewsOpen, setSavedViewsOpen] = useState(false);
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [savedViewsLoading, setSavedViewsLoading] = useState(false);
  const [saveViewLoading, setSaveViewLoading] = useState(false);
  const [savedViewsError, setSavedViewsError] = useState<string | null>(null);
  const [tagsForFilter, setTagsForFilter] = useState<Tag[]>([]);
  const [selectedTagFilter, setSelectedTagFilter] = useState<string | null>(null);
  
  // ─── Wave Animation State ───
  const [waveAnimationTrigger, setWaveAnimationTrigger] = useState<{
    originNodeKey: string;
    affectedNodes: string[];
    timestamp: number;
  } | null>(null);
  const [annotationsIndex, setAnnotationsIndex] = useState<Record<string, AnnotationRecord[]>>({});

  // ─── Impact Toast State ───
  const [impactNotifications, setImpactNotifications] = useState<ImpactNotification[]>([]);
  
  // ─── Intelligence Refresh Trigger ───
  const [intelligenceRefreshTrigger, setIntelligenceRefreshTrigger] = useState(0);

  // ─── Timeline 4D State ───
  const [timeline4DOpen, setTimeline4DOpen] = useState(false);

  // ─── Investigation Mode State ───
  const [investigationModeOpen, setInvestigationModeOpen] = useState(false);
  const [investigationNodeKey, setInvestigationNodeKey] = useState<string | null>(null);

  // ─── AI Query Engine State ───
  const [aiQueryOpen, setAiQueryOpen] = useState(false);

  // ─── Watch Mode State ───
  const [watchModeOpen, setWatchModeOpen] = useState(false);

  // ─── Settings Screen State ───
  const [settingsOpen, setSettingsOpen] = useState(false);
  
  // ─── GitHub Configuration State ───
  const [githubRepository, setGithubRepository] = useState(() => {
    const stored = localStorage.getItem('githubRepository');
    return stored || '';
  });
  const [githubBranch, setGithubBranch] = useState(() => {
    const stored = localStorage.getItem('githubBranch');
    return stored || 'main';
  });
  const [githubToken, setGithubToken] = useState(() => {
    const stored = localStorage.getItem('githubToken');
    return stored || '';
  });
  const [githubShallowClone, setGithubShallowClone] = useState(() => {
    const stored = localStorage.getItem('githubShallowClone');
    return stored === 'true';
  });

  // ─── Filter State ───
  const [selectedProjects, setSelectedProjects] = useState<string[]>([]);
  const [selectedLayer, setSelectedLayer] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const searchInputRef = useRef<HTMLInputElement>(null);

  // ─── Selection & Impact State ───
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedNodeKey, setSelectedNodeKey] = useState<string | null>(null);
  const [impactData, setImpactData] = useState<ImpactData | null>(null);
  const [blastRadius, setBlastRadius] = useState<BlastRadiusData | null>(null);
  const [highlightedUpstream, setHighlightedUpstream] = useState<Set<string>>(new Set());
  const [highlightedDownstream, setHighlightedDownstream] = useState<Set<string>>(new Set());
  const [aiHighlightedNodes, setAiHighlightedNodes] = useState<string[]>([]);
  const [impactAnalysisOpen, setImpactAnalysisOpen] = useState(false);
  const [impactAnalysisNode, setImpactAnalysisNode] = useState<GraphNode | null>(null);
  const [impactPanelTab, setImpactPanelTab] = useState<ImpactTab>('analyze');
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const recordCommandHistory = useCallback((_entry: string) => {
    // Command history recording removed - was unused
  }, []);
  const [legendOpen, setLegendOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // ─── Stats & AI Panel State ───
  const [graphStats, setGraphStats] = useState<GraphStats | null>(null);
  const [askOpen, setAskOpen] = useState(false);
  const [askInitialMessage, setAskInitialMessage] = useState<string | undefined>();
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const [simulationOpen, setSimulationOpen] = useState(false);
  const [codeQLOpen, setCodeQLOpen] = useState(false);
  const [methodUsageOpen, setMethodUsageOpen] = useState(false);
  const [methodUsageNode, setMethodUsageNode] = useState<{ key: string; name: string } | null>(null);
  const [inventoryOpen, setInventoryOpen] = useState(false);
  const [transactionOpen, setTransactionOpen] = useState(false);
  const [transactionSourceKey, setTransactionSourceKey] = useState<string | null>(null);
  const [isSimulated, setIsSimulated] = useState(false);
  const [simRisk, setSimRisk] = useState<number | null>(null);
  const [simInsights, setSimInsights] = useState<string[]>([]);
  const [isReviewLoading, setIsReviewLoading] = useState(false);
  const [aiReport, setAiReport] = useState<string | null>(null);
  const [semanticSearchEnabled, setSemanticSearchEnabled] = useState(true);
  const [ragReindexing, setRagReindexing] = useState(false);
  const [searchPanelOpen, setSearchPanelOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [securityOpen, setSecurityOpen] = useState(false);
  const [searchMode, setSearchMode] = useState<SemanticSearchMode>('code');
  const [searchResults, setSearchResults] = useState<SemanticSearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchContextNodes, setSearchContextNodes] = useState<string[]>([]);
  const [searchContextSummary, setSearchContextSummary] = useState('');
  
  // Create a ref for the full simulation data to pass to review
  const lastSimData = useRef<any>(null);

  const loadGraph = useCallback(async () => {
    try {
      const projectFilter =
        selectedProjects.length === 1 ? selectedProjects[0] : undefined;
      const data = await fetchGraph(projectFilter, selectedLayer || undefined);
      setGraphNodes(ensureArray<GraphNode>(data.nodes));
      setGraphEdges(ensureArray(data.edges));

      const projectList = await fetchProjects();
      setProjects(projectList);

      // Load stats
      try {
        const stats = await fetchGraphStats();
        setGraphStats(stats);
      } catch {
        // Stats not critical
      }
    } catch (err) {
      console.error('Failed to load graph:', err);
    }
  }, [selectedProjects, selectedLayer]);

  // ─── SSE Real-time Events ───
  const handleGraphUpdated = useCallback((data: any) => {
    console.log('[App] graph_updated event received:', data);
    // Refresh graph data when backend notifies of changes
    loadGraph();
    // Trigger intelligence refresh
    setIntelligenceRefreshTrigger(prev => prev + 1);
  }, [loadGraph]);

  const handleImpactDetected = useCallback((data: any) => {
    console.log('[App] impact_detected event received:', data);
    
    const affectedCount = data.affected_count || 0;
    const fileName = data.file_path || 'unknown file';
    const originNodeKey = data.origin_node_key || data.node_key;
    const affectedNodes = data.affected_nodes || [];
    
    // Trigger wave animation if we have origin and affected nodes
    if (originNodeKey && affectedNodes.length > 0) {
      setWaveAnimationTrigger({
        originNodeKey,
        affectedNodes,
        timestamp: Date.now(),
      });
    }
    
    // Show ImpactToast notification if impact is significant
    if (affectedCount > 5) {
      const severity: 'low' | 'medium' | 'high' = 
        affectedCount >= 30 ? 'high' : 
        affectedCount >= 10 ? 'medium' : 'low';
      
      const notification: ImpactNotification = {
        id: `impact-${Date.now()}-${Math.random()}`,
        nodeKey: originNodeKey,
        fileName,
        affectedCount,
        severity,
        timestamp: Date.now(),
        autoHide: true,
      };
      
      setImpactNotifications(prev => [...prev, notification]);
    }
    
    // Trigger intelligence refresh
    setIntelligenceRefreshTrigger(prev => prev + 1);
  }, []);

  // Initialize SSE connection if enabled
  const { connected: sseConnected, reconnectAttempts } = useRealtimeEvents({
    autoConnect: SSE_ENABLED,
    handlers: {
      graph_updated: handleGraphUpdated,
      impact_detected: handleImpactDetected,
    },
  });

  // Log SSE connection status
  useEffect(() => {
    if (SSE_ENABLED) {
      console.log('[App] SSE connection status:', sseConnected ? 'connected' : 'disconnected');
      if (reconnectAttempts > 0) {
        console.log('[App] SSE reconnection attempts:', reconnectAttempts);
      }
    }
  }, [sseConnected, reconnectAttempts]);

  // ─── Handlers ───
  const handleAddWorkspace = useCallback((path: string) => {
    setWorkspaces((prev) => [...prev, path]);
  }, []);

  const handleRemoveWorkspace = useCallback((path: string) => {
    setWorkspaces((prev) => prev.filter((p) => p !== path));
  }, []);

  const handleAskButton = useCallback(() => {
    if (selectedNodeKey && selectedNode) {
      setAskInitialMessage(`Se eu alterar ${selectedNode.name}, o que quebra?`);
    } else {
      setAskInitialMessage(undefined);
    }
    setAskOpen(true);
  }, [selectedNode, selectedNodeKey]);

  const handleDeleteProject = useCallback(async (projectName: string) => {
    try {
      const response = await fetch(`/api/workspaces/${encodeURIComponent(projectName)}`, {
        method: 'DELETE',
      });
      if (response.ok) {
        setProjects((prev) => prev.filter((p) => p !== projectName));
        // Also remove from selectedProjects if it was selected
        setSelectedProjects((prev) => prev.filter((p) => p !== projectName));
        // Reload graph to reflect changes
        loadGraph();
      } else {
        console.error('Failed to delete project');
        alert('Falha ao deletar o projeto.');
      }
    } catch (error) {
      console.error('Error deleting project:', error);
      alert('Erro ao deletar o projeto.');
    }
  }, [loadGraph]);

  const loadSavedViews = useCallback(async () => {
    setSavedViewsLoading(true);
    try {
      const projectFilter = selectedProjects.length === 1 ? selectedProjects[0] : undefined;
      const data = await listSavedViews(projectFilter);
      setSavedViews(data.items);
      setSavedViewsError(null);
    } catch (err) {
      console.error('Failed to load saved views:', err);
      setSavedViewsError('Falha ao carregar saved views.');
    } finally {
      setSavedViewsLoading(false);
    }
  }, [selectedProjects]);

  const loadTags = useCallback(async () => {
    try {
      const payload = await listTags();
      setTagsForFilter(payload.items);
    } catch (err) {
      console.error('Failed to load tags for filter:', err);
    }
  }, []);

  const availableFiles = useMemo(() => {
    const files = new Set<string>();
    graphNodes.forEach((node) => {
      if (node.file) files.add(node.file);
    });
    return Array.from(files).sort();
  }, [graphNodes]);

  const filteredGraphNodes = useMemo(() => {
    const [hotMin, hotMax] = hotspotRange;
    const [compMin, compMax] = complexityRange;
    const fileTerm = fileFilter.trim().toLowerCase();
    const searchTermLower = searchTerm.trim().toLowerCase();
    return graphNodes.filter((node) => {
      const hotspot = node.hotspot_score ?? 0;
      if (hotspot < hotMin || hotspot > hotMax) return false;
      const complexity = node.complexity ?? 0;
      if (complexity < compMin || complexity > compMax) return false;
      const labels = node.labels ?? [];
      if (selectedNodeTypes.length > 0 && !labels.some((label) => selectedNodeTypes.includes(label))) {
        return false;
      }
      if (fileTerm && !(node.file || '').toLowerCase().includes(fileTerm)) {
        return false;
      }
      if (searchTermLower && !node.name.toLowerCase().includes(searchTermLower)) {
        return false;
      }
      if (impactOnly && !(typeof node.impact_distance === 'number' && node.impact_distance > 0)) {
        return false;
      }
      return true;
    });
  }, [graphNodes, hotspotRange, complexityRange, selectedNodeTypes, fileFilter, impactOnly, searchTerm]);

  const visibleNodeCount = filteredGraphNodes.length;
  const totalNodeCount = graphNodes.length;

  const filteredGraphEdges = useMemo(() => {
    const visibleKeys = new Set(filteredGraphNodes.map((node) => node.namespace_key));
    return graphEdges.filter((edge) => visibleKeys.has(edge.source) && visibleKeys.has(edge.target));
  }, [graphEdges, filteredGraphNodes]);

  const toggleNodeType = useCallback((type: string) => {
    setSelectedNodeTypes((prev) => {
      if (prev.includes(type)) {
        return prev.filter((value) => value !== type);
      }
      return [...prev, type];
    });
  }, []);

  const updateRange = (
    setter: React.Dispatch<React.SetStateAction<[number, number]>>,
    index: 0 | 1,
    value: number
  ) => {
    setter((prev) => {
      const next: [number, number] = [...prev];
      if (index === 0) {
        next[0] = Math.min(value, prev[1]);
      } else {
        next[1] = Math.max(prev[0], value);
      }
      return next;
    });
  };

  const handleHotspotRangeChange = useCallback((index: 0 | 1, value: number) => {
    updateRange(setHotspotRange, index, value);
  }, [setHotspotRange]);

  const handleComplexityRangeChange = useCallback((index: 0 | 1, value: number) => {
    updateRange(setComplexityRange, index, value);
  }, [setComplexityRange]);

  const handleFileFilterChange = useCallback((value: string) => {
    setFileFilter(value);
  }, [setFileFilter]);

  const handleImpactOnlyToggle = useCallback(() => {
    setImpactOnly((prev) => !prev);
  }, [setImpactOnly]);

  const loadAnnotations = useCallback(async () => {
    try {
      const payload = await listAnnotations();
      const grouped: Record<string, AnnotationRecord[]> = {};
      (payload.items as AnnotationRecord[]).forEach((record) => {
        if (!record.node_key) return;
        grouped[record.node_key] = grouped[record.node_key] || [];
        grouped[record.node_key].push(record);
      });
      setAnnotationsIndex(grouped);
    } catch (err) {
      console.error('Failed to load annotations for filter:', err);
    }
  }, []);

  useEffect(() => {
    loadTags();
    loadAnnotations();
  }, [loadTags, loadAnnotations]);

  const handleOpenSavedViews = useCallback(() => {
    loadSavedViews();
    setSavedViewsOpen(true);
  }, [loadSavedViews]);

  const handleToggleSavedViews = useCallback(() => {
    if (savedViewsOpen) {
      setSavedViewsOpen(false);
      return;
    }
    handleOpenSavedViews();
  }, [savedViewsOpen, handleOpenSavedViews]);

  const handleSelectTagFilter = useCallback((tagName: string | null) => {
    setSelectedTagFilter((prev) => (prev === tagName ? null : tagName));
  }, []);

  const handleAnnotationsChanged = useCallback(() => {
    loadAnnotations();
    loadTags();
  }, [loadAnnotations, loadTags]);

  const nodeAnnotationMeta = useMemo(() => {
    const map = new Map<string, { tag?: string; color?: string | null }>();
    Object.entries(annotationsIndex).forEach(([nodeKey, records]) => {
      if (!records.length) return;
      const tagged = records.find((record) => record.tag);
      if (tagged && tagged.tag) {
        map.set(nodeKey, { tag: tagged.tag, color: tagged.tag_color ?? undefined });
      } else {
        map.set(nodeKey, { color: records[0]?.tag_color ?? undefined });
      }
    });
    return map;
  }, [annotationsIndex]);

  const nodesByTag = useMemo(() => {
    const map = new Map<string, Set<string>>();
    Object.entries(annotationsIndex).forEach(([nodeKey, records]) => {
      records.forEach((record) => {
        if (!record.tag) return;
        const existing = map.get(record.tag);
        if (existing) {
          existing.add(nodeKey);
        } else {
          map.set(record.tag, new Set([nodeKey]));
        }
      });
    });
    return map;
  }, [annotationsIndex]);

  const tagFilterNodes = useMemo(() => {
    if (!selectedTagFilter) return undefined;
    return nodesByTag.get(selectedTagFilter) ?? new Set<string>();
  }, [nodesByTag, selectedTagFilter]);

  const handleSaveCurrentView = useCallback(
    async (name: string, description?: string) => {
      if (!graphCanvasRef.current) throw new Error('Graph canvas is not ready yet.');
      const viewState = graphCanvasRef.current.captureViewState();
      setSaveViewLoading(true);
      try {
        await createSavedView({
          name,
          description,
          project: selectedProjects.length === 1 ? selectedProjects[0] : undefined,
        filters: {
          searchTerm,
          selectedLayer,
          selectedProjects: [...selectedProjects],
          hotspotRange,
          complexityRange,
          selectedNodeTypes,
          fileFilter,
          impactOnly,
        },
          reactflow_state: viewState as unknown as Record<string, unknown>,
        });
        await loadSavedViews();
      } finally {
        setSaveViewLoading(false);
      }
    },
    [selectedLayer, searchTerm, selectedProjects, hotspotRange, complexityRange, selectedNodeTypes, fileFilter, impactOnly, loadSavedViews]
  );

  const handleLoadSavedView = useCallback(
    (view: SavedView) => {
      const filters = (view.filters || {}) as Record<string, unknown>;
      if (filters.searchTerm !== undefined) {
        setSearchTerm(String(filters.searchTerm || ''));
      }
      if (filters.selectedLayer !== undefined) {
        setSelectedLayer(String(filters.selectedLayer || ''));
      }
      if (Array.isArray(filters.selectedProjects)) {
        setSelectedProjects(filters.selectedProjects.filter((p): p is string => typeof p === 'string'));
      }
      if (Array.isArray(filters.hotspotRange) && filters.hotspotRange.length === 2) {
        setHotspotRange([
          Number(filters.hotspotRange[0]) || 0,
          Number(filters.hotspotRange[1]) || 100,
        ]);
      }
      if (Array.isArray(filters.complexityRange) && filters.complexityRange.length === 2) {
        setComplexityRange([
          Number(filters.complexityRange[0]) || 0,
          Number(filters.complexityRange[1]) || 80,
        ]);
      }
      if (Array.isArray(filters.selectedNodeTypes)) {
        setSelectedNodeTypes(filters.selectedNodeTypes.filter((t): t is string => typeof t === 'string'));
      }
      if (typeof filters.fileFilter === 'string') {
        setFileFilter(filters.fileFilter);
      }
      if (typeof filters.impactOnly === 'boolean') {
        setImpactOnly(filters.impactOnly);
      }

      const rfState = view.reactflow_state as SavedViewState | undefined;
      if (rfState?.nodes?.length && graphCanvasRef.current) {
        graphCanvasRef.current.applyViewState({
          nodes: rfState.nodes,
          viewport: rfState.viewport || { x: 0, y: 0, zoom: 1 },
        });
      }
      setSavedViewsOpen(false);
    },
    []
  );

  const handleScan = useCallback(async () => {
    if (workspaces.length === 0) return;

    try {
      await scanProjects(workspaces);
      setScanStatus('scanning');
      setScanStats({ files: 0, nodes: 0, rels: 0, progress: 0, currentFile: '' });

      // Poll for status only if SSE is disabled (fallback mode)
      // When SSE is enabled, scan_complete event will trigger graph reload
      if (!SSE_ENABLED) {
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

            if (status.status !== 'scanning') {
              setScanStatus(status.status);
              if (pollRef.current) clearInterval(pollRef.current);
              // Reload graph after scan completes
              loadGraph();
            }
          } catch {
            setScanStatus('error');
            if (pollRef.current) clearInterval(pollRef.current);
          }
        }, 1500);
      } else {
        // With SSE enabled, still poll for scan progress but rely on events for completion
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

            if (status.status !== 'scanning') {
              setScanStatus(status.status);
              if (pollRef.current) clearInterval(pollRef.current);
              // Graph reload will be triggered by SSE event
            }
          } catch {
            setScanStatus('error');
            if (pollRef.current) clearInterval(pollRef.current);
          }
        }, 1500);
      }
    } catch (err) {
      console.error('Scan failed:', err);
      setScanStatus('error');
    }
  }, [workspaces, loadGraph]);

  const handleNodeClick = useCallback(
    async (nodeKey: string, nodeData: GraphNode, _screenPosition?: { x: number; y: number }) => {
      setSelectedNodeKey(nodeKey);
      setSelectedNode(nodeData);

      try {
        const [impact, br] = await Promise.all([
          fetchImpact(nodeKey),
          fetchBlastRadius(nodeKey)
        ]);
        setImpactData(impact);
        setBlastRadius(br);
        setHighlightedUpstream(new Set(impact.upstream.map((n) => n.key)));
        setHighlightedDownstream(new Set(impact.downstream.map((n) => n.key)));
      } catch (err) {
        console.error('Failed to fetch impact details:', err);
        setImpactData(null);
        setBlastRadius(null);
        setHighlightedUpstream(new Set());
        setHighlightedDownstream(new Set());
      }
    },
    []
  );
  const handleOpenImpactAnalysisPanel = useCallback((nodeKey: string, initialTab: ImpactTab = 'analyze') => {
    const node = graphNodes.find((n) => n.namespace_key === nodeKey);
    if (!node) return;
    setImpactAnalysisNode(node);
    setImpactAnalysisOpen(true);
    setImpactPanelTab(initialTab);
    handleNodeClick(nodeKey, node);
  }, [graphNodes, handleNodeClick]);

  const handleCloseImpactPanel = useCallback(() => {
    setImpactAnalysisOpen(false);
    setImpactAnalysisNode(null);
  }, []);

  const handleGuidedImpact = useCallback(() => {
    if (selectedNodeKey) {
      handleOpenImpactAnalysisPanel(selectedNodeKey);
    }
  }, [selectedNodeKey, handleOpenImpactAnalysisPanel]);

  const handleGuidedPathFinder = useCallback(() => {
    setSearchPanelOpen(true);
    setSearchMode('code');
  }, []);

  const handleGuidedSimulate = useCallback(() => {
    setSimulationOpen(true);
  }, []);

  const toggleLegend = useCallback(() => {
    setLegendOpen((prev) => !prev);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setSelectedNode(null);
    setSelectedNodeKey(null);
    setImpactData(null);
    setBlastRadius(null);
    setHighlightedUpstream(new Set());
    setHighlightedDownstream(new Set());
    setAiHighlightedNodes([]);
  }, []);

  const handleClearAiHighlights = useCallback(() => {
    setAiHighlightedNodes([]);
  }, []);

  const handleToggleProject = useCallback((project: string) => {
    setSelectedProjects((prev) =>
      prev.includes(project)
        ? prev.filter((p) => p !== project)
        : [...prev, project]
    );
  }, []);
  const lastScanLabel = useMemo(() => {
    switch (scanStatus) {
      case 'scanning':
        return 'Scan em andamento';
      case 'completed':
        return 'Último scan concluído';
      case 'error':
        return 'Último scan com erro';
      default:
        return 'Nenhum scan registrado';
    }
  }, [scanStatus]);
  const handleSimulationComplete = useCallback((simData: any) => {
    lastSimData.current = simData;
    setGraphNodes(simData.nodes);
    setGraphEdges(simData.edges);
    setSimRisk(simData.risk_score);
    setSimInsights(simData.impact_insights || []);
    setIsSimulated(true);
    setSimulationOpen(false);
    setSelectedNode(null);
    setSelectedNodeKey(null);
    setImpactData(null);
    setBlastRadius(null);
  }, []);

  const handleExitSimulation = useCallback(() => {
    setIsSimulated(false);
    setSimRisk(null);
    setSimInsights([]);
    setAiReport(null);
    lastSimData.current = null;
    loadGraph();
  }, [loadGraph]);

  const handleRequestReview = useCallback(async () => {
    if (!lastSimData.current) return;
    setIsReviewLoading(true);
    try {
      const { report } = await requestSimulationReview(lastSimData.current);
      setAiReport(report);
    } catch (err) {
      console.error('Review failed:', err);
      alert('Falha ao gerar consultoria da IA.');
    } finally {
      setIsReviewLoading(false);
    }
  }, []);

  const handleRefactorRequest = useCallback((nodeName: string, problemType: string) => {
    const message = `O Dashboard indicou que a classe/nó "${nodeName}" tem problemas de ${problemType}. Como posso refatorar e resolver isso passo a passo?`;
    setAskInitialMessage(message);
    setAskOpen(true);
    setDashboardOpen(false);
  }, []);

  const handleOpenTransaction = useCallback((nodeKey: string) => {
    setTransactionSourceKey(nodeKey);
    setTransactionOpen(true);
  }, []);

  const handleViewUsages = useCallback((nodeKey: string, nodeName: string) => {
    const methodLikeLabels = new Set(['Java_Method', 'TS_Function', 'API_Endpoint', 'SQL_Procedure']);
    const node = graphNodes.find((n) => n.namespace_key === nodeKey);
    const isMethodLike = Boolean(
      node &&
      !node.namespace_key.startsWith('cluster:') &&
      (node.labels || []).some((l) => methodLikeLabels.has(l)),
    );
    if (!isMethodLike) {
      alert('Usos do método só está disponível para métodos/funções/procedures.');
      return;
    }
    setMethodUsageNode({ key: nodeKey, name: nodeName });
    setMethodUsageOpen(true);
  }, [graphNodes]);

  const handleNavigateFromUsages = useCallback((nodeKey: string) => {
    const target = graphNodes.find((n) => n.namespace_key === nodeKey);
    if (target) {
      handleNodeClick(nodeKey, target);
      setMethodUsageOpen(false);
    }
  }, [graphNodes, handleNodeClick]);

  const handleOpenInventory = useCallback(() => {
    setInventoryOpen(true);
  }, []);

  const handleToggleInventory = useCallback(() => {
    setInventoryOpen((prev) => !prev);
  }, []);

  const handleOpenSearchPanel = useCallback(() => {
    setSearchPanelOpen(true);
  }, []);

  const handleCloseSearchPanel = useCallback(() => {
    setSearchPanelOpen(false);
  }, []);

  const handleRunSemanticSearch = useCallback(async () => {
    const q = searchQuery.trim();
    if (!q) {
      setSearchResults([]);
      setSearchError(null);
      return;
    }
    setSearchLoading(true);
    setSearchError(null);
    try {
      const response = await semanticSearch(
        q,
        searchMode,
        30,
        selectedNodeKey || undefined,
        semanticSearchEnabled,
      );
      setSearchResults(response.results);
      setSearchContextSummary(response.context_summary || '');
      setSearchContextNodes(response.context_nodes || []);
      setSearchPanelOpen(true);
      const nodeKeys = response.results
        .map((result) => result.namespace_key)
        .filter(Boolean) as string[];
      setAiHighlightedNodes(nodeKeys);
    } catch (err) {
      console.error('Semantic search failed:', err);
      setSearchError('Falha na busca semântica. Tente novamente.');
    } finally {
      setSearchLoading(false);
    }
  }, [searchMode, searchQuery, selectedNodeKey, semanticSearchEnabled]);

  const handleSelectSearchResult = useCallback(
    (nodeKey: string) => {
      const node = graphNodes.find((n) => n.namespace_key === nodeKey);
      if (node) {
        handleNodeClick(nodeKey, node);
      }
      setSearchPanelOpen(false);
    },
    [graphNodes, handleNodeClick],
  );

  const handleSearchImpactAction = useCallback(
    (nodeKey: string) => {
      handleOpenImpactAnalysisPanel(nodeKey, 'analyze');
      setSearchPanelOpen(false);
    },
    [handleOpenImpactAnalysisPanel],
  );

  const handleQuickImpactScenario = useCallback((
    scenario: 'delete' | 'signature' | 'data_type',
    node: GraphNode
  ) => {
    const keys = new Set<string>();
    keys.add(node.namespace_key);

    const ups = impactData?.upstream || [];
    const downs = impactData?.downstream || [];
    const blast = blastRadius?.nodes || [];

    if (scenario === 'delete') {
      ups.forEach((n) => keys.add(n.key));
      downs.forEach((n) => keys.add(n.key));
      blast.forEach((n) => {
        if (n.namespace_key) keys.add(n.namespace_key);
      });
    } else if (scenario === 'signature') {
      downs.forEach((n) => keys.add(n.key));
      blast.forEach((n) => {
        if ((n.labels || []).includes('Java_Method') || (n.labels || []).includes('TS_Function') || (n.labels || []).includes('API_Endpoint')) {
          keys.add(n.namespace_key);
        }
      });
    } else if (scenario === 'data_type') {
      downs.forEach((n) => keys.add(n.key));
      blast.forEach((n) => {
        if ((n.labels || []).includes('SQL_Table') || (n.labels || []).includes('SQL_Procedure') || (n.labels || []).includes('API_Endpoint')) {
          keys.add(n.namespace_key);
        }
      });
    }

    setAiHighlightedNodes(Array.from(keys));
  }, [impactData, blastRadius]);

  const handleQuickAsk = useCallback(() => {
    const label = selectedNode ? selectedNode.name : 'arquitetura';
    const message = `Explique rapidamente o impacto de ${label} e quais dependências principais precisam ser consideradas.`;
    setAskInitialMessage(message);
    setAskOpen(true);
  }, [selectedNode]);

  const handleQuickAnnotate = useCallback(() => {
    if (!selectedNode || !selectedNodeKey) return;
    setSelectedNodeKey(selectedNodeKey);
    setSelectedNode(selectedNode);
    setAiHighlightedNodes([selectedNodeKey]);
    alert('Use o painel de detalhes para adicionar uma anotação e salvar registros contextuais.');
  }, [selectedNode, selectedNodeKey]);

  const handleQuickSaveView = useCallback(() => {
    const name = window.prompt('Nome da view atual');
    if (name && name.trim()) {
      handleSaveCurrentView(name.trim());
    }
  }, [handleSaveCurrentView]);

  const handleFocusGraphNode = useCallback((nodeKey: string) => {
    const node = graphNodes.find((n) => n.namespace_key === nodeKey);
    if (node) {
      handleNodeClick(nodeKey, node);
    }
  }, [graphNodes, handleNodeClick]);

  // ─── Impact Toast Handlers ───
  const handleToastClick = useCallback((nodeKey: string) => {
    const node = graphNodes.find((n) => n.namespace_key === nodeKey);
    if (node) {
      handleNodeClick(nodeKey, node);
      // Focus camera on the node
      graphCanvasRef.current?.focusNode(nodeKey);
    }
  }, [graphNodes, handleNodeClick]);

  const handleToastDismiss = useCallback((id: string) => {
    setImpactNotifications(prev => prev.filter(n => n.id !== id));
  }, []);

  const handleArrowNavigate = useCallback((direction: 'upstream' | 'downstream') => {
    if (!selectedNodeKey || !impactData) return;
    const neighbors = direction === 'upstream' ? impactData.upstream : impactData.downstream;
    if (!neighbors.length) return;
    const target = neighbors[0];
    const node = graphNodes.find((n) => n.namespace_key === target.key);
    if (node) {
      handleNodeClick(target.key, node);
    }
  }, [selectedNodeKey, impactData, graphNodes, handleNodeClick]);

  const wrapQuickAction = useCallback(
    (label: string, effect: () => void) => (event: MouseEvent<HTMLButtonElement>) => {
      event.preventDefault();
      recordCommandHistory(label);
      effect();
    },
    [recordCommandHistory]
  );

  const quickActionItems = useMemo<QuickActionConfig[]>(() => {
    const hasNode = Boolean(selectedNodeKey);
    return [
      {
        id: 'qa-impact',
        label: 'Análise de Impacto',
        icon: '🔍',
        tooltip: 'Abrir impacto/RAG para o nó atual',
        disabled: !hasNode,
        shortcut: 'Ctrl+I',
        onClick: wrapQuickAction('Análise de Impacto', () => {
          if (hasNode && selectedNodeKey) handleOpenImpactAnalysisPanel(selectedNodeKey, 'analyze');
        }),
      },
      {
        id: 'qa-taint',
        label: 'Taint',
        icon: '🧪',
        tooltip: 'Propagar taint a partir do nó selecionado',
        disabled: !hasNode,
        onClick: (event) => {
          event.preventDefault();
          if (hasNode && selectedNodeKey) handleOpenImpactAnalysisPanel(selectedNodeKey, 'taint');
        },
      },
      {
        id: 'qa-fragility',
        label: 'Fragilidade',
        icon: '📊',
        tooltip: 'Analisar fragilidade e tendências',
        disabled: !hasNode,
        onClick: (event) => {
          event.preventDefault();
          if (hasNode && selectedNodeKey) handleOpenImpactAnalysisPanel(selectedNodeKey, 'fragility');
        },
      },
      {
        id: 'qa-dataflow',
        label: 'Fluxo de Dados',
        icon: '🔗',
        tooltip: 'Abrir transaction view do nó',
        disabled: !hasNode,
        onClick: (event) => {
          event.preventDefault();
          if (hasNode && selectedNodeKey) handleOpenTransaction(selectedNodeKey);
        },
      },
      {
        id: 'qa-ask',
        label: 'Perguntar à IA',
        icon: '💬',
        tooltip: 'Gerar pergunta rápida para o nó atual',
        onClick: (event) => {
          event.preventDefault();
          handleQuickAsk();
        },
      },
      {
        id: 'qa-annotate',
        label: 'Anotar',
        icon: '📝',
        tooltip: 'Registrar uma anotação rápida no nó',
        disabled: !hasNode,
        onClick: (event) => {
          event.preventDefault();
          handleQuickAnnotate();
        },
      },
    ];
  }, [
    selectedNodeKey,
    handleOpenImpactAnalysisPanel,
    handleOpenTransaction,
    handleQuickAsk,
    handleQuickAnnotate,
  ]);

  const handleRebuildRag = useCallback(async () => {
    try {
      setRagReindexing(true);
      const result = await rebuildRagIndex(true);
      alert(`RAG reindex concluido: ${result.indexed_nodes} nos.`);
    } catch (err) {
      console.error('RAG reindex failed:', err);
      alert('Falha ao reindexar RAG/embeddings.');
    } finally {
      setRagReindexing(false);
    }
  }, []);

  // ─── Timeline 4D Handlers ───
  const handleOpenTimeline4D = useCallback(() => {
    setTimeline4DOpen(true);
  }, []);

  const handleCloseTimeline4D = useCallback(() => {
    setTimeline4DOpen(false);
  }, []);

  // ─── Investigation Mode Handlers ───
  const handleOpenInvestigation = useCallback((nodeKey: string) => {
    setInvestigationNodeKey(nodeKey);
    setInvestigationModeOpen(true);
  }, []);

  const handleCloseInvestigation = useCallback(() => {
    setInvestigationModeOpen(false);
    setInvestigationNodeKey(null);
  }, []);

  // ─── AI Query Engine Handlers ───
  const handleOpenAIQuery = useCallback(() => {
    setAiQueryOpen(true);
  }, []);

  const handleCloseAIQuery = useCallback(() => {
    setAiQueryOpen(false);
  }, []);

  // ─── Watch Mode Handlers ───
  const handleOpenWatchMode = useCallback(() => {
    setWatchModeOpen(true);
  }, []);

  const handleCloseWatchMode = useCallback(() => {
    setWatchModeOpen(false);
  }, []);

  const handleOpenSettings = useCallback(() => {
    setSettingsOpen(true);
  }, []);

  const handleCloseSettings = useCallback(() => {
    setSettingsOpen(false);
  }, []);

  // ─── Effects ───
  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      const target = event.target as HTMLElement | null;
      const isTextInput = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);

      if (key === 'escape') {
        if (commandPaletteOpen) {
          event.preventDefault();
          setCommandPaletteOpen(false);
          return;
        }
        setAskOpen(false);
        setDashboardOpen(false);
        setSavedViewsOpen(false);
        setImpactAnalysisOpen(false);
        setTransactionOpen(false);
        setInventoryOpen(false);
        setSimulationOpen(false);
        setCodeQLOpen(false);
      }

      if ((event.ctrlKey || event.metaKey) && key === 'k') {
        event.preventDefault();
        setCommandPaletteOpen((prev) => !prev);
        return;
      }

      if ((event.ctrlKey || event.metaKey) && key === '/') {
        event.preventDefault();
        setAskOpen((prev) => !prev);
        return;
      }

      if ((event.ctrlKey || event.metaKey) && key === 'd') {
        event.preventDefault();
        setDashboardOpen((prev) => !prev);
        return;
      }

      if ((event.ctrlKey || event.metaKey) && key === 'f') {
        event.preventDefault();
        searchInputRef.current?.focus();
        return;
      }

      if ((event.ctrlKey || event.metaKey) && event.shiftKey && key === 's') {
        event.preventDefault();
        handleQuickSaveView();
        return;
      }

      if (!isTextInput && !commandPaletteOpen) {
        if (key === 'arrowup') {
          event.preventDefault();
          handleArrowNavigate('upstream');
          return;
        }
        if (key === 'arrowdown') {
          event.preventDefault();
          handleArrowNavigate('downstream');
          return;
        }
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [
    commandPaletteOpen,
    handleQuickSaveView,
    handleArrowNavigate,
    setDashboardOpen,
    setAskOpen,
    setSavedViewsOpen,
    setImpactAnalysisOpen,
    setTransactionOpen,
    setInventoryOpen,
    setSimulationOpen,
    setCodeQLOpen,
    setCommandPaletteOpen,
  ]);

  const commandActions = useMemo<CommandItem[]>(() => [
    {
      id: 'cmd_scan',
      label: 'Scan All',
      description: 'Executar scan em todos os workspaces',
      category: 'Scan',
      action: handleScan,
    },
    {
      id: 'cmd_toggle_dashboard',
      label: 'Dashboard',
      description: 'Mostrar ou ocultar o painel',
      category: 'Painel',
      action: () => setDashboardOpen((prev) => !prev),
    },
    {
      id: 'cmd_ai_assistant',
      label: 'AI Assistant',
      description: 'Abrir/fechar o assistente',
      category: 'Assistente',
      action: () => setAskOpen((prev) => !prev),
    },
    {
      id: 'cmd_saved_views',
      label: 'Saved Views',
      description: 'Abrir painel de views salvas',
      category: 'Views',
      action: () => setSavedViewsOpen(true),
    },
    {
      id: 'cmd_save_view',
      label: 'Salvar view atual',
      description: 'Salvar rapidamente a vista ativa',
      category: 'Views',
      action: handleQuickSaveView,
    },
    {
      id: 'cmd_simulation',
      label: 'Simulation Panel',
      description: 'Abrir ou fechar simulação',
      category: 'Simulação',
      action: () => setSimulationOpen((prev) => !prev),
    },
    {
      id: 'cmd_inventory',
      label: 'API Inventory',
      description: 'Explorar inventário de APIs',
      category: 'Inventário',
      action: () => setInventoryOpen((prev) => !prev),
    },
    {
      id: 'cmd_codeql',
      label: 'CodeQL',
      description: 'Abrir/fechar CodeQL modal',
      category: 'Segurança',
      action: () => setCodeQLOpen((prev) => !prev),
    },
    {
      id: 'cmd_impact_panel',
      label: 'Análise de Impacto',
      description: 'Abrir painel de impacto para o nó selecionado',
      category: 'Nó',
      action: () => {
        if (!selectedNodeKey) {
          alert('Selecione um nó antes de abrir a análise de impacto.');
          return;
        }
        handleOpenImpactAnalysisPanel(selectedNodeKey);
      },
    },
    {
      id: 'cmd_ask_context',
      label: 'Perguntar à IA',
      description: 'Enviar pergunta contextual rápida',
      category: 'IA',
      action: handleQuickAsk,
    },
    {
      id: 'cmd_reindex_rag',
      label: 'Reindexar RAG',
      description: 'Reconstruir índice semântico local',
      category: 'RAG',
      action: handleRebuildRag,
    },
  ], [
    handleScan,
    handleQuickSaveView,
    handleRebuildRag,
    handleOpenImpactAnalysisPanel,
    handleQuickAsk,
    selectedNodeKey,
  ]);

  const nodeCommandItems = useMemo<CommandItem[]>(() =>
    graphNodes.slice(0, 40).map((node) => ({
      id: `node-${node.namespace_key}`,
      label: node.name,
      description: node.file || node.layer || 'Nó da arquitetura',
      category: node.layer || 'Node',
      action: () => handleNodeClick(node.namespace_key, node),
    })),
    [graphNodes, handleNodeClick]
  );

  const savedViewCommands = useMemo<CommandItem[]>(() =>
    savedViews.map((view) => ({
      id: `saved-${view.id}`,
      label: `Carregar ${view.name}`,
      description: view.description || 'Saved View',
      category: 'Saved View',
      action: () => {
        handleLoadSavedView(view);
        setCommandPaletteOpen(false);
      },
    })),
    [savedViews, handleLoadSavedView, setCommandPaletteOpen]
  );

  const commandItems = useMemo<CommandItem[]>(() => {
    return [...commandActions, ...nodeCommandItems, ...savedViewCommands];
  }, [commandActions, nodeCommandItems, savedViewCommands]);

  const nodeQuickActionItems = useMemo<QuickActionConfig[]>(() =>
    quickActionItems.filter((action) => NODE_QUICK_ACTION_IDS.has(action.id)),
    [quickActionItems]
  );
  const globalQuickActionItems = useMemo<QuickActionConfig[]>(() =>
    quickActionItems.filter((action) => !NODE_QUICK_ACTION_IDS.has(action.id)),
    [quickActionItems]
  );

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // Load existing analyzed projects on app start
  useEffect(() => {
    const loadExistingProjects = async () => {
      try {
        const response = await fetch('/api/workspaces');
        const data = await response.json();
        if (data.projects && data.projects.length > 0) {
          setProjects(data.projects);
        }
      } catch (error) {
        console.error('Failed to load existing projects:', error);
      }
    };
    loadExistingProjects();
  }, []);

  // ─── Render ───
  return (
    <div className={`app-layout ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <TopBar
        workspaces={workspaces}
        onAddWorkspace={handleAddWorkspace}
        onRemoveWorkspace={handleRemoveWorkspace}
        onScan={handleScan}
        scanStatus={scanStatus}
        scanStats={scanStats}
        askOpen={askOpen}
        onAsk={handleAskButton}
        dashboardOpen={dashboardOpen}
        onToggleDashboard={() => setDashboardOpen((prev) => !prev)}
        simulationOpen={simulationOpen}
        onToggleSimulation={() => setSimulationOpen((prev) => !prev)}
        codeQLOpen={codeQLOpen}
        onToggleCodeQL={() => setCodeQLOpen((prev) => !prev)}
        semanticSearchEnabled={semanticSearchEnabled}
        onToggleSemanticSearchMode={() => setSemanticSearchEnabled((prev) => !prev)}
        onRebuildRagIndex={handleRebuildRag}
        ragReindexing={ragReindexing}
        savedViewsOpen={savedViewsOpen}
        onToggleSavedViews={handleToggleSavedViews}
        inventoryOpen={inventoryOpen}
        onToggleInventory={handleToggleInventory}
        onOpenSearchPanel={handleOpenSearchPanel}
        securityOpen={securityOpen}
        onToggleSecurity={() => setSecurityOpen((prev) => !prev)}
        timeline4DOpen={timeline4DOpen}
        onToggleTimeline4D={handleOpenTimeline4D}
        investigationModeOpen={investigationModeOpen}
        onToggleInvestigation={handleOpenInvestigation}
        aiQueryOpen={aiQueryOpen}
        onToggleAIQuery={handleOpenAIQuery}
        watchModeOpen={watchModeOpen}
        onToggleWatchMode={handleOpenWatchMode}
        settingsOpen={settingsOpen}
        onToggleSettings={handleOpenSettings}
        selectedNodeName={selectedNode?.name ?? null}
        lastScanLabel={lastScanLabel}
      />

      {isSimulated && (
        <div style={{ 
          position: 'fixed', 
          top: '92px', 
          left: '50%', 
          transform: 'translateX(-50%)', 
          background: 'rgba(15, 23, 42, 0.95)', 
          backdropFilter: 'blur(10px)',
          color: '#fff', 
          padding: '12px 24px', 
          zIndex: 1000, 
          display: 'flex', 
          flexDirection: 'column',
          alignItems: 'center',
          borderRadius: '0 0 16px 16px',
          boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5)',
          gap: '8px',
          width: '500px',
          borderBottom: '2px solid var(--accent-rose)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
            <span style={{ fontSize: '14px', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '18px' }}>🧪</span> CENÁRIO SIMULADO - Score de Risco: {simRisk}/100
            </span>
            <div style={{ display: 'flex', gap: '12px' }}>
                <button 
                  className="btn" 
                  style={{ padding: '4px 12px', fontSize: '12px', background: 'rgba(56, 189, 248, 0.2)', border: '1px solid #38bdf8', color: '#38bdf8' }} 
                  onClick={handleRequestReview}
                  disabled={isReviewLoading}
                >
                  {isReviewLoading ? 'Analisando...' : '✨ Consultar IA Arquiteta'}
                </button>
                <button className="btn btn-primary" style={{ padding: '4px 12px', fontSize: '12px', background: 'var(--accent-rose)' }} onClick={handleExitSimulation}>
                  Sair da Simulação ✕
                </button>
            </div>
          </div>

          {simInsights.length > 0 && (
            <div style={{ width: '100%', background: 'rgba(0,0,0,0.3)', padding: '10px', borderRadius: '8px', fontSize: '13px', maxHeight: '150px', overflowY: 'auto' }}>
              <div style={{ fontWeight: 'bold', marginBottom: '6px', fontSize: '11px', textTransform: 'uppercase', opacity: 0.7 }}>Detalhamento do Impacto:</div>
              {simInsights.map((insight, i) => (
                <div key={i} style={{ marginBottom: '4px', display: 'flex', gap: '8px' }}>
                  <span>•</span>
                  <span>{insight}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Impact Toast Notifications */}
      <ImpactToast
        impacts={impactNotifications}
        onToastClick={handleToastClick}
        onDismiss={handleToastDismiss}
      />

      <Sidebar
        workspaces={workspaces}
        onRemoveWorkspace={handleRemoveWorkspace}
        projects={projects}
        selectedProjects={selectedProjects}
        onToggleProject={handleToggleProject}
        onDeleteProject={handleDeleteProject}
        selectedLayer={selectedLayer}
        onLayerChange={setSelectedLayer}
        searchTerm={searchTerm}
        onSearchChange={setSearchTerm}
        tags={tagsForFilter}
        selectedTag={selectedTagFilter}
        onTagSelect={handleSelectTagFilter}
        nodeCount={graphNodes.length}
        edgeCount={graphEdges.length}
        nodeTypeOptions={NODE_TYPE_OPTIONS}
        selectedNodeTypes={selectedNodeTypes}
        onToggleNodeType={toggleNodeType}
        hotspotRange={hotspotRange}
        complexityRange={complexityRange}
        onHotspotRangeChange={handleHotspotRangeChange}
        onComplexityRangeChange={handleComplexityRangeChange}
        availableFiles={availableFiles}
        fileFilter={fileFilter}
        onFileFilterChange={handleFileFilterChange}
        impactOnly={impactOnly}
        onImpactOnlyToggle={handleImpactOnlyToggle}
        visibleNodeCount={visibleNodeCount}
        totalNodeCount={totalNodeCount}
        isCollapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(prev => !prev)}
        searchInputRef={searchInputRef}
        onNodeClick={handleFocusGraphNode}
        intelligenceRefreshTrigger={intelligenceRefreshTrigger}
      />

      <div className="app-main">
        <GuidedActions
          selectedNodeName={selectedNode?.name ?? null}
          onImpact={handleGuidedImpact}
          onRunPathFinder={handleGuidedPathFinder}
          onSimulate={handleGuidedSimulate}
        />
        <InventoryPanel
          stats={graphStats}
          projects={projects}
          workspaces={workspaces}
          scanStatus={scanStatus}
          scanStats={scanStats}
        />
        <div className="graph-layout">
          <GraphCanvas
            graphNodes={filteredGraphNodes}
            graphEdges={filteredGraphEdges}
            highlightedUpstream={highlightedUpstream}
            highlightedDownstream={highlightedDownstream}
            aiHighlightedNodes={aiHighlightedNodes}
            selectedNodeKey={selectedNodeKey}
            onNodeClick={handleNodeClick}
            onClearAiHighlights={handleClearAiHighlights}
            searchTerm={searchTerm}
            nodeAnnotations={nodeAnnotationMeta}
            selectedTag={selectedTagFilter}
            tagFilterNodes={tagFilterNodes}
            ref={graphCanvasRef}
            waveAnimationTrigger={waveAnimationTrigger}
          />
          <div className="legend-region">
            <button className="legend-toggle" onClick={toggleLegend} type="button">
              {legendOpen ? 'Ocultar legenda' : 'Legenda'}
            </button>
            {legendOpen && (
              <FloatingLegend onClose={() => setLegendOpen(false)} />
            )}
          </div>
          <QuickActionToolbar actions={globalQuickActionItems} />
          <NodeDetail
            node={selectedNode}
            impact={impactData}
            blastRadius={blastRadius}
            onClose={handleCloseDetail}
            onViewUsages={handleViewUsages}
            onQuickImpactScenario={handleQuickImpactScenario}
            onOpenTransaction={handleOpenTransaction}
            onAnnotationsChanged={handleAnnotationsChanged}
            quickActions={nodeQuickActionItems}
          />
        </div>
      </div>

      {transactionOpen && (
        <TransactionPanel
          isOpen={transactionOpen}
          initialSourceKey={transactionSourceKey}
          graphNodes={graphNodes}
          onClose={() => setTransactionOpen(false)}
        />
      )}

      {savedViewsOpen && (
        <SavedViewsPanel
          isOpen={savedViewsOpen}
          onClose={() => setSavedViewsOpen(false)}
          views={savedViews}
          loading={savedViewsLoading}
          saving={saveViewLoading}
          error={savedViewsError}
          onRefresh={loadSavedViews}
          onSave={handleSaveCurrentView}
          onLoad={handleLoadSavedView}
        />
      )}

      {methodUsageOpen && methodUsageNode && (
        <MethodUsageView
          nodeKey={methodUsageNode.key}
          nodeName={methodUsageNode.name}
          onClose={() => setMethodUsageOpen(false)}
          onNavigateTo={handleNavigateFromUsages}
        />
      )}

      {askOpen && (
        <AskPanel
          onClose={() => {
            setAskOpen(false);
            setAskInitialMessage(undefined);
          }}
          selectedNodeKey={selectedNodeKey}
          onHighlightNodes={setAiHighlightedNodes}
          initialMessage={askInitialMessage}
        />
      )}

      {dashboardOpen && (
        <Dashboard 
          onClose={() => setDashboardOpen(false)}
          onRefactorRequest={handleRefactorRequest}
          onOpenInventory={handleOpenInventory}
          onFocusNode={handleFocusGraphNode}
          onOpenImpactAnalysis={handleOpenImpactAnalysisPanel}
        />
      )}

      {securityOpen && (
        <SecurityDashboard
          onClose={() => setSecurityOpen(false)}
          onFocusNode={handleFocusGraphNode}
          onOpenImpactAnalysis={handleOpenImpactAnalysisPanel}
        />
      )}

      {impactAnalysisOpen && impactAnalysisNode && (
        <ImpactAnalysisPanel
          nodeKey={impactAnalysisNode.namespace_key}
          nodeName={impactAnalysisNode.name}
          onClose={handleCloseImpactPanel}
          onHighlightNodes={setAiHighlightedNodes}
          initialTab={impactPanelTab}
        />
      )}
      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        items={commandItems}
      />

      <SemanticSearchPanel
        isOpen={searchPanelOpen}
        query={searchQuery}
        onQueryChange={setSearchQuery}
        onSearch={handleRunSemanticSearch}
        loading={searchLoading}
        error={searchError}
        mode={searchMode}
        onModeChange={setSearchMode}
        results={searchResults}
        contextSummary={searchContextSummary}
        contextNodes={searchContextNodes}
        onClose={handleCloseSearchPanel}
        onSelectResult={handleSelectSearchResult}
        onImpactAction={handleSearchImpactAction}
      />

      {simulationOpen && (
        <SimulationPanel 
          availableNodes={graphNodes} 
          onSimulationComplete={handleSimulationComplete}
          onClose={() => setSimulationOpen(false)} 
        />
      )}

      {codeQLOpen && (
        <CodeQLModal onClose={() => setCodeQLOpen(false)} />
      )}

      {inventoryOpen && (
        <APIInventoryPanel onClose={() => setInventoryOpen(false)} />
      )}

      {aiReport && (
        <div className="modal-overlay" style={{ zIndex: 2000 }}>
          <div className="ask-panel" style={{ width: '800px', height: '80%', position: 'relative' }}>
             <div className="ask-header">
                <h3>🏛️ Consultoria Arquitetural Profunda</h3>
                <span className="close-btn" onClick={() => setAiReport(null)}>✕</span>
             </div>
             <div className="ask-content" style={{ padding: '24px', overflowY: 'auto', display: 'block', color: '#e2e8f0', lineHeight: '1.6' }}>
                <div style={{ whiteSpace: 'pre-wrap', fontFamily: 'Inter, sans-serif' }}>
                  {aiReport}
                </div>
                <div style={{ marginTop: '30px', padding: '16px', borderTop: '1px solid var(--border-color)', fontSize: '0.8rem', opacity: 0.6, textAlign: 'center' }}>
                  Análise gerada pelo modelo de alta performance. Considere estas recomendações como diretrizes arquiteturais.
                </div>
             </div>
          </div>
        </div>
      )}

      {/* Timeline 4D */}
      {timeline4DOpen && (
        <Timeline4D
          onCommitSelected={(hash, snapshot) => {
            console.log('Commit selected:', hash, snapshot);
            
            // Validate snapshot structure
            if (!snapshot || typeof snapshot !== 'object') {
              console.warn('Invalid snapshot received, preserving current graph');
              return;
            }
            
            // Only update graph if snapshot has populated data
            if (snapshot.nodes && Array.isArray(snapshot.nodes) && snapshot.nodes.length > 0) {
              console.log(`Updating graph with ${snapshot.nodes.length} nodes from commit ${hash}`);
              setGraphNodes(snapshot.nodes);
              setGraphEdges(snapshot.edges || []);
            } else {
              // Explicitly preserve current graph when snapshot is empty (fast mode)
              console.log(`Fast mode: Preserving current graph for commit ${hash}`);
              // No state updates - graph remains unchanged
              // Timeline4D panel will display commit diff information
            }
          }}
          onReturnToPresent={() => {
            // Reload current graph
            loadGraph();
          }}
          onClose={handleCloseTimeline4D}
          repoUrl={githubRepository}
          repoPath="."
          repoToken={githubToken}
          useShallowClone={githubShallowClone}
        />
      )}

      {/* Investigation Mode */}
      {investigationModeOpen && investigationNodeKey && (
        <InvestigationMode
          nodeKey={investigationNodeKey}
          onClose={handleCloseInvestigation}
          graphNodes={graphNodes}
          onNodeClick={handleNodeClick}
        />
      )}

      {/* AI Query Engine */}
      {aiQueryOpen && (
        <AIQueryEngine
          onClose={handleCloseAIQuery}
          graphNodes={graphNodes}
          onNodeClick={handleNodeClick}
        />
      )}

      {/* Watch Mode Panel */}
      {watchModeOpen && (
        <WatchModePanel
          onClose={handleCloseWatchMode}
        />
      )}

      {/* Settings Screen */}
      {settingsOpen && (
        <SettingsScreen onClose={handleCloseSettings} />
      )}
    </div>
  );
}
