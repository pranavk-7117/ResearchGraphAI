import {
  Check,
  CheckSquare,
  Compass,
  Download,
  ExternalLink,
  FileText,
  Filter,
  Play,
  Search,
  Sparkles,
  Square,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api, Job, Paper, Project } from "../lib/api";

export function DiscoverPage({
  project,
  onProcessingComplete,
}: {
  project: Project | null;
  onProcessingComplete: () => void;
}) {
  const [candidates, setCandidates] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Discovery parameters
  const [limit, setLimit] = useState(25);
  const [rankingMode, setRankingMode] = useState("balanced");
  const [oaOnly, setOaOnly] = useState(false);
  const [yearMin, setYearMin] = useState<number | undefined>();
  const [yearMax, setYearMax] = useState<number | undefined>();

  // Active Background Job
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (project) {
      loadCandidates();
    }
  }, [project?.id]);

  // Polling loop for active background job
  useEffect(() => {
    if (!activeJob || activeJob.status === "completed" || activeJob.status === "failed") {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const updated = await api.jobs.get(activeJob.id);
        setActiveJob(updated);
        if (updated.status === "completed" || updated.status === "completed_with_warnings") {
          clearInterval(interval);
          if (updated.type === "discovery") {
            loadCandidates();
          } else if (updated.type === "processing") {
            onProcessingComplete();
          }
        }
      } catch {
        // ignore poll errors
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [activeJob?.id, activeJob?.status]);

  async function loadCandidates() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.discovery.getCandidates(project.id);
      setCandidates(data);
      // Select all by default if none selected
      const ids = new Set<number>();
      data.forEach((p) => {
        if (p.selected) ids.add(p.id);
      });
      setSelectedIds(ids);
    } catch (err: any) {
      setError(err?.message || "Failed to load candidates.");
    } finally {
      setLoading(false);
    }
  }

  async function startDiscovery() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const job = await api.discovery.trigger(project.id, {
        limit,
        ranking_mode: rankingMode,
        oa_only: oaOnly,
        year_min: yearMin,
        year_max: yearMax,
      });
      setActiveJob(job);
    } catch (err: any) {
      setError(err?.message || "Discovery job initiation failed.");
      setLoading(false);
    }
  }

  function toggleSelect(id: number) {
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelectedIds(next);
  }

  function toggleSelectAll() {
    if (selectedIds.size === candidates.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(candidates.map((c) => c.id)));
    }
  }

  async function triggerProcessing() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      // 1. Sync candidate selection to backend
      await api.discovery.selectCandidates(
        project.id,
        Array.from(selectedIds),
        selectedIds.size === candidates.length
      );
      // 2. Trigger durable background processing
      const job = await api.discovery.triggerProcessing(project.id);
      setActiveJob(job);
    } catch (err: any) {
      setError(err?.message || "Failed to initiate processing pipeline.");
      setLoading(false);
    }
  }

  if (!project) {
    return (
      <section className="page" style={{ maxWidth: 800, margin: "40px auto", textAlign: "center" }}>
        <Compass size={48} color="#94a3b8" style={{ margin: "0 auto 16px" }} />
        <h2>No Active Research Project</h2>
        <p style={{ color: "#64748b" }}>
          Please select or create a research project from the Projects dashboard first.
        </p>
      </section>
    );
  }

  return (
    <section className="page" style={{ maxWidth: 1100, margin: "0 auto", paddingBottom: 60 }}>
      <header className="pageHeader">
        <div>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#2563eb", textTransform: "uppercase" }}>
            Discovery Engine · Project #{project.id}
          </span>
          <h1>Literature Discovery: "{project.topic}"</h1>
          <p>
            Searches OpenAlex, Semantic Scholar, and arXiv. Candidates are ranked using dense semantic vectors,
            recency, and citation authority. Nothing is downloaded until you select papers below.
          </p>
        </div>
      </header>

      {/* Discovery Controls Panel */}
      <article className="panel" style={{ padding: 20, marginBottom: 24 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16 }}>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#475569", display: "block", marginBottom: 6 }}>
              Candidate Limit
            </label>
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #cbd5e1" }}
            >
              <option value={15}>15 Papers</option>
              <option value={25}>25 Papers (Recommended)</option>
              <option value={50}>50 Papers</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#475569", display: "block", marginBottom: 6 }}>
              Ranking Mode
            </label>
            <select
              value={rankingMode}
              onChange={(e) => setRankingMode(e.target.value)}
              style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #cbd5e1" }}
            >
              <option value="balanced">Balanced (Relevance + Recency + Citations)</option>
              <option value="relevant">Most Relevant (Vector Similarity)</option>
              <option value="recent">Recent Advances (Recency Weighted)</option>
              <option value="citations">Highly Cited (Foundational Authority)</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#475569", display: "block", marginBottom: 6 }}>
              Open Access Filter
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, fontSize: 13, cursor: "pointer" }}>
              <input type="checkbox" checked={oaOnly} onChange={(e) => setOaOnly(e.target.checked)} />
              Free Full-Text PDF only
            </label>
          </div>

          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <button
              onClick={startDiscovery}
              disabled={loading || (activeJob && activeJob.status !== "completed" && activeJob.status !== "failed")}
              style={{
                width: "100%",
                padding: "9px 16px",
                background: "#2563eb",
                color: "white",
                border: "none",
                borderRadius: 6,
                fontWeight: 600,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
                cursor: "pointer",
              }}
            >
              <Search size={16} /> Discover Candidates
            </button>
          </div>
        </div>
      </article>

      {/* Background Job Progress Card */}
      {activeJob && activeJob.status !== "completed" && activeJob.status !== "failed" && (
        <article
          className="panel"
          style={{
            padding: 20,
            marginBottom: 24,
            borderLeft: "4px solid #2563eb",
            background: "#eff6ff",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <strong>
              Job in Progress: {activeJob.type === "discovery" ? "Discovering Candidates" : "Processing Literature"}
            </strong>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#1d4ed8" }}>
              {Math.round(activeJob.progress * 100)}%
            </span>
          </div>
          <div style={{ height: 6, background: "#dbeafe", borderRadius: 3, overflow: "hidden", marginBottom: 8 }}>
            <div
              style={{
                height: "100%",
                background: "#2563eb",
                width: `${Math.round(activeJob.progress * 100)}%`,
                transition: "width 0.4s ease",
              }}
            />
          </div>
          <div style={{ fontSize: 12, color: "#475569" }}>
            Stage: <code>{activeJob.stage}</code>
          </div>
        </article>
      )}

      {error && (
        <div style={{ marginBottom: 20, padding: 16, background: "#fee2e2", color: "#991b1b", borderRadius: 8 }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Candidate List Header & Action */}
      {candidates.length > 0 && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button
              onClick={toggleSelectAll}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                background: "none",
                border: "none",
                fontSize: 13,
                color: "#1e293b",
                cursor: "pointer",
              }}
            >
              {selectedIds.size === candidates.length ? <CheckSquare size={16} /> : <Square size={16} />}
              Select All ({candidates.length})
            </button>
            <span style={{ fontSize: 13, color: "#64748b" }}>
              {selectedIds.size} paper(s) selected
            </span>
          </div>

          <button
            onClick={triggerProcessing}
            disabled={selectedIds.size === 0 || loading}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "10px 20px",
              background: selectedIds.size > 0 ? "#16a34a" : "#94a3b8",
              color: "white",
              border: "none",
              borderRadius: 6,
              fontWeight: 600,
              cursor: selectedIds.size > 0 ? "pointer" : "not-allowed",
            }}
          >
            <Play size={16} /> Process Selected ({selectedIds.size})
          </button>
        </div>
      )}

      {/* Candidate Papers List */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {candidates.map((c, idx) => {
          const isSelected = selectedIds.has(c.id);
          const comp = c.score_components || {};
          return (
            <article
              key={c.id}
              className="panel"
              style={{
                padding: 16,
                border: isSelected ? "1.5px solid #2563eb" : "1px solid #e2e8f0",
                background: isSelected ? "#f8fafc" : "white",
              }}
            >
              <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => toggleSelect(c.id)}
                  style={{ marginTop: 4, cursor: "pointer", width: 16, height: 16 }}
                />
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 4 }}>
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 700,
                        background: "#e2e8f0",
                        padding: "2px 6px",
                        borderRadius: 4,
                        color: "#334155",
                      }}
                    >
                      Rank #{idx + 1}
                    </span>
                    <span style={{ fontSize: 11, fontWeight: 600, color: "#2563eb" }}>
                      Score: {c.relevance_score.toFixed(3)}
                    </span>
                    {c.oa_pdf_url ? (
                      <span
                        style={{
                          fontSize: 11,
                          background: "#dcfce7",
                          color: "#166534",
                          padding: "2px 8px",
                          borderRadius: 10,
                          fontWeight: 500,
                        }}
                      >
                        Open Access PDF
                      </span>
                    ) : (
                      <span
                        style={{
                          fontSize: 11,
                          background: "#f1f5f9",
                          color: "#64748b",
                          padding: "2px 8px",
                          borderRadius: 10,
                        }}
                      >
                        Metadata Only
                      </span>
                    )}
                    <span style={{ fontSize: 11, color: "#64748b" }}>
                      Source: {c.source_name} · Year: {c.year || "n.d."} · Citations: {c.citation_count}
                    </span>
                  </div>

                  <h3 style={{ fontSize: 15, fontWeight: 600, margin: "4px 0", color: "#0f172a" }}>
                    {c.title}
                  </h3>

                  <p style={{ fontSize: 12, color: "#475569", margin: "4px 0 8px" }}>
                    {c.authors && c.authors.length > 0
                      ? c.authors.map((a) => a.name).join(", ")
                      : "Authors available upon download"}
                  </p>

                  {c.abstract && (
                    <p style={{ fontSize: 13, color: "#334155", lineHeight: 1.5, margin: "6px 0" }}>
                      {c.abstract.slice(0, 280)}...
                    </p>
                  )}

                  {/* Why Ranked Score Breakdown */}
                  <div
                    style={{
                      display: "flex",
                      gap: 12,
                      flexWrap: "wrap",
                      fontSize: 11,
                      color: "#64748b",
                      marginTop: 8,
                      paddingTop: 8,
                      borderTop: "1px solid #f1f5f9",
                    }}
                  >
                    <span><strong>Why Ranked:</strong></span>
                    <span>Semantic: {(comp.semantic_relevance ?? 0).toFixed(2)}</span>
                    <span>Recency: {(comp.recency_score ?? 0).toFixed(2)}</span>
                    <span>Influence: {(comp.citation_influence ?? 0).toFixed(2)}</span>
                    <span>OA: {(comp.open_access_score ?? 0).toFixed(2)}</span>
                    {c.url && (
                      <a
                        href={c.url}
                        target="_blank"
                        rel="noreferrer"
                        style={{ marginLeft: "auto", color: "#2563eb", display: "flex", alignItems: "center", gap: 3 }}
                      >
                        Source Link <ExternalLink size={12} />
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
