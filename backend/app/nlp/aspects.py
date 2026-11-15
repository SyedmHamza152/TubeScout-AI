"""Aspect-Based Sentiment Analysis over configurable aspect packs.

Assigns per-aspect sentiment using the polarity of the clause in which the
aspect keywords appear. Compatible with the Review-Lens clause engine.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.nlp.aspect_packs import get_pack
from app.nlp.sentiment import SentimentResult


@dataclass
class AspectMention:
    aspect: str
    label: str          # positive|negative|neutral|mixed
    polarity: float
    confidence: float


def _clause_has_aspect(clause_text: str, aspect_key: str, pack: dict[str, dict]) -> bool:
    words = set(clause_text.lower().split())
    for kw in pack[aspect_key]["keywords"]:
        if " " in kw:
            if kw in clause_text.lower():
                return True
        elif kw in words:
            return True
    return False


def extract_aspects(sentiment: SentimentResult, pack_key: str = "product") -> list[AspectMention]:
    """Match aspects within each clause; keep the strongest mention per aspect."""
    pack = get_pack(pack_key)
    seen: dict[str, AspectMention] = {}

    for clause in sentiment.clauses:
        for aspect_key in pack:
            if not _clause_has_aspect(clause.text, aspect_key, pack):
                continue
            pol = clause.polarity
            if pol > 0.2:
                lbl = "positive"
            elif pol < -0.2:
                lbl = "negative"
            else:
                lbl = "neutral"
            conf = min(0.95, 0.35 + 0.3 * abs(pol) + (0.2 if clause.drivers else 0))
            mention = AspectMention(aspect_key, lbl, round(pol, 3), round(conf, 3))
            prev = seen.get(aspect_key)
            if prev is None:
                seen[aspect_key] = mention
            elif lbl != "neutral" and (prev.label == "neutral" or abs(pol) > abs(prev.polarity)):
                seen[aspect_key] = mention

    return list(seen.values())


def complaint_scope(mentions: list[AspectMention], pack_key: str = "product") -> str:
    """Classify complaint target within the active pack's scopes."""
    pack = get_pack(pack_key)
    neg_aspects = [m for m in mentions if m.label == "negative"]
    if not neg_aspects:
        return "none"
    scopes = {pack[m.aspect]["scope"] for m in neg_aspects}
    if len(scopes) == 1:
        return scopes.pop()
    return "mixed"
