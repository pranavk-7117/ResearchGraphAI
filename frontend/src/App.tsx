import { BookOpen, GitFork, MessageSquareText, Network, Sparkles, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { ChatPage } from "./pages/ChatPage";
import { EvolutionPage } from "./pages/EvolutionPage";
import { GapsPage } from "./pages/GapsPage";
import { GraphPage } from "./pages/GraphPage";
import { UploadPage } from "./pages/UploadPage";
import { api, Paper } from "./lib/api";

type Page = "upload" | "graph" | "gaps" | "evolution" | "chat";

const nav = [
  { id: "upload", label: "Upload", icon: Upload },
  { id: "graph", label: "Graph", icon: Network },
  { id: "gaps", label: "Gaps", icon: Sparkles },
  { id: "evolution", label: "Evolution", icon: GitFork },
  { id: "chat", label: "Chat", icon: MessageSquareText },
] as const;

export function App() {
  const [page, setPage] = useState<Page>("graph");
  const [papers, setPapers] = useState<Paper[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    api.papers().then(setPapers).catch(() => setPapers([]));
  }, [refreshKey]);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <BookOpen size={24} />
          <div>
            <strong>Research Graph AI</strong>
            <span>{papers.length} papers indexed</span>
          </div>
        </div>
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
        {page === "upload" && <UploadPage onUploaded={() => setRefreshKey((value) => value + 1)} />}
        {page === "graph" && <GraphPage papers={papers} onChanged={() => setRefreshKey((value) => value + 1)} />}
        {page === "gaps" && <GapsPage />}
        {page === "evolution" && <EvolutionPage />}
        {page === "chat" && <ChatPage />}
      </main>
    </div>
  );
}
