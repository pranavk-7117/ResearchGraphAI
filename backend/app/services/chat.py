"""
Grounding and Hybrid RAG Chat Service for ResearchGraphAI.

Three-stage retrieval pipeline:
1. Dense retrieval via pgvector cosine distance (<=>) over paper_chunks (top 30)
2. Full-text retrieval via PostgreSQL tsvector + GIN index using websearch_to_tsquery & ts_rank_cd (top 30)
3. Configurable fusion (RRF k=60 or min-max normalized convex combination with weight alpha)
4. Optional cross-encoder reranking (RERANKER=none|cross_encoder)

Strict no-evidence guard: if no chunk passes or best fused score < threshold, returns an honest
insufficient-evidence response instead of padding with unretrieved abstracts.
"""

import os
import re
import uuid
from typing import Any
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app import models
from app.services.embeddings import EmbeddingService
from app.services.llm import LLMService

_CROSS_ENCODER = None


def get_cross_encoder():
    """Lazy-load sentence-transformers CrossEncoder when RERANKER=cross_encoder."""
    global _CROSS_ENCODER
    if _CROSS_ENCODER is None:
        from sentence_transformers import CrossEncoder
        _CROSS_ENCODER = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _CROSS_ENCODER


def normalize_authors(authors: Any) -> list[dict[str, Any]]:
    """Ensure authors list is always a list of dicts with 'name' key for Pydantic compatibility."""
    if not authors:
        return []
    if isinstance(authors, list):
        out = []
        for a in authors:
            if isinstance(a, dict):
                out.append(a)
            elif isinstance(a, str) and a.strip():
                out.append({"name": a.strip()})
        return out
    if isinstance(authors, str) and authors.strip():
        return [{"name": authors.strip()}]
    return []


def min_max_normalize(scores: list[float]) -> list[float]:
    """Min-max normalize a list of non-negative scores into [0.0, 1.0]."""
    if not scores:
        return []
    mn = min(scores)
    mx = max(scores)
    if mx <= mn:
        return [1.0 if mx > 0.0 else 0.0 for _ in scores]
    return [(s - mn) / (mx - mn) for s in scores]


def fuse_retrieval_hits(
    dense_hits: list[dict[str, Any]],
    fts_hits: list[dict[str, Any]],
    fusion_method: str = "rrf",
    alpha: float = 0.5,
    rrf_k: int = 60,
) -> list[dict[str, Any]]:
    """
    Fuse dense and full-text hit lists using either:
    - 'rrf': Reciprocal Rank Fusion 1 / (rrf_k + rank + 1)
    - 'convex': alpha * norm_dense + (1 - alpha) * norm_fts
    """
    method = (fusion_method or "rrf").lower().strip()
    chunk_map: dict[int, dict[str, Any]] = {}
    fused_scores: dict[int, float] = {}

    if method == "convex":
        dense_raw = [float(h.get("dense_score", h.get("score", 0.0))) for h in dense_hits]
        fts_raw = [float(h.get("fts_score", h.get("score", 0.0))) for h in fts_hits]
        dense_norm = min_max_normalize(dense_raw)
        fts_norm = min_max_normalize(fts_raw)

        dense_by_id: dict[int, float] = {}
        for hit, norm_val in zip(dense_hits, dense_norm):
            cid = hit["chunk_id"]
            dense_by_id[cid] = max(dense_by_id.get(cid, 0.0), norm_val)
            chunk_map[cid] = dict(hit)

        fts_by_id: dict[int, float] = {}
        for hit, norm_val in zip(fts_hits, fts_norm):
            cid = hit["chunk_id"]
            fts_by_id[cid] = max(fts_by_id.get(cid, 0.0), norm_val)
            if cid not in chunk_map:
                chunk_map[cid] = dict(hit)

        for cid in chunk_map:
            d_val = dense_by_id.get(cid, 0.0)
            f_val = fts_by_id.get(cid, 0.0)
            score = alpha * d_val + (1.0 - alpha) * f_val
            fused_scores[cid] = score
            chunk_map[cid]["fused_score"] = round(score, 6)
            chunk_map[cid]["score"] = round(score, 6)
    else:
        for rank, hit in enumerate(dense_hits):
            cid = hit["chunk_id"]
            contrib = 1.0 / (rrf_k + rank + 1)
            fused_scores[cid] = fused_scores.get(cid, 0.0) + contrib
            if cid not in chunk_map:
                chunk_map[cid] = dict(hit)

        for rank, hit in enumerate(fts_hits):
            cid = hit["chunk_id"]
            contrib = 1.0 / (rrf_k + rank + 1)
            fused_scores[cid] = fused_scores.get(cid, 0.0) + contrib
            if cid not in chunk_map:
                chunk_map[cid] = dict(hit)

        for cid, score in fused_scores.items():
            chunk_map[cid]["fused_score"] = round(score, 6)
            chunk_map[cid]["score"] = round(score, 6)

    sorted_cids = sorted(fused_scores.keys(), key=lambda cid: fused_scores[cid], reverse=True)
    return [chunk_map[cid] for cid in sorted_cids]


