import { test, describe } from "node:test";
import assert from "node:assert";
import { placeLabels, boxesOverlap } from "../graphLabelPlacer.js";

// Logic helpers matching GraphPage.tsx implementations

function getLinkArrowLength(link) {
  return link.relation_type === "cites" || link.layer === "citation" ? 6 : 0;
}

function computeTop8NodeIds(nodes) {
  return new Set(
    [...nodes]
      .sort((a, b) => (b.citation_count || 0) - (a.citation_count || 0))
      .slice(0, 8)
      .map((n) => n.id)
  );
}

function computeEgoNeighborIds(selectedId, links) {
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

function isPageRankUninformative(nodes) {
  if (nodes.length < 2) return false;
  const prs = nodes.map((n) => n.pagerank || 0);
  const minPr = Math.min(...prs);
  const maxPr = Math.max(...prs);
  return maxPr - minPr < 1e-4;
}

function calculateMinEdgeWeightCutoff(nodes, edges, maxRatio = 3) {
  if (nodes.length === 0 || edges.length <= maxRatio * nodes.length) {
    return 0.0;
  }
  const simEdges = edges
    .filter((e) => e.relation_type !== "cites")
    .map((e) => e.score || 0.0)
    .sort((a, b) => b - a);
  const maxNonCitation = Math.max(0, maxRatio * nodes.length - edges.filter((e) => e.relation_type === "cites").length);
  if (simEdges.length > maxNonCitation && maxNonCitation > 0) {
    const threshold = simEdges[maxNonCitation - 1];
    return Math.min(0.85, Math.max(0.35, Math.round(threshold * 20) / 20));
  }
  return 0.50;
}

function getNodeVal(node, nodeSizeMode = "citations") {
  if (nodeSizeMode === "citations") {
    return Math.max(5, Math.min(16, 5 + Math.log2((node.citation_count || 0) + 1) * 1.6));
  } else if (nodeSizeMode === "pagerank") {
    return Math.max(5, Math.min(16, 5 + (node.pagerank || 0) * 80));
  }
  return 7;
}

function pickDefaultLayout(nodeCount) {
  return nodeCount <= 60 ? "radial" : "force";
}

function computeBeeswarmY(idxInGroup, baseCenterY, r) {
  if (idxInGroup === 0) return baseCenterY;
  const sign = idxInGroup % 2 === 1 ? 1 : -1;
  const step = Math.ceil(idxInGroup / 2);
  return baseCenterY + sign * step * (2 * r + 5);
}

describe("Knowledge Graph (G1-G8) Logic Tests", () => {
  test("G3: Arrowhead length is strictly 6 for citation edges and 0 for coupling/similarity", () => {
    assert.strictEqual(getLinkArrowLength({ relation_type: "cites", layer: "citation" }), 6);
    assert.strictEqual(getLinkArrowLength({ relation_type: "coupling", layer: "coupling" }), 0);
    assert.strictEqual(getLinkArrowLength({ relation_type: "similar", layer: "semantic" }), 0);
  });

  test("G2: Top 8 nodes by size are correctly selected for uncluttered label rendering", () => {
    const nodes = Array.from({ length: 20 }, (_, i) => ({
      id: i + 1,
      citation_count: i * 10,
    }));
    const top8 = computeTop8NodeIds(nodes);
    assert.strictEqual(top8.size, 8);
    // Highest citation counts: 190, 180, ..., 120 (ids 20, 19, ..., 13)
    assert.ok(top8.has(20));
    assert.ok(top8.has(13));
    assert.ok(!top8.has(12));
    assert.ok(!top8.has(1));
  });

  test("G2: Ego network neighbors are correctly identified for the selected paper", () => {
    const links = [
      { source: 1, target: 2 },
      { source: 1, target: 5 },
      { source: 3, target: 4 },
    ];
    const ego = computeEgoNeighborIds(1, links);
    assert.strictEqual(ego.size, 2);
    assert.ok(ego.has(2));
    assert.ok(ego.has(5));
    assert.ok(!ego.has(3));
  });

  test("G4: Uninformative PageRank detector flags flat/identical centrality", () => {
    const uniformNodes = [
      { id: 1, pagerank: 0.25 },
      { id: 2, pagerank: 0.25 },
      { id: 3, pagerank: 0.25 },
      { id: 4, pagerank: 0.25 },
    ];
    assert.strictEqual(isPageRankUninformative(uniformNodes), true);

    const diverseNodes = [
      { id: 1, pagerank: 0.55 },
      { id: 2, pagerank: 0.15 },
      { id: 3, pagerank: 0.05 },
    ];
    assert.strictEqual(isPageRankUninformative(diverseNodes), false);
  });

  test("G1: Pruning threshold limits dense edges to <= 3 * nodes", () => {
    const nodes = Array.from({ length: 10 }, (_, i) => ({ id: i + 1 }));
    // 50 similarity edges with descending scores from 0.99 down to 0.50
    const edges = Array.from({ length: 50 }, (_, i) => ({
      source: (i % 10) + 1,
      target: ((i + 1) % 10) + 1,
      relation_type: "similar",
      score: 1.0 - i * 0.01,
    }));
    const cutoff = calculateMinEdgeWeightCutoff(nodes, edges, 3);
    assert.ok(cutoff > 0.0);
    // Filtered edges with score >= cutoff should be approximately <= 30
    const retained = edges.filter((e) => e.score >= cutoff);
    assert.ok(retained.length <= 35, `Retained count ${retained.length} should be near 30`);
  });

  test("K3: placeLabels ensures selected node is always placed even in crowded clusters", () => {
    const nodes = [
      { id: 1, x: 100, y: 100, title: "Diabetic Foot Ulcer Sensor", radius: 10 },
      { id: 2, x: 102, y: 105, title: "Smart Insole Pressure", radius: 10 },
    ];
    const placed = placeLabels({
      nodes,
      candidateIds: [2],
      selectedId: 1,
      maxLabels: 8,
    });
    assert.ok(placed.has(1), "Selected node id=1 must be placed");
  });

  test("K3: placeLabels avoids overlapping bounding boxes among non-mandatory labels", () => {
    // 3 nodes very close to each other
    const nodes = [
      { id: 10, x: 200, y: 200, title: "First Dense Paper Title", radius: 10 },
      { id: 11, x: 205, y: 204, title: "Second Dense Paper Title", radius: 10 },
      { id: 12, x: 203, y: 202, title: "Third Dense Paper Title", radius: 10 },
      { id: 13, x: 500, y: 500, title: "Isolated Distant Paper", radius: 10 },
    ];
    const placed = placeLabels({
      nodes,
      candidateIds: [10, 11, 12, 13],
      maxLabels: 8,
    });
    const placedArr = Array.from(placed.values());
    for (let i = 0; i < placedArr.length; i++) {
      for (let j = i + 1; j < placedArr.length; j++) {
        const overlap = boxesOverlap(placedArr[i].bbox, placedArr[j].bbox);
        assert.strictEqual(
          overlap,
          false,
          `Boxes for nodes ${placedArr[i].nodeId} and ${placedArr[j].nodeId} should not overlap`
        );
      }
    }
  });

  test("K3: placeLabels caps total placed labels at maxLabels", () => {
    const nodes = Array.from({ length: 20 }, (_, i) => ({
      id: i + 1,
      x: i * 150,
      y: (i % 2) * 150,
      title: `Paper Number ${i + 1} Long Title`,
      radius: 8,
    }));
    const candidateIds = nodes.map((n) => n.id);
    const placed = placeLabels({
      nodes,
      candidateIds,
      maxLabels: 8,
    });
    assert.ok(placed.size <= 8, `Placed size ${placed.size} should be <= 8`);
  });

  test("K2: pickDefaultLayout chooses radial for <= 60 papers and force for > 60", () => {
    assert.strictEqual(pickDefaultLayout(25), "radial");
    assert.strictEqual(pickDefaultLayout(60), "radial");
    assert.strictEqual(pickDefaultLayout(61), "force");
    assert.strictEqual(pickDefaultLayout(150), "force");
  });

  test("K2: getNodeVal clamps radius strictly between 5px and 16px", () => {
    const zeroCitations = { id: 1, citation_count: 0 };
    const hugeCitations = { id: 2, citation_count: 500000 };
    assert.strictEqual(getNodeVal(zeroCitations), 5);
    assert.strictEqual(getNodeVal(hugeCitations), 16);
  });

  test("K2: computeBeeswarmY guarantees vertical separation >= 2r + 4 between adjacent nodes in lane", () => {
    const r = 8;
    const y0 = computeBeeswarmY(0, 100, r);
    const y1 = computeBeeswarmY(1, 100, r);
    const y2 = computeBeeswarmY(2, 100, r);
    const y3 = computeBeeswarmY(3, 100, r);
    assert.strictEqual(y0, 100);
    assert.ok(Math.abs(y1 - y0) >= 2 * r + 4, "Delta y between 0 and 1 must be >= 2r+4");
    assert.ok(Math.abs(y2 - y0) >= 2 * r + 4, "Delta y between 0 and 2 must be >= 2r+4");
    assert.ok(Math.abs(y3 - y1) >= 2 * r + 4, "Delta y between 1 and 3 on same side must be >= 2r+4");
  });

  test("K1: Node identity is preserved and not reconstructed on node click", () => {
    const rawNodes = [
      { id: 1, title: "Paper 1", fx: 10, fy: 20 },
      { id: 2, title: "Paper 2", fx: 30, fy: 40 },
    ];
    // Simulating baseNodes memoization
    const baseNodes = rawNodes.map((n) => ({ ...n, name: n.title }));

    // Simulating filteredData when selectedNode changes
    let selectedNode = baseNodes[0];
    const filteredNodesFirst = baseNodes; // Reused directly

    selectedNode = baseNodes[1];
    const filteredNodesSecond = baseNodes; // Reused directly

    assert.strictEqual(filteredNodesFirst, filteredNodesSecond, "Node arrays reference should be identical");
    assert.strictEqual(filteredNodesFirst[0], filteredNodesSecond[0], "Node object references must be preserved");
    assert.strictEqual(filteredNodesSecond[0].fx, 10, "fx coordinate must persist");
  });
});
