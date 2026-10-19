import { AlertCircle, BookOpen, CheckCircle2, FileUp, Lightbulb, Star } from "lucide-react";
import { useState } from "react";
import { api, CompareResponse, Workspace } from "../lib/api";

type Props = { workspace: Workspace | null };

export function ComparePage({ workspace }: Props) {
  const [uploading, setUploading] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!workspace) {
    return (
      <section className="page">
        <header className="pageHeader">
          <h1>Compare My Paper</h1>
          <p>Upload your research paper to compare it against the workspace literature.</p>
        </header>
        <div style={{ textAlign: "center", padding: 60, color: "#94a3b8" }}>
          <BookOpen size={40} style={{ margin: "0 auto 12px", display: "block", opacity: 0.4 }} />
          <p>Select a workspace first to compare your paper against its literature.</p>
        </div>
      </section>
    );
  }

  async function handleUpload(file: File) {
    setError(null);
    setResult(null);
    setUploading(true);
    try {
      await api.uploadMyPaper(workspace!.id, file);
      setUploading(false);
      setComparing(true);
      const compare = await api.compareMyPaper(workspace!.id);
      setResult(compare);
    } catch (err: any) {
      setError(err?.message || "Failed to upload or compare paper.");
    } finally {
      setUploading(false);
      setComparing(false);
    }
  }

  const noveltyColor = result
    ? result.novelty_score > 0.6
      ? "#16a34a"
      : result.novelty_score > 0.35
      ? "#d97706"
      : "#dc2626"
    : "#2563eb";

  return (
    <section className="page comparePage">
      <header className="pageHeader inlineHeader">
        <div>
          <h1>Compare My Paper</h1>
          <p>
            Upload your research PDF to compare it against the <strong>{workspace.topic}</strong> workspace literature
            ({workspace.paper_count} papers). Evidence-grounded — no fabricated claims.
          </p>
        </div>
      </header>

      {/* Upload zone */}
      <label className="dropZone" style={{ marginBottom: 24 }}>
        <FileUp size={32} color="#2563eb" />
        <strong style={{ fontSize: 15 }}>
          {uploading ? "Uploading & ingesting PDF…" : comparing ? "Running comparison…" : "Upload Your Paper (PDF)"}
        </strong>
        <span style={{ color: "#64748b", fontSize: 13 }}>
          Your paper will be marked separately from the corpus and compared against workspace papers
        </span>
        <input
          type="file"
          accept="application/pdf"
          disabled={uploading || comparing}
          onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
        />
      </label>

      {error && (
        <div style={{ padding: 14, background: "#fee2e2", color: "#991b1b", borderRadius: 8, marginBottom: 20, fontSize: 13 }}>
          <AlertCircle size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />
          {error}
        </div>
      )}

      {result && (
        <div className="compareLayout">
          {/* Novelty score card */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16, marginBottom: 24 }}>
            <article className="panel" style={{ textAlign: "center" }}>
              <div style={{ fontSize: 42, fontWeight: 800, color: noveltyColor }}>{Math.round(result.novelty_score * 100)}</div>
              <div style={{ fontSize: 13, color: "#475569" }}>Novelty Score / 100</div>
              <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>{result.novelty_formula}</div>
            </article>
            <article className="panel" style={{ textAlign: "center" }}>
              <div style={{ fontSize: 42, fontWeight: 800, color: "#2563eb" }}>{Math.round(result.avg_similarity_to_corpus * 100)}%</div>
              <div style={{ fontSize: 13, color: "#475569" }}>Avg Similarity to Corpus</div>
            </article>
            <article className="panel" style={{ textAlign: "center" }}>
              <div style={{ fontSize: 42, fontWeight: 800, color: "#7c3aed" }}>{result.nearest_neighbours_count}</div>
              <div style={{ fontSize: 13, color: "#475569" }}>Related Papers Found</div>
            </article>
          </div>

          {/* Your paper info */}
          <article className="panel" style={{ marginBottom: 20 }}>
            <div className="sectionTitle">
              <Star size={16} />
              <h2>Your Paper</h2>
            </div>
            <h3 style={{ margin: "0 0 4px" }}>{result.user_paper.title}</h3>
            <p style={{ color: "#475569", fontSize: 13, margin: "0 0 12px" }}>{result.user_paper.authors} · {result.user_paper.year}</p>
            <p><strong>Contribution:</strong> {result.user_paper.contribution}</p>
            <p><strong>Limitation:</strong> {result.user_paper.limitation}</p>
          </article>

          {/* Reviewer critique */}
          <article className="panel" style={{ marginBottom: 20, borderLeft: "4px solid #7c3aed" }}>
            <div className="sectionTitle">
              <Lightbulb size={16} />
              <h2>Reviewer-Style Critique</h2>
            </div>
            <p style={{ lineHeight: 1.7 }}>{result.critique}</p>
            <p style={{ fontSize: 11, color: "#94a3b8", marginTop: 12, fontStyle: "italic" }}>{result.scope_note}</p>
          </article>

          {/* Suggested citations */}
          <article className="panel" style={{ marginBottom: 20 }}>
            <div className="sectionTitle">
              <CheckCircle2 size={16} />
              <h2>Suggested Citations ({result.suggested_citations.length})</h2>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {result.suggested_citations.map((cit) => (
                <div
                  key={cit.title}
                  style={{ padding: "12px 16px", background: "#f8fafc", borderRadius: 8, border: "1px solid #e2e8f0" }}
                >
                  <div style={{ fontWeight: 600, color: "#0f172a" }}>{cit.title}</div>
                  <div style={{ fontSize: 12, color: "#475569" }}>{cit.authors} · {cit.year}</div>
                  <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>{cit.reason}</div>
                  <div
                    style={{
                      display: "inline-block",
                      marginTop: 6,
                      padding: "2px 8px",
                      background: "#eff6ff",
                      color: "#1d4ed8",
                      borderRadius: 12,
                      fontSize: 11,
                    }}
                  >
                    Similarity: {Math.round(cit.similarity_score * 100)}%
                  </div>
                </div>
              ))}
            </div>
          </article>

          {/* Side-by-side comparisons */}
          <article className="panel">
            <div className="sectionTitle">
              <BookOpen size={16} />
              <h2>Side-by-Side Comparisons</h2>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {result.comparisons.map((comp) => (
                <div
                  key={comp.neighbour_title}
                  style={{ padding: 16, background: "#f8fafc", borderRadius: 8, border: "1px solid #e2e8f0" }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                    <strong style={{ color: "#1d4ed8" }}>{comp.neighbour_title}</strong>
                    <span
                      style={{
                        fontSize: 11,
                        background: "#eff6ff",
                        color: "#1d4ed8",
                        padding: "2px 8px",
                        borderRadius: 12,
                      }}
                    >
                      {Math.round(comp.similarity_score * 100)}% similar
                    </span>
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: 12,
                      fontSize: 12,
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, color: "#475569", marginBottom: 4 }}>Corpus Paper</div>
                      <div><strong>Contribution:</strong> {comp.neighbour_contribution}</div>
                      <div style={{ marginTop: 4 }}><strong>Limitation:</strong> {comp.neighbour_limitation}</div>
                    </div>
                    <div>
                      <div style={{ fontWeight: 600, color: "#475569", marginBottom: 4 }}>Your Paper</div>
                      <div><strong>Contribution:</strong> {comp.user_contribution}</div>
                      <div style={{ marginTop: 4 }}><strong>Limitation:</strong> {comp.user_limitation}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </article>
        </div>
      )}
    </section>
  );
}
