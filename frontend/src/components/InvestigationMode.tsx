import React, { useState, useEffect } from 'react';

interface RootCauseAnalysis {
  primary_cause: string;
  contributing_factors: string[];
  confidence: number;
}

interface ImpactLevel {
  depth: number;
  nodes: any[];
  relationships: string[];
}

interface ImpactChain {
  levels: ImpactLevel[];
  total_affected: number;
  max_depth: number;
}

interface Suggestion {
  type: 'refactor' | 'test' | 'document' | 'review';
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  actionable: boolean;
}

interface InvestigationData {
  target_node: any;
  root_cause: RootCauseAnalysis;
  impact_chain: ImpactChain;
  suggestions: Suggestion[];
  blast_radius: number;
  critical_path: string[];
}

interface InvestigationModeProps {
  nodeKey: string;
  onExit: () => void;
  onNodeClick?: (nodeKey: string) => void;
}

const InvestigationMode: React.FC<InvestigationModeProps> = ({
  nodeKey,
  onExit,
  onNodeClick
}) => {
  const [data, setData] = useState<InvestigationData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedLevels, setExpandedLevels] = useState<Set<number>>(new Set([0]));

  useEffect(() => {
    loadInvestigationData();
  }, [nodeKey]);

  const loadInvestigationData = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`/api/investigate/${encodeURIComponent(nodeKey)}`);
      if (!response.ok) {
        throw new Error('Failed to load investigation data');
      }

      const investigationData: InvestigationData = await response.json();
      setData(investigationData);
    } catch (err) {
      console.error('Error loading investigation data:', err);
      setError('Failed to load investigation data');
    } finally {
      setIsLoading(false);
    }
  };

  const toggleLevel = (depth: number) => {
    const newExpanded = new Set(expandedLevels);
    if (newExpanded.has(depth)) {
      newExpanded.delete(depth);
    } else {
      newExpanded.add(depth);
    }
    setExpandedLevels(newExpanded);
  };

  const getPriorityColor = (priority: string): string => {
    switch (priority) {
      case 'high':
        return 'bg-red-500';
      case 'medium':
        return 'bg-yellow-500';
      case 'low':
        return 'bg-green-500';
      default:
        return 'bg-gray-500';
    }
  };

  const getSuggestionIcon = (type: string): string => {
    switch (type) {
      case 'refactor':
        return '🔧';
      case 'test':
        return '🧪';
      case 'document':
        return '📝';
      case 'review':
        return '👁️';
      default:
        return '💡';
    }
  };

  if (isLoading) {
    return (
      <div className="investigation-mode-overlay">
        <div className="investigation-modal loading">
          <p>Analyzing...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="investigation-mode-overlay">
        <div className="investigation-modal error">
          <h2>Investigation Failed</h2>
          <p>{error || 'No data available'}</p>
          <button onClick={onExit} className="exit-button">
            Close
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="investigation-mode-overlay">
      <div className="investigation-modal">
        <div className="investigation-header">
          <h2>Investigation Mode</h2>
          <button onClick={onExit} className="exit-button">
            Exit Investigation
          </button>
        </div>

        <div className="investigation-content">
          {/* Target Node Info */}
          <section className="target-node-section">
            <h3>Target Node</h3>
            <div className="node-info">
              <p className="node-name">{data.target_node.name}</p>
              <p className="node-type">{data.target_node.labels?.[0] || 'Unknown'}</p>
              <div className="node-metrics">
                <span>Complexity: {data.target_node.complexity || 'N/A'}</span>
                <span>LOC: {data.target_node.loc || 'N/A'}</span>
                <span>Hotspot: {data.target_node.hotspot_score || 'N/A'}</span>
              </div>
            </div>
          </section>

          {/* Root Cause Analysis */}
          <section className="root-cause-section">
            <h3>Root Cause Analysis</h3>
            <div className="confidence-bar">
              <span>Confidence: {Math.round(data.root_cause.confidence * 100)}%</span>
              <div className="bar">
                <div
                  className="fill"
                  style={{ width: `${data.root_cause.confidence * 100}%` }}
                />
              </div>
            </div>
            <div className="primary-cause">
              <h4>Primary Cause</h4>
              <p>{data.root_cause.primary_cause}</p>
            </div>
            {data.root_cause.contributing_factors.length > 0 && (
              <div className="contributing-factors">
                <h4>Contributing Factors</h4>
                <ul>
                  {data.root_cause.contributing_factors.map((factor, index) => (
                    <li key={index}>{factor}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {/* Blast Radius & Critical Path */}
          <section className="metrics-section">
            <div className="metric-card">
              <h4>Blast Radius</h4>
              <p className="metric-value">{data.blast_radius}</p>
              <p className="metric-label">Weighted Impact Score</p>
            </div>
            <div className="metric-card">
              <h4>Total Affected</h4>
              <p className="metric-value">{data.impact_chain.total_affected}</p>
              <p className="metric-label">Downstream Nodes</p>
            </div>
            <div className="metric-card">
              <h4>Max Depth</h4>
              <p className="metric-value">{data.impact_chain.max_depth}</p>
              <p className="metric-label">Dependency Levels</p>
            </div>
          </section>

          {/* Impact Chain */}
          <section className="impact-chain-section">
            <h3>Impact Chain</h3>
            <div className="impact-chain-tree">
              {data.impact_chain.levels.map((level) => (
                <div key={level.depth} className="impact-level">
                  <div
                    className="level-header"
                    onClick={() => toggleLevel(level.depth)}
                  >
                    <span className="expand-icon">
                      {expandedLevels.has(level.depth) ? '▼' : '▶'}
                    </span>
                    <span className="level-title">
                      Level {level.depth} ({level.nodes.length} nodes)
                    </span>
                    {level.relationships.length > 0 && (
                      <span className="relationships">
                        via {level.relationships.join(', ')}
                      </span>
                    )}
                  </div>
                  {expandedLevels.has(level.depth) && (
                    <div className="level-nodes">
                      {level.nodes.map((node, index) => (
                        <div
                          key={index}
                          className={`level-node ${
                            data.critical_path.includes(node.namespace_key)
                              ? 'critical'
                              : ''
                          }`}
                          onClick={() =>
                            onNodeClick && onNodeClick(node.namespace_key)
                          }
                        >
                          <span className="node-name">{node.name}</span>
                          <span className="node-complexity">
                            C: {node.complexity || 1}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* Suggestions */}
          <section className="suggestions-section">
            <h3>Suggestions</h3>
            <div className="suggestions-list">
              {data.suggestions.map((suggestion, index) => (
                <div
                  key={index}
                  className={`suggestion-card ${suggestion.priority}`}
                >
                  <div className="suggestion-header">
                    <span className="suggestion-icon">
                      {getSuggestionIcon(suggestion.type)}
                    </span>
                    <h4>{suggestion.title}</h4>
                    <span className={`priority-badge ${getPriorityColor(suggestion.priority)}`}>
                      {suggestion.priority}
                    </span>
                  </div>
                  <p className="suggestion-description">
                    {suggestion.description}
                  </p>
                  <div className="suggestion-meta">
                    <span className="suggestion-type">{suggestion.type}</span>
                    {suggestion.actionable && (
                      <span className="actionable-badge">Actionable</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default InvestigationMode;
