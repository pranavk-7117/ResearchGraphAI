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
import os
from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.clients import OpenAlexClient
from app.services.embeddings import EmbeddingService
from app.services.gap_matrix import build_method_task_matrix, cluster_limitation_signals
from app.services.llm import LLMService, post_validate_citation


EXTERNAL_ADDRESSED_THRESHOLD = int(os.getenv("GAP_EXTERNAL_ADDRESSED_THRESHOLD", "5"))
GAP_SCORE_FORMULA = (
    "min(1.0, max(0.1, (min(verified_supporting_count, 5)*0.1 + evidence_quality*0.4 + 0.2 "
    "+ matrix_void_bonus - verified_counter_count*0.1) * external_penalty)) "
    "if (verified_supporting_count > 0 or matrix_void_bonus > 0) else 0.1"
)


def compute_gap_score(
    verified_supporting_count: int,
    verified_counter_count: int,
    evidence_qual: float,
    matrix_void_bonus: float = 0.0,
    external_penalty: float = 1.0,
) -> float:
    """Single source-of-truth gap score formula excluding unverified quotes."""
    if verified_supporting_count <= 0 and matrix_void_bonus <= 0.0:
        return 0.1
    raw_score = (
        (min(verified_supporting_count, 5) * 0.1)
        + (evidence_qual * 0.4)
        + 0.2
        + matrix_void_bonus
        - (verified_counter_count * 0.1)
    ) * external_penalty
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
        self.embeddings = EmbeddingService()

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

        # Step 1: Bipartite Method x Task/Dataset matrix voids
        fact_rows = [
            (f.paper_id, paper_map[f.paper_id].title if f.paper_id in paper_map else f"Paper {f.paper_id}", f)
            for f in facts
        ]
        matrix_info = build_method_task_matrix(fact_rows, min_support=2)
        matrix_candidates = matrix_info.get("candidates", [])

        # Step 2: Cluster ALL limitation & future-work signals (no arbitrary [:15] cap)
        if not evidence_signals and not matrix_candidates:
            return []
        if not self.llm.is_available():
            return []

        signal_clusters = cluster_limitation_signals(
            evidence_signals, self.embeddings.embed_batch, sim_threshold=0.75
        ) if evidence_signals else []

        context_lines: list[str] = []
        if matrix_candidates:
            context_lines.append("## Under-Explored Method x Task/Dataset Matrix Cells")
            for cell in matrix_candidates[:5]:
                context_lines.append(
                    f"- [method='{cell['method']}', task='{cell['task']}', count={cell['count']}, "
                    f"row_support={cell['row_support']}, col_support={cell['col_support']}, "
                    f"expected={cell['expected']}, hypergeom_p={cell['hypergeom_p']}]"
                )

        if signal_clusters:
            context_lines.append("\n## Clustered Limitation & Future-Work Signals")
            for idx, cl in enumerate(signal_clusters[:5], start=1):
                context_lines.append(
                    f"Cluster {idx} ({cl['paper_count']} paper(s), {cl['verified_count']} verified quote(s)): {cl['representative']}"
                )
                for s in cl["signals"]:
                    context_lines.append(
                        f"  - [paper_id={s['paper_id']}, chunk_id={s['chunk_id']}, {s['title']} ({s['year'] or 'n.d.'}) - Page {s['page']}]: "
                        f"{s['type'].upper()}: {s['text']} (Quote: \"{s['quote']}\")"
                    )
        context_str = "\n".join(context_lines)

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

            # Step 3: Verify quotes strictly against stored chunks & DROP unverified quotes
            sup_ev = verify_evidence_list(g.supporting_evidence, chunks_by_paper_id, title_to_paper_id)
            cnt_ev = verify_evidence_list(g.counter_evidence, chunks_by_paper_id, title_to_paper_id)

            verified_sup = [e for e in sup_ev if e.get("verified") is True]
            verified_cnt = [e for e in cnt_ev if e.get("verified") is True]

            # Match against matrix void cell if gap references method & task
            matched_cell = None
            stmt_lower = g.gap_statement.lower()
            for cell in matrix_candidates:
                if cell["method"] in stmt_lower and cell["task"] in stmt_lower:
                    matched_cell = cell
                    break

            matrix_void_bonus = 0.0
            if matched_cell is not None:
                matrix_void_bonus = round(max(0.0, min(0.2, (1.0 - float(matched_cell.get("hypergeom_p", 1.0))) * 0.2)), 3)

            # Step 4: Targeted structured external check in OpenAlex
            external_info = self._external_openalex_check(g.gap_statement, matrix_cell=matched_cell)
            is_likely_addressed = bool(external_info.get("likely_addressed", False))
            external_penalty = 0.65 if is_likely_addressed else 1.0
            gap_status = "likely_addressed" if is_likely_addressed else "candidate"

            num_evidence = len(verified_sup)
            num_counter = len(verified_cnt)
            evidence_qual = 0.85 if num_evidence > 0 else 0.0
            final_score = compute_gap_score(
                num_evidence,
                num_counter,
                evidence_qual,
                matrix_void_bonus=matrix_void_bonus,
                external_penalty=external_penalty,
            )

            score_components = {
                "formula": GAP_SCORE_FORMULA,
                "formula_version": "1.2",
                "evidence_quality": evidence_qual,
                "supporting_papers_count": num_evidence,
                "total_supporting_quotes": len(sup_ev),
                "unverified_quotes_dropped": len(sup_ev) - num_evidence,
                "counter_evidence_count": num_counter,
                "matrix_void_bonus": matrix_void_bonus,
                "external_penalty": external_penalty,
                "calculated_strength": final_score,
            }

            gap_row = models.ResearchGap(
                project_id=project_id,
                corpus_version=project.corpus_version,
                statement_hash=stmt_hash,
                gap_statement=g.gap_statement,
                why_it_matters=g.why_it_matters,
                gap_type=g.gap_type,
                supporting_evidence=verified_sup,
                counter_evidence=verified_cnt,
                corpus_cannot_establish=g.corpus_cannot_establish,
                suggested_research_question=g.suggested_research_question,
                suggested_validation=g.suggested_validation,
                score_components=score_components,
                formula_version="1.2",
                evidence_strength=final_score,
                external_verification=external_info,
                matrix_cell=matched_cell,
                status=gap_status,
            )
            db.add(gap_row)
            created_gaps.append(gap_row)

        db.commit()
        return created_gaps

    def _external_openalex_check(
        self,
        gap_statement: str,
        matrix_cell: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform a structured OpenAlex query to check whether the gap is already well-studied externally."""
        if matrix_cell and matrix_cell.get("method") and matrix_cell.get("task"):
            search_terms = f'"{matrix_cell["method"]}" AND "{matrix_cell["task"]}"'
        else:
            words = [w for w in gap_statement.split() if len(w) > 4 and w.isalnum()]
            search_terms = " AND ".join(f'"{w}"' for w in words[:3]) if len(words) >= 2 else " ".join(words[:4])

        try:
            results = self.openalex.search(search_terms, limit=10)
            external_hits = [
                {"title": r.title, "year": r.year, "doi": r.doi, "citation_count": r.citation_count}
                for r in results[:5]
            ]
            total_found = len(results)
            likely_addressed = total_found > EXTERNAL_ADDRESSED_THRESHOLD
            return {
                "searched_terms": search_terms,
                "external_papers_found": total_found,
                "likely_addressed": likely_addressed,
                "threshold": EXTERNAL_ADDRESSED_THRESHOLD,
                "top_external_matches": external_hits,
                "disclaimer": (
                    f"Structured OpenAlex check found {total_found} hit(s); gap marked likely_addressed and score penalized."
                    if likely_addressed
                    else "Underrepresentation in this corpus is a candidate hypothesis. The external literature may contain related work as indicated above."
                ),
            }
        except Exception:
            return {
                "searched_terms": search_terms,
                "external_papers_found": 0,
                "likely_addressed": False,
                "threshold": EXTERNAL_ADDRESSED_THRESHOLD,
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
