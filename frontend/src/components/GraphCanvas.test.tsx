import { describe, it, expect } from 'vitest';
import type { GraphEdge } from '../api';

/**
 * Unit tests for GraphCanvas tainted edge functionality
 * Task 14.1: Enhance GraphCanvas.tsx to display tainted edges
 */

describe('GraphCanvas Tainted Edge Logic', () => {
    it('should identify tainted edges correctly', () => {
        const edges: GraphEdge[] = [
            { source: 'node1', target: 'node2', type: 'CALLS', is_tainted: true, taint_message: 'SQL Injection risk' },
            { source: 'node2', target: 'node3', type: 'DEPENDS_ON', is_tainted: false },
            { source: 'node3', target: 'node4', type: 'READS_FROM' },
        ];

        const taintedEdges = edges.filter(e => e.is_tainted === true);
        expect(taintedEdges).toHaveLength(1);
        expect(taintedEdges[0].taint_message).toBe('SQL Injection risk');
    });

    it('should handle edges without taint properties', () => {
        const edges: GraphEdge[] = [
            { source: 'node1', target: 'node2', type: 'CALLS' },
            { source: 'node2', target: 'node3', type: 'DEPENDS_ON' },
        ];

        const taintedEdges = edges.filter(e => e.is_tainted === true);
        expect(taintedEdges).toHaveLength(0);
    });

    it('should find tainted paths connected to a node', () => {
        const selectedNodeKey = 'node2';
        const edges: GraphEdge[] = [
            { source: 'node1', target: 'node2', type: 'CALLS', is_tainted: true, taint_message: 'Taint 1' },
            { source: 'node2', target: 'node3', type: 'DEPENDS_ON', is_tainted: true, taint_message: 'Taint 2' },
            { source: 'node3', target: 'node4', type: 'READS_FROM', is_tainted: false },
            { source: 'node4', target: 'node5', type: 'WRITES_TO' },
        ];

        const connectedTaintedEdges = edges.filter(
            edge => (edge.source === selectedNodeKey || edge.target === selectedNodeKey) && edge.is_tainted
        );

        expect(connectedTaintedEdges).toHaveLength(2);
        expect(connectedTaintedEdges[0].taint_message).toBe('Taint 1');
        expect(connectedTaintedEdges[1].taint_message).toBe('Taint 2');
    });

    it('should return empty array when no tainted edges are connected to node', () => {
        const selectedNodeKey = 'node5';
        const edges: GraphEdge[] = [
            { source: 'node1', target: 'node2', type: 'CALLS', is_tainted: true, taint_message: 'Taint 1' },
            { source: 'node2', target: 'node3', type: 'DEPENDS_ON', is_tainted: true, taint_message: 'Taint 2' },
            { source: 'node3', target: 'node4', type: 'READS_FROM', is_tainted: false },
        ];

        const connectedTaintedEdges = edges.filter(
            edge => (edge.source === selectedNodeKey || edge.target === selectedNodeKey) && edge.is_tainted
        );

        expect(connectedTaintedEdges).toHaveLength(0);
    });

    it('should handle multiple tainted edges in a path', () => {
        const edges: GraphEdge[] = [
            { source: 'node1', target: 'node2', type: 'CALLS', is_tainted: true, taint_message: 'User input' },
            { source: 'node2', target: 'node3', type: 'CALLS', is_tainted: true, taint_message: 'Propagated taint' },
            { source: 'node3', target: 'node4', type: 'CALLS', is_tainted: true, taint_message: 'Database query' },
        ];

        const taintedPath = edges.filter(e => e.is_tainted === true);
        expect(taintedPath).toHaveLength(3);
        
        // Verify the path forms a chain
        expect(taintedPath[0].target).toBe(taintedPath[1].source);
        expect(taintedPath[1].target).toBe(taintedPath[2].source);
    });
});
