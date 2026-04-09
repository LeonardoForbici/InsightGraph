/**
 * WaveAnimationManager
 * 
 * Manages wave animations that propagate through the dependency graph when changes occur.
 * Uses BFS to organize nodes by distance from origin and animates each level sequentially.
 * 
 * Requirements: 3.1, 3.2, 3.3
 */

export interface WaveAnimation {
  originNodeKey: string;
  affectedNodes: string[];
  startTime: number;
  maxDepth: number;
  id: string;
}

export interface AnimationConfig {
  levelDelay: number;        // Delay between levels (default: 200ms)
  nodeDuration: number;      // Duration of node animation (default: 600ms)
  waveColor: string;         // Color for wave animation (default: #60a5fa)
  scaleFrom: number;         // Starting scale (default: 1.0)
  scaleTo: number;           // Peak scale (default: 1.3)
  maxDepth: number;          // Maximum propagation depth (default: 5)
  maxNodes: number;          // Maximum nodes to animate (default: 50)
}

export interface NodeAnimationState {
  nodeKey: string;
  startTime: number;
  duration: number;
  scaleFrom: number;
  scaleTo: number;
  color: string;
  depth: number;
}

const DEFAULT_CONFIG: AnimationConfig = {
  levelDelay: 200,
  nodeDuration: 600,
  waveColor: '#60a5fa',
  scaleFrom: 1.0,
  scaleTo: 1.3,
  maxDepth: 5,
  maxNodes: 50,
};

/**
 * WaveAnimationManager
 * 
 * Manages wave animations that propagate through the graph.
 * Supports multiple concurrent waves without interference.
 */
export class WaveAnimationManager {
  private activeWaves: Map<string, WaveAnimation> = new Map();
  private config: AnimationConfig;
  private graphEdges: Map<string, string[]>; // nodeKey -> downstream neighbors
  private animationStates: Map<string, NodeAnimationState> = new Map();
  
  constructor(config: Partial<AnimationConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.graphEdges = new Map();
  }
  
  /**
   * Update the graph structure for BFS traversal
   * 
   * @param edges - Array of graph edges with source and target
   */
  updateGraphStructure(edges: Array<{ source: string; target: string }>) {
    this.graphEdges.clear();
    
    edges.forEach(edge => {
      const neighbors = this.graphEdges.get(edge.source) || [];
      neighbors.push(edge.target);
      this.graphEdges.set(edge.source, neighbors);
    });
  }
  
