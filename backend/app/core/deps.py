"""FastAPI dependencies: auth, workspace scoping, ownership checks."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_token
from app.models.identity import User, Workspace, WorkspaceMember
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(401, "Authentication required.")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(401, "Invalid or expired token.")
    user = db.get(User, payload.get("sub"))
    if not user:
        raise HTTPException(401, "User not found.")
    return user


def get_workspace(
    user: User = Depends(get_current_user),
    x_workspace_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Workspace:
    """Resolve the active workspace and verify membership (data isolation)."""
    if x_workspace_id:
        ws = db.get(Workspace, x_workspace_id)
    else:
        member = db.execute(
            select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
            .order_by(WorkspaceMember.id.asc())
        ).scalars().first()
        ws = db.get(Workspace, member.workspace_id) if member else None
    if ws is None:
        raise HTTPException(404, "No workspace found. Create one first.")
    member = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ws.id, WorkspaceMember.user_id == user.id)
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(403, "You do not have access to this workspace.")
    return ws


def ensure_workspace_member(db: Session, workspace_id: str, user_id: str) -> None:
    member = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(403, "Workspace access denied.")
