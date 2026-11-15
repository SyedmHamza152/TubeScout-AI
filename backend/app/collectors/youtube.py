"""YouTube Data API v3 collector — official API ONLY.

Policy: no scraping, no unofficial endpoints (the legacy InnerTube path from
Review-Lens is intentionally NOT carried over). Supports keyword research
(search.list with filters + pagination) and channel research (channels.list →
uploads playlist → playlistItems.list), video details (videos.list) and
comment collection (commentThreads.list + replies).

Public organic statistics only. This data is NOT advertising spend, paid
conversions, or competitor ROAS.
"""
from __future__ import annotations

import html
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import settings

logger = logging.getLogger(__name__)


class YouTubeNotConfigured(Exception):
    pass


class YouTubeApiError(Exception):
    pass


def is_configured() -> bool:
    return bool(settings.YOUTUBE_API_KEY)


def _client():
    if not is_configured():
        raise YouTubeNotConfigured(
            "YOUTUBE_API_KEY is not configured. Add it to backend/.env to enable live research."
        )
    return build("youtube", "v3", developerKey=settings.YOUTUBE_API_KEY, cache_discovery=False)


def _with_backoff(fn, *, retries: int = 3, base_delay: float = 1.0):
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except HttpError as e:
            status = e.resp.status
            reason = ""
            try:
                reason = e.error_details[0].get("reason", "")
            except Exception:
                pass
            if status == 403 and "quotaExceeded" in reason:
                raise YouTubeApiError("QUOTA_EXHAUSTED: YouTube daily quota exceeded.") from e
            if status in (403, 429, 500, 503):
                last_exc = e
                time.sleep(base_delay * (2 ** attempt))
                continue
            raise YouTubeApiError(f"YouTube API HTTP {status}: {reason or str(e)[:200]}") from e
    raise YouTubeApiError(f"YouTube API failed after retries: {last_exc}")


def _clean(text: str) -> str:
    return html.unescape(text or "")


def _parse_duration(iso: str) -> int:
    m = re.match(r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------
def search_videos(
    query: str,
    *,
    limit: int = 50,
    order: str = "relevance",
    page_token: str | None = None,
    region_code: str = "",
    relevance_language: str = "",
    published_after: datetime | None = None,
    published_before: datetime | None = None,
    video_duration: str = "",  # any|short|medium|long
    video_category_id: str = "",
) -> tuple[list[dict], str | None]:
    svc = _client()
    try:
        kwargs: dict = {
            "q": query, "part": "snippet", "type": "video",
            "maxResults": max(1, min(limit, 50)), "order": order,
            "safeSearch": "moderate",
        }
        if region_code:
            kwargs["regionCode"] = region_code
        if relevance_language:
            kwargs["relevanceLanguage"] = relevance_language
        if published_after:
            kwargs["publishedAfter"] = published_after.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if published_before:
            kwargs["publishedBefore"] = published_before.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if video_duration and video_duration != "any":
            kwargs["videoDuration"] = video_duration
        if video_category_id:
            kwargs["videoCategoryId"] = video_category_id
        if page_token:
            kwargs["pageToken"] = page_token
        resp = _with_backoff(lambda: svc.search().list(**kwargs).execute())
        out = []
        for item in resp.get("items", []):
            vid = item.get("id", {}).get("videoId")
            sn = item.get("snippet", {})
            if not vid:
                continue
            out.append({
                "video_id": vid,
                "title": _clean(sn.get("title", "")),
                "description": _clean(sn.get("description", ""))[:2000],
                "channel_id": sn.get("channelId", ""),
                "channel_title": _clean(sn.get("channelTitle", "")),
                "published_at": sn.get("publishedAt", ""),
                "thumbnail_url": (sn.get("thumbnails", {}).get("medium", {}) or {}).get("url", ""),
            })
        return out, resp.get("nextPageToken")
    finally:
        svc.close()


# --------------------------------------------------------------------------
# videos / channels
# --------------------------------------------------------------------------
def get_video_details(video_ids: list[str]) -> list[dict]:
    if not video_ids:
        return []
    svc = _client()
    out: list[dict] = []
    try:
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i:i + 50]
            resp = _with_backoff(lambda chunk=chunk: svc.videos().list(
                id=",".join(chunk), part="statistics,contentDetails,snippet",
            ).execute())
            for item in resp.get("items", []):
                st, cd, sn = item.get("statistics", {}), item.get("contentDetails", {}), item.get("snippet", {})
                duration = _parse_duration(cd.get("duration", ""))
                views = int(st.get("viewCount", 0) or 0)
                likes = int(st.get("likeCount", 0) or 0)
                comments = int(st.get("commentCount", 0) or 0)
                out.append({
                    "video_id": item.get("id", ""),
                    "title": _clean(sn.get("title", "")),
                    "description": _clean(sn.get("description", ""))[:5000],
                    "channel_id": sn.get("channelId", ""),
                    "channel_title": _clean(sn.get("channelTitle", "")),
                    "published_at": sn.get("publishedAt", ""),
                    "tags": (sn.get("tags") or [])[:20],
                    "category_id": sn.get("categoryId", ""),
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "duration_seconds": duration,
                    "content_type": "short" if 0 < duration <= 65 else "long",
                    "engagement_rate": round((likes + comments) / views, 6) if views > 0 else 0.0,
                })
    finally:
        svc.close()
    return out


