import hashlib
import json
import os

import numpy as np


EMBED_DIM = 384


class EmbeddingService:
    def __init__(self) -> None:
        self.provider = os.getenv("LLM_PROVIDER", "local").lower()
        self.model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    def embed(self, text: str) -> list[float]:
        if self.provider == "openai" and os.getenv("OPENAI_API_KEY"):
            from openai import OpenAI

            client = OpenAI()
            response = client.embeddings.create(model=self.model, input=text[:8000])
            return response.data[0].embedding
        return deterministic_embedding(text)


def deterministic_embedding(text: str, dim: int = EMBED_DIM) -> list[float]:
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


def encode_embedding(values: list[float]) -> str:
    return json.dumps(values)


def decode_embedding(value: str | None) -> list[float]:
    if not value:
        return []
    return json.loads(value)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    av = np.array(a, dtype=np.float32)
    bv = np.array(b, dtype=np.float32)
    denom = float(np.linalg.norm(av) * np.linalg.norm(bv))
    if denom == 0:
        return 0.0
    return float(np.dot(av, bv) / denom)
