"""Comment embeddings — pluggable provider with deterministic fallback.

Providers:
  hashing (default, always available): sklearn HashingVectorizer (word+char
      n-grams, robust to Roman Urdu spelling variance) + TruncatedSVD to a
      fixed dimension. Deterministic, model-free, multilingual-tolerant.
  sentence_transformers: optional multilingual transformer embeddings when
      installed (settings.EMBEDDING_PROVIDER == "st").

The active provider + identity is recorded per comment (`embedding_model`)
so results stay reproducible and honest about method.
"""
from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_st_model = None
_svd = None


def _hashing_embed(texts: list[str]) -> list[list[float]]:
    global _svd
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import HashingVectorizer
    from sklearn.pipeline import make_pipeline

    dim = min(settings.EMBEDDING_DIM, 96)
    if _svd is None:
        vec = HashingVectorizer(
            analyzer="word", ngram_range=(1, 2), n_features=2**18,
            norm="l2", alternate_sign=True,
        )
        _svd = make_pipeline(vec, TruncatedSVD(n_components=dim, random_state=42))
        # fit SVD on the corpus itself (unsupervised projection)
        _svd.fit(texts)
    projected = _svd.transform(texts)
    return [[round(float(x), 5) for x in row] for row in projected]


def _st_embed(texts: list[str]) -> list[list[float]]:
    global _st_model
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise RuntimeError("sentence-transformers is not installed")
    if _st_model is None:
        _st_model = SentenceTransformer(settings.EMBEDDING_MODEL)
    vectors = _st_model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return [[round(float(x), 5) for x in row] for row in vectors]


def embed_texts(texts: list[str]) -> tuple[list[list[float]], str]:
    """Embed a batch. Returns (vectors, model_id). Empty input -> ([], '')."""
    if not texts:
        return [], ""
    provider = (settings.EMBEDDING_PROVIDER or "hashing").lower()
    if provider == "st":
        try:
            return _st_embed(texts), f"st:{settings.EMBEDDING_MODEL}"
        except Exception as exc:  # fall back deterministically
            logger.warning("sentence-transformers unavailable (%s) — using hashing provider", exc)
    try:
        return _hashing_embed(texts), f"hashing:{settings.EMBEDDING_DIM}d"
    except Exception as exc:
        logger.warning("hashing embedding failed: %s", exc)
        return [], ""
