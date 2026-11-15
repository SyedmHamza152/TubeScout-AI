"""Topic extraction: cluster comments into discussion topics.

Method: TF-IDF over normalized comment text + MiniBatchKMeans on the
embedding space; each topic is labeled by its strongest distinctive terms
(c-TF-IDF style within-cluster term scoring). Topics carry a sentiment mix
and share of the sample. All outputs are INFERENCE-labeled.
"""
from __future__ import annotations

import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def top_terms_per_group(documents: list[str], groups: list[int], n_terms: int = 8) -> dict[int, list[str]]:
    """Distinctive terms per cluster via within-cluster TF-IDF."""
    out: dict[int, list[str]] = {}
    vectorizer = TfidfVectorizer(
        analyzer="word", ngram_range=(1, 2), min_df=1, max_features=20000,
        sublinear_tf=True,
    )
    docs = [d for d, _ in zip(documents, groups)]
    if not docs:
        return out
    try:
        matrix = vectorizer.fit_transform(docs)
    except ValueError:
        return out
    vocab = vectorizer.get_feature_names_out()
    for g in sorted(set(groups)):
        idx = [i for i, gg in enumerate(groups) if gg == g]
        if not idx:
            continue
        mean_tfidf = matrix[idx].mean(axis=0).A1
        top = sorted(range(len(vocab)), key=lambda i: -mean_tfidf[i])[:n_terms]
        out[g] = [vocab[i] for i in top if mean_tfidf[i] > 0]
    return out


def label_for_terms(terms: list[str], fallback: str = "General discussion") -> str:
    if not terms:
        return fallback
    words = [t for t in terms if " " not in t][:3]
    phrases = [t for t in terms if " " in t][:2]
    parts = words + phrases
    return ", ".join(parts[:4]).title() if parts else fallback


def choose_k(embeddings: list[list[float]], min_k: int = 2, max_k: int = 6) -> int:
    """Pick k by silhouette score (bounded for interpretability)."""
    import numpy as np
    from sklearn.cluster import MiniBatchKMeans

    n = len(embeddings)
    if n < 12:
        return 0  # not enough comments to justify topic clustering
    X = np.asarray(embeddings)
    max_k = min(max_k, max(2, n // 6))
    best_k, best_s = 0, -1.0
    for k in range(min_k, max_k + 1):
        km = MiniBatchKMeans(n_clusters=k, random_state=42, batch_size=64, n_init=10)
        labels = km.fit_predict(X)
        if len(set(labels)) < 2:
            continue
        s = float(silhouette_score(X, labels, sample_size=min(800, n), random_state=42))
        if s > best_s:
            best_k, best_s = k, s
    return best_k
