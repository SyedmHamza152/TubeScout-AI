"""Anomaly detection on audience/engagement patterns.

Methods (explained per detection, with baselines and evidence):
  - engagement_rate z-score vs session baseline (robust median/MAD)
  - comment-volume z-score vs channel's own videos in the session
  - negative-sentiment spike (binomial z vs pooled negative rate)
  - IsolationForest multivariate check when enough videos exist
All anomalies are statistical flags for investigation, not verdicts.
"""
from __future__ import annotations

import logging
import math

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.constants import LABEL_LIVE
from app.models.audience import AnomalyDetection
from app.models.research import Comment, TrackedVideo

logger = logging.getLogger(__name__)


def _robust_z(values: np.ndarray, x: float) -> float:
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median))) or 1e-9
    return 0.6745 * (x - median) / mad


def _severity(score: float) -> str:
    a = abs(score)
    if a >= 3.5:
        return "high"
    if a >= 2.5:
        return "medium"
    return "low"


def detect_session_anomalies(db: Session, workspace_id: str, session_id: str) -> dict:
    db.execute(delete(AnomalyDetection).where(AnomalyDetection.session_id == session_id))
    videos = db.execute(
        select(TrackedVideo).where(TrackedVideo.session_id == session_id)
    ).scalars().all()
    comments = db.execute(
        select(Comment).where(Comment.session_id == session_id, Comment.is_spam.is_(False))
    ).scalars().all()

    if len(videos) < 5:
        return {"anomalies": 0, "reason": "fewer than 5 videos — baselines not reliable"}

    created = 0
    eng_values = np.asarray([v.engagement_rate for v in videos if v.views > 0])
    cmt_values = np.asarray([v.comment_count for v in videos])
    view_values = np.asarray([v.views for v in videos]).astype(float)

    by_video_comments: dict[int, list[Comment]] = {}
    for c in comments:
        by_video_comments.setdefault(c.video_pk, []).append(c)

    neg_total = sum(1 for c in comments if c.sentiment == "negative")
    p_pool = neg_total / max(1, len(comments))

    detections: list[AnomalyDetection] = []

    for v in videos:
        if v.views > 0 and len(eng_values) >= 5:
            z = _robust_z(eng_values, v.engagement_rate)
            if abs(z) >= 2.5:
                detections.append(AnomalyDetection(
                    session_id=session_id, workspace_id=workspace_id,
                    kind="engagement_rate", entity_type="video", entity_id=v.video_id,
                    entity_title=v.title[:400],
                    score=round(float(z), 2), severity=_severity(z),
                    baseline={"median_engagement": round(float(np.median(eng_values)), 5),
                              "videos_compared": int(len(eng_values))},
                    observed={"engagement_rate": round(v.engagement_rate, 5),
                              "views": v.views, "likes": v.likes, "comments": v.comment_count,
                              "channel": v.channel_title},
                    explanation=(
                        f"Engagement rate {v.engagement_rate:.4f} is {z:+.1f} robust z-scores vs the "
                        f"median ({np.median(eng_values):.4f}) of {len(eng_values)} comparable videos in "
                        f"this research. {'Unusually high' if z > 0 else 'Unusually low'} engagement — "
                        "investigate content, title/thumbnail, or audience match."
                    ),
                    evidence=[{"type": "video", "url": f"https://www.youtube.com/watch?v={v.video_id}",
                               "title": v.title}],
                    data_label=LABEL_LIVE,
                ))

        if len(cmt_values) >= 5 and v.comment_count > 0:
            z = _robust_z(cmt_values, v.comment_count)
            if abs(z) >= 2.5:
                detections.append(AnomalyDetection(
                    session_id=session_id, workspace_id=workspace_id,
                    kind="comment_volume", entity_type="video", entity_id=v.video_id,
                    entity_title=v.title[:400],
                    score=round(float(z), 2), severity=_severity(z),
                    baseline={"median_comments": float(np.median(cmt_values)),
                              "videos_compared": int(len(cmt_values))},
                    observed={"comment_count": v.comment_count, "views": v.views},
                    explanation=(
                        f"Comment count {v.comment_count} is {z:+.1f} robust z-scores vs the median "
                        f"({int(np.median(cmt_values))}) across comparable videos. "
                        "Comment-volume spikes often signal discussion, controversy or reach — review the comments."
                    ),
                    evidence=[{"type": "video", "url": f"https://www.youtube.com/watch?v={v.video_id}",
                               "title": v.title}],
                    data_label=LABEL_LIVE,
                ))

        members = by_video_comments.get(v.id, [])
        if len(members) >= 15 and len(comments) >= 40:
            n_neg = sum(1 for c in members if c.sentiment == "negative")
            p_hat = n_neg / len(members)
            se = math.sqrt(max(p_pool * (1 - p_pool), 1e-6) / len(members))
            z = (p_hat - p_pool) / se
            if abs(z) >= 2.5 and n_neg > 0:
                neg_examples = sorted(
                    [c for c in members if c.sentiment == "negative"], key=lambda c: -c.like_count
                )[:3]
                detections.append(AnomalyDetection(
                    session_id=session_id, workspace_id=workspace_id,
                    kind="negative_spike", entity_type="video", entity_id=v.video_id,
                    entity_title=v.title[:400],
                    score=round(float(z), 2), severity=_severity(z),
                    baseline={"pooled_negative_share": round(p_pool, 3),
                              "comments_sampled": len(members)},
                    observed={"negative_share": round(p_hat, 3), "negative_count": n_neg},
                    explanation=(
                        f"Negative comments are {p_hat * 100:.0f}% on this video vs "
                        f"{p_pool * 100:.0f}% pooled ({z:+.1f} binomial z). A negative-feedback spike "
                        "— check what changed (content, product mention, reception)."
                    ),
                    evidence=[
                        {"type": "comment", "text": c.text_original[:200],
                         "url": c.source_url, "likes": c.like_count}
                        for c in neg_examples
                    ],
                    data_label=LABEL_LIVE,
                ))

    # Isolation Forest multivariate pass
    if len(videos) >= 15:
        try:
            from sklearn.ensemble import IsolationForest

            feats, vrows = [], []
            for v in videos:
                if v.views <= 0:
                    continue
                feats.append([
                    math.log1p(v.views), math.log1p(v.likes), math.log1p(v.comment_count),
                    v.engagement_rate,
                ])
                vrows.append(v)
            if len(feats) >= 12:
                iso = IsolationForest(contamination=0.12, random_state=42)
                preds = iso.fit_predict(np.asarray(feats))
                scores = iso.score_samples(np.asarray(feats))
                for v, p, s in zip(vrows, preds, scores):
                    if p == -1:
                        detections.append(AnomalyDetection(
                            session_id=session_id, workspace_id=workspace_id,
                            kind="isolation_forest", entity_type="video", entity_id=v.video_id,
                            entity_title=v.title[:400],
                            score=round(float(-s), 3), severity="medium",
                            baseline={"method": "IsolationForest on log views/likes/comments + engagement",
                                      "contamination": 0.12},
                            observed={"views": v.views, "likes": v.likes,
                                      "comments": v.comment_count,
                                      "engagement_rate": round(v.engagement_rate, 5)},
                            explanation=(
                                "Multivariate outlier vs the session's video population "
                                "(views/likes/comments/engagement jointly unusual). "
                                "Worth manual review before drawing conclusions."
                            ),
                            evidence=[{"type": "video", "url": f"https://www.youtube.com/watch?v={v.video_id}",
                                       "title": v.title}],
                            data_label=LABEL_LIVE,
                        ))
        except Exception:
            logger.exception("isolation forest pass failed")

    for d in detections:
        db.add(d)
        created += 1
    db.commit()
    return {"anomalies": created, "videos": len(videos)}
