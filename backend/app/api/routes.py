from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services.features import FeatureService
from app.services.pdf_ingestion import PDFIngestionService

router = APIRouter()
features = FeatureService()
ingestion = PDFIngestionService()


@router.get("/papers", response_model=list[schemas.PaperOut])
def list_papers(db: Session = Depends(get_db)):
    return db.query(models.Paper).order_by(models.Paper.year, models.Paper.title).all()


@router.put("/papers/{paper_id}", response_model=schemas.PaperOut)
def update_paper(paper_id: int, payload: schemas.PaperUpdate, db: Session = Depends(get_db)):
    paper = db.get(models.Paper, paper_id)
    if paper is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Paper not found")
    paper.title = payload.title
    paper.authors = payload.authors
    paper.abstract = payload.abstract
    paper.year = payload.year
    paper.source_type = payload.source_type
    db.commit()
    db.refresh(paper)
    return paper


@router.get("/graph", response_model=schemas.GraphOut)
def graph(db: Session = Depends(get_db)):
    return {
        "papers": db.query(models.Paper).all(),
        "edges": db.query(models.Edge).all(),
    }


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...), db: Session = Depends(get_db)):
    result = ingestion.ingest_pdf(db, await file.read())
    return {
        "paper": schemas.PaperOut.model_validate(result.paper),
        "citation_edges": result.citation_edges,
        "similarity_edges": result.similarity_edges,
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
