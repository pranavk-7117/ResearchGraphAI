/**
 * Pure helper for greedy priority label placement with collision avoidance.
 */

export function boxesOverlap(a, b) {
  return a.minX < b.maxX && a.maxX > b.minX && a.minY < b.maxY && a.maxY > b.minY;
}

export function circleIntersectsBox(cx, cy, r, box) {
  const closestX = Math.max(box.minX, Math.min(cx, box.maxX));
  const closestY = Math.max(box.minY, Math.min(cy, box.maxY));
  const dx = cx - closestX;
  const dy = cy - closestY;
  return dx * dx + dy * dy < r * r;
}

/**
 * Greedy priority label placement.
 *
 * @param {Object} options
 * @param {Array<{id: number, x?: number, y?: number, title: string, radius: number}>} options.nodes
 * @param {number[]} options.candidateIds
 * @param {number|null} [options.selectedId]
 * @param {number|null} [options.hoveredId]
 * @param {number} [options.maxLabels]
 * @param {number} [options.fontSize]
 * @param {Function} [options.measureWidth]
 * @returns {Map<number, {nodeId: number, text: string, x: number, y: number, position: "below"|"above", bbox: Object}>}
 */
export function placeLabels(options) {
  const {
    nodes,
    candidateIds = [],
    selectedId = null,
    hoveredId = null,
    maxLabels = 8,
    fontSize = 10,
    measureWidth = (text) => text.length * (fontSize * 0.58),
  } = options;

  const nodeMap = new Map();
  for (const n of nodes) {
    if (typeof n.x === "number" && typeof n.y === "number") {
      nodeMap.set(n.id, n);
    }
  }

  // Priority order:
  // 1. selectedId
  // 2. hoveredId
  // 3. candidates in order (search match, ego, top citation)
  const priorityOrder = [];
  const seen = new Set();

  if (selectedId !== null && selectedId !== undefined && nodeMap.has(selectedId)) {
    priorityOrder.push(selectedId);
    seen.add(selectedId);
  }
  if (hoveredId !== null && hoveredId !== undefined && nodeMap.has(hoveredId) && !seen.has(hoveredId)) {
    priorityOrder.push(hoveredId);
    seen.add(hoveredId);
  }
  for (const id of candidateIds) {
    if (nodeMap.has(id) && !seen.has(id)) {
      priorityOrder.push(id);
      seen.add(id);
    }
  }

  const placed = new Map();
  const placedBoxes = [];
  const textHeight = fontSize + 2;

  // Obstacle nodes with significant radius (>= 8px)
  const obstacleNodes = nodes.filter(
    (n) => typeof n.x === "number" && typeof n.y === "number" && (n.radius || 0) >= 8
  );

  for (const id of priorityOrder) {
    if (placed.size >= maxLabels && id !== selectedId && id !== hoveredId) {
      break;
    }

    const node = nodeMap.get(id);
    if (!node || node.x === undefined || node.y === undefined) continue;

    const isMustPlace = id === selectedId || id === hoveredId;
    const rawText = node.title || "";
    const maxChars = isMustPlace ? 34 : 24;
    const text = rawText.length > maxChars ? `${rawText.slice(0, maxChars - 2)}...` : rawText;
    const width = measureWidth(text);
    const halfW = width / 2;
    const r = node.radius || 8;

    // Try Position 1: Below node
    const belowBox = {
      minX: node.x - halfW - 2,
      maxX: node.x + halfW + 2,
      minY: node.y + r + 2,
      maxY: node.y + r + 2 + textHeight,
    };

    let belowCollides = false;
    for (const b of placedBoxes) {
      if (boxesOverlap(belowBox, b)) {
        belowCollides = true;
        break;
      }
    }
    if (!belowCollides) {
      for (const obs of obstacleNodes) {
        if (obs.id === node.id) continue;
        if (circleIntersectsBox(obs.x, obs.y, (obs.radius || 8) + 2, belowBox)) {
          belowCollides = true;
          break;
        }
      }
    }

    if (!belowCollides) {
      placed.set(id, {
        nodeId: id,
        text,
        x: node.x,
        y: node.y + r + 4,
        position: "below",
        bbox: belowBox,
      });
      placedBoxes.push(belowBox);
      continue;
    }

    // Try Position 2: Above node
    const aboveBox = {
      minX: node.x - halfW - 2,
      maxX: node.x + halfW + 2,
      minY: node.y - r - 2 - textHeight,
      maxY: node.y - r - 2,
    };

    let aboveCollides = false;
    for (const b of placedBoxes) {
      if (boxesOverlap(aboveBox, b)) {
        aboveCollides = true;
        break;
      }
    }
    if (!aboveCollides) {
      for (const obs of obstacleNodes) {
        if (obs.id === node.id) continue;
        if (circleIntersectsBox(obs.x, obs.y, (obs.radius || 8) + 2, aboveBox)) {
          aboveCollides = true;
          break;
        }
      }
    }

    if (!aboveCollides) {
      placed.set(id, {
        nodeId: id,
        text,
        x: node.x,
        y: node.y - r - 4,
        position: "above",
        bbox: aboveBox,
      });
      placedBoxes.push(aboveBox);
      continue;
    }

    // Both positions collide: if must-place (e.g. selected node), place anyway
    if (isMustPlace) {
      placed.set(id, {
        nodeId: id,
        text,
        x: node.x,
        y: node.y + r + 4,
        position: "below",
        bbox: belowBox,
      });
      placedBoxes.push(belowBox);
    }
  }

  return placed;
}
