import React, { useEffect } from 'react';

export interface ImpactNotification {
  id: string;
  nodeKey: string;
  fileName: string;
  affectedCount: number;
  severity: 'low' | 'medium' | 'high';
  timestamp: number;
  autoHide: boolean;
}

interface ImpactToastProps {
  impacts: ImpactNotification[];
  onToastClick: (nodeKey: string) => void;
  onDismiss: (id: string) => void;
}

const ImpactToast: React.FC<ImpactToastProps> = ({ impacts, onToastClick, onDismiss }) => {
  const visibleImpacts = impacts.slice(0, 3); // Max 3 visible

  useEffect(() => {
    visibleImpacts.forEach(impact => {
      if (impact.autoHide) {
        const timer = setTimeout(() => onDismiss(impact.id), 8000);
        return () => clearTimeout(timer);
      }
    });
  }, [visibleImpacts, onDismiss]);

  const getSeverityColor = (severity: string): string => {
    switch (severity) {
      case 'high':
        return 'bg-red-500';
      case 'medium':
        return 'bg-yellow-500';
      case 'low':
        return 'bg-green-500';
      default:
        return 'bg-blue-500';
    }
  };

  const getSeverityFromCount = (count: number): 'low' | 'medium' | 'high' => {
    if (count >= 30) return 'high';
    if (count >= 10) return 'medium';
    return 'low';
  };

  const formatTimestamp = (timestamp: number): string => {
    const now = Date.now();
    const diff = now - timestamp;
    const seconds = Math.floor(diff / 1000);
    
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
  };

  if (visibleImpacts.length === 0) {
    return null;
  }

  return (
    <div className="fixed top-4 right-4 space-y-2 z-50">
      {visibleImpacts.map((impact, index) => {
        const severity = impact.severity || getSeverityFromCount(impact.affectedCount);
        const colorClass = getSeverityColor(severity);
        
        return (
          <div
            key={impact.id}
            className={`${colorClass} text-white p-4 rounded-lg shadow-lg cursor-pointer animate-slide-in transition-all duration-300 hover:scale-105`}
            style={{
              animation: `slideIn 0.3s ease-out ${index * 0.1}s both`,
              minWidth: '300px',
              maxWidth: '400px'
            }}
            onClick={() => onToastClick(impact.nodeKey)}
          >
            <div className="flex items-center justify-between">
              <div className="flex-1">
                <p className="font-semibold text-lg">
                  {impact.affectedCount} node{impact.affectedCount !== 1 ? 's' : ''} affected
                </p>
                <p className="text-sm mt-1 truncate" title={impact.fileName}>
                  {impact.fileName}
                </p>
                <p className="text-xs opacity-75 mt-1">
                  {formatTimestamp(impact.timestamp)}
                </p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDismiss(impact.id);
                }}
                className="ml-4 text-white hover:text-gray-200 text-2xl font-bold leading-none"
                aria-label="Dismiss notification"
              >
                ×
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default ImpactToast;
