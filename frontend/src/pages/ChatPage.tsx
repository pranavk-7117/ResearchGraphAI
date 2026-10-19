import { Download, MessageSquareText, Search, Send, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { api, TopicItem, Workspace } from "../lib/api";

type Message = { role: "user" | "assistant"; text: string; citations?: string[] };

export function ChatPage({ workspace }: { workspace: Workspace | null }) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [topics, setTopics] = useState<TopicItem[]>([]);

  useEffect(() => {
    api.topics().then(setTopics).catch(() => {});
  }, []);

  const dynamicSuggestions = [
    "How does hierarchical planning coordinate autonomous multi-agent systems in AI?",
    "What are the challenges of federated learning under client drift in ML?",
    "How does zero-trust device identity secure smart city IoT grids?",
    "How does strict attribution mitigate hallucination in scientific RAG?",
    "What are the limitations of zero-knowledge proofs in cloud SQL databases?",
  ];

  async function ask(next = question) {
    if (!next.trim()) return;
    const nextQuestion = next.trim();
    setMessages((value) => [...value, { role: "user", text: nextQuestion }]);
    setQuestion("");
    setBusy(true);
    try {
      const result = await api.chat(nextQuestion, workspace?.id);
      setMessages((value) => [...value, { role: "assistant", text: result.answer, citations: result.citations }]);
    } finally {
      setBusy(false);
    }
  }

  function exportChat() {
    const transcript = messages
      .map((message) => `${message.role.toUpperCase()}: ${message.text}${message.citations ? `\nCited: ${message.citations.join(", ")}` : ""}`)
      .join("\n\n");
    const blob = new Blob([transcript], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "research-rag-chat.txt";
    link.click();
    URL.revokeObjectURL(url);
  }

  const latestCitations = [...messages].reverse().find((message) => message.citations)?.citations ?? [];

  return (
    <section className="page chatPage">
      <header className="pageHeader inlineHeader">
        <div>
          <h1>RAG Chat</h1>
          <p>Ask strictly grounded research questions across AI, ML, IoT, NLP, and Cybersecurity. Zero hallucination guaranteed.</p>
        </div>
        <button className="secondary" onClick={exportChat} disabled={messages.length === 0}><Download size={16} /> Export</button>
      </header>

      <div className="chatLayout">
        <aside className="chatSidebar">
          <div className="retrievalCard">
            <Search size={18} />
            <div>
              <strong>Grounded Retrieval Mode</strong>
              <span>FAISS dense vectors + SQL text search</span>
            </div>
          </div>

          <h2>Try asking</h2>
          <div className="promptList">
            {dynamicSuggestions.map((item) => (
              <button key={item} onClick={() => ask(item)} style={{ textAlign: "left", fontSize: 12 }}>
                {item}
              </button>
            ))}
          </div>

          {topics.length > 0 && (
            <>
              <h2 style={{ marginTop: 18 }}>Indexed Domains</h2>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 16 }}>
                {topics.slice(0, 8).map((t) => (
                  <span
                    key={t.topic}
                    onClick={() => ask(`What research is conducted on ${t.topic}?`)}
                    style={{
                      background: "#e2e8f0",
                      padding: "3px 8px",
                      borderRadius: 12,
                      fontSize: 11,
                      cursor: "pointer",
                      color: "#334155",
                    }}
                    title={`Ask about ${t.topic}`}
                  >
                    {t.topic}
                  </span>
                ))}
              </div>
            </>
          )}

          <h2>Latest citations</h2>
          <div className="citationList">
            {latestCitations.length ? latestCitations.map((citation) => <span key={citation}>{citation}</span>) : <p>No answer yet.</p>}
          </div>
        </aside>

        <main className="chatPanel">
          <div className="chatLog">
            {messages.length === 0 && (
              <article className="emptyChat">
                <MessageSquareText size={28} />
                <strong>Ask a question about the indexed research corpus</strong>
                <p>
                  Answers are synthesized strictly from retrieved paper passages and cited inline.
                  If evidence does not exist in the collection, the assistant will disclose the limitation rather than hallucinating.
                </p>
              </article>
            )}
            {messages.map((message, index) => (
              <article className={`bubble ${message.role}`} key={index}>
                <p style={{ whiteSpace: "pre-line" }}>{message.text}</p>
                {message.citations && message.citations.length > 0 && (
                  <div style={{ marginTop: 8, fontSize: 12, color: "#475569", borderTop: "1px solid rgba(0,0,0,0.06)", paddingTop: 4 }}>
                    <strong>Cited Sources:</strong> {message.citations.join(" · ")}
                  </div>
                )}
              </article>
            ))}
          </div>
          <div className="composer">
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && ask()}
              placeholder="Ask about AI agents, ML quantization, IoT routing, RAG attribution, zero-trust..."
            />
            <button className="iconButton" onClick={() => ask()} disabled={busy} title="Send">
              <Send size={18} />
            </button>
          </div>
        </main>
      </div>
    </section>
  );
}
