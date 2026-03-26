import type { QuickActionConfig } from './QuickActionToolbar';

export interface NodeActionAnchor {
    nodeKey: string;
    nodeName: string;
    position: { x: number; y: number };
}

interface NodeQuickActionsProps {
    anchor: NodeActionAnchor | null;
    actions: QuickActionConfig[];
    onClose: () => void;
}

export default function NodeQuickActions({ anchor, actions, onClose }: NodeQuickActionsProps) {
    if (!anchor || !actions.length) return null;
    if (typeof window === 'undefined') return null;

    const bubbleWidth = 260;
    const bubbleHeight = 200;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    let left = anchor.position.x + 16;
    let top = anchor.position.y - bubbleHeight / 2;
    if (left + bubbleWidth > viewportWidth) {
        left = viewportWidth - bubbleWidth - 16;
    }
    if (top < 64) {
        top = 64;
    }
    if (top + bubbleHeight > viewportHeight - 40) {
        top = viewportHeight - bubbleHeight - 40;
    }

    return (
        <div className="node-action-bubble" style={{ left, top }}>
            <div className="node-action-header">
                <div className="node-action-title">Ações rápidas em</div>
                <div className="node-action-node">{anchor.nodeName}</div>
                <button className="node-action-close" onClick={onClose} aria-label="Fechar">×</button>
            </div>
            <div className="node-action-grid">
                {actions.map((action) => (
                    <button
                        key={action.id}
                        className={`node-action-btn ${action.disabled ? 'disabled' : ''}`}
                        onClick={(event) => {
                            action.onClick(event);
                            onClose();
                        }}
                        title={action.tooltip}
                        disabled={action.disabled}
                    >
                        <div className="node-action-icon">{action.icon}</div>
                        <div className="node-action-label">{action.label}</div>
                        {action.shortcut && <span className="node-action-shortcut">{action.shortcut}</span>}
                    </button>
                ))}
            </div>
        </div>
    );
}
