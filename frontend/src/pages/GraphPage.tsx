import ForceGraph2D from "react-force-graph-2d";
import { Check, Filter, Focus, Pencil, Route, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, Edge, Paper, PaperUpdate } from "../lib/api";

type EdgeType = "citation" | "similarity" | "semantic_relation";
type GraphNode = Paper & { name: string; x: number; y: number };
type ExplainPathRow = {
  from_title: string;
  to_title: string;
  edge_type: string;
  label: string | null;
  confidence: number;
};

const edgeColors: Record<EdgeType, string> = {
  citation: "#0f766e",
  similarity: "#6d5dfc",
  semantic_relation: "#d97706",
};

const clusterColors = ["#2364aa", "#0f766e", "#8b5cf6", "#d97706", "#c2410c", "#64748b"];

function shortenTitle(title: string, max = 26) {
  return title.length > max ? `${title.slice(0, max - 1)}...` : title;
}

function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState({ width: 900, height: 640 });

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

export function GraphPage({ papers, onChanged }: { papers: Paper[]; onChanged: () => void }) {
  const graphRef = useRef<any>(null);
  const { ref: canvasRef, size } = useElementSize<HTMLDivElement>();
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selected, setSelected] = useState<Paper | null>(null);
  const [target, setTarget] = useState("");
  const [explanation, setExplanation] = useState("");
  const [pathRows, setPathRows] = useState<ExplainPathRow[]>([]);
  const [related, setRelated] = useState<Paper[]>([]);
  const [hops, setHops] = useState(2);
  const [mode, setMode] = useState<"bfs" | "dfs">("bfs");
  const [query, setQuery] = useState("");
  const [showLabels, setShowLabels] = useState(false);
  const [hoveredId, setHoveredId] = useState<number | null>(null);
  const [activeTypes, setActiveTypes] = useState<Record<EdgeType, boolean>>({
    citation: true,
    similarity: true,
    semantic_relation: true,
  });
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<PaperUpdate | null>(null);

  useEffect(() => {
    api.graph().then((data) => setEdges(data.edges));
  }, [papers.length]);

  useEffect(() => {
    if (!selected) return;
    setDraft({
      title: selected.title,
      authors: selected.authors,
      abstract: selected.abstract,
      year: selected.year,
      source_type: selected.source_type,
    });
  }, [selected]);

  const visiblePapers = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return papers;
    return papers.filter((paper) =>
      `${paper.title} ${paper.authors} ${paper.abstract}`.toLowerCase().includes(normalized),
    );
  }, [papers, query]);

  const visiblePaperIds = useMemo(() => new Set(visiblePapers.map((paper) => paper.id)), [visiblePapers]);

  const visibleEdges = useMemo(
    () =>
      edges.filter(
        (edge) =>
          activeTypes[edge.edge_type as EdgeType] &&
          visiblePaperIds.has(edge.source_paper_id) &&
          visiblePaperIds.has(edge.target_paper_id),
      ),
    [activeTypes, edges, visiblePaperIds],
  );

  const clusterInfo = useMemo(() => {
    const neighbors = new Map<number, Set<number>>();
    visiblePapers.forEach((paper) => neighbors.set(paper.id, new Set()));
    visibleEdges.forEach((edge) => {
      neighbors.get(edge.source_paper_id)?.add(edge.target_paper_id);
      neighbors.get(edge.target_paper_id)?.add(edge.source_paper_id);
    });

    const componentByPaper = new Map<number, number>();
    const summaries: { id: number; color: string; paperIds: number[] }[] = [];
    const seen = new Set<number>();
    visiblePapers.forEach((paper) => {
      if (seen.has(paper.id)) return;
      const stack = [paper.id];
      const paperIds: number[] = [];
      seen.add(paper.id);
      while (stack.length) {
        const current = stack.pop()!;
        paperIds.push(current);
        neighbors.get(current)?.forEach((next) => {
          if (!seen.has(next)) {
            seen.add(next);
            stack.push(next);
          }
        });
      }
      const id = summaries.length;
      const color = clusterColors[id % clusterColors.length];
      paperIds.forEach((paperId) => componentByPaper.set(paperId, id));
      summaries.push({ id, color, paperIds });
    });
    return { componentByPaper, summaries };
  }, [visibleEdges, visiblePapers]);

  const data = useMemo(
    () => ({
      nodes: visiblePapers.map((paper) => ({ ...paper, name: paper.title })),
      links: visibleEdges.map((edge) => ({
        source: edge.source_paper_id,
        target: edge.target_paper_id,
        label: edge.relation_label ?? edge.edge_type,
        edgeType: edge.edge_type,
        confidence: edge.confidence,
      })),
    }),
    [visiblePapers, visibleEdges],
  );

  const selectedEdges = useMemo(
    () =>
      selected
        ? edges.filter((edge) => edge.source_paper_id === selected.id || edge.target_paper_id === selected.id)
        : [],
    [edges, selected],
  );

  const connectedIds = useMemo(() => {
    const ids = new Set<number>();
    if (!selected) return ids;
    ids.add(selected.id);
    selectedEdges.forEach((edge) => {
      ids.add(edge.source_paper_id);
      ids.add(edge.target_paper_id);
    });
    return ids;
  }, [selected, selectedEdges]);

  useEffect(() => {
    if (!graphRef.current || visiblePapers.length === 0) return;
    const timer = window.setTimeout(() => graphRef.current?.zoomToFit(500, 80), 500);
    return () => window.clearTimeout(timer);
  }, [visiblePapers.length, visibleEdges.length, size.width, size.height]);

  async function explain() {
    if (!selected || !target) return;
    const result = await api.explain(selected.id, Number(target));
    setPathRows(result.path);
    setExplanation(result.explanation || "No directed path found between those papers.");
  }

  async function loadRelated(nextMode = mode, nextHops = hops) {
    if (!selected) return;
    const result = await api.related(selected.id, nextHops, nextMode);
    setRelated(result);
  }

  async function savePaper() {
    if (!selected || !draft) return;
    const saved = await api.updatePaper(selected.id, draft);
    setSelected(saved);
    setEditing(false);
    onChanged();
  }

  function toggleEdge(type: EdgeType) {
    setActiveTypes((value) => ({ ...value, [type]: !value[type] }));
  }

  return (
    <section className="graphWorkspace">
      <header className="workspaceTopbar">
        <div>
          <h1>Research Graph</h1>
          <p>{visiblePapers.length} papers, {visibleEdges.length} visible edges, {clusterInfo.summaries.length} clusters</p>
        </div>
        <div className="toolbar">
          <label className="searchBox">
            <Search size={16} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search papers" />
          </label>
          <button className="toolButton" onClick={() => graphRef.current?.zoomToFit(500, 80)} title="Fit graph">
            <Focus size={16} />
            <span>Fit</span>
          </button>
          <button className={showLabels ? "toolButton active" : "toolButton"} onClick={() => setShowLabels(!showLabels)} title="Toggle labels">
            <Filter size={16} />
            <span>Labels</span>
          </button>
        </div>
      </header>

      <div className="graphLayout">
        <div className="graphPanel">
          <div className="graphControls">
            {(Object.keys(edgeColors) as EdgeType[]).map((type) => (
              <button
                className={activeTypes[type] ? "edgeToggle active" : "edgeToggle"}
                key={type}
                onClick={() => toggleEdge(type)}
              >
                <i style={{ background: edgeColors[type] }} />
                {type === "semantic_relation" ? "extends" : type}
              </button>
            ))}
          </div>
          <div className="graphCanvas" ref={canvasRef}>
            <ForceGraph2D
              ref={graphRef}
              width={size.width}
              height={size.height}
              graphData={data}
              backgroundColor="#ffffff"
              cooldownTicks={180}
              d3AlphaDecay={0.018}
              d3VelocityDecay={0.34}
              nodeLabel="name"
              nodeRelSize={4}
              linkLabel="label"
              linkWidth={(link: any) => 0.8 + Number(link.confidence ?? 0.5)}
              linkDirectionalArrowLength={3.4}
              linkDirectionalArrowRelPos={1}
              linkCurvature={0.06}
              enableNodeDrag
              nodeCanvasObject={(node: any, ctx, scale) => {
                const graphNode = node as GraphNode;
                const isSelected = selected?.id === graphNode.id;
                const connected = connectedIds.has(graphNode.id);
                const isHovered = hoveredId === graphNode.id;
                const radius = isSelected ? 7.5 : connected || isHovered ? 6.2 : 4.8;
                ctx.globalAlpha = selected && !connected ? 0.42 : 1;
                const clusterId = clusterInfo.componentByPaper.get(graphNode.id) ?? 0;
                const clusterColor = clusterColors[clusterId % clusterColors.length];
                ctx.fillStyle = isSelected ? "#f97316" : connected ? "#1849a9" : clusterColor;
                ctx.beginPath();
                ctx.arc(graphNode.x, graphNode.y, radius, 0, 2 * Math.PI);
                ctx.fill();
                ctx.strokeStyle = "#ffffff";
                ctx.lineWidth = 1.6 / scale;
                ctx.stroke();
                ctx.globalAlpha = 1;

                const shouldLabel =
                  isSelected ||
                  isHovered ||
                  (showLabels && (visiblePapers.length <= 18 || connected || scale > 1.35));
                if (!shouldLabel) return;
                const label = shortenTitle(graphNode.name);
                const fontSize = Math.min(6.8, Math.max(4.8, 5.8 / scale));
                ctx.font = `600 ${fontSize}px Inter, sans-serif`;
                const textWidth = ctx.measureText(label).width;
                const x = graphNode.x + radius + 3.5;
                const y = graphNode.y - fontSize / 2 - 3;
                ctx.fillStyle = "rgba(255, 255, 255, 0.86)";
                ctx.strokeStyle = "rgba(208, 213, 221, 0.9)";
                ctx.lineWidth = 0.55 / scale;
                ctx.beginPath();
                ctx.roundRect(x - 3, y - 1.5, textWidth + 6, fontSize + 4, 3);
                ctx.fill();
                ctx.stroke();
                ctx.fillStyle = "#182230";
                ctx.fillText(label, x, y + fontSize);
              }}
              linkColor={(link: any) => edgeColors[link.edgeType as EdgeType] ?? "#98a2b3"}
              onNodeHover={(node: any) => setHoveredId(node?.id ?? null)}
              onNodeClick={(node: any) => {
                const paper = papers.find((item) => item.id === node.id) ?? null;
                setSelected(paper);
                setRelated([]);
                setExplanation("");
                setPathRows([]);
              }}
            />
          </div>
        </div>

        <aside className="inspector">
          <div className="inspectorHeader">
            <div>
              <h2>{selected ? "Paper Details" : "Graph Tools"}</h2>
              <p>{selected ? selected.title : "Search, filter, select a paper, then inspect paths and neighborhoods."}</p>
            </div>
            {selected && (
              <button className="iconButton subtle" onClick={() => setEditing(!editing)} title="Edit paper">
                <Pencil size={16} />
              </button>
            )}
          </div>

          {!selected && (
            <>
              <div className="legend">
                <span><i className="citation" /> citation</span>
                <span><i className="similarity" /> similarity</span>
                <span><i className="semantic" /> extends</span>
              </div>
              <div className="clusterList">
                {clusterInfo.summaries.map((cluster) => (
                  <button
                    key={cluster.id}
                    onClick={() => {
                      const first = papers.find((paper) => paper.id === cluster.paperIds[0]);
                      if (first) setSelected(first);
                    }}
                  >
                    <i style={{ background: cluster.color }} />
                    <span>Cluster {cluster.id + 1}</span>
                    <strong>{cluster.paperIds.length} papers</strong>
                  </button>
                ))}
              </div>
              <div className="paperMiniList">
                {visiblePapers.map((paper) => (
                  <button key={paper.id} onClick={() => setSelected(paper)}>
                    <strong>{paper.title}</strong>
                    <span>{paper.year ?? "No year"} - {paper.source_type}</span>
                  </button>
                ))}
              </div>
            </>
          )}

          {selected && draft && (
            <>
              {editing ? (
                <div className="editForm">
                  <label>Title<input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
                  <label>Authors<input value={draft.authors} onChange={(event) => setDraft({ ...draft, authors: event.target.value })} /></label>
                  <label>Year<input type="number" value={draft.year ?? ""} onChange={(event) => setDraft({ ...draft, year: event.target.value ? Number(event.target.value) : null })} /></label>
                  <label>Abstract<textarea value={draft.abstract} onChange={(event) => setDraft({ ...draft, abstract: event.target.value })} /></label>
                  <button className="primary" onClick={savePaper}><Check size={16} /> Save paper</button>
                </div>
              ) : (
                <>
                  <div className="meta">
                    <span>{selected.year ?? "No year"}</span>
                    <span>{selected.source_type}</span>
                    <span>{selectedEdges.length} edges</span>
                  </div>
                  <p className="authors">{selected.authors}</p>
                  <p className="abstract">{selected.abstract}</p>
                </>
              )}

              <div className="toolSection">
                <h3>Related Papers</h3>
                <div className="miniControls">
                  <select value={mode} onChange={(event) => setMode(event.target.value as "bfs" | "dfs")}>
                    <option value="bfs">BFS by hops</option>
                    <option value="dfs">DFS component</option>
                  </select>
                  <input type="number" min={1} max={5} value={hops} onChange={(event) => setHops(Number(event.target.value))} />
                  <button className="secondary" onClick={() => loadRelated()}>Find</button>
                </div>
                <div className="resultList">
                  {related.map((paper) => <button key={paper.id} onClick={() => setSelected(paper)}>{paper.title}</button>)}
                </div>
              </div>

              <div className="toolSection">
                <h3>Explain Connection</h3>
                <select value={target} onChange={(event) => setTarget(event.target.value)}>
                  <option value="">Choose target paper...</option>
                  {papers.filter((paper) => paper.id !== selected.id).map((paper) => (
                    <option key={paper.id} value={paper.id}>{paper.title}</option>
                  ))}
                </select>
                <button className="primary" onClick={explain}><Route size={16} /> Explain path</button>
                {pathRows.length > 0 && (
                  <div className="pathList">
                    {pathRows.map((row, index) => (
                      <div key={`${row.from_title}-${row.to_title}-${index}`}>
                        <strong>{row.label ?? row.edge_type}</strong>
                        <span>{row.from_title} {"->"} {row.to_title}</span>
                      </div>
                    ))}
                  </div>
                )}
                {explanation && <div className="note">{explanation}</div>}
              </div>

              <div className="toolSection">
                <h3>Edges</h3>
                <div className="edgeList">
                  {selectedEdges.map((edge) => {
                    const otherId = edge.source_paper_id === selected.id ? edge.target_paper_id : edge.source_paper_id;
                    const other = papers.find((paper) => paper.id === otherId);
                    return (
                      <button key={edge.id} onClick={() => other && setSelected(other)}>
                        <strong>{edge.relation_label ?? edge.edge_type}</strong>
                        <span>{other?.title ?? `Paper ${otherId}`}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </aside>
      </div>
    </section>
  );
}
