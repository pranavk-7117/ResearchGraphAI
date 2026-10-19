import {
  BookOpen,
  GitFork,
  GitMerge,
  MessageSquareText,
  Network,
  Sparkles,
  Upload,
} from "lucide-react";
import { useEffect, useState } from "react";
import { ChatPage } from "./pages/ChatPage";
import { ComparePage } from "./pages/ComparePage";
import { EvolutionPage } from "./pages/EvolutionPage";
import { GapsPage } from "./pages/GapsPage";
import { GraphPage } from "./pages/GraphPage";
import { UploadPage } from "./pages/UploadPage";
import { WorkspacePage } from "./pages/WorkspacePage";
import { api, Paper, Workspace } from "./lib/api";

type Page = "workspaces" | "upload" | "graph" | "gaps" | "evolution" | "chat" | "compare";

const nav = [
  { id: "workspaces", label: "Workspaces", icon: BookOpen },
  { id: "upload", label: "Upload", icon: Upload },
  { id: "graph", label: "Graph", icon: Network },
  { id: "gaps", label: "Gaps", icon: Sparkles },
  { id: "evolution", label: "Evolution", icon: GitFork },
  { id: "chat", label: "Chat", icon: MessageSquareText },
  { id: "compare", label: "Compare", icon: GitMerge },
] as const;

export function App() {
  const [page, setPage] = useState<Page>("workspaces");
  const [papers, setPapers] = useState<Paper[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedWorkspace, setSelectedWorkspace] = useState<Workspace | null>(null);

  useEffect(() => {
    if (selectedWorkspace) {
      api.papers(selectedWorkspace.id).then(setPapers).catch(() => setPapers([]));
    } else {
      api.papers().then(setPapers).catch(() => setPapers([]));
    }
  }, [refreshKey, selectedWorkspace?.id]);

  function handleWorkspaceReady() {
    setRefreshKey((v) => v + 1);
    setPage("graph");
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <BookOpen size={24} />
          <div>
            <strong>Research Graph AI</strong>
            <span>
              {selectedWorkspace
                ? `${selectedWorkspace.topic.slice(0, 22)}… · ${papers.length} papers`
                : `${papers.length} papers indexed`}
            </span>
          </div>
        </div>

        {selectedWorkspace && (
          <div
            style={{
              padding: "6px 14px",
              background: "#eff6ff",
              borderBottom: "1px solid #bfdbfe",
              fontSize: 12,
              color: "#1d4ed8",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 140 }}>
              {selectedWorkspace.topic}
            </span>
            <button
              onClick={() => { setSelectedWorkspace(null); setRefreshKey((v) => v + 1); }}
              style={{ background: "none", border: "none", color: "#6b7280", cursor: "pointer", fontSize: 11 }}
              title="Clear workspace filter"
            >
              × All
            </button>
          </div>
        )}

        <nav>
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={page === item.id ? "active" : ""}
                key={item.id}
                onClick={() => setPage(item.id)}
                title={item.label}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <main className="main">
        {page === "workspaces" && (
          <WorkspacePage
            selectedWorkspace={selectedWorkspace}
            onSelectWorkspace={setSelectedWorkspace}
            onWorkspaceReady={handleWorkspaceReady}
          />
        )}
        {page === "upload" && (
          <UploadPage onUploaded={() => setRefreshKey((v) => v + 1)} workspace={selectedWorkspace} />
        )}
        {page === "graph" && (
          <GraphPage
            papers={papers}
            onChanged={() => setRefreshKey((v) => v + 1)}
            workspace={selectedWorkspace}
          />
        )}
        {page === "gaps" && <GapsPage workspace={selectedWorkspace} />}
        {page === "evolution" && <EvolutionPage workspace={selectedWorkspace} />}
        {page === "chat" && <ChatPage workspace={selectedWorkspace} />}
        {page === "compare" && <ComparePage workspace={selectedWorkspace} />}
      </main>
    </div>
  );
}
