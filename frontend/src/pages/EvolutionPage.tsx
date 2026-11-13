import {
  Activity,
  ArrowRight,
  BarChart3,
  BookOpen,
  Calendar,
  CheckCircle2,
  ChevronRight,
  Cpu,
  ExternalLink,
  FileText,
  Filter,
  GitBranch,
  GitFork,
  GitMerge,
  Layers,
  Lightbulb,
  Maximize2,
  Minimize2,
  Network,
  Quote,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  AnnualMilestone,
  api,
  Cluster,
  EvolutionData,
  EvolutionPhase,
  EvolutionTransitionItem,
  Project,
  StreamPaperItem,
} from "../lib/api";

type TabView = "timeline" | "thematic" | "methods" | "findings";

export function EvolutionPage({ project }: { project: Project | null }) {
  const [activeTab, setActiveTab] = useState<TabView>("timeline");
  const [data, setData] = useState<EvolutionData>({
    citation_timeline: [],
    method_progression: [],
    finding_dynamics: [],
  });
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // View state
  const [selectedPhaseView, setSelectedPhaseView] = useState<"Research Phases" | "Annual Milestones" | "Paper Lineage Stream">("Research Phases");
  const [groupByPhase, setGroupByPhase] = useState(true);

  // Transitions filter state
  const [showTransitionFilter, setShowTransitionFilter] = useState(false);
  const [transitionPhaseFilter, setTransitionPhaseFilter] = useState<string>("all");
  const [transitionSearchQuery, setTransitionSearchQuery] = useState("");

  // Paper inspection modal state
  const [inspectingPapers, setInspectingPapers] = useState<StreamPaperItem[] | null>(null);
  const [inspectingTitle, setInspectingTitle] = useState("");

  // Paper Lineage Stream (Image 3) filter state
  const [streamYearFilter, setStreamYearFilter] = useState<string>("all");
  const [streamTopicFilter, setStreamTopicFilter] = useState<string>("all");
  const [streamSearchQuery, setStreamSearchQuery] = useState("");

  // Facts coverage state (Task E8)
  const [coverage, setCoverage] = useState<{
    total_papers: number;
    extracted_count: number;
    not_stated_count: number;
    source_limited_count: number;
    failed_count: number;
    coverage_percent: number;
  } | null>(null);
  const [showCoverageDetails, setShowCoverageDetails] = useState(false);
  const [reextracting, setReextracting] = useState(false);

  useEffect(() => {
    if (project) {
      loadEvolution();
    }
  }, [project?.id]);

  async function loadEvolution() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const [evoData, cData, covData] = await Promise.all([
        api.evolution.get(project.id),
        api.clusters.get(project.id),
        api.facts.coverage(project.id).catch(() => null),
      ]);
      setData(evoData);
      setClusters(cData);
      if (covData) setCoverage(covData);
    } catch (err: any) {
      setError(err?.message || "Failed to load literature evolution.");
    } finally {
      setLoading(false);
    }
  }

  async function handleReextract() {
    if (!project || reextracting) return;
    setReextracting(true);
    try {
      await api.facts.reextract(project.id, true);
      await loadEvolution();
    } catch (err: any) {
      setError(err?.message || "Re-extraction failed.");
    } finally {
      setReextracting(false);
    }
  }

  const topic = project?.topic || "Research Topic";
  const totalPapers = data.total_papers ?? project?.paper_count ?? 0;

  const timeRange = useMemo(() => {
    if (data.time_range && data.time_range.min_year) {
      return data.time_range;
    }
    return { min_year: 0, max_year: 0 };
  }, [data.time_range]);

  // Phases returned directly from backend data (no synthetic fallbacks)
  const phases: EvolutionPhase[] = useMemo(() => {
    return data.phases || [];
  }, [data.phases]);

  // Transitions returned directly from backend data
  const transitions: EvolutionTransitionItem[] = useMemo(() => {
    return data.transitions || [];
  }, [data.transitions]);

  // Filtered transitions
  const filteredTransitions = useMemo(() => {
    return transitions.filter((item) => {
      if (transitionPhaseFilter !== "all") {
        const pNum = Number(transitionPhaseFilter);
        if (item.phase_from !== pNum && item.phase_to !== pNum && !(pNum === 4 && item.badge?.includes("Recent"))) {
          return false;
        }
      }
      if (transitionSearchQuery.trim()) {
        const q = transitionSearchQuery.toLowerCase();
        const matchesTitle = item.title.toLowerCase().includes(q);
        const matchesDesc = (item.description || "").toLowerCase().includes(q);
        const matchesChanges = item.key_changes.some((k) => k.toLowerCase().includes(q));
        if (!matchesTitle && !matchesDesc && !matchesChanges) return false;
      }
      return true;
    });
  }, [transitions, transitionPhaseFilter, transitionSearchQuery]);

  // Focus Trends series using actual project clusters
  const focusTrends = useMemo(() => {
    if (data.focus_trends && data.focus_trends.series && data.focus_trends.series.length > 0) {
      return data.focus_trends;
    }
    return { years: [], series: [] };
  }, [data.focus_trends]);

  // Annual Milestones
  const annualMilestones: AnnualMilestone[] = useMemo(() => {
    return data.annual_milestones || [];
  }, [data.annual_milestones]);

  // Paper Stream Lineage
  const paperStream: StreamPaperItem[] = useMemo(() => {
    return data.paper_stream || [];
  }, [data.paper_stream]);

  // Filtered Paper Stream
  const filteredPaperStream = useMemo(() => {
    return paperStream.filter((p) => {
      if (streamYearFilter !== "all") {
        const [startY, endY] = streamYearFilter.split("-").map(Number);
        if (p.year && (p.year < startY || p.year > endY)) return false;
      }
      if (streamTopicFilter !== "all") {
        if (p.topic_tag !== streamTopicFilter) return false;
      }
      if (streamSearchQuery.trim()) {
        const q = streamSearchQuery.toLowerCase();
        const mTitle = p.title.toLowerCase().includes(q);
        const mAuthors = (p.authors_str || "").toLowerCase().includes(q);
        const mAbstract = (p.abstract || "").toLowerCase().includes(q);
        const mContrib = (p.key_contribution || "").toLowerCase().includes(q);
        if (!mTitle && !mAuthors && !mAbstract && !mContrib) return false;
      }
      return true;
    });
  }, [paperStream, streamYearFilter, streamTopicFilter, streamSearchQuery]);

  const keyInsights = useMemo(() => {
    return data.key_insights || [];
  }, [data.key_insights]);

  if (!project) {
    return (
      <section className="page" style={{ maxWidth: 800, margin: "40px auto", textAlign: "center" }}>
        <GitFork size={48} color="#94a3b8" style={{ margin: "0 auto 16px" }} />
        <h2>No Active Research Project</h2>
        <p style={{ color: "#64748b" }}>Please select a research project to view literature evolution.</p>
      </section>
    );
  }

  // Phase color & icon mapping
  const phaseStyles = [
    { border: "#3b82f6", fill: "#eff6ff", text: "#2563eb", icon: BookOpen, badge: "#dbeafe", badgeText: "#1e40af" },
    { border: "#10b981", fill: "#ecfdf5", text: "#059669", icon: Cpu, badge: "#d1fae5", badgeText: "#065f46" },
    { border: "#f59e0b", fill: "#fffbeb", text: "#d97706", icon: Sparkles, badge: "#fef3c7", badgeText: "#92400e" },
    { border: "#ef4444", fill: "#fef2f2", text: "#dc2626", icon: Activity, badge: "#fee2e2", badgeText: "#991b1b" },
  ];

  return (
    <section className="page evolutionPage" style={{ maxWidth: 1240, margin: "0 auto", paddingBottom: 60 }}>
      {/* Top Breadcrumb & Header */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "#64748b", marginBottom: 6 }}>
          <span>&lt; Back to Project</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: "#0f172a", margin: "0 0 4px" }}>
              Literature Evolution: "{project.topic}"
            </h1>
            <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>
              Visualizing how research methods, evidence and findings have evolved over time.
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", position: "relative" }}>
            {coverage && (
              <div style={{ position: "relative" }}>
                <button
                  type="button"
                  onClick={() => setShowCoverageDetails((prev) => !prev)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    padding: "6px 12px",
                    background: coverage.coverage_percent >= 80 ? "#ecfdf5" : "#fffbeb",
                    border: `1px solid ${coverage.coverage_percent >= 80 ? "#a7f3d0" : "#fde68a"}`,
                    borderRadius: 6,
                    fontSize: 12,
                    fontWeight: 600,
                    color: coverage.coverage_percent >= 80 ? "#065f46" : "#92400e",
                    cursor: "pointer",
                  }}
                  title="Click to view extraction status breakdown"
                >
                  <Sparkles size={13} />
                  Facts Coverage: {coverage.coverage_percent}% ({coverage.extracted_count}/{coverage.total_papers})
                </button>

                {showCoverageDetails && (
                  <div
                    style={{
                      position: "absolute",
                      right: 0,
                      top: "100%",
                      marginTop: 6,
                      background: "white",
                      border: "1px solid #cbd5e1",
                      borderRadius: 8,
                      boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.1)",
                      padding: 12,
                      width: 260,
                      zIndex: 30,
                      fontSize: 12,
                    }}
                  >
                    <div style={{ fontWeight: 700, color: "#0f172a", marginBottom: 8, display: "flex", justifyContent: "space-between" }}>
                      <span>Extraction Status Breakdown</span>
                      <button
                        type="button"
                        onClick={() => setShowCoverageDetails(false)}
                        style={{ border: "none", background: "none", cursor: "pointer", color: "#94a3b8" }}
                      >
                        <X size={13} />
                      </button>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6, color: "#334155" }}>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span>Extracted:</span>
                        <strong style={{ color: "#059669" }}>{coverage.extracted_count}</strong>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span>Source Limited (abstract only):</span>
                        <strong style={{ color: "#d97706" }}>{coverage.source_limited_count}</strong>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span>Not Stated in text:</span>
                        <strong style={{ color: "#64748b" }}>{coverage.not_stated_count}</strong>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span>Failed / Degraded:</span>
                        <strong style={{ color: "#dc2626" }}>{coverage.failed_count}</strong>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            <button
              onClick={handleReextract}
              disabled={reextracting || loading}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "7px 14px",
                background: "#f8fafc",
                border: "1px solid #cbd5e1",
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 500,
                cursor: (reextracting || loading) ? "not-allowed" : "pointer",
                color: "#334155",
              }}
              title="Re-extract facts for papers with missing or degraded facts"
            >
              <Sparkles size={13} className={reextracting ? "spin" : ""} />
              {reextracting ? "Re-extracting..." : "Re-extract missing"}
            </button>

            <button
              onClick={loadEvolution}
              disabled={loading}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "7px 14px",
                background: "white",
                border: "1px solid #cbd5e1",
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 500,
                cursor: "pointer",
                color: "#334155",
                boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
              }}
            >
              <RefreshCw size={13} className={loading ? "spin" : ""} /> Refresh Analysis
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div style={{ padding: 12, background: "#fee2e2", color: "#991b1b", borderRadius: 8, marginBottom: 16, fontSize: 12 }}>
          {error}
        </div>
      )}

      {/* Top 4 Metric Cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: 12,
          marginBottom: 20,
        }}
      >
        <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 10, padding: 16, display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ width: 42, height: 42, borderRadius: 8, background: "#eff6ff", display: "flex", alignItems: "center", justifyContent: "center", color: "#2563eb" }}>
            <FileText size={22} />
          </div>
          <div>
            <div style={{ fontSize: 24, fontWeight: 700, color: "#0f172a", lineHeight: 1.1 }}>{totalPapers}</div>
            <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>Papers Analyzed</div>
          </div>
        </div>

        <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 10, padding: 16, display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ width: 42, height: 42, borderRadius: 8, background: "#f5f3ff", display: "flex", alignItems: "center", justifyContent: "center", color: "#7c3aed" }}>
            <Layers size={22} />
          </div>
          <div>
            <div style={{ fontSize: 24, fontWeight: 700, color: "#0f172a", lineHeight: 1.1 }}>{phases.length}</div>
            <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>Research Phases</div>
          </div>
        </div>

        <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 10, padding: 16, display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ width: 42, height: 42, borderRadius: 8, background: "#faf5ff", display: "flex", alignItems: "center", justifyContent: "center", color: "#8b5cf6" }}>
            <GitBranch size={22} />
          </div>
          <div>
            <div style={{ fontSize: 24, fontWeight: 700, color: "#0f172a", lineHeight: 1.1 }}>{transitions.length}</div>
            <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>Key Transitions</div>
          </div>
        </div>

        <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 10, padding: 16, display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ width: 42, height: 42, borderRadius: 8, background: "#eff6ff", display: "flex", alignItems: "center", justifyContent: "center", color: "#0284c7" }}>
            <Calendar size={22} />
          </div>
          <div>
            <div style={{ fontSize: 20, fontWeight: 700, color: "#0f172a", lineHeight: 1.2 }}>
              {timeRange.min_year} – {timeRange.max_year}
            </div>
            <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>Time Range</div>
          </div>
        </div>
      </div>

      {/* Tab Switcher Pills */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
        {[
          { id: "timeline", label: "1. Research Timeline" },
          { id: "thematic", label: `2. Thematic Evolution (${clusters.length})` },
          { id: "methods", label: `3. Method & Metric Progression (${data.method_progression?.length || 0})` },
          { id: "findings", label: `4. Key Findings & Consensus (${data.finding_dynamics?.length || 0})` },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id as any)}
            style={{
              padding: "7px 18px",
              borderRadius: 6,
              border: "1px solid",
              fontSize: 13,
              fontWeight: activeTab === t.id ? 600 : 500,
              background: activeTab === t.id ? "#3b82f6" : "white",
              borderColor: activeTab === t.id ? "#2563eb" : "#e2e8f0",
              color: activeTab === t.id ? "white" : "#475569",
              cursor: "pointer",
              boxShadow: activeTab === t.id ? "0 1px 3px rgba(37,99,235,0.2)" : "0 1px 2px rgba(0,0,0,0.03)",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: RESEARCH TIMELINE                                                  */}
      {/* ========================================================================= */}
      {activeTab === "timeline" && (
        <div style={{ display: "grid", gridTemplateColumns: selectedPhaseView === "Paper Lineage Stream" ? "1fr" : "minmax(0, 1fr) 340px", gap: 20, alignItems: "start" }}>
          {/* Main Timeline Column */}
          <div style={{ display: "flex", flexDirection: "column", gap: 20, minWidth: 0 }}>
            {/* Citation Backbone (SPC Main-Path Analysis) */}
            {data.citation_backbone && (
              <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 10, padding: 18, boxShadow: "0 1px 3px rgba(0,0,0,0.03)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 30, height: 30, borderRadius: 8, background: "#eff6ff", display: "flex", alignItems: "center", justifyContent: "center", color: "#2563eb" }}>
                      <Network size={16} />
                    </div>
                    <div>
                      <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                        Citation Backbone (Search Path Count Main-Path Analysis)
                      </h3>
                      <p style={{ fontSize: 11, color: "#64748b", margin: 0 }}>
                        Chronological citation lineage scored by SPC ({data.citation_backbone.edge_count} citation edge(s), total source-to-sink paths: {data.citation_backbone.total_paths})
                      </p>
                    </div>
                  </div>
                  {data.citation_backbone.total_spc > 0 && (
                    <span style={{ fontSize: 11, fontWeight: 600, background: "#eff6ff", color: "#1d4ed8", padding: "3px 9px", borderRadius: 12 }}>
                      Total Path SPC: {data.citation_backbone.total_spc}
                    </span>
                  )}
                </div>

                {data.citation_backbone.is_sparse && (
                  <div style={{ background: "#fffbeb", border: "1px solid #fde68a", color: "#92400e", borderRadius: 8, padding: "10px 12px", fontSize: 12, marginBottom: data.citation_backbone.global_path.length > 0 ? 12 : 0 }}>
                    <strong>Sparse citation graph:</strong> {data.citation_backbone.message}
                  </div>
                )}

                {data.citation_backbone.global_path.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 12 }}>
                    {data.citation_backbone.global_path.map((node, idx) => {
                      const nextEdge = data.citation_backbone?.global_edges[idx];
                      return (
                        <div key={node.id} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <div style={{ background: "white", border: "1px solid #cbd5e1", borderRadius: 8, padding: "7px 10px", maxWidth: 210 }}>
                            <div style={{ fontSize: 10, fontWeight: 700, color: "#2563eb" }}>{node.year ?? "n.d."}</div>
                            <div style={{ fontSize: 11, fontWeight: 600, color: "#0f172a", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={node.title}>
                              {node.title}
                            </div>
                          </div>
                          {nextEdge && (
                            <div style={{ display: "flex", alignItems: "center", gap: 4, color: "#64748b", fontSize: 10, fontWeight: 600 }}>
                              <span style={{ background: "#e2e8f0", color: "#334155", padding: "2px 6px", borderRadius: 6 }}>
                                SPC {nextEdge.spc}
                              </span>
                              <ArrowRight size={14} />
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* Top Evolution Timeline Card */}
            <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 10, padding: 20, boxShadow: "0 1px 3px rgba(0,0,0,0.03)" }}>
              {/* Header with Working View Dropdown */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20, flexWrap: "wrap", gap: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{ width: 32, height: 32, borderRadius: 8, background: "#f1f5f9", display: "flex", alignItems: "center", justifyContent: "center", color: "#0f172a" }}>
                    <SlidersHorizontal size={18} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                      Evolution Timeline ({selectedPhaseView})
                    </h3>
                    <p style={{ fontSize: 12, color: "#64748b", margin: 0 }}>
                      Major shifts in methods, focus areas and findings in {project.topic.toLowerCase()} research
                    </p>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#64748b" }}>
                    <span>View:</span>
                    <select
                      value={selectedPhaseView}
                      onChange={(e) => setSelectedPhaseView(e.target.value as any)}
                      style={{ padding: "5px 10px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 12, background: "#f8fafc", cursor: "pointer", fontWeight: 600, color: "#0f172a" }}
                    >
                      <option value="Research Phases">Research Phases</option>
                      <option value="Annual Milestones">Annual Milestones</option>
                      <option value="Paper Lineage Stream">Paper Lineage Stream (Paper-by-Paper)</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* VIEW 1: Research Phases Ribbon */}
              {selectedPhaseView === "Research Phases" && (
                <div style={{ position: "relative", padding: "16px 12px 28px" }}>
                  <div
                    style={{
                      position: "absolute",
                      top: 36,
                      left: "8%",
                      right: "8%",
                      height: 4,
                      background: "linear-gradient(to right, #3b82f6 0%, #10b981 33%, #f59e0b 66%, #ef4444 100%)",
                      borderRadius: 2,
                      zIndex: 0,
                    }}
                  />
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, position: "relative", zIndex: 1 }}>
                    {phases.map((phase, idx) => {
                      const style = phaseStyles[idx % phaseStyles.length];
                      const IconComp = style.icon;
                      return (
                        <div
                          key={phase.phase_num}
                          onClick={() => {
                            if (phase.papers && phase.papers.length > 0) {
                              setInspectingPapers(phase.papers);
                              setInspectingTitle(`Phase ${phase.phase_num}: ${phase.title}`);
                            }
                          }}
                          style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", cursor: phase.papers ? "pointer" : "default" }}
                          title={phase.papers ? "Click to view papers in this phase" : undefined}
                        >
                          <div
                            style={{
                              width: 44,
                              height: 44,
                              borderRadius: "50%",
                              background: style.fill,
                              border: `3px solid ${style.border}`,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              color: style.text,
                              marginBottom: 10,
                              boxShadow: "0 2px 6px rgba(0,0,0,0.08)",
                            }}
                          >
                            <IconComp size={20} />
                          </div>
                          <div style={{ fontSize: 12, fontWeight: 700, color: "#0f172a" }}>Phase {phase.phase_num}</div>
                          <div style={{ fontSize: 11, color: "#64748b", marginBottom: 4 }}>
                            {phase.start_year} – {phase.end_year}
                          </div>
                          <div style={{ fontSize: 13, fontWeight: 700, color: style.text, marginBottom: 4 }}>
                            {phase.title}
                          </div>
                          <div style={{ fontSize: 11, color: "#475569", lineHeight: 1.4, maxWidth: 170 }}>
                            {phase.description}
                          </div>
                          <div style={{ fontSize: 11, color: "#2563eb", fontWeight: 600, marginTop: 6 }}>
                            {phase.paper_count} papers &gt;
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* VIEW 2: Annual Milestones Timeline */}
              {selectedPhaseView === "Annual Milestones" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 14, padding: "10px 4px", minWidth: 0 }}>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(145px, 1fr))", gap: 10, minWidth: 0 }}>
                    {annualMilestones.map((m) => (
                      <div
                        key={m.year}
                        onClick={() => {
                          if (m.papers && m.papers.length > 0) {
                            setInspectingPapers(m.papers);
                            setInspectingTitle(`Milestones of Year ${m.year}`);
                          }
                        }}
                        style={{
                          background: "#f8fafc",
                          border: "1px solid #e2e8f0",
                          borderRadius: 8,
                          padding: 12,
                          cursor: "pointer",
                          textAlign: "center",
                          minWidth: 0,
                          transition: "all 0.15s ease",
                        }}
                      >
                        <div style={{ fontSize: 14, fontWeight: 700, color: "#2563eb" }}>{m.year}</div>
                        <div style={{ fontSize: 11, fontWeight: 600, color: "#0f172a", marginTop: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={m.top_theme || m.milestone_title}>
                          {m.top_theme || m.milestone_title}
                        </div>
                        <div style={{ fontSize: 10, color: "#64748b", marginTop: 2 }}>{m.paper_count} {m.paper_count === 1 ? "paper" : "papers"}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* VIEW 3: Paper Lineage Stream (Image 3) */}
              {selectedPhaseView === "Paper Lineage Stream" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  {/* Image 3 Filter Toolbar */}
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", background: "#f8fafc", padding: "10px 14px", borderRadius: 8, border: "1px solid #e2e8f0" }}>
                    <select
                      value={streamYearFilter}
                      onChange={(e) => setStreamYearFilter(e.target.value)}
                      style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 12, background: "white" }}
                    >
                      <option value="all">All Years</option>
                      <option value="2015-2018">2015 – 2018</option>
                      <option value="2019-2021">2019 – 2021</option>
                      <option value="2022-2024">2022 – 2024</option>
                      <option value="2025-2026">2025 – 2026</option>
                    </select>

                    <select
                      value={streamTopicFilter}
                      onChange={(e) => setStreamTopicFilter(e.target.value)}
                      style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 12, background: "white" }}
                    >
                      <option value="all">All Topics ({clusters.length})</option>
                      {clusters.map((c) => (
                        <option key={c.id} value={c.label}>
                          {c.label}
                        </option>
                      ))}
                    </select>

                    <div style={{ position: "relative", flex: 1, minWidth: 200 }}>
                      <input
                        type="text"
                        value={streamSearchQuery}
                        onChange={(e) => setStreamSearchQuery(e.target.value)}
                        placeholder="Search papers in timeline..."
                        style={{ width: "100%", padding: "6px 10px 6px 30px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 12 }}
                      />
                      <Search size={14} color="#94a3b8" style={{ position: "absolute", left: 9, top: 9 }} />
                    </div>
                  </div>

                  {/* Image 3 Vertical Paper Stream Cards */}
                  <div style={{ display: "flex", flexDirection: "column", gap: 18, position: "relative" }}>
                    <div style={{ position: "absolute", left: 16, top: 20, bottom: 20, width: 2, background: "#cbd5e1", zIndex: 0 }} />

                    {filteredPaperStream.map((p, idx) => {
                      const stepColors = ["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#ef4444"];
                      const stepColor = stepColors[idx % stepColors.length];

                      return (
                        <div key={p.id} style={{ display: "flex", gap: 16, position: "relative", zIndex: 1 }}>
                          {/* Step Badge */}
                          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 34, flexShrink: 0, marginTop: 4 }}>
                            <div
                              style={{
                                width: 32,
                                height: 32,
                                borderRadius: "50%",
                                background: stepColor,
                                color: "white",
                                fontSize: 12,
                                fontWeight: 700,
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
                              }}
                            >
                              {idx + 1}
                            </div>
                            <div style={{ fontSize: 11, fontWeight: 700, color: stepColor, marginTop: 4 }}>
                              {p.year || "n.d."}
                            </div>
                          </div>

                          {/* Paper Card */}
                          <div
                            style={{
                              flex: 1,
                              background: "white",
                              border: "1px solid #e2e8f0",
                              borderRadius: 10,
                              padding: 16,
                              boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
                              display: "flex",
                              flexDirection: "column",
                              gap: 12,
                            }}
                          >
                            {/* Card Top: Title, Meta, and Action */}
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                              <div style={{ display: "flex", gap: 10 }}>
                                <div style={{ width: 32, height: 32, borderRadius: 6, background: "#eff6ff", color: "#2563eb", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 2 }}>
                                  <FileText size={17} />
                                </div>
                                <div>
                                  <h4 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: "0 0 4px" }}>
                                    {p.title}
                                  </h4>
                                  <div style={{ fontSize: 11, color: "#64748b" }}>
                                    {p.authors_str || "Authors not available"} {p.venue ? `· ${p.venue}` : ""}
                                  </div>
                                  {p.abstract && (
                                    <p style={{ fontSize: 11, color: "#475569", margin: "6px 0 0", lineHeight: 1.4 }}>
                                      {p.abstract.length > 140 ? `${p.abstract.slice(0, 138)}...` : p.abstract}
                                    </p>
                                  )}
                                </div>
                              </div>

                              <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                                {p.paper_kind && p.paper_kind !== "unknown" && (
                                  <span style={{ fontSize: 11, background: "#f1f5f9", color: "#475569", padding: "3px 8px", borderRadius: 6, fontWeight: 600, textTransform: "capitalize" }}>
                                    {p.paper_kind}
                                  </span>
                                )}
                                <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, fontWeight: 600, color: "#7c3aed", background: "#f5f3ff", padding: "3px 8px", borderRadius: 6 }}>
                                  <Quote size={11} /> {p.citation_count} Citations
                                </span>
                                {(p.url || p.doi) && (
                                  <a
                                    href={p.url || `https://doi.org/${p.doi}`}
                                    target="_blank"
                                    rel="noreferrer"
                                    style={{
                                      display: "flex",
                                      alignItems: "center",
                                      gap: 4,
                                      padding: "4px 8px",
                                      background: "#eff6ff",
                                      border: "1px solid #bfdbfe",
                                      borderRadius: 6,
                                      color: "#1d4ed8",
                                      fontSize: 11,
                                      fontWeight: 600,
                                      textDecoration: "none",
                                    }}
                                  >
                                    View Paper <ExternalLink size={11} />
                                  </a>
                                )}
                              </div>
                            </div>

                            {/* Card Bottom 3 Columns */}
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, background: "#f8fafc", padding: "10px 12px", borderRadius: 8, border: "1px solid #edf2f7" }}>
                              {/* Col 1: Key Contribution */}
                              <div>
                                <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 700, color: "#2563eb", marginBottom: 4 }}>
                                  <Lightbulb size={13} /> Key Contribution
                                </div>
                                <div style={{ fontSize: 11, color: "#334155", lineHeight: 1.35 }}>
                                  {p.key_contribution || "Not stated in analyzed text"}
                                </div>
                              </div>

                              {/* Col 2: Gaps / Limitations Noted */}
                              <div>
                                <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 700, color: "#059669", marginBottom: 4 }}>
                                  <CheckCircle2 size={13} /> {p.paper_kind === "survey" ? "Open Challenges" : "Limitations / Gaps"}
                                </div>
                                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                                  {(() => {
                                    const list = (p.limitations_and_gaps && p.limitations_and_gaps.length > 0)
                                      ? p.limitations_and_gaps
                                      : [];
                                    if (list.length > 0) {
                                      return list.map((g, gIdx) => {
                                        const text = typeof g === "string" ? g : (g.value || JSON.stringify(g));
                                        return (
                                          <div key={gIdx} style={{ fontSize: 11, color: "#334155", display: "flex", alignItems: "flex-start", gap: 4 }}>
                                            <span style={{ color: "#059669", fontWeight: 700 }}>•</span>
                                            <span>{text}</span>
                                          </div>
                                        );
                                      });
                                    }
                                    if (p.extraction_status === "source_limited") {
                                      return <span style={{ fontSize: 11, color: "#64748b", fontStyle: "italic" }}>Source limited (abstract only — full text not found in open access)</span>;
                                    }
                                    if (p.extraction_status === "not_stated") {
                                      return <span style={{ fontSize: 11, color: "#64748b", fontStyle: "italic" }}>Authors did not state explicit limitations in the analyzed text</span>;
                                    }
                                    if (p.extraction_status === "pending") {
                                      return <span style={{ fontSize: 11, color: "#64748b", fontStyle: "italic" }}>Extraction queued</span>;
                                    }
                                    if (p.extraction_status === "failed") {
                                      return <span style={{ fontSize: 11, color: "#dc2626", fontStyle: "italic" }}>Extraction degraded ({p.error_reason || "timeout"})</span>;
                                    }
                                    return <span style={{ fontSize: 11, color: "#64748b", fontStyle: "italic" }}>Not stated in analyzed text</span>;
                                  })()}
                                </div>
                              </div>

                              {/* Col 3: Cluster / Theme */}
                              <div>
                                <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 700, color: "#7c3aed", marginBottom: 4 }}>
                                  <Sparkles size={13} /> Cluster Tag
                                </div>
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                                  {p.topic_tag ? (
                                    <span style={{ fontSize: 10, background: "#ede9fe", color: "#6d28d9", padding: "2px 7px", borderRadius: 10, fontWeight: 500 }}>
                                      {p.topic_tag}
                                    </span>
                                  ) : (
                                    <span style={{ fontSize: 11, color: "#94a3b8" }}>Not assigned</span>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}

                    {filteredPaperStream.length === 0 && (
                      <div style={{ textAlign: "center", padding: "30px 0", color: "#64748b", fontSize: 12 }}>
                        No papers match the selected timeline filters.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Key Transitions Card (Only shown if not in Lineage Stream view) */}
            {selectedPhaseView !== "Paper Lineage Stream" && (
              <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 10, padding: 20, boxShadow: "0 1px 3px rgba(0,0,0,0.03)" }}>
                {/* Header */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 32, height: 32, borderRadius: 8, background: "#f1f5f9", display: "flex", alignItems: "center", justifyContent: "center", color: "#0f172a" }}>
                      <GitMerge size={17} />
                    </div>
                    <div>
                      <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                        Key Transitions ({filteredTransitions.length})
                      </h3>
                      <p style={{ fontSize: 12, color: "#64748b", margin: 0 }}>
                        Most significant methodological and finding changes between research phases
                      </p>
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#475569", cursor: "pointer" }}>
                      <input
                        type="checkbox"
                        checked={groupByPhase}
                        onChange={(e) => setGroupByPhase(e.target.checked)}
                        style={{ cursor: "pointer" }}
                      />
                      <span>Group by Phase</span>
                    </label>
                    <button
                      onClick={() => setShowTransitionFilter(!showTransitionFilter)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                        padding: "5px 10px",
                        background: showTransitionFilter ? "#eff6ff" : "#f8fafc",
                        border: "1px solid",
                        borderColor: showTransitionFilter ? "#93c5fd" : "#cbd5e1",
                        color: showTransitionFilter ? "#1d4ed8" : "#475569",
                        borderRadius: 6,
                        fontSize: 12,
                        cursor: "pointer",
                      }}
                    >
                      <Filter size={12} /> Filter
                    </button>
                  </div>
                </div>

                {/* Filter Bar */}
                {showTransitionFilter && (
                  <div style={{ display: "flex", gap: 10, background: "#f8fafc", padding: "10px 12px", borderRadius: 6, border: "1px solid #e2e8f0", marginBottom: 16, alignItems: "center" }}>
                    <select
                      value={transitionPhaseFilter}
                      onChange={(e) => setTransitionPhaseFilter(e.target.value)}
                      style={{ padding: "4px 8px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 12 }}
                    >
                      <option value="all">All Phases</option>
                      <option value="1">Phase 1 Transitions</option>
                      <option value="2">Phase 2 Transitions</option>
                      <option value="3">Phase 3 Transitions</option>
                      <option value="4">Phase 4 / Recent</option>
                    </select>

                    <input
                      type="text"
                      value={transitionSearchQuery}
                      onChange={(e) => setTransitionSearchQuery(e.target.value)}
                      placeholder="Search transitions..."
                      style={{ flex: 1, padding: "4px 8px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 12 }}
                    />

                    {(transitionPhaseFilter !== "all" || transitionSearchQuery) && (
                      <button
                        onClick={() => {
                          setTransitionPhaseFilter("all");
                          setTransitionSearchQuery("");
                        }}
                        style={{ background: "none", border: "none", color: "#2563eb", fontSize: 12, cursor: "pointer" }}
                      >
                        Clear
                      </button>
                    )}
                  </div>
                )}

                {/* Vertical Timeline Transitions List */}
                <div style={{ display: "flex", flexDirection: "column", gap: 16, position: "relative" }}>
                  <div style={{ position: "absolute", left: 7, top: 14, bottom: 14, width: 2, background: "#e2e8f0", zIndex: 0 }} />

                  {filteredTransitions.map((item, idx) => {
                    const isRecent = item.badge?.includes("Recent") || idx === transitions.length - 1;
                    const dotColor = isRecent ? "#ef4444" : phaseStyles[idx % phaseStyles.length].border;
                    const iconColor = isRecent ? "#ef4444" : phaseStyles[idx % phaseStyles.length].text;
                    const badgeBg = isRecent ? "#fef2f2" : phaseStyles[idx % phaseStyles.length].badge;
                    const badgeText = isRecent ? "#991b1b" : phaseStyles[idx % phaseStyles.length].badgeText;

                    return (
                      <div key={idx} style={{ display: "flex", gap: 16, position: "relative", zIndex: 1 }}>
                        <div style={{ width: 16, height: 16, borderRadius: "50%", background: "white", border: `3.5px solid ${dotColor}`, marginTop: 18, flexShrink: 0 }} />

                        <div
                          style={{
                            flex: 1,
                            background: "#fafbfc",
                            border: "1px solid #e2e8f0",
                            borderRadius: 8,
                            padding: "16px 18px",
                            position: "relative",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                            <span style={{ fontSize: 11, fontWeight: 600, padding: "3px 9px", borderRadius: 12, background: badgeBg, color: badgeText }}>
                              {item.badge}
                            </span>
                            <button
                              onClick={() => {
                                if (item.papers && item.papers.length > 0) {
                                  setInspectingPapers(item.papers);
                                  setInspectingTitle(item.title);
                                }
                              }}
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 3,
                                fontSize: 11,
                                fontWeight: 600,
                                padding: "3px 9px",
                                borderRadius: 10,
                                background: "#e0e7ff",
                                color: "#3730a3",
                                border: "none",
                                cursor: "pointer",
                              }}
                              title="Click to view all papers used in this transition"
                            >
                              {item.phase_from_count !== undefined && item.phase_to_count !== undefined
                                ? `${item.phase_from_count} + ${item.phase_to_count} = ${item.paper_count} papers`
                                : `${item.paper_count} papers`}{" "}
                              <ChevronRight size={12} />
                            </button>
                          </div>

                          <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: 18 }}>
                            <div style={{ display: "flex", gap: 10 }}>
                              <div style={{ width: 32, height: 32, borderRadius: 6, background: "white", border: "1px solid #cbd5e1", display: "flex", alignItems: "center", justifyContent: "center", color: iconColor, flexShrink: 0, marginTop: 2 }}>
                                <FileText size={17} />
                              </div>
                              <div>
                                <h4 style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", margin: "0 0 6px" }}>
                                  {item.title}
                                </h4>
                                <p style={{ fontSize: 12, color: "#475569", lineHeight: 1.45, margin: 0 }}>
                                  {item.description}
                                </p>
                              </div>
                            </div>

                            <div style={{ background: "white", padding: "10px 14px", borderRadius: 6, border: "1px solid #edf2f7" }}>
                              <div style={{ fontSize: 11, fontWeight: 700, color: "#475569", marginBottom: 6 }}>
                                Key changes
                              </div>
                              {item.key_changes && item.key_changes.length > 0 ? (
                                <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 4 }}>
                                  {item.key_changes.map((kc, kIdx) => (
                                    <li key={kIdx} style={{ display: "flex", alignItems: "flex-start", gap: 6, fontSize: 11, color: "#334155", lineHeight: 1.35 }}>
                                      <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#10b981", marginTop: 5, flexShrink: 0 }} />
                                      <span>{kc}</span>
                                    </li>
                                  ))}
                                </ul>
                              ) : (
                                <div style={{ fontSize: 11, color: "#94a3b8" }}>
                                  No extracted method/dataset diffs across this boundary yet.
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Right Sidebar Column (Shown in Timeline views) */}
          {selectedPhaseView !== "Paper Lineage Stream" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              {/* Card 1: Research Focus Trend */}
              <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 10, padding: 16, boxShadow: "0 1px 3px rgba(0,0,0,0.03)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 12 }}>
                  <BarChart3 size={16} color="#2563eb" />
                  <h3 style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", margin: 0 }}>Research Focus Trend</h3>
                </div>

                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 14 }}>
                  {focusTrends.series.map((s, idx) => (
                    <div key={idx} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "#475569" }}>
                      <span style={{ width: 7, height: 7, borderRadius: "50%", background: s.color }} />
                      <span>{s.name}</span>
                    </div>
                  ))}
                </div>

                <div style={{ width: "100%", height: 140, position: "relative" }}>
                  <svg viewBox="0 0 300 130" style={{ width: "100%", height: "100%", overflow: "visible" }}>
                    <line x1="0" y1="20" x2="300" y2="20" stroke="#f1f5f9" strokeDasharray="3 3" />
                    <line x1="0" y1="55" x2="300" y2="55" stroke="#f1f5f9" strokeDasharray="3 3" />
                    <line x1="0" y1="90" x2="300" y2="90" stroke="#f1f5f9" strokeDasharray="3 3" />
                    <line x1="0" y1="110" x2="300" y2="110" stroke="#e2e8f0" />

                    {focusTrends.series.map((s, sIdx) => {
                      const pts = s.data;
                      const maxVal = 10;
                      const stepX = 300 / (pts.length - 1);

                      let d = "";
                      pts.forEach((val, i) => {
                        const x = i * stepX;
                        const y = 110 - (val / maxVal) * 85;
                        if (i === 0) {
                          d += `M ${x},${y}`;
                        } else {
                          const prevX = (i - 1) * stepX;
                          const prevY = 110 - (pts[i - 1] / maxVal) * 85;
                          const cpX1 = prevX + stepX * 0.45;
                          const cpX2 = x - stepX * 0.45;
                          d += ` C ${cpX1},${prevY} ${cpX2},${y} ${x},${y}`;
                        }
                      });

                      return (
                        <g key={sIdx}>
                          <path d={d} fill="none" stroke={s.color} strokeWidth="2.2" strokeLinecap="round" />
                          {pts.map((val, i) => {
                            const x = i * stepX;
                            const y = 110 - (val / maxVal) * 85;
                            return (
                              <circle key={i} cx={x} cy={y} r="2.5" fill="white" stroke={s.color} strokeWidth="1.8" />
                            );
                          })}
                        </g>
                      );
                    })}

                    {focusTrends.years.map((yr, idx) => {
                      const stepX = 300 / (focusTrends.years.length - 1);
                      return (
                        <text key={yr} x={idx * stepX} y="126" fontSize="9" fill="#94a3b8" textAnchor="middle">
                          {yr}
                        </text>
                      );
                    })}
                  </svg>
                </div>
              </div>

              {/* Card 2: Research Phases Overview */}
              <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 10, padding: 16, boxShadow: "0 1px 3px rgba(0,0,0,0.03)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 12 }}>
                  <GitBranch size={16} color="#7c3aed" />
                  <h3 style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", margin: 0 }}>Research Phases Overview</h3>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {phases.map((phase, idx) => {
                    const style = phaseStyles[idx % phaseStyles.length];
                    const IconComp = style.icon;
                    return (
                      <div
                        key={phase.phase_num}
                        onClick={() => {
                          if (phase.papers && phase.papers.length > 0) {
                            setInspectingPapers(phase.papers);
                            setInspectingTitle(`Phase ${phase.phase_num}: ${phase.title}`);
                          }
                        }}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          padding: "8px 10px",
                          background: "#f8fafc",
                          borderRadius: 6,
                          border: "1px solid #e2e8f0",
                          cursor: phase.papers ? "pointer" : "default",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 8, overflow: "hidden" }}>
                          <div style={{ width: 28, height: 28, borderRadius: 6, background: style.fill, color: style.text, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                            <IconComp size={15} />
                          </div>
                          <div style={{ overflow: "hidden" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              <span style={{ fontSize: 11, fontWeight: 700, color: style.text }}>
                                Phase {phase.phase_num}
                              </span>
                              <span style={{ fontSize: 10, color: "#64748b" }}>
                                {phase.start_year} – {phase.end_year}
                              </span>
                            </div>
                            <div style={{ fontSize: 11, fontWeight: 600, color: "#0f172a", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                              {phase.title}
                            </div>
                          </div>
                        </div>
                        <span style={{ fontSize: 11, color: "#2563eb", fontWeight: 600, flexShrink: 0, marginLeft: 6 }}>
                          {phase.paper_count} papers
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Card 3: Key Insights */}
              <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 10, padding: 16, boxShadow: "0 1px 3px rgba(0,0,0,0.03)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 12 }}>
                  <Lightbulb size={16} color="#d97706" />
                  <h3 style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", margin: 0 }}>Key Insights</h3>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {keyInsights.map((insight, idx) => (
                    <div key={idx} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                      <div style={{ width: 18, height: 18, borderRadius: "50%", background: "#2563eb", color: "white", fontSize: 10, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 2 }}>
                        {idx + 1}
                      </div>
                      <div style={{ fontSize: 11, color: "#334155", lineHeight: 1.4 }}>{insight}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: THEMATIC EVOLUTION                                                 */}
      {/* ========================================================================= */}
      {activeTab === "thematic" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 10, padding: 20 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, color: "#0f172a", margin: "0 0 6px" }}>
              Thematic Evolution &amp; Cluster Trajectories
            </h3>
            <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 20px" }}>
              Analysis of how each thematic cluster emerged, matured, and integrated across this corpus.
            </p>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16 }}>
              {clusters.map((c, idx) => (
                <div key={c.id} style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ width: 10, height: 10, borderRadius: "50%", background: phaseStyles[idx % phaseStyles.length].border }} />
                      <h4 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0 }}>{c.label}</h4>
                    </div>
                    <span style={{ fontSize: 11, fontWeight: 600, background: "#e0e7ff", color: "#3730a3", padding: "2px 8px", borderRadius: 10 }}>
                      {c.member_count} papers
                    </span>
                  </div>

                  <div style={{ fontSize: 12, color: "#475569", marginBottom: 12 }}>
                    Dominant in years: {Object.keys(c.year_distribution || {}).join(", ") || "Active across span"}
                  </div>

                  <div style={{ fontSize: 11, fontWeight: 700, color: "#334155", marginBottom: 6 }}>
                    Representative Works:
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {(c.members || []).slice(0, 3).map((m) => (
                      <div key={m.paper_id} style={{ background: "white", padding: "6px 8px", borderRadius: 6, border: "1px solid #e2e8f0", fontSize: 11, color: "#0f172a" }}>
                        <div style={{ fontWeight: 600 }}>{m.title}</div>
                        <div style={{ color: "#64748b", fontSize: 10 }}>Year: {m.year || "n.d."}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              {clusters.length === 0 && (
                <div style={{ textAlign: "center", padding: "30px 0", color: "#64748b" }}>
                  No thematic clusters identified yet.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: METHOD & METRIC PROGRESSION                                        */}
      {/* ========================================================================= */}
      {activeTab === "methods" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 10, padding: 20 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, color: "#0f172a", margin: "0 0 6px" }}>
              Empirical Method &amp; Metric Progression
            </h3>
            <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 20px" }}>
              Structured chronological diffs of empirical methods, datasets, and performance over time.
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {(data.method_progression || []).map((m, idx) => (
                <div key={idx} style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, background: "#dbeafe", color: "#1e40af", padding: "2px 8px", borderRadius: 4 }}>
                        Method Transition #{idx + 1}
                      </span>
                      <span style={{ fontSize: 11, color: "#64748b" }}>
                        {m.from_paper.year || "earlier"} → {m.to_paper.year || "subsequent"}
                      </span>
                    </div>
                    <span style={{ fontSize: 10, color: "#166534", background: "#dcfce7", padding: "2px 8px", borderRadius: 10, fontWeight: 600 }}>
                      Extracted Text Evidence
                    </span>
                  </div>

                  <p style={{ fontSize: 12, color: "#334155", lineHeight: 1.45, margin: "0 0 12px" }}>
                    {m.explanation}
                  </p>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    <div style={{ background: "white", padding: 10, borderRadius: 6, border: "1px solid #edf2f7" }}>
                      <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", fontWeight: 700 }}>Earlier Work</div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: "#0f172a", marginTop: 2 }}>{m.from_paper.title}</div>
                      {m.from_paper.method && <div style={{ fontSize: 11, color: "#2563eb", marginTop: 4 }}>Method: {m.from_paper.method}</div>}
                    </div>

                    <div style={{ background: "white", padding: 10, borderRadius: 6, border: "1px solid #edf2f7" }}>
                      <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", fontWeight: 700 }}>Subsequent Work</div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: "#0f172a", marginTop: 2 }}>{m.to_paper.title}</div>
                      {m.to_paper.method && <div style={{ fontSize: 11, color: "#059669", marginTop: 4 }}>Method: {m.to_paper.method}</div>}
                    </div>
                  </div>
                </div>
              ))}
              {(!data.method_progression || data.method_progression.length === 0) && (
                <div style={{ textAlign: "center", padding: "30px 0", color: "#64748b" }}>
                  No structured method progressions indexed for this corpus yet.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 4: KEY FINDINGS & CONSENSUS                                           */}
      {/* ========================================================================= */}
      {activeTab === "findings" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 10, padding: 20 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, color: "#0f172a", margin: "0 0 6px" }}>
              Key Findings, Confirmations &amp; Consensus
            </h3>
            <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 20px" }}>
              Documented empirical confirmations, extensions, and contradictions across papers.
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {(data.finding_dynamics || []).map((f, idx) => (
                <div key={idx} style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                    <span style={{
                      fontSize: 11,
                      fontWeight: 700,
                      background: (f.kind === "confirms" || f.kind === "finding_confirms") ? "#dcfce7" : f.kind === "insufficient_evidence" ? "#fef3c7" : "#fee2e2",
                      color: (f.kind === "confirms" || f.kind === "finding_confirms") ? "#166534" : f.kind === "insufficient_evidence" ? "#92400e" : "#991b1b",
                      padding: "2px 8px",
                      borderRadius: 4,
                    }}>
                      {f.kind}
                    </span>
                    <span style={{ fontSize: 11, color: "#64748b" }}>
                      {f.from_paper.year || "earlier"} vs {f.to_paper.year || "later"}
                    </span>
                  </div>

                  <p style={{ fontSize: 12, color: "#334155", lineHeight: 1.45, margin: "0 0 10px" }}>
                    {f.explanation}
                  </p>

                  <div style={{ fontSize: 11, color: "#64748b" }}>
                    Compared: <strong>"{f.from_paper.title}"</strong> and <strong>"{f.to_paper.title}"</strong>
                  </div>
                </div>
              ))}
              {(!data.finding_dynamics || data.finding_dynamics.length === 0) && (
                <div style={{ textAlign: "center", padding: "30px 0", color: "#64748b" }}>
                  No cross-paper finding dynamics indexed yet.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: PAPERS INSPECTOR                                                   */}
      {/* ========================================================================= */}
      {inspectingPapers && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: "100vw",
            height: "100vh",
            background: "rgba(15, 23, 42, 0.6)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 99999,
            padding: 20,
          }}
          onClick={() => setInspectingPapers(null)}
        >
          <div
            style={{
              background: "white",
              borderRadius: 12,
              width: "100%",
              maxWidth: 720,
              maxHeight: "85vh",
              display: "flex",
              flexDirection: "column",
              boxShadow: "0 20px 25px -5px rgba(0,0,0,0.2)",
              overflow: "hidden",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div style={{ padding: "16px 20px", borderBottom: "1px solid #e2e8f0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 700, color: "#0f172a", margin: "0 0 2px" }}>
                  {inspectingTitle}
                </h3>
                <div style={{ fontSize: 12, color: "#64748b" }}>
                  Showing {inspectingPapers.length} papers in this transition
                </div>
              </div>
              <button
                onClick={() => setInspectingPapers(null)}
                style={{ background: "#f1f5f9", border: "none", borderRadius: "50%", width: 30, height: 30, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: "#64748b" }}
              >
                <X size={16} />
              </button>
            </div>

            {/* Modal List */}
            <div style={{ padding: "16px 20px", overflowY: "auto", display: "flex", flexDirection: "column", gap: 12 }}>
              {inspectingPapers.map((p) => (
                <div key={p.id} style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 14, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 14 }}>
                  <div style={{ overflow: "hidden" }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", lineHeight: 1.3, marginBottom: 4 }}>
                      {p.title}
                    </div>
                    <div style={{ fontSize: 11, color: "#64748b" }}>
                      {p.authors_str} · {p.year || "n.d."} {p.venue ? `· ${p.venue}` : ""}
                    </div>
                    <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                      <span style={{ fontSize: 10, fontWeight: 600, background: "#ede9fe", color: "#6d28d9", padding: "1px 6px", borderRadius: 4 }}>
                        {p.citation_count} citations
                      </span>
                      {p.topic_tag && (
                        <span style={{ fontSize: 10, background: "#e0e7ff", color: "#3730a3", padding: "1px 6px", borderRadius: 4 }}>
                          {p.topic_tag}
                        </span>
                      )}
                    </div>
                  </div>

                  {(p.url || p.doi) && (
                    <a
                      href={p.url || `https://doi.org/${p.doi}`}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                        padding: "6px 12px",
                        background: "#eff6ff",
                        border: "1px solid #bfdbfe",
                        borderRadius: 6,
                        color: "#1d4ed8",
                        fontSize: 11,
                        fontWeight: 600,
                        textDecoration: "none",
                        flexShrink: 0,
                      }}
                    >
                      View Paper <ExternalLink size={12} />
                    </a>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
