/**
 * Memory Manager for preventing memory leaks.
 * 
 * Tracks subscriptions, intervals, event listeners, and other resources
 * to ensure proper cleanup.
 * 
 * Requirements:
 *   - 12.6: Memory leak prevention
 */

type CleanupFunction = () => void;

export class MemoryManager {
  private subscriptions: Set<CleanupFunction> = new Set();
  private intervals: Set<NodeJS.Timeout> = new Set();
  private timeouts: Set<NodeJS.Timeout> = new Set();
  private eventListeners: Array<{
    target: EventTarget;
    event: string;
    handler: EventListener;
    options?: boolean | AddEventListenerOptions;
  }> = [];
  private rafIds: Set<number> = new Set();

  /**
   * Track a subscription for cleanup.
   * 
   * @param cleanup - Cleanup function to call on destroy
   */
  addSubscription(cleanup: CleanupFunction): void {
    this.subscriptions.add(cleanup);
  }

  /**
   * Track an interval for cleanup.
   * 
   * @param intervalId - Interval ID from setInterval
   */
  addInterval(intervalId: NodeJS.Timeout): void {
    this.intervals.add(intervalId);
  }

  /**
   * Track a timeout for cleanup.
   * 
   * @param timeoutId - Timeout ID from setTimeout
   */
  addTimeout(timeoutId: NodeJS.Timeout): void {
    this.timeouts.add(timeoutId);
  }

  /**
   * Track an event listener for cleanup.
   * 
   * @param target - Event target
   * @param event - Event name
   * @param handler - Event handler
   * @param options - Event listener options
   */
  addEventListener(
    target: EventTarget,
    event: string,
    handler: EventListener,
    options?: boolean | AddEventListenerOptions
  ): void {
    target.addEventListener(event, handler, options);
    this.eventListeners.push({ target, event, handler, options });
  }

  /**
   * Track a requestAnimationFrame for cleanup.
   * 
   * @param rafId - RAF ID from requestAnimationFrame
   */
  addRAF(rafId: number): void {
    this.rafIds.add(rafId);
  }

  /**
   * Remove a specific subscription.
   */
  removeSubscription(cleanup: CleanupFunction): void {
    this.subscriptions.delete(cleanup);
  }

  /**
   * Remove a specific interval.
   */
  removeInterval(intervalId: NodeJS.Timeout): void {
    if (this.intervals.has(intervalId)) {
      clearInterval(intervalId);
      this.intervals.delete(intervalId);
    }
  }

  /**
   * Remove a specific timeout.
   */
  removeTimeout(timeoutId: NodeJS.Timeout): void {
    if (this.timeouts.has(timeoutId)) {
      clearTimeout(timeoutId);
      this.timeouts.delete(timeoutId);
    }
  }

  /**
   * Remove a specific event listener.
   */
  removeEventListener(target: EventTarget, event: string, handler: EventListener): void {
    const index = this.eventListeners.findIndex(
      listener => listener.target === target && 
                  listener.event === event && 
                  listener.handler === handler
    );

    if (index !== -1) {
      const listener = this.eventListeners[index];
      target.removeEventListener(event, handler, listener.options);
      this.eventListeners.splice(index, 1);
    }
  }

  /**
   * Remove a specific RAF.
   */
  removeRAF(rafId: number): void {
    if (this.rafIds.has(rafId)) {
      cancelAnimationFrame(rafId);
      this.rafIds.delete(rafId);
    }
  }

  /**
   * Clean up all tracked resources.
   * Call this in useEffect cleanup or component unmount.
   */
  cleanup(): void {
    // Clean up subscriptions
    this.subscriptions.forEach(cleanup => {
      try {
        cleanup();
      } catch (error) {
        console.error('Error during subscription cleanup:', error);
      }
    });
    this.subscriptions.clear();

    // Clear intervals
    this.intervals.forEach(intervalId => clearInterval(intervalId));
    this.intervals.clear();

    // Clear timeouts
    this.timeouts.forEach(timeoutId => clearTimeout(timeoutId));
    this.timeouts.clear();

    // Remove event listeners
    this.eventListeners.forEach(({ target, event, handler, options }) => {
      try {
        target.removeEventListener(event, handler, options);
      } catch (error) {
        console.error('Error removing event listener:', error);
      }
    });
    this.eventListeners = [];

    // Cancel RAF
    this.rafIds.forEach(rafId => cancelAnimationFrame(rafId));
    this.rafIds.clear();
  }

  /**
   * Get statistics about tracked resources.
   */
  getStats(): {
    subscriptions: number;
    intervals: number;
    timeouts: number;
    eventListeners: number;
    rafs: number;
  } {
    return {
      subscriptions: this.subscriptions.size,
      intervals: this.intervals.size,
      timeouts: this.timeouts.size,
      eventListeners: this.eventListeners.length,
      rafs: this.rafIds.size
    };
  }

  /**
   * Check if there are any tracked resources.
   */
  hasResources(): boolean {
    return (
      this.subscriptions.size > 0 ||
      this.intervals.size > 0 ||
      this.timeouts.size > 0 ||
      this.eventListeners.length > 0 ||
      this.rafIds.size > 0
    );
  }
}

/**
 * React hook for using MemoryManager.
 * Automatically cleans up on unmount.
 */
export function useMemoryManager(): MemoryManager {
  const managerRef = React.useRef<MemoryManager | null>(null);

  if (!managerRef.current) {
    managerRef.current = new MemoryManager();
  }

  React.useEffect(() => {
    return () => {
      managerRef.current?.cleanup();
    };
  }, []);

  return managerRef.current;
}

// For non-React usage
import React from 'react';