  /**
   * Start a wave animation from an origin node
   * 
   * @param originNodeKey - The node where the wave originates
   * @param affectedNodes - Optional list of affected nodes (if known)
   * @returns Wave animation ID
   */
  startWave(originNodeKey: string, affectedNodes?: string[]): string {
    const waveId = `wave-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    const wave: WaveAnimation = {
      originNodeKey,
      affectedNodes: affectedNodes || [],
      startTime: Date.now(),
      maxDepth: this.config.maxDepth,
      id: waveId,
    };
    
    this.activeWaves.set(waveId, wave);
    
    // Start propagation asynchronously
    this.propagateWave(wave);
    
    return waveId;
  }
  
  /**
   * Propagate wave through dependency levels using BFS
   * 
   * @param wave - Wave animation to propagate
   */
  private async propagateWave(wave: WaveAnimation): Promise<void> {
    // Build levels using BFS
    const levels = this.buildLevels(wave.originNodeKey, wave.affectedNodes);
    
    // Limit to maxDepth and maxNodes
    const limitedLevels = this.limitLevels(levels);
    
    // Animate each level sequentially
    for (let depth = 0; depth < limitedLevels.length; depth++) {
      await this.animateLevel(limitedLevels[depth], depth);
      
      // Delay before next level
      if (depth < limitedLevels.length - 1) {
        await this.delay(this.config.levelDelay);
      }
    }
    
    // Clean up completed wave
    this.activeWaves.delete(wave.id);
  }
  
  /**
   * Build levels of nodes using BFS from origin
   * 
   * @param origin - Origin node key
   * @param affectedNodes - Optional list of nodes to include
   * @returns Array of levels, each containing node keys
   */
  private buildLevels(origin: string, affectedNodes: string[]): string[][] {
    const levels: string[][] = [[origin]];
    const visited = new Set<string>([origin]);
    const queue: Array<{ node: string; depth: number }> = [{ node: origin, depth: 0 }];
    
    // If affectedNodes is provided, use it as a filter
    const affectedSet = affectedNodes.length > 0 ? new Set(affectedNodes) : null;
    
    while (queue.length > 0) {
      const { node, depth } = queue.shift()!;
      
      // Stop if we've reached max depth
      if (depth >= this.config.maxDepth) {
        continue;
      }
      
      // Get downstream neighbors
      const neighbors = this.getNeighbors(node);
      
      for (const neighbor of neighbors) {
        // Skip if already visited
        if (visited.has(neighbor)) {
          continue;
        }
        
        // Skip if not in affected nodes (when filter is active)
        if (affectedSet && !affectedSet.has(neighbor)) {
          continue;
        }
        
        visited.add(neighbor);
        
        // Add to appropriate level
        const nextDepth = depth + 1;
        if (!levels[nextDepth]) {
          levels[nextDepth] = [];
        }
        levels[nextDepth].push(neighbor);
        
        // Add to queue for further traversal
        queue.push({ node: neighbor, depth: nextDepth });
      }
    }
    
    return levels;
  }
  
  /**
   * Get downstream neighbors for a node
   * 
   * @param nodeKey - Node to get neighbors for
   * @returns Array of neighbor node keys
   */
  private getNeighbors(nodeKey: string): string[] {
    return this.graphEdges.get(nodeKey) || [];
  }
  
  /**
   * Limit levels to maxDepth and maxNodes
   * 
   * @param levels - All levels from BFS
   * @returns Limited levels
   */
  private limitLevels(levels: string[][]): string[][] {
    const limited: string[][] = [];
    let totalNodes = 0;
    
    for (let i = 0; i < Math.min(levels.length, this.config.maxDepth); i++) {
      const level = levels[i];
      const remainingCapacity = this.config.maxNodes - totalNodes;
      
      if (remainingCapacity <= 0) {
        break;
      }
      
      // Take only as many nodes as we have capacity for
      const limitedLevel = level.slice(0, remainingCapacity);
      limited.push(limitedLevel);
      totalNodes += limitedLevel.length;
    }
    
    return limited;
  }
  
  /**
   * Animate all nodes in a level
   * 
   * @param nodes - Node keys to animate
   * @param depth - Depth level for this animation
   */
  private async animateLevel(nodes: string[], depth: number): Promise<void> {
    const now = Date.now();
    
    // Create animation state for each node
    nodes.forEach(nodeKey => {
      const state: NodeAnimationState = {
        nodeKey,
        startTime: now,
        duration: this.config.nodeDuration,
        scaleFrom: this.config.scaleFrom,
        scaleTo: this.config.scaleTo,
        color: this.config.waveColor,
        depth,
      };
      
      this.animationStates.set(nodeKey, state);
    });
    
    // Wait for animation duration
    await this.delay(this.config.nodeDuration);
    
    // Clean up animation states
    nodes.forEach(nodeKey => {
      this.animationStates.delete(nodeKey);
    });
  }
  
  /**
   * Get current animation state for a node
   * 
   * @param nodeKey - Node to check
   * @returns Animation state or null if not animating
   */
  getAnimationState(nodeKey: string): NodeAnimationState | null {
    return this.animationStates.get(nodeKey) || null;
  }
  
  /**
   * Get current scale for a node based on animation progress
   * 
   * @param nodeKey - Node to check
   * @returns Current scale value
   */
  getCurrentScale(nodeKey: string): number {
    const state = this.animationStates.get(nodeKey);
    
    if (!state) {
      return 1.0;
    }
    
    const elapsed = Date.now() - state.startTime;
    const progress = Math.min(1, elapsed / state.duration);
    
    // Ease in-out animation: 1.0 -> 1.3 -> 1.0
    const eased = this.easeInOutQuad(progress);
    
    // Scale up then down
    let scale: number;
    if (progress < 0.5) {
      // First half: scale up
      const upProgress = progress * 2;
      scale = state.scaleFrom + (state.scaleTo - state.scaleFrom) * upProgress;
    } else {
      // Second half: scale down
      const downProgress = (progress - 0.5) * 2;
      scale = state.scaleTo - (state.scaleTo - state.scaleFrom) * downProgress;
    }
    
    return scale;
  }
  
  /**
   * Check if a node is currently animating
   * 
   * @param nodeKey - Node to check
   * @returns True if node is animating
   */
  isAnimating(nodeKey: string): boolean {
    return this.animationStates.has(nodeKey);
  }
  
  /**
   * Get all active wave IDs
   * 
   * @returns Array of active wave IDs
   */
  getActiveWaves(): string[] {
    return Array.from(this.activeWaves.keys());
  }
  
  /**
   * Stop a specific wave animation
   * 
   * @param waveId - Wave ID to stop
   */
  stopWave(waveId: string): void {
    this.activeWaves.delete(waveId);
  }
  
  /**
   * Stop all active waves
   */
  stopAllWaves(): void {
    this.activeWaves.clear();
    this.animationStates.clear();
  }
  
  /**
   * Ease in-out quad function for smooth animation
   * 
   * @param t - Progress [0, 1]
   * @returns Eased value [0, 1]
   */
  private easeInOutQuad(t: number): number {
    return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
  }
  
  /**
   * Delay helper for async operations
   * 
   * @param ms - Milliseconds to delay
   * @returns Promise that resolves after delay
   */
  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

