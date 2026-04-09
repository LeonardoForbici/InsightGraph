/**
 * Visual Encoding Utilities for Code Intelligence OS
 * 
 * This module provides functions for encoding code metrics into visual properties:
 * - Color: Risk level (green/yellow/orange/red)
 * - Size: Importance (complexity + hotspot_score)
 * - Brightness: Recency of change (fades over 10 seconds)
 * - Pulse: Active impact indicator (hotspot_score > 70)
 */

export interface GraphNode {
  namespace_key: string;
  name: string;
  labels?: string[];
  file?: string;
  complexity?: number;
  hotspot_score?: number;
  risk_score?: number;
  loc?: number;
  last_modified?: number;
  change_frequency?: number;
  first_seen?: number;
}

/**
 * Calculate risk score from node metrics
 * Risk is a composite of complexity, hotspot score, and change frequency
 */
const calculateRisk = (node: GraphNode): number => {
  const complexity = node.complexity ?? 0;
  const hotspot = node.hotspot_score ?? 0;
  const changeFreq = node.change_frequency ?? 0;
  
  // Weighted risk calculation
  const complexityWeight = 0.4;
  const hotspotWeight = 0.4;
  const changeWeight = 0.2;
  
  const normalizedComplexity = Math.min(100, complexity * 5);
  const normalizedHotspot = Math.min(100, hotspot);
  const normalizedChange = Math.min(100, changeFreq * 10);
  
  return (
    normalizedComplexity * complexityWeight +
    normalizedHotspot * hotspotWeight +
    normalizedChange * changeWeight
  );
};

/**
 * Map risk score to color
 * 
 * Color encoding:
 * - Green (#22c55e): Low risk (< 40)
 * - Yellow (#eab308): Medium risk (40-59)
 * - Orange (#f97316): High risk (60-79)
 * - Red (#ef4444): Critical risk (>= 80)
 * 
 * @param node - Graph node with risk metrics
 * @returns Hex color string
 */
export const getRiskColor = (node: GraphNode): string => {
  const risk = node.risk_score ?? calculateRisk(node);
  
  if (risk >= 80) return '#ef4444'; // red - critical
  if (risk >= 60) return '#f97316'; // orange - high
  if (risk >= 40) return '#eab308'; // yellow - medium
  return '#22c55e'; // green - low
};

/**
 * Calculate node size from complexity and hotspot score
 * 
 * Size encoding represents importance:
 * - Base size from complexity (2-20)
 * - Boost from hotspot score (0-12)
 * - Clamped to range [6, 28]
 * 
 * @param node - Graph node with complexity and hotspot metrics
 * @returns Node size value
 */
export const getNodeSize = (node: GraphNode): number => {
  const complexity = node.complexity ?? 2;
  const hotspotScore = node.hotspot_score ?? 0;
  
  // Base size from complexity
  const complexityBase = complexity + 4;
  
  // Additional boost from hotspot score
  const hotspotBoost = Math.min(12, hotspotScore / 6);
  
  // Clamp to reasonable range
  return Math.max(6, Math.min(28, complexityBase + hotspotBoost));
};

/**
 * Calculate brightness multiplier for recently changed nodes
 * 
 * Brightness fades linearly over 10 seconds after change:
 * - 1.0 at time of change (100% brightness boost)
 * - 0.0 after 10 seconds (no boost)
 * 
 * @param nodeKey - Node identifier
 * @param recentChanges - Map of node keys to change timestamps
 * @returns Brightness multiplier [0.0, 1.0]
 */
export const getBrightness = (
  nodeKey: string,
  recentChanges: Map<string, number>
): number => {
  const changeTime = recentChanges.get(nodeKey);
  
  if (!changeTime) {
    return 0;
  }
  
  const elapsed = Date.now() - changeTime;
  const fadeTime = 10000; // 10 seconds
  
  // Linear fade from 1.0 to 0.0
  return Math.max(0, 1 - elapsed / fadeTime);
};

/**
 * Determine if node should have pulse animation
 * 
 * Pulse animation indicates active impact or high activity:
 * - Enabled when hotspot_score > 70
 * 
 * @param node - Graph node with hotspot score
 * @returns True if node should pulse
 */
export const shouldPulse = (node: GraphNode): boolean => {
  return (node.hotspot_score ?? 0) > 70;
};

/**
 * Get severity level from affected node count
 * Used for impact notifications
 * 
 * @param affectedCount - Number of affected nodes
 * @returns Severity level
 */
export const getSeverity = (affectedCount: number): 'low' | 'medium' | 'high' => {
  if (affectedCount >= 30) return 'high';
  if (affectedCount >= 10) return 'medium';
  return 'low';
};

/**
 * Apply brightness boost to a color
 * 
 * @param color - Base hex color
 * @param brightness - Brightness multiplier [0.0, 1.0]
 * @returns Modified hex color with brightness applied
 */
export const applyBrightness = (color: string, brightness: number): string => {
  if (brightness === 0) return color;
  
  // Parse hex color
  const hex = color.replace('#', '');
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  
  // Apply brightness boost (lighten towards white)
  const boost = brightness * 0.5; // Max 50% boost
  const newR = Math.min(255, Math.round(r + (255 - r) * boost));
  const newG = Math.min(255, Math.round(g + (255 - g) * boost));
  const newB = Math.min(255, Math.round(b + (255 - b) * boost));
  
  // Convert back to hex
  return `#${newR.toString(16).padStart(2, '0')}${newG.toString(16).padStart(2, '0')}${newB.toString(16).padStart(2, '0')}`;
};

/**
 * Get complete visual encoding for a node
 * 
 * @param node - Graph node
 * @param recentChanges - Map of recent changes
 * @returns Complete visual encoding
 */
export interface VisualEncoding {
  color: string;
  size: number;
  brightness: number;
  pulse: boolean;
}

export const getVisualEncoding = (
  node: GraphNode,
  recentChanges: Map<string, number>
): VisualEncoding => {
  const baseColor = getRiskColor(node);
  const brightness = getBrightness(node.namespace_key, recentChanges);
  
  return {
    color: applyBrightness(baseColor, brightness),
    size: getNodeSize(node),
    brightness,
    pulse: shouldPulse(node)
  };
};
