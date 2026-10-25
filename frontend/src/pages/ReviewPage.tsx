import { BookOpen, Copy, Download, FileText, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { api, LiteratureReview, Project } from "../lib/api";

export function ReviewPage({ project }: { project: Project | null }) {
  const [review, setReview] = useState<LiteratureReview | null>(null);
  const [bibtex, setBibtex] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (project) {
      loadReviewAndBibtex();
    }
  }, [project?.id]);

  async function loadReviewAndBibtex() {
    if (!project) return;
    loadBibtex();
    try {
      const existing = await api.review.get(project.id);
      if (existing) {
        setReview(existing);
      }
    } catch {
      // not generated yet
    }
  }

  async function loadBibtex() {
    if (!project) return;
    try {
      const res = await api.review.bibtex(project.id);
      setBibtex(res.bibtex);
    } catch {
      // ignore
    }
  }

  async function generateReview() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.review.generate(project.id);
      setReview(res);
      await loadBibtex();
    } catch (err: any) {
      setError(err?.message || "Failed to generate literature review.");
    } finally {
      setLoading(false);
    }
  }

  function copyBibtex() {
    navigator.clipboard.writeText(bibtex);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function downloadBibtex() {
    const blob = new Blob([bibtex], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${project?.topic.slice(0, 20).replace(/\W+/g, "_")}_references.bib`;
    link.click();
    URL.revokeObjectURL(url);
  }

  if (!project) {
    return (
      <section className="page" style={{ maxWidth: 800, margin: "40px auto", textAlign: "center" }}>
        <BookOpen size={48} color="#94a3b8" style={{ margin: "0 auto 16px" }} />
        <h2>No Active Research Project</h2>
        <p style={{ color: "#64748b" }}>Please select a research project to generate a literature review.</p>
      </section>
    );
  }

  return (
    <section className="page reviewPage" style={{ maxWidth: 1050, margin: "0 auto", paddingBottom: 60 }}>
      <header className="pageHeader" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#2563eb", textTransform: "uppercase" }}>
            Academic Synthesis
          </span>
          <h1>Literature Review: "{project.topic}"</h1>
          <p>
            Synthesizes peer-reviewed background, method comparisons, empirical benchmarks, and open limitations.
            Exports genuine BibTeX citations derived solely from stored metadata.
          </p>
        </div>
        <button
          onClick={generateReview}
          disabled={loading}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "9px 16px",
            background: "#2563eb",
            color: "white",
            border: "none",
            borderRadius: 6,
            fontSize: 13,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          <Sparkles size={16} /> {loading ? "Synthesizing Review..." : "Generate Review"}
        </button>
      </header>

      {error && (
        <div style={{ padding: 16, background: "#fee2e2", color: "#991b1b", borderRadius: 8, marginBottom: 20 }}>
          <strong>Notice:</strong> {error}
        </div>
      )}

      {/* Review Content */}
      {review ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 20, marginBottom: 40 }}>
          {review.sections.map((sec, idx) => (
            <article key={idx} className="panel" style={{ padding: 24 }}>
              <h2 style={{ fontSize: 18, fontWeight: 700, color: "#0f172a", marginBottom: 12, borderBottom: "1px solid #f1f5f9", paddingBottom: 8 }}>
                {sec.title}
              </h2>
              <div style={{ fontSize: 14, color: "#334155", lineHeight: 1.8, whiteSpace: "pre-line" }}>
                {sec.content}
              </div>
              {sec.cited_paper_ids && sec.cited_paper_ids.length > 0 && (
                <div style={{ marginTop: 16, fontSize: 12, color: "#64748b", display: "flex", gap: 6, alignItems: "center" }}>
                  <span>Verified Citations:</span>
                  {sec.cited_paper_ids.map((id) => (
                    <span key={id} style={{ background: "#e2e8f0", padding: "2px 6px", borderRadius: 4, fontWeight: 600 }}>
                      [ID {id}]
                    </span>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
      ) : (
        <article className="panel" style={{ padding: 32, textAlign: "center", color: "#64748b", marginBottom: 32 }}>
          <FileText size={36} style={{ margin: "0 auto 12px", opacity: 0.5 }} />
          <h3>No Literature Review Generated Yet</h3>
          <p style={{ fontSize: 13, maxWidth: 480, margin: "0 auto 16px" }}>
            Click "Generate Review" above to synthesize an evidence-grounded review across the processed papers in this project.
          </p>
        </article>
      )}

      {/* Verified BibTeX Export Panel */}
      {bibtex && (
        <article className="panel" style={{ padding: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: "#0f172a" }}>
              Verified BibTeX Citations ({bibtex.split("@article").length - 1} entries)
            </h2>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={copyBibtex}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "6px 12px",
                  background: "#f1f5f9",
                  border: "1px solid #cbd5e1",
                  borderRadius: 6,
                  fontSize: 12,
                  cursor: "pointer",
                }}
              >
                <Copy size={14} /> {copied ? "Copied!" : "Copy BibTeX"}
              </button>
              <button
                onClick={downloadBibtex}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "6px 12px",
                  background: "#f1f5f9",
                  border: "1px solid #cbd5e1",
                  borderRadius: 6,
                  fontSize: 12,
                  cursor: "pointer",
                }}
              >
                <Download size={14} /> Download .bib
              </button>
            </div>
          </div>
          <pre
            style={{
              background: "#0f172a",
              color: "#f8fafc",
              padding: 16,
              borderRadius: 6,
              fontSize: 12,
              overflowX: "auto",
              lineHeight: 1.5,
              maxHeight: 280,
            }}
          >
            {bibtex}
          </pre>
        </article>
      )}
    </section>
  );
}
