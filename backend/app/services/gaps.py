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

import hashlib
import math
from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.clients import OpenAlexClient
from app.services.llm import LLMService, post_validate_citation


def compute_gap_score(verified_supporting_count: int, verified_counter_count: int, evidence_qual: float) -> float:
    """Deterministic gap score formula excluding unverified quotes."""
    if verified_supporting_count <= 0:
        return 0.1
    raw_score = (
        (min(verified_supporting_count, 5) * 0.1)
        + (evidence_qual * 0.4)
        + 0.2
        - (verified_counter_count * 0.1)
    )
    return round(max(0.1, min(1.0, raw_score)), 3)


def verify_evidence_list(
    items: list[dict[str, Any]],
    chunks_by_paper_id: dict[int, list[dict[str, Any]]],
    title_to_paper_id: dict[str, int],
) -> list[dict[str, Any]]:
    """Verify each evidence quote strictly against the cited paper's stored chunks."""
    verified_items: list[dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        quote = (item.get("quote") or "").strip()
        pid = item.get("paper_id")
        if pid is None and item.get("paper_title"):
            pid = title_to_paper_id.get(str(item["paper_title"]).strip().lower())
            if pid is not None:
                item["paper_id"] = pid

        claimed_chunk_id = item.get("chunk_id")
        result = {"verified": False, "chunk_id": claimed_chunk_id, "match_type": "none", "score": 0.0}

        if quote and pid is not None and pid in chunks_by_paper_id:
            paper_chunks = chunks_by_paper_id[pid]
            if claimed_chunk_id is not None:
                target_chunk = next((c for c in paper_chunks if c["chunk_id"] == claimed_chunk_id), None)
                if target_chunk:
                    result = post_validate_citation(quote, target_chunk["text"], chunk_id=claimed_chunk_id)
            else:
                for ch in paper_chunks:
                    res = post_validate_citation(quote, ch["text"], chunk_id=ch["chunk_id"])
                    if res["verified"]:
                        result = res
                        break

        item["verified"] = bool(result["verified"])
        item["chunk_id"] = result["chunk_id"] if result["verified"] else claimed_chunk_id
        item["match_type"] = result["match_type"]
        verified_items.append(item)
    return verified_items


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
        # Clear existing non-saved gaps for this project (handling SQL NULL semantics)
        from sqlalchemy import or_
        db.query(models.ResearchGap).filter(
            models.ResearchGap.project_id == project_id,
            or_(
                models.ResearchGap.user_feedback.is_(None),
                models.ResearchGap.user_feedback != "saved",
            ),
        ).delete(synchronize_session=False)
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
        title_to_paper_id = {p.title.strip().lower(): p.id for p in papers if p.title}

        all_chunks = (
            db.query(models.PaperChunk)
            .filter(models.PaperChunk.paper_id.in_(paper_ids))
            .order_by(models.PaperChunk.paper_id, models.PaperChunk.chunk_index)
            .all()
        )
        chunks_by_paper_id: dict[int, list[dict[str, Any]]] = {}
        for c in all_chunks:
            chunks_by_paper_id.setdefault(c.paper_id, []).append(
                {"chunk_id": c.id, "text": c.text, "page": c.page_start}
            )

        facts = db.query(models.PaperFact).filter(models.PaperFact.paper_id.in_(paper_ids)).all()

        # Collect documented limitations and future work (keep verification flag)
        evidence_signals: list[dict[str, Any]] = []
        for f in facts:
            p = paper_map.get(f.paper_id)
            if not p:
                continue

            for signal_type, field_obj in (("limitation", f.limitations), ("future_work", f.future_work)):
                if not isinstance(field_obj, dict):
                    continue
                val = field_obj.get("value")
                if not val:
                    continue
                evidence_signals.append({
                    "paper_id": p.id,
                    "title": p.title,
                    "year": p.year,
                    "type": signal_type,
                    "text": val,
                    "quote": field_obj.get("quote") or "",
                    "page": field_obj.get("page") or 1,
                    "chunk_id": field_obj.get("chunk_id"),
                    "verified": bool(field_obj.get("verified", False)),
                })

        # If insufficient signals and no LLM, return empty without padding
        if not evidence_signals or not self.llm.is_available():
            return []

        # Prefer verified signals in prompt context
        ordered_signals = sorted(evidence_signals, key=lambda s: (not s["verified"], s["paper_id"]))
        context_items = []
        for s in ordered_signals[:15]:
            context_items.append(
                f"- [paper_id={s['paper_id']}, chunk_id={s['chunk_id']}, {s['title']} ({s['year'] or 'n.d.'}) - Page {s['page']}]: "
                f"{s['type'].upper()}: {s['text']} (Quote: \"{s['quote']}\")"
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
        existing_hashes = {
            r[0]
            for r in db.query(models.ResearchGap.statement_hash)
            .filter(
                models.ResearchGap.project_id == project_id,
                models.ResearchGap.corpus_version == project.corpus_version,
            )
            .all()
        }

        for g in batch.gaps:
            stmt_hash = hashlib.sha256(g.gap_statement.strip().lower().encode("utf-8")).hexdigest()
            if stmt_hash in existing_hashes:
                continue
            existing_hashes.add(stmt_hash)

            # 1. Verify quotes strictly against stored chunks (keep unverified flagged, exclude from score)
            sup_ev = verify_evidence_list(g.supporting_evidence, chunks_by_paper_id, title_to_paper_id)
            cnt_ev = verify_evidence_list(g.counter_evidence, chunks_by_paper_id, title_to_paper_id)

            verified_sup = [e for e in sup_ev if e.get("verified") is True]
            verified_cnt = [e for e in cnt_ev if e.get("verified") is True]

            num_evidence = len(verified_sup)
            num_counter = len(verified_cnt)
            evidence_qual = 0.85 if num_evidence > 0 else 0.0
            final_score = compute_gap_score(num_evidence, num_counter, evidence_qual)

            score_components = {
                "formula": "min(1.0, max(0.1, min(verified_supporting_count, 5)*0.1 + evidence_quality*0.4 + 0.2 - verified_counter_count*0.1)) if verified_supporting_count > 0 else 0.1",
                "formula_version": "1.1",
                "evidence_quality": evidence_qual,
                "supporting_papers_count": num_evidence,
                "total_supporting_quotes": len(sup_ev),
                "unverified_quotes_excluded": len(sup_ev) - num_evidence,
                "counter_evidence_count": num_counter,
                "calculated_strength": final_score,
            }

            # 2. Targeted external check in OpenAlex for gap terms
            external_info = self._external_openalex_check(g.gap_statement)

            gap_row = models.ResearchGap(
                project_id=project_id,
                corpus_version=project.corpus_version,
                statement_hash=stmt_hash,
                gap_statement=g.gap_statement,
                why_it_matters=g.why_it_matters,
                gap_type=g.gap_type,
                supporting_evidence=sup_ev,
                counter_evidence=cnt_ev,
                corpus_cannot_establish=g.corpus_cannot_establish,
                suggested_research_question=g.suggested_research_question,
                suggested_validation=g.suggested_validation,
                score_components=score_components,
                formula_version="1.1",
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
