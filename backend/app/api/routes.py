"""
REST API Routes for ResearchGraphAI.

Structured around:
- User-owned research projects
- Academic literature candidate discovery (separate from processing)
- Candidate selection and resilient background processing
- Evidence-grounded graph, clusters, evolution, gaps, and literature reviews
- Passage-attributed RAG chat
- Uploaded manuscript comparison
- Job queue status tracking
"""

import threading
from typing import Annotated
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import AuthenticatedUser, get_current_user, verify_project_ownership
from app.database import get_db
from app.services.chat import ChatService
from app.services.clustering import ClusteringService
from app.services.compare import CompareService
from app.services.discovery import DiscoveryService
from app.services.embeddings import EmbeddingService
from app.services.evolution import EvolutionService
from app.services.gaps import GapsService
from app.services.jobs import JobService
from app.services.literature_review import LiteratureReviewService
from app.services.pdf_processing import PDFProcessingService
from app.services.relations import RelationsService
from app.storage import storage_service

router = APIRouter()


# ==============================================================================
# Research Projects
# ==============================================================================

@router.post("/projects", response_model=schemas.ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    data: schemas.ProjectCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new research project workspace."""
    project = models.ResearchProject(
        user_id=user.id,
        topic=data.topic.strip(),
        filters=data.filters,
        status="active",
        corpus_version=1,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    return schemas.ProjectOut(
        id=project.id,
        user_id=project.user_id,
        topic=project.topic,
        status=project.status,
        filters=project.filters or {},
        corpus_version=project.corpus_version,
        paper_count=0,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get("/projects", response_model=list[schemas.ProjectOut])
def list_projects(
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all research projects owned by the authenticated user."""
    projects = (
        db.query(models.ResearchProject)
        .filter(models.ResearchProject.user_id == user.id)
        .order_by(models.ResearchProject.created_at.desc())
        .all()
    )

    out = []
    for p in projects:
        count = (
            db.query(models.ProjectPaper)
            .filter(models.ProjectPaper.project_id == p.id)
            .count()
        )
        out.append(
            schemas.ProjectOut(
                id=p.id,
                user_id=p.user_id,
                topic=p.topic,
                status=p.status,
                filters=p.filters or {},
                corpus_version=p.corpus_version,
                paper_count=count,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
        )
    return out


@router.get("/projects/{project_id}", response_model=schemas.ProjectOut)
def get_project(
    project_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get project details with server-side ownership verification."""
    project = verify_project_ownership(project_id, user, db)
    count = (
        db.query(models.ProjectPaper)
        .filter(models.ProjectPaper.project_id == project.id)
        .count()
    )
    return schemas.ProjectOut(
        id=project.id,
        user_id=project.user_id,
        topic=project.topic,
        status=project.status,
        filters=project.filters or {},
        corpus_version=project.corpus_version,
        paper_count=count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete project with storage cleanup and cascade."""
    project = verify_project_ownership(project_id, user, db)

    # Clean up stored files
    docs = db.query(models.PaperDocument).filter(models.PaperDocument.project_id == project.id).all()
    for d in docs:
        storage_service.delete_document(d.storage_path)

    db.delete(project)
    db.commit()
    return None


# ==============================================================================
# Discovery & Candidate Selection
# ==============================================================================

@router.post("/projects/{project_id}/discover", response_model=schemas.JobOut)
def trigger_discovery(
    project_id: int,
    limit: int = Query(25, ge=5, le=100),
    ranking_mode: str = Query("balanced", pattern="^(balanced|relevant|recent|citations)$"),
    year_min: int | None = Query(None),
    year_max: int | None = Query(None),
    oa_only: bool = Query(False),
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start academic discovery job across OpenAlex, Semantic Scholar, and arXiv."""
    project = verify_project_ownership(project_id, user, db)

    # Update project filters
    filters = project.filters or {}
    filters.update({
        "limit": limit,
        "ranking_mode": ranking_mode,
        "year_min": year_min,
        "year_max": year_max,
        "oa_only": oa_only,
    })
    project.filters = filters
    db.commit()

    job = JobService.create_job(db, job_type="discovery", project_id=project.id)

    # Launch background thread to run job execution
    thread = threading.Thread(target=JobService.execute_job, args=(job.id,), daemon=True)
    thread.start()

    return schemas.JobOut.model_validate(job)


@router.get("/projects/{project_id}/candidates", response_model=list[schemas.PaperOut])
def get_candidates(
    project_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve ranked candidate papers discovered for this project."""
    project = verify_project_ownership(project_id, user, db)

    entries = (
        db.query(models.ProjectPaper, models.Paper)
        .join(models.Paper, models.ProjectPaper.paper_id == models.Paper.id)
        .filter(models.ProjectPaper.project_id == project.id)
        .order_by(models.ProjectPaper.relevance_score.desc())
        .all()
    )

    out = []
    for pp, paper in entries:
        out.append(
            schemas.PaperOut(
                id=paper.id,
                doi=paper.doi,
                title=paper.title,
                abstract=paper.abstract,
                authors=paper.authors or [],
                year=paper.year,
                date=paper.date,
                venue=paper.venue,
                url=paper.url,
                oa_status=paper.oa_status,
                oa_pdf_url=paper.oa_pdf_url,
                citation_count=paper.citation_count,
                source_name=paper.source_name,
                abstract_only=pp.abstract_only,
                selected=pp.selected,
                processing_status=pp.processing_status,
                relevance_score=pp.relevance_score,
                score_components=pp.score_components or {},
            )
        )
    return out


@router.post("/projects/{project_id}/select-candidates")
def select_candidates(
    project_id: int,
    data: schemas.CandidateSelectionRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Select candidate papers for processing."""
    project = verify_project_ownership(project_id, user, db)

    project_papers = (
        db.query(models.ProjectPaper)
        .filter(models.ProjectPaper.project_id == project.id)
        .all()
    )

    selected_ids = set(data.paper_ids)
    for pp in project_papers:
        if data.select_all:
            pp.selected = True
        else:
            pp.selected = pp.paper_id in selected_ids

    db.commit()
    return {"ok": True, "selected_count": sum(1 for pp in project_papers if pp.selected)}


@router.post("/projects/{project_id}/process", response_model=schemas.JobOut)
def trigger_processing(
    project_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start durable background job to process selected candidates."""
    project = verify_project_ownership(project_id, user, db)

    job = JobService.create_job(db, job_type="processing", project_id=project.id)

    # Launch background thread
    thread = threading.Thread(target=JobService.execute_job, args=(job.id,), daemon=True)
    thread.start()

    return schemas.JobOut.model_validate(job)


# ==============================================================================
# Graph & Research Corpus
# ==============================================================================

@router.get("/projects/{project_id}/papers", response_model=list[schemas.PaperOut])
def list_project_papers(
    project_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all papers indexed in the project corpus."""
    project = verify_project_ownership(project_id, user, db)

    entries = (
        db.query(models.ProjectPaper, models.Paper)
        .join(models.Paper, models.ProjectPaper.paper_id == models.Paper.id)
        .filter(models.ProjectPaper.project_id == project.id)
        .order_by(models.Paper.year.desc().nullslast())
        .all()
    )

    out = []
    for pp, paper in entries:
        out.append(
            schemas.PaperOut(
                id=paper.id,
                doi=paper.doi,
                title=paper.title,
                abstract=paper.abstract,
                authors=paper.authors or [],
                year=paper.year,
                date=paper.date,
                venue=paper.venue,
                url=paper.url,
                oa_status=paper.oa_status,
                oa_pdf_url=paper.oa_pdf_url,
                citation_count=paper.citation_count,
                source_name=paper.source_name,
                abstract_only=pp.abstract_only,
                selected=pp.selected,
                processing_status=pp.processing_status,
                relevance_score=pp.relevance_score,
                score_components=pp.score_components or {},
            )
        )
    return out


@router.get("/projects/{project_id}/graph", response_model=schemas.GraphOut)
def get_project_graph(
    project_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve NetworkX knowledge graph with distinct citation vs inferred edges."""
    project = verify_project_ownership(project_id, user, db)

    project_papers = (
        db.query(models.ProjectPaper, models.Paper)
        .join(models.Paper, models.ProjectPaper.paper_id == models.Paper.id)
        .filter(models.ProjectPaper.project_id == project.id)
        .all()
    )

    # Get clusters for node coloring
    members = (
        db.query(models.ClusterMember)
        .join(models.ResearchCluster, models.ClusterMember.cluster_id == models.ResearchCluster.id)
        .filter(models.ResearchCluster.project_id == project.id)
        .all()
    )
    cluster_map = {m.paper_id: m.cluster_id for m in members}

    # Compute PageRank centrality
    from app.services.research_graph import NetworkXGraphService
    G = NetworkXGraphService.build_project_graph(db, project.id)
    graph_analytics = NetworkXGraphService.analyze_graph(G)
    pagerank_map = graph_analytics.get("pagerank", {})

    nodes = []
    for pp, paper in project_papers:
        authors_list = [a.get("name", "") for a in (paper.authors or []) if isinstance(a, dict)]
        nodes.append(
            schemas.GraphNode(
                id=paper.id,
                title=paper.title,
                year=paper.year,
                citation_count=paper.citation_count,
                abstract_only=pp.abstract_only,
                cluster_id=cluster_map.get(paper.id),
                authors_str=", ".join(authors_list[:3]),
                abstract=paper.abstract,
                venue=paper.venue,
                doi=paper.doi,
                url=paper.original_url or (f"https://doi.org/{paper.doi}" if paper.doi else None),
                pagerank=float(pagerank_map.get(paper.id, 0.0)),
            )
        )

    relations = (
        db.query(models.PaperRelation)
        .filter(models.PaperRelation.project_id == project.id)
        .all()
    )

    edges = []
    for rel in relations:
        edges.append(
            schemas.GraphEdge(
                id=rel.id,
                source=rel.source_id,
                target=rel.target_id,
                relation_type=rel.relation_type,
                basis=rel.basis,
                score=rel.score,
            )
        )

    return schemas.GraphOut(
        nodes=nodes,
        edges=edges,
        total_nodes=len(nodes),
        total_edges=len(edges),
    )


# ==============================================================================
# Clusters, Evolution & Gaps
# ==============================================================================

@router.get("/projects/{project_id}/clusters", response_model=list[schemas.ClusterOut])
def get_clusters(
    project_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve thematic clusters derived from pgvector embeddings."""
    project = verify_project_ownership(project_id, user, db)

    clusters = (
        db.query(models.ResearchCluster)
        .filter(models.ResearchCluster.project_id == project.id)
        .all()
    )

    out = []
    for c in clusters:
        members_query = (
            db.query(models.ClusterMember, models.Paper)
            .join(models.Paper, models.ClusterMember.paper_id == models.Paper.id)
            .filter(models.ClusterMember.cluster_id == c.id)
            .all()
        )
        member_outs = [
            schemas.ClusterMemberOut(
                paper_id=p.id,
                title=p.title,
                year=p.year,
                membership_score=cm.membership_score,
            )
            for cm, p in members_query
        ]
        out.append(
            schemas.ClusterOut(
                id=c.id,
                label=c.label,
                representative_paper_ids=c.representative_paper_ids or [],
                year_distribution=c.year_distribution or {},
                member_count=len(member_outs),
                members=member_outs,
            )
        )
    return out


@router.get("/projects/{project_id}/evolution", response_model=schemas.EvolutionOut)
def get_evolution(
    project_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve evolution analysis across citation timeline, method changes, and findings."""
    project = verify_project_ownership(project_id, user, db)
    evolution_service = EvolutionService()
    res = evolution_service.generate_evolution(db, project.id)
    return schemas.EvolutionOut(
        citation_timeline=res.get("citation_timeline", []),
        method_progression=res.get("method_progression", []),
        finding_dynamics=res.get("finding_dynamics", []),
        phases=res.get("phases", []),
        transitions=res.get("transitions", []),
        focus_trends=res.get("focus_trends", {}),
        key_insights=res.get("key_insights", []),
        time_range=res.get("time_range", {}),
        total_papers=res.get("total_papers", 0),
        paper_stream=res.get("paper_stream", []),
        annual_milestones=res.get("annual_milestones", []),
    )


@router.get("/projects/{project_id}/gaps", response_model=list[schemas.GapOut])
def get_gaps(
    project_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve evidence-backed research gaps with formula scores and external validation."""
    project = verify_project_ownership(project_id, user, db)

    gaps = (
        db.query(models.ResearchGap)
        .filter(models.ResearchGap.project_id == project.id)
        .order_by(models.ResearchGap.evidence_strength.desc())
        .all()
    )

    # If no gaps computed yet, run detection
    if not gaps:
        gaps_service = GapsService()
        gaps = gaps_service.detect_gaps(db, project.id)

    # Deduplicate gaps (keeping highest evidence score) and clean up duplicate rows in DB
    seen_statements = set()
    unique_gaps = []
    dup_ids = []
    for g in gaps:
        stmt_key = (g.gap_statement or "").strip().lower()
        if not stmt_key:
            continue
        if stmt_key in seen_statements:
            dup_ids.append(g.id)
        else:
            seen_statements.add(stmt_key)
            unique_gaps.append(g)

    if dup_ids:
        try:
            db.query(models.ResearchGap).filter(models.ResearchGap.id.in_(dup_ids)).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()

    return [
        schemas.GapOut(
            id=g.id,
            gap_statement=g.gap_statement,
            why_it_matters=g.why_it_matters,
            gap_type=g.gap_type,
            supporting_evidence=g.supporting_evidence or [],
            counter_evidence=g.counter_evidence or [],
            corpus_cannot_establish=g.corpus_cannot_establish,
            suggested_research_question=g.suggested_research_question,
            suggested_validation=g.suggested_validation,
            score_components=g.score_components or {},
            evidence_strength=g.evidence_strength,
            external_verification=g.external_verification or {},
            user_feedback=g.user_feedback,
            created_at=g.created_at,
        )
        for g in unique_gaps
    ]


@router.post("/gaps/{gap_id}/feedback")
def submit_gap_feedback(
    gap_id: int,
    data: schemas.GapFeedbackRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record user feedback on candidate research gap."""
    gaps_service = GapsService()
    gap = gaps_service.record_feedback(db, gap_id=gap_id, feedback=data.feedback)
    if not gap:
        raise HTTPException(status_code=404, detail="Research gap not found")
    return {"ok": True, "feedback": gap.user_feedback}


# ==============================================================================
# Literature Review & BibTeX
# ==============================================================================

@router.get("/projects/{project_id}/literature-review", response_model=schemas.LiteratureReviewOut)
def get_literature_review(
    project_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve existing grounded literature review if previously generated."""
    project = verify_project_ownership(project_id, user, db)
    review = (
        db.query(models.LiteratureReview)
        .filter(models.LiteratureReview.project_id == project.id)
        .order_by(models.LiteratureReview.created_at.desc())
        .first()
    )
    if not review:
        raise HTTPException(status_code=404, detail="No literature review generated yet for this project")
    return schemas.LiteratureReviewOut(
        id=review.id,
        corpus_version=review.corpus_version,
        sections=review.sections or [],
        verification_status=review.verification_status,
        created_at=review.created_at,
    )


@router.post("/projects/{project_id}/literature-review", response_model=schemas.LiteratureReviewOut)
def generate_literature_review(
    project_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate or retrieve grounded literature review."""
    project = verify_project_ownership(project_id, user, db)
    review_service = LiteratureReviewService()
    try:
        review = review_service.generate_review(db, project_id=project.id)
        return schemas.LiteratureReviewOut(
            id=review.id,
            corpus_version=review.corpus_version,
            sections=review.sections or [],
            verification_status=review.verification_status,
            created_at=review.created_at,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/bibtex")
def export_bibtex(
    project_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export verified BibTeX file from stored paper metadata."""
    project = verify_project_ownership(project_id, user, db)
    review_service = LiteratureReviewService()
    bibtex_str = review_service.generate_bibtex(db, project_id=project.id)
    return {"bibtex": bibtex_str}


# ==============================================================================
# RAG Chat
# ==============================================================================

@router.post("/projects/{project_id}/chat", response_model=schemas.ChatResponse)
def chat_with_corpus(
    project_id: int,
    data: schemas.ChatRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Query research corpus with hybrid retrieval and passage-attributed citations."""
    project = verify_project_ownership(project_id, user, db)
    chat_service = ChatService()
    res = chat_service.query_rag(
        db=db,
        project_id=project.id,
        question=data.question,
        session_id=data.session_id,
        paper_id_filter=data.paper_id_filter,
    )
    return schemas.ChatResponse(
        session_id=res["session_id"],
        answer=res["answer"],
        citations=res["citations"],
        retrieved_count=res["retrieved_count"],
    )


# ==============================================================================
# Upload & Comparison
# ==============================================================================

@router.post("/projects/{project_id}/upload", response_model=schemas.PaperAnalysisOut)
async def upload_and_compare(
    project_id: int,
    file: UploadFile = File(...),
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload user paper, extract full text, and run comparative gap/novelty report against corpus."""
    project = verify_project_ownership(project_id, user, db)

    content = await file.read()
    storage_path, sha256_hash, file_size = storage_service.save_document(content, project_id=project.id)

    pdf_service = PDFProcessingService()
    extracted = pdf_service.process_pdf_bytes(content)

    doc_row = models.PaperDocument(
        project_id=project.id,
        storage_path=storage_path,
        sha256=sha256_hash,
        pages=extracted.total_pages,
        bytes=file_size,
        source="uploaded",
    )
    db.add(doc_row)
    db.commit()
    db.refresh(doc_row)

    compare_service = CompareService()
    analysis = compare_service.compare_uploaded_paper(
        db=db,
        project_id=project.id,
        extracted=extracted,
        document_id=doc_row.id,
    )

    return schemas.PaperAnalysisOut(
        id=analysis.id,
        paper_title=analysis.paper_title,
        report=analysis.report or {},
        evidence_rows=analysis.evidence_rows or [],
        created_at=analysis.created_at,
    )


@router.get("/projects/{project_id}/analyses", response_model=list[schemas.PaperAnalysisOut])
def list_analyses(
    project_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List comparative reports for uploaded papers."""
    project = verify_project_ownership(project_id, user, db)
    analyses = (
        db.query(models.PaperAnalysis)
        .filter(models.PaperAnalysis.project_id == project.id)
        .order_by(models.PaperAnalysis.created_at.desc())
        .all()
    )
    return [
        schemas.PaperAnalysisOut(
            id=a.id,
            paper_title=a.paper_title,
            report=a.report or {},
            evidence_rows=a.evidence_rows or [],
            created_at=a.created_at,
        )
        for a in analyses
    ]


# ==============================================================================
# Jobs
# ==============================================================================

@router.get("/jobs/{job_id}", response_model=schemas.JobOut)
def get_job_status(
    job_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Poll status of background discovery or processing job."""
    job = db.query(models.ResearchJob).filter(models.ResearchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.project_id:
        verify_project_ownership(job.project_id, user, db)

    return schemas.JobOut.model_validate(job)