def get_channel_details(channel_ids: list[str]) -> dict[str, dict]:
    if not channel_ids:
        return {}
    svc = _client()
    out: dict[str, dict] = {}
    try:
        uniq = list(dict.fromkeys(channel_ids))
        for i in range(0, len(uniq), 50):
            chunk = uniq[i:i + 50]
            resp = _with_backoff(lambda chunk=chunk: svc.channels().list(
                id=",".join(chunk), part="statistics,snippet,contentDetails",
            ).execute())
            for item in resp.get("items", []):
                st, sn, cd = item.get("statistics", {}), item.get("snippet", {}), item.get("contentDetails", {})
                out[item.get("id", "")] = {
                    "channel_id": item.get("id", ""),
                    "title": _clean(sn.get("title", "")),
                    "handle": (sn.get("customUrl") or "").lstrip("@"),
                    "description": _clean(sn.get("description", ""))[:1000],
                    "country": sn.get("country", ""),
                    "subscribers": int(st.get("subscriberCount", 0) or 0),
                    "total_views": int(st.get("viewCount", 0) or 0),
                    "video_count": int(st.get("videoCount", 0) or 0),
                    "uploads_playlist_id": (cd.get("relatedPlaylists") or {}).get("uploads", ""),
                    "thumbnail_url": (sn.get("thumbnails", {}).get("medium", {}) or {}).get("url", ""),
                }
    finally:
        svc.close()
    return out


def resolve_channel(channel_input: str) -> dict:
    """Resolve a channel URL / @handle / channel_id / search name to details."""
    raw = (channel_input or "").strip()
    if not raw:
        raise YouTubeApiError("Provide a channel URL, @handle, or channel ID.")
    # URL forms
    if "://" in raw or raw.startswith("/") or "youtube.com" in raw or "youtu.be" in raw:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        path = parsed.path
        if "/channel/" in path:
            cid = path.split("/channel/")[1].split("/")[0]
            return get_channel_details([cid]).get(cid) or {}
        query = ""
        for key in ("c", "user"):
            if f"/{key}/" in path:
                query = path.split(f"/{key}/")[1].split("/")[0]
                break
        if not query and path.startswith("/@"):
            query = path[2:].split("/")[0]
        if not query:  # /watch?v=... — resolve the video's channel
            v = parse_qs(parsed.query).get("v", [""])[0]
            if v:
                details = get_video_details([v])
                if details:
                    return get_channel_details([details[0]["channel_id"]]).get(details[0]["channel_id"]) or {}
            raise YouTubeApiError("Could not parse a channel from this URL.")
        raw = f"@{query}"
    if raw.startswith("UC") and len(raw) >= 24:
        got = get_channel_details([raw])
        if got:
            return got[raw]
    handle = raw.lstrip("@")
    svc = _client()
    try:
        resp = _with_backoff(lambda: svc.channels().list(
            part="statistics,snippet,contentDetails", forHandle=handle,
        ).execute())
        items = resp.get("items", [])
        if not items:
            resp = _with_backoff(lambda: svc.channels().list(
                part="statistics,snippet,contentDetails", forUsername=handle,
            ).execute())
            items = resp.get("items", [])
        if not items:
            return _search_channel_fallback(handle)
        item = items[0]
        return get_channel_details([item["id"]]).get(item["id"]) or {}
    finally:
        svc.close()


def _search_channel_fallback(name: str) -> dict:
    svc = _client()
    try:
        resp = _with_backoff(lambda: svc.search().list(
            q=name, part="snippet", type="channel", maxResults=1,
        ).execute())
        items = resp.get("items", [])
        if not items:
            raise YouTubeApiError(f"No channel found for '{name}'.")
        cid = items[0]["snippet"]["channelId"] or items[0]["id"].get("channelId", "")
        return get_channel_details([cid]).get(cid, {})
    finally:
        svc.close()


