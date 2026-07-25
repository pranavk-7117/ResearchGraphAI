import { BookOpen, Download, GitBranch, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";

type EvolutionData = Awaited<ReturnType<typeof api.evolution>>;

const topicPresets = [
  "retrieval",
  "rag",
  "knowledge graph",
  "gap",
  "evolution",
  "summarization",
  "recommendation",
  "metadata",
  "interface",
];

export function EvolutionPage() {
  const [topic, setTopic] = useState("retrieval");
  const [days, setDays] = useState(5);
  const [data, setData] = useState<EvolutionData | null>(null);

  const exportText = useMemo(() => {
    if (!data) return "";
    const timeline = data.papers.map((paper) => `${paper.year ?? "----"} - ${paper.title}: ${paper.contribution}`).join("\n");
    const transitions = data.steps.map((step) => `${step.from} -> ${step.to}\nSolved: ${step.solved}\nLeft open: ${step.left_open}\nNext fixed: ${step.next_fixed}`).join("\n\n");
    const plan = data.reading_plan.map((day) => `Day ${day.day}: ${day.papers.join(", ") || "Buffer day"}`).join("\n");
    return `Evolution Chain: ${topic}\n\nTimeline\n${timeline}\n\nTransitions\n${transitions}\n\nLiterature Review\n${data.literature_review}\n\nReading Plan\n${plan}`;
  }, [data, topic]);

  useEffect(() => {
    run();
  }, []);

  async function run() {
    setData(await api.evolution(topic, days));
  }

  function downloadReview() {
    const blob = new Blob([exportText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "research-evolution-review.txt";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="page evolutionPage">
      <header className="pageHeader inlineHeader">
        <div>
          <h1>Evolution Chain</h1>
          <p>Trace how a topic moves from early papers to newer fixes, gaps, and review-ready claims.</p>
        </div>
        <div className="controls">
          <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Topic" />
          <input type="number" min={1} max={30} value={days} onChange={(event) => setDays(Number(event.target.value))} />
          <button className="primary" onClick={run}>Run</button>
          <button className="secondary" onClick={downloadReview} disabled={!data}><Download size={16} /> Export</button>
        </div>
      </header>

      <div className="topicPresetBar">
        {topicPresets.map((preset) => (
          <button
            className={topic === preset ? "active" : ""}
            key={preset}
            onClick={() => {
              setTopic(preset);
              api.evolution(preset, days).then(setData);
            }}
          >
            {preset}
          </button>
        ))}
      </div>

      <div className="evolutionLayout">
        <main className="evolutionMain">
          <article className="reviewPanel">
            <Sparkles size={18} />
            <div>
              <strong>Literature Review</strong>
              <p>{data?.literature_review ?? "Run a topic to generate a connected review paragraph."}</p>
            </div>
          </article>

          <div className="timelineRail">
            {data?.papers?.map((paper, index) => (
              <article className="evolutionNode" key={paper.id}>
                <div className="yearBadge">{paper.year ?? "----"}</div>
                <div>
                  <h2>{paper.title}</h2>
                  <span>{paper.authors}</span>
                  <p>{paper.contribution}</p>
                </div>
                {data.steps[index] && (
                  <div className="transitionCard">
                    <GitBranch size={15} />
                    <div>
                      <strong>Next advance</strong>
                      <p><b>Opened question:</b> {data.steps[index].left_open}</p>
                      <p><b>{data.steps[index].to} adds:</b> {data.steps[index].next_fixed}</p>
                    </div>
                  </div>
                )}
              </article>
            ))}
          </div>
        </main>

        <aside className="readingPlanner">
          <div className="plannerHeader">
            <BookOpen size={18} />
            <div>
              <strong>{days}-Day Reading Plan</strong>
              <span>{data?.papers.length ?? 0} papers sequenced</span>
            </div>
          </div>
          <div className="plannerDays">
            {data?.reading_plan?.map((day) => (
              <article key={day.day}>
                <strong>Day {day.day}</strong>
                <p>{day.papers.join(", ") || "Buffer day"}</p>
              </article>
            ))}
          </div>
        </aside>
      </div>
    </section>
  );
}
