/**
 * FRONTEND INTEGRATION GUIDE - GraphCanvas Hotspot Risk Display
 * 
 * Purpose: Display nodes with color intensity based on true_risk_score (Phase 3)
 * 
 * THIS IS DOCUMENTATION ONLY - Copy relevant code/types into your GraphCanvas.tsx
 * 
 * REQUIRED CHANGES:
 * 1. Add RiskMetrics type and utility functions
 * 2. Modify node rendering to use risk-based colors
 * 3. Add risk tooltip on node hover
 * 4. Filter hotspots by severity level
 * 5. Update Dashboard to pass risk metrics
 * 6. Add API calls for risk data
 */

/*
================================================================================
STEP 1: ADD to GraphCanvas.tsx (after imports)
================================================================================

import React, { useState } from 'react';
import { Background, Controls, MiniMap } from 'reactflow';

// Add RiskScore utilities
type RiskSeverity = 'Low' | 'Medium' | 'High' | 'Critical';
type RiskColor = '#22c55e' | '#eab308' | '#f97316' | '#ef4444';

interface RiskMetrics {
  complexity: number;
  churn_rate: number;
  churn_intensity: number;
  true_risk_score: number;
  severity: RiskSeverity;
  color: RiskColor;
}

const getRiskScoreColor = (trueRiskScore: number): { 
  color: RiskColor; 
  severity: RiskSeverity; 
  label: string 
} => {
  if (trueRiskScore < 30) {
    return { color: '#22c55e', severity: 'Low', label: 'Low Risk' };
  } else if (trueRiskScore < 60) {
    return { color: '#eab308', severity: 'Medium', label: 'Medium Risk' };
  } else if (trueRiskScore < 90) {
    return { color: '#f97316', severity: 'High', label: 'High Risk' };
  } else {
    return { color: '#ef4444', severity: 'Critical', label: 'Critical Risk' };
  }
};

const getRiskStatusBadge = (severity: RiskSeverity): string => {
  switch(severity) {
    case 'Critical': return '⚠️ CRITICAL';
    case 'High': return '⚡ HIGH';
    case 'Medium': return '⚙️ MEDIUM';
    case 'Low': return '✓ LOW';
  }
};

================================================================================
STEP 2: Update GraphCanvas Component Props & State
================================================================================

interface GraphCanvasProps {
  nodes: any[];
  edges: any[];
  selectedNode: any;
  onNodeClick: (node: any) => void;
  onEdgeClick: (edge: any) => void;
  riskFilter?: 'All' | 'Critical' | 'High' | 'Medium' | 'Low';
}

Inside GraphCanvas component body, add:

  const [hoveredNodeRisk, setHoveredNodeRisk] = useState<RiskMetrics | null>(null);
  const [hoverPosition, setHoverPosition] = useState({ x: 0, y: 0 });

  const transformedNodes = nodes.map((node: any) => {
    const trueRiskScore = node.data?.true_risk_score || 0;
    const { color, severity, label } = getRiskScoreColor(trueRiskScore);
    
    if (riskFilter && riskFilter !== 'All' && severity !== riskFilter) {
      return { ...node, hidden: true };
    }

    return {
      ...node,
      style: {
        ...node.style,
        backgroundColor: color,
        borderColor: color,
        boxShadow: trueRiskScore > 70 
          ? `0 0 20px ${color}, inset 0 0 10px ${color}80`
          : `0 0 10px ${color}80`,
        opacity: trueRiskScore > 50 ? 1 : 0.7,
        fontWeight: trueRiskScore > 70 ? 'bold' : 'normal',
        borderWidth: trueRiskScore > 70 ? '3px' : '2px',
      },
      data: {
        ...node.data,
        risk_metadata: {
          true_risk_score: trueRiskScore,
          severity: severity,
          color: color,
          label: label
        }
      }
    };
  });

================================================================================
STEP 3: Add Node Hover Handler
================================================================================

  const handleNodeHover = async (
    nodeId: string, 
    position: { x: number; y: number }
  ): Promise<void> => {
    try {
      const response = await fetch(`/api/node/${nodeId}/risk-metrics`);
      if (response.ok) {
        const metrics: any = await response.json();
        setHoveredNodeRisk({
          complexity: metrics.cyclomatic_complexity || 0,
          churn_rate: metrics.churn_rate || 0,
          churn_intensity: metrics.churn_intensity || 0,
          true_risk_score: metrics.true_risk_score || 0,
          severity: metrics.severity || 'Low',
          color: metrics.color?.color || '#22c55e' as RiskColor
        });
        setHoverPosition(position);
      }
    } catch (error) {
      console.error('Error fetching risk metrics:', error);
    }
  };

  const handleNodeLeave = (): void => {
    setHoveredNodeRisk(null);
  };

================================================================================
STEP 4: Return JSX with Risk UI Components
================================================================================

Return from GraphCanvas component:

  return (
    <div className="w-full h-full bg-slate-900 relative">
      <div className="absolute top-4 left-4 z-10 bg-slate-800 rounded-lg p-4 border border-cyan-500/30">
        <h3 className="text-cyan-400 font-semibold mb-2">Risk Filter</h3>
        <div className="flex flex-col gap-2">
          {['All', 'Critical', 'High', 'Medium', 'Low'].map((severity) => (
            <button key={severity} className="px-3 py-1 rounded text-sm font-medium transition">
              {severity}
            </button>
          ))}
        </div>
      </div>

      {hoveredNodeRisk && (
        <div className="absolute bg-slate-900 border-2 rounded-lg p-3 z-50 pointer-events-none">
          Risk metrics tooltip here
        </div>
      )}

      <div className="absolute bottom-4 right-4 z-10 bg-slate-800 rounded-lg p-4 border border-cyan-500/30">
        <h3 className="text-cyan-400 font-semibold mb-2 text-sm">Risk Levels</h3>
      </div>

      <div className="w-full h-full">
        <Background />
        <Controls />
        <MiniMap />
      </div>
    </div>
  );

================================================================================
STEP 5: UPDATE Dashboard.tsx
================================================================================

Add risk filtering state:
  const [riskFilter, setRiskFilter] = useState<'All' | 'Critical' | 'High' | 'Medium' | 'Low'>('All');

When fetching graph data, add risk metrics:
  const enhancedNodes = graphNodes.map((node: any) => ({
    ...node,
    data: {
      ...node.data,
      true_risk_score: node.data.true_risk_score || 0,
      churn_rate: node.data.churn_rate || 0,
      churn_intensity: node.data.churn_intensity || 0,
    }
  }));

Pass to GraphCanvas with riskFilter prop:
  <GraphCanvas
    nodes={enhancedNodes}
    edges={graphEdges}
    selectedNode={selectedNode}
    onNodeClick={handleNodeClick}
    onEdgeClick={handleEdgeClick}
    riskFilter={riskFilter}
  />

Add this card to Dashboard render:
  <div className="bg-slate-800 border border-cyan-500/20 rounded-lg p-6 col-span-2">
    <h3 className="text-lg font-semibold text-cyan-400 mb-4">
      🔴 True Risk Hotspots (Complexity × Churn)
    </h3>
    {antipatterns?.true_risk_hotspots && antipatterns.true_risk_hotspots.length > 0 ? (
      <div className="space-y-2 max-h-64 overflow-y-auto">
        {antipatterns.true_risk_hotspots.map((hotspot: any) => (
          <div
            key={hotspot.namespace_key}
            className="bg-slate-700/50 hover:bg-slate-700 border-l-4 p-3 rounded"
            onClick={() => onNodeClick(hotspot)}
          >
            <p className="text-white font-mono text-sm">{hotspot.namespace_key}</p>
            <p className="text-xs text-slate-400">Risk Score: {hotspot.true_risk_score.toFixed(1)}</p>
          </div>
        ))}
      </div>
    ) : (
      <p className="text-slate-400 text-sm">No high-risk hotspots. Good job! 🎉</p>
    )}
  </div>

================================================================================
API UPDATE: src/api.ts - New endpoints
================================================================================

export interface RiskMetrics {
  namespace_key: string;
  cyclomatic_complexity: number;
  churn_rate: number;
  churn_intensity: number;
  commit_count: number;
  true_risk_score: number;
  severity: 'Low' | 'Medium' | 'High' | 'Critical';
  color: {
    color: '#22c55e' | '#eab308' | '#f97316' | '#ef4444';
    label: string;
  };
}

export async function getNodeRiskMetrics(nodeKey: string): Promise<RiskMetrics> {
  const response = await fetch(`/api/node/${nodeKey}/risk-metrics`);
  if (!response.ok) throw new Error('Failed to fetch risk metrics');
  return response.json();
}

export interface TaintTraceResult {
  source: string;
  flows: Array<{
    start_prop: string;
    paths: any[];
    affected_components: string[];
  }>;
  recommendation: string;
}

export async function traceTaintFlow(propertyName: string): Promise<TaintTraceResult> {
  const response = await fetch(`/api/taint/trace/${propertyName}`);
  if (!response.ok) throw new Error('Taint trace failed');
  return response.json();
}

================================================================================
STYLING: Tailwind classes reference
================================================================================

const riskColorClasses = {
  critical: 'from-red-900 to-red-700',
  high: 'from-orange-900 to-orange-700',
  medium: 'from-yellow-900 to-yellow-700',
  low: 'from-green-900 to-green-700',
};

================================================================================
TESTING: Verification Checklist
================================================================================

1. Dashboard loads and displays True Risk Hotspots section
2. Hover over a node to see risk metrics tooltip
3. Node colors change based on true_risk_score
   - Red (#ef4444) for scores > 70
   - Orange (#f97316) for scores 60-70
   - Yellow (#eab308) for scores 30-60
   - Green (#22c55e) for scores < 30
4. Risk filter buttons work (All, Critical, High, Medium, Low)
5. Click hotspot to select node in GraphCanvas
6. Legend displays correctly in bottom-right corner
7. API call GET /api/node/{key}/risk-metrics returns valid data
8. Taint flow API Returns sensitive data paths
*/
