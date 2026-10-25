"""
Academic Paper Discovery Service for ResearchGraphAI.

Fetches literature candidates across OpenAlex, Semantic Scholar, and arXiv.
Performs robust multi-stage deduplication, vector-based semantic ranking,
and records candidates in the database without auto-processing.
"""

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import math
import os
import re
from typing import Any
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.clients import ArxivClient, OpenAlexClient, RawCandidatePaper, SemanticScholarClient
from app import models
from app.services.embeddings import EmbeddingService, cosine_similarity
from app.services.llm import LLMService


def normalize_title(title: str) -> str:
    """Normalize title for hashing and fuzzy comparison."""
    clean = re.sub(r"[^\w\s]", "", title.lower())
    return " ".join(clean.split())


def hash_title(title: str) -> str:
    return hashlib.sha256(normalize_title(title).encode("utf-8")).hexdigest()


class DiscoveryService:
    def __init__(self):
        self.openalex = OpenAlexClient()
        self.semantic_scholar = SemanticScholarClient()
        self.arxiv = ArxivClient()
        self.embeddings = EmbeddingService()
        self.llm = LLMService()

    def expand_topic_queries(self, topic: str) -> list[str]:
        """
        Use LLM to expand a broad topic into focused academic search queries.
        If LLM is unconfigured, returns [topic] without synthetic fixed templates.
        """
        if not self.llm.is_available():
            return [topic]

        prompt = (
            f"You are a research librarian. Given the user's research topic '{topic}', "
            "generate 3 to 4 distinct academic keyword search queries to retrieve comprehensive, "
            "foundational, and recent literature from scholarly databases. "
            "Output strictly one search query per line with no numbers, bullets, or commentary."
        )
        try:
            res = self.llm.complete(prompt)
            queries = [q.strip() for q in res.splitlines() if q.strip()]
            valid = [q for q in queries if len(q) > 3][:4]
            if topic not in valid:
                valid.insert(0, topic)
            return valid
        except Exception:
            return [topic]

    def discover_candidates(
        self,
        db: Session,
        project_id: int,
        topic: str,
        limit: int = 25,
        year_min: int | None = None,
        year_max: int | None = None,
        oa_only: bool = False,
        ranking_mode: str = "balanced",
    ) -> list[models.ProjectPaper]:
        """
        Main discovery entry point: searches sources, deduplicates, ranks candidates,
        and saves candidate records in project_papers.
        """
        queries = self.expand_topic_queries(topic)

        # Update project filters and expanded queries
        project = db.query(models.ResearchProject).filter(models.ResearchProject.id == project_id).first()
        if project:
            current_filters = project.filters or {}
            current_filters.update({
                "expanded_queries": queries,
                "ranking_mode": ranking_mode,
                "year_min": year_min,
                "year_max": year_max,
                "oa_only": oa_only,
            })
            project.filters = current_filters
            db.commit()

        raw_candidates: list[RawCandidatePaper] = []
        per_query_limit = max(10, limit // len(queries) + 5)

        # Fast parallel candidate retrieval across sources
        tasks = []
        with ThreadPoolExecutor(max_workers=min(9, len(queries) * 3)) as executor:
            for q in queries:
                tasks.append(executor.submit(self.openalex.search, q, limit=per_query_limit, year_min=year_min, year_max=year_max, oa_only=oa_only))
                tasks.append(executor.submit(self.semantic_scholar.search, q, limit=per_query_limit, year_min=year_min, year_max=year_max, oa_only=oa_only))
                tasks.append(executor.submit(self.arxiv.search, q, limit=per_query_limit, year_min=year_min, year_max=year_max, oa_only=oa_only))

            for future in as_completed(tasks):
                try:
                    res = future.result()
                    if res:
                        raw_candidates.extend(res)
                except Exception:
                    continue

        # 1. Deduplicate
        deduped = self._deduplicate_candidates(raw_candidates)

        # 2. Embed and Rank
        ranked = self._rank_candidates(deduped, topic=topic, mode=ranking_mode, limit=limit)

        # 3. Upsert global papers and project_papers
        results = self._persist_candidates(db, project_id, ranked)
        return results

    def _deduplicate_candidates(self, candidates: list[RawCandidatePaper]) -> list[RawCandidatePaper]:
        seen_dois: set[str] = set()
        seen_s2: set[str] = set()
        seen_arxiv: set[str] = set()
        seen_hashes: set[str] = set()
        unique: list[RawCandidatePaper] = []

        for c in candidates:
            # Check DOI
            if c.doi:
                doi_norm = c.doi.strip().lower()
                if doi_norm in seen_dois:
                    continue
                seen_dois.add(doi_norm)

            # Check S2
            if c.source == "semantic_scholar" and c.external_id:
                if c.external_id in seen_s2:
                    continue
                seen_s2.add(c.external_id)

            # Check arXiv
            if c.source == "arxiv" and c.external_id:
                if c.external_id in seen_arxiv:
                    continue
                seen_arxiv.add(c.external_id)

            # Check normalized title hash
            thash = hash_title(c.title)
            if thash in seen_hashes:
                continue

            # Fuzzy match check against recent unique items
            is_fuzzy_dup = False
            norm_curr = normalize_title(c.title)
            for u in unique[-50:]:
                norm_u = normalize_title(u.title)
                if fuzz.token_set_ratio(norm_curr, norm_u) > 88:
                    is_fuzzy_dup = True
                    break

            if is_fuzzy_dup:
                continue

            seen_hashes.add(thash)
            unique.append(c)

        return unique

    def _rank_candidates(
        self,
        candidates: list[RawCandidatePaper],
        topic: str,
        mode: str = "balanced",
        limit: int = 25,
    ) -> list[tuple[RawCandidatePaper, float, dict[str, Any]]]:
        if not candidates:
            return []

        # Embed topic
        topic_vector = self.embeddings.embed(topic)

        # Batch embed candidate title + abstract
        texts_to_embed = [
            f"{c.title}. {c.abstract or ''}".strip()
            for c in candidates
        ]
        doc_vectors = self.embeddings.embed_batch(texts_to_embed)

        current_year = datetime.now(timezone.utc).year

        # Configurable ranking weights
        if mode == "recent":
            w_rel, w_rec, w_cit, w_oa = 0.35, 0.45, 0.10, 0.10
        elif mode == "citations":
            w_rel, w_rec, w_cit, w_oa = 0.35, 0.10, 0.45, 0.10
        elif mode == "relevant":
            w_rel, w_rec, w_cit, w_oa = 0.70, 0.10, 0.10, 0.10
        else:  # balanced
            w_rel, w_rec, w_cit, w_oa = 0.50, 0.20, 0.15, 0.15

        scored: list[tuple[RawCandidatePaper, float, dict[str, Any]]] = []

        for candidate, vector in zip(candidates, doc_vectors):
            # 1. Semantic similarity
            sim = max(0.0, cosine_similarity(topic_vector, vector))

            # 2. Recency score (decay over 25 years)
            if candidate.year and candidate.year > 1900:
                recency = max(0.0, 1.0 - (current_year - candidate.year) / 25.0)
            else:
                recency = 0.3

            # 3. Citation influence (log-scaled)
            cit_score = min(1.0, math.log1p(candidate.citation_count) / math.log1p(500))

            # 4. Open-access availability
            oa_score = 1.0 if candidate.oa_pdf_url else 0.2

            total_score = (
                sim * w_rel +
                recency * w_rec +
                cit_score * w_cit +
                oa_score * w_oa
            )

            score_components = {
                "total_score": round(total_score, 4),
                "semantic_relevance": round(sim, 4),
                "recency_score": round(recency, 4),
                "citation_influence": round(cit_score, 4),
                "open_access_score": round(oa_score, 4),
                "ranking_mode": mode,
                "weights": {
                    "relevance": w_rel,
                    "recency": w_rec,
                    "citations": w_cit,
                    "open_access": w_oa,
                },
            }

            scored.append((candidate, total_score, score_components))

        # Sort descending by total score
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def _persist_candidates(
        self,
        db: Session,
        project_id: int,
        ranked: list[tuple[RawCandidatePaper, float, dict[str, Any]]],
    ) -> list[models.ProjectPaper]:
        persisted_entries: list[models.ProjectPaper] = []

        for rank_idx, (cand, score, components) in enumerate(ranked, start=1):
            thash = hash_title(cand.title)

            # Find or create Paper
            paper = None
            if cand.doi:
                paper = db.query(models.Paper).filter(models.Paper.doi == cand.doi).first()
            if not paper:
                paper = db.query(models.Paper).filter(models.Paper.title_hash == thash).first()

            if not paper:
                paper = models.Paper(
                    doi=cand.doi,
                    openalex_id=cand.external_id if cand.source == "openalex" else None,
                    s2_id=cand.external_id if cand.source == "semantic_scholar" else None,
                    arxiv_id=cand.external_id if cand.source == "arxiv" else None,
                    title_hash=thash,
                    title=cand.title,
                    abstract=cand.abstract,
                    authors=cand.authors,
                    year=cand.year,
                    date=cand.date,
                    venue=cand.venue,
                    url=cand.url,
                    oa_status=cand.oa_status,
                    oa_pdf_url=cand.oa_pdf_url,
                    license=cand.license,
                    citation_count=cand.citation_count,
                    source_name=cand.source,
                    external_id=cand.external_id,
                    original_url=cand.url,
                )
                db.add(paper)
                db.flush()

            # Find or create ProjectPaper
            project_paper = (
                db.query(models.ProjectPaper)
                .filter(
                    models.ProjectPaper.project_id == project_id,
                    models.ProjectPaper.paper_id == paper.id,
                )
                .first()
            )

            if not project_paper:
                project_paper = models.ProjectPaper(
                    project_id=project_id,
                    paper_id=paper.id,
                    rank=rank_idx,
                    relevance_score=score,
                    score_components=components,
                    selected=False,  # Discovery strictly produces candidates
                    processing_status="discovered",
                    abstract_only=cand.metadata_only,
                )
                db.add(project_paper)
            else:
                project_paper.rank = rank_idx
                project_paper.relevance_score = score
                project_paper.score_components = components

            # Store raw references if available
            for ref in cand.raw_references[:20]:
                existing_ref = (
                    db.query(models.PaperReference)
                    .filter(
                        models.PaperReference.citing_paper_id == paper.id,
                        models.PaperReference.raw_reference == str(ref),
                    )
                    .first()
                )
                if not existing_ref:
                    db.add(
                        models.PaperReference(
                            citing_paper_id=paper.id,
                            raw_reference=str(ref),
                            source="api",
                            resolved=False,
                        )
                    )

            persisted_entries.append(project_paper)

        db.commit()
        return persisted_entries
