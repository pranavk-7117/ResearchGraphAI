"""
Evidence-Grounded Structured Fact Extraction Service for ResearchGraphAI.

Extracts research problem, methodology, datasets, metrics, results, limitations,
and contributions from paper full-text chunks (or abstract if full text is unavailable).
Every extracted field carries page number, supporting quote, and citation chunk ID,
post-validated against actual stored chunk passages.
"""

from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.services.llm import LLMService, post_validate_citation


class ExtractedField(BaseModel):
    value: str = Field(description="The factual finding or extracted description")
    quote: str = Field(description="Direct verbatim sentence quote from the paper text")
    chunk_id: int | None = Field(default=None, description="Chunk ID from context where quote appears")
    page: int | None = Field(default=None, description="Page number where quote appears")
    confidence: float = Field(default=0.9, description="Confidence score from 0.0 to 1.0")


class PaperFactsSchema(BaseModel):
    research_question: ExtractedField | None = None
    problem: ExtractedField | None = None
    method: ExtractedField | None = None
    algorithm_or_model: ExtractedField | None = None
    dataset: ExtractedField | None = None
    metrics: ExtractedField | None = None
    results: ExtractedField | None = None
    limitations: ExtractedField | None = None
    future_work: ExtractedField | None = None
    claimed_contributions: ExtractedField | None = None


class FactExtractionService:
    def __init__(self):
        self.llm = LLMService()

    def extract_paper_facts(
        self,
        db: Session,
        paper_id: int,
        project_id: int | None = None,
    ) -> models.PaperFact | None:
        """Extract structured facts and persist them linked to paper and chunks."""
        paper = db.query(models.Paper).filter(models.Paper.id == paper_id).first()
        if not paper:
            return None

        # Fetch paper chunks
        chunks = (
            db.query(models.PaperChunk)
            .filter(models.PaperChunk.paper_id == paper_id)
            .order_by(models.PaperChunk.chunk_index)
            .all()
        )

        abstract_only = len(chunks) == 0
        passages: list[dict[str, Any]] = []

        if not abstract_only:
            # Full text passages: pick key chunks (Intro, Methods, Results, Conclusion)
            for c in chunks:
                passages.append({
                    "chunk_id": c.id,
                    "page": c.page_start,
                    "section": c.section,
                    "text": c.text,
                })
        else:
            # Abstract fallback
            passages.append({
                "chunk_id": None,
                "page": 1,
                "section": "Abstract",
                "text": paper.abstract or paper.title,
            })

        if not self.llm.is_available():
            # If LLM is not configured, record minimal placeholder fact showing provider missing
            fact_row = models.PaperFact(
                paper_id=paper_id,
                project_id=project_id,
                problem={"value": f"Analysis for: {paper.title}", "quote": "", "page": 1, "confidence": 0.5},
                extraction_model="unconfigured",
                abstract_only=abstract_only,
            )
            db.add(fact_row)
            db.commit()
            return fact_row

        # Build context prompt
        context_lines = []
        for p in passages[:12]:
            chunk_header = f"[Chunk {p['chunk_id'] or 'Abstract'} - Page {p['page']} - Section: {p['section']}]"
            context_lines.append(f"{chunk_header}\n{p['text']}")
        context_str = "\n\n".join(context_lines)

        prompt = (
            f"Paper Title: {paper.title}\n\n"
            "Carefully analyze the provided paper excerpts. Extract the core scientific facts into structured fields: "
            "research_question, problem, method, algorithm_or_model, dataset, metrics, results, limitations, future_work, claimed_contributions. "
            "For each field, you MUST provide an exact supporting quote from the text and the corresponding page number. "
            "If an excerpt does not discuss a field, leave that field as null instead of inventing or assuming."
        )

        system_prompt = (
            "You are an expert scientific fact extraction engine. "
            "Strictly extract verifiable statements with verbatim quotes from the context. "
            "Never fabricate or guess."
        )

        try:
            facts_data: PaperFactsSchema = self.llm.generate_structured(
                schema=PaperFactsSchema,
                prompt=prompt,
                system_prompt=system_prompt,
                context=context_str,
            )
        except Exception as e:
            # Failed to extract facts from LLM
            fact_row = models.PaperFact(
                paper_id=paper_id,
                project_id=project_id,
                problem={"value": f"Extraction degraded: {e}", "quote": "", "page": 1, "confidence": 0.0},
                extraction_model="error",
                abstract_only=abstract_only,
            )
            db.add(fact_row)
            db.commit()
            return fact_row

        # Post-validate citations strictly against the specific cited chunk
        passages_by_id = {
            p["chunk_id"]: p for p in passages if p.get("chunk_id") is not None
        }

        def format_field(f: ExtractedField | None) -> dict[str, Any] | None:
            if not f or not f.value:
                return None

            verification = {"verified": False, "chunk_id": f.chunk_id, "match_type": "none", "score": 0.0}
            if f.quote and f.quote.strip():
                if f.chunk_id is not None and f.chunk_id in passages_by_id:
                    verification = post_validate_citation(
                        f.quote, passages_by_id[f.chunk_id]["text"], chunk_id=f.chunk_id
                    )
                elif f.chunk_id is None:
                    best_unverified = verification
                    for p in passages:
                        res = post_validate_citation(
                            f.quote, p["text"], chunk_id=p.get("chunk_id")
                        )
                        if res["verified"]:
                            verification = res
                            break
                        if res["score"] > best_unverified["score"]:
                            best_unverified = res
                    else:
                        verification = best_unverified

            valid = bool(verification["verified"])
            return {
                "value": f.value,
                "quote": f.quote,
                "page": f.page,
                "chunk_id": verification["chunk_id"],
                "confidence": f.confidence if valid else round(f.confidence * 0.5, 2),
                "verified": valid,
                "match_type": verification["match_type"],
                "verification_score": verification["score"],
            }

        fact_row = models.PaperFact(
            paper_id=paper_id,
            project_id=project_id,
            research_question=format_field(facts_data.research_question),
            problem=format_field(facts_data.problem),
            method=format_field(facts_data.method),
            algorithm_or_model=format_field(facts_data.algorithm_or_model),
            dataset=format_field(facts_data.dataset),
            metrics=format_field(facts_data.metrics),
            results=format_field(facts_data.results),
            limitations=format_field(facts_data.limitations),
            future_work=format_field(facts_data.future_work),
            claimed_contributions=format_field(facts_data.claimed_contributions),
            extraction_model=self.llm.provider,
            abstract_only=abstract_only,
        )

        db.add(fact_row)
        db.commit()
        return fact_row


