import {
  AlertTriangle,
  Bookmark,
  CheckCircle2,
  ExternalLink,
  HelpCircle,
  Lightbulb,
  Quote,
  RefreshCw,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api, Gap, GapMatrixCell, GapMatrixData, Job, Project } from "../lib/api";

export function GapsPage({ project }: { project: Project | null }) {
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [matrix, setMatrix] = useState<GapMatrixData | null>(null);
  const [selectedCell, setSelectedCell] = useState<GapMatrixCell | null>(null);
  const [loading, setLoading] = useState(false);
  const [detectJob, setDetectJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (project) {
      loadGaps();
    }
  }, [project?.id]);

  async function loadGaps() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const [data, mat] = await Promise.all([
        api.gaps.get(project.id),
        api.gaps.matrix(project.id).catch(() => null),
      ]);
      setGaps(data);
      setMatrix(mat);
      setSelectedCell(null);
    } catch (err: any) {
      setError(err?.message || "Failed to load candidate research gaps.");
    } finally {
      setLoading(false);
    }
  }

  async function triggerGapDetection() {
    if (!project) return;
    setError(null);
    try {
      const job = await api.gaps.detect(project.id);
      setDetectJob(job);
      const poll = setInterval(async () => {
        try {
          const updated = await api.jobs.get(job.id);
          setDetectJob(updated);
          if (updated.status === "completed" || updated.status === "failed" || updated.status === "completed_with_warnings") {
            clearInterval(poll);
            if (updated.status === "failed") {
              setError(updated.errors?.[0] || "Gap detection job failed.");
            } else {
              await loadGaps();
            }
          }
        } catch {
          clearInterval(poll);
        }
      }, 1500);
    } catch (err: any) {
      setError(err?.message || "Failed to enqueue gap detection.");
    }
  }

  async function handleFeedback(gapId: number, feedback: string) {
    try {
      await api.gaps.feedback(gapId, feedback);
      setGaps((prev) =>
        prev.map((g) => (g.id === gapId ? { ...g, user_feedback: feedback } : g))
      );
    } catch (err: any) {
      alert(err?.message || "Failed to record feedback.");
    }
  }

  if (!project) {
    return (
      <section className="page" style={{ maxWidth: 800, margin: "40px auto", textAlign: "center" }}>
        <Sparkles size={48} color="#94a3b8" style={{ margin: "0 auto 16px" }} />
        <h2>No Active Research Project</h2>
        <p style={{ color: "#64748b" }}>Please select a research project to inspect candidate research gaps.</p>
      </section>
    );
  }

  return (
    <section className="page gapsPage" style={{ maxWidth: 1050, margin: "0 auto", paddingBottom: 60 }}>
      <header className="pageHeader" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#2563eb", textTransform: "uppercase" }}>
            Evidence Engine
          </span>
          <h1>Candidate Research Gaps: "{project.topic}"</h1>
          <p>
            Synthesized strictly from repeated limitations, unaddressed future work, and method-dataset evaluation voids
            documented in your indexed corpus. Never claims total absence in scientific literature.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={loadGaps}
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
            <RefreshCw size={14} /> Refresh
          </button>
          <button
            onClick={triggerGapDetection}
            disabled={loading || (detectJob?.status === "pending" || detectJob?.status === "analysing" || detectJob?.status === "processing")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "8px 14px",
              background: "#2563eb",
              color: "white",
              border: "none",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <Sparkles size={14} /> Detect Gaps
          </button>
        </div>
      </header>

      {detectJob && (detectJob.status !== "completed" || detectJob.progress < 1) && (
        <div style={{ padding: 14, background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 8, marginBottom: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#1e40af", marginBottom: 6 }}>
            <span><strong>Gap Detection Job:</strong> {detectJob.stage} ({detectJob.status})</span>
            <span>{Math.round((detectJob.progress || 0) * 100)}%</span>
          </div>
          <div style={{ height: 6, background: "#dbeafe", borderRadius: 3, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${Math.round((detectJob.progress || 0) * 100)}%`, background: "#2563eb", transition: "width 0.3s" }} />
          </div>
        </div>
      )}

      {error && (
        <div style={{ padding: 16, background: "#fee2e2", color: "#991b1b", borderRadius: 8, marginBottom: 20 }}>
          {error}
        </div>
      )}

      {/* T12 Auditable Method x Task/Dataset Evaluation Matrix Heatmap */}
      {matrix && matrix.methods.length > 0 && matrix.tasks.length > 0 && (
        <article className="panel" style={{ padding: 18, marginBottom: 22, overflowX: "auto" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <div>
              <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "#0f172a" }}>
                Method × Task/Dataset Evaluation Matrix
              </h3>
              <p style={{ margin: "2px 0 0", fontSize: 12, color: "#64748b" }}>
                Amber-outlined zero/sparse cells indicate statistically under-explored combinations (hypergeometric p-value &amp; PMI over {matrix.total_papers} papers). Click a cell to inspect.
              </p>
            </div>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "6px 8px", borderBottom: "1px solid #e2e8f0", color: "#475569" }}>Method \ Task</th>
                {matrix.tasks.slice(0, 8).map((t) => (
                  <th key={t} style={{ padding: "6px 8px", borderBottom: "1px solid #e2e8f0", color: "#334155", maxWidth: 110, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={t}>
                    {t}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.methods.slice(0, 8).map((m) => (
                <tr key={m}>
                  <td style={{ padding: "6px 8px", borderBottom: "1px solid #f1f5f9", fontWeight: 600, color: "#0f172a", maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={m}>
                    {m}
                  </td>
                  {matrix.tasks.slice(0, 8).map((t) => {
                    const cell = matrix.cells.find((c) => c.method === m && c.task === t);
                    const cnt = cell?.count ?? 0;
                    const isVoid = Boolean(cell?.is_candidate_void);
                    const bg = cnt === 0 ? (isVoid ? "#fffbeb" : "#f8fafc") : cnt === 1 ? "#dbeafe" : "#93c5fd";
                    return (
                      <td
                        key={`${m}__${t}`}
                        onClick={() => cell && setSelectedCell(cell)}
                        style={{
                          padding: "6px 8px",
                          textAlign: "center",
                          cursor: "pointer",
                          background: bg,
                          border: isVoid ? "2px dashed #f59e0b" : "1px solid #e2e8f0",
                          fontWeight: isVoid || cnt > 0 ? 700 : 400,
                          color: isVoid ? "#92400e" : "#1e293b",
                        }}
                      >
                        {cnt}{isVoid ? " · void" : ""}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          {selectedCell && (
            <div style={{ marginTop: 10, padding: "8px 12px", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 6, fontSize: 12, color: "#334155" }}>
              <strong>{selectedCell.method}</strong> × <strong>{selectedCell.task}</strong>: observed={selectedCell.count}, expected={selectedCell.expected}, PMI={selectedCell.pmi}, hypergeom p={selectedCell.hypergeom_p}.
              {selectedCell.papers.length > 0 && (
                <span> Papers: {selectedCell.papers.map((p) => p.title).join("; ")}</span>
              )}
            </div>
          )}
        </article>
      )}

      {loading ? (
        <p style={{ color: "#64748b" }}>Synthesizing candidate gaps from paper limitations...</p>
      ) : gaps.length === 0 ? (
        <article className="panel" style={{ padding: 32, textAlign: "center", color: "#64748b" }}>
          <Lightbulb size={36} style={{ margin: "0 auto 12px", opacity: 0.5 }} />
          <h3>No Evidence-Backed Gaps Detected</h3>
          <p style={{ fontSize: 13, maxWidth: 500, margin: "0 auto" }}>
            The current indexed papers do not provide enough converging limitation or future-work signals.
            The system refuses to pad or fabricate generic gaps. Try discovering and processing additional papers.
          </p>
        </article>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {gaps.map((g) => {
            const comp = g.score_components || {};
            const ext = g.external_verification || {};
            return (
              <article
                key={g.id}
                className="panel"
                style={{
                  padding: 24,
                  border: "1px solid #e2e8f0",
                  background: "white",
                }}
              >
                {/* Header & Score */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                  <div>
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 600,
                        textTransform: "uppercase",
                        padding: "2px 8px",
                        borderRadius: 10,
                        background: "#f1f5f9",
                        color: "#475569",
                        marginRight: 8,
                      }}
                    >
                      Type: {g.gap_type.replace(/_/g, " ")}
                    </span>
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 700,
                        padding: "2px 8px",
                        borderRadius: 10,
                        background: "#dbeafe",
                        color: "#1d4ed8",
                        marginRight: 8,
                      }}
                    >
                      Evidence Score: {g.evidence_strength.toFixed(2)}
                    </span>
                    {g.status === "likely_addressed" && (
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 700,
                          padding: "2px 8px",
                          borderRadius: 10,
                          background: "#fef3c7",
                          color: "#92400e",
                        }}
                      >
                        Likely Addressed Externally
                      </span>
                    )}
                  </div>

                  {/* Feedback Controls */}
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      onClick={() => handleFeedback(g.id, "relevant")}
                      style={{
                        padding: "4px 8px",
                        borderRadius: 4,
                        border: "1px solid #cbd5e1",
                        background: g.user_feedback === "relevant" ? "#dcfce7" : "white",
                        color: g.user_feedback === "relevant" ? "#166534" : "#475569",
                        fontSize: 11,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                      }}
                      title="Mark as Relevant"
                    >
                      <ThumbsUp size={12} /> Relevant
                    </button>

                    <button
                      onClick={() => handleFeedback(g.id, "needs_evidence")}
                      style={{
                        padding: "4px 8px",
                        borderRadius: 4,
                        border: "1px solid #cbd5e1",
                        background: g.user_feedback === "needs_evidence" ? "#fef3c7" : "white",
                        color: g.user_feedback === "needs_evidence" ? "#92400e" : "#475569",
                        fontSize: 11,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                      }}
                      title="Needs More Evidence"
                    >
                      <HelpCircle size={12} /> Needs Evidence
                    </button>

                    <button
                      onClick={() => handleFeedback(g.id, "saved")}
                      style={{
                        padding: "4px 8px",
                        borderRadius: 4,
                        border: "1px solid #cbd5e1",
                        background: g.user_feedback === "saved" ? "#eff6ff" : "white",
                        color: g.user_feedback === "saved" ? "#1d4ed8" : "#475569",
                        fontSize: 11,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                      }}
                      title="Save to Workspace"
                    >
                      <Bookmark size={12} /> Save
                    </button>
                  </div>
                </div>

                {/* Gap Statement */}
                <h3 style={{ fontSize: 17, fontWeight: 700, color: "#0f172a", margin: "0 0 8px", lineHeight: 1.4 }}>
                  {g.gap_statement}
                </h3>

                {/* Why It Matters */}
                <p style={{ fontSize: 13, color: "#334155", lineHeight: 1.6, marginBottom: 16 }}>
                  <strong>Why it matters:</strong> {g.why_it_matters}
                </p>

                {/* Supporting Evidence Cards */}
                {g.supporting_evidence && g.supporting_evidence.length > 0 && (
                  <div style={{ background: "#f8fafc", padding: 16, borderRadius: 6, marginBottom: 16 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "#0f172a", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
                      <Quote size={14} color="#2563eb" /> Grounded Evidence in Corpus ({g.supporting_evidence.length}):
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {g.supporting_evidence.map((ev, i) => (
                        <div key={i} style={{ fontSize: 12, color: "#334155", borderLeft: "3px solid #2563eb", paddingLeft: 10 }}>
                          <span style={{ fontWeight: 600, color: "#1e293b" }}>{ev.paper_title || "Corpus Paper"}</span>
                          {ev.page ? <span style={{ color: "#64748b" }}> (Page {ev.page})</span> : null}:
                          {ev.quote ? (
                            <p style={{ fontStyle: "italic", margin: "2px 0 0", color: "#475569" }}>"{ev.quote}"</p>
                          ) : (
                            <p style={{ margin: "2px 0 0" }}>{ev.limitation_observed || "Documented technical barrier"}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Research Question & Proposed Validation */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
                  <div style={{ background: "#eff6ff", padding: 12, borderRadius: 6, fontSize: 12 }}>
                    <strong style={{ color: "#1d4ed8", display: "block", marginBottom: 4 }}>Candidate Research Question:</strong>
                    <span style={{ color: "#1e293b" }}>{g.suggested_research_question}</span>
                  </div>
                  <div style={{ background: "#f0fdf4", padding: 12, borderRadius: 6, fontSize: 12 }}>
                    <strong style={{ color: "#166534", display: "block", marginBottom: 4 }}>Proposed Validation / Experiment:</strong>
                    <span style={{ color: "#1e293b" }}>{g.suggested_validation}</span>
                  </div>
                </div>

                {/* Limitations of Corpus Disclosure */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 8,
                    background: "#fffbeb",
                    padding: "10px 14px",
                    borderRadius: 6,
                    border: "1px solid #fef3c7",
                    fontSize: 12,
                    color: "#92400e",
                    marginBottom: 12,
                  }}
                >
                  <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
                  <div>
                    <strong>Corpus Limitation Disclosure:</strong> {g.corpus_cannot_establish}
                  </div>
                </div>

                {/* External OpenAlex Check */}
                {ext.searched_terms && (
                  <div style={{ fontSize: 11, color: "#64748b", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span>
                      External OpenAlex verification on <em>"{ext.searched_terms}"</em>: {ext.external_papers_found} related papers located.
                    </span>
                    <span style={{ color: "#94a3b8" }}>Formula: {comp.formula || "Transparent weighted score"}</span>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
