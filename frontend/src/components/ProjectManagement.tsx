import { useCallback, useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';

type ProjectStatus = 'idle' | 'watching' | 'scanning' | 'error' | string;
type Severity = 'BREAKING' | 'DEGRADED' | 'INFORMATIONAL' | 'ORIGIN' | string;

interface ProjectRecord {
  id: string;
  workspace_id: string;
  name: string;
  path: string;
  type: string;
  status: ProjectStatus;
  updated_at?: number;
  last_error?: string | null;
}

interface WorkspaceRecord {
  id: string;
  name: string;
  root_path: string;
  projects: ProjectRecord[];
}

interface ImpactAffectedItem {
  workspace_id?: string;
  project_id: string;
  project_name: string;
  node_key?: string;
  symbol_name: string;
  relation_type: string;
  severity: Severity;
}

interface ImpactDetectedPayload {
  workspace_id?: string;
  origin_project_id: string;
  file_path?: string;
  file?: string;
  changed_nodes?: string[];
  affected: ImpactAffectedItem[];
  total_affected?: number;
  breaking_count?: number;
}

interface GraphUpdatedPayload {
  workspace_id?: string;
  project_id: string;
  project_name: string;
  file?: string;
  changed_nodes?: string[];
  risk_score?: number;
}

interface ImpactDetectedEventEnvelope {
  type: 'impact_detected';
  timestamp: number;
  payload: ImpactDetectedPayload;
}

interface GraphUpdatedEventEnvelope {
  type: 'graph_updated';
  timestamp: number;
  payload: GraphUpdatedPayload;
}

interface GenericEventEnvelope {
  type: string;
  timestamp: number;
  payload: unknown;
}

interface GodSymbolItem {
  node_key: string;
  name: string;
  project_id?: string;
  project_name?: string;
  file?: string;
  total_dependencies: number;
  inbound_dependencies: number;
  outbound_dependencies: number;
}

interface GodSymbolsResponse {
  workspace_id: string;
  items: GodSymbolItem[];
}

interface BlastRadiusItem {
  node_key: string;
  node_name: string;
  project_id?: string;
  project_name?: string;
  severity: Severity;
  hop: number;
  parent_key?: string | null;
  edge_type?: string | null;
}

interface BlastRadiusResponse {
  workspace_id: string;
  symbol: string;
  origin_nodes: string[];
  blast_radius: BlastRadiusItem[];
  total_impacted: number;
  max_hops: number;
}

const STATUS_META: Record<string, { dot: string; badgeBg: string; badgeFg: string; label: string }> = {
  idle: { dot: '#737373', badgeBg: 'rgba(82,82,91,0.22)', badgeFg: '#d4d4d8', label: 'IDLE' },
  watching: { dot: '#10b981', badgeBg: 'rgba(16,185,129,0.18)', badgeFg: '#6ee7b7', label: 'WATCHING' },
  scanning: { dot: '#f59e0b', badgeBg: 'rgba(245,158,11,0.18)', badgeFg: '#fcd34d', label: 'SCANNING' },
  error: { dot: '#fb7185', badgeBg: 'rgba(244,63,94,0.18)', badgeFg: '#fda4af', label: 'ERROR' },
};

const SURFACE_0 = '#000000';
const SURFACE_1 = '#09090b';
const SURFACE_2 = '#171717';
const BORDER = '#1f1f1f';
const TEXT_PRIMARY = '#ededed';
const TEXT_SECONDARY = '#a1a1aa';

function isImpactDetected(event: GenericEventEnvelope): event is ImpactDetectedEventEnvelope {
  return event.type === 'impact_detected' && typeof event.payload === 'object' && event.payload !== null;
}

function isGraphUpdated(event: GenericEventEnvelope): event is GraphUpdatedEventEnvelope {
  return event.type === 'graph_updated' && typeof event.payload === 'object' && event.payload !== null;
}

function formatElapsed(updatedAt?: number): string {
  if (!updatedAt) return 'Sem registro recente';
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - updatedAt));
  if (seconds < 60) return `Ultimo scan ha ${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `Ultimo scan ha ${minutes}min`;
  const hours = Math.floor(minutes / 60);
  return `Ultimo scan ha ${hours}h`;
}

function projectIcon(projectType: string): string {
  if (projectType === 'backend') return 'BE';
  if (projectType === 'frontend') return 'FE';
  if (projectType === 'mobile') return 'MB';
  return 'PR';
}

function severityStyle(severity: Severity): { bg: string; fg: string; border: string } {
  if (severity === 'BREAKING') return { bg: 'rgba(244,63,94,0.16)', fg: '#fda4af', border: 'rgba(244,63,94,0.45)' };
  if (severity === 'DEGRADED') return { bg: 'rgba(245,158,11,0.14)', fg: '#fcd34d', border: 'rgba(245,158,11,0.45)' };
  if (severity === 'ORIGIN') return { bg: 'rgba(59,130,246,0.14)', fg: '#93c5fd', border: 'rgba(59,130,246,0.45)' };
  return { bg: 'rgba(82,82,91,0.16)', fg: '#d4d4d8', border: 'rgba(113,113,122,0.45)' };
}

function headerButtonStyle(kind: 'primary' | 'ghost'): CSSProperties {
  if (kind === 'primary') {
    return {
      height: 34,
      borderRadius: 10,
      border: '1px solid #3f3f46',
      background: '#18181b',
      color: '#fafafa',
      fontSize: 12,
      padding: '0 12px',
      cursor: 'pointer',
      fontWeight: 600,
    };
  }

  return {
    height: 34,
    borderRadius: 10,
    border: `1px solid ${BORDER}`,
    background: '#0f0f10',
    color: '#d4d4d8',
    fontSize: 12,
    padding: '0 12px',
    cursor: 'pointer',
    fontWeight: 600,
  };
}

const tableHeadCellStyle: CSSProperties = {
  color: '#a1a1aa',
  textAlign: 'left',
  fontSize: 11,
  letterSpacing: 0.5,
  fontWeight: 600,
  padding: '8px 10px',
};

const tableCellStyle: CSSProperties = {
  color: '#e4e4e7',
  fontSize: 12,
  padding: '8px 10px',
};

function Sidebar(props: {
  workspaces: WorkspaceRecord[];
  selectedWorkspaceId: string | null;
  expandedWorkspaceIds: Set<string>;
  onSelectWorkspace: (workspaceId: string) => void;
  onToggleWorkspace: (workspaceId: string) => void;
}) {
  const { workspaces, selectedWorkspaceId, expandedWorkspaceIds, onSelectWorkspace, onToggleWorkspace } = props;

  return (
    <aside
      style={{
        width: 300,
        background: SURFACE_1,
        borderRight: `1px solid ${BORDER}`,
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',
      }}
    >
      <div style={{ padding: '20px 18px', borderBottom: `1px solid ${BORDER}` }}>
        <div style={{ color: TEXT_PRIMARY, fontWeight: 700, letterSpacing: 0.4 }}>InsightGraph</div>
        <div style={{ color: TEXT_SECONDARY, fontSize: 12, marginTop: 4 }}>Live Architecture Mission Control</div>
      </div>

      <div style={{ padding: '18px' }}>
        <div style={{ fontSize: 11, letterSpacing: 1.2, color: '#71717a', marginBottom: 10 }}>WORKSPACES</div>

        <div style={{ display: 'grid', gap: 8 }}>
          {workspaces.map((workspace) => {
            const isSelected = selectedWorkspaceId === workspace.id;
            const expanded = expandedWorkspaceIds.has(workspace.id);

            return (
              <div key={workspace.id} style={{ border: `1px solid ${isSelected ? '#3f3f46' : BORDER}`, borderRadius: 10, overflow: 'hidden' }}>
                <button
                  type="button"
                  onClick={() => onSelectWorkspace(workspace.id)}
                  style={{
                    width: '100%',
                    background: isSelected ? 'rgba(39,39,42,0.65)' : 'rgba(23,23,23,0.6)',
                    border: 'none',
                    color: TEXT_PRIMARY,
                    padding: '10px 12px',
                    textAlign: 'left',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{workspace.name}</div>
                    <div style={{ color: TEXT_SECONDARY, fontSize: 11, marginTop: 2 }}>{workspace.projects.length} projetos</div>
                  </div>
                  <span
                    onClick={(event) => {
                      event.stopPropagation();
                      onToggleWorkspace(workspace.id);
                    }}
                    style={{ color: '#d4d4d8', fontSize: 12 }}
                  >
                    {expanded ? '▾' : '▸'}
                  </span>
                </button>

                {expanded && (
                  <div style={{ background: 'rgba(9,9,11,0.95)', padding: '8px 10px 10px' }}>
                    {workspace.projects.map((project) => {
                      const meta = STATUS_META[project.status] || STATUS_META.idle;
                      return (
                        <div key={project.id} style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#d4d4d8', fontSize: 12, padding: '6px 4px' }}>
                          <span
                            style={{
                              width: 6,
                              height: 6,
                              borderRadius: 999,
                              background: meta.dot,
                              boxShadow: project.status === 'watching' ? `0 0 8px ${meta.dot}` : undefined,
                              animation: project.status === 'watching' ? 'igPulse 1.2s ease-in-out infinite' : undefined,
                            }}
                          />
                          <span style={{ color: '#a1a1aa', fontSize: 10, width: 18 }}>{projectIcon(project.type)}</span>
                          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{project.name}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </aside>
  );
}

function HeaderBar(props: {
  currentWorkspace?: WorkspaceRecord | null;
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  onAddWorkspace: () => void;
  onAddProject: () => void;
  onRescanAll: () => void;
  onOpen4D: () => void;
}) {
  const { currentWorkspace, searchQuery, onSearchQueryChange, onAddWorkspace, onAddProject, onRescanAll, onOpen4D } = props;

  return (
    <header
      style={{
        height: 76,
        borderBottom: `1px solid ${BORDER}`,
        background: 'rgba(9,9,11,0.88)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
      }}
    >
      <div style={{ display: 'grid', gap: 8, width: 'min(620px, 64vw)' }}>
        <div style={{ color: '#d4d4d8', fontSize: 12 }}>InsightGraph / {currentWorkspace?.name ?? 'No workspace selected'}</div>
        <input
          value={searchQuery}
          onChange={(event) => onSearchQueryChange(event.target.value)}
          placeholder="Search symbols ou repos..."
          style={{
            height: 36,
            borderRadius: 10,
            border: `1px solid ${BORDER}`,
            background: SURFACE_2,
            color: TEXT_PRIMARY,
            padding: '0 12px',
            outline: 'none',
            fontSize: 13,
          }}
        />
      </div>

      <div style={{ display: 'flex', gap: 10 }}>
        <button style={headerButtonStyle('ghost')} onClick={onOpen4D}>🚀 4D Matrix</button>
        <button style={headerButtonStyle('ghost')} onClick={onRescanAll}>Rescan All</button>
        <button style={headerButtonStyle('ghost')} onClick={onAddWorkspace}>Add Workspace</button>
        <button style={headerButtonStyle('primary')} onClick={onAddProject}>Add Project</button>
      </div>
    </header>
  );
}

function ImpactPanel(props: { events: ImpactDetectedEventEnvelope[] }) {
  const latest = props.events[0];
  const rows = latest?.payload?.affected ?? [];
  const hasBreaking = rows.some((row) => row.severity === 'BREAKING');

  return (
    <section
      style={{
        border: `1px solid ${hasBreaking ? 'rgba(244,63,94,0.55)' : BORDER}`,
        borderRadius: 14,
        background: hasBreaking ? 'linear-gradient(180deg, rgba(127,29,29,0.24), rgba(9,9,11,0.92))' : 'linear-gradient(180deg, rgba(23,23,23,0.85), rgba(9,9,11,0.92))',
        boxShadow: hasBreaking ? '0 0 0 1px rgba(244,63,94,0.14), 0 0 32px rgba(244,63,94,0.2)' : 'none',
        padding: 16,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
        <div style={{ color: TEXT_PRIMARY, fontSize: 16, fontWeight: 700 }}>Cross-Project Impact (LIVE)</div>
        <div style={{ color: TEXT_SECONDARY, fontSize: 12 }}>{latest ? `Ultimo evento: ${new Date(latest.timestamp * 1000).toLocaleTimeString()}` : 'Sem eventos'}</div>
      </div>

      {latest && hasBreaking && <div style={{ marginBottom: 12, color: '#fecdd3', fontSize: 13 }}>O endpoint/contrato alterado propagou quebra entre projetos dependentes.</div>}

      {rows.length === 0 ? (
        <div style={{ color: TEXT_SECONDARY, fontSize: 13 }}>Nenhum impacto cruzado detectado no momento.</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
            <thead>
              <tr>
                {['Simbolo Alterado', 'Relacionamento', 'Projeto Afetado', 'Severidade'].map((header) => (
                  <th key={header} style={tableHeadCellStyle}>{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const badge = severityStyle(row.severity);
                const symbol = row.symbol_name || row.node_key || '-';
                return (
                  <tr key={`${row.project_id}-${row.node_key ?? row.symbol_name}-${index}`} style={{ borderTop: `1px solid ${BORDER}` }}>
                    <td style={tableCellStyle}>{symbol}</td>
                    <td style={tableCellStyle}>{row.relation_type}</td>
                    <td style={tableCellStyle}>{row.project_name}</td>
                    <td style={tableCellStyle}>
                      <span
                        style={{
                          border: `1px solid ${badge.border}`,
                          background: badge.bg,
                          color: badge.fg,
                          borderRadius: 999,
                          fontSize: 11,
                          padding: '3px 9px',
                          fontWeight: 700,
                          letterSpacing: 0.2,
                        }}
                      >
                        {row.severity}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function StatusCard({ project }: { project: ProjectRecord }) {
  const meta = STATUS_META[project.status] || STATUS_META.idle;
  const healthPercent = Math.max(15, Math.min(98, project.status === 'error' ? 28 : project.status === 'scanning' ? 62 : 86));

  return (
    <article
      style={{
        border: `1px solid ${BORDER}`,
        borderRadius: 14,
        background: 'linear-gradient(180deg, rgba(23,23,23,0.9), rgba(9,9,11,0.95))',
        padding: 14,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ color: '#d4d4d8', fontSize: 12 }}>{project.type.toUpperCase()}</div>
          <div style={{ color: TEXT_PRIMARY, fontWeight: 700, marginTop: 3 }}>{project.name}</div>
        </div>
        <span
          style={{
            border: `1px solid ${meta.dot}`,
            background: meta.badgeBg,
            color: meta.badgeFg,
            borderRadius: 999,
            fontSize: 10,
            padding: '3px 9px',
            fontWeight: 700,
            letterSpacing: 0.5,
          }}
        >
          {meta.label}
        </span>
      </div>

      <div style={{ marginTop: 10, color: TEXT_SECONDARY, fontSize: 12 }}>{formatElapsed(project.updated_at)}</div>

      <div style={{ marginTop: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', color: '#a1a1aa', fontSize: 11 }}>
          <span>Code Health</span>
          <span>{healthPercent}%</span>
        </div>
        <div
          style={{
            marginTop: 6,
            height: 7,
            borderRadius: 999,
            background: '#18181b',
            border: `1px solid ${BORDER}`,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${healthPercent}%`,
              height: '100%',
              background: `linear-gradient(90deg, ${meta.dot}, rgba(255,255,255,0.32))`,
            }}
          />
        </div>
      </div>
    </article>
  );
}

