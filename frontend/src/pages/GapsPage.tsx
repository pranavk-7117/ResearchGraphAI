import { AlertTriangle, CheckCircle2, GitBranch, Lightbulb, Network, Target } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, GapSuggestion, GapsResponse, Workspace } from "../lib/api";

export function GapsPage({ workspace }: { workspace: Workspace | null }) {
  const [data, setData] = useState<GapsResponse | null>(null);
  const [selectedCluster, setSelectedCluster] = useState<number | "all">("all");

  useEffect(() => {
    api.gaps(workspace?.id).then((result) => {
      setData(result);
      setSelectedCluster(result.gap_suggestions[0]?.cluster ?? "all");
    });
  }, [workspace?.id]);

  const selectedGap = useMemo(() => {
    if (!data) return null;
    if (selectedCluster === "all") return data.gap_suggestions[0] ?? null;
    return data.gap_suggestions.find((gap) => gap.cluster === selectedCluster) ?? null;
  }, [data, selectedCluster]);

  const averageCoverage = data?.gap_suggestions.length
    ? Math.round(data.gap_suggestions.reduce((sum, gap) => sum + gap.coverage_score, 0) / data.gap_suggestions.length)
    : 0;

  return (
    <section className="page gapsPage">
      <header className="pageHeader inlineHeader">
        <div>
          <h1>Gap Analysis</h1>
          <p>Scan clusters, compare evidence strength, and turn weak graph regions into research questions.</p>
        </div>
        <select value={selectedCluster} onChange={(event) => setSelectedCluster(event.target.value === "all" ? "all" : Number(event.target.value))}>
          <option value="all">Show first cluster</option>
          {data?.gap_suggestions.map((gap) => (
            <option key={gap.cluster} value={gap.cluster}>Cluster {gap.cluster}: {gap.topic}</option>
          ))}
        </select>
      </header>

      <div className="gapMetrics">
        <article><Network size={18} /><strong>{data?.gap_suggestions.length ?? 0}</strong><span>clusters</span></article>
        <article><GitBranch size={18} /><strong>{data?.gap_suggestions.reduce((sum, gap) => sum + gap.paper_count, 0) ?? 0}</strong><span>papers</span></article>
        <article><Target size={18} /><strong>{averageCoverage}%</strong><span>avg coverage</span></article>
        <article><AlertTriangle size={18} /><strong>{data?.missing_citations.length ?? 0}</strong><span>citation flags</span></article>
      </div>

      <div className="clusterSummaryGrid">
        {data?.gap_suggestions.map((gap) => (
          <button
            className={selectedGap?.cluster === gap.cluster ? "clusterSummary active" : "clusterSummary"}
            key={gap.cluster}
            onClick={() => setSelectedCluster(gap.cluster)}
          >
            <span>Cluster {gap.cluster}</span>
            <strong>{gap.topic}</strong>
            <em>{gap.opportunity_type}</em>
            <small>{gap.coverage_score}% coverage · {gap.paper_count} papers</small>
          </button>
        ))}
      </div>

      {selectedGap && (
        <article className="gapDetail">
          <div className="gapDetailHeader">
            <div>
              <span className="eyebrow">Cluster {selectedGap.cluster} · {selectedGap.opportunity_type}</span>
              <h2>{selectedGap.topic}</h2>
            </div>
            <div className="coverageRing">
              <strong>{selectedGap.coverage_score}</strong>
              <span>/100</span>
            </div>
          </div>

          <div className="gapStats">
            <span>{selectedGap.paper_count} papers</span>
            <span>{selectedGap.edge_count} edges</span>
            <span>{selectedGap.average_degree} avg degree</span>
          </div>

          <p className="gapSummary"><strong>Potential gap:</strong> {selectedGap.suggestion.replace(/^Potential gap:\s*/i, "")}</p>

          <div className="gapInsightGrid">
            <section>
              <h3><Lightbulb size={15} /> Research Questions</h3>
              <ol>
                {selectedGap.research_questions.map((question) => <li key={question}>{question}</li>)}
              </ol>
            </section>
            <section>
              <h3><CheckCircle2 size={15} /> Next Steps</h3>
              <ol>
                {selectedGap.next_steps.map((step) => <li key={step}>{step}</li>)}
              </ol>
            </section>
            <section>
              <h3><Target size={15} /> Weak Signals</h3>
              <div className="tagList">
                {selectedGap.weak_edge_types.map((signal) => <span key={signal}>{signal}</span>)}
              </div>
              <h3><GitBranch size={15} /> Bridge Candidates</h3>
              <ul>
                {selectedGap.bridge_candidates.map((paper) => <li key={paper}>{paper}</li>)}
              </ul>
            </section>
          </div>

          <div className="candidateStrip">
            <strong>Low-degree papers to inspect</strong>
            <span>{selectedGap.candidate_papers.join(", ")}</span>
          </div>
        </article>
      )}

      <h2 className="sectionTitle">Missing Citation Checks</h2>
      <div className="citationFlagGrid">
        {data?.missing_citations?.length ? data.missing_citations.slice(0, 8).map((item) => (
          <article className="citationFlag" key={`${item.paper}-${item.may_need_citation}`}>
            <strong>{item.paper}</strong>
            <span>may be missing a citation to</span>
            <strong>{item.may_need_citation}</strong>
            <em>{item.similarity}</em>
          </article>
        )) : <p className="muted">No high-confidence missing citations flagged.</p>}
      </div>
    </section>
  );
}
