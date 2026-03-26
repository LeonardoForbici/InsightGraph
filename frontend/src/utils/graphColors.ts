export const hotspotColorScale = (score?: number): string => {
    if (typeof score !== 'number') return '#7c859c';
    if (score >= 80) return '#f97316';
    if (score >= 60) return '#fb923c';
    if (score >= 40) return '#facc15';
    if (score >= 20) return '#34d399';
    return '#a5b4fc';
};

export const getHeatmapColor = (complexity?: number): string => {
    if (typeof complexity !== 'number') return '#64748b';
    if (complexity > 20) return '#ef4444';
    if (complexity >= 10) return '#f97316';
    if (complexity >= 5) return '#eab308';
    if (complexity >= 1) return '#3b82f6';
    return '#94a3b8';
};

const TYPE_COLOR_MAP: Record<string, string> = {
    Java_Class: '#f97316',
    Java_Method: '#fdba74',
    API_Endpoint: '#67e8f9',
    TS_Component: '#60a5fa',
    TS_Function: '#93c5fd',
    SQL_Table: '#34d399',
    SQL_Procedure: '#6ee7b7',
    Mobile_Component: '#a78bfa',
    External_Dependency: '#cbd5e1',
};

export const getTypeColor = (labels: string[] = []): string => {
    for (const label of labels) {
        if (TYPE_COLOR_MAP[label]) return TYPE_COLOR_MAP[label];
    }
    return '#94a3b8';
};

const LAYER_COLOR_MAP: Record<string, string> = {
    Database: '#34d399',
    Service: '#fbbf24',
    API: '#a78bfa',
    Frontend: '#4f8ff7',
    Mobile: '#38bdf8',
    External: '#f472b6',
    Other: '#7c3aed',
};

export const getLayerColor = (layer?: string): string => {
    if (!layer) return LAYER_COLOR_MAP.Other;
    const normalized = layer.charAt(0).toUpperCase() + layer.slice(1);
    return LAYER_COLOR_MAP[normalized] || LAYER_COLOR_MAP.Other;
};
