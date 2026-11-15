"""Topic building service: cluster a session's comments into topics."""
from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.research import Comment, TopicRecord
from app.nlp.topics import choose_k, label_for_terms, top_terms_per_group

logger = logging.getLogger(__name__)


def build_topics(db: Session, session_id: str) -> dict:
    """Cluster session comments (by embeddings) into discussion topics."""
    db.execute(delete(TopicRecord).where(TopicRecord.session_id == session_id))
    rows = db.execute(
        select(Comment).where(
            Comment.session_id == session_id,
            Comment.is_spam.is_(False),
            Comment.embedding.isnot(None),
        )
    ).scalars().all()
    if len(rows) < 12:
        return {"topics": 0, "reason": "insufficient comments for topic clustering"}

    embeddings = [r.embedding for r in rows]
    k = choose_k(embeddings, min_k=2, max_k=6)
    if k == 0:
        return {"topics": 0, "reason": "insufficient comments for topic clustering"}

    import numpy as np
    from sklearn.cluster import MiniBatchKMeans

    X = np.asarray(embeddings)
    km = MiniBatchKMeans(n_clusters=k, random_state=42, batch_size=64, n_init=10)
    labels = km.fit_predict(X).tolist()

    docs = [r.text_normalized or r.text_original for r in rows]
    terms_by_group = top_terms_per_group(docs, labels, n_terms=8)
    total = len(rows)
    created = 0
    for g in sorted(set(labels)):
        idx = [i for i, gg in enumerate(labels) if gg == g]
        if not idx:
            continue
        members = [rows[i] for i in idx]
        mix = {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0, "uncertain": 0}
        for m in members:
            mix[m.sentiment] = mix.get(m.sentiment, 0) + 1
        terms = terms_by_group.get(g, [])
        db.add(TopicRecord(
            session_id=session_id,
            topic_key=f"topic_{g}",
            label=label_for_terms(terms),
            keywords=terms,
            comment_count=len(members),
            share=round(len(members) / total, 4),
            sentiment_mix=mix,
        ))
        created += 1
    db.commit()
    return {"topics": created, "comments": total}
