import { useMemo } from 'react';
import type { Node } from '@xyflow/react';
import type { Viewport } from '@xyflow/system';

export interface ViewportSize {
  width: number;
  height: number;
}

export interface VirtualizedNodesResult<T extends Node> {
  nodes: T[];
  visibleIds: Set<string>;
}

const DEFAULT_VIEWPORT_SIZE = { width: 1440, height: 900 };

export function useVirtualizedNodes<T extends Node>(
  nodes: T[],
  viewport: Viewport,
  viewportSize: ViewportSize,
  limit = 1000
): VirtualizedNodesResult<T> {
  return useMemo(() => {
    if (!nodes?.length) {
      return { nodes: [], visibleIds: new Set() };
    }

    const zoom = Math.max(viewport.zoom || 1, 0.1);
    const centerX = viewport.x ?? 0;
    const centerY = viewport.y ?? 0;
    const width = viewportSize.width || DEFAULT_VIEWPORT_SIZE.width;
    const height = viewportSize.height || DEFAULT_VIEWPORT_SIZE.height;

    const halfWidth = width / zoom / 2;
    const halfHeight = height / zoom / 2;

    const bounds = {
      left: centerX - halfWidth,
      right: centerX + halfWidth,
      top: centerY - halfHeight,
      bottom: centerY + halfHeight,
    };

    const inView: T[] = [];
    const outOfView: T[] = [];

    for (const node of nodes) {
      const position = node.position ?? { x: 0, y: 0 };
      const x = position.x ?? 0;
      const y = position.y ?? 0;
      const isVisible = x >= bounds.left && x <= bounds.right && y >= bounds.top && y <= bounds.bottom;

      if (isVisible) {
        inView.push(node);
      } else {
        outOfView.push(node);
      }
    }

    const selectedNodes =
      inView.length >= limit
        ? inView.slice(0, limit)
        : [...inView, ...outOfView.slice(0, Math.max(limit - inView.length, 0))];

    const visibleIds = new Set(selectedNodes.map((node) => node.id));
    return { nodes: selectedNodes, visibleIds };
  }, [
    nodes,
    viewport.x,
    viewport.y,
    viewport.zoom,
    viewportSize.width,
    viewportSize.height,
    limit,
  ]);
}
