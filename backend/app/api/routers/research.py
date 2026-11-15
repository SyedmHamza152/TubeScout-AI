"""Research sessions, videos, comments and analytics endpoints."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.sentiment_stats import aspect_summary, session_summary
from app.core.deps import get_current_user, get_workspace
from app.core.db import get_db
from app.core.constants import QUOTA_COST
from app.collectors import youtube as yt
from app.collectors.quota import assert_budget, status as quota_status, spend
from app.jobs.runner import is_running, submit
from app.models.identity import User, Workspace
from app.models.research import (
    CollectionJob,
    Comment,
    ResearchKeyword,
    ResearchSession,
    TopicRecord,
    TrackedVideo,
    VideoStatsSnapshot,
)
from app.services.research import execute_session, refresh_workspace_videos

router = APIRouter(prefix="/research", tags=["research"])


def _own_session(db: Session, ws_id: str, session_id: str) -> ResearchSession:
    s = db.get(ResearchSession, session_id)
    if s is None or s.workspace_id != ws_id:
        raise HTTPException(404, "Research session not found.")
    return s


class ManualSessionBody(BaseModel):
    title: str = Field(default="YouTube research", max_length=300)
    product: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=1000)
    keywords: list[str] = Field(default_factory=list, max_length=8)
    channels: list[str] = Field(default_factory=list, max_length=8)
    mode: str = Field(default="keyword", max_length=12)
    country: str = Field(default="PK", max_length=8)
    language: str = Field(default="", max_length=8)
    published_after_days: int = Field(default=90, ge=1, le=3650)
    max_videos: int = Field(default=40, ge=5, le=200)
    comments_per_video: int = Field(default=60, ge=10, le=500)
    comment_total_cap: int = Field(default=2000, ge=50, le=10000)
    aspect_pack: str = Field(default="", max_length=30)
    research_intent: str = Field(default="campaign", max_length=30)


@router.post("/sessions", status_code=201)
def create_session(body: ManualSessionBody, user: User = Depends(get_current_user),
                   ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    """Direct manual research configuration (user-controlled; agent uses /agent)."""
    from datetime import datetime, timedelta, timezone as _tz

    if not yt.is_configured():
        raise HTTPException(503, "YOUTUBE_API_KEY is not configured — live collection is unavailable.")
    mode = body.mode if body.mode in ("keyword", "channel") else "keyword"
    if mode == "keyword" and not body.keywords:
        raise HTTPException(422, "At least one keyword is required for keyword research.")
    if mode == "channel" and not body.channels:
        raise HTTPException(422, "At least one channel is required for channel research.")
    aspect_pack = body.aspect_pack if body.aspect_pack in ("product", "youtube_content") else (
        "youtube_content" if body.research_intent == "content" else "product")
    channels = [c.strip()[:120] for c in body.channels if c.strip()][:3] if mode == "channel" else []
    session = ResearchSession(
        workspace_id=ws.id, created_by=user.id, title=body.title[:300], mode=mode,
        status="queued", config={
            "product": body.product.strip(), "description": body.description.strip(),
            "country": body.country.upper(), "language": body.language,
            "research_intent": body.research_intent, "aspect_pack": aspect_pack,
            "published_after": (datetime.now(_tz.utc) - timedelta(days=body.published_after_days))
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "video_duration": "any", "order": "relevance",
            "max_videos": body.max_videos, "comments_per_video": body.comments_per_video,
            "comment_total_cap": body.comment_total_cap, "channels": channels,
            "mode": mode,
        },
    )
    db.add(session)
    db.flush()
    for kw in body.keywords:
        db.add(ResearchKeyword(session_id=session.id, keyword=kw[:300], source="user"))
    db.commit()
    db.refresh(session)
    key = f"session_{session.id}"
    if not is_running(key):
        submit(key, _run_job, session.id, ws.id)
    return {"id": session.id, "title": session.title, "status": session.status, "queued": True}


@router.get("/sessions")
def list_sessions(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                  db: Session = Depends(get_db)):
    rows = db.execute(
        select(ResearchSession).where(ResearchSession.workspace_id == ws.id)
        .order_by(ResearchSession.created_at.desc()).limit(100)
    ).scalars().all()
    return {"sessions": [{
        "id": s.id, "title": s.title, "mode": s.mode, "status": s.status, "stage": s.stage,
        "progress": s.progress, "stats": s.stats, "error": s.error,
        "data_label": s.data_label, "created_at": str(s.created_at),
        "completed_at": str(s.completed_at) if s.completed_at else None,
        "running": is_running(f"session_{s.id}"),
    } for s in rows]}


@router.get("/sessions/{session_id}")
def session_detail(session_id: str, user: User = Depends(get_current_user),
                   ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    s = _own_session(db, ws.id, session_id)
    return {
        "id": s.id, "title": s.title, "mode": s.mode, "status": s.status, "stage": s.stage,
        "progress": s.progress, "config": s.config, "stats": s.stats, "error": s.error,
        "data_label": s.data_label, "created_at": str(s.created_at),
        "completed_at": str(s.completed_at) if s.completed_at else None,
        "running": is_running(f"session_{s.id}"),
    }


@router.post("/sessions/{session_id}/rerun")
def rerun(session_id: str, parts: str = Query(default="topics,summary,clusters,anomalies,findings"),
          user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
          db: Session = Depends(get_db)):
    s = _own_session(db, ws.id, session_id)
    if s.status not in ("completed", "partial"):
        raise HTTPException(400, "Session has not completed collection yet.")
    from app.agent.tools import rerun_analytics

    return rerun_analytics(db, ws.id, session_id, [p.strip() for p in parts.split(",") if p.strip()])


@router.get("/sessions/{session_id}/analytics")
def analytics(session_id: str, user: User = Depends(get_current_user),
              ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    s = _own_session(db, ws.id, session_id)
    summary = session_summary(db, s)
    aspects = aspect_summary(db, s, (s.config or {}).get("aspect_pack", "product"))
    topics = db.execute(
        select(TopicRecord).where(TopicRecord.session_id == session_id)
        .order_by(TopicRecord.comment_count.desc())
    ).scalars().all()
    return {
        "session": {"id": s.id, "title": s.title, "status": s.status},
        "summary": summary,
        "aspects": aspects,
        "topics": [{"topic_key": t.topic_key, "label": t.label, "keywords": t.keywords,
                    "comment_count": t.comment_count, "share": t.share,
                    "sentiment_mix": t.sentiment_mix} for t in topics],
    }


@router.get("/sessions/{session_id}/videos")
def session_videos(session_id: str, limit: int = 100, offset: int = 0,
                   user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                   db: Session = Depends(get_db)):
    s = _own_session(db, ws.id, session_id)
    rows = db.execute(
        select(TrackedVideo).where(TrackedVideo.session_id == session_id)
        .order_by(TrackedVideo.views.desc()).offset(offset).limit(min(limit, 500))
    ).scalars().all()
    total = db.execute(
        select(func.count()).select_from(TrackedVideo).where(TrackedVideo.session_id == session_id)
    ).scalar()
    return {"total": total, "videos": [{
        "video_id": v.video_id, "title": v.title, "channel_title": v.channel_title,
        "channel_id": v.channel_id, "published_at": str(v.published_at) if v.published_at else None,
        "duration_seconds": v.duration_seconds, "content_type": v.content_type,
        "views": v.views, "likes": v.likes, "comment_count": v.comment_count,
        "engagement_rate": v.engagement_rate, "matched_keyword": v.matched_keyword,
        "url": f"https://www.youtube.com/watch?v={v.video_id}", "data_label": v.data_label,
    } for v in rows]}


@router.get("/sessions/{session_id}/comments")
def session_comments(session_id: str, video_id: str | None = None, sentiment: str | None = None,
                     intent: str | None = None, language: str | None = None,
                     search: str | None = None, limit: int = 100, offset: int = 0,
                     user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                     db: Session = Depends(get_db)):
    _own_session(db, ws.id, session_id)
    q = select(Comment).where(Comment.session_id == session_id)
    if video_id:
        q = q.where(Comment.video_id == video_id)
    if sentiment:
        q = q.where(Comment.sentiment == sentiment)
    if language:
        q = q.where(Comment.language == language)
    if search:
        q = q.where(Comment.text_original.ilike(f"%{search[:80]}%"))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    rows = db.execute(q.order_by(Comment.like_count.desc()).offset(offset).limit(min(limit, 300))).scalars().all()
    items = [{
        "comment_id": c.comment_id, "video_id": c.video_id, "author": c.author_display_name,
        "text": c.text_original, "translation": c.translation,
        "language": c.language, "sentiment": c.sentiment, "sentiment_score": c.sentiment_score,
        "sentiment_confidence": c.sentiment_confidence, "sarcasm_suspect": c.sarcasm_suspect,
        "intents": c.intents, "like_count": c.like_count, "reply_count": c.reply_count,
        "published_at": str(c.published_at) if c.published_at else None,
        "url": c.source_url, "is_spam": c.is_spam, "data_label": c.data_label,
    } for c in rows]
    if intent:
        items = [i for i in items if (i["intents"] or {}).get(intent)]
    return {"total": total, "comments": items}


@router.get("/sessions/{session_id}/export.csv")
def export_csv(session_id: str, user: User = Depends(get_current_user),
               ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    _own_session(db, ws.id, session_id)
    rows = db.execute(
        select(Comment).where(Comment.session_id == session_id).order_by(Comment.id.asc()).limit(50000)
    ).scalars().all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["comment_id", "video_id", "author", "language", "sentiment", "sentiment_score",
                     "sentiment_confidence", "purchase_intent", "text_original", "like_count",
                     "published_at", "source_url", "data_label"])
    for c in rows:
        writer.writerow([c.comment_id, c.video_id, c.author_display_name, c.language, c.sentiment,
                         c.sentiment_score, c.sentiment_confidence,
                         (c.intents or {}).get("purchase_intent", False), c.text_original,
                         c.like_count, str(c.published_at or ""), c.source_url or "", c.data_label])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=comments_{session_id[:8]}.csv"})


@router.post("/sessions/{session_id}/run")
def run_session(session_id: str, user: User = Depends(get_current_user),
                ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    """(Re)execute collection for an existing session."""
    s = _own_session(db, ws.id, session_id)
    if not yt.is_configured():
        raise HTTPException(503, "YOUTUBE_API_KEY is not configured — live collection is unavailable.")
    key = f"session_{session_id}"
    if is_running(key):
        return {"ok": True, "status": "already_running"}
    submit(key, _run_job, session_id, ws.id)
    return {"ok": True, "session_id": session_id, "status": "queued"}


def _run_job(session_id: str, workspace_id: str) -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        execute_session(db, workspace_id, session_id)


@router.post("/sessions/{session_id}/refresh")
def refresh_session(session_id: str, user: User = Depends(get_current_user),
                    ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    """Snapshot fresh public stats for this session's videos (periodic polling)."""
    s = _own_session(db, ws.id, session_id)
    if not yt.is_configured():
        raise HTTPException(503, "YOUTUBE_API_KEY is not configured.")
    rows = db.execute(select(TrackedVideo).where(TrackedVideo.session_id == session_id)).scalars().all()
    ids = [v.video_id for v in rows][:200]
    if not ids:
        return {"ok": False, "error": "no videos to refresh"}
    assert_budget(db, ws.id, max(1, len(ids) // 50))
    details = yt.get_video_details(ids)
    spend(db, ws.id, "videos", cost=max(1, len(ids) // 50))
    by_id = {d["video_id"]: d for d in details}
    updated = 0
    for row in rows:
        d = by_id.get(row.video_id)
        if not d:
            continue
        db.add(VideoStatsSnapshot(video_pk=row.id, views=d["views"], likes=d["likes"],
                                  comment_count=d["comments"]))
        row.views, row.likes, row.comment_count = d["views"], d["likes"], d["comments"]
        row.engagement_rate = d["engagement_rate"]
        updated += 1
    db.commit()
    return {"ok": True, "updated": updated, "data_label": "LIVE DATA"}


@router.get("/videos/{video_id}/snapshots")
def video_snapshots(video_id: str, user: User = Depends(get_current_user),
                    ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    v = db.execute(
        select(TrackedVideo).where(TrackedVideo.workspace_id == ws.id, TrackedVideo.video_id == video_id)
    ).scalar_one_or_none()
    if v is None:
        raise HTTPException(404, "Video not tracked in this workspace.")
    snaps = db.execute(
        select(VideoStatsSnapshot).where(VideoStatsSnapshot.video_pk == v.id)
        .order_by(VideoStatsSnapshot.captured_at.asc()).limit(500)
    ).scalars().all()
    return {"video": {"video_id": v.video_id, "title": v.title, "views": v.views,
                      "likes": v.likes, "comment_count": v.comment_count},
            "snapshots": [{"captured_at": str(s.captured_at), "views": s.views,
                           "likes": s.likes, "comment_count": s.comment_count} for s in snaps]}


@router.get("/quota")
def quota(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
          db: Session = Depends(get_db)):
    return quota_status(db, ws.id)


@router.get("/collection-jobs")
def collection_jobs(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                    db: Session = Depends(get_db)):
    rows = db.execute(
        select(CollectionJob).where(CollectionJob.workspace_id == ws.id)
        .order_by(CollectionJob.started_at.desc()).limit(50)
    ).scalars().all()
    return {"jobs": [{"id": j.id, "session_id": j.session_id, "kind": j.kind, "status": j.status,
                      "stage": j.stage, "progress": j.progress, "quota_spent": j.quota_spent,
                      "items_collected": j.items_collected, "error": j.error,
                      "started_at": str(j.started_at)} for j in rows]}
