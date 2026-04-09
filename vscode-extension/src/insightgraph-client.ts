export interface ScanResult {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
}

export interface GraphNode {
  id: string;
  name: string;
  layer: string;
  cyclomatic_complexity?: number;
  dependents_count?: number;
  score?: number;
  file?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface ImpactResult {
  target_key: string;
  affected_nodes: GraphNode[];
  affected_count: number;
  max_depth: number;
  impact_score: number;
  antipatterns: AntipatternItem[];
}

export interface AntipatternItem {
  node_key: string;
  type: string;
  description: string;
  severity: string;
}

export interface AntipatternResult {
  antipatterns: AntipatternItem[];
  total: number;
}

export class InsightGraphClient {
  private serverUrl: string;

  constructor(serverUrl: string) {
    this.serverUrl = serverUrl.replace(/\/$/, '');
  }

  async scan(filePath: string): Promise<ScanResult> {
    const response = await fetch(`${this.serverUrl}/api/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: filePath }),
    });
    if (!response.ok) {
      throw new Error(`Scan failed: ${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<ScanResult>;
  }

  async analyzeImpact(targetKey: string): Promise<ImpactResult> {
    const response = await fetch(`${this.serverUrl}/api/impact/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_key: targetKey }),
    });
    if (!response.ok) {
      throw new Error(`Impact analysis failed: ${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<ImpactResult>;
  }

  async checkHealth(): Promise<boolean> {
    try {
      const response = await fetch(`${this.serverUrl}/api/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(5000),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  async getAntipatterns(): Promise<AntipatternResult> {
    const response = await fetch(`${this.serverUrl}/api/antipatterns`, {
      method: 'GET',
    });
    if (!response.ok) {
      throw new Error(`Get antipatterns failed: ${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<AntipatternResult>;
  }
}
