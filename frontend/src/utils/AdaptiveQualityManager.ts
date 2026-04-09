/**
 * AdaptiveQualityManager
 * 
 * Manages rendering quality based on graph size to maintain performance.
 * Automatically adjusts visual settings for large graphs (>1200 nodes).
 * 
 * Requirements: 12.1, 12.2, 12.3, 12.5, 12.6
 */

export interface QualitySettings {
  nodeOpacity: number;
  linkOpacity: number;
  particlesEnabled: boolean;
  cooldownTicks: number;
}

export class AdaptiveQualityManager {
  private static readonly LARGE_GRAPH_THRESHOLD = 1200;
  
  /**
   * Calculate optimal quality settings based on node count.
   * 
   * @param nodeCount - Total number of nodes in the graph
   * @returns Quality settings optimized for the given graph size
   */
  static getQualitySettings(nodeCount: number): QualitySettings {
    const isLargeGraph = nodeCount > this.LARGE_GRAPH_THRESHOLD;
    
    return {
      // Requirement 12.1: Reduce node opacity to 0.75 for graphs > 1200 nodes
      nodeOpacity: isLargeGraph ? 0.75 : 1.0,
      
      // Requirement 12.2: Reduce link opacity to 0.18 for graphs > 1200 nodes
      linkOpacity: isLargeGraph ? 0.18 : 0.4,
      
      // Requirement 12.3: Disable particles for graphs > 1200 nodes
      particlesEnabled: !isLargeGraph,
      
      // Requirement 12.5, 12.6: Adjust cooldownTicks based on node count
      // 60 for large graphs (>1200), 120 for smaller graphs
      cooldownTicks: isLargeGraph ? 60 : 120,
    };
  }
  
  /**
   * Check if the graph is considered large.
   * 
   * @param nodeCount - Total number of nodes in the graph
   * @returns True if graph exceeds the large graph threshold
   */
  static isLargeGraph(nodeCount: number): boolean {
    return nodeCount > this.LARGE_GRAPH_THRESHOLD;
  }
  
  /**
   * Get the threshold for large graph classification.
   * 
   * @returns The node count threshold (1200)
   */
  static getThreshold(): number {
    return this.LARGE_GRAPH_THRESHOLD;
  }
  
  /**
   * Calculate particle count for medium-sized graphs (500-1200 nodes).
   * For graphs > 1200 nodes, particles are disabled.
   * For graphs <= 500 nodes, full particles are enabled.
   * 
   * @param nodeCount - Total number of nodes in the graph
   * @returns Number of particles per edge (0, 1, or 2)
   */
  static getParticleCount(nodeCount: number): number {
    if (nodeCount > this.LARGE_GRAPH_THRESHOLD) {
      return 0; // Disabled for large graphs
    } else if (nodeCount > 500) {
      return 1; // Reduced for medium graphs (Requirement 12.5)
    } else {
      return 2; // Full particles for small graphs
    }
  }
}
