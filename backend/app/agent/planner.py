"""Research plan builder — LLM-assisted with deterministic fallback."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.core.config import settings
from app.nlp.aspect_packs import select_pack

COUNTRIES = {
    "pakistan": "PK", "pk": "PK", "india": "IN", "usa": "US", "united states": "US",
    "us": "US", "uk": "GB", "united kingdom": "GB", "uae": "AE", "dubai": "AE",
    "saudi": "SA", "canada": "CA", "australia": "AU", "germany": "DE",
}

SYSTEM_PROMPT = """You are the research planner of a YouTube audience intelligence platform.
Extract structured research intent from the user's message. Return STRICT JSON:
{
 "business": str,                 # product/service/business being researched
 "country": str,                  # ISO-2 target market if mentioned
 "industry": str,
 "research_intent": "campaign" | "product" | "content" | "market",
 "keywords": [str, ...],          # 3-6 YouTube search keywords
 "channels": [str, ...],          # 0-3 competitor/channel names or handles
 "date_days": int,                # recency window in days (30/90/365)
 "language": str,                 # content language hint or ""
 "questions": [str, ...]          # 1-3 clarifying questions ONLY if critical info is missing
}
Do not invent brands or countries the user did not mention."""


def extract_intent(text: str, history: list[dict] | None = None) -> dict:
    from app.agent.llm import chat_json

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in (history or [])[-6:]:
        messages.append({"role": m["role"], "content": m["content"][:1000]})
    messages.append({"role": "user", "content": text[:2000]})
    parsed = chat_json(messages)
    if parsed and isinstance(parsed, dict):
        parsed.setdefault("business", "")
        parsed.setdefault("country", "")
        parsed.setdefault("industry", "")
        parsed.setdefault("research_intent", "campaign")
        parsed.setdefault("keywords", [])
        parsed.setdefault("channels", [])
        parsed.setdefault("date_days", 90)
        parsed.setdefault("language", "")
        parsed.setdefault("questions", [])
        return parsed

    # deterministic fallback
    lowered = text.lower()
    country = next((code for name, code in COUNTRIES.items() if re.search(rf"\b{name}\b", lowered)), "")
    business = ""
    m = re.search(r"(?:for|about|of|launching|selling|promote[ds]?)\s+(?:my|our|a|an|the)?\s*([a-z0-9' &-]{3,60})", lowered)
    if m:
        business = m.group(1).strip(" '")[:60]
    intent = "campaign"
    if any(k in lowered for k in ("content", "creator", "video idea")):
        intent = "content"
    elif any(k in lowered for k in ("campaign", "budget", "ads", "advert")):
        intent = "campaign"
    elif any(k in lowered for k in ("product", "review", "launch")):
        intent = "product"
    keywords = heuristic_keywords(business or text[:40], intent)
    questions = []
    if not business:
        questions.append("What product, service or business should this research focus on?")
    if not country:
        questions.append("Which target country/market should YouTube research cover?")
    return {
        "business": business, "country": country, "industry": "",
        "research_intent": intent, "keywords": keywords, "channels": [],
        "date_days": 90, "language": "", "questions": questions,
    }


def heuristic_keywords(business: str, intent: str) -> list[str]:
    b = (business or "product").strip().lower()[:50]
    base = [f"{b} review", f"{b} unboxing", f"best {b}", f"{b} price"]
    if intent == "content":
        base = [f"{b} tips", f"how to {b}", f"{b} tutorial", f"best {b}"]
    return base


def suggest_keywords(intent: dict) -> list[str]:
    from app.agent.llm import chat

    business = intent.get("business") or "the product"
    country = intent.get("country") or ""
    raw = chat([
        {"role": "system", "content": "Suggest 6 YouTube search keywords for audience research. One keyword per line, no numbering, no explanations."},
        {"role": "user", "content": f"Business/product: {business}. Market: {country or 'unspecified'}. Research intent: {intent.get('research_intent', 'campaign')}."},
    ])
    if raw:
        kws = [line.strip("-•0123456789. ") for line in raw.strip().splitlines() if line.strip()]
        return [k[:120] for k in kws if 3 <= len(k)][:6]
    return heuristic_keywords(business, intent.get("research_intent", "campaign"))


def draft_plan(intent: dict, extra: dict | None = None) -> dict:
    from app.core.config import settings as s

    intent = dict(intent)
    if not intent.get("keywords"):
        intent["keywords"] = suggest_keywords(intent)
    country = (intent.get("country") or "").upper()
    days = int(intent.get("date_days") or 90)
    now = datetime.utcnow()
    config = {
        "product": intent.get("business", ""),
        "description": intent.get("industry", ""),
        "country": country or settings.DEFAULT_MARKET,
        "language": intent.get("language", ""),
        "research_intent": intent.get("research_intent", "campaign"),
        "published_after": (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "published_before": None,
        "video_duration": "any",
        "order": "relevance",
        "max_videos": min(int(extra or {}).get("max_videos", s.DEFAULT_MAX_VIDEOS) if extra else s.DEFAULT_MAX_VIDEOS, s.MAX_VIDEOS_HARD_CAP),
        "comments_per_video": s.DEFAULT_MAX_COMMENTS_PER_VIDEO,
        "comment_total_cap": s.DEFAULT_COMMENT_TOTAL_CAP,
        "channels": intent.get("channels", []),
        "mode": "channel" if (intent.get("channels") and not intent.get("keywords")) else "keyword",
    }
    config["aspect_pack"] = select_pack(config)
    return {
        "title": f"YouTube research — {intent.get('business') or 'audience'} ({country or 'global'})",
        "business": intent.get("business", ""),
        "country": country or settings.DEFAULT_MARKET,
        "industry": intent.get("industry", ""),
        "research_intent": intent.get("research_intent", "campaign"),
        "mode": config["mode"],
        "keywords": intent.get("keywords", [])[:6],
        "channels": intent.get("channels", []),
        "filters": {k: config[k] for k in ("country", "language", "published_after", "video_duration", "order")},
        "collection": {k: config[k] for k in ("max_videos", "comments_per_video", "comment_total_cap")},
        "aspect_pack": config["aspect_pack"],
        "date_range_days": days,
        "estimated_quota_units": 100 * len(intent.get("keywords", [])) * 2 + 400,
        "methodology": (
            "Official YouTube Data API v3 only. Keyword search with regional/recency filters, "
            "video details, channel metadata, public comments (top-level + replies). "
            "NLP: language detection, sentiment, aspect-based sentiment, intent detection, "
            "embeddings, topic clustering, audience clustering, anomaly detection."
        ),
    }