def get_playlist_items(playlist_id: str, *, limit: int = 50) -> list[dict]:
    """Uploads-playlist items (preferred over search.list for channel videos)."""
    svc = _client()
    out: list[dict] = []
    try:
        token = None
        while len(out) < limit:
            kwargs = {
                "playlistId": playlist_id, "part": "snippet,contentDetails",
                "maxResults": min(50, limit - len(out)),
            }
            if token:
                kwargs["pageToken"] = token
            resp = _with_backoff(lambda kwargs=kwargs: svc.playlistItems().list(**kwargs).execute())
            for item in resp.get("items", []):
                sn, cd = item.get("snippet", {}), item.get("contentDetails", {})
                vid = cd.get("videoId") or (item.get("id") or "")
                if not vid:
                    continue
                out.append({
                    "video_id": vid,
                    "title": _clean(sn.get("title", "")),
                    "description": _clean(sn.get("description", ""))[:2000],
                    "channel_id": sn.get("channelId", "") or cd.get("videoOwnerChannelId", ""),
                    "channel_title": _clean(sn.get("videoOwnerChannelTitle", "") or sn.get("channelTitle", "")),
                    "published_at": cd.get("videoPublishedAt") or sn.get("publishedAt", ""),
                    "thumbnail_url": (sn.get("thumbnails", {}).get("medium", {}) or {}).get("url", ""),
                })
            token = resp.get("nextPageToken")
            if not token:
                break
    finally:
        svc.close()
    return out


# --------------------------------------------------------------------------
# comments
# --------------------------------------------------------------------------
def collect_comments(video_id: str, max_comments: int = 100, include_replies: bool = True) -> tuple[list[dict], bool]:
    """Collect top-level comments (and replies where available).

    Returns (comments, comments_enabled). Handles disabled comments,
    pagination and missing metadata.
    """
    svc = _client()
    out: list[dict] = []
    token = None
    enabled = True
    try:
        while len(out) < max_comments:
            kwargs = {
                "part": "snippet", "videoId": video_id, "maxResults": min(100, max_comments - len(out)),
                "textFormat": "plainText", "order": "relevance",
            }
            if token:
                kwargs["pageToken"] = token
            try:
                resp = _with_backoff(lambda kwargs=kwargs: svc.commentThreads().list(**kwargs).execute())
            except YouTubeApiError as exc:
                if "has disabled comments" in str(exc) or "commentDisabled" in str(exc):
                    enabled = False
                    break
                raise
            for item in resp.get("items", []):
                top = item.get("snippet", {}).get("topLevelComment", {})
                sn = top.get("snippet", {})
                cid = top.get("id", "")
                text = (sn.get("textDisplay") or "").strip()
                if cid and text:
                    out.append({
                        "comment_id": cid,
                        "parent_id": None,
                        "video_id": video_id,
                        "author_channel_id": sn.get("authorChannelId", {}).get("value", "") if isinstance(sn.get("authorChannelId"), dict) else "",
                        "author": sn.get("authorDisplayName", ""),
                        "text": text[:2000],
                        "like_count": int(sn.get("likeCount", 0) or 0),
                        "reply_count": int(item.get("snippet", {}).get("totalReplyCount", 0) or 0),
                        "published_at": sn.get("publishedAt", ""),
                        "source_url": f"https://www.youtube.com/watch?v={video_id}&lc={cid}",
                    })
                if include_replies and item.get("replies", {}).get("comments") and len(out) < max_comments:
                    for rep in item["replies"]["comments"]:
                        rsn = rep.get("snippet", {})
                        rid = rep.get("id", "")
                        rtext = (rsn.get("textDisplay") or "").strip()
                        if rid and rtext:
                            out.append({
                                "comment_id": rid,
                                "parent_id": cid,
                                "video_id": video_id,
                                "author_channel_id": rsn.get("authorChannelId", {}).get("value", "") if isinstance(rsn.get("authorChannelId"), dict) else "",
                                "author": rsn.get("authorDisplayName", ""),
                                "text": rtext[:2000],
                                "like_count": int(rsn.get("likeCount", 0) or 0),
                                "reply_count": 0,
                                "published_at": rsn.get("publishedAt", ""),
                                "source_url": f"https://www.youtube.com/watch?v={video_id}&lc={rid}",
                            })
            token = resp.get("nextPageToken")
            if not token:
                break
    finally:
        svc.close()
    return out, enabled


def default_date_window(days: int) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    return end - timedelta(days=days), end
