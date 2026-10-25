import { Bookmark, Calendar, CheckCircle2, ChevronRight, GitFork, Info, Layers, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { api, EvolutionData, Project } from "../lib/api";

type TabView = "citation_timeline" | "method_progression" | "finding_dynamics";

export function EvolutionPage({ project }: { project: Project | null }) {
  const [activeTab, setActiveTab] = useState<TabView>("citation_timeline");
  const [data, setData] = useState<EvolutionData>({
    citation_timeline: [],
    method_progression: [],
    finding_dynamics: [],
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      const res = await api.evolution.get(project.id);
      setData(res);
      if (res.citation_timeline.length === 0 && res.method_progression.length > 0) {
        setActiveTab("method_progression");
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load evolution analysis.");
    } finally {
      setLoading(false);
    }
  }

  if (!project) {
    return (
      <section className="page" style={{ maxWidth: 800, margin: "40px auto", textAlign: "center" }}>
        <GitFork size={48} color="#94a3b8" style={{ margin: "0 auto 16px" }} />
        <h2>No Active Research Project</h2>
        <p style={{ color: "#64748b" }}>Please select a research project to view literature evolution.</p>
      </section>
    );
  }

  const currentItems = data[activeTab] || [];

  return (
    <section className="page evolutionPage" style={{ maxWidth: 1050, margin: "0 auto", paddingBottom: 60 }}>
      <header className="pageHeader" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#2563eb", textTransform: "uppercase" }}>
            Scientific Trajectory
          </span>
          <h1>Literature Evolution: "{project.topic}"</h1>
          <p>
            Traces chronological succession, empirical method progressions, and verified citation lineages across this corpus.
          </p>
        </div>
        <button
          onClick={loadEvolution}
          disabled={loading}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "8px 14px",
            background: "#f1f5f9",
            border: "1px solid #cbd5e1",
            borderRadius: 6,
            fontSize: 12,
            cursor: "pointer",
          }}
        >
          <RefreshCw size={14} /> Refresh Analysis
        </button>
      </header>

      {/* View Switcher Tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 24, borderBottom: "1px solid #e2e8f0", paddingBottom: 12 }}>
        <button
          onClick={() => setActiveTab("citation_timeline")}
          style={{
            padding: "8px 16px",
            borderRadius: 6,
            border: "none",
            fontSize: 13,
            fontWeight: activeTab === "citation_timeline" ? 600 : 400,
            background: activeTab === "citation_timeline" ? "#2563eb" : "#f1f5f9",
            color: activeTab === "citation_timeline" ? "white" : "#475569",
            cursor: "pointer",
          }}
        >
          1. Verified Citation Timeline ({data.citation_timeline.length})
        </button>

        <button
          onClick={() => setActiveTab("method_progression")}
          style={{
            padding: "8px 16px",
            borderRadius: 6,
            border: "none",
            fontSize: 13,
            fontWeight: activeTab === "method_progression" ? 600 : 400,
            background: activeTab === "method_progression" ? "#2563eb" : "#f1f5f9",
            color: activeTab === "method_progression" ? "white" : "#475569",
            cursor: "pointer",
          }}
        >
          2. Method & Metric Progression ({data.method_progression.length})
        </button>

        <button
          onClick={() => setActiveTab("finding_dynamics")}
          style={{
            padding: "8px 16px",
            borderRadius: 6,
            border: "none",
            fontSize: 13,
            fontWeight: activeTab === "finding_dynamics" ? 600 : 400,
            background: activeTab === "finding_dynamics" ? "#2563eb" : "#f1f5f9",
            color: activeTab === "finding_dynamics" ? "white" : "#475569",
            cursor: "pointer",
          }}
        >
          3. Finding Dynamics & Consensus ({data.finding_dynamics.length})
        </button>
      </div>

      {error && (
        <div style={{ padding: 16, background: "#fee2e2", color: "#991b1b", borderRadius: 8, marginBottom: 20 }}>
          {error}
        </div>
      )}

      {loading ? (
        <p style={{ color: "#64748b" }}>Analyzing evolution chain from corpus facts...</p>
      ) : currentItems.length === 0 ? (
        <article className="panel" style={{ padding: 36, textAlign: "center", color: "#64748b" }}>
          <Info size={36} style={{ margin: "0 auto 12px", opacity: 0.6, color: "#3b82f6" }} />
          <h3 style={{ marginBottom: 8, color: "#1e293b" }}>No Transitions in this Specific View</h3>
          <p style={{ fontSize: 13, maxWidth: 520, margin: "0 auto 16px", lineHeight: 1.5 }}>
            {activeTab === "citation_timeline"
              ? "No direct verified citation records exist between these specific papers (papers were published independently across different venues)."
              : "Insufficient extracted signals to establish chronological progression in this view."}
          </p>
          {data.method_progression.length > 0 && activeTab !== "method_progression" && (
            <button
              onClick={() => setActiveTab("method_progression")}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                padding: "9px 18px",
                background: "#2563eb",
                color: "white",
                border: "none",
                borderRadius: 6,
                fontSize: 13,
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              Switch to Method & Metric Progression ({data.method_progression.length} transitions) <ChevronRight size={15} />
            </button>
          )}
        </article>
      ) : (
        <div style={{ position: "relative", paddingLeft: 24, borderLeft: "2px solid #cbd5e1", display: "flex", flexDirection: "column", gap: 24 }}>
          {currentItems.map((item, idx) => (
            <article
              key={idx}
              className="panel"
              style={{
                position: "relative",
                padding: 20,
                border: "1px solid #e2e8f0",
                background: "white",
              }}
            >
              {/* Dot on the timeline rail */}
              <div
                style={{
                  position: "absolute",
                  left: -31,
                  top: 24,
                  width: 12,
                  height: 12,
                  borderRadius: "50%",
                  background: item.basis === "citation_metadata" ? "#0f766e" : "#2563eb",
                  border: "2px solid white",
                  boxShadow: "0 0 0 2px #cbd5e1",
                }}
              />

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      padding: "2px 8px",
                      borderRadius: 10,
                      background: item.basis === "citation_metadata" ? "#ccfbf1" : "#dbeafe",
                      color: item.basis === "citation_metadata" ? "#0f766e" : "#1d4ed8",
                    }}
                  >
                    Basis: {item.basis}
                  </span>
                  <span style={{ fontSize: 11, color: "#64748b" }}>
                    Kind: {item.kind}
                  </span>
                </div>
              </div>

              {/* Transition Header */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  background: "#f8fafc",
                  padding: "10px 14px",
                  borderRadius: 6,
                  marginBottom: 12,
                  fontSize: 13,
                }}
              >
                <div style={{ flex: 1 }}>
                  <strong style={{ color: "#0f172a" }}>{item.from_paper.title}</strong>
                  <span style={{ color: "#64748b", marginLeft: 6 }}>({item.from_paper.year || "n.d."})</span>
                </div>
                <ChevronRight size={18} color="#94a3b8" />
                <div style={{ flex: 1 }}>
                  <strong style={{ color: "#0f172a" }}>{item.to_paper.title}</strong>
                  <span style={{ color: "#64748b", marginLeft: 6 }}>({item.to_paper.year || "n.d."})</span>
                </div>
              </div>

              {/* Grounded Explanation */}
              <p style={{ fontSize: 13, color: "#334155", lineHeight: 1.6, margin: 0 }}>
                {item.explanation}
              </p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
