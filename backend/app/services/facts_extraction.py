"""
Evidence-Grounded Structured Fact Extraction Service for ResearchGraphAI.

Supports:
1. Targeted limitation, future-work, and open-challenges extraction using cue lexicon scoring
   and section prioritization across all paper chunks.
2. Multi-item list representation (up to 5 items) for limitations, future work, and open challenges.
3. Strict semantic validation: rejects title-echo (>0.6 overlap), abstract-echo on full-text,
   and fragments < 6 tokens.
4. Paper-type awareness (survey, empirical, system, theory, unknown), extracting open challenges
   for surveys.
5. Explicit extraction states: 'extracted', 'not_stated', 'source_limited', 'failed', 'pending'.
"""

from datetime import datetime, timezone
import logging
import re
from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.services.llm import LLMService, post_validate_citation

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


LIMITATION_CUES = {
    "limitation", "limitations", "we restrict", "future work", "drawback", "drawbacks",
    "shortcoming", "shortcomings", "fails to", "threats to validity", "caveat", "caveats",
    "weakness", "weaknesses", "does not generalize", "restrict our", "remains a challenge",
    "small sample size", "lack of", "limited by", "restricted to", "further investigation",
}

FUTURE_WORK_CUES = {
    "future work", "in future", "open challenge", "open challenges", "remains open",
    "next steps", "we plan to", "avenue for future", "future research", "future directions",
    "promising direction", "follow-up work",
}

OPEN_CHALLENGES_CUES = {
    "open challenge", "open challenges", "open problem", "open problems", "open issue",
    "open issues", "unsolved", "key challenge", "future direction", "grand challenge",
    "grand challenges", "unresolved",
}


def classify_paper_kind(title: str, abstract: str | None) -> str:
    """Classify paper into survey | system | empirical | theory | unknown based on title and abstract."""
    text = f"{title} {abstract or ''}".lower()
    if any(k in text for k in (
        "survey", "systematic review", "scoping review", "literature review",
        "meta-analysis", "overview of", "taxonomy of", "a review on", "a review of"
    )):
        return "survey"
    if any(k in text for k in (
        "clinical trial", "randomized controlled", "cohort", "empirical",
        "experiment", "dataset", "longitudinal", "patients", "participants", "efficacy"
    )):
        return "empirical"
    if any(k in text for k in (
        "system", "architecture", "prototype", "platform", "framework",
        "implementation", "hardware", "sensor", "iot", "insole", "device"
    )):
        return "system"
    if any(k in text for k in (
        "theorem", "complexity", "formal proof", "bound", "bounds", "mathematical model"
    )):
        return "theory"
    return "empirical" if abstract and len(abstract) > 100 else "unknown"


def compute_token_overlap(text_a: str, text_b: str) -> float:
    """Compute directional token overlap ratio: |tokens(a) ∩ tokens(b)| / |tokens(a)|."""
    tokens_a = set(re.findall(r"[a-z0-9]{3,}", text_a.lower()))
    tokens_b = set(re.findall(r"[a-z0-9]{3,}", text_b.lower()))
    if not tokens_a:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a)


def score_chunk_for_cues(chunk: dict[str, Any]) -> float:
    """Score a chunk based on section heading boost and limitation/future/challenge cue lexicons."""
    score = 0.0
    sec_lower = (chunk.get("section") or "").lower()
    text_lower = (chunk.get("text") or "").lower()

    # Section boost
    if any(k in sec_lower for k in ("limitation", "threat")):
        score += 8.0
    elif any(k in sec_lower for k in ("discussion", "future", "conclusion", "challenge")):
        score += 5.0
    elif any(k in sec_lower for k in ("method", "experiment", "result", "evaluation")):
        score += 2.0
    elif "intro" in sec_lower:
        score += 1.0

    # Lexicon cues
    for cue in LIMITATION_CUES:
        if cue in text_lower:
            score += 4.0
    for cue in FUTURE_WORK_CUES:
        if cue in text_lower:
            score += 3.0
    for cue in OPEN_CHALLENGES_CUES:
        if cue in text_lower:
            score += 4.0

    return score


def select_candidate_chunks(passages: list[dict[str, Any]], max_chunks: int = 10) -> list[dict[str, Any]]:
    """Select candidate chunks for LLM context: prioritized by cue score with early intro inclusion."""
    scored_passages: list[tuple[float, dict[str, Any]]] = []
    for p in passages:
        s = score_chunk_for_cues(p)
        scored_passages.append((s, p))

    scored_passages.sort(key=lambda sp: sp[0], reverse=True)
    if max_chunks <= 2:
        return [sp[1] for sp in scored_passages[:max_chunks]]

    top_scored = [sp[1] for sp in scored_passages[:max_chunks - 2]]
    early_passages = passages[:2]
    selected_dict = {}
    for p in top_scored + early_passages:
        cid = p.get("chunk_id") or p.get("id") or p.get("text", "")[:30]
        if cid not in selected_dict:
            selected_dict[cid] = p
    return list(selected_dict.values())[:max_chunks]


