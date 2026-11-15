"""Configurable aspect packs for ABSA.

The active pack depends on the research topic — product-review aspects are
NOT applied to every video. Pack selection happens at research-session level.

Trilingual keywords: English / Roman Urdu / Urdu script (matched against
normalized Latin tokens and raw Urdu-script tokens).
"""
from __future__ import annotations

PRODUCT_ASPECTS: dict[str, dict] = {
    "quality": {
        "label": "Product Quality", "scope": "product",
        "keywords": {
            "quality", "kwality", "build", "material", "maal", "jins", "standard",
            "banawat", "khoobi", "کارکردگی", "معیار", "بنائی", "ساخت", "مواد", "کوالیٹی",
        },
    },
    "price_value": {
        "label": "Price & Value", "scope": "product",
        "keywords": {
            "price", "qeemat", "rate", "paisay", "paisa", "paise", "rs", "mehnga",
            "mehngi", "sasta", "sasti", "costly", "expensive", "overpriced",
            "affordable", "wasool", "worth", "value", "cheap", "bargain", "budget",
            "قیمت", "مہنگا", "مہنگی", "سستا", "پیسے", "پیسہ",
        },
    },
    "design": {
        "label": "Design & Appearance", "scope": "product",
        "keywords": {
            "design", "look", "looks", "style", "color", "colour", "rang", "sleek",
            "beautiful", "pretty", "khoobsurat", "shakal", "appearance", "finish",
            "premium", "ڈیزائن", "رنگ", "شکل", "خوبصورت",
        },
    },
    "durability": {
        "label": "Durability & Reliability", "scope": "product",
        "keywords": {
            "durable", "durability", "sturdy", "strong", "mazboot", "mazbooti",
            "toot", "toota", "last", "lasting", "reliable", "مضبوط", "ٹوٹ", "چلے",
        },
    },
    "availability": {
        "label": "Availability & Stock", "scope": "product",
        "keywords": {
            "available", "availability", "stock", "out of stock", "in stock",
            "milega", "milega kya", "milta", "mila kaha", "karachi", "lahore",
            "store me", "dukaan", "حاصل", "دستیاب", "اسٹاک",
        },
    },
    "delivery_shipping": {
        "label": "Delivery & Shipping", "scope": "marketplace",
        "keywords": {
            "delivery", "shipping", "shipped", "courier", "parcel", "rider", "dair",
            "late", "jaldi", "kitne din", "ترسیل", "ڈیلیوری", "کورئیر", "پارسل", "دیر", "وقت",
        },
    },
    "packaging": {
        "label": "Packaging", "scope": "marketplace",
        "keywords": {
            "packaging", "packing", "box", "dabba", "dibba", "seal", "sealed", "tape",
            "پیکنگ", "پیکجنگ", "ڈبہ", "ڈبے", "سیل",
        },
    },
    "customer_support": {
        "label": "Customer Support", "scope": "seller",
        "keywords": {
            "support", "service", "complaint", "shikayat", "response", "reply",
            "jawab", "helpline", "refund", "warranty", "guarantee", "return",
            "شکایت", "جواب", "وارنٹی", "ضمانت", "خدمت", "ریفنڈ",
        },
    },
    "brand_trust": {
        "label": "Brand Trust & Authenticity", "scope": "product",
        "keywords": {
            "fake", "nakli", "jaali", "original", "asli", "copy", "replica",
            "counterfeit", "genuine", "trusted", "bharosa", "beiman", "dhoka",
            "کاپی", "نقلی", "جعلی", "اصل", "بھروسہ", "بے ایمان",
        },
    },
}

YOUTUBE_CONTENT_ASPECTS: dict[str, dict] = {
    "content_quality": {
        "label": "Content Quality", "scope": "content",
        "keywords": {
            "quality", "content", "informative", "helpful", "useful", "behtareen",
            "kamaal", "zabardast", "acha", "achi", "bakwas", "faltu", "fazool",
            "waste", "time waste", "ghatiya", "بہترین", "عمدہ", "بکواس", "فضول",
        },
    },
    "presentation": {
        "label": "Video Presentation", "scope": "content",
        "keywords": {
            "editing", "sound", "audio", "video quality", "camera", "lighting",
            "voice", "clear", "blurry", "mic", "thumbnail", "title", "presentation",
            "آواز", "ویڈیو", "ایڈیٹنگ", "کیمرہ",
        },
    },
    "creator_credibility": {
        "label": "Creator Credibility", "scope": "creator",
        "keywords": {
            "honest", "bharosa", "trust", "sponsored", "paid", "promotion", "bias",
            "fake review", "genuine", "sach", "jhoot", "imandar", "خوش", "سچ", "جھوٹ",
        },
    },
    "entertainment": {
        "label": "Entertainment Value", "scope": "content",
        "keywords": {
            "funny", "entertaining", "boring", "mazedaar", "boring tha", "enjoyed",
            "mast", "enjoy", "fun", "مزے", "مزیدار", "بور",
        },
    },
    "educational": {
        "label": "Educational Value", "scope": "content",
        "keywords": {
            "learn", "learned", "tutorial", "guide", "explained", " informative",
            "shukriya", "thanks", "helped", "samajh", "aasan", "سیکھ", "ٹیوٹوریل", "آسان",
        },
    },
    "information_accuracy": {
        "label": "Information Accuracy", "scope": "content",
        "keywords": {
            "wrong", "galat", "incorrect", "misleading", "actual", "accurate",
            "sach me", "tested", "ghalat", "غلط", "درست",
        },
    },
    "audience_experience": {
        "label": "Audience Experience", "scope": "content",
        "keywords": {
            "subscribe", "subscribed", "bell", "notification", "next video",
            "part 2", "more videos", "fan", "follow", "سبسکرائب", "اگلا",
        },
    },
    "brand_perception": {
        "label": "Brand Perception", "scope": "brand",
        "keywords": {
            "brand", "company", "company ne", "brand ne", "trust", "value", "reputation",
            "برانڈ", "کمپنی", "اعتماد",
        },
    },
}

ASPECT_PACKS: dict[str, dict[str, dict]] = {
    "product": PRODUCT_ASPECTS,
    "youtube_content": YOUTUBE_CONTENT_ASPECTS,
}

PACK_LABELS = {"product": "Product & Service Aspects", "youtube_content": "YouTube Content Aspects"}


def get_pack(pack_key: str) -> dict[str, dict]:
    return ASPECT_PACKS.get(pack_key, PRODUCT_ASPECTS)


def select_pack(session_config: dict) -> str:
    """Choose the aspect pack from research configuration.

    Explicit config wins; otherwise infer from research intent: campaign /
    product research -> product pack; general content/market research ->
    youtube_content pack. Mixed topics use the product pack (richer commercial
    signals) — noted in methodology.
    """
    explicit = (session_config or {}).get("aspect_pack")
    if explicit in ASPECT_PACKS:
        return explicit
    intent = (session_config or {}).get("research_intent", "")
    mode = (session_config or {}).get("mode", "keyword")
    if intent in ("campaign", "product", "competitor_products"):
        return "product"
    if mode == "channel" and intent in ("content", "market"):
        return "youtube_content"
    return "youtube_content" if intent == "content" else "product"
