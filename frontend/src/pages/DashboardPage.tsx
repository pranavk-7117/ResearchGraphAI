import { BookOpen, FolderPlus, Layers, Plus, Trash2, ArrowRight } from "lucide-react";
import { useEffect, useState } from "react";
import { api, Project } from "../lib/api";

export function DashboardPage({
  activeProject,
  onSelectProject,
}: {
  activeProject: Project | null;
  onSelectProject: (p: Project) => void;
}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [topicInput, setTopicInput] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadProjects();
  }, []);

  async function loadProjects() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.projects.list();
      setProjects(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load research projects.");
    } finally {
      setLoading(false);
    }
  }

  async function createProject(e: React.FormEvent) {
    e.preventDefault();
    if (!topicInput.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const newProj = await api.projects.create(topicInput.trim());
      setTopicInput("");
      await loadProjects();
      onSelectProject(newProj);
    } catch (err: any) {
      setError(err?.message || "Failed to create research project.");
    } finally {
      setCreating(false);
    }
  }

  async function deleteProject(id: number) {
    if (!confirm("Are you sure you want to delete this research project and all its indexed literature?")) {
      return;
    }
    try {
      await api.projects.delete(id);
      loadProjects();
    } catch (err: any) {
      alert(err?.message || "Failed to delete project.");
    }
  }

  return (
    <section className="page" style={{ maxWidth: 1000, margin: "0 auto", paddingBottom: 60 }}>
      <header className="pageHeader">
        <h1>Research Projects Dashboard</h1>
        <p>
          Organize your scholarly investigations. Every project maintains its own isolated literature corpus,
          evidence graph, extracted facts, and research gaps in Supabase.
        </p>
      </header>

      {/* Create Project Form */}
      <form onSubmit={createProject} className="panel" style={{ padding: 24, marginBottom: 32 }}>
        <h2 style={{ fontSize: 18, marginBottom: 8, display: "flex", alignItems: "center", gap: 8 }}>
          <FolderPlus size={20} color="#2563eb" /> Start a New Research Project
        </h2>
        <p style={{ color: "#64748b", fontSize: 13, marginBottom: 16 }}>
          Enter any research domain or specific scientific topic (e.g. "CRISPR gene drive biosafety", "zero-knowledge verifiable computation", "quantum error correction").
        </p>
        <div style={{ display: "flex", gap: 12 }}>
          <input
            type="text"
            value={topicInput}
            onChange={(e) => setTopicInput(e.target.value)}
            placeholder="e.g. Photovoltaic perovskite degradation mechanisms..."
            style={{
              flex: 1,
              padding: "10px 14px",
              borderRadius: 6,
              border: "1px solid #cbd5e1",
              fontSize: 14,
            }}
            disabled={creating}
          />
          <button
            type="submit"
            disabled={creating || !topicInput.trim()}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "10px 20px",
              background: "#2563eb",
              color: "white",
              border: "none",
              borderRadius: 6,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            <Plus size={16} /> {creating ? "Creating..." : "Create Project"}
          </button>
        </div>
      </form>

      {error && (
        <div style={{ marginBottom: 24, padding: 16, background: "#fee2e2", color: "#991b1b", borderRadius: 8 }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Projects Grid */}
      <div>
        <h2 style={{ fontSize: 18, marginBottom: 16, display: "flex", alignItems: "center", gap: 8 }}>
          <Layers size={20} /> Your Active Workspaces ({projects.length})
        </h2>

        {loading ? (
          <p style={{ color: "#64748b" }}>Loading research projects...</p>
        ) : projects.length === 0 ? (
          <article className="panel" style={{ padding: 32, textAlign: "center", color: "#64748b" }}>
            <BookOpen size={36} style={{ margin: "0 auto 12px", opacity: 0.5 }} />
            <h3 style={{ fontSize: 16, color: "#1e293b", margin: "0 0 6px" }}>No research projects yet</h3>
            <p style={{ fontSize: 13, margin: 0 }}>
              Create your first project above to begin discovering and analyzing literature.
            </p>
          </article>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 16 }}>
            {projects.map((p) => {
              const isSelected = activeProject?.id === p.id;
              return (
                <article
                  key={p.id}
                  className="panel"
                  style={{
                    padding: 20,
                    border: isSelected ? "2px solid #2563eb" : "1px solid #e2e8f0",
                    background: isSelected ? "#eff6ff" : "white",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                  }}
                >
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 600,
                          padding: "2px 8px",
                          borderRadius: 12,
                          background: isSelected ? "#dbeafe" : "#f1f5f9",
                          color: isSelected ? "#1d4ed8" : "#475569",
                        }}
                      >
                        Project #{p.id}
                      </span>
                      <button
                        onClick={() => deleteProject(p.id)}
                        style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer" }}
                        title="Delete project"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                    <h3 style={{ fontSize: 16, fontWeight: 600, margin: "0 0 8px", color: "#0f172a" }}>
                      {p.topic}
                    </h3>
                    <div style={{ fontSize: 12, color: "#64748b", marginBottom: 16 }}>
                      {p.paper_count} papers indexed · Corpus v{p.corpus_version}
                    </div>
                  </div>

                  <button
                    onClick={() => onSelectProject(p)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 6,
                      padding: "8px 14px",
                      background: isSelected ? "#2563eb" : "#f8fafc",
                      color: isSelected ? "white" : "#1e293b",
                      border: isSelected ? "none" : "1px solid #cbd5e1",
                      borderRadius: 6,
                      fontSize: 13,
                      fontWeight: 500,
                      cursor: "pointer",
                    }}
                  >
                    {isSelected ? "Active Workspace" : "Open Workspace"} <ArrowRight size={14} />
                  </button>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