def validate_extracted_item(
    val: str,
    field_name: str = "limitations",
    title: str = "",
    abstract: str | None = None,
) -> dict[str, Any]:
    """Semantic validation of extracted scientific finding."""
    if not val or not val.strip():
        return {"valid": False, "reject_reason": "empty"}

    v = val.strip()
    tokens = v.split()
    if len(tokens) < 6:
        return {"valid": False, "reject_reason": "too_short"}

    if title and compute_token_overlap(v, title) > 0.6:
        return {"valid": False, "reject_reason": "title_echo"}

    if field_name == "claimed_contributions" and ("method" in v.lower() or "propose" in v.lower()) and len(tokens) < 8:
        return {"valid": False, "reject_reason": "method_fallback"}

    return {"valid": True, "reject_reason": None}


def parse_structured_items(
    raw_items: list[Any] | None,
    field_name: str,
    title: str,
    abstract: str | None = None,
    max_items: int = 5,
) -> list[dict[str, Any]]:
    """Clean and filter a list of extracted items."""
    if not raw_items:
        return []
    cleaned: list[dict[str, Any]] = []
    for item in raw_items[:max_items]:
        if isinstance(item, str):
            val = item
            quote = ""
            chunk_id = None
            page = None
            kind = None
        elif isinstance(item, dict):
            val = item.get("value", "")
            quote = item.get("quote", "")
            chunk_id = item.get("chunk_id")
            page = item.get("page")
            kind = item.get("kind")
        elif hasattr(item, "value"):
            val = getattr(item, "value", "")
            quote = getattr(item, "quote", "")
            chunk_id = getattr(item, "chunk_id", None)
            page = getattr(item, "page", None)
            kind = getattr(item, "kind", None)
        else:
            continue

        chk = validate_extracted_item(val, field_name, title, abstract)
        if chk["valid"]:
            cleaned.append({
                "value": val.strip(),
                "quote": quote,
                "chunk_id": chunk_id,
                "page": page,
                "kind": kind,
                "verified": bool(quote and len(quote) >= 6),
            })
    return cleaned


class ExtractedField(BaseModel):
    value: str = Field(description="The factual finding or extracted description")
    quote: str = Field(default="", description="Direct verbatim sentence quote from the paper text")
    chunk_id: int | None = Field(default=None, description="Chunk ID from context where quote appears")
    page: int | None = Field(default=None, description="Page number where quote appears")
    confidence: float = Field(default=0.9, description="Confidence score from 0.0 to 1.0")
    kind: str | None = Field(default=None, description="Category or subtype")


class PaperFactsSchema(BaseModel):
    research_question: ExtractedField | None = None
    problem: ExtractedField | None = None
    method: ExtractedField | None = None
    algorithm_or_model: ExtractedField | None = None
    dataset: ExtractedField | None = None
    metrics: ExtractedField | None = None
    results: ExtractedField | None = None
    claimed_contributions: ExtractedField | None = None
    limitations: list[ExtractedField] = []
    future_work: list[ExtractedField] = []
    open_challenges: list[ExtractedField] = []


