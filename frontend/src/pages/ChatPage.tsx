import { Download, MessageSquareText, Search, Send } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";

type Message = { role: "user" | "assistant"; text: string; citations?: string[] };

const suggestions = [
  "What are graphs in this research system?",
  "Which gaps exist in retrieval and RAG?",
  "How does missing citation detection work?",
  "Explain the evolution of knowledge graph interfaces.",
];

export function ChatPage() {
  const [question, setQuestion] = useState("How do graph methods improve research discovery?");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);

  async function ask(next = question) {
    if (!next.trim()) return;
    const nextQuestion = next.trim();
    setMessages((value) => [...value, { role: "user", text: nextQuestion }]);
    setQuestion("");
    setBusy(true);
    try {
      const result = await api.chat(nextQuestion);
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
          <p>Ask grounded questions over paper titles, abstracts, and embedded chunks. Answers adapt to retrieved evidence.</p>
        </div>
        <button className="secondary" onClick={exportChat} disabled={messages.length === 0}><Download size={16} /> Export</button>
      </header>

      <div className="chatLayout">
        <aside className="chatSidebar">
          <div className="retrievalCard">
            <Search size={18} />
            <div>
              <strong>Retrieval Mode</strong>
              <span>SQL match + vector search</span>
            </div>
          </div>
          <h2>Try asking</h2>
          <div className="promptList">
            {suggestions.map((item) => (
              <button key={item} onClick={() => ask(item)}>{item}</button>
            ))}
          </div>
          <h2>Latest citations</h2>
          <div className="citationList">
            {latestCitations.length ? latestCitations.map((citation) => <span key={citation}>{citation}</span>) : <p>No answer yet.</p>}
          </div>
        </aside>

        <main className="chatPanel">
          <div className="chatLog">
            {messages.length === 0 && (
              <article className="emptyChat">
                <MessageSquareText size={24} />
                <strong>Ask a question about the research collection</strong>
                <p>The local answer engine uses the retrieved papers to produce different responses for graph, gap, citation, evolution, retrieval, and RAG questions.</p>
              </article>
            )}
            {messages.map((message, index) => (
              <article className={`bubble ${message.role}`} key={index}>
                <p>{message.text}</p>
                {message.citations && <span>Cited: {message.citations.join(", ")}</span>}
              </article>
            ))}
          </div>
          <div className="composer">
            <input value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => event.key === "Enter" && ask()} placeholder="Ask about graphs, gaps, citations, evolution..." />
            <button className="iconButton" onClick={() => ask()} disabled={busy} title="Send">
              <Send size={18} />
            </button>
          </div>
        </main>
      </div>
    </section>
  );
}
