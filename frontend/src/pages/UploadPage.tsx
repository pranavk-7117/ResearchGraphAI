import { CheckCircle2, Download, FileUp, FolderCheck } from "lucide-react";
import { useState } from "react";
import { api, Paper } from "../lib/api";

export function UploadPage({ onUploaded }: { onUploaded: () => void }) {
  const [result, setResult] = useState<{
    paper: Paper;
    citation_edges: number;
    similarity_edges: number;
    saved_path: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const next = await api.upload(file);
      setResult(next);
      onUploaded();
    } catch (err: any) {
      setError(err?.message || "Failed to upload and index the research paper.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page">
      <header className="pageHeader">
        <h1>Upload Paper</h1>
        <p>Drop in a research PDF to automatically index metadata, references, chunks, vectors, and graph edges.</p>
      </header>
      <label className="dropZone">
        <FileUp size={34} />
        <strong>{busy ? "Ingesting and indexing paper..." : "Choose a PDF"}</strong>
        <span>PDF will also be automatically stored in your Downloads folder</span>
        <input
          type="file"
          accept="application/pdf"
          disabled={busy}
          onChange={(event) => event.target.files?.[0] && upload(event.target.files[0])}
        />
      </label>

      {error && (
        <div style={{ marginTop: 16, padding: 16, background: "#fee2e2", color: "#991b1b", borderRadius: 8 }}>
          <strong>Upload Error:</strong> {error}
        </div>
      )}

      {result && (
        <article className="panel" style={{ marginTop: 24 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <div className="pill" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <CheckCircle2 size={14} /> Indexed in Knowledge Graph
            </div>
            {result.saved_path && (
              <div
                className="pill"
                style={{
                  background: "#e0f2fe",
                  color: "#0369a1",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                }}
              >
                <FolderCheck size={14} /> Stored in Downloads
              </div>
            )}
          </div>

          <h2>{result.paper.title}</h2>
          <p style={{ color: "#475569", margin: "4px 0 12px" }}>{result.paper.authors || "Authors extracted"}</p>

          {result.saved_path && (
            <div
              style={{
                background: "#f8fafc",
                border: "1px solid #e2e8f0",
                borderRadius: 6,
                padding: "10px 14px",
                margin: "12px 0 16px",
                fontSize: 13,
                wordBreak: "break-all",
                color: "#1e293b",
              }}
            >
              <div style={{ fontWeight: 600, color: "#0f172a", marginBottom: 2, display: "flex", alignItems: "center", gap: 6 }}>
                <Download size={14} /> Saved PDF Location:
              </div>
              <code>{result.saved_path}</code>
            </div>
          )}

          <div className="metricGrid">
            <span>{result.citation_edges} citation edges</span>
            <span>{result.similarity_edges} similarity edges</span>
            <span>{result.paper.source_type}</span>
            <span>Year: {result.paper.year || "Unknown"}</span>
          </div>
        </article>
      )}
    </section>
  );
}