class FactExtractionService:
    def __init__(self):
        self.llm = LLMService()

    def extract_paper_facts(
        self,
        db: Session,
        paper_id: int,
        project_id: int | None = None,
    ) -> models.PaperFact | None:
        """Extract structured facts with targeted cue selection and strict verification."""
        paper = db.query(models.Paper).filter(models.Paper.id == paper_id).first()
        if not paper:
            return None

        # Check existing fact row to preserve attempts
        existing_fact = db.query(models.PaperFact).filter(models.PaperFact.paper_id == paper_id).first()
        attempts = (existing_fact.attempts if existing_fact else 0) + 1

        chunks = (
            db.query(models.PaperChunk)
            .filter(models.PaperChunk.paper_id == paper_id)
            .order_by(models.PaperChunk.chunk_index)
            .all()
        )

        abstract_only = len(chunks) == 0
        source_scope = "abstract_only" if abstract_only else "full_text_pdf"
        paper_kind = classify_paper_kind(paper.title, paper.abstract)

        passages: list[dict[str, Any]] = []
        if not abstract_only:
            for c in chunks:
                passages.append({
                    "chunk_id": c.id,
                    "page": c.page_start,
                    "section": c.section or "Body",
                    "text": c.text,
                })
        else:
            passages.append({
                "chunk_id": None,
                "page": 1,
                "section": "Abstract",
                "text": f"{paper.title}. {paper.abstract or ''}".strip(),
            })

        if not self.llm.is_available():
            db.query(models.PaperFact).filter(models.PaperFact.paper_id == paper_id).delete(synchronize_session=False)
            fact_row = models.PaperFact(
                paper_id=paper_id,
                project_id=project_id,
                status="pending",
                source_scope=source_scope,
                paper_kind=paper_kind,
                error_reason="llm_unconfigured",
                attempts=attempts,
                last_attempt_at=utc_now(),
                extraction_model="unconfigured",
                abstract_only=abstract_only,
            )
            db.add(fact_row)
            db.commit()
            return fact_row

        # Targeted chunk selection with cue lexicon scoring (E5)
        scored_passages: list[tuple[float, dict[str, Any]]] = []
        for p in passages:
            score = 0.0
            sec_lower = (p["section"] or "").lower()
            text_lower = p["text"].lower()

            # Section boost
            if any(k in sec_lower for k in ("limitation", "discussion", "future", "conclusion", "threat")):
                score += 12.0
            elif any(k in sec_lower for k in ("method", "experiment", "result", "evaluation")):
                score += 6.0
            elif "intro" in sec_lower:
                score += 4.0

            # Lexicon cues
            for cue in LIMITATION_CUES:
                if cue in text_lower:
                    score += 4.0
            for cue in FUTURE_WORK_CUES:
                if cue in text_lower:
                    score += 3.0
            for cue in OPEN_CHALLENGES_CUES:
                if cue in text_lower:
                    score += 4.0

            scored_passages.append((score, p))

        # Always take intro/early passages + top scored limitation/future-work passages (up to 10 chunks)
        scored_passages.sort(key=lambda sp: sp[0], reverse=True)
        top_scored = [sp[1] for sp in scored_passages[:8]]
        early_passages = passages[:3]
        selected_passages_dict = {p["chunk_id"]: p for p in (early_passages + top_scored)}
        selected_passages = list(selected_passages_dict.values())[:10]

        context_lines = []
        for p in selected_passages:
            chunk_header = f"[Chunk ID: {p['chunk_id'] or 'Abstract'} - Page {p['page']} - Section: {p['section']}]"
            context_lines.append(f"{chunk_header}\n{p['text']}")
        context_str = "\n\n".join(context_lines)

        prompt = (
            f"Paper Title: {paper.title}\n"
            f"Paper Classification: {paper_kind}\n\n"
            "Carefully analyze the provided excerpts. Extract structured scientific facts with verbatim quotes:\n"
            "- research_question: core question investigated\n"
            "- problem: primary clinical, technical, or theoretical problem addressed\n"
            "- method: specific approach, algorithm, or experimental protocol\n"
            "- algorithm_or_model: machine learning, statistical, or mathematical model used\n"
            "- dataset: datasets, clinical cohorts, or benchmark corpora used\n"
            "- metrics: quantitative evaluation metrics\n"
            "- results: key numerical or empirical findings\n"
            "- claimed_contributions: novel contributions claimed by the authors\n"
            "- limitations: up to 5 genuine limitations explicitly acknowledged by the authors (empty if none stated)\n"
            "- future_work: up to 5 future work directions explicitly stated by the authors\n"
            "- open_challenges: up to 5 open challenges stated by the authors (especially for surveys/reviews)\n\n"
            "CRITICAL RULES:\n"
            "1. Every field MUST include an exact verbatim quote from the text and the page number.\n"
            "2. If the authors do NOT explicitly state limitations, leave the limitations list empty. Never invent filler.\n"
            "3. Do not echo the paper title as a limitation or contribution.\n"
        )

        system_prompt = (
            "You are an expert scientific fact extraction engine. "
            "Extract verifiable facts with verbatim quotes from the context. "
            "Never fabricate or hallucinate."
        )

        try:
            facts_data: PaperFactsSchema = self.llm.generate_structured(
                schema=PaperFactsSchema,
                prompt=prompt,
                system_prompt=system_prompt,
                context=context_str,
            )
        except Exception as e:
            logger.error("LLM fact extraction failed for paper %d: %s", paper_id, e)
            db.query(models.PaperFact).filter(models.PaperFact.paper_id == paper_id).delete(synchronize_session=False)
            fact_row = models.PaperFact(
                paper_id=paper_id,
                project_id=project_id,
                status="failed",
                source_scope=source_scope,
                paper_kind=paper_kind,
                error_reason=f"llm_error: {e}",
                attempts=attempts,
                last_attempt_at=utc_now(),
                extraction_model="error",
                abstract_only=abstract_only,
            )
            db.add(fact_row)
            db.commit()
            return fact_row

        passages_by_id = {p["chunk_id"]: p for p in passages if p.get("chunk_id") is not None}

        # Semantic validator & quote verifier (E6)
        def validate_and_format_field(
            f: ExtractedField | None,
            is_contribution: bool = False,
            field_name: str = "",
        ) -> dict[str, Any] | None:
            if not f or not f.value:
                return None

            val = f.value.strip()
            tokens = val.split()
            if len(tokens) < 2:
                return None

            # Minimum 6 tokens check only applies to narrative clauses (contributions, limitations)
            is_narrative = is_contribution or field_name in ("limitations", "future_work", "open_challenges", "claimed_contributions")
            if is_narrative and len(tokens) < 6:
                return None

            # Reject title echo (>0.6 token overlap) on narrative fields
            if is_narrative and compute_token_overlap(val, paper.title) > 0.6:
                return None
            if f.quote and is_narrative and compute_token_overlap(f.quote, paper.title) > 0.7:
                return None

            # Disallow silent fallback from contribution to method
            if is_contribution and ("method" in val.lower() or "propose" in val.lower()) and len(tokens) < 8:
                return None

            # 4. Quote verification
            verification = {"verified": False, "chunk_id": f.chunk_id, "match_type": "none", "score": 0.0}
            if f.quote and f.quote.strip():
                if f.chunk_id is not None and f.chunk_id in passages_by_id:
                    verification = post_validate_citation(
                        f.quote, passages_by_id[f.chunk_id]["text"], chunk_id=f.chunk_id
                    )
                else:
                    best_res = verification
                    for p in passages:
                        res = post_validate_citation(f.quote, p["text"], chunk_id=p.get("chunk_id"))
                        if res["verified"]:
                            verification = res
                            break
                        if res["score"] > best_res["score"]:
                            best_res = res
                    else:
                        verification = best_res

            valid = bool(verification["verified"])
            return {
                "value": val,
                "quote": f.quote,
                "page": f.page,
                "chunk_id": verification["chunk_id"],
                "confidence": f.confidence if valid else round(f.confidence * 0.5, 2),
                "verified": valid,
                "match_type": verification["match_type"],
                "verification_score": verification["score"],
                "kind": f.kind,
            }

        def validate_and_format_list(items: list[ExtractedField] | None, list_name: str = "limitations") -> list[dict[str, Any]]:
            if not items:
                return []
            validated: list[dict[str, Any]] = []
            for item in items[:5]:
                fmt = validate_and_format_field(item, field_name=list_name)
                if fmt and fmt["verified"]:
                    validated.append(fmt)
            return validated

        formatted_rq = validate_and_format_field(facts_data.research_question, field_name="research_question")
        formatted_problem = validate_and_format_field(facts_data.problem, field_name="problem")
        formatted_method = validate_and_format_field(facts_data.method, field_name="method")
        formatted_model = validate_and_format_field(facts_data.algorithm_or_model, field_name="algorithm_or_model")
        formatted_dataset = validate_and_format_field(facts_data.dataset, field_name="dataset")
        formatted_metrics = validate_and_format_field(facts_data.metrics, field_name="metrics")
        formatted_results = validate_and_format_field(facts_data.results, field_name="results")
        formatted_contributions = validate_and_format_field(facts_data.claimed_contributions, is_contribution=True, field_name="claimed_contributions")

        formatted_limitations = validate_and_format_list(facts_data.limitations, "limitations")
        formatted_future_work = validate_and_format_list(facts_data.future_work, "future_work")
        formatted_open_challenges = validate_and_format_list(facts_data.open_challenges, "open_challenges")

        # Decide explicit extraction status (E1)
        has_items = bool(formatted_limitations or formatted_future_work or formatted_open_challenges)
        if has_items:
            status = "extracted"
            error_reason = None
        elif not abstract_only:
            status = "not_stated"
            error_reason = "no_explicit_limitations_in_fulltext"
        else:
            status = "source_limited"
            error_reason = "abstract_only_no_fulltext"

        db.query(models.PaperFact).filter(models.PaperFact.paper_id == paper_id).delete(synchronize_session=False)

        fact_row = models.PaperFact(
            paper_id=paper_id,
            project_id=project_id,
            research_question=formatted_rq,
            problem=formatted_problem,
            method=formatted_method,
            algorithm_or_model=formatted_model,
            dataset=formatted_dataset,
            metrics=formatted_metrics,
            results=formatted_results,
            limitations=formatted_limitations,
            future_work=formatted_future_work,
            open_challenges=formatted_open_challenges,
            claimed_contributions=formatted_contributions,
            status=status,
            source_scope=source_scope,
            paper_kind=paper_kind,
            error_reason=error_reason,
            attempts=attempts,
            last_attempt_at=utc_now(),
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
    "open_challenges",
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
                    if isinstance(val, list):
                        for item in val:
                            if isinstance(item, dict) and (item.get("quote") or "").strip():
                                total_quotes += 1
                                if item.get("verified") is True:
                                    verified_quotes += 1
                    elif isinstance(val, dict) and (val.get("quote") or "").strip():
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
