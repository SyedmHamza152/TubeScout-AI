"""Identity & workspace models."""
from __future__ import annotations

import uuid

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def uid() -> str:
    return uuid.uuid4().hex


def utcnow():
    from sqlalchemy import func

    return func.now()


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    market: Mapped[str] = mapped_column(String(8), default="PK")
    currency: Mapped[str] = mapped_column(String(8), default="PKR")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_ws_member"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="owner")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())
