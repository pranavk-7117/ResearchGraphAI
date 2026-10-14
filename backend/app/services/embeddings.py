import hashlib
import json
import os
from typing import Any

import numpy as np

EMBED_DIM = 384
_LOCAL_MODEL = None


def get_sentence_transformer():
    """Lazy load and cache sentence-transformers model (all-MiniLM-L6-v2)."""
    global _LOCAL_MODEL
    if _LOCAL_MODEL is None:
        from sentence_transformers import SentenceTransformer

        _LOCAL_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _LOCAL_MODEL


class EmbeddingService:
    def __init__(self) -> None:
        self.provider = os.getenv("LLM_PROVIDER", "local").lower()
        self.model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    def embed(self, text: str) -> list[float]:
        # 1. Optional OpenAI embeddings if explicitly configured
        if self.provider == "openai" and os.getenv("OPENAI_API_KEY"):
            try:
                from openai import OpenAI

                client = OpenAI()
                response = client.embeddings.create(model=self.model, input=text[:8000])
                return response.data[0].embedding
            except Exception as e:
                print(f"[EmbeddingService] OpenAI embed failed ({e}), falling back to local sentence-transformers.")

        # 2. Real local embedding model: sentence-transformers all-MiniLM-L6-v2
        if self.provider != "fake":
            try:
                st = get_sentence_transformer()
                embedding = st.encode(text[:4000], normalize_embeddings=True)
                return embedding.tolist()
            except Exception as e:
                print(f"[EmbeddingService] sentence-transformers embed failed ({e}), using deterministic fake.")

        # 3. Test fake fallback
        return deterministic_embedding(text)


def deterministic_embedding(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Hash-based pseudo-embedding used strictly as a fast test fake."""
    tokens = [token.strip(".,;:()[]{}").lower() for token in text.split()]
    vector = np.zeros(dim, dtype=np.float32)
    for token in tokens:
        if not token:
            continue
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "little") % dim
        sign = 1 if digest[4] % 2 == 0 else -1
        vector[index] += sign
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector.tolist()
    return (vector / norm).tolist()


def encode_embedding(values: list[float] | Any) -> Any:
    """Helper for compatibility: returns list of floats for pgvector."""
    if isinstance(values, str):
        try:
            return json.loads(values)
        except Exception:
            return []
    return values


def decode_embedding(value: Any) -> list[float]:
    """Helper for compatibility: extracts list of floats."""
    if not value:
        return []
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return []
    if hasattr(value, "tolist"):
        return value.tolist()
    return list(value)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    av = np.array(a, dtype=np.float32)
    bv = np.array(b, dtype=np.float32)
    denom = float(np.linalg.norm(av) * np.linalg.norm(bv))
    if denom == 0:
        return 0.0
    return float(np.dot(av, bv) / denom)