class ChatService:
    def __init__(
        self,
        fusion_method: str | None = None,
        alpha: float | None = None,
        reranker: str | None = None,
        min_dense_similarity: float | None = None,
        min_fused_score: float | None = None,
    ):
        self.embeddings = EmbeddingService()
        self.llm = LLMService()
        self.fusion_method = (fusion_method or os.getenv("RETRIEVAL_FUSION", "convex")).lower().strip()
        self.alpha = float(alpha if alpha is not None else os.getenv("RETRIEVAL_ALPHA", "0.5"))
        self.reranker = (reranker or os.getenv("RERANKER", "none")).lower().strip()
        self.min_dense_similarity = float(
            min_dense_similarity
            if min_dense_similarity is not None
            else os.getenv("RETRIEVAL_MIN_DENSE_SIM", "0.22")
        )
        default_min_score = "0.05" if self.fusion_method == "convex" else "0.005"
        self.min_fused_score = float(
            min_fused_score
            if min_fused_score is not None
            else os.getenv("RETRIEVAL_MIN_SCORE", default_min_score)
        )

    def query_rag(
        self,
        db: Session,
        project_id: int,
        question: str,
        session_id: str | None = None,
        paper_id_filter: int | None = None,
    ) -> dict[str, Any]:
        """Execute hybrid search, synthesize answer, and persist chat message."""
        project = db.query(models.ResearchProject).filter(models.ResearchProject.id == project_id).first()
        if not project:
            raise RuntimeError(f"Project {project_id} not found")

        if not session_id:
            session_id = str(uuid.uuid4())
            new_session = models.ChatSession(
                id=session_id,
                project_id=project_id,
                title=question[:60],
            )
            db.add(new_session)
            db.commit()

        user_msg = models.ChatMessage(
            session_id=session_id,
            role="user",
            content=question,
            citations=[],
        )
        db.add(user_msg)
        db.commit()

        retrieved_passages = self._hybrid_retrieve(
            db, project_id, question, paper_id_filter=paper_id_filter
        )

        if not retrieved_passages:
            answer = (
                f"Based on the indexed literature in the project '{project.topic}', "
                "no direct evidence or matching passages passed the retrieval relevance threshold "
                "to address your question."
            )
            assistant_msg = models.ChatMessage(
                session_id=session_id,
                role="assistant",
                content=answer,
                citations=[],
            )
            db.add(assistant_msg)
            db.commit()
            return {
                "session_id": session_id,
                "answer": answer,
                "evidence": "",
                "interpretation": "",
                "suggestions": ["Try querying with terms present in your indexed corpus"],
                "citations": [],
                "retrieved_count": 0,
            }

        context_blocks = []
        for idx, p in enumerate(retrieved_passages, start=1):
            context_blocks.append(
                f"[{idx}] Paper: '{p['title']}' (Year: {p['year'] or 'n.d.'}, Page: {p['page']}, Section: {p['section']}):\n"
                f"\"{p['text']}\""
            )
        context_str = "\n\n".join(context_blocks)

        prompt = (
            f"Project Research Topic: {project.topic}\n"
            f"User Question: {question}\n\n"
            "Note: Unless the user explicitly names a specific individual paper from the excerpts above, treat references to "
            f"'{project.topic}' as referring to the overall multi-paper project corpus above.\n"
            "Respond to the question strictly and solely based on the retrieved academic excerpts above. "
            "Format your response with three distinct markdown sections:\n"
            "### Evidence\n(Direct findings and exact factual quotes from the retrieved papers, attributed with citation numbers like [1])\n\n"
            "### Interpretation\n(Synthesis of what the evidence demonstrates regarding the question)\n\n"
            "### Suggestions\n(Follow-up research questions or methodologies to explore next)\n\n"
            "If the excerpts do not contain sufficient evidence to answer, state clearly in the Evidence section "
            "that the retrieved corpus is insufficient, rather than making up answers."
        )

        system_prompt = (
            "You are a rigorous scientific research assistant. "
            "Every single claim in the Evidence section MUST be attributed with ASCII square brackets like [1]. "
            "Never invent facts, metrics, or citations."
        )

        try:
            raw_answer = self.llm.complete(prompt, system_prompt=system_prompt, context=context_str)
        except Exception:
            evidence_lines = [
                f"[{idx}] **{p['title']}** ({p['year'] or 'n.d.'}): \"{p['text'][:240].strip()}...\""
                for idx, p in enumerate(retrieved_passages[:4], start=1)
            ]
            raw_answer = (
                "### Evidence\n"
                + "\n\n".join(evidence_lines)
                + "\n\n### Interpretation\n"
                + f"Retrieved passages for **{project.topic}** are listed above (LLM synthesis unavailable).\n\n"
                + "### Suggestions\n"
                + "- Review the cited passages directly."
            )

        raw_answer = re.sub(r"【(\d+(?:\s*,\s*\d+)*)】", r"[\1]", raw_answer)
        used_citations: list[dict[str, Any]] = []
        for idx, p in enumerate(retrieved_passages, start=1):
            if f"[{idx}]" in raw_answer or re.search(rf"\[[^\]]*\b{idx}\b[^\]]*\]", raw_answer):
                used_citations.append({
                    "ref": f"[{idx}]",
                    "paper_id": p["paper_id"],
                    "title": p["title"],
                    "authors": normalize_authors(p["authors"]),
                    "doi": p["doi"],
                    "page": p["page"],
                    "section": p["section"],
                    "quote": p["text"][:250],
                })

        assistant_msg = models.ChatMessage(
            session_id=session_id,
            role="assistant",
            content=raw_answer,
            citations=used_citations,
        )
        db.add(assistant_msg)
        db.commit()

        return {
            "session_id": session_id,
            "answer": raw_answer,
            "citations": used_citations,
            "retrieved_count": len(retrieved_passages),
        }

    def _dense_search(
        self,
        db: Session,
        paper_ids: list[int],
        query: str,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Dense pgvector cosine retrieval (<=>) scoped strictly to paper_ids."""
        if not paper_ids or not query.strip():
            return []
        query_vector = self.embeddings.embed(query)
        vector_str = f"[{','.join(str(v) for v in query_vector)}]"

        dense_sql = text("""
            SELECT
                c.id AS chunk_id,
                c.paper_id,
                c.page_start AS page,
                c.section,
                c.text,
                p.title,
                p.authors,
                p.doi,
                p.year,
                1 - (c.embedding <=> CAST(:query_vec AS vector)) AS similarity
            FROM paper_chunks c
            JOIN papers p ON p.id = c.paper_id
            WHERE c.paper_id IN :paper_ids
            ORDER BY c.embedding <=> CAST(:query_vec AS vector) ASC
            LIMIT :limit;
        """).bindparams(bindparam("paper_ids", expanding=True))

        rows = db.execute(
            dense_sql,
            {"query_vec": vector_str, "paper_ids": paper_ids, "limit": limit},
        ).fetchall()

        hits: list[dict[str, Any]] = []
        for r in rows:
            sim = float(r.similarity)
            if sim < self.min_dense_similarity:
                continue
            hits.append({
                "chunk_id": r.chunk_id,
                "paper_id": r.paper_id,
                "page": r.page or 1,
                "section": r.section or "Body",
                "text": r.text,
                "title": r.title,
                "authors": r.authors,
                "doi": r.doi,
                "year": r.year,
                "dense_score": sim,
                "score": sim,
            })
        return hits

    def _fts_search(
        self,
        db: Session,
        paper_ids: list[int],
        query: str,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Full-text search using generated tsvector column + GIN index."""
        if not paper_ids or not query.strip():
            return []

        fts_sql = text("""
            SELECT
                c.id AS chunk_id,
                c.paper_id,
                c.page_start AS page,
                c.section,
                c.text,
                p.title,
                p.authors,
                p.doi,
                p.year,
                ts_rank_cd(c.text_tsv, websearch_to_tsquery('english', :query)) AS fts_rank
            FROM paper_chunks c
            JOIN papers p ON p.id = c.paper_id
            WHERE c.paper_id IN :paper_ids
              AND c.text_tsv @@ websearch_to_tsquery('english', :query)
            ORDER BY fts_rank DESC
            LIMIT :limit;
        """).bindparams(bindparam("paper_ids", expanding=True))

        rows = db.execute(
            fts_sql,
            {"query": query, "paper_ids": paper_ids, "limit": limit},
        ).fetchall()

        hits: list[dict[str, Any]] = []
        for r in rows:
            rank_val = float(r.fts_rank)
            hits.append({
                "chunk_id": r.chunk_id,
                "paper_id": r.paper_id,
                "page": r.page or 1,
                "section": r.section or "Body",
                "text": r.text,
                "title": r.title,
                "authors": r.authors,
                "doi": r.doi,
                "year": r.year,
                "fts_score": rank_val,
                "score": rank_val,
            })
        return hits

    def _rerank(self, query: str, passages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Optional cross-encoder reranking behind RERANKER=cross_encoder."""
        if self.reranker != "cross_encoder" or not passages:
            return passages
        model = get_cross_encoder()
        pairs = [(query, p["text"][:1000]) for p in passages]
        scores = model.predict(pairs)
        reranked = []
        for p, s in zip(passages, scores):
            item = dict(p)
            item["rerank_score"] = float(s)
            reranked.append(item)
        reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
        return reranked

    def _hybrid_retrieve(
        self,
        db: Session,
        project_id: int,
        query: str,
        paper_id_filter: int | None = None,
        top_k: int = 6,
    ) -> list[dict[str, Any]]:
        """
        Execute 3-stage hybrid retrieval (dense top 30, FTS top 30, fusion) + optional reranker.
        Returns [] if no chunk passes or best fused score < min_fused_score.
        """
        q_papers = (
            db.query(models.ProjectPaper.paper_id)
            .filter(models.ProjectPaper.project_id == project_id)
        )
        if paper_id_filter:
            q_papers = q_papers.filter(models.ProjectPaper.paper_id == paper_id_filter)
        paper_ids = [r[0] for r in q_papers.all()]

        if not paper_ids:
            return []

        dense_hits: list[dict[str, Any]] = []
        fts_hits: list[dict[str, Any]] = []

        try:
            dense_hits = self._dense_search(db, paper_ids, query, limit=30)
        except Exception:
            db.rollback()
            dense_hits = []

        try:
            fts_hits = self._fts_search(db, paper_ids, query, limit=30)
        except Exception:
            db.rollback()
            fts_hits = []

        if not dense_hits and not fts_hits:
            return []

        fused = fuse_retrieval_hits(
            dense_hits,
            fts_hits,
            fusion_method=self.fusion_method,
            alpha=self.alpha,
        )
        if not fused:
            return []

        best_score = fused[0].get("fused_score", 0.0)
        if best_score < self.min_fused_score:
            return []

        if self.reranker == "cross_encoder":
            fused = self._rerank(query, fused[:15])

        return fused[:top_k]
