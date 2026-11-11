"""
Evidence-Backed Evolution Chain Service for ResearchGraphAI.

Constructs 3 distinct evolutionary perspectives without fabricated filler:
1. Citation Timeline: Direct lineage traced along verified citation edges, or
   chronological semantic similarity edges when citations are absent.
2. Method & Metric Progression: Chronological diffs across extracted methods & datasets.
3. Finding Dynamics: Structured LLM comparison of top-N high-similarity chronological
   pairs with strict quote verification against stored chunk/abstract text.
"""

from collections import Counter
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.services.constants import (
    BASIS_CITATION_METADATA,
    BASIS_EMBEDDING_SIMILARITY,
    BASIS_EXTRACTED_TEXT,
    BASIS_LLM_INFERENCE,
    KIND_CITATION,
    KIND_METHOD_CHANGE,
    KIND_THEMATIC_LINEAGE,
    RELATION_CITES,
    RELATION_SIMILAR,
)
from app.services.llm import LLMService, post_validate_citation


class FindingRelationEnum(str, Enum):
    confirms = "confirms"
    extends = "extends"
    contradicts = "contradicts"
    unrelated = "unrelated"
    insufficient_evidence = "insufficient_evidence"


class FindingComparisonSchema(BaseModel):
    relation: FindingRelationEnum = Field(description="Relationship between the later paper and earlier paper findings")
    explanation: str = Field(description="Concise factual summary grounded strictly in the provided texts")
    quote_from_earlier: str = Field(description="Exact verbatim quote from the earlier paper's provided text")
    quote_from_later: str = Field(description="Exact verbatim quote from the later paper's provided text")


