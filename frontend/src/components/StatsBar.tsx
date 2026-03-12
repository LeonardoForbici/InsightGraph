import type { GraphStats } from '../api';

interface StatsBarProps {
    stats: GraphStats | null;
}

const TYPE_ICONS: Record<string, string> = {
    Java_Class: '☕',
    Java_Method: 'ƒ',
    TS_Component: '⚛',
    TS_Function: 'λ',
    SQL_Table: '🗄',
    SQL_Procedure: '⚙',
    Mobile_Component: '📱',
};

const TYPE_TRANSLATIONS: Record<string, string> = {
    Java_Class: 'Classe Java',
    Java_Method: 'Método Java',
    TS_Component: 'Componente TS',
    TS_Function: 'Função TS',
    SQL_Table: 'Tabela SQL',
    SQL_Procedure: 'Procedure SQL',
    Mobile_Component: 'Componente Mobile',
};

export default function StatsBar({ stats }: StatsBarProps) {
    if (!stats || stats.total_nodes === 0) return null;

    const topTypes = Object.entries(stats.nodes_by_type)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 4);

    return (
        <div className="stats-bar">
            <div className="stat-chip">
                <span className="stat-icon">📊</span>
                <span className="stat-value">{stats.total_nodes}</span>
                nós
            </div>
            <div className="stat-divider" />
            <div className="stat-chip">
                <span className="stat-icon">🔗</span>
                <span className="stat-value">{stats.total_edges}</span>
                conexões
            </div>

            {topTypes.length > 0 && (
                <>
                    <div className="stat-divider" />
                    {topTypes.map(([type, count]) => (
                        <div key={type} className="stat-chip">
                            <span className="stat-icon">{TYPE_ICONS[type] || '◇'}</span>
                            <span className="stat-value">{count}</span>
                            {TYPE_TRANSLATIONS[type] || type.replace('_', ' ')}
                        </div>
                    ))}
                </>
            )}

            {stats.projects.length > 0 && (
                <>
                    <div className="stat-divider" />
                    <div className="stat-chip">
                        <span className="stat-icon">📁</span>
                        <span className="stat-value">{stats.projects.length}</span>
                        {stats.projects.length === 1 ? 'projeto' : 'projetos'}
                    </div>
                </>
            )}
        </div>
    );
}
