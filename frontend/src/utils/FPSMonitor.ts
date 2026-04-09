/**
 * FPSMonitor - Tracks frame rate and detects performance degradation
 * 
 * Monitors rendering performance over a rolling window of frames and
 * automatically triggers quality reduction when FPS drops below threshold.
 * 
 * Requirements: 10.6, 12.6
 */

export interface FPSMetrics {
  currentFPS: number;
  averageFPS: number;
  minFPS: number;
  maxFPS: number;
  frameCount: number;
  isDegraded: boolean;
}

export interface QualitySettings {
  nodeOpacity: number;
  linkOpacity: number;
  particlesEnabled: boolean;
  animationQuality: 'high' | 'medium' | 'low';
}

export class FPSMonitor {
  private frameTimes: number[] = [];
  private lastFrameTime: number = 0;
  private frameCount: number = 0;
  private readonly maxFrames: number = 60;
  private readonly degradationThreshold: number = 30;
  private isDegraded: boolean = false;
  private isRunning: boolean = false;
  private animationFrameId: number | null = null;
  
  private onQualityChange?: (settings: QualitySettings) => void;

  constructor(onQualityChange?: (settings: QualitySettings) => void) {
    this.onQualityChange = onQualityChange;
  }

  /**
   * Start monitoring frame rate
   */
  start(): void {
    if (this.isRunning) return;
    
    this.isRunning = true;
    this.lastFrameTime = performance.now();
    this.tick();
  }

  /**
   * Stop monitoring frame rate
   */
  stop(): void {
    this.isRunning = false;
    if (this.animationFrameId !== null) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }
  }

  /**
   * Reset all metrics
   */
  reset(): void {
    this.frameTimes = [];
    this.frameCount = 0;
    this.isDegraded = false;
    this.lastFrameTime = performance.now();
  }

  /**
   * Get current FPS metrics
   */
  getMetrics(): FPSMetrics {
    const currentFPS = this.calculateCurrentFPS();
    const averageFPS = this.calculateAverageFPS();
    const minFPS = this.frameTimes.length > 0 ? Math.min(...this.frameTimes.map(t => 1000 / t)) : 0;
    const maxFPS = this.frameTimes.length > 0 ? Math.max(...this.frameTimes.map(t => 1000 / t)) : 0;

    return {
      currentFPS,
      averageFPS,
      minFPS,
      maxFPS,
      frameCount: this.frameCount,
      isDegraded: this.isDegraded
    };
  }

  /**
   * Main tick function called on each animation frame
   */
  private tick = (): void => {
    if (!this.isRunning) return;

    const now = performance.now();
    const deltaTime = now - this.lastFrameTime;
    
    // Record frame time
    this.frameTimes.push(deltaTime);
    this.frameCount++;
    
    // Keep only last 60 frames
    if (this.frameTimes.length > this.maxFrames) {
      this.frameTimes.shift();
    }
    
    // Check for performance degradation after we have enough samples
    if (this.frameTimes.length >= 30) {
      this.checkPerformance();
    }
    
    this.lastFrameTime = now;
    this.animationFrameId = requestAnimationFrame(this.tick);
  };

  /**
   * Calculate current instantaneous FPS
   */
  private calculateCurrentFPS(): number {
    if (this.frameTimes.length === 0) return 0;
    
    const lastFrameTime = this.frameTimes[this.frameTimes.length - 1];
    return lastFrameTime > 0 ? Math.round(1000 / lastFrameTime) : 0;
  }

  /**
   * Calculate average FPS over the rolling window
   */
  private calculateAverageFPS(): number {
    if (this.frameTimes.length === 0) return 0;
    
    const totalTime = this.frameTimes.reduce((sum, time) => sum + time, 0);
    const avgFrameTime = totalTime / this.frameTimes.length;
    
    return avgFrameTime > 0 ? Math.round(1000 / avgFrameTime) : 0;
  }

  /**
   * Check for performance degradation and adjust quality if needed
   */
  private checkPerformance(): void {
    const averageFPS = this.calculateAverageFPS();
    
    // Detect degradation
    if (averageFPS < this.degradationThreshold && !this.isDegraded) {
      this.isDegraded = true;
      this.reduceQuality();
    }
    
    // Detect recovery (with hysteresis to avoid oscillation)
    if (averageFPS > this.degradationThreshold + 10 && this.isDegraded) {
      this.isDegraded = false;
      this.restoreQuality();
    }
  }

  /**
   * Reduce animation quality when FPS drops
   */
  private reduceQuality(): void {
    const lowQualitySettings: QualitySettings = {
      nodeOpacity: 0.6,
      linkOpacity: 0.12,
      particlesEnabled: false,
      animationQuality: 'low'
    };
    
    if (this.onQualityChange) {
      this.onQualityChange(lowQualitySettings);
    }
    
    console.warn(`FPS degradation detected (${this.calculateAverageFPS()} FPS). Reducing quality.`);
  }

  /**
   * Restore animation quality when FPS recovers
   */
  private restoreQuality(): void {
    const highQualitySettings: QualitySettings = {
      nodeOpacity: 1.0,
      linkOpacity: 0.25,
      particlesEnabled: true,
      animationQuality: 'high'
    };
    
    if (this.onQualityChange) {
      this.onQualityChange(highQualitySettings);
    }
    
    console.info(`FPS recovered (${this.calculateAverageFPS()} FPS). Restoring quality.`);
  }

  /**
   * Manually trigger quality reduction (for testing or external control)
   */
  forceReduceQuality(): void {
    this.isDegraded = true;
    this.reduceQuality();
  }

  /**
   * Manually trigger quality restoration (for testing or external control)
   */
  forceRestoreQuality(): void {
    this.isDegraded = false;
    this.restoreQuality();
  }

  /**
   * Check if performance is currently degraded
   */
  isPerformanceDegraded(): boolean {
    return this.isDegraded;
  }

  /**
   * Get a formatted string of current metrics for debugging
   */
  getDebugInfo(): string {
    const metrics = this.getMetrics();
    return `FPS: ${metrics.currentFPS} (avg: ${metrics.averageFPS}, min: ${metrics.minFPS.toFixed(1)}, max: ${metrics.maxFPS.toFixed(1)}) | Frames: ${metrics.frameCount} | Degraded: ${metrics.isDegraded}`;
  }
}

/**
 * Create a singleton FPS monitor instance
 */
let globalFPSMonitor: FPSMonitor | null = null;

export function createFPSMonitor(onQualityChange?: (settings: QualitySettings) => void): FPSMonitor {
  if (globalFPSMonitor) {
    globalFPSMonitor.stop();
  }
  
  globalFPSMonitor = new FPSMonitor(onQualityChange);
  return globalFPSMonitor;
}

export function getGlobalFPSMonitor(): FPSMonitor | null {
  return globalFPSMonitor;
}
