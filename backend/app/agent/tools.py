"""Agent tool registry — the ONLY way the agent touches data.

Every tool is a validated backend service call. The LLM never runs SQL and
never calls external APIs directly; it only chooses/suggests tools, and any
execution-requiring action (research run, optimization) needs explicit user
approval in the conversation flow.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import planner
from app.analytics.competitors import compare_workspace_channels, content_gaps
from app.analytics.findings import build_findings
from app.analytics.sentiment_stats import aspect_summary, session_summary
from app.audience.anomalies import detect_session_anomalies
from app.audience.clustering import cluster_session
from app.core.config import settings
from app.models.campaign import BudgetAllocation, BudgetRun, CampaignBrief, Finding
from app.models.audience import AnomalyDetection, AudienceCluster
from app.models.research import (
    Comment,
    Conversation,
    ResearchPlan,
    ResearchSession,
    TopicRecord,
    TrackedVideo,
)
from app.optimization.service import run_budget_optimization
from app.services.research import execute_session
from app.jobs.runner import is_running, submit

logger = logging.getLogger(__name__)

KEY = "session_{sid}"


def _latest_session(db: Session, workspace_id: str, session_id: str | None = None) -> ResearchSession | None:
    if session_id:
        return db.get(ResearchSession, session_id)
    return db.execute(
        select(ResearchSession)
        .where(ResearchSession.workspace_id == workspace_id,
               ResearchSession.status.in_(["completed", "partial"]))
        .order_by(ResearchSession.created_at.desc())
    ).scalars().first()


# --- planning tools ---------------------------------------------------------
def suggest_keywords(text: str) -> dict:
    intent = planner.extract_intent(text)
    return {"keywords": planner.suggest_keywords(intent), "intent": intent}


def draft_plan(conversation: Conversation, user_text: str, history: list[dict]) -> dict:
    intent = planner.extract_intent(user_text, history)
    plan = planner.draft_plan(intent)
    return {"plan": plan, "questions": intent.get("questions", [])}


def save_plan(db: Session, conversation: Conversation, plan: dict, questions: list[str],
              status: str = "draft") -> ResearchPlan:
    last = db.execute(
        select(ResearchPlan).where(ResearchPlan.conversation_id == conversation.id)
        .order_by(ResearchPlan.version.desc())
    ).scalars().first()
    row = ResearchPlan(
        conversation_id=conversation.id,
        version=(last.version + 1) if last else 1,
        plan=plan, status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def approve_plan(db: Session, workspace_id: str, conversation: Conversation, plan_id: int | None) -> ResearchPlan | None:
    row = db.get(ResearchPlan, plan_id) if plan_id else None
    if row is None:
        row = db.execute(
            select(ResearchPlan).where(ResearchPlan.conversation_id == conversation.id)
            .order_by(ResearchPlan.version.desc())
        ).scalars().first()
    if row is None or row.status in ("executed",):
        return None
    row.status = "approved"
    db.commit()
    return row


def edit_plan(db: Session, conversation: Conversation, plan_id: int, edits: dict) -> ResearchPlan | None:
    row = db.get(ResearchPlan, plan_id) if plan_id else db.execute(
        select(ResearchPlan).where(ResearchPlan.conversation_id == conversation.id)
        .order_by(ResearchPlan.version.desc())
    ).scalars().first()
    if row is None:
        return None
    plan = json.loads(json.dumps(row.plan or {}))
    plan.setdefault("filters", {})
    plan.setdefault("collection", {})
    edits = {k: v for k, v in edits.items() if v is not None and k != "plan_id"}

    if edits.get("title"):
        plan["title"] = str(edits["title"]).strip()[:300] or plan.get("title", "Research plan")
    if "keywords" in edits:
        plan["keywords"] = [str(k).strip()[:120] for k in (edits.get("keywords") or []) if str(k).strip()][:8]
    if "channels" in edits:
        plan["channels"] = [str(c).strip()[:120] for c in (edits.get("channels") or []) if str(c).strip()][:3]
    if edits.get("country"):
        plan["country"] = str(edits["country"]).strip().upper()[:8]
        plan["filters"]["country"] = plan["country"]
    if edits.get("mode") in ("keyword", "channel"):
        plan["mode"] = edits["mode"]
    if edits.get("aspect_pack") in ("product", "youtube_content"):
        plan["aspect_pack"] = edits["aspect_pack"]
    if edits.get("research_intent") in ("campaign", "product", "content", "market"):
        plan["research_intent"] = edits["research_intent"]
    if edits.get("date_range_days") is not None:
        days = max(1, min(int(edits["date_range_days"]), 3650))
        plan["date_range_days"] = days
        plan["filters"]["published_after"] = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    if edits.get("max_videos") is not None:
        plan["collection"]["max_videos"] = max(5, min(int(edits["max_videos"]), settings.MAX_VIDEOS_HARD_CAP))
    if edits.get("comments_per_video") is not None:
        plan["collection"]["comments_per_video"] = max(10, min(int(edits["comments_per_video"]), 500))
    if edits.get("comment_total_cap") is not None:
        plan["collection"]["comment_total_cap"] = max(50, min(int(edits["comment_total_cap"]), settings.MAX_COMMENTS_HARD_CAP))

    keywords = plan.get("keywords") or []
    channels = plan.get("channels") or []
    col = plan.get("collection") or {}
    max_videos = int(col.get("max_videos") or settings.DEFAULT_MAX_VIDEOS)
    per_video = max(1, int(col.get("comments_per_video") or settings.DEFAULT_MAX_COMMENTS_PER_VIDEO))
    comment_cap = max(1, int(col.get("comment_total_cap") or settings.DEFAULT_COMMENT_TOTAL_CAP))
    videos_with_comments = min(max_videos, max(1, comment_cap // per_video) + 1)
    if plan.get("mode") == "channel":
        plan["estimated_quota_units"] = (
            max(1, len(channels)) * 2 + max(1, (max_videos + 49) // 50) + videos_with_comments
        )
    else:
        plan["estimated_quota_units"] = (
            max(1, len(keywords)) * 200 + max(1, (max_videos + 49) // 50)
            + max(1, (len(channels) + 49) // 50) + videos_with_comments
        )

    row.plan = plan
    row.status = "edited"
    db.commit()
    return row


# --- execution tool ---------------------------------------------------------
def execute_approved_plan(db: Session, workspace_id: str, user_id: str,
                          conversation: Conversation, plan_id: int | None) -> dict:
    row = approve_plan(db, workspace_id, conversation, plan_id)
    if row is None:
        return {"ok": False, "error": "No approvable research plan found in this conversation."}
    plan = row.plan
    config = {
        "product": plan.get("business", ""),
        "description": plan.get("industry", ""),
        "country": plan.get("country", ""),
        "language": plan.get("filters", {}).get("language", ""),
        "research_intent": plan.get("research_intent", "campaign"),
        "aspect_pack": plan.get("aspect_pack", ""),
        "published_after": plan.get("filters", {}).get("published_after"),
        "video_duration": plan.get("filters", {}).get("video_duration", "any"),
        "order": plan.get("filters", {}).get("order", "relevance"),
        "max_videos": plan.get("collection", {}).get("max_videos", settings.DEFAULT_MAX_VIDEOS),
        "comments_per_video": plan.get("collection", {}).get("comments_per_video", settings.DEFAULT_MAX_COMMENTS_PER_VIDEO),
        "comment_total_cap": plan.get("collection", {}).get("comment_total_cap", settings.DEFAULT_COMMENT_TOTAL_CAP),
        "channels": plan.get("channels", []),
        "mode": plan.get("mode", "keyword"),
    }
    session = ResearchSession(
        workspace_id=workspace_id, created_by=user_id, conversation_id=conversation.id,
        title=plan.get("title", "YouTube research"), mode=config["mode"], config=config,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    row.session_id = session.id
    row.status = "executed"
    from app.models.research import ResearchKeyword

    for kw in plan.get("keywords", []):
        db.add(ResearchKeyword(session_id=session.id, keyword=kw[:300], source="agent"))
    db.commit()

    if not is_running(KEY.format(sid=session.id)):
        submit(KEY.format(sid=session.id), _run_session_job, session.id, workspace_id)
    return {"ok": True, "session_id": session.id, "status": session.status}


def _run_session_job(session_id: str, workspace_id: str) -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        execute_session(db, workspace_id, session_id)


def get_session_status(db: Session, workspace_id: str, session_id: str) -> dict:
    s = db.get(ResearchSession, session_id)
    if s is None or s.workspace_id != workspace_id:
        return {"found": False}
    return {
        "found": True, "session_id": s.id, "title": s.title, "status": s.status,
        "stage": s.stage, "progress": s.progress, "error": s.error,
        "stats": s.stats, "running": is_running(KEY.format(sid=s.id)),
        "data_label": s.data_label,
    }


# --- answer tools -----------------------------------------------------------
def _evidence_pack(db: Session, workspace_id: str, session: ResearchSession) -> dict:
    summary = session_summary(db, session)
    aspects = aspect_summary(db, session, (session.config or {}).get("aspect_pack", "product"))
    clusters = db.execute(
        select(AudienceCluster).where(AudienceCluster.session_id == session.id)
        .order_by(AudienceCluster.size.desc())
    ).scalars().all()
    findings = db.execute(
        select(Finding).where(Finding.session_id == session.id).order_by(Finding.id.desc()).limit(8)
    ).scalars().all()
    top_videos = db.execute(
        select(TrackedVideo).where(TrackedVideo.session_id == session.id)
        .order_by(TrackedVideo.views.desc()).limit(8)
    ).scalars().all()
    topics = db.execute(
        select(TopicRecord)
        .where(TopicRecord.session_id == session.id).order_by(TopicRecord.comment_count.desc()).limit(6)
    ).scalars().all()
    return {
        "session": {"id": session.id, "title": session.title, "status": session.status,
                    "collected_comments": (session.stats or {}).get("comments_stored"),
                    "videos_found": (session.stats or {}).get("videos_found")},
        "sentiment": summary.get("sentiment_overall"),
        "languages": summary.get("languages"),
        "intents": summary.get("intents"),
        "top_videos": [{"title": v.title, "channel": v.channel_title, "views": v.views,
                        "engagement_rate": v.engagement_rate} for v in top_videos],
        "topics": [{"label": t.label, "comments": t.comment_count, "keywords": t.keywords[:5]}
                   for t in topics],
        "aspects": aspects.get("aspects", []),
        "segments": [{"label": c.label, "size": c.size,
                      "neg_share": c.profile.get("neg_share"),
                      "purchase_intent": c.profile.get("intent_purchase_intent")}
                     for c in clusters],
        "findings": [{"title": f.title, "category": f.category,
                      "metrics": f.metrics, "action": f.recommended_action} for f in findings],
        "sample_disclaimer": summary.get("sample_disclaimer"),
    }


def answer_from_data(db: Session, workspace_id: str, question: str, session_id: str | None) -> dict:
    session = _latest_session(db, workspace_id, session_id)
    if session is None:
        return {
            "answer": "No completed YouTube research is available yet. Approve and run a research "
                      "plan first — answers are always grounded in collected data, never invented.",
            "data_label": "INSUFFICIENT DATA",
        }
    pack = _evidence_pack(db, workspace_id, session)
    from app.agent.llm import chat

    ground = (
        "You are the research assistant of a YouTube audience intelligence platform. "
        "Answer the user's question STRICTLY from the JSON evidence below. "
        "If the evidence does not contain the answer, say so plainly. "
        "Cite concrete numbers. Percentages describe the collected sample, not all of YouTube. "
        "Do not invent metrics.\n\nEVIDENCE:\n" + json.dumps(pack, default=str)[:12000]
    )
    answer = chat([
        {"role": "system", "content": ground},
        {"role": "user", "content": question[:1000]},
    ])
    if not answer:
        answer = _deterministic_answer(question, pack)
    return {"answer": answer, "session_id": session.id, "data_label": session.data_label,
            "evidence_used": list(pack.keys())}


def _deterministic_answer(question: str, pack: dict) -> str:
    q = question.lower()
    s = pack.get("sentiment") or {}
    lines = [f"Based on research '{pack['session']['title']}' "
             f"({pack['session'].get('collected_comments') or 0} comments, "
             f"{pack['session'].get('videos_found') or 0} videos):"]
    if any(k in q for k in ("brand", "channel", "strongest engagement")):
        vids = pack.get("top_videos") or []
        if vids:
            lines.append(f"Strongest engagement leader: “{vids[0]['title']}” by {vids[0]['channel']} "
                         f"(views {vids[0]['views']:,}, engagement {vids[0]['engagement_rate']:.4f}).")
    if any(k in q for k in ("complain", "complaint", "negative", "problem")):
        aspects = [a for a in pack.get("aspects", []) if a.get("negative_pct", 0) > 0]
        if aspects:
            top = max(aspects, key=lambda a: a["negative_pct"])
            lines.append(f"Top complaint area: {top['label']} — {top['negative_pct']}% of its mentions are negative "
                         f"({top['mentions']} mentions).")
        else:
            lines.append("No clear negative aspect pattern was detected in this sample.")
    if any(k in q for k in ("topic", "discuss", "talk")):
        topics = pack.get("topics") or []
        if topics:
            lines.append("Most-discussed topics: " + "; ".join(f"{t['label']} ({t['comments']} comments)" for t in topics[:3]))
    if any(k in q for k in ("segment", "audience", "cluster", "group")):
        segs = pack.get("segments") or []
        if segs:
            lines.append("Audience segments: " + "; ".join(
                f"{s['label']} (n={s['size']}, neg {round((s.get('neg_share') or 0) * 100)}%)" for s in segs[:4]))
    if any(k in q for k in ("opportunit", "content gap", "strategy", "recommend", "campaign", "budget")):
        findings = pack.get("findings") or []
        for f in findings[:3]:
            if f.get("action"):
                lines.append(f"Recommendation ({f['category']}): {f['action']}")
    if s:
        lines.append(f"Overall sentiment in sample: {s.get('positive_pct')}% positive, "
                     f"{s.get('negative_pct')}% negative, {s.get('neutral_pct')}% neutral, "
                     f"{s.get('mixed_pct')}% mixed, {s.get('uncertain_pct')}% uncertain.")
    lines.append(pack.get("sample_disclaimer", ""))
    return "\n".join(lines)


# --- analytics triggers (re-run on demand) ----------------------------------
def rerun_analytics(db: Session, workspace_id: str, session_id: str, parts: list[str]) -> dict:
    session = db.get(ResearchSession, session_id)
    if session is None or session.workspace_id != workspace_id:
        return {"ok": False, "error": "session not found"}
    out: dict[str, object] = {}
    if "topics" in parts:
        from app.nlp.topics_service import build_topics

        out["topics"] = build_topics(db, session_id)
    if "summary" in parts:
        out["summary"] = bool(session_summary(db, session))
    if "clusters" in parts:
        out["clusters"] = cluster_session(db, workspace_id, session_id)
    if "anomalies" in parts:
        out["anomalies"] = detect_session_anomalies(db, workspace_id, session_id)
    if "findings" in parts:
        out["findings"] = build_findings(db, workspace_id, session_id)
    if "competitors" in parts:
        out["competitors"] = compare_workspace_channels(db, workspace_id, session_id)
    return {"ok": True, **out}


# --- campaign/optimizer tool -------------------------------------------------
def run_optimizer(db: Session, workspace_id: str, brief_data: dict) -> dict:
    brief = CampaignBrief(
        workspace_id=workspace_id,
        session_id=brief_data.get("session_id"),
        product=brief_data.get("product", "product"),
        description=brief_data.get("description", ""),
        business_category=brief_data.get("business_category", ""),
        country=brief_data.get("country", settings.DEFAULT_MARKET),
        currency=brief_data.get("currency", settings.DEFAULT_CURRENCY),
        total_budget=float(brief_data.get("total_budget") or 0),
        duration_days=int(brief_data.get("duration_days") or 14),
        objective=brief_data.get("objective") or "Sales / Conversions",
        target_audience=brief_data.get("target_audience", ""),
        preferred_formats=brief_data.get("preferred_formats") or [],
    )
    if brief.total_budget <= 0:
        return {"ok": False, "error": "total_budget must be positive"}
    db.add(brief)
    db.commit()
    db.refresh(brief)
    run = run_budget_optimization(db, workspace_id, brief, brief_data.get("strategy") or "balanced")
    allocs = db.execute(select(BudgetAllocation).where(BudgetAllocation.run_id == run.id)).scalars().all()
    return {
        "ok": True,
        "run": {
            "id": run.id, "strategy": run.strategy, "cold_start": run.cold_start,
            "confidence": run.confidence, "algorithm": run.algorithm,
            "methodology": run.methodology, "source_label": run.source_label,
            "predicted_totals": run.predicted_totals,
            "allocations": [{
                "format_key": a.format_key, "label": a.label, "share": a.share,
                "amount": a.amount, "predicted": a.predicted, "confidence": a.confidence,
                "reason": a.reason, "fit_factors": a.fit_factors,
            } for a in allocs],
        },
    }


def competitor_overview(db: Session, workspace_id: str, session_id: str | None) -> dict:
    return compare_workspace_channels(db, workspace_id, session_id)