FACT_QUOTE_FIELDS = (
    "research_question",
    "problem",
    "method",
    "algorithm_or_model",
    "dataset",
    "metrics",
    "results",
    "limitations",
    "future_work",
    "claimed_contributions",
)


def quote_verification_precision(project_id: int, db: Session | None = None) -> float:
    """
    Compute corpus-level quote verification precision for a project:
    verified_quotes / total_quotes across extracted PaperFact fields and ResearchGap evidence.
    Returns 0.0 if no quotes exist.
    """
    own_session = db is None
    if own_session:
        from app.database import SessionLocal
        db = SessionLocal()

    try:
        paper_ids = [
            r[0]
            for r in db.query(models.ProjectPaper.paper_id)
            .filter(models.ProjectPaper.project_id == project_id)
            .all()
        ]
        total_quotes = 0
        verified_quotes = 0

        if paper_ids:
            facts = db.query(models.PaperFact).filter(models.PaperFact.paper_id.in_(paper_ids)).all()
            for fact in facts:
                for field_name in FACT_QUOTE_FIELDS:
                    val = getattr(fact, field_name, None)
                    if isinstance(val, dict) and (val.get("quote") or "").strip():
                        total_quotes += 1
                        if val.get("verified") is True:
                            verified_quotes += 1

        gaps = db.query(models.ResearchGap).filter(models.ResearchGap.project_id == project_id).all()
        for gap in gaps:
            for ev in (gap.supporting_evidence or []) + (gap.counter_evidence or []):
                if isinstance(ev, dict) and (ev.get("quote") or "").strip():
                    total_quotes += 1
                    if ev.get("verified") is True:
                        verified_quotes += 1

        return round(verified_quotes / total_quotes, 4) if total_quotes > 0 else 0.0
    finally:
        if own_session:
            db.close()
