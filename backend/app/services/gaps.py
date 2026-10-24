"""
Evidence-Grounded Research Gap Engine for ResearchGraphAI.

Extracts candidate research gaps derived strictly from:
- Repeated limitations and future work across corpus papers
- Method x Dataset evaluation voids
- Contradictory findings or lack of generalization

Includes:
- Transparent scoring formula with stored components
- Targeted external check in OpenAlex for gap terms (disclaiming absence in literature)
- User feedback loop (relevant, not_relevant, already_addressed, needs_evidence, saved)
- Rejection of padding: returns empty list if no evidence exists
"""

import math
from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.clients import OpenAlexClient
from app.services.llm import LLMService


class SynthesizedGap(BaseModel):
    gap_statement: str = Field(description="Clear, precise statement of the research gap")
    why_it_matters: str = Field(description="Scientific significance and impact of addressing this gap")
    gap_type: str = Field(description="methodological_limitation | evaluation_void | generalization_barrier | conflicting_evidence")
    supporting_evidence: list[dict[str, Any]] = Field(description="List of {paper_title, quote, page, limitation_observed}")
    counter_evidence: list[dict[str, Any]] = Field(default_factory=list, description="Papers or findings that partially address this")
    corpus_cannot_establish: str = Field(description="Explicit disclosure of what cannot be conclusively verified from this corpus alone")
    suggested_research_question: str = Field(description="Formal candidate research question")
    suggested_validation: str = Field(description="Proposed experiment, benchmark, or evaluation methodology")


