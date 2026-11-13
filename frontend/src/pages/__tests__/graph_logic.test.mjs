import { test, describe } from "node:test";
import assert from "node:assert";
import {
  placeLabels,
  boxesOverlap,
  circleIntersectsBox,
  getLinkArrowLength,
  computeTop8NodeIds,
  computeEgoNeighborIds,
  isPageRankUninformative,
  calculateMinEdgeWeightCutoff,
  getNodeVal,
  pickDefaultLayout,
  computeBeeswarmY,
  filterGraphData,
} from "../graphLabelPlacer.js";

describe("Knowledge Graph (G1-G8, K1-K6) Logic Tests — Live Helper Imports", () => {
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
      { id: 2, pagerank: 0.20 },
      { id: 3, pagerank: 0.15 },
      { id: 4, pagerank: 0.10 },
    ];
    assert.strictEqual(isPageRankUninformative(diverseNodes), false);
  });

  test("G1: Pruning threshold limits dense edges to <= 3 * nodes", () => {
    const nodes = Array.from({ length: 10 }, (_, i) => ({ id: i + 1 }));
    // 50 semantic edges with scores from 0.50 to 0.99
    const edges = Array.from({ length: 50 }, (_, i) => ({
      source: (i % 10) + 1,
      target: ((i + 1) % 10) + 1,
      relation_type: "similar",
      layer: "semantic",
      score: 0.5 + (i / 100),
    }));

    const cutoff = calculateMinEdgeWeightCutoff(nodes, edges, 3);
    assert.ok(cutoff >= 0.5, "Cutoff should prune excess edges");

    const surviving = edges.filter((e) => e.score >= cutoff);
    assert.ok(surviving.length <= 3 * nodes.length + 5, `Surviving edges (${surviving.length}) should be bounded`);
  });

  test("K3: placeLabels ensures selected node is always placed even in crowded clusters", () => {
    const crowdedNodes = Array.from({ length: 15 }, (_, i) => ({
      id: i + 1,
      x: 100 + (i % 3) * 10,
      y: 100 + Math.floor(i / 3) * 10,
      title: `Very Long Paper Title ${i + 1}`,
      radius: 12,
    }));

    const selectedId = 7;
    const placed = placeLabels({
      nodes: crowdedNodes,
      candidateIds: crowdedNodes.map((n) => n.id),
      selectedId,
      maxLabels: 5,
    });

    assert.ok(placed.has(selectedId), "Selected node must be placed even in dense clusters");
  });

  test("K3: placeLabels avoids overlapping bounding boxes among non-mandatory labels", () => {
    const nodes = [
      { id: 1, x: 100, y: 100, title: "Paper One Title", radius: 10 },
      { id: 2, x: 100, y: 100, title: "Paper Two Above Position", radius: 10 },
      { id: 3, x: 100, y: 100, title: "Paper Three Third Candidate Colliding", radius: 10 },
      { id: 4, x: 400, y: 400, title: "Paper Four Distant", radius: 10 },
    ];

    const placed = placeLabels({
      nodes,
      candidateIds: [1, 2, 3, 4],
      maxLabels: 5,
    });

    assert.ok(placed.has(1), "First candidate placed below");
    assert.ok(placed.has(2), "Second candidate placed above");
    assert.ok(!placed.has(3), "Third colliding candidate must be rejected because both below and above are occupied");
    assert.ok(placed.has(4), "Distant non-colliding candidate placed");

    const placedList = Array.from(placed.values());
    for (let i = 0; i < placedList.length; i++) {
      for (let j = i + 1; j < placedList.length; j++) {
        assert.ok(!boxesOverlap(placedList[i].bbox, placedList[j].bbox), "No two placed bounding boxes may overlap");
      }
    }
  });

  test("K3: placeLabels caps total placed labels at maxLabels", () => {
    const nodes = Array.from({ length: 25 }, (_, i) => ({
      id: i + 1,
      x: (i % 5) * 150,
      y: Math.floor(i / 5) * 100,
      title: `Spaced Paper Title ${i + 1}`,
      radius: 8,
    }));

    const placed = placeLabels({
      nodes,
      candidateIds: nodes.map((n) => n.id),
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

  test("K1: filterGraphData preserves exact node object references when selectedNode changes", () => {
    const nodeA = { id: 1, title: "Paper A", cluster_id: 1, citation_count: 5, fx: 100, fy: 200 };
    const nodeB = { id: 2, title: "Paper B", cluster_id: 1, citation_count: 10, fx: 300, fy: 400 };
    const baseNodes = [nodeA, nodeB];
    const edges = [{ source: 1, target: 2, relation_type: "cites", score: 1.0 }];

    // 1. Initial selection: nodeA
    const resA = filterGraphData({
      baseNodes,
      edges,
      selectedClusterId: null,
      searchQuery: "",
      enabledLayers: { citation: true, coupling: true, semantic: true },
      minEdgeWeight: 0.0,
      egoHops: "all",
      selectedNodeId: 1,
    });

    // 2. Click / select nodeB
    const resB = filterGraphData({
      baseNodes,
      edges,
      selectedClusterId: null,
      searchQuery: "",
      enabledLayers: { citation: true, coupling: true, semantic: true },
      minEdgeWeight: 0.0,
      egoHops: "all",
      selectedNodeId: 2,
    });

    // Node object references MUST be strictly identical (preserving simulation position & pinned fx/fy)
    assert.strictEqual(resA.nodes[0], baseNodes[0], "Node 0 must retain exact object reference");
    assert.strictEqual(resB.nodes[0], baseNodes[0], "Node 0 must retain exact object reference after selecting node B");
    assert.strictEqual(resA.nodes[0], resB.nodes[0], "Nodes across selections must have identical object identity");
    assert.strictEqual(resA.nodes[1], resB.nodes[1], "Node 1 must have identical object identity");
    assert.strictEqual(resB.nodes[0].fx, 100, "Pinned fx coordinate must be preserved");
    assert.strictEqual(resB.nodes[0].fy, 200, "Pinned fy coordinate must be preserved");
  });
});
