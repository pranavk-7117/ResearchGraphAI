from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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
