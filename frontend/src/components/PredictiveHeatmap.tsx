import React from 'react';

interface PredictiveHeatmapProps {
  onHeatmapChange: (type: 'risk' | 'activity' | 'complexity') => void;
  currentHeatmap: 'risk' | 'activity' | 'complexity';
}

const PredictiveHeatmap: React.FC<PredictiveHeatmapProps> = ({
  onHeatmapChange,
  currentHeatmap,
}) => {
  const handleHeatmapToggle = (type: 'risk' | 'activity' | 'complexity') => {
    onHeatmapChange(type);
  };

  return (
    <div className="predictive-heatmap">
      <div className="heatmap-controls">
        <label>Heatmap Type:</label>
        <select
          value={currentHeatmap}
          onChange={(e) => handleHeatmapToggle(e.target.value as any)}
        >
          <option value="risk">Risk Prediction</option>
          <option value="activity">Activity</option>
          <option value="complexity">Complexity</option>
        </select>
      </div>
      <div className="heatmap-legend">
        <div className="legend-item">
          <div className="color-box" style={{ backgroundColor: '#22c55e' }}></div>
          <span>Low</span>
        </div>
        <div className="legend-item">
          <div className="color-box" style={{ backgroundColor: '#eab308' }}></div>
          <span>Medium</span>
        </div>
        <div className="legend-item">
          <div className="color-box" style={{ backgroundColor: '#dc2626' }}></div>
          <span>High</span>
        </div>
      </div>
    </div>
  );
};

export default PredictiveHeatmap;
