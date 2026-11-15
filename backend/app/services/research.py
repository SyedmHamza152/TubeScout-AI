"""Research execution service — the validated backend pipeline the agent calls.

Flow (mode=keyword): approved keywords → search.list (filters + pagination)
→ videos.list details → upsert videos/channels + stats snapshots →
commentThreads for selected videos → NLP pipeline → topics → clusters →
anomalies → findings. Every stage is quota-aware and records progress.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors import youtube as yt
from app.collectors.quota import QuotaExhausted, assert_budget, spend
from app.core.config import settings
from app.core.constants import LABEL_LIVE
from app.models.audience import AudienceCluster, AnomalyDetection, ClusterMember
from app.models.campaign import Finding
from app.models.research import (
    CollectionJob,
    Comment,
    ResearchKeyword,
    ResearchSession,
    TrackedChannel,
    TrackedVideo,
    VideoStatsSnapshot,
)
from app.nlp.aspect_packs import select_pack
from app.nlp.pipeline import process_comments
from app.nlp.relevance import product_tokens as build_product_tokens

logger = logging.getLogger(__name__)


class ResearchError(Exception):
    pass


# ---------------------------------------------------------------------------
# upserts
# ---------------------------------------------------------------------------
def upsert_channel(db: Session, workspace_id: str, details: dict, competitor: bool = False) -> TrackedChannel:
    row = db.execute(
        select(TrackedChannel).where(
            TrackedChannel.workspace_id == workspace_id,
            TrackedChannel.channel_id == details["channel_id"],
        )
    ).scalar_one_or_none()
    if row is None:
        row = TrackedChannel(workspace_id=workspace_id, channel_id=details["channel_id"])
        db.add(row)
    row.title = details.get("title") or row.title
    row.handle = details.get("handle") or row.handle
    row.description = details.get("description") or row.description
    row.country = details.get("country") or row.country
    row.subscribers = details.get("subscribers") or row.subscribers
    row.total_views = details.get("total_views") or row.total_views
    row.video_count = details.get("video_count") or row.video_count
    row.uploads_playlist_id = details.get("uploads_playlist_id") or row.uploads_playlist_id
    row.is_competitor = row.is_competitor or competitor
    row.stats = {k: v for k, v in details.items() if isinstance(v, (int, str, float))}
    row.last_synced_at = datetime.now(timezone.utc)
    row.data_label = LABEL_LIVE
    db.flush()
    return row


def upsert_video(db: Session, workspace_id: str, session_id: str | None, d: dict,
                 matched_keyword: str = "") -> TrackedVideo:
    row = db.execute(
        select(TrackedVideo).where(TrackedVideo.workspace_id == workspace_id,
                                   TrackedVideo.video_id == d["video_id"])
    ).scalar_one_or_none()
    published = yt._parse_ts(d.get("published_at"))
    if row is None:
        row = TrackedVideo(workspace_id=workspace_id, session_id=session_id, video_id=d["video_id"])
        db.add(row)
    elif session_id and row.session_id is None:
        row.session_id = session_id
    row.channel_id = d.get("channel_id") or row.channel_id
    row.channel_title = d.get("channel_title") or row.channel_title
    row.title = d.get("title") or row.title
    row.description = d.get("description") or row.description
    row.published_at = published or row.published_at
    row.duration_seconds = d.get("duration_seconds") or row.duration_seconds
    row.content_type = d.get("content_type") or row.content_type
    row.tags = d.get("tags") or row.tags
    row.views = d.get("views") or 0
    row.likes = d.get("likes") or 0
    row.comment_count = d.get("comments") or 0
    row.engagement_rate = d.get("engagement_rate") or 0.0
    if matched_keyword:
        row.matched_keyword = matched_keyword
    row.last_synced_at = datetime.now(timezone.utc)
    row.data_label = LABEL_LIVE
    db.flush()
    db.add(VideoStatsSnapshot(
        video_pk=row.id, views=row.views, likes=row.likes, comment_count=row.comment_count,
    ))
    return row


# ---------------------------------------------------------------------------
# execution
# ---------------------------------------------------------------------------
def execute_session(db: Session, workspace_id: str, session_id: str) -> None:
    """Full pipeline run. Called in a background thread with its own session."""
    session = db.get(ResearchSession, session_id)
    if session is None:
        raise ResearchError("session not found")
    job = CollectionJob(workspace_id=workspace_id, session_id=session_id, kind="keyword_search",
                        status="running", stage="starting")
    db.add(job)
    session.status, session.stage, session.progress = "collecting", "starting", 2
    session.error = None
    db.commit()

    stats: dict = {"videos_found": 0, "new_videos": 0, "comments_stored": 0,
                   "comments_duplicate": 0, "quota_spent": 0, "comments_disabled_videos": 0}
    try:
        config = session.config or {}
        max_videos = min(int(config.get("max_videos") or settings.DEFAULT_MAX_VIDEOS), settings.MAX_VIDEOS_HARD_CAP)
        per_video_comments = min(
            int(config.get("comments_per_video") or settings.DEFAULT_MAX_COMMENTS_PER_VIDEO),
            settings.MAX_COMMENTS_HARD_CAP // 2,
        )
        comment_cap = min(int(config.get("comment_total_cap") or settings.DEFAULT_COMMENT_TOTAL_CAP),
                          settings.MAX_COMMENTS_HARD_CAP)
        pack_key = select_pack(config)
        config["aspect_pack"] = pack_key

        # ---- 1. discover videos ------------------------------------------------
        video_details: dict[str, dict] = {}
        keywords = [kw.keyword for kw in db.execute(
            select(ResearchKeyword).where(
                ResearchKeyword.session_id == session_id, ResearchKeyword.approved.is_(True))
        ).scalars().all()]

        filters = {
            "region_code": config.get("country") or "",
            "relevance_language": config.get("language") or "",
            "published_after": _iso_dt(config.get("published_after")),
            "published_before": _iso_dt(config.get("published_before")),
            "video_duration": config.get("video_duration") or "",
            "video_category_id": config.get("video_category_id") or "",
            "order": config.get("order") or "relevance",
        }

        if session.mode == "channel":
            _collect_channel_videos(db, session, workspace_id, config, max_videos, video_details, stats, job)
        else:
            if not keywords:
                raise ResearchError("No approved keywords in the research plan.")
            per_kw = max(10, max_videos // max(1, len(keywords)))
            found = 0
            for ki, keyword in enumerate(keywords):
                assert_budget(db, workspace_id, 100)
                session.stage = f"searching: {keyword[:40]}"
                session.progress = 5 + int(20 * ki / max(1, len(keywords)))
                db.commit()
                seen_ids = set(video_details.keys())
                token = None
                pages = 0
                while found < max_videos and pages < 2:
                    items, token = yt.search_videos(keyword, limit=min(50, max_videos - found),
                                                    page_token=token, **filters)
                    spend(db, workspace_id, "search")
                    stats["quota_spent"] += 100
                    job.quota_spent = stats["quota_spent"]
                    pages += 1
                    for item in items:
                        if item["video_id"] in seen_ids:
                            continue
                        seen_ids.add(item["video_id"])
                        item["matched_query"] = keyword
                        video_details[item["video_id"]] = item
                        found += 1
                    if not token or found >= max_videos:
                        break
            stats["videos_found"] = found

        # ---- 2. hydrate details ------------------------------------------------
        ids = list(video_details.keys())
        if ids:
            session.stage = "fetching video details"
            session.progress = 30
            db.commit()
            assert_budget(db, workspace_id, max(1, len(ids) // 50) + 2)
            details = yt.get_video_details(ids)
            spend(db, workspace_id, "videos", cost=max(1, len(ids) // 50))
            stats["quota_spent"] += max(1, len(ids) // 50)
            by_id = {d["video_id"]: d for d in details}
            for vid, base in video_details.items():
                d = by_id.get(vid, base)
                d.setdefault("matched_query", base.get("matched_query", ""))
                row = upsert_video(db, workspace_id, session_id, d, d.get("matched_query", ""))
                stats["new_videos"] += 1
            channel_ids = [d.get("channel_id") for d in details if d.get("channel_id")]
            if channel_ids:
                ch_details = yt.get_channel_details(list(set(channel_ids)))
                spend(db, workspace_id, "channels", cost=max(1, len(set(channel_ids)) // 50))
                stats["quota_spent"] += max(1, len(set(channel_ids)) // 50)
                for cid, ch in ch_details.items():
                    upsert_channel(db, workspace_id, ch)
            db.commit()

        # ---- 3. comments -------------------------------------------------------
        video_rows = db.execute(
            select(TrackedVideo).where(
                TrackedVideo.workspace_id == workspace_id,
                TrackedVideo.session_id == session_id,
            ).order_by(TrackedVideo.comment_count.desc())
        ).scalars().all()
        target_videos = [v for v in video_rows if v.comment_count > 0][: max(1, comment_cap // per_video_comments + 1)]
        tokens = build_product_tokens(config.get("product", ""), config.get("description", "")) \
            if config.get("product") else set()
        comments_done = 0
        for vi, vrow in enumerate(target_videos):
            if comments_done >= comment_cap:
                break
            assert_budget(db, workspace_id, 1)
            session.stage = f"comments: {vrow.title[:40]}"
            session.progress = 35 + int(35 * vi / max(1, len(target_videos)))
            db.commit()
            want = min(per_video_comments, comment_cap - comments_done)
            comments, enabled = yt.collect_comments(vrow.video_id, max_comments=want)
            spend(db, workspace_id, "commentThreads")
            stats["quota_spent"] += 1
            if not enabled:
                stats["comments_disabled_videos"] += 1
            result = process_comments(
                db, workspace_id, session_id, vrow.id, vrow.video_id,
                comments, tokens, pack_key,
            )
            stats["comments_stored"] += result["stored"]
            stats["comments_duplicate"] += result["duplicates"]
            comments_done += result["stored"]
        job.kind = "comment_pull" if session.mode == "channel" else job.kind
        job.items_collected = stats["comments_stored"]
        job.quota_spent = stats["quota_spent"]

        # ---- 4. analytics ------------------------------------------------------
        session.stage = "topics & sentiment analytics"
        session.progress = 72
        db.commit()
        from app.analytics.sentiment_stats import build_session_stats
        from app.nlp.topics_service import build_topics

        build_topics(db, session_id)
        build_session_stats(db, session)

        session.stage = "audience clustering"
        session.progress = 82
        db.commit()
        from app.audience.clustering import cluster_session
        cluster_session(db, workspace_id, session_id)

        session.stage = "anomaly detection"
        session.progress = 88
        db.commit()
        from app.audience.anomalies import detect_session_anomalies
        detect_session_anomalies(db, workspace_id, session_id)

        session.stage = "findings"
        session.progress = 94
        db.commit()
        from app.analytics.findings import build_findings
        build_findings(db, workspace_id, session_id)

        session.stats = stats
        session.data_label = LABEL_LIVE
        session.status = "completed" if stats["comments_stored"] > 0 else "partial"
        if stats["videos_found"] == 0:
            session.status = "partial"
            session.error = "No videos matched the research keywords/filters."
        elif stats["comments_stored"] == 0:
            session.error = "No comments could be collected (disabled comments or quota limits)."
        session.progress = 100
        session.completed_at = datetime.now(timezone.utc)
        job.status = "completed"
        job.stage = "completed"
        job.progress = 100
        job.items_collected = stats["comments_stored"]
        db.commit()
    except QuotaExhausted as exc:
        session.status = "partial"
        session.error = str(exc)
        session.progress = min(session.progress, 95)
        session.completed_at = datetime.now(timezone.utc)
        job.status, job.error = "failed", str(exc)[:500]
        db.commit()
    except Exception as exc:
        logger.exception("research execution failed")
        job_id = job.id
        db.rollback()
        session = db.get(ResearchSession, session_id)
        job = db.get(CollectionJob, job_id)
        if session is not None:
            session.status = "failed"
            session.error = str(exc)[:800]
            session.completed_at = datetime.now(timezone.utc)
        if job is not None:
            job.status, job.error = "failed", str(exc)[:500]
        db.commit()
    finally:
        if job is not None:
            job.finished_at = datetime.now(timezone.utc)
            db.commit()


def _collect_channel_videos(db, session, workspace_id, config, max_videos, video_details, stats, job) -> None:
    channels = config.get("channels") or []
    if not channels:
        raise ResearchError("No channels provided for channel-based research.")
    found = 0
    for ci, channel_input in enumerate(channels):
        assert_budget(db, workspace_id, 2)
        session.stage = f"resolving channel: {str(channel_input)[:40]}"
        session.progress = 8 + int(15 * ci / max(1, len(channels)))
        db.commit()
        ch = yt.resolve_channel(str(channel_input))
        spend(db, workspace_id, "channels")
        stats["quota_spent"] += 1
        if not ch.get("channel_id"):
            continue
        upsert_channel(db, workspace_id, ch, competitor=config.get("mark_competitor", False))
        playlist = ch.get("uploads_playlist_id")
        if not playlist:
            continue
        assert_budget(db, workspace_id, 1)
        items = yt.get_playlist_items(playlist, limit=max_videos)
        spend(db, workspace_id, "playlistItems")
        stats["quota_spent"] += 1
        for item in items:
            if found >= max_videos:
                break
            if item["video_id"] in video_details:
                continue
            video_details[item["video_id"]] = item
            found += 1
    stats["videos_found"] = found


def refresh_workspace_videos(db: Session, limit_per_workspace: int = 200) -> int:
    """Periodic refresh: snapshot current public stats for tracked videos."""
    from app.core.db import SessionLocal as _SL  # noqa: F401 (kept for scheduler clarity)

    updated = 0
    workspaces = db.execute(select(TrackedVideo.workspace_id).distinct()).scalars().all()
    for ws in workspaces:
        rows = db.execute(
            select(TrackedVideo).where(TrackedVideo.workspace_id == ws)
            .order_by(TrackedVideo.last_synced_at.asc().nullsfirst())
            .limit(limit_per_workspace)
        ).scalars().all()
        if not rows:
            continue
        ids = [r.video_id for r in rows]
        try:
            details = yt.get_video_details(ids)
            spend(db, ws, "videos", cost=max(1, len(ids) // 50))
            by_id = {d["video_id"]: d for d in details}
            for row in rows:
                d = by_id.get(row.video_id)
                if not d:
                    continue
                row.views = d["views"]
                row.likes = d["likes"]
                row.comment_count = d["comments"]
                row.engagement_rate = d["engagement_rate"]
                row.last_synced_at = datetime.now(timezone.utc)
                db.add(VideoStatsSnapshot(video_pk=row.id, views=row.views, likes=row.likes,
                                          comment_count=row.comment_count))
                updated += 1
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("refresh failed for workspace %s", ws)
    return updated


def _iso_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
