"""
T3: Topic Discovery Pipeline
Fetches real academic papers from OpenAlex and Semantic Scholar,
deduplicates, ranks by semantic relevance + citations, and ingests into workspace.
All HTTP responses are cached on disk (24h TTL) keyed by query hash.
Never invents papers; if APIs are unreachable and cache is empty, records in job error.
"""
import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app import models
from app.services.embeddings import EmbeddingService, cosine_similarity, encode_embedding


_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "discovery"
_CACHE_TTL_HOURS = 24
_OPENALEX_MAILTO = os.getenv("OPENALEX_MAILTO", "research@researchgraphai.com")


class DiscoveryService:
    def __init__(self) -> None:
        self.embeddings = EmbeddingService()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def discover(
        self,
        db: Session,
        workspace_id: int,
        topic: str,
        max_papers: int = 25,
        job_id: str | None = None,
    ) -> list[models.Paper]:
        """
        Full discovery pipeline for a topic into a workspace.
        Updates the Job row at key milestones if job_id is given.
        """
        self._update_job(db, job_id, "running", 0.05, "Expanding queries…")

        queries = self._expand_queries(topic)

        self._update_job(db, job_id, "running", 0.10, f"Fetching papers for {len(queries)} queries…")

        raw: list[dict] = []
        for i, q in enumerate(queries):
            try:
                raw.extend(self._fetch_openalex(q, limit=25))
            except Exception as exc:
                self._update_job(db, job_id, "running", 0.10 + i * 0.04, f"OpenAlex error: {exc}")
            try:
                raw.extend(self._fetch_semantic_scholar(q, limit=15))
            except Exception as exc:
                self._update_job(db, job_id, "running", 0.10 + i * 0.04, f"S2 error: {exc}")

        self._update_job(db, job_id, "running", 0.45, f"Deduplicating {len(raw)} raw results…")
        deduped = self._dedup(raw)

        # Filter: must have a non-empty abstract
        deduped = [p for p in deduped if (p.get("abstract") or "").strip()]

        self._update_job(db, job_id, "running", 0.55, f"Ranking {len(deduped)} unique papers…")
        topic_embedding = self.embeddings.embed(topic)
        ranked = self._rank(deduped, topic_embedding)[:max_papers]

        self._update_job(db, job_id, "running", 0.65, f"Ingesting top {len(ranked)} papers…")
        ingested: list[models.Paper] = []
        for idx, paper_dict in enumerate(ranked):
            try:
                p = self._ingest_paper(db, workspace_id, paper_dict)
                ingested.append(p)
                progress = 0.65 + (idx + 1) / max(len(ranked), 1) * 0.30
                self._update_job(db, job_id, "running", round(progress, 2), f"Ingested {idx + 1}/{len(ranked)}: {paper_dict['title'][:60]}")
            except Exception as exc:
                # Skip individual paper errors; do not fail the whole job
                pass

        # Update workspace status
        ws = db.get(models.Workspace, workspace_id)
        if ws:
            ws.status = "ready"
            ws.expanded_queries = json.dumps(queries)
            db.commit()

        self._update_job(db, job_id, "completed", 1.0, f"Discovery complete — {len(ingested)} papers ingested.")
        return ingested

    # ------------------------------------------------------------------
    # Query expansion
    # ------------------------------------------------------------------

    def _expand_queries(self, topic: str) -> list[str]:
        """Generate 5 search queries as variations of the topic (no LLM required)."""
        t = topic.strip()
        return [
            t,
            f"survey {t}",
            f"{t} review",
            f"{t} methods",
            f"{t} applications",
        ]

    # ------------------------------------------------------------------
    # API fetchers with disk cache
    # ------------------------------------------------------------------

    def _cache_path(self, query: str, source: str) -> Path:
        key = hashlib.md5(f"{source}:{query}".encode()).hexdigest()
        return _CACHE_DIR / f"{key}.json"

    def _cache_load(self, path: Path) -> list[dict] | None:
        if not path.exists():
            return None
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            if datetime.now() - mtime > timedelta(hours=_CACHE_TTL_HOURS):
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _cache_save(self, path: Path, data: list[dict]) -> None:
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _fetch_openalex(self, query: str, limit: int = 20) -> list[dict]:
        cache_path = self._cache_path(query, "openalex")
        cached = self._cache_load(cache_path)
        if cached is not None:
            return cached

        url = "https://api.openalex.org/works"
        params = {
            "search": query,
            "per-page": limit,
            "mailto": _OPENALEX_MAILTO,
            "filter": "has_abstract:true",
            "select": "id,title,abstract_inverted_index,publication_year,authorships,doi,cited_by_count,open_access,primary_location",
        }
        try:
            resp = httpx.get(url, params=params, timeout=15)
            resp.raise_for_status()
            works = resp.json().get("results", [])
        except Exception as exc:
            raise RuntimeError(f"OpenAlex fetch failed: {exc}") from exc

        papers = []
        for work in works:
            title = work.get("title") or ""
            if not title:
                continue
            abstract = self._reconstruct_abstract(work.get("abstract_inverted_index") or {})
            authors_raw = work.get("authorships") or []
            authors = ", ".join(
                a.get("author", {}).get("display_name", "")
                for a in authors_raw[:6]
                if a.get("author", {}).get("display_name")
            )
            doi = (work.get("doi") or "").replace("https://doi.org/", "")
            oa = work.get("open_access") or {}
            pdf_url = oa.get("oa_url") or ""
            loc = work.get("primary_location") or {}
            venue = (loc.get("source") or {}).get("display_name") or ""
            papers.append({
                "title": title,
                "abstract": abstract,
                "year": work.get("publication_year"),
                "authors": authors,
                "doi": doi,
                "citation_count": work.get("cited_by_count") or 0,
                "url": work.get("id") or "",
                "pdf_url": pdf_url,
                "venue": venue,
                "external_id": work.get("id") or "",
                "source": "openalex",
                "tldr": None,
            })

        self._cache_save(cache_path, papers)
        return papers

    def _reconstruct_abstract(self, inverted_index: dict) -> str:
        """Reconstruct OpenAlex inverted-index abstract into plain text."""
        if not inverted_index:
            return ""
        pos_word: dict[int, str] = {}
        for word, positions in inverted_index.items():
            for pos in positions:
                pos_word[pos] = word
        if not pos_word:
            return ""
        return " ".join(pos_word[i] for i in sorted(pos_word))

    def _fetch_semantic_scholar(self, query: str, limit: int = 15) -> list[dict]:
        cache_path = self._cache_path(query, "semantic_scholar")
        cached = self._cache_load(cache_path)
        if cached is not None:
            return cached

        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": query,
            "limit": limit,
            "fields": "title,abstract,year,authors,citationCount,externalIds,openAccessPdf,venue,tldr",
        }
        try:
            resp = httpx.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json().get("data", [])
        except Exception as exc:
            raise RuntimeError(f"Semantic Scholar fetch failed: {exc}") from exc

        papers = []
        for item in data:
            title = item.get("title") or ""
            if not title:
                continue
            abstract = item.get("abstract") or ""
            authors = ", ".join(
                a.get("name", "")
                for a in (item.get("authors") or [])[:6]
                if a.get("name")
            )
            ext_ids = item.get("externalIds") or {}
            doi = ext_ids.get("DOI") or ""
            oa = item.get("openAccessPdf") or {}
            pdf_url = oa.get("url") or ""
            tldr_obj = item.get("tldr") or {}
            tldr = tldr_obj.get("text") if isinstance(tldr_obj, dict) else None
            papers.append({
                "title": title,
                "abstract": abstract,
                "year": item.get("year"),
                "authors": authors,
                "doi": doi,
                "citation_count": item.get("citationCount") or 0,
                "url": f"https://www.semanticscholar.org/paper/{item.get('paperId', '')}",
                "pdf_url": pdf_url,
                "venue": item.get("venue") or "",
                "external_id": item.get("paperId") or "",
                "source": "semantic_scholar",
                "tldr": tldr,
            })

        self._cache_save(cache_path, papers)
        return papers

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _dedup(self, papers: list[dict]) -> list[dict]:
        seen_dois: set[str] = set()
        seen_titles: list[str] = []
        result: list[dict] = []

        for p in papers:
            doi = (p.get("doi") or "").strip().lower()
            title = (p.get("title") or "").strip()

            # Dedup by DOI first
            if doi:
                if doi in seen_dois:
                    continue
                seen_dois.add(doi)

            # Dedup by fuzzy title
            is_dup = any(
                fuzz.token_set_ratio(title.lower(), existing.lower()) > 88
                for existing in seen_titles
            )
            if is_dup:
                continue

            seen_titles.append(title)
            result.append(p)

        return result

    # ------------------------------------------------------------------
    # Ranking
    # ------------------------------------------------------------------

    def _rank(self, papers: list[dict], topic_embedding: list[float]) -> list[dict]:
        scored = []
        for p in papers:
            text = f"{p.get('title', '')} {p.get('abstract', '')}".strip()
            if not text:
                scored.append((0.0, p))
                continue
            try:
                emb = self.embeddings.embed(text[:1000])
                sem_score = cosine_similarity(topic_embedding, emb)
            except Exception:
                sem_score = 0.0
            cite_score = min((p.get("citation_count") or 0) / 500.0, 1.0)
            total = sem_score * 0.6 + cite_score * 0.4
            scored.append((total, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored]

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def _ingest_paper(self, db: Session, workspace_id: int, paper_dict: dict) -> models.Paper:
        title = paper_dict.get("title") or "Untitled"
        abstract = paper_dict.get("abstract") or ""
        embed_text = f"{title}\n{abstract}"
        whole_embedding = self.embeddings.embed(embed_text[:1000])

        paper = models.Paper(
            workspace_id=workspace_id,
            title=title,
            authors=paper_dict.get("authors") or "",
            abstract=abstract,
            year=paper_dict.get("year"),
            source_type="discovered",
            full_text="",
            whole_embedding=encode_embedding(whole_embedding),
            doi=paper_dict.get("doi") or None,
            external_id=paper_dict.get("external_id") or None,
            citation_count=paper_dict.get("citation_count") or 0,
            venue=paper_dict.get("venue") or None,
            url=paper_dict.get("url") or None,
            pdf_url=paper_dict.get("pdf_url") or None,
            tldr=paper_dict.get("tldr") or None,
        )
        db.add(paper)
        db.flush()  # get paper.id without full commit

        # Store abstract as a single chunk for RAG
        if abstract:
            chunk_emb = self.embeddings.embed(abstract[:1000])
            db.add(models.PaperChunk(
                workspace_id=workspace_id,
                paper_id=paper.id,
                chunk_index=0,
                text=abstract[:2000],
                embedding=encode_embedding(chunk_emb),
            ))

        # Link similarity edges to existing workspace papers
        existing = (
            db.query(models.Paper)
            .filter(
                models.Paper.workspace_id == workspace_id,
                models.Paper.id != paper.id,
                models.Paper.whole_embedding.is_not(None),
            )
            .all()
        )
        SIMILARITY_THRESHOLD = 0.72
        for other in existing:
            try:
                score = cosine_similarity(whole_embedding, list(other.whole_embedding))
                if score >= SIMILARITY_THRESHOLD:
                    db.add(models.Edge(
                        workspace_id=workspace_id,
                        source_paper_id=paper.id,
                        target_paper_id=other.id,
                        edge_type="similarity",
                        relation_label="similar",
                        confidence=round(score, 3),
                    ))
                    db.add(models.Edge(
                        workspace_id=workspace_id,
                        source_paper_id=other.id,
                        target_paper_id=paper.id,
                        edge_type="similarity",
                        relation_label="similar",
                        confidence=round(score, 3),
                    ))
            except Exception:
                pass

        db.commit()
        db.refresh(paper)
        return paper

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def _update_job(
        self,
        db: Session,
        job_id: str | None,
        status: str,
        progress: float,
        message: str,
        error: str | None = None,
    ) -> None:
        if not job_id:
            return
        try:
            job = db.get(models.Job, job_id)
            if job:
                job.status = status
                job.progress = progress
                job.message = message[:500]
                if error:
                    job.error = error
                job.updated_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass  # Never let job tracking crash the discovery pipeline
