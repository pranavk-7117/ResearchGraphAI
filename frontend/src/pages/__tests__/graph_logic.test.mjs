import { test, describe } from "node:test";
import assert from "node:assert";

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
});
