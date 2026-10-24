"""
Embedding Service for ResearchGraphAI.

Provides real 384-dimensional dense vector embeddings using sentence-transformers (all-MiniLM-L6-v2)
or OpenAI embeddings if configured. Bounded and normalized for pgvector cosine indexing.
Strictly disallows silent fallback to fake embeddings in production.
"""

import os
from typing import Any
import numpy as np

EMBED_DIM = 384
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
EMBED_MODEL_VERSION = "1.0"

_LOCAL_MODEL = None


def get_sentence_transformer():
    """Lazy-load and cache sentence-transformers all-MiniLM-L6-v2."""
    global _LOCAL_MODEL
    if _LOCAL_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            _LOCAL_MODEL = SentenceTransformer(EMBED_MODEL_NAME)
        except Exception as e:
            # Check if running in a pure offline test environment
            if os.getenv("TESTING") == "true" or os.getenv("PYTEST_CURRENT_TEST"):
                return None
            raise RuntimeError(
                f"Failed to initialize sentence-transformers embedding model '{EMBED_MODEL_NAME}': {e}. "
                "Ensure PyTorch and sentence-transformers are properly installed."
            ) from e
    return _LOCAL_MODEL


class EmbeddingService:
    def __init__(self) -> None:
        self.provider = os.getenv("EMBEDDING_PROVIDER", "sentence-transformers").lower()
        self.model_name = os.getenv("EMBEDDING_MODEL_NAME", EMBED_MODEL_NAME)
        self.dim = int(os.getenv("EMBEDDING_DIM", str(EMBED_DIM)))
        self.version = EMBED_MODEL_VERSION

    def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        if not text or not text.strip():
            return [0.0] * self.dim
        res = self.embed_batch([text])
        return res[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch-embed multiple text strings."""
        if not texts:
            return []

        # 1. Optional OpenAI embeddings if explicitly requested
        if self.provider == "openai" and os.getenv("OPENAI_API_KEY"):
            try:
                from openai import OpenAI
                client = OpenAI()
                truncated = [t[:8000] for t in texts]
                response = client.embeddings.create(model=self.model_name, input=truncated)
                return [d.embedding for d in response.data]
            except Exception as e:
                raise RuntimeError(f"OpenAI embedding generation failed: {e}") from e

        # 2. Local sentence-transformers (default)
        st = get_sentence_transformer()
        if st is not None:
            truncated = [t[:4000] for t in texts]
            embeddings = st.encode(truncated, normalize_embeddings=True, show_progress_bar=False)
            return embeddings.tolist()

        # 3. Test-only deterministic fake when explicitly in test mode
        if os.getenv("TESTING") == "true" or os.getenv("PYTEST_CURRENT_TEST"):
            return [deterministic_test_embedding(t, self.dim) for t in texts]

        raise RuntimeError(
            "Embedding model is unavailable. Silent fallback to pseudo-embeddings is prohibited in production."
        )


def deterministic_test_embedding(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Deterministic pseudo-embedding strictly for automated unit testing."""
    import hashlib
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


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    av = np.array(a, dtype=np.float32)
    bv = np.array(b, dtype=np.float32)
    denom = float(np.linalg.norm(av) * np.linalg.norm(bv))
    if denom == 0:
        return 0.0
    return float(np.dot(av, bv) / denom)
