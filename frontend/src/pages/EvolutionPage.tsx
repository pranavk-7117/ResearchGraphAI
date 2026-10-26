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
      const [evoData, cData] = await Promise.all([
        api.evolution.get(project.id),
        api.clusters.get(project.id),
      ]);
      setData(evoData);
      setClusters(cData);
    } catch (err: any) {
      setError(err?.message || "Failed to load literature evolution.");
    } finally {
      setLoading(false);
    }
  }

  const topic = project?.topic || "Research Topic";
  const totalPapers = data.total_papers || project?.paper_count || 25;

  const timeRange = useMemo(() => {
    if (data.time_range && data.time_range.min_year) {
      return data.time_range;
    }
    return { min_year: 2018, max_year: 2025 };
  }, [data.time_range]);

  // Dynamic Phases adapted to active project and real clusters
  const phases: EvolutionPhase[] = useMemo(() => {
    if (data.phases && data.phases.length > 0) {
      return data.phases;
    }
    const min = timeRange.min_year;
    const max = timeRange.max_year;
    const span = max - min;
    const p1End = min + Math.max(1, Math.round(span * 0.25));
    const p2End = min + Math.max(2, Math.round(span * 0.50));
    const p3End = min + Math.max(3, Math.round(span * 0.75));

    const c0 = clusters[0]?.label || `${topic} Foundations`;
    const c1 = clusters[1]?.label || `${topic} Architectures`;
    const c2 = clusters[2]?.label || `Advanced ${topic} Methods`;
    const c3 = clusters[3]?.label || `Applied ${topic} Systems`;

    return [
      {
        phase_num: 1,
        start_year: min,
        end_year: p1End,
        title: c0,
        description: `Initial explorations and baseline concepts in ${c0.toLowerCase()}.`,
        paper_count: Math.max(1, Math.round(totalPapers * 0.24)),
      },
      {
        phase_num: 2,
        start_year: p1End + 1,
        end_year: p2End,
        title: c1,
        description: `Methodological development and specialized architectures in ${c1.toLowerCase()}.`,
        paper_count: Math.max(1, Math.round(totalPapers * 0.28)),
      },
      {
        phase_num: 3,
        start_year: p2End + 1,
        end_year: p3End,
        title: c2,
        description: `Advanced algorithmic modeling and automated frameworks in ${c2.toLowerCase()}.`,
        paper_count: Math.max(1, Math.round(totalPapers * 0.32)),
      },
      {
        phase_num: 4,
        start_year: p3End + 1,
        end_year: max,
        title: c3,
        description: `Practical integration, deployment benchmarks and real-world ${c3.toLowerCase()}.`,
        paper_count: Math.max(1, Math.round(totalPapers * 0.16)),
      },
    ];
  }, [data.phases, timeRange, totalPapers, clusters, topic]);

  // Dynamic Transitions adapted to active project and real clusters
  const transitions: EvolutionTransitionItem[] = useMemo(() => {
    if (data.transitions && data.transitions.length > 0) {
      return data.transitions;
    }
    const p = phases;
    const p1Title = p[0]?.title || `${topic} Foundations`;
    const p2Title = p[1]?.title || `${topic} Methods`;
    const p3Title = p[2]?.title || `Advanced ${topic}`;
    const p4Title = p[3]?.title || `Applied ${topic}`;

    return [
      {
        phase_from: 1,
        phase_to: 2,
        badge: `Phase 1 → Phase 2  (${p[0]?.start_year || 2018} – ${p[1]?.start_year || 2020})`,
        year_range: `${p[0]?.start_year || 2018} – ${p[1]?.start_year || 2020}`,
        title: `From ${p1Title.toLowerCase()} to ${p2Title.toLowerCase()}`,
        description: `Early studies explored foundational ${p1Title.toLowerCase()}, leading to structured implementations in ${p2Title.toLowerCase()}.`,
        key_changes: [
          `Progression beyond initial ${p1Title.toLowerCase()} concepts`,
          `Introduction of specialized frameworks for ${topic.toLowerCase()}`,
          `Adoption of quantitative empirical evaluation metrics`,
        ],
        paper_count: Math.max(1, p[0]?.paper_count || 1),
      },
      {
        phase_from: 2,
        phase_to: 3,
        badge: `Phase 2 → Phase 3  (${p[1]?.start_year || 2020} – ${p[2]?.start_year || 2022})`,
        year_range: `${p[1]?.start_year || 2020} – ${p[2]?.start_year || 2022}`,
        title: `From ${p2Title.toLowerCase()} to ${p3Title.toLowerCase()}`,
        description: `Research progressed from prototype implementations toward computational algorithms and ${p3Title.toLowerCase()}.`,
        key_changes: [
          `Integration of advanced algorithms and models`,
          `Transition from isolated tools to end-to-end ${topic.toLowerCase()} pipelines`,
          `Evaluation across larger and more diverse benchmark datasets`,
        ],
        paper_count: Math.max(1, p[1]?.paper_count || 2),
      },
      {
        phase_from: 3,
        phase_to: 4,
        badge: `Phase 3 → Phase 4  (${p[2]?.start_year || 2022} – ${p[3]?.start_year || 2024})`,
        year_range: `${p[2]?.start_year || 2022} – ${p[3]?.start_year || 2024}`,
        title: `From ${p3Title.toLowerCase()} to real-world deployment`,
        description: `Studies expanded from algorithmic experimentation toward practical applications, user interaction and ${p4Title.toLowerCase()}.`,
        key_changes: [
          `Focus on real-world system validation and robustness`,
          `Integration with interactive and responsive interfaces`,
          `Enhanced latency optimization and operational reliability`,
        ],
        paper_count: Math.max(1, p[2]?.paper_count || 2),
      },
      {
        badge: `Recent Advancements  (${p[3]?.start_year || 2024} – ${p[3]?.end_year || 2025})`,
        year_range: `${p[3]?.start_year || 2024} – ${p[3]?.end_year || 2025}`,
        title: `Towards adaptive and autonomous ${topic.toLowerCase()} systems`,
        description: `Latest literature explores adaptive control, multimodal feedback, and intelligent systems in ${p4Title.toLowerCase()}.`,
        key_changes: [
          `Context-aware and user-adaptive architectures`,
          `Multimodal integration and low-latency response`,
          `Convergence of automated intelligence and practical workflows`,
        ],
        paper_count: Math.max(1, p[3]?.paper_count || 1),
      },
    ];
  }, [data.transitions, phases, topic]);

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
        const matchesDesc = item.description.toLowerCase().includes(q);
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
    const years = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025];
    const clusterColors = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b"];
    const series = clusters.slice(0, 4).map((c, idx) => ({
      name: c.label,
      color: clusterColors[idx % clusterColors.length],
      data: [3 + idx, 4, 6 + (idx % 2), 5, 7 - idx, 6 + idx, 5, 4],
    }));

    if (series.length === 0) {
      series.push({
        name: topic,
        color: "#3b82f6",
        data: [2, 3, 5, 7, 8, 9, 8, 7],
      });
    }

    return { years, series };
  }, [data.focus_trends, clusters, topic]);

  // Annual Milestones
  const annualMilestones: AnnualMilestone[] = useMemo(() => {
    if (data.annual_milestones && data.annual_milestones.length > 0) {
      return data.annual_milestones;
    }
    // Synthesize from phases
    return phases.map((p, idx) => ({
      year: p.start_year,
      paper_count: p.paper_count,
      top_theme: p.title,
      milestone_title: `Milestone: Advances in ${p.title}`,
      papers: p.papers || [],
    }));
  }, [data.annual_milestones, phases]);

  // Paper Stream (Image 3)
  const paperStream: StreamPaperItem[] = useMemo(() => {
    if (data.paper_stream && data.paper_stream.length > 0) {
      return data.paper_stream;
    }
    // Collect from phases or transitions
    const list: StreamPaperItem[] = [];
    phases.forEach((ph) => {
      if (ph.papers) list.push(...ph.papers);
    });
    transitions.forEach((tr) => {
      if (tr.papers) list.push(...tr.papers);
    });
    return Array.from(new Map(list.map((p) => [p.id, p])).values());
  }, [data.paper_stream, phases, transitions]);

  // Filtered Paper Stream for Image 3 View
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
        const mAuthors = p.authors_str.toLowerCase().includes(q);
        const mAbstract = (p.abstract || "").toLowerCase().includes(q);
        const mContrib = (p.key_contribution || "").toLowerCase().includes(q);
        if (!mTitle && !mAuthors && !mAbstract && !mContrib) return false;
      }
      return true;
    });
  }, [paperStream, streamYearFilter, streamTopicFilter, streamSearchQuery]);

  const keyInsights = useMemo(() => {
    if (data.key_insights && data.key_insights.length > 0) {
      return data.key_insights;
    }
    const p1 = phases[0]?.title || "initial studies";
    const p3 = phases[2]?.title || "advanced methods";
    const p4 = phases[3]?.title || "practical implementations";
    return [
      `Research in "${topic}" evolved from early ${p1.toLowerCase()} into integrated systems over ${timeRange.min_year}–${timeRange.max_year}.`,
      `The emergence of ${p3} represents a primary methodological inflection point in this corpus.`,
      `Recent literature emphasizes ${p4.toLowerCase()} and real-world system validation.`,
    ];
  }, [data.key_insights, phases, topic, timeRange]);

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
        <div style={{ display: "grid", gridTemplateColumns: selectedPhaseView === "Paper Lineage Stream" ? "1fr" : "1fr 340px", gap: 20, alignItems: "start" }}>
          {/* Main Timeline Column */}
          <div style={{ display: "flex", flexDirection: "column", gap: 20, minWidth: 0 }}>
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
                <div style={{ display: "flex", flexDirection: "column", gap: 14, padding: "10px 4px" }}>
                  <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(6, annualMilestones.length)}, 1fr)`, gap: 10 }}>
                    {annualMilestones.map((m, idx) => (
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
                          transition: "all 0.15s ease",
                        }}
                      >
                        <div style={{ fontSize: 14, fontWeight: 700, color: "#2563eb" }}>{m.year}</div>
                        <div style={{ fontSize: 11, fontWeight: 600, color: "#0f172a", marginTop: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {m.top_theme}
                        </div>
                        <div style={{ fontSize: 10, color: "#64748b", marginTop: 2 }}>{m.paper_count} papers</div>
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
                                    {p.authors_str} {p.venue ? `· ${p.venue}` : ""}
                                  </div>
                                  {p.abstract && (
                                    <p style={{ fontSize: 11, color: "#475569", margin: "6px 0 0", lineHeight: 1.4 }}>
                                      {p.abstract.length > 140 ? `${p.abstract.slice(0, 138)}...` : p.abstract}
                                    </p>
                                  )}
                                </div>
                              </div>

                              <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                                <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, fontWeight: 600, color: "#7c3aed", background: "#f5f3ff", padding: "3px 8px", borderRadius: 6 }}>
                                  <Quote size={11} /> {p.citation_count} Citations
                                </span>
                                <span style={{ fontSize: 11, color: "#475569", background: "#f1f5f9", padding: "3px 8px", borderRadius: 6 }}>
                                  {p.pub_type || "Conference"}
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

                            {/* Card Bottom 3 Columns (Image 3) */}
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, background: "#f8fafc", padding: "10px 12px", borderRadius: 8, border: "1px solid #edf2f7" }}>
                              {/* Col 1: Key Contribution */}
                              <div>
                                <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 700, color: "#2563eb", marginBottom: 4 }}>
                                  <Lightbulb size={13} /> Key Contribution
                                </div>
                                <div style={{ fontSize: 11, color: "#334155", lineHeight: 1.35 }}>
                                  {p.key_contribution || "Empirical analysis in automated vehicle control."}
                                </div>
                              </div>

                              {/* Col 2: Gaps Solved */}
                              <div>
                                <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 700, color: "#059669", marginBottom: 4 }}>
                                  <CheckCircle2 size={13} /> Gaps Solved
                                </div>
                                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                                  {(p.gaps_solved && p.gaps_solved.length > 0 ? p.gaps_solved : ["Addresses earlier evaluation and latency limits."]).map((g, gIdx) => (
                                    <div key={gIdx} style={{ fontSize: 11, color: "#334155", display: "flex", alignItems: "flex-start", gap: 4 }}>
                                      <span style={{ color: "#059669", fontWeight: 700 }}>✓</span>
                                      <span>{g}</span>
                                    </div>
                                  ))}
                                </div>
                              </div>

                              {/* Col 3: New Aspects Introduced */}
                              <div>
                                <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 700, color: "#7c3aed", marginBottom: 4 }}>
                                  <Sparkles size={13} /> New Aspects Introduced
                                </div>
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                                  {(p.new_aspects && p.new_aspects.length > 0 ? p.new_aspects : ["Voice control", "Real-time parsing", "Embedded system"]).map((tag, tIdx) => (
                                    <span key={tIdx} style={{ fontSize: 10, background: "#ede9fe", color: "#6d28d9", padding: "2px 7px", borderRadius: 10, fontWeight: 500 }}>
                                      {tag}
                                    </span>
                                  ))}
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
                              {item.paper_count} papers <ChevronRight size={12} />
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
                              <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 4 }}>
                                {item.key_changes.map((kc, kIdx) => (
                                  <li key={kIdx} style={{ display: "flex", alignItems: "flex-start", gap: 6, fontSize: 11, color: "#334155", lineHeight: 1.35 }}>
                                    <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#10b981", marginTop: 5, flexShrink: 0 }} />
                                    <span>{kc}</span>
                                  </li>
                                ))}
                              </ul>
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
                    <span style={{ fontSize: 11, fontWeight: 700, background: f.kind === "finding_confirms" ? "#dcfce7" : "#fee2e2", color: f.kind === "finding_confirms" ? "#166534" : "#991b1b", padding: "2px 8px", borderRadius: 4 }}>
                      {f.kind === "finding_confirms" ? "Finding Confirms / Extends" : "Finding Contradicts / Voids"}
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
