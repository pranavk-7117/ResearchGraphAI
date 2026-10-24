import ForceGraph2D from "react-force-graph-2d";
import { Filter, Focus, Layers, Network, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, Cluster, GraphData, GraphEdge, GraphNode, Project } from "../lib/api";

const clusterPalette = ["#2563eb", "#059669", "#7c3aed", "#d97706", "#db2777", "#475569"];

function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState({ width: 900, height: 600 });

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
      nodes = nodes.filter((n) => n.title.toLowerCase().includes(q) || n.authors_str.toLowerCase().includes(q));
    }

    const nodeIds = new Set(nodes.map((n) => n.id));
    const edges = graphData.edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));

    return {
      nodes: nodes.map((n) => ({ ...n, name: n.title })),
      links: edges.map((e) => ({
        ...e,
        source: e.source,
        target: e.target,
      })),
    };
  }, [graphData, selectedClusterId, searchQuery]);

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
    <section className="page graphPage" style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 40px)" }}>
      {/* Top Filter Bar */}
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 20, margin: "0 0 4px", color: "#0f172a" }}>
            Knowledge Graph · "{project.topic}"
          </h1>
          <p style={{ fontSize: 12, color: "#64748b", margin: 0 }}>
            {graphData.total_nodes} nodes · {graphData.total_edges} relations · Solid lines: verified citations · Dashed lines: inferred semantic similarity
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {/* Cluster filter */}
          {clusters.length > 0 && (
            <select
              value={selectedClusterId ?? ""}
              onChange={(e) => setSelectedClusterId(e.target.value ? Number(e.target.value) : null)}
              style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 12 }}
            >
              <option value="">All Thematic Clusters ({clusters.length})</option>
              {clusters.map((c, idx) => (
                <option key={c.id} value={c.id}>
                  {c.label} ({c.member_count} papers)
                </option>
              ))}
            </select>
          )}

          {/* Search */}
          <div style={{ position: "relative" }}>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search papers in graph..."
              style={{ padding: "6px 10px 6px 28px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 12, width: 200 }}
            />
            <Search size={14} color="#94a3b8" style={{ position: "absolute", left: 8, top: 9 }} />
          </div>

          <button
            onClick={() => graphRef.current?.zoomToFit(400, 30)}
            style={{ padding: "6px 12px", background: "#f1f5f9", border: "1px solid #cbd5e1", borderRadius: 6, fontSize: 12, cursor: "pointer" }}
            title="Recenter Graph"
          >
            <Focus size={14} />
          </button>
        </div>
      </header>

      {error && (
        <div style={{ padding: 12, background: "#fee2e2", color: "#991b1b", borderRadius: 6, marginBottom: 12 }}>
          {error}
        </div>
      )}

      {/* Main Canvas + Drawer Layout */}
      <div style={{ flex: 1, position: "relative", border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden", background: "#f8fafc" }}>
        <div ref={canvasRef} style={{ width: "100%", height: "100%" }}>
          <ForceGraph2D
            ref={graphRef}
            width={size.width}
            height={size.height}
            graphData={filteredData}
            nodeId="id"
            nodeLabel={(node: any) => `${node.title}\n(${node.year || "n.d."})`}
            nodeColor={(node: any) => {
              if (node.cluster_id !== null && clusters.length > 0) {
                const clusterIdx = clusters.findIndex((c) => c.id === node.cluster_id);
                return clusterPalette[clusterIdx % clusterPalette.length] || "#2563eb";
              }
              return "#2563eb";
            }}
            nodeVal={(node: any) => Math.max(4, Math.min(14, 4 + Math.log2(node.citation_count + 1)))}
            linkColor={(link: any) => (link.relation_type === "cites" ? "#0f766e" : "#8b5cf6")}
            linkWidth={(link: any) => (link.relation_type === "cites" ? 2 : 1)}
            linkLineDash={(link: any) => (link.relation_type === "cites" ? undefined : [4, 4])}
            linkDirectionalArrowLength={(link: any) => (link.relation_type === "cites" ? 6 : 0)}
            linkDirectionalArrowRelPos={0.8}
            onNodeClick={(node: any) => setSelectedNode(node)}
          />
        </div>

        {/* Legend */}
        <div
          style={{
            position: "absolute",
            bottom: 14,
            left: 14,
            background: "rgba(255, 255, 255, 0.92)",
            padding: "8px 14px",
            borderRadius: 6,
            border: "1px solid #cbd5e1",
            fontSize: 11,
            display: "flex",
            gap: 16,
            alignItems: "center",
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 14, height: 2, background: "#0f766e", display: "inline-block" }} />
            Verified Citation (Metadata)
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 14, height: 2, borderTop: "2px dashed #8b5cf6", display: "inline-block" }} />
            Inferred Semantic Similarity
          </span>
        </div>

        {/* Node Detail Drawer */}
        {selectedNode && (
          <aside
            style={{
              position: "absolute",
              top: 0,
              right: 0,
              width: 360,
              height: "100%",
              background: "white",
              borderLeft: "1px solid #e2e8f0",
              boxShadow: "-4px 0 16px rgba(0,0,0,0.06)",
              padding: 20,
              overflowY: "auto",
              zIndex: 10,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  padding: "2px 8px",
                  borderRadius: 10,
                  background: selectedNode.abstract_only ? "#f1f5f9" : "#dcfce7",
                  color: selectedNode.abstract_only ? "#64748b" : "#166534",
                }}
              >
                {selectedNode.abstract_only ? "Abstract-Level" : "Full-Text Indexed"}
              </span>
              <button
                onClick={() => setSelectedNode(null)}
                style={{ background: "none", border: "none", cursor: "pointer", color: "#64748b" }}
              >
                <X size={18} />
              </button>
            </div>

            <h3 style={{ fontSize: 16, fontWeight: 600, color: "#0f172a", margin: "0 0 6px" }}>
              {selectedNode.title}
            </h3>

            <div style={{ fontSize: 12, color: "#475569", marginBottom: 12 }}>
              {selectedNode.authors_str || "Authors indexed"} · {selectedNode.year || "n.d."}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 16 }}>
              <div style={{ background: "#f8fafc", padding: "8px 12px", borderRadius: 6, border: "1px solid #e2e8f0" }}>
                <span style={{ fontSize: 11, color: "#64748b" }}>Citations</span>
                <div style={{ fontSize: 16, fontWeight: 700, color: "#0f172a" }}>{selectedNode.citation_count}</div>
              </div>
              <div style={{ background: "#f8fafc", padding: "8px 12px", borderRadius: 6, border: "1px solid #e2e8f0" }}>
                <span style={{ fontSize: 11, color: "#64748b" }}>Paper ID</span>
                <div style={{ fontSize: 16, fontWeight: 700, color: "#0f172a" }}>#{selectedNode.id}</div>
              </div>
            </div>

            {/* Thematic Cluster */}
            {selectedNode.cluster_id !== null && (
              <div style={{ marginBottom: 16 }}>
                <strong style={{ fontSize: 12, color: "#334155", display: "block", marginBottom: 4 }}>Thematic Theme:</strong>
                <span style={{ fontSize: 12, color: "#2563eb", background: "#eff6ff", padding: "3px 8px", borderRadius: 4 }}>
                  {clusters.find((c) => c.id === selectedNode.cluster_id)?.label || `Cluster #${selectedNode.cluster_id}`}
                </span>
              </div>
            )}
          </aside>
        )}
      </div>
    </section>
  );
}