function LiveFeed({ lines }: { lines: string[] }) {
  return (
    <section
      style={{
        border: `1px solid ${BORDER}`,
        borderRadius: 14,
        background: '#000000',
        padding: 14,
        height: 350,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div style={{ color: '#d4d4d8', fontWeight: 700, marginBottom: 10 }}>Live Event Feed</div>
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace',
          fontSize: 12,
          color: '#a3a3a3',
          lineHeight: 1.42,
        }}
      >
        {lines.map((line, index) => (
          <div key={`${line}-${index}`} style={{ padding: '3px 0', borderBottom: '1px solid rgba(31,31,31,0.7)' }}>{line}</div>
        ))}
      </div>
    </section>
  );
}

function Architecture4DModal(props: {
  open: boolean;
  loading: boolean;
  symbolQuery: string;
  blastResult: BlastRadiusResponse | null;
  godSymbols: GodSymbolItem[];
  onClose: () => void;
  onSymbolQueryChange: (value: string) => void;
  onRunSimulation: () => void;
}) {
  const { open, loading, symbolQuery, blastResult, godSymbols, onClose, onSymbolQueryChange, onRunSimulation } = props;
  if (!open) return null;

  const sortedBlast = [...(blastResult?.blast_radius ?? [])].sort((a, b) => a.hop - b.hop);

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.72)', zIndex: 2200, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div style={{ width: 'min(1240px, 95vw)', height: 'min(86vh, 920px)', background: SURFACE_1, border: `1px solid ${BORDER}`, borderRadius: 16, display: 'grid', gridTemplateRows: 'auto 1fr' }}>
        <div style={{ padding: '14px 16px', borderBottom: `1px solid ${BORDER}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ color: TEXT_PRIMARY, fontWeight: 700, fontSize: 16 }}>🚀 4D ARCHITECTURE MATRIX</div>
            <div style={{ color: TEXT_SECONDARY, fontSize: 12, marginTop: 3 }}>Blast Radius transitivo (N-Hops) e gargalos arquiteturais</div>
          </div>
          <button style={headerButtonStyle('ghost')} onClick={onClose}>Fechar</button>
        </div>

        <div style={{ padding: 16, display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 14, overflow: 'hidden' }}>
          <section style={{ border: `1px solid ${BORDER}`, borderRadius: 12, padding: 14, background: 'rgba(23,23,23,0.8)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <input
                value={symbolQuery}
                onChange={(event) => onSymbolQueryChange(event.target.value)}
                placeholder="Simulate Blast Radius (ex: AuthService.login)"
                style={{
                  flex: 1,
                  height: 36,
                  borderRadius: 10,
                  border: `1px solid ${BORDER}`,
                  background: SURFACE_2,
                  color: TEXT_PRIMARY,
                  padding: '0 12px',
                  fontSize: 13,
                  outline: 'none',
                }}
              />
              <button style={headerButtonStyle('primary')} onClick={onRunSimulation} disabled={loading || !symbolQuery.trim()}>
                {loading ? 'Simulating...' : 'Simular'}
              </button>
            </div>

            <div style={{ color: TEXT_SECONDARY, fontSize: 12, marginBottom: 10 }}>
              {blastResult ? `Origens: ${blastResult.origin_nodes.length} | Impactados: ${blastResult.total_impacted} | Max hops: ${blastResult.max_hops}` : 'Execute uma simulacao para visualizar a reacao em cadeia.'}
            </div>

            <div style={{ overflowY: 'auto', flex: 1, border: `1px solid ${BORDER}`, borderRadius: 10, padding: 12, background: '#09090b' }}>
              {sortedBlast.length === 0 ? (
                <div style={{ color: '#71717a', fontSize: 13 }}>Nenhum resultado para a simulacao atual.</div>
              ) : (
                sortedBlast.map((item, index) => {
                  const pad = Math.max(0, item.hop) * 18;
                  const sev = severityStyle(item.severity);
                  return (
                    <div key={`${item.node_key}-${index}`} style={{ marginLeft: pad, borderLeft: item.hop > 0 ? '1px solid #27272a' : 'none', paddingLeft: item.hop > 0 ? 10 : 0, marginBottom: 9 }}>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                        {item.hop > 0 && <span style={{ color: '#71717a', fontSize: 12 }}>↳</span>}
                        <span style={{ color: TEXT_PRIMARY, fontSize: 13 }}>[{item.project_name ?? 'N/A'}/{item.node_name}]</span>
                        <span
                          style={{
                            border: `1px solid ${sev.border}`,
                            background: sev.bg,
                            color: sev.fg,
                            borderRadius: 999,
                            fontSize: 10,
                            padding: '2px 7px',
                            fontWeight: 700,
                          }}
                        >
                          {item.severity}
                        </span>
                        <span style={{ color: '#71717a', fontSize: 11 }}>hop {item.hop}</span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </section>

          <section style={{ border: `1px solid ${BORDER}`, borderRadius: 12, padding: 14, background: 'rgba(23,23,23,0.8)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ color: TEXT_PRIMARY, fontWeight: 700, marginBottom: 8 }}>Architectural Bottlenecks (God Symbols)</div>
            <div style={{ color: TEXT_SECONDARY, fontSize: 12, marginBottom: 12 }}>Top simbolos mais acoplados no ecossistema atual</div>

            <div style={{ overflowY: 'auto', flex: 1 }}>
              {godSymbols.length === 0 ? (
                <div style={{ color: '#71717a', fontSize: 13 }}>Nenhum dado de gargalo encontrado.</div>
              ) : (
                <div style={{ display: 'grid', gap: 8 }}>
                  {godSymbols.map((item) => (
                    <div key={item.node_key} style={{ border: `1px solid ${BORDER}`, borderRadius: 10, padding: 10, background: '#09090b' }}>
                      <div style={{ color: TEXT_PRIMARY, fontSize: 13, fontWeight: 600 }}>{item.name}</div>
                      <div style={{ color: TEXT_SECONDARY, fontSize: 11, marginTop: 2 }}>{item.project_name ?? 'N/A'} · {item.file ?? item.node_key}</div>
                      <div style={{ display: 'flex', gap: 12, marginTop: 8, fontSize: 11, color: '#a1a1aa' }}>
                        <span>Total: {item.total_dependencies}</span>
                        <span>Inbound: {item.inbound_dependencies}</span>
                        <span>Outbound: {item.outbound_dependencies}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default function ProjectManagement() {
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null);
  const [expandedWorkspaceIds, setExpandedWorkspaceIds] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');

  const [impactEvents, setImpactEvents] = useState<ImpactDetectedEventEnvelope[]>([]);
  const [liveFeedLines, setLiveFeedLines] = useState<string[]>([]);

  const [modal4DOpen, setModal4DOpen] = useState(false);
  const [symbolQuery, setSymbolQuery] = useState('');
  const [blastResult, setBlastResult] = useState<BlastRadiusResponse | null>(null);
  const [godSymbols, setGodSymbols] = useState<GodSymbolItem[]>([]);
  const [simLoading, setSimLoading] = useState(false);

  const selectedWorkspace = useMemo(() => workspaces.find((workspace) => workspace.id === selectedWorkspaceId) ?? null, [workspaces, selectedWorkspaceId]);

  const filteredProjects = useMemo(() => {
    const projects = selectedWorkspace?.projects ?? [];
    const query = searchQuery.trim().toLowerCase();
    if (!query) return projects;
    return projects.filter((project) => project.name.toLowerCase().includes(query) || project.type.toLowerCase().includes(query) || project.path.toLowerCase().includes(query));
  }, [searchQuery, selectedWorkspace?.projects]);

  const loadWorkspaces = useCallback(async () => {
    const response = await fetch('/api/workspaces');
    if (!response.ok) throw new Error(await response.text());

    const data: WorkspaceRecord[] = await response.json();
    setWorkspaces(data);

    if (!selectedWorkspaceId && data.length > 0) {
      const first = data[0].id;
      setSelectedWorkspaceId(first);
      setExpandedWorkspaceIds(new Set([first]));
    }
  }, [selectedWorkspaceId]);

  const loadGodSymbols = useCallback(async (workspaceId: string) => {
    const response = await fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/analysis/god-symbols`);
    if (!response.ok) {
      setGodSymbols([]);
      return;
    }
    const payload: GodSymbolsResponse = await response.json();
    setGodSymbols(payload.items ?? []);
  }, []);

  const run4DSimulation = useCallback(async () => {
    if (!selectedWorkspaceId || !symbolQuery.trim()) return;
    setSimLoading(true);
    try {
      const response = await fetch(`/api/workspaces/${encodeURIComponent(selectedWorkspaceId)}/analysis/4d-blast-radius?symbol=${encodeURIComponent(symbolQuery.trim())}`);
      if (!response.ok) throw new Error(await response.text());
      const payload: BlastRadiusResponse = await response.json();
      setBlastResult(payload);
    } catch {
      setBlastResult(null);
    } finally {
      setSimLoading(false);
    }
  }, [selectedWorkspaceId, symbolQuery]);

  useEffect(() => {
    void loadWorkspaces();
  }, [loadWorkspaces]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      void loadWorkspaces();
    }, 8000);
    return () => window.clearInterval(intervalId);
  }, [loadWorkspaces]);

  useEffect(() => {
    if (!selectedWorkspaceId) return;
    void loadGodSymbols(selectedWorkspaceId);
  }, [selectedWorkspaceId, loadGodSymbols]);

  useEffect(() => {
    if (!selectedWorkspaceId) return;

    const source = new EventSource(`/api/events/stream?workspace_id=${encodeURIComponent(selectedWorkspaceId)}`);

    source.onmessage = (messageEvent) => {
      let parsed: GenericEventEnvelope;
      try {
        parsed = JSON.parse(messageEvent.data) as GenericEventEnvelope;
      } catch {
        return;
      }

      const ts = new Date((parsed.timestamp || Date.now() / 1000) * 1000).toLocaleTimeString();

      if (isImpactDetected(parsed)) {
        setImpactEvents((prev) => [parsed, ...prev].slice(0, 40));
        const summary = parsed.payload.affected[0];
        const sample = summary ? `[${ts}] [IMPACT] ${summary.symbol_name} -> ${summary.project_name} (${summary.severity})` : `[${ts}] [IMPACT] Impacto cross-project detectado`;
        setLiveFeedLines((prev) => [sample, ...prev].slice(0, 250));
        return;
      }

      if (isGraphUpdated(parsed)) {
        const file = parsed.payload.file ?? 'arquivo desconhecido';
        const line = `[${ts}] [${parsed.payload.project_name}] ${file} modificado. Scanning...`;
        setLiveFeedLines((prev) => [line, ...prev].slice(0, 250));
        return;
      }

      setLiveFeedLines((prev) => [`[${ts}] [${parsed.type}] evento recebido`, ...prev].slice(0, 250));
    };

    source.onerror = () => {
      source.close();
    };

    return () => source.close();
  }, [selectedWorkspaceId]);

  const handleSelectWorkspace = useCallback((workspaceId: string) => {
    setSelectedWorkspaceId(workspaceId);
    setExpandedWorkspaceIds((prev) => {
      const next = new Set(prev);
      next.add(workspaceId);
      return next;
    });
  }, []);

  const handleToggleWorkspace = useCallback((workspaceId: string) => {
    setExpandedWorkspaceIds((prev) => {
      const next = new Set(prev);
      if (next.has(workspaceId)) next.delete(workspaceId);
      else next.add(workspaceId);
      return next;
    });
  }, []);

  const handleAddProject = useCallback(async () => {
    if (!selectedWorkspace) return;

    const name = window.prompt('Nome do projeto (Backend, Frontend, Mobile):');
    if (!name) return;
    const path = window.prompt('Caminho absoluto do projeto:');
    if (!path) return;
    const type = (window.prompt('Tipo: backend, frontend, mobile, other', 'other') || 'other').toLowerCase();

    const response = await fetch(`/api/workspaces/${selectedWorkspace.id}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, path, type }),
    });

    if (!response.ok) {
      alert(await response.text());
      return;
    }

    await loadWorkspaces();
  }, [loadWorkspaces, selectedWorkspace]);

  const handleAddWorkspace = useCallback(async () => {
    const name = window.prompt('Nome do workspace:');
    if (!name) return;
    const rootPath = window.prompt('Caminho raiz absoluto do workspace:');
    if (!rootPath) return;

    const response = await fetch('/api/workspaces', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, root_path: rootPath }),
    });

    if (!response.ok) {
      alert(await response.text());
      return;
    }

    const created: WorkspaceRecord = await response.json();
    setSelectedWorkspaceId(created.id);
    await loadWorkspaces();
  }, [loadWorkspaces]);

  const handleRescanAll = useCallback(async () => {
    if (!selectedWorkspace || selectedWorkspace.projects.length === 0) {
      const stamp = new Date().toLocaleTimeString();
      setLiveFeedLines((prev) => [`[${stamp}] [SYSTEM] Nenhum projeto cadastrado para rescan`, ...prev].slice(0, 250));
      return;
    }

    const paths = selectedWorkspace.projects.map((project) => project.path).filter(Boolean);
    const stamp = new Date().toLocaleTimeString();
    setLiveFeedLines((prev) => [`[${stamp}] [SYSTEM] Rescan all iniciado para ${paths.length} projeto(s)`, ...prev].slice(0, 250));

    try {
      const response = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: 'local',
          paths,
          triggered_by: 'project_management_rescan',
        }),
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      const failStamp = new Date().toLocaleTimeString();
      setLiveFeedLines((prev) => [`[${failStamp}] [SYSTEM] Falha no rescan: ${errorMessage}`, ...prev].slice(0, 250));
    }
  }, [selectedWorkspace]);

  return (
    <div style={{ display: 'flex', background: SURFACE_0, color: TEXT_PRIMARY, minHeight: '100vh' }}>
      <style>{`
        @keyframes igPulse {
          0% { transform: scale(1); opacity: 0.75; }
          50% { transform: scale(1.22); opacity: 1; }
          100% { transform: scale(1); opacity: 0.75; }
        }
      `}</style>

      <Sidebar
        workspaces={workspaces}
        selectedWorkspaceId={selectedWorkspaceId}
        expandedWorkspaceIds={expandedWorkspaceIds}
        onSelectWorkspace={handleSelectWorkspace}
        onToggleWorkspace={handleToggleWorkspace}
      />

      <div style={{ flex: 1, display: 'grid', gridTemplateRows: 'auto 1fr' }}>
        <HeaderBar
          currentWorkspace={selectedWorkspace}
          searchQuery={searchQuery}
          onSearchQueryChange={setSearchQuery}
          onAddWorkspace={() => void handleAddWorkspace()}
          onAddProject={handleAddProject}
          onRescanAll={() => void handleRescanAll()}
          onOpen4D={() => setModal4DOpen(true)}
        />

        <main style={{ padding: 16, display: 'grid', gridTemplateRows: 'auto 1fr', gap: 14 }}>
          <ImpactPanel events={impactEvents} />

          <section style={{ display: 'grid', gridTemplateColumns: '1.45fr 1fr', gap: 14, minHeight: 0 }}>
            <div style={{ border: `1px solid ${BORDER}`, borderRadius: 14, background: 'linear-gradient(180deg, rgba(23,23,23,0.9), rgba(9,9,11,0.94))', padding: 14, display: 'grid', gridTemplateRows: 'auto 1fr', minHeight: 0 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div style={{ color: TEXT_PRIMARY, fontSize: 15, fontWeight: 700 }}>Project Status</div>
                <div style={{ color: TEXT_SECONDARY, fontSize: 12 }}>{filteredProjects.length} projetos no workspace atual</div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: 10, alignContent: 'start', overflowY: 'auto', paddingRight: 2 }}>
                {filteredProjects.length === 0 ? (
                  <div style={{ color: '#71717a', fontSize: 13 }}>Nenhum projeto para os filtros atuais.</div>
                ) : (
                  filteredProjects.map((project) => <StatusCard key={project.id} project={project} />)
                )}
              </div>
            </div>

            <LiveFeed lines={liveFeedLines} />
          </section>
        </main>
      </div>

      <Architecture4DModal
        open={modal4DOpen}
        loading={simLoading}
        symbolQuery={symbolQuery}
        blastResult={blastResult}
        godSymbols={godSymbols}
        onClose={() => setModal4DOpen(false)}
        onSymbolQueryChange={setSymbolQuery}
        onRunSimulation={() => void run4DSimulation()}
      />
    </div>
  );
}
