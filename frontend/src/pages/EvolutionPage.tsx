import { BookOpen, Download, GitBranch, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, TopicItem } from "../lib/api";

type EvolutionData = Awaited<ReturnType<typeof api.evolution>>;

export function EvolutionPage() {
  const [topic, setTopic] = useState("Artificial Intelligence");
  const [days, setDays] = useState(5);
  const [data, setData] = useState<EvolutionData | null>(null);
  const [availableTopics, setAvailableTopics] = useState<TopicItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Fetch dynamic topics from the database
    api.topics().then((items) => {
      setAvailableTopics(items);
      if (items.length > 0) {
        setTopic(items[0].topic);
        run(items[0].topic);
      } else {
        run("Artificial Intelligence");
      }
    }).catch(() => {
      run("Artificial Intelligence");
    });
  }, []);

  async function run(topicToRun = topic) {
    setLoading(true);
    try {
      const res = await api.evolution(topicToRun, days);
      setData(res);
    } finally {
      setLoading(false);
    }
  }

  const exportText = useMemo(() => {
    if (!data) return "";
    const timeline = data.papers.map((paper) => `${paper.year ?? "----"} - ${paper.title}: ${paper.contribution}`).join("\n");
    const transitions = data.steps.map((step) => `${step.from} -> ${step.to}\nSolved: ${step.solved}\nLeft open: ${step.left_open}\nNext fixed: ${step.next_fixed}`).join("\n\n");
    const plan = data.reading_plan.map((day) => `Day ${day.day}: ${day.papers.join(", ") || "Buffer day"}`).join("\n");
    return `Evolution Chain: ${topic}\n\nTimeline\n${timeline}\n\nTransitions\n${transitions}\n\nLiterature Review\n${data.literature_review}\n\nReading Plan\n${plan}`;
  }, [data, topic]);

  function downloadReview() {
    const blob = new Blob([exportText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `evolution-${topic.toLowerCase().replace(/\s+/g, "-")}-review.txt`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="page evolutionPage">
      <header className="pageHeader inlineHeader">
        <div>
          <h1>Evolution Chain</h1>
          <p>Trace how research in a domain moves from early foundations to modern extensions, open gaps, and reading plans.</p>
        </div>
        <div className="controls">
          <input
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && run()}
            placeholder="Search domain or topic..."
          />
          <input type="number" min={1} max={30} value={days} onChange={(event) => setDays(Number(event.target.value))} />
          <button className="primary" onClick={() => run()} disabled={loading}>
            {loading ? "Analyzing..." : "Run"}
          </button>
          <button className="secondary" onClick={downloadReview} disabled={!data}><Download size={16} /> Export</button>
        </div>
      </header>

      {/* Dynamic Topic Pills */}
      <div className="topicPresetBar" style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "14px 0" }}>
        {availableTopics.slice(0, 10).map((item) => (
          <button
            className={topic.toLowerCase() === item.topic.toLowerCase() ? "active" : ""}
            key={item.topic}
            onClick={() => {
              setTopic(item.topic);
              run(item.topic);
            }}
            style={{ fontSize: 12, padding: "5px 12px", borderRadius: 16 }}
          >
            {item.topic} <span style={{ opacity: 0.6, fontSize: 10 }}>({item.count})</span>
          </button>
        ))}
      </div>

      {data && (
        <div className="evolutionGrid">
          <article className="panel">
            <div className="sectionTitle">
              <Sparkles size={18} />
              <h2>Literature Review</h2>
            </div>
            <p className="lead">{data.literature_review}</p>
          </article>

          <article className="panel">
            <div className="sectionTitle">
              <BookOpen size={18} />
              <h2>Reading Plan ({days} Days)</h2>
            </div>
            <div className="readingPlan">
              {data.reading_plan.map((day) => (
                <div key={day.day} className="planDay">
                  <strong>Day {day.day}</strong>
                  <ul>
                    {day.papers.length ? day.papers.map((title) => <li key={title}>{title}</li>) : <li>Synthesis and notes buffer</li>}
                  </ul>
                </div>
              ))}
            </div>
          </article>

          <article className="panel fullWidth">
            <div className="sectionTitle">
              <GitBranch size={18} />
              <h2>Methodology Transitions & Progression</h2>
            </div>
            <div className="stepList">
              {data.steps.length ? (
                data.steps.map((step, index) => (
                  <div key={index} className="stepCard">
                    <div className="stepHeader">
                      <span className="stepNode">{step.from}</span>
                      <span className="stepArrow">&rarr;</span>
                      <span className="stepNode">{step.to}</span>
                    </div>
                    <div className="stepDetails">
                      <p><strong>Solved:</strong> {step.solved}</p>
                      <p><strong>Left open:</strong> {step.left_open}</p>
                      <p><strong>Next fixed:</strong> {step.next_fixed}</p>
                    </div>
                    <p className="stepNote">{step.note}</p>
                  </div>
                ))
              ) : (
                <p>No direct extension edges found for this subset. Showing standalone chronological papers below.</p>
              )}
            </div>
          </article>

          <article className="panel fullWidth">
            <div className="sectionTitle">
              <BookOpen size={18} />
              <h2>Topic Papers ({data.papers.length})</h2>
            </div>
            <div className="paperList">
              {data.papers.map((paper) => (
                <div key={paper.id} className="paperItem">
                  <div className="paperItemHeader">
                    <strong>{paper.title}</strong>
                    <span>{paper.year ?? "N/A"}</span>
                  </div>
                  <p className="authors">{paper.authors}</p>
                  <p className="contribution"><strong>Contribution:</strong> {paper.contribution}</p>
                </div>
              ))}
            </div>
          </article>
        </div>
      )}
    </section>
  );
}
