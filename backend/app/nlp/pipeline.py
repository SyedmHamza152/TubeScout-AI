"""Comment processing pipeline.

For every collected comment:
  1. language detection (EN / Urdu / Roman Urdu / mixed, with confidence)
  2. normalization (original text preserved verbatim)
  3. spam / relevance scoring
  4. dedup (workspace + comment_id unique; upsert-safe)
  5. sentiment (5-class: positive|negative|neutral|mixed|uncertain)
  6. intent detection
  7. ABSA with the session's aspect pack
  8. optional English gloss
  9. embeddings (batched)
 10. persistence with provenance labels
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.constants import LABEL_LIVE
from app.models.research import AspectSentiment, Comment
from app.nlp import relevance as rel
from app.nlp.aspects import extract_aspects
from app.nlp.aspect_packs import get_pack
from app.nlp.embeddings import embed_texts
from app.nlp.intents import detect_intents
from app.nlp.language import detect_language
from app.nlp.roman_urdu import normalize_text
from app.nlp.sentiment import analyze_sentiment
from app.nlp.translate import gloss_translate

logger = logging.getLogger(__name__)


def _map_sentiment_class(label: str, confidence: float, uncertain: bool, drivers: list[str]) -> str:
    """5-class mapping: never force a label when the engine is uncertain."""
    if label == "mixed":
        return "mixed"
    if uncertain or (confidence < 0.45 and not drivers):
        return "uncertain"
    return label


def _to_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=datetime.now().astimezone().tzinfo)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def process_comments(
    db: Session,
    workspace_id: str,
    session_id: str | None,
    video_pk: int,
    video_id: str,
    raw_comments: list[dict],
    product_tokens: set[str],
    pack_key: str = "product",
    data_label: str = LABEL_LIVE,
) -> dict:
    """Analyze + store one video's comments. Returns counters."""
    pack = get_pack(pack_key)
    existing = {
        row[0]
        for row in db.query(Comment.comment_id)
        .filter(Comment.workspace_id == workspace_id, Comment.video_pk == video_pk)
        .all()
    }

    stored = duplicates = spam = 0
    pending: list[tuple[dict, object]] = []

    for raw in raw_comments:
        text = (raw.get("text") or "").strip()
        cid = raw.get("comment_id") or ""
        if not text or not cid or cid in existing:
            duplicates += 1
            continue
        existing.add(cid)

        lang = detect_language(text)
        normalized = normalize_text(text)
        is_spam, _spam_reason = rel.spam_signals(text)
        relevance = rel.relevance_score(normalized, product_tokens) if product_tokens else 0.6
        sent = analyze_sentiment(text)
        label = _map_sentiment_class(sent.label, sent.confidence, sent.uncertain, sent.drivers)
        intents = detect_intents(text, normalized)
        aspects = extract_aspects(sent, pack_key)
        translation = gloss_translate(text, lang.language) if lang.language != "english" else None

        row = Comment(
            workspace_id=workspace_id,
            session_id=session_id,
            video_pk=video_pk,
            video_id=video_id,
            comment_id=cid,
            parent_id=raw.get("parent_id"),
            author_channel_id=raw.get("author_channel_id") or "",
            author_display_name=(raw.get("author") or "")[:200],
            text_original=text,
            text_normalized=normalized,
            translation=translation,
            language=lang.language,
            language_confidence=lang.confidence,
            language_uncertain=lang.uncertain,
            sentiment=label,
            sentiment_score=sent.score,
            sentiment_confidence=sent.confidence,
            sarcasm_suspect=sent.sarcasm_suspect,
            intents=intents,
            relevance=round(relevance, 3),
            is_spam=is_spam,
            like_count=int(raw.get("like_count") or 0),
            reply_count=int(raw.get("reply_count") or 0),
            published_at=_to_dt(raw.get("published_at")),
            source_url=raw.get("source_url"),
            data_label=data_label,
        )
        db.add(row)
        db.flush()

        for m in aspects:
            db.add(AspectSentiment(
                comment_pk=row.id,
                session_id=session_id,
                workspace_id=workspace_id,
                pack=pack_key,
                aspect=m.aspect,
                label=m.label,
                polarity=m.polarity,
                confidence=m.confidence,
            ))
        stored += 1
        if is_spam:
            spam += 1
        pending.append((raw, row))

    # batch embeddings for the new comments
    if pending:
        vectors, model_id = embed_texts([r["text"] for r, _ in pending]) if pending else ([], "")
        if vectors:
            for (_, row), vec in zip(pending, vectors):
                row.embedding = vec
                row.embedding_model = model_id

    db.commit()
    return {"video_pk": video_pk, "video_id": video_id, "stored": stored,
            "duplicates": duplicates, "spam": spam, "pack": pack_key,
            "aspects": sorted(pack.keys())}
