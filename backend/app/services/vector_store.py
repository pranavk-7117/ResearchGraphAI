from sqlalchemy.orm import Session

from app import models
from app.services.embeddings import cosine_similarity


class VectorStore:
    """
    Vector search service utilizing PostgreSQL pgvector extension for native SQL similarity search.
    Removes legacy FAISS and JSON text dependencies.
    """

    def search_chunks(
        self,
        db: Session,
        query_embedding: list[float],
        limit: int = 5,
        paper_ids: list[int] | None = None,
        workspace_id: int | None = None,
    ) -> list[tuple[float, models.PaperChunk]]:
        """
        Execute chunk similarity search directly in SQL using pgvector's cosine distance operator (<=>).
        """
        query = db.query(
            models.PaperChunk,
            models.PaperChunk.embedding.cosine_distance(query_embedding).label("distance"),
        )
        if workspace_id is not None:
            query = query.filter(models.PaperChunk.workspace_id == workspace_id)
        if paper_ids:
            query = query.filter(models.PaperChunk.paper_id.in_(paper_ids))
        results = query.order_by("distance").limit(limit).all()
        return [(round(float(1.0 - dist), 4), chunk) for chunk, dist in results]

    def search_papers(
        self,
        db: Session,
        query_embedding: list[float],
        limit: int = 5,
        exclude_paper_id: int | None = None,
        workspace_id: int | None = None,
    ) -> list[tuple[float, models.Paper]]:
        """
        Execute paper similarity search directly in SQL using pgvector's cosine distance operator (<=>).
        """
        query = db.query(
            models.Paper,
            models.Paper.whole_embedding.cosine_distance(query_embedding).label("distance"),
        ).filter(models.Paper.whole_embedding.is_not(None))
        if workspace_id is not None:
            query = query.filter(models.Paper.workspace_id == workspace_id)
        if exclude_paper_id is not None:
            query = query.filter(models.Paper.id != exclude_paper_id)
        results = query.order_by("distance").limit(limit).all()
        return [(round(float(1.0 - dist), 4), paper) for paper, dist in results]

    def search(
        self,
        chunks: list[models.PaperChunk],
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[tuple[float, models.PaperChunk]]:
        """
        In-memory fallback for lists of already loaded chunks.
        """
        scored = [
            (cosine_similarity(query_embedding, list(chunk.embedding)), chunk)
            for chunk in chunks
            if chunk.embedding is not None
        ]
        return sorted(scored, reverse=True, key=lambda item: item[0])[:limit]
