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

export function getLinkArrowLength(link) {
  return link.relation_type === "cites" || link.layer === "citation" ? 6 : 0;
}

export function computeTop8NodeIds(nodes) {
  return new Set(
    [...nodes]
      .sort((a, b) => (b.citation_count || 0) - (a.citation_count || 0))
      .slice(0, 8)
      .map((n) => n.id)
  );
}

export function computeEgoNeighborIds(selectedId, links) {
  if (!selectedId) return new Set();
  const ids = new Set();
  links.forEach((l) => {
    const s = typeof l.source === "object" ? l.source.id : l.source;
    const t = typeof l.target === "object" ? l.target.id : l.target;
    if (s === selectedId) ids.add(t);
    if (t === selectedId) ids.add(s);
  });
  return ids;
}

export function isPageRankUninformative(nodes) {
  if (nodes.length < 2) return false;
  const prs = nodes.map((n) => n.pagerank || 0);
  const minPr = Math.min(...prs);
  const maxPr = Math.max(...prs);
  return maxPr - minPr < 1e-4;
}

export function calculateMinEdgeWeightCutoff(nodes, edges, maxRatio = 3) {
  if (nodes.length === 0 || edges.length <= maxRatio * nodes.length) {
    return 0.0;
  }
  const simEdges = edges
    .filter((e) => {
      const l = e.layer || (e.relation_type === "cites" ? "citation" : e.relation_type === "coupling" ? "coupling" : "semantic");
      return l === "semantic";
    })
    .map((e) => e.score || 0.0)
    .sort((a, b) => b - a);
  const maxNonCitation = Math.max(0, maxRatio * nodes.length - edges.filter((e) => e.relation_type === "cites").length);
  if (simEdges.length > maxNonCitation && maxNonCitation > 0) {
    const threshold = simEdges[maxNonCitation - 1];
    return Math.min(0.85, Math.max(0.35, Math.round(threshold * 20) / 20));
  }
  return 0.50;
}

export function getNodeVal(node, nodeSizeMode = "citations") {
  if (nodeSizeMode === "citations") {
    return Math.max(5, Math.min(16, 5 + Math.log2((node.citation_count || 0) + 1) * 1.6));
  } else if (nodeSizeMode === "pagerank") {
    return Math.max(5, Math.min(16, 5 + (node.pagerank || 0) * 80));
  }
  return 7;
}

export function pickDefaultLayout(nodeCount) {
  return nodeCount <= 60 ? "radial" : "force";
}

export function computeBeeswarmY(idxInGroup, baseCenterY, r) {
  if (idxInGroup === 0) return baseCenterY;
  const sign = idxInGroup % 2 === 1 ? 1 : -1;
  const step = Math.ceil(idxInGroup / 2);
  return baseCenterY + sign * step * (2 * r + 5);
}

export function filterGraphData(options) {
  const {
    baseNodes,
    edges,
    selectedClusterId = null,
    searchQuery = "",
    enabledLayers = { citation: true, coupling: true, semantic: true },
    minEdgeWeight = 0.0,
    egoHops = "all",
    selectedNodeId = null,
  } = options;

  let nodes = baseNodes;
  if (selectedClusterId !== null) {
    nodes = nodes.filter((n) => n.cluster_id === selectedClusterId);
  }
  if (searchQuery.trim()) {
    const q = searchQuery.toLowerCase();
    nodes = nodes.filter(
      (n) => (n.title || "").toLowerCase().includes(q) || (n.authors_str || "").toLowerCase().includes(q)
    );
  }

  const activeEdges = edges.filter((e) => {
    const layer = e.layer || (e.relation_type === "cites" ? "citation" : e.relation_type === "coupling" ? "coupling" : "semantic");
    if (layer === "citation" && !enabledLayers.citation) return false;
    if (layer === "coupling" && !enabledLayers.coupling) return false;
    if (layer === "semantic" && !enabledLayers.semantic) return false;
    if (layer === "semantic" && (e.score || 0) < minEdgeWeight) return false;
    return true;
  });

  let nodeIds = new Set(nodes.map((n) => n.id));
  if (egoHops !== "all" && selectedNodeId && nodeIds.has(selectedNodeId)) {
    const maxHops = egoHops === "1" ? 1 : 2;
    const egoIds = new Set([selectedNodeId]);
    let frontier = new Set([selectedNodeId]);
    for (let h = 0; h < maxHops; h++) {
      const nextFrontier = new Set();
      activeEdges.forEach((e) => {
        const s = typeof e.source === "object" ? e.source.id : e.source;
        const t = typeof e.target === "object" ? e.target.id : e.target;
        if (frontier.has(s) && !egoIds.has(t) && nodeIds.has(t)) {
          egoIds.add(t);
          nextFrontier.add(t);
        }
        if (frontier.has(t) && !egoIds.has(s) && nodeIds.has(s)) {
          egoIds.add(s);
          nextFrontier.add(s);
        }
      });
      frontier = nextFrontier;
      if (frontier.size === 0) break;
    }
    nodes = nodes.filter((n) => egoIds.has(n.id));
    nodeIds = egoIds;
  }

  const finalEdges = activeEdges.filter((e) => {
    const s = typeof e.source === "object" ? e.source.id : e.source;
    const t = typeof e.target === "object" ? e.target.id : e.target;
    return nodeIds.has(s) && nodeIds.has(t);
  });

  return {
    nodes,
    edges: finalEdges.map((e) => ({
      ...e,
      source: typeof e.source === "object" ? e.source.id : e.source,
      target: typeof e.target === "object" ? e.target.id : e.target,
    })),
  };
}
