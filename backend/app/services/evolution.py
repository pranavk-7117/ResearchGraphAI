"""
Evidence-Backed Evolution Chain Service for ResearchGraphAI.

Constructs 3 distinct evolutionary perspectives:
1. Citation Timeline: Direct lineage traced along verified citation edges.
2. Method & Metric Progression: Structured diffs of methods, datasets, and performance over time.
3. Finding Dynamics: Documented confirmations and contradictions across papers.

Each transition carries explicit basis provenance (citation_metadata / extracted_text / llm_inference)
and evidence citations. Never fabricates claims of superiority or fixing limitations without direct evidence.
"""

from typing import Any
from sqlalchemy.orm import Session

from app import models
from app.services.llm import LLMService


class EvolutionService:
    def __init__(self):
        self.llm = LLMService()

    def generate_evolution(
        self,
        db: Session,
        project_id: int,
    ) -> dict[str, Any]:
        """Generate structured evolution analysis across the project corpus."""
        # Clear old transitions
        db.query(models.EvolutionTransition).filter(
            models.EvolutionTransition.project_id == project_id
        ).delete()
        db.commit()

        # Fetch papers in project sorted chronologically
        project_papers = (
            db.query(models.ProjectPaper)
            .filter(models.ProjectPaper.project_id == project_id)
            .all()
        )
        paper_ids = [p.paper_id for p in project_papers]
        if not paper_ids:
            return {"citation_timeline": [], "method_progression": [], "finding_dynamics": []}

        papers = (
            db.query(models.Paper)
            .filter(models.Paper.id.in_(paper_ids))
            .order_by(models.Paper.year.asc().nullslast(), models.Paper.id.asc())
            .all()
        )
        paper_map = {p.id: p for p in papers}

        # Fetch relations
        relations = (
            db.query(models.PaperRelation)
            .filter(models.PaperRelation.project_id == project_id)
            .all()
        )

        # Fetch facts
        facts = (
            db.query(models.PaperFact)
            .filter(models.PaperFact.paper_id.in_(paper_ids))
            .all()
        )
        facts_map = {f.paper_id: f for f in facts}

        citation_timeline = []
        method_progression = []
        finding_dynamics = []

        # 1. View A: Citation Timeline from verified citation edges
        citation_edges = [r for r in relations if r.relation_type == "cites"]
        for edge in citation_edges:
            citing = paper_map.get(edge.source_id)
            cited = paper_map.get(edge.target_id)
            if not citing or not cited:
                continue

            explanation = (
                f"'{citing.title}' ({citing.year or 'n.d.'}) cites '{cited.title}' ({cited.year or 'n.d.'}) "
                "as foundational or related literature."
            )

            trans = models.EvolutionTransition(
                project_id=project_id,
                from_paper_id=cited.id,
                to_paper_id=citing.id,
                kind="citation",
                explanation=explanation,
                evidence=[{"basis": "Citation metadata record", "source": citing.source_name}],
                basis="citation_metadata",
            )
            db.add(trans)
            citation_timeline.append({
                "from_paper": {"id": cited.id, "title": cited.title, "year": cited.year},
                "to_paper": {"id": citing.id, "title": citing.title, "year": citing.year},
                "kind": "citation",
                "explanation": explanation,
                "basis": "citation_metadata",
            })

        # 2. View B: Method & Metric Progression (Chronological or Adjacent Facts)
        for i in range(len(papers) - 1):
            p1 = papers[i]
            p2 = papers[i + 1]
            f1 = facts_map.get(p1.id)
            f2 = facts_map.get(p2.id)

            m1 = f1.method.get("value") if f1 and f1.method else None
            m2 = f2.method.get("value") if f2 and f2.method else None
            d1 = f1.dataset.get("value") if f1 and f1.dataset else None
            d2 = f2.dataset.get("value") if f2 and f2.dataset else None

            if m1 or m2 or d1 or d2:
                explanation = (
                    f"Chronological progression from {p1.year or 'earlier'} to {p2.year or 'later'}: "
                    f"'{p1.title}' evaluated {m1 or 'baseline methods'} on {d1 or 'benchmark data'}, "
                    f"whereas '{p2.title}' investigated {m2 or 'subsequent techniques'} on {d2 or 'corresponding datasets'}."
                )
                trans = models.EvolutionTransition(
                    project_id=project_id,
                    from_paper_id=p1.id,
                    to_paper_id=p2.id,
                    kind="method_change",
                    explanation=explanation,
                    evidence=[
                        {"paper_id": p1.id, "method": m1, "dataset": d1},
                        {"paper_id": p2.id, "method": m2, "dataset": d2},
                    ],
                    basis="extracted_text",
                )
                db.add(trans)
                method_progression.append({
                    "from_paper": {"id": p1.id, "title": p1.title, "year": p1.year, "method": m1, "dataset": d1},
                    "to_paper": {"id": p2.id, "title": p2.title, "year": p2.year, "method": m2, "dataset": d2},
                    "kind": "method_change",
                    "explanation": explanation,
                    "basis": "extracted_text",
                })

        # 3. View C: Finding Confirmations & Contradictions (synthesized if LLM available)
        if self.llm.is_available() and len(papers) >= 2:
            try:
                # Compare top 2 papers' results
                p_early = papers[0]
                p_late = papers[-1]
                f_early = facts_map.get(p_early.id)
                f_late = facts_map.get(p_late.id)

                res_early = f_early.results.get("value") if f_early and f_early.results else p_early.abstract
                res_late = f_late.results.get("value") if f_late and f_late.results else p_late.abstract

                if res_early and res_late:
                    prompt = (
                        f"Compare the findings of Paper A ('{p_early.title}', {p_early.year}) and Paper B ('{p_late.title}', {p_late.year}):\n"
                        f"Paper A Results: {res_early[:400]}\n"
                        f"Paper B Results: {res_late[:400]}\n\n"
                        "State in 2 sentences whether Paper B confirms, extends, or contradicts Paper A's findings, "
                        "and what conditions differ. Be precise and avoid generic praise."
                    )
                    synth = self.llm.complete(prompt).strip()
                    kind = "finding_confirms" if "confirm" in synth.lower() or "extend" in synth.lower() else "finding_contradicts"

                    trans = models.EvolutionTransition(
                        project_id=project_id,
                        from_paper_id=p_early.id,
                        to_paper_id=p_late.id,
                        kind=kind,
                        explanation=synth,
                        evidence=[{"early": res_early[:200], "late": res_late[:200]}],
                        basis="llm_inference",
                    )
                    db.add(trans)
                    finding_dynamics.append({
                        "from_paper": {"id": p_early.id, "title": p_early.title, "year": p_early.year},
                        "to_paper": {"id": p_late.id, "title": p_late.title, "year": p_late.year},
                        "kind": kind,
                        "explanation": synth,
                        "basis": "llm_inference",
                    })
            except Exception:
                pass

        db.commit()

        return {
            "citation_timeline": citation_timeline,
            "method_progression": method_progression,
            "finding_dynamics": finding_dynamics,
        }
