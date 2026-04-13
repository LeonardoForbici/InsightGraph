import { useEffect } from 'react';
import type React from 'react';

export interface ImpactNotificationEntry {
  id: string;
  nodeKey: string;
  fileName: string;
  affectedCount: number;
  severity: 'low' | 'medium' | 'high';
  timestamp: number;
  autoHide: boolean;
}

interface ImpactNotificationProps {
  impacts: ImpactNotificationEntry[];
  onToastClick: (nodeKey: string) => void;
  onDismiss: (id: string) => void;
}

const ImpactNotification: React.FC<ImpactNotificationProps> = ({ impacts, onToastClick, onDismiss }) => {
  const visibleImpacts = impacts.slice(0, 3);

  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    visibleImpacts.forEach((impact) => {
      if (impact.autoHide) {
        timers.push(setTimeout(() => onDismiss(impact.id), 5000));
      }
    });
    return () => timers.forEach((timer) => clearTimeout(timer));
  }, [visibleImpacts, onDismiss]);

  if (visibleImpacts.length === 0) {
    return null;
  }

  const formatTimestamp = (timestamp: number) => {
    const diff = Date.now() - timestamp;
    if (diff < 1000) return 'agora mesmo';
    const seconds = Math.floor(diff / 1000);
    if (seconds < 60) return `${seconds}s atrás`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m atrás`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h atrás`;
  };

  const severityClass = (severity: ImpactNotificationEntry['severity']) => {
    switch (severity) {
      case 'high':
        return 'impact-notification-card--high';
      case 'medium':
        return 'impact-notification-card--medium';
      default:
        return 'impact-notification-card--low';
    }
  };

  return (
    <div className="impact-notification-container">
      {visibleImpacts.map((impact, index) => (
        <div
          key={impact.id}
          className={`impact-notification-card ${severityClass(impact.severity)}`}
          style={{ animationDelay: `${index * 120}ms` }}
          onClick={() => onToastClick(impact.nodeKey)}
        >
          <div className="impact-notification-card__header">
            <span className="impact-notification-card__badge">{impact.severity.toUpperCase()}</span>
            <span className="impact-notification-card__timestamp">{formatTimestamp(impact.timestamp)}</span>
          </div>
          <p className="impact-notification-card__count">
            <strong>{impact.affectedCount}</strong> node{impact.affectedCount !== 1 ? 's' : ''} afetado{impact.affectedCount !== 1 ? 's' : ''}
          </p>
          <p className="impact-notification-card__file" title={impact.fileName}>
            {impact.fileName}
          </p>
          <button
            type="button"
            className="impact-notification-card__close"
            onClick={(event) => {
              event.stopPropagation();
              onDismiss(impact.id);
            }}
            aria-label="Fechar notificação"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
};

export default ImpactNotification;
