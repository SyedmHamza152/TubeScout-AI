"""Periodic refresh scheduler (APScheduler, in-process).

Refreshes public stats snapshots for tracked videos so engagement change is
measurable over time. Data freshness is therefore "as of the last refresh" —
never claimed to be real-time.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _refresh_all_workspaces() -> None:
    try:
        from app.core.db import SessionLocal
        from app.services.research import refresh_workspace_videos

        with SessionLocal() as db:
            refreshed = refresh_workspace_videos(db)
            logger.info("scheduled refresh: %s videos updated", refreshed)
    except Exception:
        logger.exception("scheduled refresh failed")


def start_scheduler() -> None:
    global _scheduler
    if not settings.REFRESH_ENABLED:
        return
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _refresh_all_workspaces, "interval",
        minutes=max(15, settings.REFRESH_INTERVAL_MINUTES),
        id="stats-refresh", replace_existing=True,
    )
    _scheduler.start()
    logger.info("refresh scheduler started (interval %s min)", settings.REFRESH_INTERVAL_MINUTES)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
