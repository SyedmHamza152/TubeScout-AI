"""Audience feature builder.

Aggregates comment-level signals into author-level behavioural features
(using author_channel_id when present, else per-comment rows). Features are
behavioural ONLY — they never imply demographic identity (age/gender), which
the YouTube API does not provide for commenters.
"""
from __future__ import annotations

import numpy as np


def build_author_features(comments: list) -> tuple[list[str], list[dict], np.ndarray | None]:
    """Returns (author_keys, feature_dicts, embedding_centroids)."""
    by_author: dict[str, list] = {}
    for c in comments:
        key = c.author_channel_id or f"anon:{c.comment_id}"
        by_author.setdefault(key, []).append(c)

    keys: list[str] = []
    features: list[dict] = []
    centroids: list[list[float] | None] = []

    for key, rows in by_author.items():
        n = len(rows)
        sentiments = [r.sentiment for r in rows]
        pos_share = sentiments.count("positive") / n
        neg_share = sentiments.count("negative") / n
        mixed_share = sentiments.count("mixed") / n
        uncertain_share = sentiments.count("uncertain") / n
        avg_score = sum(r.sentiment_score for r in rows) / n
        avg_likes = sum(r.like_count for r in rows) / n
        reply_share = sum(1 for r in rows if r.parent_id) / n

        intents = {k: 0 for k in ("price_inquiry", "discount_seeking", "availability_check",
                                  "delivery_concern", "purchase_intent", "support_complaint",
                                  "recommendation_request", "question_general")}
        languages: dict[str, int] = {}
        for r in rows:
            for ik, hit in (r.intents or {}).items():
                if hit and ik in intents:
                    intents[ik] += 1
            languages[r.language] = languages.get(r.language, 0) + 1
        intent_rates = {k: v / n for k, v in intents.items()}

        vecs = [r.embedding for r in rows if r.embedding]
        centroid = None
        if vecs:
            centroid = [round(float(x), 5) for x in np.mean(np.asarray(vecs), axis=0)]

        keys.append(key)
        features.append({
            "comment_count": n,
            "pos_share": round(pos_share, 3),
            "neg_share": round(neg_share, 3),
            "mixed_share": round(mixed_share, 3),
            "uncertain_share": round(uncertain_share, 3),
            "avg_score": round(avg_score, 3),
            "avg_likes": round(avg_likes, 2),
            "reply_share": round(reply_share, 3),
            **{f"intent_{k}": round(v, 3) for k, v in intent_rates.items()},
            "language_top": max(languages, key=lambda k: languages[k]) if languages else "unknown",
        })
        centroids.append(centroid)

    X = None
    if keys:
        scalar_names = [
            "comment_count", "pos_share", "neg_share", "mixed_share", "uncertain_share",
            "avg_score", "avg_likes", "reply_share",
        ] + [f"intent_{k}" for k in intents]
        scalar = np.asarray([[f[k] for k in scalar_names] for f in features], dtype=float)
        # log-compress volume, then standardize
        scalar[:, 0] = np.log1p(scalar[:, 0])
        scalar[:, 6] = np.log1p(scalar[:, 6])
        mean = scalar.mean(axis=0)
        std = np.where(scalar.std(axis=0) > 1e-9, scalar.std(axis=0), 1.0)
        scalar = (scalar - mean) / std

        emb_present = [i for i, c in enumerate(centroids) if c]
        if len(emb_present) >= 12:
            emb = np.zeros((len(keys), len(centroids[emb_present[0]])), dtype=float)
            for i in emb_present:
                emb[i] = np.asarray(centroids[i])
            emb_weight = 0.6
            X = np.hstack([scalar * (1.0 - emb_weight), emb * emb_weight])
        else:
            X = scalar

    return keys, features, X
