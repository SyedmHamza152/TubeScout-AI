"""Findings & Recommendation Engine.

Converts collected data + analytics into evidence-based findings. Every
finding includes: description, supporting metrics, evidence links,
collection period, methodology, confidence, limitations, and a recommended
action. No generic AI filler — findings are generated only from computed
results, and each carries provenance labels.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.constants import LABEL_INFERENCE, LABEL_LIVE
from app.models.audience import AnomalyDetection, AudienceCluster
from app.models.campaign import Finding
from app.models.research import Comment, ResearchSession, TopicRecord, TrackedChannel, TrackedVideo
from app.nlp.aspect_packs import PACK_LABELS, get_pack


def build_findings(db: Session, workspace_id: str, session_id: str) -> dict:
    session = db.get(ResearchSession, session_id)
    if session is None:
        return {"findings": 0}

    db.execute(delete(Finding).where(Finding.session_id == session_id))
    comments = db.execute(
        select(Comment).where(Comment.session_id == session_id, Comment.is_spam.is_(False))
    ).scalars().all()
    videos = db.execute(select(TrackedVideo).where(TrackedVideo.session_id == session_id)).scalars().all()
    channels = db.execute(select(TrackedChannel).where(TrackedChannel.workspace_id == workspace_id)).scalars().all()
    topics = db.execute(select(TopicRecord).where(TopicRecord.session_id == session_id)
                        .order_by(TopicRecord.comment_count.desc())).scalars().all()
    clusters = db.execute(select(AudienceCluster).where(AudienceCluster.session_id == session_id)
                          .order_by(AudienceCluster.size.desc())).scalars().all()
    anomalies = db.execute(select(AnomalyDetection).where(AnomalyDetection.session_id == session_id)
                           .order_by(AnomalyDetection.score.desc())).scalars().all()

    n = len(comments)
    period_start = min((c.published_at for c in comments if c.published_at), default=None)
    period_end = max((c.published_at for c in comments if c.published_at), default=None)
    created = 0

    def add(category, title, description, metrics, evidence, methodology, confidence,
            limitations, action, label=LABEL_LIVE):
        nonlocal created
        db.add(Finding(
            workspace_id=workspace_id, session_id=session_id, category=category,
            title=title[:300], description=description, metrics=metrics, evidence=evidence,
            methodology=methodology, confidence=confidence, limitations=limitations,
            recommended_action=action, period_start=period_start, period_end=period_end,
            data_label=label,
        ))
        created += 1

    vmeta = {v.id: v for v in videos}

    # 1. most discussed videos / engagement leaders
    if videos:
        top_by_eng = sorted([v for v in videos if v.views > 0], key=lambda v: -v.engagement_rate)[:3]
        if top_by_eng:
            add(
                "engagement",
                f"Strongest engagement: {top_by_eng[0].title[:80]}",
                "Videos ranked by public engagement rate (likes+comments)/views within this research. "
                f"The leader reached {top_by_eng[0].engagement_rate:.4f} vs a median of "
                f"{sorted(v.engagement_rate for v in videos)[len(videos) // 2]:.4f}.",
                {"leader_video": top_by_eng[0].video_id,
                 "leader_engagement_rate": top_by_eng[0].engagement_rate,
                 "videos_compared": len(videos)},
                [{"type": "video", "url": f"https://www.youtube.com/watch?v={v.video_id}",
                  "title": v.title, "views": v.views, "engagement_rate": v.engagement_rate}
                 for v in top_by_eng],
                "engagement_rate = (likes + comments) / views from public statistics (LIVE DATA)",
                0.7,
                "Organic engagement only; not advertising performance. Small sample caveat applies "
                "when fewer than 15 videos were collected.",
                "Study the leader's format, title, thumbnail and first-30-seconds hook; replicate "
                "the pattern in upcoming content.",
            )

    # 2. top complaint areas from aspect sentiment
    pack_key = (session.config or {}).get("aspect_pack", "product")
    pack = get_pack(pack_key)
    from app.models.research import AspectSentiment
    aspects = db.execute(
        select(AspectSentiment).where(AspectSentiment.session_id == session_id)
    ).scalars().all()
    by_aspect: dict[str, dict] = {}
    for a in aspects:
        slot = by_aspect.setdefault(a.aspect, {"neg": 0, "pos": 0, "n": 0})
        slot["n"] += 1
        slot["neg"] += a.label == "negative"
        slot["pos"] += a.label == "positive"
    worst = sorted(by_aspect.items(), key=lambda kv: -(kv[1]["neg"] / max(1, kv[1]["n"])))[:1]
    if worst and worst[0][1]["neg"] >= 3:
        key, slot = worst[0]
        neg_comments = [c for c in comments if any(
            ax.aspect == key and ax.label == "negative"
            for ax in aspects if ax.comment_pk == c.id)] if aspects else []
        evidence = []
        for c in sorted(neg_comments, key=lambda c: -c.like_count)[:3]:
            v = vmeta.get(c.video_pk)
            evidence.append({"type": "comment", "text": c.text_original[:200],
                             "url": c.source_url,
                             "video": v.title if v else ""})
        add(
            "complaint",
            f"Top complaint area: {pack[key]['label'] if key in pack else key}",
            f"'{pack[key]['label'] if key in pack else key}' is the most negatively-charged aspect in "
            f"collected comments ({slot['neg']} of {slot['n']} aspect mentions negative).",
            {"aspect": key, "negative_mentions": slot["neg"], "mentions": slot["n"],
             "negative_share": round(slot["neg"] / max(1, slot["n"]), 2)},
            evidence,
            f"ABSA with the '{PACK_LABELS.get(pack_key, pack_key)}' pack; clause-level polarity mapping",
            0.65,
            "Aspect keywords are rule-matched; sarcasm/irony can distort aspect polarity. "
            "Percentages describe the collected sample only.",
            "Prioritize fixes/messaging for this aspect; prepare a response playbook for the "
            "most-liked negative comments.",
            LABEL_INFERENCE,
        )

    # 3. intent signals
    intent_counts: dict[str, int] = {}
    for c in comments:
        for k, hit in (c.intents or {}).items():
            if hit and k in ("price_inquiry", "discount_seeking", "availability_check",
                             "delivery_concern", "purchase_intent", "support_complaint"):
                intent_counts[k] = intent_counts.get(k, 0) + 1
    if intent_counts and n:
        top_intent = max(intent_counts, key=lambda k: intent_counts[k])
        add(
            "intent",
            f"Dominant audience intent: {top_intent.replace('_', ' ')}",
            f"{intent_counts[top_intent]} of {n} collected comments signal '{top_intent.replace('_', ' ')}' — "
            "the strongest behavioural intent in this sample.",
            {"intent": top_intent, "count": intent_counts[top_intent],
             "share_pct": round(100 * intent_counts[top_intent] / n, 1), "comments_analyzed": n},
            [],
            "Rule-based trilingual intent detection (English/Roman Urdu/Urdu script), INFERENCE-labeled",
            0.6,
            "Intent flags are lexical signals, not verified customer actions; authors are anonymous "
            "public commenters, not confirmed customers.",
            "If purchase/price intents dominate: add pricing info to descriptions/pinned comments "
            "and prepare a conversion path (link-in-bio, store links).",
            LABEL_INFERENCE,
        )

    # 4. audience segments summary
    if clusters:
        biggest = clusters[0]
        add(
            "audience",
            f"Largest audience segment: {biggest.label} ({biggest.size} commenters)",
            f"Clustering (k={biggest.k}, silhouette {biggest.silhouette}) found {len(clusters)} behavioural "
            f"segments. Largest: '{biggest.label}'. Negative share {biggest.profile.get('neg_share', 0)}, "
            f"purchase-intent rate {biggest.profile.get('intent_purchase_intent', 0)}.",
            {"k": biggest.k, "silhouette": biggest.silhouette, "segments": len(clusters),
             "largest_segment": biggest.label, "size": biggest.size},
            [],
            "K-Means over author-level behavioural features; segment labels assigned by rule-based "
            "interpretation of cluster profiles",
            0.55 if biggest.silhouette < 0.35 else 0.65,
            "Segments are analytical behaviour patterns of commenters, NOT verified demographics or "
            "confirmed customer categories.",
            "Use segments to differentiate messaging: address the dominant segment's needs first "
            "in content and campaign copy.",
            LABEL_INFERENCE,
        )

    # 5. topics gaining attention
    if topics:
        top_topic = topics[0]
        neg_share_topic = top_topic.sentiment_mix.get("negative", 0) / max(1, top_topic.comment_count)
        add(
            "content",
            f"Most-discussed topic: {top_topic.label}",
            f"'{top_topic.label}' accounts for {round(top_topic.share * 100)}% of collected comments "
            f"({top_topic.comment_count}). Negative share within topic: {round(neg_share_topic * 100)}%.",
            {"topic": top_topic.label, "comments": top_topic.comment_count,
             "share_pct": round(top_topic.share * 100, 1),
             "keywords": top_topic.keywords[:6]},
            [],
            "TF-IDF + MiniBatchKMeans topic clustering over normalized comment text",
            0.6,
            "Topic labels are derived from distinctive terms; interpret with the keyword list.",
            "Create content explicitly answering this topic; monitor whether its sentiment mix shifts "
            "after response content ships.",
            LABEL_INFERENCE,
        )

    # 6. anomalies worth investigating
    for a in anomalies[:2]:
        add(
            "anomaly",
            f"Unusual pattern: {a.kind.replace('_', ' ')} on '{a.entity_title[:60]}'",
            a.explanation,
            {"kind": a.kind, "score": a.score, "severity": a.severity,
             "observed": a.observed, "baseline": a.baseline},
            a.evidence,
            "Robust z-scores (median/MAD), binomial z for sentiment spikes, IsolationForest for "
            "multivariate outliers — see the anomaly module for each baseline",
            0.6,
            "Statistical flags on public data; confirm causes manually before acting.",
            "Investigate this video's recent audience reactions; check for product issues, "
            "controversy, or viral dynamics.",
            LABEL_LIVE,
        )

    # 7. competitor sentiment contrast (when multiple channels present)
    ch_comment_neg: dict[str, int] = {}
    ch_comment_n: dict[str, int] = {}
    for c in comments:
        v = vmeta.get(c.video_pk)
        if v and v.channel_title:
            ch_comment_n[v.channel_title] = ch_comment_n.get(v.channel_title, 0) + 1
            ch_comment_neg[v.channel_title] = ch_comment_neg.get(v.channel_title, 0) + (c.sentiment == "negative")
    eligible = {ch: (neg, ch_comment_n[ch]) for ch, neg in ch_comment_neg.items()
                if ch_comment_n[ch] >= 10}
    if len(eligible) >= 2:
        ranked = sorted(eligible.items(), key=lambda kv: -(kv[1][0] / kv[1][1]))
        worst_ch, (neg, tot) = ranked[0]
        best_ch, (neg_b, tot_b) = ranked[-1]
        add(
            "brand",
            f"Channel sentiment contrast: '{worst_ch}' vs '{best_ch}'",
            f"'{worst_ch}' shows {round(100 * neg / tot)}% negative comments (n={tot}) while "
            f"'{best_ch}' shows {round(100 * neg_b / tot_b)}% (n={tot_b}) in collected samples.",
            {"worst_channel": worst_ch, "worst_negative_pct": round(100 * neg / tot, 1),
             "best_channel": best_ch, "best_negative_pct": round(100 * neg_b / tot_b, 1)},
            [],
            "Sentiment distribution per channel over collected comments (LIVE DATA)",
            0.6,
            "Comment samples differ per channel (counts depend on collection caps); only compare "
            "directionally, not precisely.",
            "Study what the positively-received channel does differently; identify dissatisfaction "
            "themes on the negative channel as positioning opportunities.",
        )

    db.commit()
    return {"findings": created}
