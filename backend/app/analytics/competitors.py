"""Competitor & market intelligence.

Channel-level comparisons built from PUBLIC YouTube data only (activity,
cadence, formats, engagement, audience sentiment of collected comments,
topics). No private analytics — competitor ad spend/conversions are never
claimed or shown.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import LABEL_LIVE
from app.models.research import Comment, TrackedChannel, TrackedVideo


def _days_since(dt: datetime | None) -> float | None:
    if not dt:
        return None
    return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 86400


def channel_profile(videos: list[TrackedVideo], comments: list[Comment]) -> dict:
    views = [v.views for v in videos if v.views > 0]
    eng = [v.engagement_rate for v in videos if v.views > 0]
    shorts = [v for v in videos if v.content_type == "short"]
    published = [v.published_at for v in videos if v.published_at]
    cadence = 0.0
    if len(published) >= 2:
        span_days = (max(published) - min(published).astimezone(published[0].tzinfo)).days or 1
        cadence = round(len(videos) / max(1, span_days) * 7, 2)

    v_ids = {v.id for v in videos}
    c_rows = [c for c in comments if c.video_pk in v_ids]
    n = len(c_rows)
    neg = sum(1 for c in c_rows if c.sentiment == "negative")
    pos = sum(1 for c in c_rows if c.sentiment == "positive")

    return {
        "channel_id": videos[0].channel_id if videos else "",
        "channel_title": videos[0].channel_title if videos else "",
        "videos_in_research": len(videos),
        "median_views": float(np.median(views)) if views else 0,
        "avg_engagement_rate": round(float(np.mean(eng)), 5) if eng else 0.0,
        "shorts_share": round(len(shorts) / len(videos), 2) if videos else 0.0,
        "upload_cadence_per_week": cadence,
        "comments_collected": n,
        "negative_pct": round(100 * neg / n, 1) if n else 0.0,
        "positive_pct": round(100 * pos / n, 1) if n else 0.0,
        "data_label": LABEL_LIVE,
    }


def compare_workspace_channels(db: Session, workspace_id: str, session_id: str | None = None) -> dict:
    video_q = select(TrackedVideo).where(TrackedVideo.workspace_id == workspace_id)
    if session_id:
        video_q = video_q.where(TrackedVideo.session_id == session_id)
    videos = db.execute(video_q).scalars().all()
    comment_q = select(Comment).where(
        Comment.workspace_id == workspace_id, Comment.is_spam.is_(False)
    )
    if session_id:
        comment_q = comment_q.where(Comment.session_id == session_id)
    comments = db.execute(comment_q).scalars().all()

    by_channel: dict[str, list[TrackedVideo]] = defaultdict(list)
    for v in videos:
        by_channel[v.channel_id].append(v)
    profiles = []
    for cid, vids in by_channel.items():
        if len(vids) >= 1:
            profiles.append(channel_profile(vids, comments))
    profiles.sort(key=lambda p: -(p["median_views"] or 0))
    return {"channels": profiles, "data_label": LABEL_LIVE}


def content_gaps(db: Session, workspace_id: str, session_id: str, target_channel: str) -> dict:
    """Topics covered by comparable channels but missing from the target."""
    videos = db.execute(
        select(TrackedVideo).where(TrackedVideo.workspace_id == workspace_id)
    ).scalars().all()
    target_videos = [v for v in videos if v.channel_title and target_channel.lower() in v.channel_title.lower()]
    other_videos = [v for v in videos if v not in target_videos]
    if not target_videos or not other_videos:
        return {"gaps": [], "reason": "need both a target channel and comparison channels"}

    def tags_of(rows: list[TrackedVideo]) -> set[str]:
        out: set[str] = set()
        for v in rows:
            for t in (v.tags or []):
                t = (t or "").lower().strip()
                if 3 <= len(t) <= 40:
                    out.add(t)
        return out

    target_tags = tags_of(target_videos)
    other_tags = tags_of(other_videos)
    missing = [
        {"tag": t, "coverage": sum(1 for v in other_videos if t in [x.lower() for x in (v.tags or [])])}
        for t in other_tags - target_tags
    ]
    missing.sort(key=lambda m: -m["coverage"])
    return {"gaps": missing[:15], "target": target_channel, "data_label": LABEL_LIVE}
