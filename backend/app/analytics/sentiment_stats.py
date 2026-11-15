"""Sentiment analytics: distributions, trends, per-video/channel/language/aspect
breakdowns, representative comments. Percentages represent the COLLECTED
SAMPLE only — never the entire YouTube audience."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import LABEL_LIVE
from app.models.research import AspectSentiment, Comment, ResearchSession, TrackedVideo
from app.nlp.aspect_packs import PACK_LABELS, get_pack


def _pct(n: int, total: int) -> float:
    return round(100.0 * n / total, 1) if total else 0.0


def _mix(rows: list[Comment]) -> dict:
    counts = defaultdict(int)
    for r in rows:
        counts[r.sentiment] += 1
    total = len(rows)
    return {
        "total": total,
        "positive_pct": _pct(counts["positive"], total),
        "negative_pct": _pct(counts["negative"], total),
        "neutral_pct": _pct(counts["neutral"], total),
        "mixed_pct": _pct(counts["mixed"], total),
        "uncertain_pct": _pct(counts["uncertain"], total),
        "counts": dict(counts),
        "avg_score": round(sum(r.sentiment_score for r in rows) / total, 3) if total else 0.0,
    }


def build_session_stats(db: Session, session: ResearchSession) -> dict:
    """Compute and cache a compact analytics summary on the session row."""
    rows = db.execute(
        select(Comment).where(
            Comment.session_id == session.id, Comment.is_spam.is_(False)
        )
    ).scalars().all()
    videos = db.execute(
        select(TrackedVideo).where(TrackedVideo.session_id == session.id)
    ).scalars().all()

    summary: dict = {
        "sentiment_overall": _mix(rows),
        "languages": _language_mix(rows),
        "intents": _intent_mix(rows),
        "videos": _video_mix(rows, videos),
        "trend": _trend(rows),
        "representative": _representative(rows, videos),
        "sample_disclaimer": (
            "All percentages describe the collected sample of public comments, "
            "not the entire YouTube audience."
        ),
        "data_label": LABEL_LIVE,
    }
    session.stats = {**(session.stats or {}), "analytics": summary}
    db.commit()
    return summary


def session_summary(db: Session, session: ResearchSession) -> dict:
    cached = (session.stats or {}).get("analytics")
    if cached:
        return cached
    return build_session_stats(db, session)


def aspect_summary(db: Session, session: ResearchSession, pack_key: str) -> dict:
    """Aspect-wise sentiment for the session's active pack."""
    pack = get_pack(pack_key)
    rows = db.execute(
        select(AspectSentiment).where(
            AspectSentiment.session_id == session.id,
            AspectSentiment.pack == pack_key,
        )
    ).scalars().all()
    by_aspect: dict[str, dict] = {}
    for r in rows:
        slot = by_aspect.setdefault(r.aspect, {"positive": 0, "negative": 0, "neutral": 0})
        slot[r.label] = slot.get(r.label, 0) + 1
    out = []
    for key, counts in sorted(by_aspect.items(), key=lambda kv: -sum(kv[1].values())):
        total = sum(counts.values())
        out.append({
            "aspect": key,
            "label": pack[key]["label"] if key in pack else key,
            "scope": pack[key]["scope"] if key in pack else "",
            "mentions": total,
            "positive_pct": _pct(counts.get("positive", 0), total),
            "negative_pct": _pct(counts.get("negative", 0), total),
            "neutral_pct": _pct(counts.get("neutral", 0), total),
        })
    return {"pack": pack_key, "pack_label": PACK_LABELS.get(pack_key, pack_key), "aspects": out}


def _language_mix(rows: list[Comment]) -> list[dict]:
    by_lang: dict[str, list[Comment]] = defaultdict(list)
    for r in rows:
        by_lang[r.language].append(r)
    return [
        {"language": lang, **_mix(members)}
        for lang, members in sorted(by_lang.items(), key=lambda kv: -len(kv[1]))
    ]


def _intent_mix(rows: list[Comment]) -> dict:
    totals: dict[str, int] = defaultdict(int)
    names = {
        "price_inquiry": "Price inquiry", "discount_seeking": "Discount seeking",
        "availability_check": "Availability check", "delivery_concern": "Delivery concern",
        "purchase_intent": "Purchase-intent signal", "support_complaint": "Support complaint",
        "recommendation_request": "Recommendation request", "question_general": "General question",
    }
    for r in rows:
        for key, hit in (r.intents or {}).items():
            if hit and key in names:
                totals[key] += 1
    total = len(rows) or 1
    return [
        {"intent": key, "label": names[key], "count": n, "share_pct": _pct(n, total)}
        for key, n in sorted(totals.items(), key=lambda kv: -kv[1])
    ]


def _video_mix(rows: list[Comment], videos: list[TrackedVideo]) -> list[dict]:
    by_video: dict[int, list[Comment]] = defaultdict(list)
    for r in rows:
        by_video[r.video_pk].append(r)
    vmeta = {v.id: v for v in videos}
    out = []
    for vpk, members in sorted(by_video.items(), key=lambda kv: -len(kv[1]))[:50]:
        v = vmeta.get(vpk)
        out.append({
            "video_pk": vpk,
            "video_id": v.video_id if v else "",
            "title": v.title if v else "",
            "channel_title": v.channel_title if v else "",
            "views": v.views if v else 0,
            "comments_collected": len(members),
            **_mix(members),
        })
    return out


def _trend(rows: list[Comment]) -> list[dict]:
    by_day: dict[str, list[Comment]] = defaultdict(list)
    for r in rows:
        if r.published_at:
            day = r.published_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
            by_day[day].append(r)
    return [
        {"date": day, **_mix(members)}
        for day, members in sorted(by_day.items())
    ]


def _representative(rows: list[Comment], videos: list[TrackedVideo]) -> dict:
    vmeta = {v.id: v for v in videos}

    def pack(label: str) -> list[dict]:
        cands = [r for r in rows if r.sentiment == label and not r.is_spam]
        cands.sort(key=lambda r: -r.like_count)
        out = []
        for r in cands[:5]:
            v = vmeta.get(r.video_pk)
            out.append({
                "comment_id": r.comment_id,
                "text": r.text_original[:280],
                "like_count": r.like_count,
                "language": r.language,
                "video_title": v.title if v else "",
                "url": r.source_url or (f"https://www.youtube.com/watch?v={r.video_id}&lc={r.comment_id}" if v else None),
                "sentiment": r.sentiment,
            })
        return out

    return {"positive": pack("positive"), "negative": pack("negative")}
