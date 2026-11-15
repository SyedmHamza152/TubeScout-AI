"""Intent detection (trilingual: English / Roman Urdu / Urdu script).

Detects marketing-relevant intent signals in comments. Intent flags are
INFERENCE-labeled analytical signals — they indicate likely intent, never
verified purchase behaviour or identity.
"""
from __future__ import annotations

import re

INTENTS: dict[str, dict] = {
    "price_inquiry": {
        "label": "Price inquiry",
        "patterns": [
            r"\bprice\b( please| kya| kitna| kya hai)?", r"\bkitn(e|a|i)? (price|paisay|ka hai)\b",
            r"\bqeemat\b", r"\brate kya\b", r"price\s*\?", r"قیمت کیا", "قیمت بتا",
        ],
    },
    "discount_seeking": {
        "label": "Discount seeking",
        "patterns": [
            r"\bdiscount\b", r"\bsale\b", r"\boffer\b", r"\bcoupon\b", r"\bdeal\b",
            r"\bkam(qeemat| price)\b", "رعایت", "ڈسکاؤنٹ", "سیل",
        ],
    },
    "availability_check": {
        "label": "Availability check",
        "patterns": [
            r"\bavailable\b", r"\bin stock\b", r"\bout of stock\b", r"\bmile(ga|gi)\b",
            r"\bkaha se mile\b", r"\bstock me\b", "دستیاب", "ملے گا",
        ],
    },
    "delivery_concern": {
        "label": "Delivery concern",
        "patterns": [
            r"\bdelivery\b", r"\bshipping\b", r"\bkitne din\b", r"\bparcel\b",
            r"\border (kitne din|nahi|nhai|cancel)\b", r"\bwaiting\b", "ڈیلیوری", "پارسل",
        ],
    },
    "purchase_intent": {
        "label": "Possible inquiry",
        "patterns": [
            r"\bi want (to buy|this|one)\b", r"\bwant to order\b", r"\bhow to order\b",
            r"\border kar(na|do| den)\b", r"\binbox me\b", r"\bdm\b", r"\bcontact\b",
            r"\bbook (kar|karo)\b", r"\binterested\b", "آرڈر", "خریدنا",
        ],
    },
    "support_complaint": {
        "label": "Support/service complaint",
        "patterns": [
            r"\bno (reply|response)\b", r"\bnot replying\b", r"\bcomplaint\b",
            r"\brefund\b", r"\bfraud\b", r"\bscam\b", r"\bnumber (de|do|dia)\b",
            "شکایت", "جواب نہیں",
        ],
    },
    "recommendation_request": {
        "label": "Recommendation request",
        "patterns": [
            r"\bwhich (one|is better)\b", r"\bsuggest\b", r"\brecommend\b",
            r"\bkaunsa (behtar|better|acha)\b", r"\bbest\b.*\?", "تجویز", "بہتر",
        ],
    },
    "question_general": {
        "label": "General question",
        "patterns": [r"\?\s*$", r"^kya\b", r"^what\b", r"^how\b", r"^when\b", r"^where\b", r"کیا ", "کیسے "],
    },
}

_COMPILED = {
    intent: [re.compile(p, re.IGNORECASE) for p in spec["patterns"]]
    for intent, spec in INTENTS.items()
}


def detect_intents(text_original: str, text_normalized: str) -> dict:
    """Return {intent_key: true,...} plus convenience summary flags."""
    haystacks = (text_original, text_normalized)
    flags: dict[str, bool] = {}
    for intent, patterns in _COMPILED.items():
        hit = any(p.search(h) for p in patterns for h in haystacks)
        flags[intent] = bool(hit)
    flags["purchase_intent"] = bool(
        flags["purchase_intent"] or flags["price_inquiry"] or flags["availability_check"]
    )
    flags["has_intent"] = any(v for k, v in flags.items() if k not in ("purchase_intent", "has_intent"))
    return flags
