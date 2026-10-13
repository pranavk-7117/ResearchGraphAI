from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import execute_read_only_query, get_db, get_db_info
from app.services.features import FeatureService
from app.services.pdf_ingestion import PDFIngestionService

router = APIRouter()
features = FeatureService()
ingestion = PDFIngestionService()


@router.get("/papers", response_model=list[schemas.PaperOut])
def list_papers(db: Session = Depends(get_db)):
    return db.query(models.Paper).order_by(models.Paper.year.desc().nullslast(), models.Paper.title).all()


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
    db.commit()
    db.refresh(paper)
    return paper


@router.delete("/papers/{paper_id}")
def delete_paper(paper_id: int, db: Session = Depends(get_db)):
    paper = db.get(models.Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Cascade delete associated chunks, edges, and keyword associations
    db.query(models.PaperChunk).filter(models.PaperChunk.paper_id == paper_id).delete()
    db.query(models.Edge).filter(
        (models.Edge.source_paper_id == paper_id) | (models.Edge.target_paper_id == paper_id)
    ).delete()
    db.query(models.PaperKeyword).filter(models.PaperKeyword.paper_id == paper_id).delete()
    db.delete(paper)
    db.commit()
    return {"ok": True, "deleted_paper_id": paper_id}


@router.get("/graph", response_model=schemas.GraphOut)
def graph(db: Session = Depends(get_db)):
    return {
        "papers": db.query(models.Paper).all(),
        "edges": db.query(models.Edge).all(),
    }


@router.post("/upload", response_model=schemas.UploadOut)
async def upload_pdf(file: UploadFile = File(...), db: Session = Depends(get_db)):
    file_bytes = await file.read()
    result = ingestion.ingest_pdf(db, file_bytes, original_filename=file.filename or "uploaded_paper.pdf")
    return {
        "paper": schemas.PaperOut.model_validate(result.paper),
        "citation_edges": result.citation_edges,
        "similarity_edges": result.similarity_edges,
        "saved_path": result.saved_path,
    }


@router.post("/related", response_model=list[schemas.PaperOut])
def related(payload: schemas.RelatedRequest, db: Session = Depends(get_db)):
    return features.related_papers(db, payload.paper_id, payload.hops, payload.mode)


@router.post("/explain")
def explain(payload: schemas.ExplainRequest, db: Session = Depends(get_db)):
    return features.explain_connection(db, payload.source_id, payload.target_id)


@router.get("/gaps")
def gaps(db: Session = Depends(get_db)):
    return {
        "gap_suggestions": features.gap_suggestions(db),
        "missing_citations": features.missing_citations(db),
    }


@router.post("/evolution")
def evolution(payload: schemas.ChainRequest, db: Session = Depends(get_db)):
    return features.evolution_chain(db, payload.paper_ids, payload.topic, payload.days)


@router.post("/chat")
def chat(payload: schemas.ChatRequest, db: Session = Depends(get_db)):
    return features.rag_chat(db, payload.question)


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
        # Fallback check for current working directory or backend sibling
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


# --- DBMS Explorer & Query Endpoints ---

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
