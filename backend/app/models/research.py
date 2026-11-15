"""Research, collection and NLP models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.identity import uid, utcnow


class Conversation(Base):
    """AI research-agent conversation (persistent context)."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    title: Mapped[str] = mapped_column(String(300), default="New research conversation")
    status: Mapped[str] = mapped_column(String(20), default="active")
    current_session_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow(), onupdate=utcnow())


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(12))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # tool results, plan refs, labels
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())


class ResearchPlan(Base):
    """Versioned research plan; user edits and approves before execution."""

    __tablename__ = "research_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|edited|approved|rejected|executed
    session_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())


class ResearchSession(Base):
    __tablename__ = "research_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(String(300), default="YouTube research")
    mode: Mapped[str] = mapped_column(String(12), default="keyword")  # keyword | channel
    # planning|collecting|processing|analyzing|completed|failed|partial
    status: Mapped[str] = mapped_column(String(20), default="planning", index=True)
    stage: Mapped[str] = mapped_column(String(60), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_label: Mapped[str] = mapped_column(String(30), default="LIVE DATA")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchKeyword(Base):
    __tablename__ = "research_keywords"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("research_sessions.id"), index=True)
    keyword: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(20), default="user")  # user | agent
    approved: Mapped[bool] = mapped_column(Boolean, default=True)


class TrackedChannel(Base):
    __tablename__ = "tracked_channels"
    __table_args__ = (UniqueConstraint("workspace_id", "channel_id", name="uq_ws_channel"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(32), ForeignKey("workspaces.id"), index=True)
    channel_id: Mapped[str] = mapped_column(String(40), index=True)
    handle: Mapped[str] = mapped_column(String(120), default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    country: Mapped[str] = mapped_column(String(8), default="")
    subscribers: Mapped[int] = mapped_column(BigInteger, default=0)
    total_views: Mapped[int] = mapped_column(BigInteger, default=0)
    video_count: Mapped[int] = mapped_column(BigInteger, default=0)
    uploads_playlist_id: Mapped[str] = mapped_column(String(120), default="")
    is_competitor: Mapped[bool] = mapped_column(Boolean, default=False)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_label: Mapped[str] = mapped_column(String(30), default="LIVE DATA")


class TrackedVideo(Base):
    __tablename__ = "tracked_videos"
    __table_args__ = (
        UniqueConstraint("workspace_id", "video_id", name="uq_ws_video"),
        Index("ix_videos_ws_session", "workspace_id", "session_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(32), ForeignKey("workspaces.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("research_sessions.id"), nullable=True)
    channel_id: Mapped[str] = mapped_column(String(40), index=True, default="")
    channel_title: Mapped[str] = mapped_column(String(300), default="")
    video_id: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str] = mapped_column(String(12), default="long")  # short | long
    tags: Mapped[list] = mapped_column(JSON, default=list)
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    likes: Mapped[int] = mapped_column(BigInteger, default=0)
    comment_count: Mapped[int] = mapped_column(BigInteger, default=0)
    engagement_rate: Mapped[float] = mapped_column(Float, default=0.0)
    matched_keyword: Mapped[str] = mapped_column(String(300), default="")
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_label: Mapped[str] = mapped_column(String(30), default="LIVE DATA")


class VideoStatsSnapshot(Base):
    """Time-series of public stats so engagement change is measurable."""

    __tablename__ = "video_stats_snapshots"
    __table_args__ = (Index("ix_snap_video_time", "video_pk", "captured_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    video_pk: Mapped[int] = mapped_column(ForeignKey("tracked_videos.id"), index=True)
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    likes: Mapped[int] = mapped_column(BigInteger, default=0)
    comment_count: Mapped[int] = mapped_column(BigInteger, default=0)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        UniqueConstraint("workspace_id", "comment_id", name="uq_ws_comment"),
        Index("ix_comments_ws_session", "workspace_id", "session_id"),
        Index("ix_comments_sentiment", "workspace_id", "sentiment"),
        Index("ix_comments_video", "video_pk"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(32), ForeignKey("workspaces.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("research_sessions.id"), nullable=True)
    video_pk: Mapped[int] = mapped_column(ForeignKey("tracked_videos.id"), index=True)
    video_id: Mapped[str] = mapped_column(String(40), default="")
    comment_id: Mapped[str] = mapped_column(String(120), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    author_channel_id: Mapped[str] = mapped_column(String(40), default="", index=True)
    author_display_name: Mapped[str] = mapped_column(String(200), default="")
    # layered text: original verbatim -> normalized (analysis) -> gloss
    text_original: Mapped[str] = mapped_column(Text)
    text_normalized: Mapped[str] = mapped_column(Text, default="")
    translation: Mapped[str | None] = mapped_column(Text, nullable=True)

    language: Mapped[str] = mapped_column(String(16), default="unknown", index=True)
    language_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    language_uncertain: Mapped[bool] = mapped_column(Boolean, default=False)

    # positive|negative|neutral|mixed|uncertain
    sentiment: Mapped[str] = mapped_column(String(12), index=True)
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    sentiment_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    sarcasm_suspect: Mapped[bool] = mapped_column(Boolean, default=False)

    intents: Mapped[dict] = mapped_column(JSON, default=dict)  # intent flags + purchase_intent
    relevance: Mapped[float] = mapped_column(Float, default=0.0)
    is_spam: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    like_count: Mapped[int] = mapped_column(BigInteger, default=0)
    reply_count: Mapped[int] = mapped_column(BigInteger, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(80), default="")
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())
    data_label: Mapped[str] = mapped_column(String(30), default="LIVE DATA")


class AspectSentiment(Base):
    __tablename__ = "aspect_sentiments"
    __table_args__ = (Index("ix_aspect_session", "session_id", "aspect"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    comment_pk: Mapped[int] = mapped_column(ForeignKey("comments.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    pack: Mapped[str] = mapped_column(String(30), default="product")
    aspect: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(12))
    polarity: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class TopicRecord(Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("session_id", "topic_key", name="uq_session_topic"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(32), ForeignKey("research_sessions.id"), index=True)
    topic_key: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(160))
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    share: Mapped[float] = mapped_column(Float, default=0.0)
    sentiment_mix: Mapped[dict] = mapped_column(JSON, default=dict)


class CollectionJob(Base):
    __tablename__ = "collection_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    session_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))  # keyword_search|channel_sync|comment_pull|stats_refresh
    status: Mapped[str] = mapped_column(String(20), default="queued")
    stage: Mapped[str] = mapped_column(String(80), default="")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    quota_spent: Mapped[int] = mapped_column(Integer, default=0)
    items_collected: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QuotaUsage(Base):
    """Persistent YouTube API quota ledger (per workspace, per day)."""

    __tablename__ = "quota_usage"
    __table_args__ = (Index("ix_quota_ws_date", "workspace_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    date: Mapped[datetime] = mapped_column(Date, index=True)
    endpoint: Mapped[str] = mapped_column(String(40))
    cost: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())
