import {
  BookOpen,
  Compass,
  FileText,
  GitFork,
  GitMerge,
  Layers,
  MessageSquareText,
  Network,
  Sparkles,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api, Project } from "./lib/api";
import { ChatPage } from "./pages/ChatPage";
import { ComparePage } from "./pages/ComparePage";
import { DashboardPage } from "./pages/DashboardPage";
import { DiscoverPage } from "./pages/DiscoverPage";
import { EvolutionPage } from "./pages/EvolutionPage";
import { GapsPage } from "./pages/GapsPage";
import { GraphPage } from "./pages/GraphPage";
import { ReviewPage } from "./pages/ReviewPage";

type Page =
  | "dashboard"
  | "discover"
  | "graph"
  | "evolution"
  | "gaps"
  | "review"
  | "chat"
  | "compare";

const nav = [
  { id: "dashboard", label: "Projects", icon: BookOpen },
  { id: "discover", label: "Discover", icon: Compass },
  { id: "graph", label: "Knowledge Graph", icon: Network },
  { id: "evolution", label: "Evolution", icon: GitFork },
  { id: "gaps", label: "Research Gaps", icon: Sparkles },
  { id: "review", label: "Literature Review", icon: FileText },
  { id: "chat", label: "RAG Chat", icon: MessageSquareText },
  { id: "compare", label: "Upload & Compare", icon: GitMerge },
] as const;

export function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [activeProject, setActiveProject] = useState<Project | null>(null);

  useEffect(() => {
    // Attempt to restore active project from projects list
    api.projects
      .list()
      .then((projects) => {
        if (projects.length > 0 && !activeProject) {
          setActiveProject(projects[0]);
        }
      })
      .catch(() => {});
  }, []);

  function handleSelectProject(proj: Project) {
    setActiveProject(proj);
    setPage("discover");
  }

  function handleProcessingComplete() {
    setPage("graph");
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <BookOpen size={24} />
          <div>
            <strong>ResearchGraphAI</strong>
            <span>
              {activeProject
                ? `${activeProject.topic.slice(0, 18)}... (${activeProject.paper_count} papers)`
                : "Scholarly Intelligence"}
            </span>
          </div>
        </div>

        {activeProject && (
          <div
            style={{
              padding: "8px 14px",
              background: "#eff6ff",
              borderBottom: "1px solid #bfdbfe",
              fontSize: 12,
              color: "#1d4ed8",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span
              style={{
                fontWeight: 600,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                maxWidth: 160,
              }}
              title={activeProject.topic}
            >
              {activeProject.topic}
            </span>
            <button
              onClick={() => {
                setActiveProject(null);
                setPage("dashboard");
              }}
              style={{
                background: "none",
                border: "none",
                color: "#6b7280",
                cursor: "pointer",
                fontSize: 11,
              }}
              title="Switch project"
            >
              Switch
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

      <main className="content">
        {page === "dashboard" && (
          <DashboardPage
            activeProject={activeProject}
            onSelectProject={handleSelectProject}
          />
        )}
        {page === "discover" && (
          <DiscoverPage
            project={activeProject}
            onProcessingComplete={handleProcessingComplete}
          />
        )}
        {page === "graph" && <GraphPage project={activeProject} />}
        {page === "evolution" && <EvolutionPage project={activeProject} />}
        {page === "gaps" && <GapsPage project={activeProject} />}
        {page === "review" && <ReviewPage project={activeProject} />}
        {page === "chat" && <ChatPage project={activeProject} />}
        {page === "compare" && <ComparePage project={activeProject} />}
      </main>
    </div>
  );
}
