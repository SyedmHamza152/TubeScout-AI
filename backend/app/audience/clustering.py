"""Audience clustering: K-Means (silhouette-selected k) + DBSCAN noise pass.

Segments are analytical behaviour patterns inferred from public comments —
they are NOT verified demographic identities or confirmed customer categories.
All outputs carry the INFERENCE label.
"""
from __future__ import annotations

import logging

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.constants import LABEL_INFERENCE
from app.models.audience import AudienceCluster, ClusterMember
from app.models.research import Comment
from app.audience.features import build_author_features

logger = logging.getLogger(__name__)

SEGMENT_RULES: list[tuple[str, callable]] = [
    ("Price-sensitive audience", lambda p, v: p.get("intent_price_inquiry", 0) >= 0.25 or v is not None and False),
    ("Discount seekers", lambda p, v: p.get("intent_discount_seeking", 0) >= 0.15),
    ("Product researchers", lambda p, v: p.get("intent_recommendation_request", 0) >= 0.15
        or p.get("intent_question_general", 0) >= 0.3),
    ("Dissatisfied audience", lambda p, v: p.get("neg_share", 0) >= 0.4),
    ("Brand supporters", lambda p, v: p.get("pos_share", 0) >= 0.5 and p.get("neg_share", 0) < 0.15),
    ("Delivery-concerned shoppers", lambda p, v: p.get("intent_delivery_concern", 0) >= 0.15),
    ("Purchase-intent audience", lambda p, v: p.get("intent_purchase_intent", 0) >= 0.25),
    ("Support-complaint cluster", lambda p, v: p.get("intent_support_complaint", 0) >= 0.1),
]


def _label_cluster(profile: dict) -> str:
    for label, rule in SEGMENT_RULES:
        try:
            if rule(profile, None):
                return label
        except Exception:
            continue
    if profile.get("pos_share", 0) >= 0.35:
        return "Positive engagement audience"
    if profile.get("neg_share", 0) >= 0.3:
        return "Critical audience"
    if profile.get("intent_question_general", 0) >= 0.2:
        return "Information seekers"
    return "Mixed-interest audience"


def cluster_session(db: Session, workspace_id: str, session_id: str, min_authors: int = 12) -> dict:
    db.execute(delete(AudienceCluster).where(AudienceCluster.session_id == session_id))
    db.execute(delete(ClusterMember).where(
        ClusterMember.cluster_id.in_(
            select(AudienceCluster.id).where(AudienceCluster.session_id == session_id)
        )
    ))

    comments = db.execute(
        select(Comment).where(Comment.session_id == session_id, Comment.is_spam.is_(False))
    ).scalars().all()
    if len(comments) < min_authors * 2:
        return {"clusters": 0, "reason": "insufficient data to train clustering (need more comments)"}

    keys, features, X = build_author_features(comments)
    if X is None or len(keys) < min_authors:
        return {"clusters": 0, "reason": "insufficient data to train clustering (need more commenters)"}

    from sklearn.cluster import DBSCAN, KMeans
    from sklearn.metrics import silhouette_score

    n = len(keys)
    best_k, best_s = 0, -1.0
    max_k = min(8, max(2, n // 6))
    for k in range(2, max_k + 1):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X)
        if len(set(labels)) < 2:
            continue
        s = float(silhouette_score(X, labels, sample_size=min(800, n), random_state=42))
        if s > best_s:
            best_k, best_s = k, s
    if best_k == 0:
        return {"clusters": 0, "reason": "clustering produced no separable structure"}

    km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    labels = km.fit_predict(X).tolist()

    # DBSCAN noise pass (surfaces outliers as -1; used for anomaly context)
    db_labels = DBSCAN(eps=2.5, min_samples=4).fit_predict(X)
    noise_count = int(np.sum(db_labels == -1))

    method_note = (
        "K-Means on standardized behavioural features (sentiment shares, intent rates, "
        f"engagement, embeddings) with silhouette-selected k={best_k}; DBSCAN noise: {noise_count} authors."
    )

    created = 0
    for g in sorted(set(labels)):
        idx = [i for i, gg in enumerate(labels) if gg == g]
        if not idx:
            continue
        members_feat = [features[i] for i in idx]
        n_g = len(idx)
        profile = {
            "comment_count": sum(f["comment_count"] for f in members_feat),
            "pos_share": round(np.mean([f["pos_share"] for f in members_feat]), 3),
            "neg_share": round(np.mean([f["neg_share"] for f in members_feat]), 3),
            "mixed_share": round(np.mean([f["mixed_share"] for f in members_feat]), 3),
            "avg_score": round(np.mean([f["avg_score"] for f in members_feat]), 3),
            "avg_likes": round(np.mean([f["avg_likes"] for f in members_feat]), 2),
            "intent_price_inquiry": round(np.mean([f["intent_price_inquiry"] for f in members_feat]), 3),
            "intent_discount_seeking": round(np.mean([f["intent_discount_seeking"] for f in members_feat]), 3),
            "intent_availability_check": round(np.mean([f["intent_availability_check"] for f in members_feat]), 3),
            "intent_delivery_concern": round(np.mean([f["intent_delivery_concern"] for f in members_feat]), 3),
            "intent_purchase_intent": round(np.mean([f["intent_purchase_intent"] for f in members_feat]), 3),
            "intent_support_complaint": round(np.mean([f["intent_support_complaint"] for f in members_feat]), 3),
            "intent_recommendation_request": round(np.mean([f["intent_recommendation_request"] for f in members_feat]), 3),
            "intent_question_general": round(np.mean([f["intent_question_general"] for f in members_feat]), 3),
            "languages": sorted({f["language_top"] for f in members_feat}),
        }
        cluster = AudienceCluster(
            session_id=session_id,
            workspace_id=workspace_id,
            method="kmeans",
            k=best_k,
            silhouette=round(best_s, 3),
            cluster_index=int(g),
            label=_label_cluster(profile),
            size=n_g,
            profile=profile,
            interpretation="inference",
            data_label=LABEL_INFERENCE,
        )
        db.add(cluster)
        db.flush()
        for i in idx:
            db.add(ClusterMember(
                cluster_id=cluster.id,
                author_channel_id=keys[i] if not keys[i].startswith("anon:") else "",
                display_name="",
                comment_count=features[i]["comment_count"],
                features=features[i],
            ))
        created += 1
    db.commit()
    return {"clusters": created, "k": best_k, "silhouette": round(best_s, 3),
            "methodology": method_note, "authors": n}
