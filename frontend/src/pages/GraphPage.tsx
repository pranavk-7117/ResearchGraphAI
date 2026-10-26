import ForceGraph2D from "react-force-graph-2d";
import {
  BarChart3,
  BookOpen,
  ChevronRight,
  Download,
  ExternalLink,
  Filter,
  Focus,
  Layers,
  Maximize2,
  Minimize2,
  Network,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, Cluster, GraphData, GraphEdge, GraphNode, Project } from "../lib/api";

// Cluster color themes matching the reference design (Emerald, Amber, Blue, Rose, Purple, Cyan, Indigo)
export const CLUSTER_PALETTES = [
  { hex: "#10b981", bg: "rgba(16, 185, 129, 0.08)", border: "rgba(16, 185, 129, 0.32)", badge: "#059669" },
  { hex: "#f59e0b", bg: "rgba(245, 158, 11, 0.08)", border: "rgba(245, 158, 11, 0.32)", badge: "#d97706" },
  { hex: "#3b82f6", bg: "rgba(59, 130, 246, 0.08)", border: "rgba(59, 130, 246, 0.32)", badge: "#2563eb" },
  { hex: "#ef4444", bg: "rgba(239, 68, 68, 0.08)", border: "rgba(239, 68, 68, 0.32)", badge: "#dc2626" },
  { hex: "#8b5cf6", bg: "rgba(139, 92, 246, 0.08)", border: "rgba(139, 92, 246, 0.32)", badge: "#7c3aed" },
  { hex: "#06b6d4", bg: "rgba(6, 182, 212, 0.08)", border: "rgba(6, 182, 212, 0.32)", badge: "#0891b2" },
  { hex: "#6366f1", bg: "rgba(99, 102, 241, 0.08)", border: "rgba(99, 102, 241, 0.32)", badge: "#4f46e5" },
];

interface Point {
  x: number;
  y: number;
}

// 2D Convex Hull (Monotone Chain algorithm)
function computeConvexHull(points: Point[]): Point[] {
  if (points.length <= 1) return points;
  if (points.length === 2) {
    const [p1, p2] = points;
    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;
    const len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len;
    const ny = dx / len;
    const pad = 24;
    return [
      { x: p1.x + nx * pad, y: p1.y + ny * pad },
      { x: p2.x + nx * pad, y: p2.y + ny * pad },
      { x: p2.x - nx * pad, y: p2.y - ny * pad },
      { x: p1.x - nx * pad, y: p1.y - ny * pad },
    ];
  }

  const sorted = [...points].sort((a, b) => (a.x === b.x ? a.y - b.y : a.x - b.x));
  const cross = (o: Point, a: Point, b: Point) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);

  const lower: Point[] = [];
  for (const p of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) {
      lower.pop();
    }
    lower.push(p);
  }

  const upper: Point[] = [];
  for (let i = sorted.length - 1; i >= 0; i--) {
    const p = sorted[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) {
      upper.pop();
    }
    upper.push(p);
  }

  lower.pop();
  upper.pop();
  return lower.concat(upper);
}

// Expand convex hull outward for smooth bubble clouds
function expandHull(hull: Point[], padding = 42): Point[] {
  if (hull.length === 0) return [];
  if (hull.length === 1) {
    const p = hull[0];
    const pts: Point[] = [];
    const steps = 12;
    for (let i = 0; i < steps; i++) {
      const angle = (i / steps) * 2 * Math.PI;
      pts.push({
        x: p.x + Math.cos(angle) * padding,
        y: p.y + Math.sin(angle) * padding,
      });
    }
    return pts;
  }

  let cx = 0;
  let cy = 0;
  for (const p of hull) {
    cx += p.x;
    cy += p.y;
  }
  cx /= hull.length;
  cy /= hull.length;

  return hull.map((p) => {
    const dx = p.x - cx;
    const dy = p.y - cy;
    const dist = Math.hypot(dx, dy) || 1;
    return {
      x: p.x + (dx / dist) * padding,
      y: p.y + (dy / dist) * padding,
    };
  });
}

function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState({ width: 900, height: 650 });

  useEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(([entry]) => {
      setSize({
        width: Math.max(320, entry.contentRect.width),
        height: Math.max(420, entry.contentRect.height),
      });
    });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);

  return { ref, size };
}

