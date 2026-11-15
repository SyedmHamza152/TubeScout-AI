"""Google Ads API client — YouTube video campaign reporting via GAQL.

Scope & honesty rules:
  * only VIDEO advertising-channel campaigns are fetched (YouTube inventory);
    Search / Display / Performance Max rows are filtered OUT by the query.
  * cost arrives in micros and is converted at this boundary.
  * per-workspace credentials (OAuth refresh token + customer id).
  * missing credentials or permission errors are typed errors — the app
    then clearly reports that ACTUAL campaign data is unavailable. It never
    substitutes organic YouTube stats for advertising metrics.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import SUBTYPE_TO_FORMAT
from app.googleads import oauth

logger = logging.getLogger(__name__)

GAQL_DAILY = """
SELECT
  campaign.id, campaign.name, campaign.status,
  campaign.advertising_channel_type, campaign.advertising_channel_subtype,
  segments.date,
  metrics.impressions, metrics.clicks, metrics.cost_micros,
  metrics.conversions, metrics.conversions_value, metrics.video_views,
  metrics.video_view_rate, metrics.ctr, metrics.average_cpc, metrics.average_cpv,
  metrics.cost_per_conversion
FROM campaign
WHERE campaign.advertising_channel_type = 'VIDEO'
  AND metrics.impressions > 0
  AND segments.date BETWEEN '{start}' AND '{end}'
ORDER BY segments.date DESC
"""

GAQL_CAMPAIGN_SUMMARY = """
SELECT
  campaign.id, campaign.name, campaign.status,
  campaign.advertising_channel_type, campaign.advertising_channel_subtype,
  metrics.impressions, metrics.clicks, metrics.cost_micros,
  metrics.conversions, metrics.conversions_value, metrics.video_views
FROM campaign
WHERE campaign.advertising_channel_type = 'VIDEO'
  AND metrics.impressions > 0
  AND segments.date DURING LAST_90_DAYS
"""


class GoogleAdsNotConfigured(Exception):
    pass


class GoogleAdsError(Exception):
    pass


def workspace_requirements(conn) -> list[str]:
    missing = oauth.app_missing_requirements()
    if not (conn and oauth.get_refresh_token(conn)):
        missing.append("workspace Google OAuth connection (refresh token)")
    if not (conn and conn.customer_id):
        missing.append("Google Ads customer ID")
    return missing


@dataclass
class AdsRow:
    campaign_id: str
    campaign_name: str
    status: str
    channel_type: str
    channel_subtype: str
    format_key: str
    date: str | None
    impressions: int
    clicks: int
    cost_units: float
    conversions: float
    conversion_value: float
    video_views: int
    video_view_rate: float
    ctr: float
    avg_cpc: float
    avg_cpv: float
    cost_per_conversion: float


def _load_client(conn):
    missing = workspace_requirements(conn)
    if missing:
        raise GoogleAdsNotConfigured("Google Ads API not fully configured. Missing: " + "; ".join(missing))
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError as e:
        raise GoogleAdsError("google-ads client library is not installed. Run: pip install google-ads") from e
    credentials = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": oauth.get_refresh_token(conn),
        "use_proto_plus": True,
    }
    if settings.GOOGLE_ADS_DEVELOPER_TOKEN:
        credentials["developer_token"] = settings.GOOGLE_ADS_DEVELOPER_TOKEN
    try:
        return GoogleAdsClient.load_from_dict(credentials)
    except Exception as e:
        typed = _typed_error(e)
        raise GoogleAdsError(str(typed)) from e


def _classify_format(subtype: str, name: str) -> str:
    base = SUBTYPE_TO_FORMAT.get(subtype, "in_stream")
    if base == "in_stream":
        lowered = name.lower()
        if "short" in lowered:
            return "shorts"
        if "feed" in lowered or "discovery" in lowered:
            return "in_feed"
    return base


def _row_to_ads_row(row, with_date: bool) -> AdsRow:
    camp, met = row.campaign, row.metrics
    return AdsRow(
        campaign_id=str(camp.id),
        campaign_name=str(camp.name),
        status=str(camp.status).split(".")[-1] if str(camp.status) else "UNKNOWN",
        channel_type=str(camp.advertising_channel_type),
        channel_subtype=str(camp.advertising_channel_subtype or ""),
        format_key=_classify_format(str(camp.advertising_channel_subtype or ""), str(camp.name)),
        date=str(row.segments.date) if with_date else None,
        impressions=int(met.impressions),
        clicks=int(met.clicks),
        cost_units=float(met.cost_micros) / 1_000_000.0,
        conversions=float(met.conversions),
        conversion_value=float(met.conversions_value),
        video_views=int(met.video_views),
        video_view_rate=float(met.video_view_rate),
        ctr=float(met.ctr),
        avg_cpc=float(met.average_cpc) / 1_000_000.0,
        avg_cpv=float(met.average_cpv) / 1_000_000.0,
        cost_per_conversion=float(met.cost_per_conversion) / 1_000_000.0,
    )


def _customer_id(conn) -> str:
    return (conn.customer_id or "").replace("-", "")


def fetch_campaign_summary(conn) -> list[AdsRow]:
    client = _load_client(conn)
    ga = client.get_service("GoogleAdsService")
    query = GAQL_CAMPAIGN_SUMMARY
    try:
        stream = ga.search(customer_id=_customer_id(conn), query=query)
        return [_row_to_ads_row(r, with_date=False) for r in stream]
    except Exception as e:
        raise _typed_error(e)


def fetch_daily_performance(conn, start: str, end: str) -> list[AdsRow]:
    client = _load_client(conn)
    ga = client.get_service("GoogleAdsService")
    query = GAQL_DAILY.format(start=start, end=end)
    try:
        stream = ga.search(customer_id=_customer_id(conn), query=query)
        return [_row_to_ads_row(r, with_date=True) for r in stream]
    except Exception as e:
        raise _typed_error(e)


def _typed_error(e: Exception) -> Exception:
    msg = str(e)
    if "PERMISSION_DENIED" in msg or "USER_PERMISSION" in msg:
        return GoogleAdsError(
            "Permission denied — the authenticated Google account cannot access this customer id, "
            "or the developer token lacks approved access."
        )
    if "AUTHENTICATION_ERROR" in msg or "invalid_grant" in msg or "unauthorized_client" in msg or "RefreshError" in msg:
        return GoogleAdsError("Authentication failed — refresh the OAuth connection.")
    if "QUOTA" in msg or "RESOURCE_EXHAUSTED" in msg:
        return GoogleAdsError("Google Ads API quota exhausted — retry later.")
    return GoogleAdsError(f"Google Ads API error: {msg[:400]}")


def test_connection(conn) -> dict:
    try:
        client = _load_client(conn)
    except (GoogleAdsNotConfigured, GoogleAdsError) as e:
        return {"ok": False, "status": "not_configured", "detail": str(e)}
    ga = client.get_service("GoogleAdsService")
    try:
        stream = ga.search(customer_id=_customer_id(conn), query=GAQL_CAMPAIGN_SUMMARY)
        count = sum(1 for _ in stream)
        return {"ok": True, "status": "connected", "video_campaigns_last_90d": count,
                "customer_id": _customer_id(conn), "data_label": "LIVE DATA"}
    except Exception as e:
        return {"ok": False, "status": "error", "detail": str(_typed_error(e))[:400]}
