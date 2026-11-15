"""Integrations endpoints: YouTube status, Google Ads OAuth + sync."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors import youtube as yt
from app.collectors.quota import status as quota_status
from app.core.db import get_db
from app.core.deps import get_current_user, get_workspace
from app.googleads import client as gads
from app.googleads import oauth
from app.models.campaign import AdsCampaign, AdsCampaignPerformance, GoogleConnection
from app.models.identity import User, Workspace

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/youtube/status")
def youtube_status(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                   db: Session = Depends(get_db)):
    return {
        "configured": yt.is_configured(),
        "api": "YouTube Data API v3 (official)",
        "scraping": "disabled by policy",
        "quota": quota_status(db, ws.id),
        "hint": "" if yt.is_configured() else "Set YOUTUBE_API_KEY in backend/.env to enable live collection.",
    }


# ---------------- Google Ads OAuth ----------------
@router.get("/google/start")
def google_start(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                 db: Session = Depends(get_db)):
    if not oauth.is_configured():
        missing = oauth.app_missing_requirements()
        raise HTTPException(503, f"Google OAuth is not configured on the server. Missing: {', '.join(missing)}")
    url, state = oauth.build_authorization_url(ws.id)
    oauth.ensure_connection(db, ws.id)
    return {"authorization_url": url}


@router.get("/google/callback")
def google_callback(code: str = Query(...), state: str = Query(...), db: Session = Depends(get_db)):
    workspace_id = oauth.consume_state(state)
    if not workspace_id:
        raise HTTPException(400, "Invalid or expired OAuth state.")
    conn = oauth.ensure_connection(db, workspace_id)
    tokens = oauth.exchange_code(code)
    try:
        info = oauth.fetch_userinfo(tokens.get("access_token", ""))
        email = info.get("email", "")
    except Exception:
        email = ""
    oauth.store_tokens(db, conn, tokens, email=email)
    return {"ok": True, "status": "connected", "email": email,
            "next": "Store the Google Ads customer ID via /integrations/google/customer"}


@router.post("/google/customer")
def set_customer(customer_id: str = Query(..., min_length=8, max_length=20),
                 user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                 db: Session = Depends(get_db)):
    conn = oauth.ensure_connection(db, ws.id)
    conn.customer_id = customer_id.replace("-", "")
    db.commit()
    return {"ok": True, "customer_id": conn.customer_id}


@router.get("/google/status")
def google_status(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                  db: Session = Depends(get_db)):
    conn = oauth.get_connection(db, ws.id)
    app_missing = oauth.app_missing_requirements()
    return {
        "app_configured": not app_missing,
        "app_missing": app_missing,
        "workspace_connected": bool(conn and conn.status == "connected" and oauth.get_refresh_token(conn)),
        "email": conn.email if conn else "",
        "customer_id": (conn.customer_id if conn else ""),
        "status": conn.status if conn else "not_connected",
        "detail": conn.detail if conn else "",
        "actual_data_available": bool(
            conn and conn.status == "connected" and oauth.get_refresh_token(conn) and conn.customer_id
            and not app_missing
        ),
        "note": "When not connected, actual campaign performance data is unavailable. "
                "Estimated planning scenarios are clearly labeled instead.",
    }


@router.post("/google/disconnect")
def google_disconnect(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                      db: Session = Depends(get_db)):
    conn = oauth.get_connection(db, ws.id)
    if conn is None:
        return {"ok": True, "status": "not_connected"}
    conn.status = "disconnected"
    conn.refresh_token_encrypted = ""
    db.commit()
    return {"ok": True, "status": "disconnected"}


@router.post("/google/test-connection")
def google_test(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                db: Session = Depends(get_db)):
    conn = oauth.get_connection(db, ws.id)
    if conn is None:
        raise HTTPException(400, "No Google connection for this workspace — connect first.")
    result = gads.test_connection(conn)
    conn.last_checked_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    conn.status = "connected" if result.get("ok") else "error"
    conn.detail = str(result.get("detail", ""))[:500]
    db.commit()
    return result


@router.post("/google/sync")
def google_sync(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                db: Session = Depends(get_db), days: int = Query(default=90, le=180)):
    """Sync ACTUAL campaign performance from Google Ads (LIVE DATA only)."""
    conn = oauth.get_connection(db, ws.id)
    if conn is None:
        raise HTTPException(400, "No Google connection for this workspace.")
    try:
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days)
        rows = gads.fetch_daily_performance(conn, start.isoformat(), end.isoformat())
    except gads.GoogleAdsNotConfigured as e:
        raise HTTPException(503, str(e))
    except gads.GoogleAdsError as e:
        conn.status = "error"
        conn.detail = str(e)[:500]
        db.commit()
        raise HTTPException(502, str(e))

    # upsert campaigns
    campaigns: dict[str, AdsCampaign] = {}
    for row in rows:
        camp = db.execute(
            select(AdsCampaign).where(AdsCampaign.workspace_id == ws.id,
                                      AdsCampaign.external_id == row.campaign_id)
        ).scalar_one_or_none()
        if camp is None:
            camp = AdsCampaign(workspace_id=ws.id, connection_id=conn.id, external_id=row.campaign_id)
            db.add(camp)
        camp.name = row.campaign_name
        camp.format_key = row.format_key
        camp.status = row.status
        camp.currency = ws.currency
        campaigns[row.campaign_id] = camp
    db.flush()

    synced = 0
    for row in rows:
        camp = campaigns[row.campaign_id]
        if not row.date:
            continue
        from datetime import datetime as _dt

        d = _dt.strptime(row.date, "%Y-%m-%d").date()
        perf = db.execute(
            select(AdsCampaignPerformance).where(
                AdsCampaignPerformance.campaign_pk == camp.id,
                AdsCampaignPerformance.date == d)
        ).scalar_one_or_none()
        if perf is None:
            perf = AdsCampaignPerformance(campaign_pk=camp.id, date=d)
            db.add(perf)
        perf.impressions = row.impressions
        perf.clicks = row.clicks
        perf.cost_micros = int(row.cost_units * 1_000_000)
        perf.conversions = row.conversions
        perf.conversion_value = row.conversion_value
        perf.video_views = row.video_views
        perf.data_label = "LIVE DATA"
        synced += 1
    db.commit()
    return {"ok": True, "campaigns": len(campaigns), "rows_synced": synced,
            "range": f"{start.isoformat()}..{end.isoformat()}", "data_label": "LIVE DATA"}


@router.get("/google/campaigns")
def google_campaigns(user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                     db: Session = Depends(get_db)):
    camps = db.execute(
        select(AdsCampaign).where(AdsCampaign.workspace_id == ws.id)
    ).scalars().all()
    return {"campaigns": [{
        "id": c.id, "external_id": c.external_id, "name": c.name, "format_key": c.format_key,
        "status": c.status, "currency": c.currency, "data_label": c.data_label,
    } for c in camps],
        "note": "Actual advertising metrics from your authorized Google Ads account (LIVE DATA). "
                "Organic YouTube statistics are never shown here."}


@router.get("/google/performance")
def google_performance(days: int = Query(default=90, le=180),
                      user: User = Depends(get_current_user), ws: Workspace = Depends(get_workspace),
                      db: Session = Depends(get_db)):
    """Aggregated ACTUAL Google Ads video-campaign performance (LIVE DATA only)."""
    conn = oauth.get_connection(db, ws.id)
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    if conn is None:
        return {"rows": [], "campaigns": 0, "range": f"{start.isoformat()}..{end.isoformat()}",
                "data_label": "LIVE DATA", "note": "No Google connection for this workspace."}
    rows = db.execute(
        select(AdsCampaignPerformance, AdsCampaign)
        .join(AdsCampaign, AdsCampaignPerformance.campaign_pk == AdsCampaign.id)
        .where(AdsCampaign.workspace_id == ws.id, AdsCampaignPerformance.date >= start)
        .order_by(AdsCampaignPerformance.date.desc())
    ).all()
    agg: dict[int, dict] = {}
    for perf, camp in rows:
        a = agg.setdefault(camp.id, {
            "campaign": camp, "impressions": 0, "clicks": 0, "cost_micros": 0,
            "conversions": 0.0, "conversion_value": 0.0, "video_views": 0,
        })
        a["impressions"] += perf.impressions
        a["clicks"] += perf.clicks
        a["cost_micros"] += perf.cost_micros
        a["conversions"] += perf.conversions
        a["conversion_value"] += perf.conversion_value
        a["video_views"] += perf.video_views
    out = []
    for a in agg.values():
        camp: AdsCampaign = a["campaign"]
        cost = a["cost_micros"] / 1_000_000.0
        impressions, clicks = a["impressions"], a["clicks"]
        conversions, cval = a["conversions"], a["conversion_value"]
        out.append({
            "id": camp.id, "external_id": camp.external_id, "name": camp.name,
            "format_key": camp.format_key, "status": camp.status,
            "currency": camp.currency or ws.currency,
            "impressions": impressions, "clicks": clicks, "cost": round(cost, 2),
            "conversions": round(conversions, 2), "conversion_value": round(cval, 2),
            "video_views": a["video_views"],
            "ctr": round((clicks / impressions * 100) if impressions else 0.0, 2),
            "cvr": round((conversions / clicks * 100) if clicks else 0.0, 2),
            "cpa": round((cost / conversions) if conversions else 0.0, 2),
            "roas": round((cval / cost) if cost else 0.0, 2),
            "data_label": "LIVE DATA",
        })
    out.sort(key=lambda r: r["cost"], reverse=True)
    return {"rows": out, "campaigns": len(out), "range": f"{start.isoformat()}..{end.isoformat()}",
            "data_label": "LIVE DATA",
            "note": "Actual Google Ads VIDEO campaign metrics synced from your authorized account."}
