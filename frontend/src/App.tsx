import { useState, useCallback, useEffect, useRef } from 'react';
import TopBar from './components/TopBar';
import Sidebar from './components/Sidebar';
import GraphCanvas from './components/GraphCanvas';
import NodeDetail from './components/NodeDetail';
import AskPanel from './components/AskPanel';
import StatsBar from './components/StatsBar';
import Dashboard from './components/Dashboard';
import SimulationPanel from './components/SimulationPanel';
import CodeQLModal from './components/CodeQLModal';
import MethodUsageView from './components/MethodUsageView';
import {
  scanProjects,
  getScanStatus,
  fetchGraph,
  fetchImpact,
  fetchBlastRadius,
  fetchProjects,
  fetchGraphStats,
  requestSimulationReview,
  semanticGraphSearch,
  rebuildRagIndex
} from './api';
import type { GraphNode, ImpactData, GraphStats, BlastRadiusData } from './api';
import './index.css';

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

  // ─── Filter State ───
  const [selectedProjects, setSelectedProjects] = useState<string[]>([]);
  const [selectedLayer, setSelectedLayer] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  // ─── Selection & Impact State ───
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedNodeKey, setSelectedNodeKey] = useState<string | null>(null);
  const [impactData, setImpactData] = useState<ImpactData | null>(null);
  const [blastRadius, setBlastRadius] = useState<BlastRadiusData | null>(null);
  const [highlightedUpstream, setHighlightedUpstream] = useState<Set<string>>(new Set());
  const [highlightedDownstream, setHighlightedDownstream] = useState<Set<string>>(new Set());
  const [aiHighlightedNodes, setAiHighlightedNodes] = useState<string[]>([]);

  // ─── Stats & AI Panel State ───
  const [graphStats, setGraphStats] = useState<GraphStats | null>(null);
  const [askOpen, setAskOpen] = useState(false);
  const [askInitialMessage, setAskInitialMessage] = useState<string | undefined>();
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const [simulationOpen, setSimulationOpen] = useState(false);
  const [codeQLOpen, setCodeQLOpen] = useState(false);
  const [methodUsageOpen, setMethodUsageOpen] = useState(false);
  const [methodUsageNode, setMethodUsageNode] = useState<{ key: string; name: string } | null>(null);
  const [isSimulated, setIsSimulated] = useState(false);
  const [simRisk, setSimRisk] = useState<number | null>(null);
  const [simInsights, setSimInsights] = useState<string[]>([]);
  const [isReviewLoading, setIsReviewLoading] = useState(false);
  const [aiReport, setAiReport] = useState<string | null>(null);
  const [semanticSearchEnabled, setSemanticSearchEnabled] = useState(true);
  const [ragReindexing, setRagReindexing] = useState(false);
  
  // Create a ref for the full simulation data to pass to review
  const lastSimData = useRef<any>(null);

  // ─── Handlers ───
  const handleAddWorkspace = useCallback((path: string) => {
    setWorkspaces((prev) => [...prev, path]);
  }, []);

  const handleRemoveWorkspace = useCallback((path: string) => {
    setWorkspaces((prev) => prev.filter((p) => p !== path));
  }, []);

  const loadGraph = useCallback(async () => {
    try {
      const projectFilter =
        selectedProjects.length === 1 ? selectedProjects[0] : undefined;
      const data = await fetchGraph(projectFilter, selectedLayer || undefined);
      setGraphNodes(data.nodes);
      setGraphEdges(data.edges);

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

  const handleScan = useCallback(async () => {
    if (workspaces.length === 0) return;

    try {
      await scanProjects(workspaces);
      setScanStatus('scanning');
      setScanStats({ files: 0, nodes: 0, rels: 0, progress: 0, currentFile: '' });

      // Poll for status
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
    } catch (err) {
      console.error('Scan failed:', err);
      setScanStatus('error');
    }
  }, [workspaces, loadGraph]);

  const handleNodeClick = useCallback(
    async (nodeKey: string, nodeData: GraphNode) => {
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

  const handleSemanticSearch = useCallback(async (query: string) => {
    const q = query.trim();
    if (!q) return;
    try {
      const res = await semanticGraphSearch(q, 20, selectedNodeKey || undefined, semanticSearchEnabled);
      const keys = (res.results || []).map((r: any) => r.key || r.namespace_key).filter(Boolean);
      setAiHighlightedNodes(keys);
      if (keys.length > 0) {
        const first = graphNodes.find((n) => n.namespace_key === keys[0]);
        if (first) setSelectedNode(first);
      }
    } catch (err) {
      console.error('Semantic search failed:', err);
      alert('Falha na busca semântica.');
    }
  }, [selectedNodeKey, graphNodes, semanticSearchEnabled]);

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

  // ─── Effects ───
  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

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
    <div className="app-layout">
      <TopBar
        workspaces={workspaces}
        onAddWorkspace={handleAddWorkspace}
        onRemoveWorkspace={handleRemoveWorkspace}
        onScan={handleScan}
        scanStatus={scanStatus}
        scanStats={scanStats}
        askOpen={askOpen}
        onToggleAsk={() => setAskOpen((prev) => !prev)}
        dashboardOpen={dashboardOpen}
        onToggleDashboard={() => setDashboardOpen((prev) => !prev)}
        simulationOpen={simulationOpen}
        onToggleSimulation={() => setSimulationOpen((prev) => !prev)}
        codeQLOpen={codeQLOpen}
        onToggleCodeQL={() => setCodeQLOpen((prev) => !prev)}
        onSemanticSearch={handleSemanticSearch}
        semanticSearchEnabled={semanticSearchEnabled}
        onToggleSemanticSearchMode={() => setSemanticSearchEnabled((prev) => !prev)}
        onRebuildRagIndex={handleRebuildRag}
        ragReindexing={ragReindexing}
      />

      {isSimulated && (
        <div style={{ 
          position: 'fixed', 
          top: '60px', 
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
        nodeCount={graphNodes.length}
        edgeCount={graphEdges.length}
      />

      <GraphCanvas
        graphNodes={graphNodes}
        graphEdges={graphEdges}
        highlightedUpstream={highlightedUpstream}
        highlightedDownstream={highlightedDownstream}
        aiHighlightedNodes={aiHighlightedNodes}
        selectedNodeKey={selectedNodeKey}
        onNodeClick={handleNodeClick}
        onClearAiHighlights={handleClearAiHighlights}
        searchTerm={searchTerm}
      />

      <NodeDetail
        node={selectedNode}
        impact={impactData}
        blastRadius={blastRadius}
        onClose={handleCloseDetail}
        onViewUsages={handleViewUsages}
        onQuickImpactScenario={handleQuickImpactScenario}
      />

      {methodUsageOpen && methodUsageNode && (
        <MethodUsageView
          nodeKey={methodUsageNode.key}
          nodeName={methodUsageNode.name}
          onClose={() => setMethodUsageOpen(false)}
          onNavigateTo={handleNavigateFromUsages}
        />
      )}

      {graphNodes.length > 0 && <StatsBar stats={graphStats} />}

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
        />
      )}

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
    </div>
  );
}
