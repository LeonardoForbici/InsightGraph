/**
 * Lazy Node Renderer for performance optimization.
 * 
 * Only renders nodes within the camera's view frustum to improve
 * performance with large graphs (>1200 nodes).
 * 
 * Requirements:
 *   - 12.6: Lazy rendering for large graphs
 */

interface CameraPosition {
  x: number;
  y: number;
  z: number;
}

interface Node {
  id: string;
  x?: number;
  y?: number;
  z?: number;
  [key: string]: any;
}

export class LazyNodeRenderer {
  private visibleNodes: Set<string> = new Set();
  private viewDistance: number = 500;
  private lastCameraPosition: CameraPosition | null = null;
  private updateThreshold: number = 50; // Update only if camera moved > 50 units

  constructor(viewDistance: number = 500) {
    this.viewDistance = viewDistance;
  }

  /**
   * Update visible nodes based on camera position.
   * 
   * @param nodes - All graph nodes
   * @param cameraPosition - Current camera position
   * @returns Set of visible node IDs
   */
  updateVisibleNodes(nodes: Node[], cameraPosition: CameraPosition): Set<string> {
    // Check if camera moved significantly
    if (this.lastCameraPosition && !this.shouldUpdate(cameraPosition)) {
      return this.visibleNodes;
    }

    this.lastCameraPosition = { ...cameraPosition };
    this.visibleNodes.clear();

    // Calculate visible nodes based on distance from camera
    for (const node of nodes) {
      if (this.isNodeVisible(node, cameraPosition)) {
        this.visibleNodes.add(node.id);
      }
    }

    return this.visibleNodes;
  }

  /**
   * Check if camera moved enough to warrant an update.
   */
  private shouldUpdate(newPosition: CameraPosition): boolean {
    if (!this.lastCameraPosition) return true;

    const dx = newPosition.x - this.lastCameraPosition.x;
    const dy = newPosition.y - this.lastCameraPosition.y;
    const dz = newPosition.z - this.lastCameraPosition.z;
    const distance = Math.sqrt(dx * dx + dy * dy + dz * dz);

    return distance > this.updateThreshold;
  }

  /**
   * Check if a node is within view distance.
   */
  private isNodeVisible(node: Node, cameraPosition: CameraPosition): boolean {
    // If node doesn't have position, assume it's visible
    if (node.x === undefined || node.y === undefined || node.z === undefined) {
      return true;
    }

    const dx = node.x - cameraPosition.x;
    const dy = node.y - cameraPosition.y;
    const dz = node.z - cameraPosition.z;
    const distance = Math.sqrt(dx * dx + dy * dy + dz * dz);

    return distance <= this.viewDistance;
  }

  /**
   * Get current visible nodes.
   */
  getVisibleNodes(): Set<string> {
    return this.visibleNodes;
  }

  /**
   * Check if a specific node is visible.
   */
  isVisible(nodeId: string): boolean {
    return this.visibleNodes.has(nodeId);
  }

  /**
   * Set view distance.
   */
  setViewDistance(distance: number): void {
    this.viewDistance = distance;
  }

  /**
   * Reset renderer state.
   */
  reset(): void {
    this.visibleNodes.clear();
    this.lastCameraPosition = null;
  }
}
