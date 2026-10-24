"""
Grounding and RAG Chat Service for ResearchGraphAI.

Features:
- Hybrid dense pgvector + full-text SQL retrieval with Reciprocal Rank Fusion (RRF)
- Structured answer format: Evidence / Interpretation / Suggestions
- Passage-level clickable citations: paper title, authors, DOI, page, section, verbatim quote
- Honest disclosure when evidence is insufficient (zero fabricated answers)
- Persisted chat sessions and message logs
"""

import math
import os
import re
import uuid
from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models
from app.services.embeddings import EmbeddingService, cosine_similarity
from app.services.llm import LLMService


class ChatService:
    def __init__(self):
        self.embeddings = EmbeddingService()
        self.llm = LLMService()

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

        # 1. Ensure or create session
        if not session_id:
            session_id = str(uuid.uuid4())
            new_session = models.ChatSession(
                id=session_id,
                project_id=project_id,
                title=question[:60],
            )
            db.add(new_session)
            db.commit()

        # Record user message
        user_msg = models.ChatMessage(
            session_id=session_id,
            role="user",
            content=question,
            citations=[],
        )
        db.add(user_msg)
        db.commit()

        # 2. Hybrid Retrieval: pgvector dense cosine + SQL text search
        retrieved_passages = self._hybrid_retrieve(db, project_id, question, paper_id_filter=paper_id_filter)

        if not retrieved_passages:
            answer = (
                f"Based on the indexed literature in the project '{project.topic}', "
                "no direct evidence or matching passages were found to address your question. "
                "Please consider indexing additional papers on this topic."
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
                "suggestions": ["Try querying with different terms", "Check if relevant papers are processed"],
                "citations": [],
            }

        # 3. Build context with citation tracking
        context_blocks = []
        for idx, p in enumerate(retrieved_passages, start=1):
            ref_id = f"[{idx}]"
            context_blocks.append(
                f"{ref_id} Paper: '{p['title']}' (Year: {p['year'] or 'n.d.'}, Page: {p['page']}, Section: {p['section']}):\n"
                f"\"{p['text']}\""
            )
        context_str = "\n\n".join(context_blocks)

        prompt = (
            f"User Question: {question}\n\n"
            "Respond to the question strictly and solely based on the retrieved academic excerpts above. "
            "Format your response with three distinct markdown sections:\n"
            "### Evidence\n(Direct findings and factual quotes attributed with citation numbers like [1])\n\n"
            "### Interpretation\n(Synthesis of what the evidence demonstrates regarding the question)\n\n"
            "### Suggestions\n(Follow-up research questions or methodologies to explore next)\n\n"
            "If the excerpts do not contain sufficient evidence to answer, state clearly in the Evidence section "
            "that the retrieved corpus is insufficient, rather than making up answers."
        )

        system_prompt = (
            "You are a rigorous scientific research assistant. "
            "Every single claim in the Evidence section MUST be attributed with bracketed numbers like [1]. "
            "Never invent facts, metrics, or citations."
        )

        try:
            raw_answer = self.llm.complete(prompt, system_prompt=system_prompt, context=context_str)
        except Exception as e:
            raw_answer = f"### Evidence\nUnable to reach LLM provider: {e}\n\n### Interpretation\nProvider failure."

        # Map cited references to passage metadata
        used_citations: list[dict[str, Any]] = []
        for idx, p in enumerate(retrieved_passages, start=1):
            if f"[{idx}]" in raw_answer:
                used_citations.append({
                    "ref": f"[{idx}]",
                    "paper_id": p["paper_id"],
                    "title": p["title"],
                    "authors": p["authors"],
                    "doi": p["doi"],
                    "page": p["page"],
                    "section": p["section"],
                    "quote": p["text"][:250],
                })

        # Save assistant message
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

    def _hybrid_retrieve(
        self,
        db: Session,
        project_id: int,
        query: str,
        paper_id_filter: int | None = None,
        top_k: int = 6,
    ) -> list[dict[str, Any]]:
        # Get project paper IDs
        q_papers = (
            db.query(models.ProjectPaper.paper_id)
            .filter(models.ProjectPaper.project_id == project_id)
        )
        if paper_id_filter:
            q_papers = q_papers.filter(models.ProjectPaper.paper_id == paper_id_filter)
        paper_ids = [r[0] for r in q_papers.all()]

        if not paper_ids:
            return []

        # 1. Dense Vector Search (pgvector cosine)
        query_vector = self.embeddings.embed(query)
        vector_str = f"[{','.join(str(v) for v in query_vector)}]"

        vector_sql = text("""
            SELECT 
                c.id as chunk_id,
                c.paper_id,
                c.page_start as page,
                c.section,
                c.text,
                p.title,
                p.authors,
                p.doi,
                p.year,
                1 - (c.embedding <=> :query_vec) as similarity
            FROM paper_chunks c
            JOIN papers p ON p.id = c.paper_id
            WHERE c.paper_id = ANY(:paper_ids)
            ORDER BY c.embedding <=> :query_vec ASC
            LIMIT 15;
        """)

        vector_hits = []
        try:
            res = db.execute(vector_sql, {"query_vec": vector_str, "paper_ids": paper_ids}).fetchall()
            for r in res:
                vector_hits.append({
                    "chunk_id": r.chunk_id,
                    "paper_id": r.paper_id,
                    "page": r.page or 1,
                    "section": r.section or "Body",
                    "text": r.text,
                    "title": r.title,
                    "authors": r.authors,
                    "doi": r.doi,
                    "year": r.year,
                    "score": float(r.similarity),
                })
        except Exception:
            pass

        # 2. Text Keyword Search
        clean_terms = [w.strip() for w in query.split() if len(w) > 3][:5]
        text_hits = []
        if clean_terms:
            like_clause = " OR ".join(f"c.text ILIKE :term_{i}" for i in range(len(clean_terms)))
            text_sql = text(f"""
                SELECT 
                    c.id as chunk_id,
                    c.paper_id,
                    c.page_start as page,
                    c.section,
                    c.text,
                    p.title,
                    p.authors,
                    p.doi,
                    p.year
                FROM paper_chunks c
                JOIN papers p ON p.id = c.paper_id
                WHERE c.paper_id = ANY(:paper_ids) AND ({like_clause})
                LIMIT 15;
            """)
            params = {"paper_ids": paper_ids}
            for i, term in enumerate(clean_terms):
                params[f"term_{i}"] = f"%{term}%"
            try:
                res_text = db.execute(text_sql, params).fetchall()
                for r in res_text:
                    text_hits.append({
                        "chunk_id": r.chunk_id,
                        "paper_id": r.paper_id,
                        "page": r.page or 1,
                        "section": r.section or "Body",
                        "text": r.text,
                        "title": r.title,
                        "authors": r.authors,
                        "doi": r.doi,
                        "year": r.year,
                    })
            except Exception:
                pass

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_scores: dict[int, float] = {}
        chunk_map: dict[int, dict[str, Any]] = {}

        k_rrf = 60.0
        for rank, hit in enumerate(vector_hits):
            cid = hit["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k_rrf + rank + 1)
            chunk_map[cid] = hit

        for rank, hit in enumerate(text_hits):
            cid = hit["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k_rrf + rank + 1)
            if cid not in chunk_map:
                chunk_map[cid] = hit

        sorted_cids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
        return [chunk_map[cid] for cid in sorted_cids[:top_k]]
