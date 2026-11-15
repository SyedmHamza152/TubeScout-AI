"""Auth & workspace endpoints (email/password; Google OAuth reserved for Ads connections)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, get_workspace
from app.core.security import create_access_token, hash_password, verify_password
from app.models.identity import AuditLog, User, Workspace, WorkspaceMember

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterBody(BaseModel):
    email: EmailStr
    name: str = Field(default="", max_length=200)
    password: str = Field(min_length=8, max_length=128)
    workspace_name: str = Field(default="My workspace", max_length=200)
    market: str = Field(default="PK", max_length=8)
    currency: str = Field(default="PKR", max_length=8)


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class WorkspaceBody(BaseModel):
    name: str = Field(max_length=200)
    market: str = Field(default="PK", max_length=8)
    currency: str = Field(default="PKR", max_length=8)


def _workspace_payload(ws: Workspace) -> dict:
    return {"id": ws.id, "name": ws.name, "market": ws.market, "currency": ws.currency}


@router.post("/register", status_code=201)
def register(body: RegisterBody, db: Session = Depends(get_db)):
    existing = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "An account with this email already exists.")
    user = User(email=body.email.lower(), name=body.name or body.email.split("@")[0],
                password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    ws = Workspace(name=body.workspace_name, owner_id=user.id,
                   market=body.market.upper(), currency=body.currency.upper())
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    db.add(AuditLog(workspace_id=ws.id, user_id=user.id, action="register", detail={}))
    db.commit()
    db.refresh(ws)
    return {"token": create_access_token(user.id, ws.id), "user": {"id": user.id, "email": user.email, "name": user.name},
            "workspace": _workspace_payload(ws)}


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password.")
    member = db.execute(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
        .order_by(WorkspaceMember.id.asc())
    ).scalars().first()
    ws = db.get(Workspace, member.workspace_id) if member else None
    if ws is None:
        ws = Workspace(name=f"{user.name or user.email} workspace", owner_id=user.id)
        db.add(ws)
        db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
        db.commit()
        db.refresh(ws)
    return {"token": create_access_token(user.id, ws.id), "user": {"id": user.id, "email": user.email, "name": user.name},
            "workspace": _workspace_payload(ws)}


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    workspaces = db.execute(
        select(Workspace).join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
    ).scalars().all()
    return {"user": {"id": user.id, "email": user.email, "name": user.name},
            "workspaces": [_workspace_payload(w) for w in workspaces]}


@router.post("/workspaces", status_code=201)
def create_workspace(body: WorkspaceBody, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    ws = Workspace(name=body.name, owner_id=user.id, market=body.market.upper(), currency=body.currency.upper())
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    db.commit()
    db.refresh(ws)
    return _workspace_payload(ws)


@router.get("/workspaces")
def list_workspaces(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    workspaces = db.execute(
        select(Workspace).join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
    ).scalars().all()
    return {"workspaces": [_workspace_payload(w) for w in workspaces]}


@router.get("/workspace/current")
def current_workspace(ws: Workspace = Depends(get_workspace)):
    return _workspace_payload(ws)