class EvolutionService:
    def __init__(self):
        self.llm = LLMService()

    def _paper_text_units(
        self, paper: models.Paper, chunks_by_pid: dict[int, list[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        """Return stored text units (chunks, falling back to abstract) for strict quote verification."""
        units = list(chunks_by_pid.get(paper.id, []))
        if not units and paper.abstract:
            units.append({"chunk_id": None, "text": paper.abstract})
        return units

    def _verify_quote_in_paper(
        self, quote: str, units: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Verify quote strictly against at least one stored chunk/text unit of the paper."""
        if not quote or not quote.strip() or not units:
            return {"verified": False, "chunk_id": None, "match_type": "none", "score": 0.0}
        for u in units:
            res = post_validate_citation(quote, u["text"], chunk_id=u.get("chunk_id"))
            if res["verified"]:
                return res
        return {"verified": False, "chunk_id": None, "match_type": "none", "score": 0.0}

    def generate_evolution(
        self,
        db: Session,
        project_id: int,
        top_n_finding_pairs: int = 5,
    ) -> dict[str, Any]:
        """Generate structured, honest evolution analysis across the project corpus."""
        db.query(models.EvolutionTransition).filter(
            models.EvolutionTransition.project_id == project_id
        ).delete()
        db.commit()

        project_papers = (
            db.query(models.ProjectPaper)
            .filter(models.ProjectPaper.project_id == project_id)
            .all()
        )
        paper_ids = [p.paper_id for p in project_papers]
        if not paper_ids:
            return {
                "citation_timeline": [],
                "method_progression": [],
                "finding_dynamics": [],
                "phases": [],
                "transitions": [],
                "annual_milestones": [],
                "paper_stream": [],
                "focus_trends": {"years": [], "series": []},
                "key_insights": [],
                "time_range": {},
                "total_papers": 0,
            }

        papers = (
            db.query(models.Paper)
            .filter(models.Paper.id.in_(paper_ids))
            .order_by(models.Paper.year.asc().nullslast(), models.Paper.id.asc())
            .all()
        )
        paper_map = {p.id: p for p in papers}

        relations = (
            db.query(models.PaperRelation)
            .filter(models.PaperRelation.project_id == project_id)
            .all()
        )
        facts = (
            db.query(models.PaperFact)
            .filter(models.PaperFact.paper_id.in_(paper_ids))
            .all()
        )
        facts_map = {f.paper_id: f for f in facts}

        all_chunks = (
            db.query(models.PaperChunk)
            .filter(models.PaperChunk.paper_id.in_(paper_ids))
            .order_by(models.PaperChunk.paper_id, models.PaperChunk.chunk_index)
            .all()
        )
        chunks_by_pid: dict[int, list[dict[str, Any]]] = {}
        for c in all_chunks:
            chunks_by_pid.setdefault(c.paper_id, []).append(
                {"chunk_id": c.id, "text": c.text}
            )

        citation_timeline: list[dict[str, Any]] = []
        method_progression: list[dict[str, Any]] = []
        finding_dynamics: list[dict[str, Any]] = []

        # 1. Citation Timeline (verified citations, or similarity fallback)
        citation_edges = [r for r in relations if r.relation_type == RELATION_CITES]
        for edge in citation_edges:
            citing = paper_map.get(edge.source_id)
            cited = paper_map.get(edge.target_id)
            if not citing or not cited:
                continue

            explanation = (
                f"'{citing.title}' ({citing.year or 'n.d.'}) cites "
                f"'{cited.title}' ({cited.year or 'n.d.'})."
            )
            db.add(models.EvolutionTransition(
                project_id=project_id,
                from_paper_id=cited.id,
                to_paper_id=citing.id,
                kind=KIND_CITATION,
                explanation=explanation,
                evidence=[{"basis": "Citation metadata record", "source": citing.source_name}],
                basis=BASIS_CITATION_METADATA,
            ))
            citation_timeline.append({
                "from_paper": {"id": cited.id, "title": cited.title, "year": cited.year},
                "to_paper": {"id": citing.id, "title": citing.title, "year": citing.year},
                "kind": KIND_CITATION,
                "explanation": explanation,
                "basis": BASIS_CITATION_METADATA,
            })

        sim_edges = [
            r for r in relations
            if r.relation_type == RELATION_SIMILAR and (r.score or 0.0) >= 0.55
        ]
        sim_edges.sort(key=lambda x: x.score or 0.0, reverse=True)

        if not citation_timeline and sim_edges:
            added_pairs: set[tuple[int, int]] = set()
            for edge in sim_edges:
                p_src = paper_map.get(edge.source_id)
                p_tgt = paper_map.get(edge.target_id)
                if not p_src or not p_tgt or p_src.id == p_tgt.id:
                    continue

                if (p_src.year or 9999, p_src.id) <= (p_tgt.year or 9999, p_tgt.id):
                    earlier, later = p_src, p_tgt
                else:
                    earlier, later = p_tgt, p_src

                pair_key = (earlier.id, later.id)
                if pair_key in added_pairs:
                    continue
                added_pairs.add(pair_key)

                sim_score = round(float(edge.score or 0.0), 3)
                explanation = (
                    f"Chronological similarity edge (cosine {sim_score}): "
                    f"'{earlier.title}' ({earlier.year or 'n.d.'}) -> '{later.title}' ({later.year or 'n.d.'})."
                )
                db.add(models.EvolutionTransition(
                    project_id=project_id,
                    from_paper_id=earlier.id,
                    to_paper_id=later.id,
                    kind=KIND_THEMATIC_LINEAGE,
                    explanation=explanation,
                    evidence=[{"basis": BASIS_EMBEDDING_SIMILARITY, "similarity_score": sim_score}],
                    basis=BASIS_EMBEDDING_SIMILARITY,
                ))
                citation_timeline.append({
                    "from_paper": {"id": earlier.id, "title": earlier.title, "year": earlier.year},
                    "to_paper": {"id": later.id, "title": later.title, "year": later.year},
                    "kind": KIND_THEMATIC_LINEAGE,
                    "explanation": explanation,
                    "basis": BASIS_EMBEDDING_SIMILARITY,
                })
                if len(citation_timeline) >= 8:
                    break

        # 2. Method & Metric Progression (strictly from extracted PaperFact fields)
        for p1, p2 in zip(papers, papers[1:]):
            f1 = facts_map.get(p1.id)
            f2 = facts_map.get(p2.id)
            m1 = f1.method.get("value") if f1 and isinstance(f1.method, dict) else None
            m2 = f2.method.get("value") if f2 and isinstance(f2.method, dict) else None
            d1 = f1.dataset.get("value") if f1 and isinstance(f1.dataset, dict) else None
            d2 = f2.dataset.get("value") if f2 and isinstance(f2.dataset, dict) else None

            if not (m1 or m2 or d1 or d2):
                continue

            parts = []
            if m1 or m2:
                parts.append(f"methods: {m1 or 'not reported'} -> {m2 or 'not reported'}")
            if d1 or d2:
                parts.append(f"datasets: {d1 or 'not reported'} -> {d2 or 'not reported'}")
            explanation = (
                f"{p1.title[:60]} ({p1.year or 'n.d.'}) to {p2.title[:60]} ({p2.year or 'n.d.'}): "
                + "; ".join(parts)
            )
            db.add(models.EvolutionTransition(
                project_id=project_id,
                from_paper_id=p1.id,
                to_paper_id=p2.id,
                kind=KIND_METHOD_CHANGE,
                explanation=explanation,
                evidence=[
                    {"paper_id": p1.id, "method": m1, "dataset": d1},
                    {"paper_id": p2.id, "method": m2, "dataset": d2},
                ],
                basis=BASIS_EXTRACTED_TEXT,
            ))
            method_progression.append({
                "from_paper": {"id": p1.id, "title": p1.title, "year": p1.year, "method": m1, "dataset": d1},
                "to_paper": {"id": p2.id, "title": p2.title, "year": p2.year, "method": m2, "dataset": d2},
                "kind": KIND_METHOD_CHANGE,
                "explanation": explanation,
                "basis": BASIS_EXTRACTED_TEXT,
            })

        # 3. Finding Dynamics: top-N high-similarity chronological pairs, Pydantic enum + quote verification
        candidate_pairs: list[tuple[models.Paper, models.Paper, float]] = []
        seen_dyn_pairs: set[tuple[int, int]] = set()
        for edge in sim_edges:
            p_a = paper_map.get(edge.source_id)
            p_b = paper_map.get(edge.target_id)
            if not p_a or not p_b or p_a.id == p_b.id:
                continue
            if (p_a.year or 9999, p_a.id) <= (p_b.year or 9999, p_b.id):
                earlier, later = p_a, p_b
            else:
                earlier, later = p_b, p_a
            if (earlier.id, later.id) not in seen_dyn_pairs:
                seen_dyn_pairs.add((earlier.id, later.id))
                candidate_pairs.append((earlier, later, float(edge.score or 0.0)))

        if not candidate_pairs and len(papers) >= 2:
            for p_a, p_b in zip(papers, papers[1:]):
                if (p_a.id, p_b.id) not in seen_dyn_pairs:
                    seen_dyn_pairs.add((p_a.id, p_b.id))
                    candidate_pairs.append((p_a, p_b, 0.0))

        if self.llm.is_available() and candidate_pairs:
            for earlier, later, _score in candidate_pairs[:top_n_finding_pairs]:
                e_units = self._paper_text_units(earlier, chunks_by_pid)
                l_units = self._paper_text_units(later, chunks_by_pid)
                if not e_units or not l_units:
                    continue

                e_ctx = "\n".join(u["text"] for u in e_units[:3])[:1200]
                l_ctx = "\n".join(u["text"] for u in l_units[:3])[:1200]

                prompt = (
                    f"Earlier Paper ('{earlier.title}', {earlier.year or 'n.d.'}):\n{e_ctx}\n\n"
                    f"Later Paper ('{later.title}', {later.year or 'n.d.'}):\n{l_ctx}\n\n"
                    "Classify the relationship of the Later Paper's findings to the Earlier Paper's findings "
                    "using ONLY the provided text excerpts. Return one verbatim quote from each paper."
                )
                sys_prompt = (
                    "You are a scientific comparison engine. Return valid JSON matching the schema. "
                    "Never invent quotes; copy verbatim substrings from the provided excerpts."
                )
                try:
                    comp: FindingComparisonSchema = self.llm.generate_structured(
                        schema=FindingComparisonSchema,
                        prompt=prompt,
                        system_prompt=sys_prompt,
                    )
                    v_early = self._verify_quote_in_paper(comp.quote_from_earlier, e_units)
                    v_later = self._verify_quote_in_paper(comp.quote_from_later, l_units)
                    if v_early["verified"] and v_later["verified"]:
                        final_kind = comp.relation.value
                        verified_pair = True
                    else:
                        final_kind = FindingRelationEnum.insufficient_evidence.value
                        verified_pair = False
                    explanation = comp.explanation
                    ev_payload = [
                        {
                            "paper_id": earlier.id,
                            "quote": comp.quote_from_earlier,
                            "verified": v_early["verified"],
                            "chunk_id": v_early["chunk_id"],
                        },
                        {
                            "paper_id": later.id,
                            "quote": comp.quote_from_later,
                            "verified": v_later["verified"],
                            "chunk_id": v_later["chunk_id"],
                        },
                    ]
                except Exception:
                    final_kind = FindingRelationEnum.insufficient_evidence.value
                    verified_pair = False
                    explanation = "Structured finding comparison could not be verified."
                    ev_payload = []

                db.add(models.EvolutionTransition(
                    project_id=project_id,
                    from_paper_id=earlier.id,
                    to_paper_id=later.id,
                    kind=final_kind,
                    explanation=explanation,
                    evidence=ev_payload,
                    basis=BASIS_LLM_INFERENCE,
                ))
                finding_dynamics.append({
                    "from_paper": {"id": earlier.id, "title": earlier.title, "year": earlier.year},
                    "to_paper": {"id": later.id, "title": later.title, "year": later.year},
                    "kind": final_kind,
                    "verified": verified_pair,
                    "explanation": explanation,
                    "evidence": ev_payload,
                    "basis": BASIS_LLM_INFERENCE,
                })

        # 4. Data-driven Phases & Paper Serialization (zero fabricated filler)
        project = db.query(models.ResearchProject).filter(models.ResearchProject.id == project_id).first()
        topic = project.topic.strip() if project and project.topic else ""

        years = [p.year for p in papers if p.year is not None]
        min_year = min(years) if years else None
        max_year = max(years) if years else None

        cluster_records = (
            db.query(models.ResearchCluster)
            .filter(models.ResearchCluster.project_id == project_id)
            .all()
        )
        cluster_members = (
            db.query(models.ClusterMember, models.ResearchCluster)
            .join(models.ResearchCluster, models.ClusterMember.cluster_id == models.ResearchCluster.id)
            .filter(models.ResearchCluster.project_id == project_id)
            .all()
        )
        paper_cluster_map: dict[int, str] = {
            cm.paper_id: rc.label for cm, rc in cluster_members
        }

        def serialize_paper(p: models.Paper) -> dict[str, Any]:
            authors_list = [
                a.get("name") for a in (p.authors or []) if isinstance(a, dict) and a.get("name")
            ]
            f = facts_map.get(p.id)
            method_val = f.method.get("value") if f and isinstance(f.method, dict) else None
            lim_val = f.limitations.get("value") if f and isinstance(f.limitations, dict) else None
            contrib_val = (
                f.claimed_contributions.get("value")
                if f and isinstance(f.claimed_contributions, dict)
                else None
            )

            return {
                "id": p.id,
                "title": p.title,
                "year": p.year,
                "authors_str": ", ".join(authors_list[:3]) if authors_list else None,
                "abstract": p.abstract,
                "venue": p.venue,
                "pub_type": None,
                "citation_count": p.citation_count or 0,
                "doi": p.doi,
                "url": p.original_url or (f"https://doi.org/{p.doi}" if p.doi else None),
                "topic_tag": paper_cluster_map.get(p.id),
                "key_contribution": contrib_val or method_val,
                "gaps_solved": [lim_val] if lim_val else [],
                "new_aspects": [],
            }

        # Group papers into up to 4 chronological windows; OMIT empty windows
        phases_out: list[dict[str, Any]] = []
        phase_papers_by_num: dict[int, list[models.Paper]] = {}
        if min_year is not None and max_year is not None:
            if min_year == max_year:
                windows = [(min_year, max_year)]
            else:
                span = max_year - min_year
                n_bins = min(4, span + 1)
                step = (span + 1) / n_bins
                windows = []
                for idx in range(n_bins):
                    s = min_year + int(round(idx * step))
                    e = min_year + int(round((idx + 1) * step)) - 1 if idx < n_bins - 1 else max_year
                    if s <= e and (not windows or s > windows[-1][1]):
                        windows.append((s, e))

            for w_idx, (s_yr, e_yr) in enumerate(windows, start=1):
                p_list = [p for p in papers if p.year is not None and s_yr <= p.year <= e_yr]
                if w_idx == 1:
                    p_list.extend([p for p in papers if p.year is None])
                if not p_list:
                    continue  # Omit empty phases completely

                phase_c_labels = [paper_cluster_map[p.id] for p in p_list if p.id in paper_cluster_map]
                if phase_c_labels:
                    title = Counter(phase_c_labels).most_common(1)[0][0]
                    desc = f"{len(p_list)} paper(s); primary cluster: {title}."
                else:
                    title = f"{s_yr}–{e_yr}" if s_yr != e_yr else str(s_yr)
                    desc = None

                phase_num = len(phases_out) + 1
                phase_papers_by_num[phase_num] = p_list
                phases_out.append({
                    "phase_num": phase_num,
                    "start_year": min((p.year for p in p_list if p.year is not None), default=s_yr),
                    "end_year": max((p.year for p in p_list if p.year is not None), default=e_yr),
                    "title": title,
                    "description": desc,
                    "paper_count": len(p_list),
                    "dominant_theme": title if phase_c_labels else None,
                    "papers": [serialize_paper(p) for p in p_list],
                })

        transitions_out: list[dict[str, Any]] = []
        for idx in range(len(phases_out) - 1):
            ph_a = phases_out[idx]
            ph_b = phases_out[idx + 1]
            combined = list({
                p.id: p
                for p in (phase_papers_by_num[ph_a["phase_num"]] + phase_papers_by_num[ph_b["phase_num"]])
            }.values())
            transitions_out.append({
                "phase_from": ph_a["phase_num"],
                "phase_to": ph_b["phase_num"],
                "badge": f"Phase {ph_a['phase_num']} -> Phase {ph_b['phase_num']} ({ph_a['start_year']}–{ph_b['end_year']})",
                "year_range": f"{ph_a['start_year']}–{ph_b['end_year']}",
                "title": f"{ph_a['title']} -> {ph_b['title']}",
                "description": None,
                "key_changes": [],
                "paper_count": len(combined),
                "papers": [serialize_paper(p) for p in combined],
            })

        papers_by_year: dict[int, list[models.Paper]] = {}
        for p in papers:
            if p.year is not None:
                papers_by_year.setdefault(p.year, []).append(p)

        annual_milestones = []
        for yr in sorted(papers_by_year.keys()):
            yr_papers = papers_by_year[yr]
            c_labels = [paper_cluster_map[p.id] for p in yr_papers if p.id in paper_cluster_map]
            top_theme = Counter(c_labels).most_common(1)[0][0] if c_labels else None
            annual_milestones.append({
                "year": yr,
                "paper_count": len(yr_papers),
                "top_theme": top_theme,
                "milestone_title": yr_papers[0].title,
                "papers": [serialize_paper(p) for p in yr_papers],
            })

        paper_stream = [serialize_paper(p) for p in papers]

        trend_years = list(range(min_year, max_year + 1)) if (min_year is not None and max_year is not None) else []
        trend_series = []
        cluster_colors = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b"]
        for idx, cl in enumerate(cluster_records[:4]):
            c_pids = {cm.paper_id for cm, rc in cluster_members if rc.id == cl.id}
            counts = [
                sum(1 for p in papers if p.id in c_pids and p.year == y)
                for y in trend_years
            ]
            trend_series.append({
                "name": cl.label,
                "color": cluster_colors[idx % len(cluster_colors)],
                "data": counts,
            })

        key_insights: list[str] = []
        if min_year is not None and max_year is not None:
            key_insights.append(f"Corpus spans {len(papers)} papers published between {min_year} and {max_year}.")
        if citation_edges:
            key_insights.append(f"Found {len(citation_edges)} verified in-corpus citation edge(s).")
        if cluster_records:
            key_insights.append(f"Organized across {len(cluster_records)} thematic cluster(s).")

        db.commit()

        return {
            "citation_timeline": citation_timeline,
            "method_progression": method_progression,
            "finding_dynamics": finding_dynamics,
            "phases": phases_out,
            "transitions": transitions_out,
            "annual_milestones": annual_milestones,
            "paper_stream": paper_stream,
            "focus_trends": {"years": trend_years, "series": trend_series},
            "key_insights": key_insights,
            "time_range": {"min_year": min_year, "max_year": max_year} if min_year is not None else {},
            "total_papers": len(papers),
        }
