import { BookOpen, ChevronRight, Loader2, Plus, RefreshCw, Search, Trash2, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { api, Job, Workspace } from "../lib/api";

type Props = {
  selectedWorkspace: Workspace | null;
  onSelectWorkspace: (ws: Workspace | null) => void;
  onWorkspaceReady: () => void;
};

export function WorkspacePage({ selectedWorkspace, onSelectWorkspace, onWorkspaceReady }: Props) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [newTopic, setNewTopic] = useState("");
  const [maxPapers, setMaxPapers] = useState(20);
  const [loading, setLoading] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [jobPollId, setJobPollId] = useState<ReturnType<typeof setInterval> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadWorkspaces();
  }, []);

  async function loadWorkspaces() {
    setLoading(true);
    try {
      const ws = await api.workspaces();
      setWorkspaces(ws);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  async function createAndDiscover() {
    if (!newTopic.trim()) return;
    setError(null);
    setLoading(true);
    try {
      const ws = await api.createWorkspace({ topic: newTopic.trim(), max_papers: maxPapers });
      setWorkspaces((prev) => [ws, ...prev]);
      onSelectWorkspace(ws);
      setNewTopic("");
      await startDiscovery(ws);
    } catch (err: any) {
      setError(err?.message || "Failed to create workspace.");
    } finally {
      setLoading(false);
    }
  }

  async function startDiscovery(ws: Workspace) {
    setDiscovering(true);
    setJob(null);
    try {
      const res = await api.discoverPapers(ws.id, maxPapers);
      pollJob(res.job_id, ws.id);
    } catch (err: any) {
      setError(`Discovery failed: ${err?.message}`);
      setDiscovering(false);
    }
  }

  function pollJob(jobId: string, wsId: number) {
    const id = setInterval(async () => {
      try {
        const j = await api.getJob(jobId);
        setJob(j);
        if (j.status === "completed" || j.status === "failed") {
          clearInterval(id);
          setJobPollId(null);
          setDiscovering(false);
          if (j.status === "completed") {
            // Refresh workspace paper count
            const updated = await api.getWorkspace(wsId);
            setWorkspaces((prev) => prev.map((w) => (w.id === wsId ? updated : w)));
            onWorkspaceReady();
          }
        }
      } catch {
        clearInterval(id);
        setJobPollId(null);
        setDiscovering(false);
      }
    }, 2500);
    setJobPollId(id);
  }

  async function deleteWorkspace(id: number, e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await api.deleteWorkspace(id);
      setWorkspaces((prev) => prev.filter((w) => w.id !== id));
      if (selectedWorkspace?.id === id) onSelectWorkspace(null);
    } catch {}
  }

  return (
    <section className="page workspacePage">
      <header className="pageHeader">
        <div>
          <h1>Research Workspaces</h1>
          <p>Create a topic workspace — the system fetches real papers, builds the graph, and enables gap &amp; evolution analysis.</p>
        </div>
      </header>

      {/* Create new workspace */}
      <article className="panel" style={{ marginBottom: 28 }}>
        <div className="sectionTitle">
          <Plus size={18} />
          <h2>New Research Topic</h2>
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
          <label style={{ flex: "1 1 320px" }}>
            <span style={{ fontSize: 12, color: "#475569", display: "block", marginBottom: 4 }}>Research Topic</span>
            <input
              value={newTopic}
              onChange={(e) => setNewTopic(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && createAndDiscover()}
              placeholder="e.g. AI in diabetic healthcare, federated learning, quantum computing…"
              style={{ width: "100%" }}
            />
          </label>
          <label style={{ width: 120 }}>
            <span style={{ fontSize: 12, color: "#475569", display: "block", marginBottom: 4 }}>Max papers</span>
            <input
              type="number"
              min={5}
              max={50}
              value={maxPapers}
              onChange={(e) => setMaxPapers(Number(e.target.value))}
            />
          </label>
          <button
            className="primary"
            onClick={createAndDiscover}
            disabled={loading || discovering || !newTopic.trim()}
            style={{ height: 38, alignSelf: "flex-end" }}
          >
            {discovering ? <Loader2 size={16} className="spin" /> : <Zap size={16} />}
            {discovering ? "Discovering…" : "Create & Discover"}
          </button>
        </div>

        {/* Job progress */}
        {discovering && job && (
          <div style={{ marginTop: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#475569", marginBottom: 4 }}>
              <span>{job.message}</span>
              <span>{Math.round(job.progress * 100)}%</span>
            </div>
            <div style={{ height: 6, background: "#e2e8f0", borderRadius: 3, overflow: "hidden" }}>
              <div
                style={{
                  height: "100%",
                  background: "linear-gradient(90deg, #2563eb, #7c3aed)",
                  borderRadius: 3,
                  width: `${Math.round(job.progress * 100)}%`,
                  transition: "width 0.4s ease",
                }}
              />
            </div>
            {job.error && (
              <p style={{ color: "#dc2626", fontSize: 12, marginTop: 6 }}>Error: {job.error}</p>
            )}
          </div>
        )}

        {error && (
          <div style={{ marginTop: 12, padding: "10px 14px", background: "#fee2e2", color: "#991b1b", borderRadius: 6, fontSize: 13 }}>
            {error}
          </div>
        )}
      </article>

      {/* Workspace list */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Your Workspaces ({workspaces.length})</h2>
        <button className="secondary" onClick={loadWorkspaces} title="Refresh">
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>

      {loading && !workspaces.length && (
        <div style={{ textAlign: "center", padding: 40, color: "#64748b" }}>
          <Loader2 size={24} className="spin" />
          <p>Loading workspaces…</p>
        </div>
      )}

      {!loading && workspaces.length === 0 && (
        <div style={{ textAlign: "center", padding: 48, color: "#94a3b8" }}>
          <Search size={40} style={{ margin: "0 auto 12px", display: "block", opacity: 0.4 }} />
          <p>No workspaces yet. Create one above to start discovering papers.</p>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {workspaces.map((ws) => (
          <button
            key={ws.id}
            className={selectedWorkspace?.id === ws.id ? "workspaceCard active" : "workspaceCard"}
            onClick={() => {
              onSelectWorkspace(ws);
              onWorkspaceReady();
            }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 14,
              padding: "14px 18px",
              border: selectedWorkspace?.id === ws.id ? "1.5px solid #2563eb" : "1px solid #e2e8f0",
              borderRadius: 10,
              background: selectedWorkspace?.id === ws.id ? "#eff6ff" : "#ffffff",
              cursor: "pointer",
              textAlign: "left",
              width: "100%",
            }}
          >
            <BookOpen size={20} color={selectedWorkspace?.id === ws.id ? "#2563eb" : "#64748b"} />
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, color: "#0f172a", fontSize: 15 }}>{ws.topic}</div>
              <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
                {ws.paper_count} papers · Status: {ws.status} · Created {new Date(ws.created_at).toLocaleDateString()}
              </div>
            </div>
            <ChevronRight size={16} color="#94a3b8" />
            <button
              onClick={(e) => deleteWorkspace(ws.id, e)}
              style={{ background: "none", border: "none", cursor: "pointer", padding: 4, color: "#94a3b8" }}
              title="Delete workspace"
            >
              <Trash2 size={15} />
            </button>
          </button>
        ))}
      </div>
    </section>
  );
}
