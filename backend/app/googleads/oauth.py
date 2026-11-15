"""Google OAuth 2.0 (authorization-code, offline access) — per workspace.

Scopes: userinfo.email (identity) + adwords (Google Ads reporting).
Refresh tokens are stored encrypted (per workspace) and never returned to
the frontend. OAuth state is stored in the database-backed KV so it works
across processes.
"""
from __future__ import annotations

import logging
import secrets

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models.campaign import GoogleConnection

logger = logging.getLogger(__name__)

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/adwords",
]

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"

_states: set[str] = set()


class OAuthNotConfigured(Exception):
    pass


def is_configured() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def app_missing_requirements() -> list[str]:
    return [
        name for name, val in {
            "GOOGLE_CLIENT_ID": settings.GOOGLE_CLIENT_ID,
            "GOOGLE_CLIENT_SECRET": settings.GOOGLE_CLIENT_SECRET,
        }.items() if not val
    ]


def build_authorization_url(workspace_id: str) -> tuple[str, str]:
    if not is_configured():
        raise OAuthNotConfigured(
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not configured (backend/.env)."
        )
    state = secrets.token_urlsafe(24) + "." + workspace_id
    _states.add(state)
    from urllib.parse import urlencode

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_ENDPOINT}?{urlencode(params)}", state


def consume_state(state: str) -> str | None:
    """Returns the workspace_id encoded in the state, or None."""
    if state in _states:
        _states.discard(state)
        return state.split(".", 1)[1] if "." in state else None
    return None


def get_connection(db: Session, workspace_id: str) -> GoogleConnection | None:
    return db.execute(
        select_connection(workspace_id)
    ).scalar_one_or_none()


def select_connection(workspace_id: str):
    from sqlalchemy import select

    return select(GoogleConnection).where(GoogleConnection.workspace_id == workspace_id)


def ensure_connection(db: Session, workspace_id: str) -> GoogleConnection:
    conn = get_connection(db, workspace_id)
    if conn is None:
        conn = GoogleConnection(workspace_id=workspace_id)
        db.add(conn)
        db.commit()
        db.refresh(conn)
    return conn


def store_tokens(db: Session, conn: GoogleConnection, tokens: dict, email: str = "", customer_id: str = "") -> None:
    if tokens.get("refresh_token"):
        conn.refresh_token_encrypted = encrypt_secret(tokens["refresh_token"])
    if email:
        conn.email = email
    if customer_id:
        conn.customer_id = customer_id
    conn.status = "connected"
    conn.connected_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    db.commit()


def get_refresh_token(conn: GoogleConnection) -> str:
    return decrypt_secret(conn.refresh_token_encrypted)


def refresh_access_token(refresh_token: str) -> dict:
    if not is_configured():
        raise OAuthNotConfigured("OAuth client is not configured.")
    resp = requests.post(TOKEN_ENDPOINT, data={
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def access_token_from_connection(conn: GoogleConnection) -> str:
    rt = get_refresh_token(conn)
    if not rt:
        raise OAuthNotConfigured("No Google refresh token stored for this workspace — connect first.")
    return refresh_access_token(rt).get("access_token", "")


def fetch_userinfo(access_token: str) -> dict:
    resp = requests.get(USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    resp.raise_for_status()
    return resp.json()
