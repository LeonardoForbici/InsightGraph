/**
 * SSE Types - Tipos compartilhados para Server-Sent Events
 */

export type SSEEventType = 
    | 'graph_updated'
    | 'impact_detected'
    | 'audit_alert'
    | 'scan_complete'
    | 'node_changed';

export interface SSEEventData {
    type: SSEEventType;
    payload: any;
    timestamp: number;
}

export type SSEEventHandler = (data: SSEEventData) => void;
