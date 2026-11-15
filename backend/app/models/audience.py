"""Audience intelligence models: clusters, members, anomalies."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.identity import utcnow


class AudienceCluster(Base):
    """One analytically-derived audience segment (NOT verified demographics)."""

    __tablename__ = "audience_clusters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(32), ForeignKey("research_sessions.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    method: Mapped[str] = mapped_column(String(40), default="kmeans")
    k: Mapped[int] = mapped_column(Integer, default=0)
    silhouette: Mapped[float] = mapped_column(Float, default=0.0)
    cluster_index: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(120), default="Segment")
    size: Mapped[int] = mapped_column(Integer, default=0)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)  # sentiments, intents, topics, language mix
    interpretation: Mapped[str] = mapped_column(String(60), default="inference")
    data_label: Mapped[str] = mapped_column(String(30), default="INFERENCE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())


class ClusterMember(Base):
    __tablename__ = "cluster_members"
    __table_args__ = (UniqueConstraint("cluster_id", "author_channel_id", name="uq_cluster_author"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("audience_clusters.id"), index=True)
    author_channel_id: Mapped[str] = mapped_column(String(40), default="")
    display_name: Mapped[str] = mapped_column(String(200), default="")
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    features: Mapped[dict] = mapped_column(JSON, default=dict)


class AnomalyDetection(Base):
    __tablename__ = "anomaly_detections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("research_sessions.id"), nullable=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # engagement_rate|comment_volume|negative_spike|isolation_forest
    entity_type: Mapped[str] = mapped_column(String(12), default="video")
    entity_id: Mapped[str] = mapped_column(String(80), index=True)
    entity_title: Mapped[str] = mapped_column(String(400), default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    severity: Mapped[str] = mapped_column(String(12), default="low")  # low|medium|high
    baseline: Mapped[dict] = mapped_column(JSON, default=dict)
    observed: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation: Mapped[str] = mapped_column(String(2000), default="")
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    data_label: Mapped[str] = mapped_column(String(30), default="LIVE DATA")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())
