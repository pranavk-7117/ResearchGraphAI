"""
API routes for ResearchGraphAI.
All endpoints that operate on workspace-scoped data accept an optional ?workspace_id query parameter.
Workspace CRUD provides full isolation between research sessions.
"""
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import SessionLocal, execute_read_only_query, get_db, get_db_info
from app.services.features import FeatureService
from app.services.pdf_ingestion import PDFIngestionService

router = APIRouter()
features = FeatureService()
ingestion = PDFIngestionService()


# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------

@router.post("/workspaces", response_model=schemas.WorkspaceOut, status_code=201)
def create_workspace(payload: schemas.WorkspaceCreate, db: Session = Depends(get_db)):
    ws = models.Workspace(topic=payload.topic, status="active")
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return {**ws.__dict__, "paper_count": 0}


@router.get("/workspaces", response_model=list[schemas.WorkspaceOut])
def list_workspaces(db: Session = Depends(get_db)):
    workspaces = db.query(models.Workspace).order_by(models.Workspace.created_at.desc()).all()
    results = []
    for ws in workspaces:
        count = db.query(func.count(models.Paper.id)).filter(models.Paper.workspace_id == ws.id).scalar() or 0
        results.append({**ws.__dict__, "paper_count": count})
    return results


@router.get("/workspaces/{workspace_id}", response_model=schemas.WorkspaceOut)
def get_workspace(workspace_id: int, db: Session = Depends(get_db)):
    ws = db.get(models.Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    count = db.query(func.count(models.Paper.id)).filter(models.Paper.workspace_id == workspace_id).scalar() or 0
    return {**ws.__dict__, "paper_count": count}


@router.delete("/workspaces/{workspace_id}")
def delete_workspace(workspace_id: int, db: Session = Depends(get_db)):
    ws = db.get(models.Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    db.delete(ws)
    db.commit()
    return {"ok": True, "deleted_workspace_id": workspace_id}


# ---------------------------------------------------------------------------
# Discovery job (POST triggers background thread, GET polls progress)
# ---------------------------------------------------------------------------

@router.post("/workspaces/{workspace_id}/discover")
def discover_papers(
    workspace_id: int,
    payload: schemas.DiscoverRequest,
    db: Session = Depends(get_db),
):
    ws = db.get(models.Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    job_id = str(uuid.uuid4())
    job = models.Job(
        id=job_id,
        workspace_id=workspace_id,
        type="discovery",
        status="pending",
        progress=0.0,
        message="Starting discovery…",
    )
    db.add(job)
    db.commit()

    topic = ws.topic

    def _run_discovery():
        from app.services.discovery import DiscoveryService
        session = SessionLocal()
        try:
            DiscoveryService().discover(
                session,
                workspace_id=workspace_id,
                topic=topic,
                max_papers=payload.max_papers,
                job_id=job_id,
            )
        except Exception as exc:
            _job = session.get(models.Job, job_id)
            if _job:
                _job.status = "failed"
                _job.error = str(exc)
                session.commit()
        finally:
            session.close()

    threading.Thread(target=_run_discovery, daemon=True).start()
    return {"job_id": job_id, "workspace_id": workspace_id}


@router.get("/jobs/{job_id}", response_model=schemas.JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(models.Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ---------------------------------------------------------------------------
# Papers
# ---------------------------------------------------------------------------

@router.get("/papers", response_model=list[schemas.PaperOut])
def list_papers(workspace_id: int | None = Query(None), db: Session = Depends(get_db)):
    q = db.query(models.Paper)
    if workspace_id is not None:
        q = q.filter(models.Paper.workspace_id == workspace_id)
    return q.order_by(models.Paper.year.desc().nullslast(), models.Paper.title).all()


@router.put("/papers/{paper_id}", response_model=schemas.PaperOut)
def update_paper(paper_id: int, payload: schemas.PaperUpdate, db: Session = Depends(get_db)):
    paper = db.get(models.Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    paper.title = payload.title
    paper.authors = payload.authors
    paper.abstract = payload.abstract
    paper.year = payload.year
    paper.source_type = payload.source_type
    if payload.doi is not None:
        paper.doi = payload.doi
    if payload.venue is not None:
        paper.venue = payload.venue
    db.commit()
    db.refresh(paper)
    return paper


@router.delete("/papers/{paper_id}")
def delete_paper(paper_id: int, db: Session = Depends(get_db)):
    paper = db.get(models.Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    db.query(models.PaperChunk).filter(models.PaperChunk.paper_id == paper_id).delete()
    db.query(models.Edge).filter(
        (models.Edge.source_paper_id == paper_id) | (models.Edge.target_paper_id == paper_id)
    ).delete()
    db.query(models.PaperKeyword).filter(models.PaperKeyword.paper_id == paper_id).delete()
    db.delete(paper)
    db.commit()
    return {"ok": True, "deleted_paper_id": paper_id}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

@router.get("/graph", response_model=schemas.GraphOut)
def graph(workspace_id: int | None = Query(None), db: Session = Depends(get_db)):
    pq = db.query(models.Paper)
    eq = db.query(models.Edge)
    if workspace_id is not None:
        pq = pq.filter(models.Paper.workspace_id == workspace_id)
        eq = eq.filter(models.Edge.workspace_id == workspace_id)
    return {
        "papers": pq.all(),
        "edges": eq.all(),
        "workspace_id": workspace_id,
    }


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=schemas.UploadOut)
async def upload_pdf(
    file: UploadFile = File(...),
    workspace_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    file_bytes = await file.read()
    result = ingestion.ingest_pdf(db, file_bytes, original_filename=file.filename or "uploaded_paper.pdf", workspace_id=workspace_id)
    return {
        "paper": schemas.PaperOut.model_validate(result.paper),
        "citation_edges": result.citation_edges,
        "similarity_edges": result.similarity_edges,
        "saved_path": result.saved_path,
        "workspace_id": workspace_id,
    }


# ---------------------------------------------------------------------------
# Graph features
# ---------------------------------------------------------------------------

@router.post("/related", response_model=list[schemas.PaperOut])
def related(payload: schemas.RelatedRequest, db: Session = Depends(get_db)):
    return features.related_papers(db, payload.paper_id, payload.hops, payload.mode, workspace_id=payload.workspace_id)


@router.post("/explain")
def explain(payload: schemas.ExplainRequest, db: Session = Depends(get_db)):
    return features.explain_connection(db, payload.source_id, payload.target_id, workspace_id=payload.workspace_id)


@router.get("/gaps")
def gaps(workspace_id: int | None = Query(None), db: Session = Depends(get_db)):
    return {
        "gap_suggestions": features.gap_suggestions(db, workspace_id=workspace_id),
        "missing_citations": features.missing_citations(db, workspace_id=workspace_id),
    }


@router.post("/evolution")
def evolution(payload: schemas.ChainRequest, db: Session = Depends(get_db)):
    return features.evolution_chain(
        db, payload.paper_ids, payload.topic, payload.days, workspace_id=payload.workspace_id
    )


@router.post("/chat")
def chat(payload: schemas.ChatRequest, db: Session = Depends(get_db)):
    return features.rag_chat(db, payload.question, workspace_id=payload.workspace_id)


# ---------------------------------------------------------------------------
# Compare against my paper (T6)
# ---------------------------------------------------------------------------

@router.post("/workspaces/{workspace_id}/my-paper", response_model=schemas.UploadOut)
async def upload_my_paper(
    workspace_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    ws = db.get(models.Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    file_bytes = await file.read()
    result = ingestion.ingest_pdf(
        db, file_bytes, original_filename=file.filename or "my_paper.pdf",
        workspace_id=workspace_id, is_user_paper=True
    )
    return {
        "paper": schemas.PaperOut.model_validate(result.paper),
        "citation_edges": result.citation_edges,
        "similarity_edges": result.similarity_edges,
        "saved_path": result.saved_path,
        "workspace_id": workspace_id,
    }


@router.get("/workspaces/{workspace_id}/compare")
def compare_my_paper(workspace_id: int, db: Session = Depends(get_db)):
    """Compare the user's uploaded paper against all other workspace papers."""
    ws = db.get(models.Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    user_paper = (
        db.query(models.Paper)
        .filter(models.Paper.workspace_id == workspace_id, models.Paper.is_user_paper == True)
        .order_by(models.Paper.id.desc())
        .first()
    )
    if user_paper is None:
        raise HTTPException(status_code=404, detail="No user paper uploaded to this workspace yet")

    return features.compare_paper(db, user_paper, workspace_id=workspace_id)


# ---------------------------------------------------------------------------
# Metadata endpoints
# ---------------------------------------------------------------------------

@router.get("/topics")
def get_topics(db: Session = Depends(get_db)):
    """Retrieve distinct topics and domains dynamically from database keywords and paper counts."""
    results = (
        db.query(models.Keyword.text, func.count(models.PaperKeyword.paper_id).label("count"))
        .join(models.PaperKeyword, models.Keyword.id == models.PaperKeyword.keyword_id)
        .group_by(models.Keyword.id, models.Keyword.text)
        .order_by(func.count(models.PaperKeyword.paper_id).desc(), models.Keyword.text)
        .all()
    )
    return [{"topic": r[0], "count": r[1]} for r in results]


@router.get("/sample-papers")
def list_sample_papers():
    """List all pre-generated domain PDF research papers available in the research_papers directory."""
    project_root = Path(__file__).resolve().parents[3]
    papers_dir = project_root / "research_papers"
    if not papers_dir.exists():
        papers_dir = Path.cwd().parent / "research_papers" if Path.cwd().name == "backend" else Path.cwd() / "research_papers"
    if not papers_dir.exists():
        return {"domains": [], "total_papers": 0, "directory": str(papers_dir)}

    domains_list = []
    total = 0
    for domain_folder in sorted(papers_dir.iterdir()):
        if domain_folder.is_dir():
            pdfs = [
                {
                    "filename": f.name,
                    "title": f.stem.replace("_", " "),
                    "size_bytes": f.stat().st_size,
                    "relative_path": str(f.relative_to(project_root)).replace("\\", "/"),
                    "absolute_path": str(f.resolve()),
                }
                for f in sorted(domain_folder.glob("*.pdf"))
            ]
            total += len(pdfs)
            domains_list.append({
                "domain_name": domain_folder.name.replace("_Domain", "").replace("_", " "),
                "folder_name": domain_folder.name,
                "paper_count": len(pdfs),
                "papers": pdfs,
            })

    return {
        "domains": domains_list,
        "total_papers": total,
        "directory": str(papers_dir.resolve()),
    }


# ---------------------------------------------------------------------------
# DBMS Explorer & Query Endpoints
# ---------------------------------------------------------------------------

@router.get("/db/status")
def database_status(db: Session = Depends(get_db)):
    """Retrieve full database metadata, relational tables, row counts, and schema for DBMS demo."""
    return get_db_info(db)


@router.post("/db/query", response_model=schemas.SQLQueryResponse)
def execute_sql_query(payload: schemas.SQLQueryRequest, db: Session = Depends(get_db)):
    """Execute a safe read-only SQL query to demonstrate database features."""
    try:
        return execute_read_only_query(db, payload.query)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SQL Execution Error: {e}")
