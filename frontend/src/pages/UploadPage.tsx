import { FileUp } from "lucide-react";
import { useState } from "react";
import { api, Paper } from "../lib/api";

export function UploadPage({ onUploaded }: { onUploaded: () => void }) {
  const [result, setResult] = useState<{ paper: Paper; citation_edges: number; similarity_edges: number } | null>(null);
  const [busy, setBusy] = useState(false);

  async function upload(file: File) {
    setBusy(true);
    try {
      const next = await api.upload(file);
      setResult(next);
      onUploaded();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page">
      <header className="pageHeader">
        <h1>Upload Paper</h1>
        <p>Drop in a PDF and the backend extracts metadata, references, chunks, vectors, and graph edges.</p>
      </header>
      <label className="dropZone">
        <FileUp size={34} />
        <strong>{busy ? "Indexing paper..." : "Choose a PDF"}</strong>
        <span>Semantic Scholar lookup falls back to local extraction when needed.</span>
        <input type="file" accept="application/pdf" onChange={(event) => event.target.files?.[0] && upload(event.target.files[0])} />
      </label>
      {result && (
        <article className="panel">
          <div className="pill">Indexed</div>
          <h2>{result.paper.title}</h2>
          <p>{result.paper.authors}</p>
          <div className="metricGrid">
            <span>{result.citation_edges} citation edges</span>
            <span>{result.similarity_edges} similarity edges</span>
            <span>{result.paper.source_type}</span>
          </div>
        </article>
      )}
    </section>
  );
}
