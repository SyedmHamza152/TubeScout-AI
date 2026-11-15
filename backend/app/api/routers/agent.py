"""AI research agent endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import orchestrator, tools
from app.core.db import get_db
from app.core.deps import get_current_user, get_workspace
from app.models.identity import User, Workspace
from app.models.research import ChatMessage, Conversation, ResearchPlan

router = APIRouter(prefix="/agent", tags=["agent"])


class MessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None


class PlanEditBody(BaseModel):
    plan_id: int | None = None
    title: str | None = None
    keywords: list[str] | None = None
    channels: list[str] | None = None
    country: str | None = None
    mode: str | None = None
    aspect_pack: str | None = None
    research_intent: str | None = None
    date_range_days: int | None = None
    max_videos: int | None = None
    comments_per_video: int | None = None
    comment_total_cap: int | None = None


class PlanApproveBody(BaseModel):
    plan_id: int | None = None


@router.get("/conversations")
def list_conversations(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                       db: Session = Depends(get_db)):
    rows = db.execute(
        select(Conversation).where(Conversation.workspace_id == ws.id, Conversation.status == "active")
        .order_by(Conversation.updated_at.desc()).limit(50)
    ).scalars().all()
    return {"conversations": [{"id": c.id, "title": c.title, "updated_at": str(c.updated_at),
                               "current_session_id": c.current_session_id} for c in rows]}


@router.post("/conversations")
def new_conversation(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                     db: Session = Depends(get_db)):
    conv = orchestrator.get_or_create_conversation(db, ws.id, None)
    return {"conversation_id": conv.id}


@router.get("/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: str, user: User = Depends(get_current_user),
                          ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.workspace_id != ws.id:
        raise HTTPException(404, "Conversation not found.")
    rows = db.execute(
        select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.id.asc()).limit(500)
    ).scalars().all()
    return {"messages": [{"id": r.id, "role": r.role, "content": r.content,
                          "payload": r.payload, "created_at": str(r.created_at)} for r in rows]}


@router.post("/message")
def send_message(body: MessageBody, user: User = Depends(get_current_user),
                 ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    result = orchestrator.handle_message(db, ws.id, user, body.conversation_id, body.text)
    return result


@router.get("/plans/{plan_id}")
def get_plan(plan_id: int, user: User = Depends(get_current_user),
             ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    row = db.get(ResearchPlan, plan_id)
    if row is None:
        raise HTTPException(404, "Plan not found.")
    conv = db.get(Conversation, row.conversation_id)
    if conv is None or conv.workspace_id != ws.id:
        raise HTTPException(403, "Plan access denied.")
    return {"plan": row.plan, "id": row.id, "version": row.version, "status": row.status}


@router.put("/plans/{plan_id}")
def edit_plan(plan_id: int, body: PlanEditBody, user: User = Depends(get_current_user),
              ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    conv = db.get(Conversation, _conversation_of(db, ws.id, plan_id))
    row = tools.edit_plan(db, conv, plan_id, body.model_dump(exclude_none=True))
    if row is None:
        raise HTTPException(404, "Plan not found.")
    return {"plan": row.plan, "id": row.id, "status": row.status}


@router.post("/plans/{plan_id}/approve")
def approve_plan(plan_id: int, user: User = Depends(get_current_user),
                 ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    conv = orchestrator.get_or_create_conversation(db, ws.id, None)
    conv_id = _conversation_of(db, ws.id, plan_id)
    conv = db.get(Conversation, conv_id)
    result = tools.execute_approved_plan(db, ws.id, user.id, conv, plan_id)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Could not execute plan."))
    return result


def _conversation_of(db: Session, workspace_id: str, plan_id: int) -> str:
    row = db.get(ResearchPlan, plan_id)
    if row is None:
        raise HTTPException(404, "Plan not found.")
    conv = db.get(Conversation, row.conversation_id)
    if conv is None or conv.workspace_id != workspace_id:
        raise HTTPException(403, "Plan access denied.")
    return conv.id
