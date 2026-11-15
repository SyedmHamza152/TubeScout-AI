"""Competitor & market intelligence endpoints (public data only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.competitors import compare_workspace_channels, content_gaps
from app.core.db import get_db
from app.core.deps import get_current_user, get_workspace
from app.models.identity import User, Workspace
from app.models.research import TrackedChannel, TrackedVideo

router = APIRouter(prefix="/competitors", tags=["competitors"])


@router.get("/channels")
def channels(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
             db: Session = Depends(get_db), session_id: str | None = None):
    result = compare_workspace_channels(db, ws.id, session_id)
    tracked = db.execute(
        select(TrackedChannel).where(TrackedChannel.workspace_id == ws.id)
    ).scalars().all()
    return {
        "profiles": result["channels"],
        "tracked_channels": [{
            "channel_id": c.channel_id, "title": c.title, "handle": c.handle,
            "subscribers": c.subscribers, "video_count": c.video_count,
            "is_competitor": c.is_competitor, "country": c.country,
            "last_synced_at": str(c.last_synced_at) if c.last_synced_at else None,
            "data_label": c.data_label,
        } for c in tracked],
        "data_label": "LIVE DATA",
        "disclaimer": "Only public YouTube data is used. Private competitor analytics, ad spend, "
                      "paid conversions and competitor ROAS are never claimed or shown.",
    }


@router.get("/gaps/{session_id}")
def gaps(session_id: str, target_channel: str = Query(...),
         user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
         db: Session = Depends(get_db)):
    s = db.get(TrackedVideo, None)
    return content_gaps(db, ws.id, session_id, target_channel)
