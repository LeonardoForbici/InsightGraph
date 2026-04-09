/**
 * Event Processor with debouncing and throttling utilities.
 * 
 * Provides performance optimization through event rate limiting:
 * - Debounce: Delays execution until events stop
 * - Throttle: Limits execution frequency
 * 
 * Requirements:
 *   - 10.1, 10.2, 10.3, 10.4: Event optimization
 */

type EventHandler = (...args: any[]) => void;

export class EventProcessor {
  private debounceTimers: Map<string, NodeJS.Timeout> = new Map();
  private throttleTimers: Map<string, NodeJS.Timeout> = new Map();
  private throttleLastCall: Map<string, number> = new Map();

  /**
   * Debounce a function call.
   * Delays execution until the specified delay has passed without new calls.
   * 
   * @param key - Unique identifier for this debounced function
   * @param fn - Function to debounce
   * @param delay - Delay in milliseconds
   */
  debounce(key: string, fn: EventHandler, delay: number): EventHandler {
    return (...args: any[]) => {
      // Clear existing timer
      const existingTimer = this.debounceTimers.get(key);
      if (existingTimer) {
        clearTimeout(existingTimer);
      }

      // Set new timer
      const timer = setTimeout(() => {
        fn(...args);
        this.debounceTimers.delete(key);
      }, delay);

      this.debounceTimers.set(key, timer);
    };
  }

  /**
   * Throttle a function call.
   * Limits execution to once per specified interval.
   * 
   * @param key - Unique identifier for this throttled function
   * @param fn - Function to throttle
   * @param interval - Minimum interval between calls in milliseconds
   */
  throttle(key: string, fn: EventHandler, interval: number): EventHandler {
    return (...args: any[]) => {
      const now = Date.now();
      const lastCall = this.throttleLastCall.get(key) || 0;
      const timeSinceLastCall = now - lastCall;

      if (timeSinceLastCall >= interval) {
        // Execute immediately
        fn(...args);
        this.throttleLastCall.set(key, now);
      } else {
        // Schedule for later if not already scheduled
        if (!this.throttleTimers.has(key)) {
          const remainingTime = interval - timeSinceLastCall;
          const timer = setTimeout(() => {
            fn(...args);
            this.throttleLastCall.set(key, Date.now());
            this.throttleTimers.delete(key);
          }, remainingTime);

          this.throttleTimers.set(key, timer);
        }
      }
    };
  }

  /**
   * Create a debounced graph update handler.
   * Debounces graph updates to 500ms.
   */
  createDebouncedGraphUpdate(handler: EventHandler): EventHandler {
    return this.debounce('graph-update', handler, 500);
  }

  /**
   * Create a throttled impact calculation handler.
   * Throttles impact calculations to 1000ms.
   */
  createThrottledImpactCalculation(handler: EventHandler): EventHandler {
    return this.throttle('impact-calculation', handler, 1000);
  }

  /**
   * Create a throttled camera movement handler.
   * Throttles camera movements to 100ms.
   */
  createThrottledCameraMovement(handler: EventHandler): EventHandler {
    return this.throttle('camera-movement', handler, 100);
  }

  /**
   * Cancel all pending debounced/throttled calls.
   */
  cancelAll(): void {
    // Clear debounce timers
    this.debounceTimers.forEach(timer => clearTimeout(timer));
    this.debounceTimers.clear();

    // Clear throttle timers
    this.throttleTimers.forEach(timer => clearTimeout(timer));
    this.throttleTimers.clear();
    this.throttleLastCall.clear();
  }

  /**
   * Cancel a specific debounced/throttled call.
   */
  cancel(key: string): void {
    const debounceTimer = this.debounceTimers.get(key);
    if (debounceTimer) {
      clearTimeout(debounceTimer);
      this.debounceTimers.delete(key);
    }

    const throttleTimer = this.throttleTimers.get(key);
    if (throttleTimer) {
      clearTimeout(throttleTimer);
      this.throttleTimers.delete(key);
      this.throttleLastCall.delete(key);
    }
  }
}

// Singleton instance for global use
export const eventProcessor = new EventProcessor();
