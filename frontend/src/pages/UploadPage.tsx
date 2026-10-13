import { CheckCircle2, Download, FileText, FileUp, Folder, FolderCheck, HardDrive } from "lucide-react";
import { useEffect, useState } from "react";
import { api, Paper, SamplePapersResponse } from "../lib/api";

export function UploadPage({ onUploaded }: { onUploaded: () => void }) {
  const [result, setResult] = useState<{
    paper: Paper;
    citation_edges: number;
    similarity_edges: number;
    saved_path: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sampleData, setSampleData] = useState<SamplePapersResponse | null>(null);
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);

  useEffect(() => {
    api.samplePapers().then((res) => {
      setSampleData(res);
      if (res.domains.length > 0) {
        setSelectedDomain(res.domains[0].domain_name);
      }
    }).catch(() => {});
  }, []);

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

  const activeDomain = sampleData?.domains.find((d) => d.domain_name === selectedDomain);

  return (
    <section className="page" style={{ maxWidth: 1100, margin: "0 auto", paddingBottom: 60 }}>
      <header className="pageHeader">
        <h1>Upload & Manage Research Papers</h1>
        <p>Drop in any academic PDF to extract metadata, citations, embeddings, and graph linkages. Files are automatically saved to your Downloads folder.</p>
      </header>

      <label className="dropZone">
        <FileUp size={36} color="#2563eb" />
        <strong style={{ fontSize: 16 }}>{busy ? "Parsing and indexing PDF..." : "Choose a Research Paper PDF"}</strong>
        <span style={{ color: "#64748b" }}>PDF will be automatically copied to your Downloads folder and linked in the knowledge graph</span>
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

      {/* Showcase of Pre-Generated Domain Papers on Disk */}
      {sampleData && sampleData.domains.length > 0 && (
        <article className="panel" style={{ marginTop: 32, padding: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#2563eb", marginBottom: 4 }}>
                <Folder size={20} />
                <h2 style={{ margin: 0, fontSize: 18 }}>Pre-Generated Research Paper Clusters ({sampleData.total_papers} Papers)</h2>
              </div>
              <p style={{ margin: 0, color: "#64748b", fontSize: 13 }}>
                These actual academic papers are organized in your project folder on disk and indexed into the knowledge graph.
              </p>
            </div>
            <div
              style={{
                background: "#f1f5f9",
                padding: "6px 12px",
                borderRadius: 6,
                fontSize: 12,
                color: "#334155",
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <HardDrive size={14} />
              <code>research_papers/</code>
            </div>
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 18 }}>
            {sampleData.domains.map((dom) => (
              <button
                key={dom.domain_name}
                type="button"
                onClick={() => setSelectedDomain(dom.domain_name)}
                style={{
                  padding: "8px 16px",
                  borderRadius: 20,
                  fontSize: 13,
                  fontWeight: selectedDomain === dom.domain_name ? 600 : 400,
                  border: selectedDomain === dom.domain_name ? "1px solid #2563eb" : "1px solid #cbd5e1",
                  background: selectedDomain === dom.domain_name ? "#eff6ff" : "#ffffff",
                  color: selectedDomain === dom.domain_name ? "#1d4ed8" : "#475569",
                  cursor: "pointer",
                }}
              >
                {dom.domain_name} ({dom.paper_count} PDFs)
              </button>
            ))}
          </div>

          {activeDomain && (
            <div style={{ background: "#f8fafc", borderRadius: 8, border: "1px solid #e2e8f0", padding: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#0f172a", marginBottom: 12 }}>
                Folder: <code>research_papers/{activeDomain.folder_name}/</code>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {activeDomain.papers.map((p) => (
                  <div
                    key={p.filename}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      background: "white",
                      padding: "10px 14px",
                      borderRadius: 6,
                      border: "1px solid #e2e8f0",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <FileText size={18} color="#0284c7" />
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 13, color: "#0f172a" }}>{p.title}</div>
                        <div style={{ fontSize: 11, color: "#64748b" }}>File: {p.filename} · {(p.size_bytes / 1024).toFixed(1)} KB</div>
                      </div>
                    </div>
                    <span
                      style={{
                        fontSize: 11,
                        background: "#dcfce7",
                        color: "#166534",
                        padding: "3px 8px",
                        borderRadius: 10,
                        fontWeight: 500,
                      }}
                    >
                      Indexed & Available on Disk
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </article>
      )}
    </section>
  );
}
