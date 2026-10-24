import { Download, MessageSquareText, Search, Send, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ChatCitation, Project } from "../lib/api";

type Message = {
  role: "user" | "assistant";
  text: string;
  citations?: ChatCitation[];
};

export function ChatPage({ project }: { project: Project | null }) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [selectedCitation, setSelectedCitation] = useState<ChatCitation | null>(null);

  const dynamicSuggestions = project
    ? [
        `What are the primary methodologies evaluated in "${project.topic}"?`,
        `What empirical datasets and benchmarks are used in this corpus?`,
        `What common hardware, algorithmic, or practical limitations are reported?`,
        `How do recent papers improve accuracy, efficiency, or robustness?`,
      ]
    : [];

  async function ask(next = question) {
    if (!project || !next.trim() || busy) return;
    const nextQuestion = next.trim();
    setMessages((prev) => [...prev, { role: "user", text: nextQuestion }]);
    setQuestion("");
    setBusy(true);

    try {
      const res = await api.chat.send(project.id, nextQuestion, sessionId);
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: res.answer, citations: res.citations },
      ]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: `### Evidence\nUnable to retrieve grounded answer: ${err?.message || "Internal error"}.`,
          citations: [],
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function exportChat() {
    const transcript = messages
      .map(
        (m) =>
          `${m.role.toUpperCase()}:\n${m.text}\n` +
          (m.citations && m.citations.length > 0
            ? `Citations: ${m.citations.map((c) => `${c.title} (Page ${c.page || 1})`).join("; ")}\n`
            : "")
      )
      .join("\n---\n\n");
    const blob = new Blob([transcript], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `rag-chat-${project?.topic.slice(0, 15).replace(/\W+/g, "_")}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  }

  if (!project) {
    return (
      <section className="page" style={{ maxWidth: 800, margin: "40px auto", textAlign: "center" }}>
        <MessageSquareText size={48} color="#94a3b8" style={{ margin: "0 auto 16px" }} />
        <h2>No Active Research Project</h2>
        <p style={{ color: "#64748b" }}>Please select a research project to chat with its literature corpus.</p>
      </section>
    );
  }

  return (
    <section className="page chatPage" style={{ maxWidth: 1150, margin: "0 auto", paddingBottom: 40 }}>
      <header className="pageHeader inlineHeader" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#2563eb", textTransform: "uppercase" }}>
            Attributed RAG Chat
          </span>
          <h1 style={{ margin: "4px 0" }}>Scholarly Q&A: "{project.topic}"</h1>
          <p style={{ margin: 0, fontSize: 13, color: "#64748b" }}>
            Hybrid pgvector + SQL text search with Reciprocal Rank Fusion. Every claim is attributed to stored passage excerpts.
          </p>
        </div>
        <button
          className="secondary"
          onClick={exportChat}
          disabled={messages.length === 0}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: 6, border: "1px solid #cbd5e1" }}
        >
          <Download size={14} /> Export Transcript
        </button>
      </header>

      <div className="chatLayout" style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 20, marginTop: 16 }}>
        {/* Left Sidebar */}
        <aside className="chatSidebar">
          <div className="retrievalCard" style={{ background: "#f8fafc", padding: 14, borderRadius: 6, border: "1px solid #e2e8f0", marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#2563eb", marginBottom: 4 }}>
              <Search size={16} />
              <strong style={{ fontSize: 13 }}>Hybrid Retrieval Active</strong>
            </div>
            <div style={{ fontSize: 11, color: "#64748b" }}>
              pgvector dense cosine + full-text SQL matching with RRF reranking
            </div>
          </div>

          <h3 style={{ fontSize: 13, color: "#475569", marginBottom: 8 }}>Suggested Inquiries</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 20 }}>
            {dynamicSuggestions.map((item, idx) => (
              <button
                key={idx}
                onClick={() => ask(item)}
                disabled={busy}
                style={{
                  textAlign: "left",
                  fontSize: 12,
                  padding: "8px 10px",
                  background: "#f1f5f9",
                  border: "1px solid #e2e8f0",
                  borderRadius: 6,
                  color: "#1e293b",
                  cursor: "pointer",
                }}
              >
                {item}
              </button>
            ))}
          </div>

          {/* Citation Passage Drawer when clicked */}
          {selectedCitation && (
            <div style={{ background: "#eff6ff", border: "1px solid #bfdbfe", padding: 14, borderRadius: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                <strong style={{ fontSize: 12, color: "#1d4ed8" }}>Source Passage {selectedCitation.ref}</strong>
                <button
                  onClick={() => setSelectedCitation(null)}
                  style={{ background: "none", border: "none", fontSize: 12, color: "#64748b", cursor: "pointer" }}
                >
                  ×
                </button>
              </div>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#0f172a", marginBottom: 4 }}>
                {selectedCitation.title}
              </div>
              <div style={{ fontSize: 11, color: "#475569", marginBottom: 8 }}>
                Page {selectedCitation.page || 1} · Section: {selectedCitation.section || "Body"}
              </div>
              <p style={{ fontSize: 12, fontStyle: "italic", color: "#334155", margin: 0, lineHeight: 1.5, background: "white", padding: 8, borderRadius: 4 }}>
                "{selectedCitation.quote}"
              </p>
            </div>
          )}
        </aside>

        {/* Main Chat Panel */}
        <main className="chatPanel" style={{ display: "flex", flexDirection: "column", height: 560, background: "white", border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
          <div className="chatLog" style={{ flex: 1, padding: 20, overflowY: "auto", display: "flex", flexDirection: "column", gap: 16 }}>
            {messages.length === 0 ? (
              <article style={{ textAlign: "center", color: "#64748b", margin: "auto" }}>
                <MessageSquareText size={36} style={{ margin: "0 auto 12px", opacity: 0.5 }} />
                <h3 style={{ fontSize: 16, color: "#0f172a", margin: "0 0 6px" }}>Ask about the indexed research corpus</h3>
                <p style={{ fontSize: 13, maxWidth: 440, margin: "0 auto" }}>
                  Answers are synthesized strictly from retrieved paper passages and cited inline.
                  If evidence does not exist in the collection, the assistant will disclose the limitation.
                </p>
              </article>
            ) : (
              messages.map((m, idx) => (
                <div
                  key={idx}
                  style={{
                    alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                    maxWidth: m.role === "user" ? "75%" : "88%",
                    padding: "12px 16px",
                    borderRadius: 8,
                    background: m.role === "user" ? "#2563eb" : "#f8fafc",
                    color: m.role === "user" ? "white" : "#0f172a",
                    border: m.role === "user" ? "none" : "1px solid #e2e8f0",
                    fontSize: 13,
                    lineHeight: 1.6,
                  }}
                >
                  <div style={{ whiteSpace: "pre-line" }}>{m.text}</div>

                  {/* Clickable Citations Footer */}
                  {m.citations && m.citations.length > 0 && (
                    <div style={{ marginTop: 12, paddingTop: 8, borderTop: "1px solid #e2e8f0", fontSize: 11 }}>
                      <strong style={{ color: "#475569", display: "block", marginBottom: 4 }}>Passage Citations:</strong>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {m.citations.map((c, i) => (
                          <button
                            key={i}
                            onClick={() => setSelectedCitation(c)}
                            style={{
                              background: "#eff6ff",
                              border: "1px solid #bfdbfe",
                              padding: "2px 8px",
                              borderRadius: 4,
                              color: "#1d4ed8",
                              fontSize: 11,
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                              gap: 4,
                            }}
                          >
                            <span>{c.ref}</span> {c.title.slice(0, 24)}... (p. {c.page || 1})
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))
            )}
            {busy && (
              <div style={{ alignSelf: "flex-start", padding: "10px 14px", background: "#f1f5f9", borderRadius: 8, fontSize: 12, color: "#64748b" }}>
                Retrieving passage evidence and synthesizing attributed answer...
              </div>
            )}
          </div>

          {/* Composer */}
          <div style={{ padding: 12, borderTop: "1px solid #e2e8f0", display: "flex", gap: 8, background: "#f8fafc" }}>
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask()}
              placeholder="Ask an evidence-grounded question across indexed literature..."
              style={{ flex: 1, padding: "10px 14px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 13 }}
              disabled={busy}
            />
            <button
              onClick={() => ask()}
              disabled={busy || !question.trim()}
              style={{
                padding: "10px 18px",
                background: "#2563eb",
                color: "white",
                border: "none",
                borderRadius: 6,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <Send size={16} />
            </button>
          </div>
        </main>
      </div>
    </section>
  );
}
