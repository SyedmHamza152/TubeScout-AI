"""Persistent YouTube API quota ledger.

Tracks consumption per workspace per day in the database so quota survives
process restarts. search.list costs 100 units; everything else ~1 unit.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import QUOTA_COST
from app.models.research import QuotaUsage


class QuotaExhausted(Exception):
    def __init__(self, used: int, limit: int):
        self.used, self.limit = used, limit
        super().__init__(
            f"YouTube API quota exhausted for today: {used}/{limit} units used. "
            "Collection paused — try again after the daily reset (midnight PT)."
        )


def used_today(db: Session, workspace_id: str) -> int:
    return int(
        db.execute(
            select(func.coalesce(func.sum(QuotaUsage.cost), 0)).where(
                QuotaUsage.workspace_id == workspace_id,
                QuotaUsage.date == date.today(),
            )
        ).scalar() or 0
    )


def spend(db: Session, workspace_id: str, endpoint: str, cost: int | None = None) -> None:
    cost = int(cost if cost is not None else QUOTA_COST.get(endpoint, 1))
    db.add(QuotaUsage(workspace_id=workspace_id, date=date.today(), endpoint=endpoint, cost=cost))
    db.commit()


def assert_budget(db: Session, workspace_id: str, units_needed: int) -> None:
    used = used_today(db, workspace_id)
    limit = settings.YOUTUBE_DAILY_QUOTA
    if used + units_needed > limit:
        raise QuotaExhausted(used, limit)


def status(db: Session, workspace_id: str) -> dict:
    used = used_today(db, workspace_id)
    limit = settings.YOUTUBE_DAILY_QUOTA
    by_endpoint = dict(
        db.execute(
            select(QuotaUsage.endpoint, func.sum(QuotaUsage.cost)).where(
                QuotaUsage.workspace_id == workspace_id, QuotaUsage.date == date.today()
            ).group_by(QuotaUsage.endpoint)
        ).all() or []
    )
    window_start = date.today() - timedelta(days=13)
    history = dict(
        db.execute(
            select(QuotaUsage.date, func.sum(QuotaUsage.cost)).where(
                QuotaUsage.workspace_id == workspace_id, QuotaUsage.date >= window_start
            ).group_by(QuotaUsage.date)
        ).all() or []
    )
    return {
        "used_today": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "by_endpoint": {k: int(v) for k, v in by_endpoint.items()},
        "last_14_days": {str(k): int(v) for k, v in sorted(history.items())},
    }
