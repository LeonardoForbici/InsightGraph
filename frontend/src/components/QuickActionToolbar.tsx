import type { MouseEvent } from 'react';

export interface QuickActionConfig {
    id: string;
    label: string;
    icon: string;
    tooltip: string;
    onClick: (event: MouseEvent<HTMLButtonElement>) => void;
    disabled?: boolean;
    shortcut?: string;
}

interface QuickActionToolbarProps {
    actions: QuickActionConfig[];
}

export default function QuickActionToolbar({ actions }: QuickActionToolbarProps) {
    return (
        <div className="quick-action-toolbar">
            {actions.map((action) => (
                <button
                    key={action.id}
                    className={`quick-action-btn ${action.disabled ? 'disabled' : ''}`}
                    onClick={action.onClick}
                    title={action.tooltip}
                    disabled={action.disabled}
                >
                    <span className="quick-action-icon">{action.icon}</span>
                    <span className="quick-action-label">{action.label}</span>
                </button>
            ))}
        </div>
    );
}
