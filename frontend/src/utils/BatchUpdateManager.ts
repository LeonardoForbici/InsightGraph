/**
 * Batch Update Manager for performance optimization.
 * 
 * Queues node updates and flushes them in a single render pass
 * using requestAnimationFrame for smooth updates.
 * 
 * Requirements:
 *   - 10.1, 10.2, 10.3, 10.4: Batch updates for performance
 */

interface NodeUpdate {
  nodeId: string;
  properties: Record<string, any>;
  timestamp: number;
}

type UpdateCallback = (updates: NodeUpdate[]) => void;

export class BatchUpdateManager {
  private updateQueue: Map<string, NodeUpdate> = new Map();
  private flushInterval: number = 100; // 100ms
  private flushTimer: NodeJS.Timeout | null = null;
  private rafId: number | null = null;
  private callback: UpdateCallback | null = null;
  private isProcessing: boolean = false;

  constructor(callback?: UpdateCallback, flushInterval: number = 100) {
    this.callback = callback || null;
    this.flushInterval = flushInterval;
  }

  /**
   * Queue a node update.
   * Updates are batched and flushed periodically.
   * 
   * @param nodeId - Node identifier
   * @param properties - Properties to update
   */
  queueUpdate(nodeId: string, properties: Record<string, any>): void {
    const existingUpdate = this.updateQueue.get(nodeId);

    if (existingUpdate) {
      // Merge with existing update
      existingUpdate.properties = {
        ...existingUpdate.properties,
        ...properties
      };
      existingUpdate.timestamp = Date.now();
    } else {
      // Add new update
      this.updateQueue.set(nodeId, {
        nodeId,
        properties,
        timestamp: Date.now()
      });
    }

    // Schedule flush if not already scheduled
    this.scheduleFlush();
  }

  /**
   * Queue multiple updates at once.
   */
  queueBatch(updates: Array<{ nodeId: string; properties: Record<string, any> }>): void {
    for (const update of updates) {
      this.queueUpdate(update.nodeId, update.properties);
    }
  }

  /**
   * Schedule a flush using requestAnimationFrame.
   */
  private scheduleFlush(): void {
    if (this.flushTimer || this.isProcessing) {
      return;
    }

    this.flushTimer = setTimeout(() => {
      this.flushTimer = null;
      this.flush();
    }, this.flushInterval);
  }

  /**
   * Flush all queued updates in a single render pass.
   */
  flush(): void {
    if (this.updateQueue.size === 0 || this.isProcessing) {
      return;
    }

    this.isProcessing = true;

    // Use requestAnimationFrame for smooth updates
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
    }

    this.rafId = requestAnimationFrame(() => {
      const updates = Array.from(this.updateQueue.values());
      this.updateQueue.clear();

      // Execute callback with batched updates
      if (this.callback) {
        this.callback(updates);
      }

      this.isProcessing = false;
      this.rafId = null;

      // If new updates arrived during processing, schedule another flush
      if (this.updateQueue.size > 0) {
        this.scheduleFlush();
      }
    });
  }

  /**
   * Force immediate flush without waiting for timer.
   */
  flushImmediate(): void {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
    this.flush();
  }

  /**
   * Set the callback function for processing updates.
   */
  setCallback(callback: UpdateCallback): void {
    this.callback = callback;
  }

  /**
   * Get the number of queued updates.
   */
  getQueueSize(): number {
    return this.updateQueue.size;
  }

  /**
   * Check if updates are currently being processed.
   */
  isProcessingUpdates(): boolean {
    return this.isProcessing;
  }

  /**
   * Clear all queued updates without processing.
   */
  clear(): void {
    this.updateQueue.clear();
    
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }

    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }

    this.isProcessing = false;
  }

  /**
   * Destroy the batch update manager and clean up resources.
   */
  destroy(): void {
    this.clear();
    this.callback = null;
  }
}