export function GraphPage({ project }: { project: Project | null }) {
  const graphRef = useRef<any>(null);
  const { ref: canvasRef, size } = useElementSize<HTMLDivElement>();

  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [], total_nodes: 0, total_edges: 0 });
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedClusterId, setSelectedClusterId] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Toolbar state
  const [layoutMode, setLayoutMode] = useState<"force" | "radial" | "concentric">("force");
  const [colorMode, setColorMode] = useState<"cluster" | "citations" | "year">("cluster");
  const [nodeSizeMode, setNodeSizeMode] = useState<"citations" | "pagerank" | "uniform">("citations");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showAbstractFull, setShowAbstractFull] = useState(false);

  useEffect(() => {
    if (project) {
      loadGraphAndClusters();
    }
  }, [project?.id]);

  async function loadGraphAndClusters() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const [gData, cData] = await Promise.all([
        api.graph.get(project.id),
        api.clusters.get(project.id),
      ]);
      setGraphData(gData);
      setClusters(cData);

      // Default select the most central / most cited paper
      if (gData.nodes.length > 0) {
        const sorted = [...gData.nodes].sort((a, b) => (b.pagerank || 0) - (a.pagerank || 0) || b.citation_count - a.citation_count);
        setSelectedNode(sorted[0]);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load knowledge graph.");
    } finally {
      setLoading(false);
    }
  }

  // Filtered nodes and edges
  const filteredData = useMemo(() => {
    let nodes = graphData.nodes;
    if (selectedClusterId !== null) {
      nodes = nodes.filter((n) => n.cluster_id === selectedClusterId);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      nodes = nodes.filter(
        (n) => n.title.toLowerCase().includes(q) || n.authors_str.toLowerCase().includes(q)
      );
    }

    const nodeIds = new Set(nodes.map((n) => n.id));
    const edges = graphData.edges.filter(
      (e) =>
        (typeof e.source === "object" ? nodeIds.has((e.source as any).id) : nodeIds.has(e.source)) &&
        (typeof e.target === "object" ? nodeIds.has((e.target as any).id) : nodeIds.has(e.target))
    );

    return {
      nodes: nodes.map((n) => ({ ...n, name: n.title })),
      links: edges.map((e) => ({
        ...e,
        source: typeof e.source === "object" ? (e.source as any).id : e.source,
        target: typeof e.target === "object" ? (e.target as any).id : e.target,
      })),
    };
  }, [graphData, selectedClusterId, searchQuery]);

  // Apply Layout Transformations
  useEffect(() => {
    if (!graphRef.current || filteredData.nodes.length === 0) return;

    if (layoutMode === "radial") {
      const clusterMap = new Map<number | null, any[]>();
      filteredData.nodes.forEach((node: any) => {
        const cid = node.cluster_id;
        if (!clusterMap.has(cid)) clusterMap.set(cid, []);
        clusterMap.get(cid)!.push(node);
      });

      const clusterKeys = Array.from(clusterMap.keys());
      const totalClusters = clusterKeys.length || 1;
      const radius = Math.min(size.width, size.height) * 0.32;

      clusterKeys.forEach((cid, idx) => {
        const angle = (idx / totalClusters) * 2 * Math.PI;
        const cx = Math.cos(angle) * radius;
        const cy = Math.sin(angle) * radius;
        const group = clusterMap.get(cid)!;

        group.forEach((node: any, nIdx: number) => {
          const subAngle = (nIdx / group.length) * 2 * Math.PI;
          const subR = 30 + Math.sqrt(nIdx) * 18;
          node.fx = cx + Math.cos(subAngle) * subR;
          node.fy = cy + Math.sin(subAngle) * subR;
        });
      });
      graphRef.current.d3ReheatSimulation();
    } else if (layoutMode === "concentric") {
      // Concentric rings by citation tier
      const sorted = [...filteredData.nodes].sort((a: any, b: any) => b.citation_count - a.citation_count);
      const total = sorted.length;
      sorted.forEach((node: any, idx: number) => {
        let ringR = 0;
        if (idx < Math.ceil(total * 0.15)) {
          ringR = 50 + idx * 8; // Inner central ring
        } else if (idx < Math.ceil(total * 0.5)) {
          ringR = 150 + (idx - total * 0.15) * 6; // Mid ring
        } else {
          ringR = 270 + (idx - total * 0.5) * 5; // Outer ring
        }
        const angle = (idx / total) * 2 * Math.PI * 3.5;
        node.fx = Math.cos(angle) * ringR;
        node.fy = Math.sin(angle) * ringR;
      });
      graphRef.current.d3ReheatSimulation();
    } else {
      // Standard Free Force-Directed layout
      filteredData.nodes.forEach((node: any) => {
        node.fx = undefined;
        node.fy = undefined;
      });
      graphRef.current.d3ReheatSimulation();
    }
  }, [layoutMode, filteredData.nodes.length, size]);

  // Compute node color
  const getNodeColor = (node: any) => {
    if (colorMode === "cluster") {
      if (node.cluster_id !== null && clusters.length > 0) {
        const cIdx = clusters.findIndex((c) => c.id === node.cluster_id);
        const palette = CLUSTER_PALETTES[(cIdx >= 0 ? cIdx : 0) % CLUSTER_PALETTES.length];
        return palette.hex;
      }
      return "#3b82f6";
    } else if (colorMode === "citations") {
      const c = node.citation_count || 0;
      if (c >= 50) return "#f59e0b"; // Gold
      if (c >= 20) return "#8b5cf6"; // Purple
      if (c >= 5) return "#3b82f6"; // Blue
      return "#94a3b8"; // Slate
    } else {
      // Year ramp
      const y = node.year || 2020;
      if (y >= 2023) return "#ef4444";
      if (y >= 2020) return "#f59e0b";
      if (y >= 2017) return "#10b981";
      return "#0284c7";
    }
  };

  // Compute node size
  const getNodeVal = (node: any) => {
    if (nodeSizeMode === "citations") {
      return Math.max(5, Math.min(22, 5 + Math.log2((node.citation_count || 0) + 1) * 2.2));
    } else if (nodeSizeMode === "pagerank") {
      return Math.max(5, Math.min(22, 5 + (node.pagerank || 0) * 110));
    }
    return 7;
  };

  // Connected papers to selected node
  const connectedNeighbors = useMemo(() => {
    if (!selectedNode) return [];
    const neighbors: Array<{
      node: GraphNode;
      relationType: string;
      score: number;
      basis: string;
    }> = [];

    const nodeId = selectedNode.id;
    for (const e of graphData.edges) {
      const src = typeof e.source === "object" ? (e.source as any).id : e.source;
      const tgt = typeof e.target === "object" ? (e.target as any).id : e.target;

      if (src === nodeId || tgt === nodeId) {
        const otherId = src === nodeId ? tgt : src;
        const otherNode = graphData.nodes.find((n) => n.id === otherId);
        if (otherNode && !neighbors.some((item) => item.node.id === otherId)) {
          neighbors.push({
            node: otherNode,
            relationType: e.relation_type,
            score: e.score || 0.85,
            basis: e.basis,
          });
        }
      }
    }

    return neighbors.sort((a, b) => b.score - a.score);
  }, [selectedNode, graphData]);

  // Export handlers
  const handleExportPNG = () => {
    const canvas = canvasRef.current?.querySelector("canvas");
    if (!canvas) return;
    const url = canvas.toDataURL("image/png");
    const a = document.createElement("a");
    a.download = `knowledge-graph-${project?.topic || "research"}.png`;
    a.href = url;
    a.click();
  };

  const handleExportJSON = () => {
    const dataStr = JSON.stringify(filteredData, null, 2);
    const blob = new Blob([dataStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.download = `knowledge-graph-${project?.topic || "research"}.json`;
    a.href = url;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!project) {
    return (
      <section className="page" style={{ maxWidth: 800, margin: "40px auto", textAlign: "center" }}>
        <Network size={48} color="#94a3b8" style={{ margin: "0 auto 16px" }} />
        <h2>No Active Research Project</h2>
        <p style={{ color: "#64748b" }}>Please select a research project to inspect its knowledge graph.</p>
      </section>
    );
  }

  return (
    <section
      className="page graphPage"
      style={{
        display: "flex",
        flexDirection: "column",
        height: isFullscreen ? "100vh" : "calc(100vh - 40px)",
        position: isFullscreen ? "fixed" : "relative",
        top: isFullscreen ? 0 : undefined,
        left: isFullscreen ? 0 : undefined,
        width: isFullscreen ? "100vw" : "100%",
        zIndex: isFullscreen ? 9999 : 1,
        background: "#f8fafc",
        padding: isFullscreen ? 16 : undefined,
      }}
    >
      {/* Top Controls Toolbar */}
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 10,
          flexWrap: "wrap",
          gap: 10,
          background: "white",
          padding: "10px 16px",
          borderRadius: 8,
          border: "1px solid #e2e8f0",
          boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
        }}
      >
        {/* Left Toolbar Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          {/* Layout Mode */}
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#475569" }}>
            <Layers size={14} color="#64748b" />
            <span style={{ fontWeight: 500 }}>Layout:</span>
            <select
              value={layoutMode}
              onChange={(e) => setLayoutMode(e.target.value as any)}
              style={{
                padding: "5px 10px",
                borderRadius: 6,
                border: "1px solid #cbd5e1",
                fontSize: 12,
                background: "#f8fafc",
                cursor: "pointer",
              }}
            >
              <option value="force">Force-Directed</option>
              <option value="radial">Radial Clustered</option>
              <option value="concentric">Concentric Rings</option>
            </select>
          </div>

          {/* Color By */}
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#475569" }}>
            <span style={{ fontWeight: 500 }}>Color:</span>
            <select
              value={colorMode}
              onChange={(e) => setColorMode(e.target.value as any)}
              style={{
                padding: "5px 10px",
                borderRadius: 6,
                border: "1px solid #cbd5e1",
                fontSize: 12,
                background: "#f8fafc",
                cursor: "pointer",
              }}
            >
              <option value="cluster">Thematic Cluster</option>
              <option value="citations">Citation Influence</option>
              <option value="year">Publication Year</option>
            </select>
          </div>

          {/* Node Size */}
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#475569" }}>
            <span style={{ fontWeight: 500 }}>Node Size:</span>
            <select
              value={nodeSizeMode}
              onChange={(e) => setNodeSizeMode(e.target.value as any)}
              style={{
                padding: "5px 10px",
                borderRadius: 6,
                border: "1px solid #cbd5e1",
                fontSize: 12,
                background: "#f8fafc",
                cursor: "pointer",
              }}
            >
              <option value="citations">Citation Count</option>
              <option value="pagerank">PageRank Centrality</option>
              <option value="uniform">Uniform Size</option>
            </select>
          </div>

          {/* Search bar */}
          <div style={{ position: "relative", marginLeft: 4 }}>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search in graph..."
              style={{
                padding: "5px 10px 5px 28px",
                borderRadius: 6,
                border: "1px solid #cbd5e1",
                fontSize: 12,
                width: 180,
                background: "#ffffff",
              }}
            />
            <Search size={14} color="#94a3b8" style={{ position: "absolute", left: 8, top: 8 }} />
          </div>
        </div>

        {/* Right Toolbar Actions */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            onClick={() => graphRef.current?.zoomToFit(400, 36)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 5,
              padding: "5px 10px",
              background: "#f1f5f9",
              border: "1px solid #cbd5e1",
              borderRadius: 6,
              fontSize: 12,
              cursor: "pointer",
              color: "#334155",
            }}
            title="Fit view to graph"
          >
            <Focus size={14} />
            <span>Fit View</span>
          </button>

          {/* Export Dropdown */}
          <button
            onClick={handleExportPNG}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 5,
              padding: "5px 10px",
              background: "#f1f5f9",
              border: "1px solid #cbd5e1",
              borderRadius: 6,
              fontSize: 12,
              cursor: "pointer",
              color: "#334155",
            }}
            title="Download Canvas PNG"
          >
            <Download size={14} />
            <span>Export PNG</span>
          </button>

          <button
            onClick={handleExportJSON}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 5,
              padding: "5px 10px",
              background: "#f1f5f9",
              border: "1px solid #cbd5e1",
              borderRadius: 6,
              fontSize: 12,
              cursor: "pointer",
              color: "#334155",
            }}
            title="Download Graph JSON"
          >
            <span>JSON</span>
          </button>

          {/* Fullscreen Toggle */}
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            style={{
              display: "flex",
              alignItems: "center",
              padding: "5px 8px",
              background: "#f1f5f9",
              border: "1px solid #cbd5e1",
              borderRadius: 6,
              fontSize: 12,
              cursor: "pointer",
              color: "#334155",
            }}
            title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </header>

      {error && (
        <div style={{ padding: 10, background: "#fee2e2", color: "#991b1b", borderRadius: 6, marginBottom: 8, fontSize: 12 }}>
          {error}
        </div>
      )}

      {/* Main 2-Column Canvas + Inspector Layout */}
      <div style={{ flex: 1, display: "flex", gap: 12, minHeight: 0 }}>
        {/* Left: Interactive Canvas */}
        <div
          style={{
            flex: 1,
            position: "relative",
            border: "1px solid #e2e8f0",
            borderRadius: 8,
            overflow: "hidden",
            background: "#ffffff",
          }}
        >
          <div ref={canvasRef} style={{ width: "100%", height: "100%" }}>
            <ForceGraph2D
              ref={graphRef}
              width={size.width}
              height={size.height}
              graphData={filteredData}
              nodeId="id"
              nodeVal={getNodeVal}
              nodeColor={getNodeColor}
              linkColor={(link: any) => (link.relation_type === "cites" ? "#0f766e" : "#8b5cf6")}
              linkWidth={(link: any) => (link.relation_type === "cites" ? 1.8 : 1.2)}
              linkLineDash={(link: any) => (link.relation_type === "cites" ? undefined : [4, 4])}
              linkDirectionalArrowLength={(link: any) => (link.relation_type === "cites" ? 6 : 0)}
              linkDirectionalArrowRelPos={0.8}
              linkCurvature={0.08}
              // Thematic Convex Hulls / Cluster Clouds
              onRenderFramePre={(ctx, globalScale) => {
                if (clusters.length === 0 || colorMode !== "cluster") return;

                // Group nodes by cluster_id
                const clusterNodeCoords = new Map<number, Point[]>();
                filteredData.nodes.forEach((n: any) => {
                  if (n.cluster_id !== null && typeof n.x === "number" && typeof n.y === "number") {
                    if (!clusterNodeCoords.has(n.cluster_id)) {
                      clusterNodeCoords.set(n.cluster_id, []);
                    }
                    clusterNodeCoords.get(n.cluster_id)!.push({ x: n.x, y: n.y });
                  }
                });

                clusters.forEach((cluster, idx) => {
                  const points = clusterNodeCoords.get(cluster.id);
                  if (!points || points.length === 0) return;

                  const palette = CLUSTER_PALETTES[idx % CLUSTER_PALETTES.length];
                  const hull = computeConvexHull(points);
                  const padded = expandHull(hull, 40);

                  if (padded.length < 3) return;

                  ctx.save();
                  // Draw smoothed convex hull
                  ctx.beginPath();
                  const len = padded.length;
                  for (let i = 0; i < len; i++) {
                    const p1 = padded[i];
                    const p2 = padded[(i + 1) % len];
                    const midX = (p1.x + p2.x) / 2;
                    const midY = (p1.y + p2.y) / 2;
                    if (i === 0) {
                      ctx.moveTo(midX, midY);
                    } else {
                      ctx.quadraticCurveTo(p1.x, p1.y, midX, midY);
                    }
                  }
                  const pFirst = padded[0];
                  const pSecond = padded[1 % len];
                  ctx.quadraticCurveTo(pFirst.x, pFirst.y, (pFirst.x + pSecond.x) / 2, (pFirst.y + pSecond.y) / 2);
                  ctx.closePath();

                  ctx.fillStyle = palette.bg;
                  ctx.fill();
                  ctx.strokeStyle = palette.border;
                  ctx.lineWidth = 1.5;
                  ctx.stroke();

                  // Find top vertex for cluster title pill badge
                  let minY = Infinity;
                  let topX = 0;
                  for (const p of padded) {
                    if (p.y < minY) {
                      minY = p.y;
                      topX = p.x;
                    }
                  }

                  // Draw pill label badge at the top of the cluster
                  const fontSize = Math.max(9, Math.min(13, 11 / Math.sqrt(globalScale)));
                  ctx.font = `600 ${fontSize}px Inter, -apple-system, sans-serif`;
                  const labelText = cluster.label;
                  const textMetrics = ctx.measureText(labelText);
                  const pillW = textMetrics.width + 16;
                  const pillH = fontSize + 10;
                  const pillX = topX - pillW / 2;
                  const pillY = minY - pillH - 6;

                  // Pill background
                  ctx.beginPath();
                  const r = pillH / 2;
                  ctx.moveTo(pillX + r, pillY);
                  ctx.lineTo(pillX + pillW - r, pillY);
                  ctx.arcTo(pillX + pillW, pillY, pillX + pillW, pillY + r, r);
                  ctx.lineTo(pillX + pillW, pillY + pillH - r);
                  ctx.arcTo(pillX + pillW, pillY + pillH, pillX + pillW - r, pillY + pillH, r);
                  ctx.lineTo(pillX + r, pillY + pillH);
                  ctx.arcTo(pillX, pillY + pillH, pillX, pillY + pillH - r, r);
                  ctx.lineTo(pillX, pillY + r);
                  ctx.arcTo(pillX, pillY, pillX + r, pillY, r);
                  ctx.closePath();

                  ctx.fillStyle = palette.badge;
                  ctx.fill();
                  ctx.strokeStyle = "rgba(255, 255, 255, 0.4)";
                  ctx.lineWidth = 1;
                  ctx.stroke();

                  // Pill text
                  ctx.fillStyle = "#ffffff";
                  ctx.textAlign = "center";
                  ctx.textBaseline = "middle";
                  ctx.fillText(labelText, topX, pillY + pillH / 2);

                  ctx.restore();
                });
              }}
              // Custom Node Rendering
              nodeCanvasObjectMode={() => "replace"}
              nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
                const r = getNodeVal(node);
                const color = getNodeColor(node);
                const isSelected = selectedNode?.id === node.id;

                // Outer halo for selected node
                if (isSelected) {
                  ctx.beginPath();
                  ctx.arc(node.x, node.y, r + 6, 0, 2 * Math.PI);
                  ctx.fillStyle = "rgba(59, 130, 246, 0.28)";
                  ctx.fill();

                  ctx.beginPath();
                  ctx.arc(node.x, node.y, r + 3, 0, 2 * Math.PI);
                  ctx.strokeStyle = "#2563eb";
                  ctx.lineWidth = 2;
                  ctx.stroke();
                }

                // Node circle
                ctx.beginPath();
                ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
                ctx.fillStyle = color;
                ctx.fill();
                ctx.lineWidth = 1.5;
                ctx.strokeStyle = "#ffffff";
                ctx.stroke();

                // Draw label
                if (isSelected) {
                  // Prominent card pill badge for selected node
                  const label = node.title.length > 34 ? `${node.title.slice(0, 32)}...` : node.title;
                  const fontSize = Math.max(10, 11 / Math.sqrt(globalScale));
                  ctx.font = `600 ${fontSize}px Inter, sans-serif`;
                  const metrics = ctx.measureText(label);
                  const bW = metrics.width + 16;
                  const bH = fontSize + 10;
                  const bX = node.x - bW / 2;
                  const bY = node.y - r - bH - 6;

                  ctx.save();
                  ctx.shadowColor = "rgba(0,0,0,0.14)";
                  ctx.shadowBlur = 6;
                  ctx.shadowOffsetY = 2;

                  ctx.beginPath();
                  const cr = 4;
                  ctx.moveTo(bX + cr, bY);
                  ctx.lineTo(bX + bW - cr, bY);
                  ctx.arcTo(bX + bW, bY, bX + bW, bY + cr, cr);
                  ctx.lineTo(bX + bW, bY + bH - cr);
                  ctx.arcTo(bX + bW, bY + bH, bX + bW - cr, bY + bH, cr);
                  ctx.lineTo(bX + cr, bY + bH);
                  ctx.arcTo(bX, bY + bH, bX, bY + bH - cr, cr);
                  ctx.lineTo(bX, bY + cr);
                  ctx.arcTo(bX, bY, bX + cr, bY, cr);
                  ctx.closePath();

                  ctx.fillStyle = "#ffffff";
                  ctx.fill();
                  ctx.strokeStyle = "#cbd5e1";
                  ctx.lineWidth = 1;
                  ctx.stroke();
                  ctx.restore();

                  ctx.fillStyle = "#0f172a";
                  ctx.textAlign = "center";
                  ctx.textBaseline = "middle";
                  ctx.fillText(label, node.x, bY + bH / 2);
                } else if (globalScale >= 0.75) {
                  // Clean text label below node
                  const label = node.title.length > 26 ? `${node.title.slice(0, 24)}...` : node.title;
                  const fontSize = Math.max(9, 10 / Math.sqrt(globalScale));
                  ctx.font = `500 ${fontSize}px Inter, sans-serif`;
                  ctx.fillStyle = "#334155";
                  ctx.textAlign = "center";
                  ctx.textBaseline = "top";
                  ctx.fillText(label, node.x, node.y + r + 4);
                }
              }}
              nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
                const r = getNodeVal(node) + 4;
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
                ctx.fill();
              }}
              onNodeClick={(node: any) => setSelectedNode(node)}
            />
          </div>

          {/* Bottom Floating Legend Bar */}
          <div
            style={{
              position: "absolute",
              bottom: 12,
              left: 12,
              background: "rgba(255, 255, 255, 0.94)",
              backdropFilter: "blur(6px)",
              padding: "8px 14px",
              borderRadius: 8,
              border: "1px solid #cbd5e1",
              fontSize: 11,
              display: "flex",
              gap: 18,
              alignItems: "center",
              boxShadow: "0 2px 6px rgba(0,0,0,0.06)",
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 6, color: "#334155" }}>
              <span style={{ width: 16, height: 2.5, background: "#0f766e", display: "inline-block", borderRadius: 1 }} />
              Verified Citation (Metadata)
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 6, color: "#334155" }}>
              <span style={{ width: 16, height: 2, borderTop: "2px dashed #8b5cf6", display: "inline-block" }} />
              Inferred Semantic Similarity
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 6, color: "#64748b" }}>
              <span>Size:</span>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#94a3b8", display: "inline-block" }} />
              <span style={{ width: 12, height: 12, borderRadius: "50%", background: "#94a3b8", display: "inline-block" }} />
              Lower / Higher Influence
            </span>
          </div>
        </div>

        {/* Right: Persistent 3-Card Inspector Sidebar */}
        <aside
          style={{
            width: 340,
            display: "flex",
            flexDirection: "column",
            gap: 12,
            overflowY: "auto",
            minHeight: 0,
          }}
        >
          {/* Card 1: Thematic Clusters */}
          <div
            style={{
              background: "white",
              border: "1px solid #e2e8f0",
              borderRadius: 8,
              padding: "14px 16px",
              boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Sparkles size={15} color="#2563eb" />
                <h3 style={{ fontSize: 13, fontWeight: 600, color: "#0f172a", margin: 0 }}>Thematic Clusters</h3>
              </div>
              <span
                style={{
                  fontSize: 11,
                  background: "#eff6ff",
                  color: "#1d4ed8",
                  padding: "2px 7px",
                  borderRadius: 10,
                  fontWeight: 600,
                }}
              >
                {clusters.length}
              </span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 160, overflowY: "auto" }}>
              {clusters.map((c, idx) => {
                const palette = CLUSTER_PALETTES[idx % CLUSTER_PALETTES.length];
                const isSelected = selectedClusterId === c.id;
                return (
                  <button
                    key={c.id}
                    onClick={() => setSelectedClusterId(isSelected ? null : c.id)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "6px 10px",
                      borderRadius: 6,
                      background: isSelected ? "#f1f5f9" : "transparent",
                      border: isSelected ? `1px solid ${palette.hex}` : "1px solid transparent",
                      cursor: "pointer",
                      textAlign: "left",
                      width: "100%",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8, overflow: "hidden" }}>
                      <span
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: "50%",
                          background: palette.hex,
                          flexShrink: 0,
                        }}
                      />
                      <span
                        style={{
                          fontSize: 12,
                          color: isSelected ? "#0f172a" : "#334155",
                          fontWeight: isSelected ? 600 : 400,
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                        }}
                      >
                        {c.label}
                      </span>
                    </div>
                    <span style={{ fontSize: 11, color: "#64748b", flexShrink: 0, marginLeft: 6 }}>
                      {c.member_count} nodes
                    </span>
                  </button>
                );
              })}
              {clusters.length === 0 && (
                <div style={{ fontSize: 12, color: "#94a3b8", textAlign: "center", padding: "8px 0" }}>
                  No clusters identified yet.
                </div>
              )}
            </div>

            {selectedClusterId !== null && (
              <button
                onClick={() => setSelectedClusterId(null)}
                style={{
                  marginTop: 8,
                  fontSize: 11,
                  color: "#2563eb",
                  background: "none",
                  border: "none",
                  padding: 0,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                }}
              >
                <X size={12} /> Clear cluster filter
              </button>
            )}
          </div>

          {/* Card 2: Selected Node */}
          <div
            style={{
              background: "white",
              border: "1px solid #e2e8f0",
              borderRadius: 8,
              padding: "16px",
              boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
            }}
          >
            {selectedNode ? (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 600,
                        padding: "2px 7px",
                        borderRadius: 8,
                        background: selectedNode.abstract_only ? "#f1f5f9" : "#dcfce7",
                        color: selectedNode.abstract_only ? "#64748b" : "#166534",
                      }}
                    >
                      {selectedNode.abstract_only ? "Abstract-Level" : "Full-Text Indexed"}
                    </span>
                    {(selectedNode.pagerank || 0) > 0.05 && (
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 600,
                          padding: "2px 7px",
                          borderRadius: 8,
                          background: "#e0e7ff",
                          color: "#3730a3",
                        }}
                      >
                        High Centrality
                      </span>
                    )}
                    {selectedNode.citation_count >= 30 && (
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 600,
                          padding: "2px 7px",
                          borderRadius: 8,
                          background: "#fef3c7",
                          color: "#92400e",
                        }}
                      >
                        Top Cited
                      </span>
                    )}
                  </div>
                </div>

                <h4 style={{ fontSize: 14, fontWeight: 600, color: "#0f172a", margin: "0 0 6px", lineHeight: 1.3 }}>
                  {selectedNode.title}
                </h4>

                <div style={{ fontSize: 11, color: "#64748b", marginBottom: 12 }}>
                  {selectedNode.authors_str || "Authors indexed"} · {selectedNode.year || "n.d."}
                  {selectedNode.venue ? ` · ${selectedNode.venue}` : ""}
                </div>

                {/* Metrics 3-Col Box */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, marginBottom: 12 }}>
                  <div style={{ background: "#f8fafc", padding: "6px 8px", borderRadius: 6, border: "1px solid #e2e8f0" }}>
                    <span style={{ fontSize: 10, color: "#64748b" }}>Citations</span>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>{selectedNode.citation_count}</div>
                  </div>
                  <div style={{ background: "#f8fafc", padding: "6px 8px", borderRadius: 6, border: "1px solid #e2e8f0" }}>
                    <span style={{ fontSize: 10, color: "#64748b" }}>Relations</span>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>{connectedNeighbors.length}</div>
                  </div>
                  <div style={{ background: "#f8fafc", padding: "6px 8px", borderRadius: 6, border: "1px solid #e2e8f0" }}>
                    <span style={{ fontSize: 10, color: "#64748b" }}>PageRank</span>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>
                      {((selectedNode.pagerank || 0) * 100).toFixed(1)}%
                    </div>
                  </div>
                </div>

                {/* Abstract Preview */}
                {selectedNode.abstract ? (
                  <div style={{ marginBottom: 12 }}>
                    <p
                      style={{
                        fontSize: 11,
                        color: "#475569",
                        lineHeight: 1.45,
                        margin: 0,
                        display: showAbstractFull ? "block" : "-webkit-box",
                        WebkitLineClamp: showAbstractFull ? "unset" : 3,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}
                    >
                      {selectedNode.abstract}
                    </p>
                    {selectedNode.abstract.length > 150 && (
                      <button
                        onClick={() => setShowAbstractFull(!showAbstractFull)}
                        style={{
                          fontSize: 10,
                          color: "#2563eb",
                          background: "none",
                          border: "none",
                          padding: "2px 0 0",
                          cursor: "pointer",
                          fontWeight: 500,
                        }}
                      >
                        {showAbstractFull ? "Show less" : "Read more"}
                      </button>
                    )}
                  </div>
                ) : (
                  <div style={{ fontSize: 11, color: "#94a3b8", fontStyle: "italic", marginBottom: 12 }}>
                    Abstract not indexed for this node.
                  </div>
                )}

                {/* Actions */}
                <div style={{ display: "flex", gap: 8 }}>
                  {selectedNode.doi && (
                    <a
                      href={`https://doi.org/${selectedNode.doi}`}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        flex: 1,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: 4,
                        padding: "6px 10px",
                        background: "#eff6ff",
                        color: "#1d4ed8",
                        border: "1px solid #bfdbfe",
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 500,
                        textDecoration: "none",
                      }}
                    >
                      <ExternalLink size={12} /> DOI Link
                    </a>
                  )}
                  {selectedNode.url && !selectedNode.doi && (
                    <a
                      href={selectedNode.url}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        flex: 1,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: 4,
                        padding: "6px 10px",
                        background: "#eff6ff",
                        color: "#1d4ed8",
                        border: "1px solid #bfdbfe",
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 500,
                        textDecoration: "none",
                      }}
                    >
                      <ExternalLink size={12} /> Paper URL
                    </a>
                  )}
                  <button
                    onClick={() => {
                      if (selectedNode && graphRef.current) {
                        const n: any = filteredData.nodes.find((item) => item.id === selectedNode.id);
                        if (n && typeof n.x === "number") {
                          graphRef.current.centerAt(n.x, n.y, 400);
                          graphRef.current.zoom(2.5, 400);
                        }
                      }
                    }}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                      padding: "6px 10px",
                      background: "#f1f5f9",
                      border: "1px solid #cbd5e1",
                      borderRadius: 6,
                      fontSize: 11,
                      cursor: "pointer",
                      color: "#334155",
                    }}
                    title="Center and focus in graph"
                  >
                    <Focus size={12} /> Focus
                  </button>
                </div>
              </>
            ) : (
              <div style={{ textAlign: "center", padding: "16px 0", color: "#64748b" }}>
                <BookOpen size={24} color="#94a3b8" style={{ margin: "0 auto 8px" }} />
                <p style={{ fontSize: 12, margin: 0 }}>Click any node in the graph to inspect details.</p>
              </div>
            )}
          </div>

          {/* Card 3: Related Topics / Connected Papers */}
          <div
            style={{
              background: "white",
              border: "1px solid #e2e8f0",
              borderRadius: 8,
              padding: "14px 16px",
              boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
              flex: 1,
              minHeight: 180,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <BarChart3 size={15} color="#8b5cf6" />
                <h3 style={{ fontSize: 13, fontWeight: 600, color: "#0f172a", margin: 0 }}>Connected Papers</h3>
              </div>
              <span style={{ fontSize: 11, color: "#64748b" }}>{connectedNeighbors.length} relations</span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8, overflowY: "auto", flex: 1 }}>
              {connectedNeighbors.map(({ node, relationType, score }) => {
                const pct = Math.round(Math.min(100, Math.max(10, score * 100)));
                const isCitation = relationType === "cites";
                return (
                  <button
                    key={node.id}
                    onClick={() => {
                      setSelectedNode(node);
                      const targetNode: any = filteredData.nodes.find((item) => item.id === node.id);
                      if (targetNode && typeof targetNode.x === "number") {
                        graphRef.current?.centerAt(targetNode.x, targetNode.y, 400);
                      }
                    }}
                    style={{
                      background: "#f8fafc",
                      border: "1px solid #e2e8f0",
                      borderRadius: 6,
                      padding: "8px 10px",
                      cursor: "pointer",
                      textAlign: "left",
                      display: "flex",
                      flexDirection: "column",
                      gap: 4,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 600,
                          color: "#0f172a",
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          flex: 1,
                        }}
                      >
                        {node.title}
                      </span>
                      <span
                        style={{
                          fontSize: 9,
                          fontWeight: 600,
                          padding: "1px 5px",
                          borderRadius: 4,
                          background: isCitation ? "#ccfbf1" : "#f3e8ff",
                          color: isCitation ? "#0f766e" : "#7c3aed",
                          flexShrink: 0,
                        }}
                      >
                        {isCitation ? "Citation" : "Similarity"}
                      </span>
                    </div>

                    {/* Score Bar */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 2 }}>
                      <div
                        style={{
                          flex: 1,
                          height: 4,
                          background: "#e2e8f0",
                          borderRadius: 2,
                          overflow: "hidden",
                        }}
                      >
                        <div
                          style={{
                            width: `${pct}%`,
                            height: "100%",
                            background: isCitation ? "#0f766e" : "#8b5cf6",
                            borderRadius: 2,
                          }}
                        />
                      </div>
                      <span style={{ fontSize: 10, color: "#64748b", fontWeight: 600, minWidth: 26, textAlign: "right" }}>
                        {score.toFixed(2)}
                      </span>
                    </div>
                  </button>
                );
              })}

              {connectedNeighbors.length === 0 && (
                <div style={{ fontSize: 11, color: "#94a3b8", textAlign: "center", padding: "16px 0" }}>
                  {selectedNode ? "No direct citation or similarity links for this paper." : "Select a paper to view connections."}
                </div>
              )}
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}
