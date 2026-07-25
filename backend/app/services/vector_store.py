import numpy as np

from app import models
from app.services.embeddings import cosine_similarity, decode_embedding


class VectorStore:
    def search(self, chunks: list[models.PaperChunk], query_embedding: list[float], limit: int = 5) -> list[tuple[float, models.PaperChunk]]:
        if not chunks:
            return []
        try:
            import faiss

            vectors = np.array([decode_embedding(chunk.embedding) for chunk in chunks], dtype=np.float32)
            query = np.array([query_embedding], dtype=np.float32)
            faiss.normalize_L2(vectors)
            faiss.normalize_L2(query)
            index = faiss.IndexFlatIP(vectors.shape[1])
            index.add(vectors)
            scores, positions = index.search(query, min(limit, len(chunks)))
            return [(float(score), chunks[int(pos)]) for score, pos in zip(scores[0], positions[0]) if pos >= 0]
        except Exception:
            scored = [
                (cosine_similarity(query_embedding, decode_embedding(chunk.embedding)), chunk)
                for chunk in chunks
            ]
            return sorted(scored, reverse=True, key=lambda item: item[0])[:limit]
