"""
Durable Research Job Queue & Execution Service for ResearchGraphAI.

Manages background jobs with:
- DB-backed state in research_jobs
- Atomic lock acquisition using SELECT ... FOR UPDATE SKIP LOCKED
- Per-paper fault isolation (single paper failure yields completed_with_warnings)
- Progress tracking and heartbeat updates
"""

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import os
import time
import uuid
from typing import Any
import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app import models
from app.database import SessionLocal
from app.services.clustering import ClusteringService
from app.services.discovery import DiscoveryService
from app.services.embeddings import EmbeddingService
from app.services.evolution import EvolutionService
from app.services.facts_extraction import FactExtractionService
from app.services.gaps import GapsService
from app.services.literature_review import LiteratureReviewService
from app.services.pdf_processing import PDFProcessingService
from app.services.relations import RelationsService
from app.storage import storage_service


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobService:
    @staticmethod
    def create_job(
        db: Session,
        job_type: str,
        project_id: int | None = None,
        initial_stage: str = "queued",
    ) -> models.ResearchJob:
        job = models.ResearchJob(
            id=str(uuid.uuid4()),
            project_id=project_id,
            type=job_type,
            status="pending",
            stage=initial_stage,
            progress=0.0,
            per_paper_results={},
            warnings=[],
            errors=[],
        )
        db.add(job)
        db.commit()
        return job

    @staticmethod
    def acquire_next_job(db: Session, worker_id: str) -> models.ResearchJob | None:
        """Atomically lock and fetch the next pending job using PostgreSQL SKIP LOCKED."""
        stmt = text("""
            SELECT id FROM research_jobs
            WHERE status = 'pending'
            ORDER BY created_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1;
        """)
        row = db.execute(stmt).fetchone()
        if not row:
            return None

        job_id = row[0]
        job = db.query(models.ResearchJob).filter(models.ResearchJob.id == job_id).first()
        if job:
            job.status = "processing"
            job.locked_by = worker_id
            job.locked_at = utc_now()
            job.attempts += 1
            db.commit()
        return job

    @staticmethod
    def execute_job(job_id: str) -> None:
        """Execute a locked job synchronously or from worker."""
        db = SessionLocal()
        try:
            job = db.query(models.ResearchJob).filter(models.ResearchJob.id == job_id).first()
            if not job:
                return

            if job.type == "discovery":
                JobService._run_discovery_job(db, job)
            elif job.type == "processing":
                JobService._run_processing_job(db, job)
            else:
                job.status = "failed"
                job.errors.append(f"Unknown job type: {job.type}")
                db.commit()
        except Exception as e:
            db.rollback()
            job = db.query(models.ResearchJob).filter(models.ResearchJob.id == job_id).first()
            if job:
                job.status = "failed"
                job.errors = list(job.errors or []) + [str(e)]
                flag_modified(job, "errors")
                db.commit()
        finally:
            db.close()

    @staticmethod
    def _run_discovery_job(db: Session, job: models.ResearchJob) -> None:
        if not job.project_id:
            job.status = "failed"
            job.errors.append("Discovery job missing project_id")
            db.commit()
            return

        project = db.query(models.ResearchProject).filter(models.ResearchProject.id == job.project_id).first()
        if not project:
            job.status = "failed"
            job.errors.append(f"Project {job.project_id} not found")
            db.commit()
            return

        job.status = "discovering"
        job.stage = "fetching_academic_candidates"
        job.progress = 0.2
        db.commit()

        discovery = DiscoveryService()
        filters = project.filters or {}
        limit = filters.get("limit", 25)
        ranking_mode = filters.get("ranking_mode", "balanced")
        year_min = filters.get("year_min")
        year_max = filters.get("year_max")
        oa_only = filters.get("oa_only", False)

        candidates = discovery.discover_candidates(
            db=db,
            project_id=project.id,
            topic=project.topic,
            limit=limit,
            year_min=year_min,
            year_max=year_max,
            oa_only=oa_only,
            ranking_mode=ranking_mode,
        )

        job.status = "completed"
        job.stage = "candidates_ready"
        job.progress = 1.0
        job.per_paper_results = {"discovered_count": len(candidates)}
        db.commit()

    @staticmethod
    def _run_processing_job(db: Session, job: models.ResearchJob) -> None:
        if not job.project_id:
            job.status = "failed"
            job.errors.append("Processing job missing project_id")
            db.commit()
            return

        project = db.query(models.ResearchProject).filter(models.ResearchProject.id == job.project_id).first()
        if not project:
            job.status = "failed"
            job.errors.append(f"Project {job.project_id} not found")
            db.commit()
            return

        # Fetch selected papers in this project
        selected_project_papers = (
            db.query(models.ProjectPaper)
            .filter(
                models.ProjectPaper.project_id == project.id,
                models.ProjectPaper.selected == True,
            )
            .all()
        )

        # If none marked selected, default to processing all discovered papers
        if not selected_project_papers:
            all_papers = (
                db.query(models.ProjectPaper)
                .filter(models.ProjectPaper.project_id == project.id)
                .all()
            )
            for p in all_papers:
                p.selected = True
            db.commit()
            selected_project_papers = all_papers

        total_papers = len(selected_project_papers)
        if total_papers == 0:
            job.status = "completed"
            job.progress = 1.0
            job.stage = "no_papers_to_process"
            db.commit()
            return

        pdf_service = PDFProcessingService()
        embedding_service = EmbeddingService()
        fact_service = FactExtractionService()

        per_paper_results = dict(job.per_paper_results or {})
        warnings = list(job.warnings or [])

        # Fast parallel pre-fetch of PDFs (5 concurrent workers, 7s timeout)
        pdf_urls_map: dict[int, str] = {}
        for pp in selected_project_papers:
            p_obj = db.query(models.Paper.id, models.Paper.oa_pdf_url).filter(models.Paper.id == pp.paper_id).first()
            if p_obj and p_obj.oa_pdf_url:
                pdf_urls_map[p_obj.id] = p_obj.oa_pdf_url

        pdf_cache: dict[int, bytes | None] = {}
        def fetch_pdf(pid: int, url: str) -> tuple[int, bytes | None]:
            try:
                with httpx.Client(timeout=7.0, follow_redirects=True, headers={"User-Agent": "ResearchGraphAI/2.0"}) as client:
                    resp = client.get(url)
                    if resp.status_code == 200 and resp.content.startswith(b"%PDF-"):
                        return (pid, resp.content)
            except Exception:
                return (pid, None)
            return (pid, None)

        if pdf_urls_map:
            with ThreadPoolExecutor(max_workers=min(5, len(pdf_urls_map))) as pool:
                futures = [pool.submit(fetch_pdf, pid, url) for pid, url in pdf_urls_map.items()]
                for f in futures:
                    try:
                        pid, b = f.result()
                        if b:
                            pdf_cache[pid] = b
                    except Exception:
                        pass

        # Process each paper with isolation
        for idx, pp in enumerate(selected_project_papers, start=1):
            try:
                paper = db.query(models.Paper).filter(models.Paper.id == pp.paper_id).first()
                if not paper:
                    continue

                job.stage = f"processing_paper_{idx}_of_{total_papers}"
                job.progress = round(0.1 + 0.6 * (idx / total_papers), 2)
                db.commit()

                pdf_bytes = pdf_cache.get(paper.id)

                # Extract text & chunks
                if pdf_bytes:
                    pp.processing_status = "extracting"
                    db.commit()

                    # Save document in storage idempotently
                    storage_path, sha256_hash, file_size = storage_service.save_document(
                        pdf_bytes, project_id=project.id
                    )
                    doc_row = (
                        db.query(models.PaperDocument)
                        .filter(models.PaperDocument.sha256 == sha256_hash)
                        .first()
                    )
                    if not doc_row:
                        doc_row = models.PaperDocument(
                            paper_id=paper.id,
                            project_id=project.id,
                            storage_path=storage_path,
                            sha256=sha256_hash,
                            pages=1,
                            bytes=file_size,
                            source="discovered",
                        )
                        db.add(doc_row)
                        db.flush()

                    extracted = pdf_service.process_pdf_bytes(pdf_bytes, known_title=paper.title)
                    pp.abstract_only = not extracted.full_text_available
                    doc_row.pages = extracted.total_pages

                    # Embed and save chunks idempotently
                    chunk_texts = [c.text for c in extracted.chunks]
                    if chunk_texts:
                        vectors = embedding_service.embed_batch(chunk_texts)
                        for c, vec in zip(extracted.chunks, vectors):
                            existing_chunk = (
                                db.query(models.PaperChunk)
                                .filter(
                                    models.PaperChunk.paper_id == paper.id,
                                    models.PaperChunk.text_hash == c.text_hash,
                                    models.PaperChunk.embedding_model == embedding_service.model_name,
                                )
                                .first()
                            )
                            if not existing_chunk:
                                chunk_row = models.PaperChunk(
                                    paper_id=paper.id,
                                    page_start=c.page_start,
                                    page_end=c.page_end,
                                    section=c.section,
                                    chunk_index=c.chunk_index,
                                    text=c.text,
                                    text_hash=c.text_hash,
                                    embedding=vec,
                                    embedding_model=embedding_service.model_name,
                                    embedding_version=embedding_service.version,
                                )
                                db.add(chunk_row)
                else:
                    # Abstract only chunking
                    pp.abstract_only = True
                    abstract_text = paper.abstract or paper.title
                    import hashlib
                    thash = hashlib.sha256(abstract_text.encode("utf-8")).hexdigest()
                    existing_chunk = (
                        db.query(models.PaperChunk)
                        .filter(
                            models.PaperChunk.paper_id == paper.id,
                            models.PaperChunk.text_hash == thash,
                        )
                        .first()
                    )
                    if not existing_chunk:
                        vec = embedding_service.embed(abstract_text)
                        chunk_row = models.PaperChunk(
                            paper_id=paper.id,
                            page_start=1,
                            page_end=1,
                            section="Abstract",
                            chunk_index=0,
                            text=abstract_text,
                            text_hash=thash,
                            embedding=vec,
                            embedding_model=embedding_service.model_name,
                            embedding_version=embedding_service.version,
                        )
                        db.add(chunk_row)

                # Extract structured facts idempotently (skip if already extracted)
                existing_fact = (
                    db.query(models.PaperFact)
                    .filter(models.PaperFact.paper_id == paper.id)
                    .first()
                )
                if not existing_fact:
                    pp.processing_status = "extracting_facts"
                    db.commit()
                    fact_service.extract_paper_facts(db, paper_id=paper.id, project_id=project.id)

                pp.processing_status = "completed"
                per_paper_results[str(paper.id)] = {"status": "success", "abstract_only": pp.abstract_only}
                db.commit()
            except Exception as e:
                db.rollback()
                try:
                    re_pp = (
                        db.query(models.ProjectPaper)
                        .filter(
                            models.ProjectPaper.project_id == project.id,
                            models.ProjectPaper.paper_id == pp.paper_id,
                        )
                        .first()
                    )
                    if re_pp:
                        re_pp.processing_status = "error"
                        re_pp.error = str(e)
                        db.commit()
                except Exception:
                    pass
                paper_title = paper.title if "paper" in locals() and paper else str(pp.paper_id)
                warnings.append(f"Error processing paper '{paper_title}': {e}")
                per_paper_results[str(pp.paper_id)] = {"status": "error", "error": str(e)}

        # Step 2: Build Relations (Citations + Semantic Similarity)
        job.stage = "building_relations"
        job.progress = 0.75
        db.commit()
        relations_service = RelationsService()
        relations_service.build_project_relations(db, project_id=project.id)

        # Step 3: Compute Clusters
        job.stage = "clustering_themes"
        job.progress = 0.85
        db.commit()
        clustering_service = ClusteringService()
        clustering_service.cluster_project(db, project_id=project.id)

        # Step 4: Evolution & Gaps
        job.stage = "synthesizing_evolution_and_gaps"
        job.progress = 0.92
        db.commit()
        evolution_service = EvolutionService()
        evolution_service.generate_evolution(db, project_id=project.id)

        gaps_service = GapsService()
        gaps_service.detect_gaps(db, project_id=project.id)

        # Step 5: Literature Review
        job.stage = "generating_literature_review"
        job.progress = 0.98
        db.commit()
        try:
            review_service = LiteratureReviewService()
            review_service.generate_review(db, project_id=project.id)
        except Exception as rev_err:
            warnings.append(f"Literature review generation note: {rev_err}")

        # Complete job
        job.status = "completed_with_warnings" if warnings else "completed"
        job.stage = "done"
        job.progress = 1.0
        job.warnings = warnings
        job.per_paper_results = per_paper_results
        flag_modified(job, "warnings")
        flag_modified(job, "per_paper_results")
        db.commit()
        db.commit()
