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
_ONNX_EMBEDDER = None


class OnnxMiniLMEmbedder:
    """
    Low-memory pure-ONNX Runtime embedder for sentence-transformers/all-MiniLM-L6-v2.
    Uses ~70 MB total RSS (vs ~420 MB for PyTorch + sentence-transformers) with >0.99 cosine parity,
    keeping single-container deployments safely inside 512 MB RAM limits.
    """

    def __init__(self, repo_id: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer
        from huggingface_hub import hf_hub_download

        tok_path = hf_hub_download(repo_id, "tokenizer.json")
        model_file = "onnx/model_quint8_avx2.onnx"
        try:
            mdl_path = hf_hub_download(repo_id, model_file)
        except Exception:
            mdl_path = hf_hub_download(repo_id, "onnx/model.onnx")

        self.tokenizer = Tokenizer.from_file(tok_path)
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        try:
            self.session = ort.InferenceSession(mdl_path, sess_options=opts, providers=["CPUExecutionProvider"])
        except Exception:
            mdl_path = hf_hub_download(repo_id, "onnx/model.onnx")
            self.session = ort.InferenceSession(mdl_path, sess_options=opts, providers=["CPUExecutionProvider"])
        self.input_names = {inp.name for inp in self.session.get_inputs()}

    def encode(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        if not texts:
            return np.zeros((0, EMBED_DIM), dtype=np.float32)

        all_vecs: list[np.ndarray] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            encs = self.tokenizer.encode_batch(batch)
            input_ids = np.array([e.ids for e in encs], dtype=np.int64)
            attention_mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
            feed: dict[str, np.ndarray] = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            }
            if "token_type_ids" in self.input_names:
                feed["token_type_ids"] = np.zeros_like(input_ids, dtype=np.int64)

            token_emb = self.session.run(None, feed)[0]
            mask_exp = attention_mask[:, :, None].astype(np.float32)
            summed = (token_emb * mask_exp).sum(axis=1)
            counts = np.clip(mask_exp.sum(axis=1), 1e-9, None)
            pooled = summed / counts
            norms = np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-9, None)
            all_vecs.append((pooled / norms).astype(np.float32))

        return np.vstack(all_vecs)


def get_onnx_embedder() -> OnnxMiniLMEmbedder | None:
    """Lazy-load and cache pure-ONNX MiniLM embedder when onnxruntime + tokenizers are available."""
    global _ONNX_EMBEDDER
    if _ONNX_EMBEDDER is None:
        try:
            _ONNX_EMBEDDER = OnnxMiniLMEmbedder()
        except Exception:
            return None
    return _ONNX_EMBEDDER


def get_sentence_transformer():
    """Lazy-load and cache sentence-transformers all-MiniLM-L6-v2 fallback."""
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
                f"Failed to initialize embedding model '{EMBED_MODEL_NAME}': {e}. "
                "Ensure onnxruntime/tokenizers or sentence-transformers are properly installed."
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

        # 2. Pure-ONNX Runtime embedder (low-memory production default, avoids ~400 MB PyTorch spike)
        if os.getenv("EMBEDDING_BACKEND", "onnx").lower() != "sentence_transformers":
            onnx_emb = get_onnx_embedder()
            if onnx_emb is not None:
                truncated = [t[:4000] for t in texts]
                return onnx_emb.encode(truncated, batch_size=16).tolist()

        # 3. Local PyTorch sentence-transformers fallback
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


def l2_normalize_vector(vec: np.ndarray) -> list[float]:
    """Return L2-normalized list[float] for a 1D numpy vector."""
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        return vec.tolist()
    return (vec / norm).tolist()


def get_paper_embeddings(
    db: Any,
    papers: list[Any],
    embed_missing: bool = False,
    embed_service: EmbeddingService | None = None,
) -> dict[int, list[float]]:
    """
    Compute L2-normalized mean of all stored chunk embeddings per paper in a single query.
    Falls back to batch-embedding abstract/title when embed_missing=True and a paper has no chunks.
    """
    from app import models

    if not papers:
        return {}
    paper_ids = [p.id for p in papers]
    rows = (
        db.query(models.PaperChunk.paper_id, models.PaperChunk.embedding)
        .filter(models.PaperChunk.paper_id.in_(paper_ids))
        .all()
    )
    grouped: dict[int, list[np.ndarray]] = {}
    for pid, emb in rows:
        if emb is None:
            continue
        arr = np.array(emb.tolist() if hasattr(emb, "tolist") else emb, dtype=np.float32)
        grouped.setdefault(pid, []).append(arr)

    result: dict[int, list[float]] = {}
    missing_papers = []
    for p in papers:
        vecs = grouped.get(p.id)
        if vecs:
            result[p.id] = l2_normalize_vector(np.mean(vecs, axis=0))
        elif embed_missing and (p.abstract or p.title):
            missing_papers.append(p)

    if missing_papers:
        svc = embed_service or EmbeddingService()
        texts = [f"{p.title}. {p.abstract or ''}".strip() for p in missing_papers]
        try:
            fallback_vecs = svc.embed_batch(texts)
            for p, fvec in zip(missing_papers, fallback_vecs):
                result[p.id] = l2_normalize_vector(np.array(fvec, dtype=np.float32))
        except Exception:
            pass

    return result
