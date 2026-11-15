"""Campaign, Google Ads, optimization and findings models."""
from __future__ import annotations

from datetime import date, datetime

from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.identity import utcnow


class CampaignBrief(Base):
    """User-provided campaign inputs (USER INPUT provenance)."""

    __tablename__ = "campaign_briefs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(32), ForeignKey("workspaces.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    business_category: Mapped[str] = mapped_column(String(120), default="")
    country: Mapped[str] = mapped_column(String(8), default="PK")
    currency: Mapped[str] = mapped_column(String(8), default="PKR")
    total_budget: Mapped[float] = mapped_column(Float, default=0.0)
    duration_days: Mapped[int] = mapped_column(Integer, default=14)
    objective: Mapped[str] = mapped_column(String(60), default="Sales / Conversions")
    target_audience: Mapped[str] = mapped_column(String(400), default="")
    preferred_formats: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())


class GoogleConnection(Base):
    """Per-workspace Google Ads OAuth connection. Tokens encrypted at rest."""

    __tablename__ = "google_connections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(32), ForeignKey("workspaces.id"), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), default="")
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, default="")
    customer_id: Mapped[str] = mapped_column(String(30), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|connected|error|disconnected
    detail: Mapped[str] = mapped_column(Text, default="")
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AdsCampaign(Base):
    """Actual Google Ads VIDEO campaigns synced from GAQL (LIVE DATA only)."""

    __tablename__ = "ads_campaigns"
    __table_args__ = (UniqueConstraint("workspace_id", "external_id", name="uq_ws_ads_campaign"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(32), ForeignKey("workspaces.id"), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("google_connections.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(300))
    format_key: Mapped[str] = mapped_column(String(20), default="in_stream")
    status: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    objective: Mapped[str] = mapped_column(String(60), default="")
    currency: Mapped[str] = mapped_column(String(8), default="PKR")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())
    data_label: Mapped[str] = mapped_column(String(30), default="LIVE DATA")


class AdsCampaignPerformance(Base):
    __tablename__ = "ads_campaign_performance"
    __table_args__ = (UniqueConstraint("campaign_pk", "date", name="uq_ads_perf_row"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    campaign_pk: Mapped[int] = mapped_column(ForeignKey("ads_campaigns.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    impressions: Mapped[int] = mapped_column(BigInteger, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    conversions: Mapped[float] = mapped_column(Float, default=0.0)
    conversion_value: Mapped[float] = mapped_column(Float, default=0.0)
    video_views: Mapped[int] = mapped_column(BigInteger, default=0)
    data_label: Mapped[str] = mapped_column(String(30), default="LIVE DATA")


class BudgetRun(Base):
    __tablename__ = "budget_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    brief_id: Mapped[int] = mapped_column(ForeignKey("campaign_briefs.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    strategy: Mapped[str] = mapped_column(String(20), default="balanced")
    total_budget: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="PKR")
    objective: Mapped[str] = mapped_column(String(60), default="")
    cold_start: Mapped[bool] = mapped_column(Boolean, default=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    algorithm: Mapped[str] = mapped_column(String(120), default="")
    methodology: Mapped[str] = mapped_column(Text, default="")
    source_label: Mapped[str] = mapped_column(String(30), default="ESTIMATED SCENARIO")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    predicted_totals: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())


class BudgetAllocation(Base):
    __tablename__ = "budget_allocations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("budget_runs.id"), index=True)
    format_key: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(60))
    share: Mapped[float] = mapped_column(Float)
    amount: Mapped[float] = mapped_column(Float)
    predicted: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    fit_factors: Mapped[dict] = mapped_column(JSON, default=dict)


class Finding(Base):
    """Evidence-based finding with methodology, confidence and limitations."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(32), ForeignKey("workspaces.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("research_sessions.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(60), index=True)  # brand|engagement|complaint|intent|opportunity|anomaly|content|audience
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[list] = mapped_column(JSON, default=list)  # videos / comments / links
    methodology: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    limitations: Mapped[str] = mapped_column(Text, default="")
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_label: Mapped[str] = mapped_column(String(30), default="LIVE DATA")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())


class GeneratedReport(Base):
    __tablename__ = "generated_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    session_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(10), default="pdf")
    title: Mapped[str] = mapped_column(String(300), default="")
    path: Mapped[str] = mapped_column(String(500), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=utcnow())
