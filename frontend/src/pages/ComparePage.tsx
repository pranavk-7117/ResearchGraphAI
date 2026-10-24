import {
  AlertCircle,
  CheckCircle2,
  FileText,
  FileUp,
  GitMerge,
  HelpCircle,
  Layers,
  Sparkles,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api, PaperAnalysis, Project } from "../lib/api";

export function ComparePage({ project }: { project: Project | null }) {
  const [analyses, setAnalyses] = useState<PaperAnalysis[]>([]);
  const [selectedAnalysis, setSelectedAnalysis] = useState<PaperAnalysis | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (project) {
      loadAnalyses();
    }
  }, [project?.id]);

  async function loadAnalyses() {
    if (!project) return;
    try {
      const data = await api.upload.listAnalyses(project.id);
      setAnalyses(data);
      if (data.length > 0 && !selectedAnalysis) {
        setSelectedAnalysis(data[0]);
      }
    } catch {
      // ignore
    }
  }

  async function handleUpload(file: File) {
    if (!project) return;
    setUploading(true);
    setError(null);
    try {
      const analysis = await api.upload.compare(project.id, file);
      setSelectedAnalysis(analysis);
      await loadAnalyses();
    } catch (err: any) {
      setError(err?.message || "Failed to upload and compare manuscript.");
    } finally {
      setUploading(false);
    }
  }

  if (!project) {
    return (
      <section className="page" style={{ maxWidth: 800, margin: "40px auto", textAlign: "center" }}>
        <GitMerge size={48} color="#94a3b8" style={{ margin: "0 auto 16px" }} />
        <h2>No Active Research Project</h2>
        <p style={{ color: "#64748b" }}>Please select a research project to compare uploaded manuscripts.</p>
      </section>
    );
  }

  const report = selectedAnalysis?.report || {};

  return (
    <section className="page comparePage" style={{ maxWidth: 1100, margin: "0 auto", paddingBottom: 60 }}>
      <header className="pageHeader">
        <div>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#2563eb", textTransform: "uppercase" }}>
            Manuscript Assessment
          </span>
          <h1>Upload & Literature Comparison: "{project.topic}"</h1>
          <p>
            Drop in an academic draft or pre-print to benchmark its contributions, gap alignment, methodology,
            and missing comparisons against your project's indexed corpus.
          </p>
        </div>
      </header>

      {/* Upload Drop Zone */}
      <label
        className="dropZone"
        style={{
          border: "2px dashed #cbd5e1",
          borderRadius: 8,
          padding: 32,
          textAlign: "center",
          background: "#f8fafc",
          display: "block",
          cursor: uploading ? "wait" : "pointer",
          marginBottom: 24,
        }}
      >
        <FileUp size={36} color="#2563eb" style={{ margin: "0 auto 8px" }} />
        <strong style={{ fontSize: 15, display: "block", marginBottom: 4 }}>
          {uploading ? "Ingesting and benchmarking manuscript against corpus..." : "Choose a Manuscript PDF to Compare"}
        </strong>
        <span style={{ fontSize: 12, color: "#64748b" }}>
          PDF will be securely uploaded to private storage, parsed per-page, and evaluated against the active corpus
        </span>
        <input
          type="file"
          accept="application/pdf"
          disabled={uploading}
          onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
          style={{ display: "none" }}
        />
      </label>

      {error && (
        <div style={{ padding: 16, background: "#fee2e2", color: "#991b1b", borderRadius: 8, marginBottom: 20 }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Prior Analyses Switcher */}
      {analyses.length > 1 && (
        <div style={{ display: "flex", gap: 8, overflowX: "auto", marginBottom: 20, paddingBottom: 6 }}>
          {analyses.map((a) => (
            <button
              key={a.id}
              onClick={() => setSelectedAnalysis(a)}
              style={{
                padding: "6px 12px",
                borderRadius: 6,
                border: selectedAnalysis?.id === a.id ? "1.5px solid #2563eb" : "1px solid #cbd5e1",
                background: selectedAnalysis?.id === a.id ? "#eff6ff" : "white",
                color: selectedAnalysis?.id === a.id ? "#1d4ed8" : "#475569",
                fontSize: 12,
                cursor: "pointer",
                whiteSpace: "nowrap",
              }}
            >
              {a.paper_title.slice(0, 30)}...
            </button>
          ))}
        </div>
      )}

      {/* Analysis Report Card */}
      {selectedAnalysis ? (
        <article className="panel" style={{ padding: 24, background: "white", border: "1px solid #e2e8f0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
            <div>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  padding: "2px 8px",
                  borderRadius: 10,
                  background: "#dcfce7",
                  color: "#166534",
                }}
              >
                Benchmarked Against Corpus
              </span>
              <h2 style={{ fontSize: 18, fontWeight: 700, margin: "8px 0 4px", color: "#0f172a" }}>
                {selectedAnalysis.paper_title}
              </h2>
            </div>
          </div>

          {/* Semantic Distance Disclosure */}
          {report.semantic_distance_label && (
            <div
              style={{
                background: "#f0fdf4",
                border: "1px solid #bbf7d0",
                padding: "10px 14px",
                borderRadius: 6,
                fontSize: 12,
                color: "#166534",
                marginBottom: 20,
              }}
            >
              <strong>Semantic Distance Provenance:</strong> {report.semantic_distance_label}
            </div>
          )}

          {/* Section: Overview & Problem */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
            <div style={{ background: "#f8fafc", padding: 14, borderRadius: 6, border: "1px solid #e2e8f0" }}>
              <strong style={{ fontSize: 13, color: "#0f172a", display: "block", marginBottom: 4 }}>
                Premise & Overview:
              </strong>
              <p style={{ fontSize: 13, color: "#334155", margin: 0, lineHeight: 1.5 }}>
                {report.overview || "Overview extracted from manuscript"}
              </p>
            </div>
            <div style={{ background: "#f8fafc", padding: 14, borderRadius: 6, border: "1px solid #e2e8f0" }}>
              <strong style={{ fontSize: 13, color: "#0f172a", display: "block", marginBottom: 4 }}>
                Core Problem Addressed:
              </strong>
              <p style={{ fontSize: 13, color: "#334155", margin: 0, lineHeight: 1.5 }}>
                {report.problem || "Problem defined in manuscript"}
              </p>
            </div>
          </div>

          {/* Claimed Contributions */}
          {report.claimed_contributions && report.claimed_contributions.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <strong style={{ fontSize: 13, color: "#0f172a", display: "block", marginBottom: 8 }}>
                Claimed Scientific Contributions:
              </strong>
              <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: "#334155", lineHeight: 1.6 }}>
                {report.claimed_contributions.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Gap Alignment */}
          {report.gap_alignment && (
            <div style={{ background: "#eff6ff", border: "1px solid #bfdbfe", padding: 16, borderRadius: 6, marginBottom: 20 }}>
              <strong style={{ fontSize: 13, color: "#1d4ed8", display: "block", marginBottom: 4 }}>
                Corpus Gap Alignment: Status: {report.gap_alignment.status || "Evaluated"}
              </strong>
              <p style={{ fontSize: 13, color: "#1e293b", margin: 0, lineHeight: 1.5 }}>
                {report.gap_alignment.explanation}
              </p>
            </div>
          )}

          {/* Candidate Uncited Literature */}
          {report.candidate_uncited_comparisons && report.candidate_uncited_comparisons.length > 0 && (
            <div style={{ background: "#fffbeb", border: "1px solid #fef3c7", padding: 16, borderRadius: 6, marginBottom: 20 }}>
              <strong style={{ fontSize: 13, color: "#92400e", display: "block", marginBottom: 8 }}>
                Candidate Relevant Literature to Compare or Cite:
              </strong>
              <ul style={{ margin: 0, paddingLeft: 20, fontSize: 12, color: "#78350f", lineHeight: 1.6 }}>
                {report.candidate_uncited_comparisons.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Suggested Improvements & Next Experiments */}
          {report.suggested_improvements && report.suggested_improvements.length > 0 && (
            <div>
              <strong style={{ fontSize: 13, color: "#0f172a", display: "block", marginBottom: 8 }}>
                Suggested Next Experiments & Benchmarks:
              </strong>
              <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: "#334155", lineHeight: 1.6 }}>
                {report.suggested_improvements.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}
        </article>
      ) : (
        <article className="panel" style={{ padding: 32, textAlign: "center", color: "#64748b" }}>
          <FileText size={36} style={{ margin: "0 auto 12px", opacity: 0.5 }} />
          <h3>No Manuscript Uploaded Yet</h3>
          <p style={{ fontSize: 13 }}>
            Upload an academic draft or PDF manuscript above to view its comparative analysis report.
          </p>
        </article>
      )}
    </section>
  );
}
