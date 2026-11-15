"""Agent orchestrator — conversation state machine.

Hybrid architecture: the LLM handles understanding, suggestions and grounded
explanations; backend tools handle data/execution; the user explicitly
approves plans before execution. Deterministic fallbacks keep the whole flow
working when no LLM is configured.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import tools
from app.agent.llm import chat, chat_json
from app.models.identity import AuditLog, User
from app.models.research import ChatMessage, Conversation, ResearchPlan, ResearchSession

APPROVE_PAT = re.compile(
    r"\b(approve|approved|execute|run it|go ahead|looks good|proceed|start the research|"
    r"yes\s*,?\s*(run|execute|go|start)|confirm)\b", re.IGNORECASE)
DATA_QUESTION_PAT = re.compile(
    r"\b(brand|engagement|complain|complaint|topic|trending|segment|audience|cluster|"
    r"opportunit|sentiment|negative|positive|dislike|like most|recommend|campaign|budget|"
    r"finding|insight|which|what are|how many|what do)\b", re.IGNORECASE)
RESEARCH_REQUEST_PAT = re.compile(
    r"\b(research|analyse|analyze|analysis|collect|run|execute|study|"
    r"what do (?:viewers|people|users|customers|audience) say|sentiment|"
    r"trending|anomal|cluster|segment|finding|insight|keyword research|channel research|"
    r"video (?:research|analysis|comments)|comment (?:research|analysis|sentiment))\b",
    re.IGNORECASE)
CANCEL_PAT = re.compile(r"\b(cancel|stop|abort|discard|delete|clear|nevermind|never mind)\b", re.IGNORECASE)


def get_or_create_conversation(db: Session, workspace_id: str, conversation_id: str | None) -> Conversation:
    if conversation_id:
        conv = db.get(Conversation, conversation_id)
        if conv and conv.workspace_id == workspace_id and conv.status == "active":
            return conv
    conv = Conversation(workspace_id=workspace_id)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def _history(db: Session, conversation_id: str, limit: int = 10) -> list[dict]:
    rows = db.execute(
        select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.id.desc()).limit(limit)
    ).scalars().all()
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


def _latest_plan(db: Session, conversation_id: str) -> ResearchPlan | None:
    return db.execute(
        select(ResearchPlan).where(ResearchPlan.conversation_id == conversation_id)
        .order_by(ResearchPlan.version.desc())
    ).scalars().first()


def _active_session(db: Session, conversation: Conversation) -> ResearchSession | None:
    if conversation.current_session_id:
        return db.get(ResearchSession, conversation.current_session_id)
    return db.execute(
        select(ResearchSession)
        .where(ResearchSession.conversation_id == conversation.id)
        .order_by(ResearchSession.created_at.desc())
    ).scalars().first()


def handle_message(db: Session, workspace_id: str, user: User,
                   conversation_id: str | None, text: str) -> dict:
    conv = get_or_create_conversation(db, workspace_id, conversation_id)
    db.add(ChatMessage(conversation_id=conv.id, role="user", content=text,
                       payload={"data_label": "USER INPUT"}))
    db.commit()

    history = _history(db, conv.id)
    plan = _latest_plan(db, conv.id)
    session = _active_session(db, conv)
    reply_payload: dict = {}

    # ---- 1. plan approval ---------------------------------------------------
    if plan and plan.status in ("draft", "edited") and APPROVE_PAT.search(text):
        result = tools.execute_approved_plan(db, workspace_id, user.id, conv, plan.id)
        if result.get("ok"):
            conv.current_session_id = result["session_id"]
            db.commit()
            reply = (
                f"Research approved and started (session `{result['session_id'][:8]}`). "
                "I am collecting public YouTube data through the official API: videos, "
                "channels and comments, then running sentiment, aspect, intent, topic, "
                "clustering and anomaly analysis. Ask me for status any time — for example "
                "'how is the research going?' — or ask questions about the results once "
                "the session completes."
            )
            reply_payload = {"type": "execution_started", "session_id": result["session_id"]}
        else:
            reply = result.get("error", "Could not start the research.")
            reply_payload = {"type": "execution_error"}
        db.add(ChatMessage(conversation_id=conv.id, role="assistant", content=reply, payload=reply_payload))
        db.commit()
        return {"reply": reply, "conversation_id": conv.id, "payload": reply_payload}

    # ---- 1b. plan cancellation -------------------------------------------------
    if plan and plan.status in ("draft", "edited") and CANCEL_PAT.search(text):
        plan.status = "cancelled"
        db.commit()
        reply = "Cancelled the draft research plan. You can ask for recommendations or start a new research anytime."
        reply_payload = {"type": "plan_cancelled", "plan_id": plan.id, "status": "cancelled"}
        db.add(ChatMessage(conversation_id=conv.id, role="assistant", content=reply, payload=reply_payload))
        db.commit()
        return {"reply": reply, "conversation_id": conv.id, "payload": reply_payload}

    # ---- 2. research status -------------------------------------------------
    if session and re.search(r"\b(status|progress|going|running|done yet|finished)\b", text, re.IGNORECASE):
        st = tools.get_session_status(db, workspace_id, session.id)
        reply = _status_reply(st)
        db.add(ChatMessage(conversation_id=conv.id, role="assistant", content=reply,
                           payload={"type": "status", "data_label": "LIVE DATA"}))
        db.commit()
        return {"reply": reply, "conversation_id": conv.id, "payload": reply_payload}

    # ---- 3. data question ----------------------------------------------------
    if (session and session.status in ("completed", "partial")
            and DATA_QUESTION_PAT.search(text) and len(text.split()) >= 3):
        result = tools.answer_from_data(db, workspace_id, text, session.id)
        reply = result["answer"]
        reply_payload = {"type": "data_answer", "data_label": result.get("data_label"),
                         "session_id": result.get("session_id")}
        db.add(ChatMessage(conversation_id=conv.id, role="assistant", content=reply, payload=reply_payload))
        db.commit()
        return {"reply": reply, "conversation_id": conv.id, "payload": reply_payload}

    # ---- 4. plan editing ------------------------------------------------------
    if plan and plan.status in ("draft", "edited") and re.search(
            r"\b(edit|change|add keyword|remove|replace|use instead|instead)\b", text, re.IGNORECASE):
        edits = _plan_edits_from_text(text, plan.plan)
        if edits:
            row = tools.edit_plan(db, conv, plan.id, edits)
            if row:
                reply = _plan_reply(row.plan, "Updated the research plan with your edits. Review it and approve to execute.")
                reply_payload = {"type": "plan", "plan": row.plan, "plan_id": row.id, "status": row.status}
                db.add(ChatMessage(conversation_id=conv.id, role="assistant", content=reply, payload=reply_payload))
                db.commit()
                return {"reply": reply, "conversation_id": conv.id, "payload": reply_payload,
                        "plan": row.plan, "plan_id": row.id}

    # ---- 6. conversational recommendations ------------------------------------
    if not RESEARCH_REQUEST_PAT.search(text):
        result = _recommendation_reply(history, text)
        reply_payload = {"type": "recommendation", "data_label": "INFERENCE",
                         "recommendations": result["recommendations"]}
        db.add(ChatMessage(conversation_id=conv.id, role="assistant", content=result["reply"],
                           payload=reply_payload))
        db.commit()
        return {"reply": result["reply"], "conversation_id": conv.id, "payload": reply_payload,
                "recommendations": result["recommendations"]}

    # ---- 5. new planning flow -------------------------------------------------
    draft = tools.draft_plan(conv, text, history)
    plan_dict = draft["plan"]
    questions = draft["questions"]
    # refine plan with LLM polish when available
    polish = chat_json([
        {"role": "system", "content": (
            "You are the research planner. Given the draft plan JSON and user message, "
            "improve the keywords and title. Return JSON with keys: title, keywords (max 6). "
            "Only use information present in the message or plan.")},
        {"role": "user", "content": "USER: " + text[:1500] + "\nDRAFT: " + json.dumps(
            {"title": plan_dict["title"], "keywords": plan_dict["keywords"]})}
    ]) or {}
    if polish.get("keywords"):
        plan_dict["keywords"] = [k[:120] for k in polish["keywords"]][:6]
    if polish.get("title"):
        plan_dict["title"] = str(polish["title"])[:300]

    row = tools.save_plan(db, conv, plan_dict, questions)
    if questions:
        reply = _questions_reply(questions, plan_dict)
    else:
        reply = _plan_reply(plan_dict, "Here is the research plan I prepared. Review it — "
                                       "edit anything you want, or approve it to start the research.")
    reply_payload = {"type": "plan", "plan": plan_dict, "plan_id": row.id, "status": row.status}
    db.add(ChatMessage(conversation_id=conv.id, role="assistant", content=reply, payload=reply_payload))
    db.commit()
    db.add(AuditLog(workspace_id=workspace_id, user_id=user.id, action="plan_drafted",
                    detail={"plan_id": row.id, "title": plan_dict.get("title")}))
    db.commit()
    return {"reply": reply, "conversation_id": conv.id, "payload": reply_payload,
            "plan": plan_dict, "plan_id": row.id, "questions": questions}


def _recommendation_reply(history: list[dict], text: str) -> dict:
    today = datetime.now(timezone.utc).date().isoformat()
    messages = [
        {"role": "system", "content": (
            f"Current date: {today}. You are AudienceLens, a recommendation assistant for YouTube audience and campaign intelligence. "
            "Have a natural conversation and give practical recommendations based on what the user says and general knowledge. "
            "Use the most current products, models, platforms, and market trends you know as of the current date; "
            "do not recommend outdated models or old flagship generations unless the user asks for budget/older options. "
            "When the user asks for the best/current products or models, name specific current models/products released or "
            "updated in the last 12 months as of the current date in both reply and recommendations; if you are not certain "
            "a model exists, say so instead of listing older flagships as current. "
            "Do not claim access to live YouTube audience sentiment, viewer opinions, comments, trends, or collected data "
            "unless a completed research session is provided in the conversation. If the user wants live YouTube evidence, "
            "tell them to ask for research (for example 'research ...' or 'what do viewers say about ...') or use Product Search. "
            "Return JSON only with keys: reply (string, concise conversational answer) and recommendations "
            "(array of up to 6 short actionable strings with the specific names/details)."
        )},
    ] + history[-8:]
    parsed = chat_json(messages)
    reply = ""
    recs: list[str] = []
    if isinstance(parsed, dict):
        reply = str(parsed.get("reply") or "").strip()
        raw = parsed.get("recommendations")
        if isinstance(raw, list):
            recs = [str(x).strip()[:300] for x in raw if str(x).strip()][:6]
    if not reply:
        reply, recs = _fallback_recommendations(text, history)
    if not recs:
        _, recs = _fallback_recommendations(text, history)
    return {"reply": reply, "recommendations": recs}


def _fallback_recommendations(text: str, history: list[dict] | None = None) -> tuple[str, list[str]]:
    def clean(s: str) -> str:
        return s.strip().rstrip("?.!")

    def generic(s: str) -> bool:
        n = clean(s).lower()
        return (not n) or re.fullmatch(
            r"(hi|hello|hey|good (morning|afternoon|evening)|salam|salaam|"
            r"i want (some )?(recommendations?|suggestions?|ideas)|recommend(ations| me)?|"
            r"suggest(ions)?|ideas|help|start|what can you do|thanks|thank you)[!. ]*",
            n) is not None

    topic = clean(text)
    if generic(topic):
        topic = ""
        for msg in reversed((history or [])[:-1]):
            if msg.get("role") == "user" and not generic(str(msg.get("content") or "")):
                topic = clean(str(msg.get("content" or "")))
                break

    if not topic:
        reply = (
            "I can help with YouTube audience, content, and campaign recommendations. "
            "Tell me your product/niche/goal — for example a cosmetics line, phone brand, course, or local service — "
            "and I’ll give specific ideas. If you want live viewer evidence, say 'research [topic]'."
        )
        return reply, [
            "Product launch: pick one hero benefit, one proof point, and one objection to answer in the first 30 seconds.",
            "YouTube channel growth: post one searchable problem-solving video per week and reply to every comment for the first 48 hours.",
            "Ad campaign: test 3 hooks against the same offer, then scale only the hook with the best qualified-comment rate.",
            "Competitor research: compare titles, thumbnails, comment objections, and pricing language before planning content.",
            "Content strategy: build a 4-week arc — awareness, comparison, proof, and offer — tied to one audience problem.",
        ]

    low = topic.lower()
    if re.search(r"phone|mobile|smartphone|iphone|android|pixel|samsung|xiaomi|oneplus|fold", low):
        recs = [
            "Compare the newest iPhone, Pixel, and Galaxy flagships released this year on camera, battery, software support, and resale value.",
            "Position around one clear buyer question: best camera, best battery, best value, or best for gaming/video.",
            "Create comparison content that answers 'which should I buy?' with price bands and trade-offs, not spec dumps.",
            "Track comments for price sensitivity, brand trust, durability doubts, and ecosystem lock-in concerns.",
            "Measure success by purchase-intent comments, saves, and repeat comparison questions rather than views alone.",
        ]
    elif re.search(r"cosmetic|beauty|makeup|skincare|lawn|dress|fashion|cloth|jewelry|watch", low):
        recs = [
            "Lead with one visual proof point: texture, fit, finish, or before/after — not a generic product shot.",
            "Build trust with authenticity, delivery time, sizing/fit, and return-policy answers in the first minute.",
            "Use comparison angles: price vs quality, original vs copy, and which occasion/season fits best.",
            "Watch comments for price objections, trust doubts, quality complaints, and delivery/stock issues.",
            "Measure success by qualified comments, purchase-intent signals, and repeat sizing/price questions.",
        ]
    else:
        recs = [
            f"Define the target viewer for {topic}: who is most likely to watch, comment, or buy? Keep it specific — market, age, problem, and budget.",
            "Build 3 YouTube content angles: problem/solution, comparison, and proof/review. Each should answer a real viewer question.",
            "Track keywords around price, quality, availability, delivery, and authenticity — these drive purchase decisions.",
            "Watch comments for complaints, price sensitivity, authenticity doubts, and delivery issues; they reveal objections to address.",
            "Measure success by qualified comments, purchase-intent signals, sentiment mix, and repeat questions — not just views.",
        ]

    reply = (
        f"Based on our chat, here are practical recommendations for {topic}. "
        "If you want live viewer evidence, ask me to research it or use Product Search."
    )
    return reply, recs


def _plan_edits_from_text(text: str, plan: dict) -> dict:
    edits: dict = {}
    quoted = re.findall(r"\"(.+?)\"|'(.+?)'", text)
    flat = [a or b for a, b in quoted]
    add_kw = re.search(r"add keyword[s]?\s+(.*)", text, re.IGNORECASE)
    if add_kw:
        edits["keywords"] = (plan.get("keywords") or []) + [add_kw.group(1).strip("\"' ")[:120]]
    elif flat and re.search(r"\b(use|replace|instead|keyword)\b", text, re.IGNORECASE):
        edits["keywords"] = [k[:120] for k in flat][:6]
    vm = re.search(r"(\d{1,4})\s*videos", text, re.IGNORECASE)
    if vm:
        edits["max_videos"] = int(vm.group(1))
    cm = re.search(r"(\d{1,5})\s*comments", text, re.IGNORECASE)
    if cm:
        edits["comments_per_video"] = max(10, min(int(cm.group(1)), 500))
    dm = re.search(r"(\d{1,3})\s*days", text, re.IGNORECASE)
    if dm:
        edits["date_range_days"] = int(dm.group(1))
    return edits


def _plan_reply(plan: dict, lead: str) -> str:
    kws = ", ".join(f"“{k}”" for k in plan.get("keywords", [])[:6]) or "—"
    chs = ", ".join(plan.get("channels", [])) or "—"
    col = plan.get("collection", {})
    return (
        f"{lead}\n\n"
        f"Title: {plan.get('title')}\n"
        f"Market: {plan.get('country')} | Mode: {plan.get('mode')} | Aspect pack: {plan.get('aspect_pack')}\n"
        f"Keywords: {kws}\n"
        f"Channels: {chs}\n"
        f"Collection: up to {col.get('max_videos')} videos, "
        f"{col.get('comments_per_video')} comments/video (cap {col.get('comment_total_cap')})\n"
        f"Estimated quota: ~{plan.get('estimated_quota_units')} units"
    )


def _questions_reply(questions: list[str], plan: dict) -> str:
    return ("Before finalizing the research plan I need a few details:\n"
            + "\n".join(f"- {q}" for q in questions)
            + "\n\nYou can answer briefly (e.g. 'scented candles, Pakistan'). "
              "A draft plan is ready and I will refine it with your answers.")


def _status_reply(st: dict) -> str:
    if not st.get("found"):
        return "I could not find that research session."
    if st.get("running") and st.get("status") in ("collecting", "processing", "analyzing"):
        return (f"Research in progress: {st.get('stage')} ({st.get('progress')}%). "
                f"Collected so far: {((st.get('stats') or {}).get('comments_stored') or 0)} comments, "
                f"{((st.get('stats') or {}).get('videos_found') or 0)} videos. "
                "Quota and retries are handled automatically.")
    if st.get("status") in ("completed", "partial"):
        stats = st.get("stats") or {}
        msg = (f"Research {'completed' if st['status'] == 'completed' else 'completed with warnings'}. "
               f"Videos: {stats.get('videos_found', 0)}, comments stored: {stats.get('comments_stored', 0)}, "
               f"quota spent: {stats.get('quota_spent', 0)} units.")
        if st.get("error"):
            msg += f" Note: {st['error']}"
        return msg + " Ask me anything about the results — e.g. 'which brand has the strongest engagement?'"
    if st.get("status") == "failed":
        return f"The research run failed: {st.get('error')}. You can approve the plan again to retry."
    return f"Session status: {st.get('status')} — {st.get('stage')}."
