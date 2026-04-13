/**
 * SSE Types - Tipos compartilhados para Server-Sent Events
 */

export type SSEEventType = 
    | 'graph_updated'
    | 'impact_detected'
    | 'audit_alert'
    | 'scan_complete'
    | 'node_changed'
    | 'cicd_build_update'
    | 'collaboration_event'
    | 'chat_message'
    | 'session_replay_ready'
    | 'auto_healer_suggestion';

export interface SSEEventData {
    type: SSEEventType;
    payload: any;
    timestamp: number;
}

export type SSEEventHandler = (data: SSEEventData) => void;