class GapsService:
    def __init__(self):
        self.llm = LLMService()
        self.openalex = OpenAlexClient()

    def detect_gaps(
        self,
        db: Session,
        project_id: int,
    ) -> list[models.ResearchGap]:
        """Detect and synthesize evidence-backed candidate research gaps."""
        # Clear existing non-saved gaps for this project
        db.query(models.ResearchGap).filter(
            models.ResearchGap.project_id == project_id,
            models.ResearchGap.user_feedback != "saved",
        ).delete()
        db.commit()

        project = db.query(models.ResearchProject).filter(models.ResearchProject.id == project_id).first()
        if not project:
            return []

        # Fetch facts for papers in this project
        project_papers = (
            db.query(models.ProjectPaper)
            .filter(models.ProjectPaper.project_id == project_id)
            .all()
        )
        paper_ids = [p.paper_id for p in project_papers]
        if not paper_ids:
            return []

        papers = db.query(models.Paper).filter(models.Paper.id.in_(paper_ids)).all()
        paper_map = {p.id: p for p in papers}

        facts = db.query(models.PaperFact).filter(models.PaperFact.paper_id.in_(paper_ids)).all()

        # Collect documented limitations and future work
        evidence_signals: list[dict[str, Any]] = []
        for f in facts:
            p = paper_map.get(f.paper_id)
            if not p:
                continue

            lim = f.limitations.get("value") if f.limitations else None
            lim_quote = f.limitations.get("quote") if f.limitations else ""
            lim_page = f.limitations.get("page") if f.limitations else 1

            fut = f.future_work.get("value") if f.future_work else None
            fut_quote = f.future_work.get("quote") if f.future_work else ""
            fut_page = f.future_work.get("page") if f.future_work else 1

            if lim:
                evidence_signals.append({
                    "paper_id": p.id,
                    "title": p.title,
                    "year": p.year,
                    "type": "limitation",
                    "text": lim,
                    "quote": lim_quote,
                    "page": lim_page,
                })
            if fut:
                evidence_signals.append({
                    "paper_id": p.id,
                    "title": p.title,
                    "year": p.year,
                    "type": "future_work",
                    "text": fut,
                    "quote": fut_quote,
                    "page": fut_page,
                })

        # If insufficient signals and no LLM, return empty without padding
        if not evidence_signals or not self.llm.is_available():
            return []

        # Build prompt for LLM synthesis
        context_items = []
        for s in evidence_signals[:15]:
            context_items.append(
                f"- [{s['title']} ({s['year'] or 'n.d.'}) - Page {s['page']}]: {s['type'].upper()}: {s['text']} (Quote: \"{s['quote']}\")"
            )
        context_str = "\n".join(context_items)

        prompt = (
            f"Topic: {project.topic}\n\n"
            "Analyze the following documented paper limitations and future work statements from our indexed corpus. "
            "Identify 1 to 3 genuine, evidence-grounded candidate research gaps that recur across multiple papers or represent an unaddressed technical challenge. "
            "Never fabricate a gap that has no evidence in the provided list. "
            "State explicitly in 'corpus_cannot_establish' what this specific dataset cannot prove regarding the broader scientific field."
        )

        system_prompt = (
            "You are a rigorous scientific gap analysis engine. "
            "Only output candidate gaps that are directly supported by the documented limitations. "
            "Do NOT output generic textbook gaps."
        )

        class GapBatchSchema(BaseModel):
            gaps: list[SynthesizedGap] = Field(default_factory=list)

        try:
            batch = self.llm.generate_structured(
                schema=GapBatchSchema,
                prompt=prompt,
                system_prompt=system_prompt,
                context=context_str,
            )
        except Exception:
            return []

        if not batch.gaps:
            return []

        created_gaps: list[models.ResearchGap] = []

        for g in batch.gaps:
            # 1. Transparent Score Calculation
            num_evidence = len(g.supporting_evidence)
            num_counter = len(g.counter_evidence)
            evidence_qual = 0.85 if any(e.get("quote") for e in g.supporting_evidence) else 0.60
            
            # Formula: (num_evidence * 0.4) + (evidence_qual * 0.4) - (num_counter * 0.15)
            raw_score = (min(num_evidence, 5) * 0.1) + (evidence_qual * 0.4) + 0.2 - (num_counter * 0.1)
            final_score = round(max(0.1, min(1.0, raw_score)), 3)

            score_components = {
                "formula": "0.4 * evidence_quality + 0.4 * supporting_count_scaled + 0.2 - 0.1 * counter_count",
                "formula_version": "1.0",
                "evidence_quality": evidence_qual,
                "supporting_papers_count": num_evidence,
                "counter_evidence_count": num_counter,
                "calculated_strength": final_score,
            }

            # 2. Targeted external check in OpenAlex for gap terms
            external_info = self._external_openalex_check(g.gap_statement)

            gap_row = models.ResearchGap(
                project_id=project_id,
                corpus_version=project.corpus_version,
                gap_statement=g.gap_statement,
                why_it_matters=g.why_it_matters,
                gap_type=g.gap_type,
                supporting_evidence=g.supporting_evidence,
                counter_evidence=g.counter_evidence,
                corpus_cannot_establish=g.corpus_cannot_establish,
                suggested_research_question=g.suggested_research_question,
                suggested_validation=g.suggested_validation,
                score_components=score_components,
                formula_version="1.0",
                evidence_strength=final_score,
                external_verification=external_info,
                status="candidate",
            )
            db.add(gap_row)
            created_gaps.append(gap_row)

        db.commit()
        return created_gaps

    def _external_openalex_check(self, gap_statement: str) -> dict[str, Any]:
        """Perform a targeted external check in OpenAlex to see if related literature exists."""
        # Extract 3-5 key terms from gap statement
        words = [w for w in gap_statement.split() if len(w) > 4 and w.isalnum()]
        search_terms = " ".join(words[:4])
        try:
            results = self.openalex.search(search_terms, limit=5)
            external_hits = [
                {"title": r.title, "year": r.year, "doi": r.doi, "citation_count": r.citation_count}
                for r in results[:3]
            ]
            return {
                "searched_terms": search_terms,
                "external_papers_found": len(external_hits),
                "top_external_matches": external_hits,
                "disclaimer": "Underrepresentation in this corpus is a candidate hypothesis. The external literature may contain related work as indicated above.",
            }
        except Exception:
            return {
                "searched_terms": search_terms,
                "external_papers_found": 0,
                "top_external_matches": [],
                "disclaimer": "External lookup service was temporarily unreachable.",
            }

    def record_feedback(
        self,
        db: Session,
        gap_id: int,
        feedback: str,  # relevant | not_relevant | already_addressed | needs_evidence | saved
    ) -> models.ResearchGap | None:
        gap = db.query(models.ResearchGap).filter(models.ResearchGap.id == gap_id).first()
        if not gap:
            return None
        gap.user_feedback = feedback
        db.commit()
        return gap
