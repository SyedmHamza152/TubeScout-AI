"""LLM client for the research agent.

Provider priority:
  1. OpenAI-compatible endpoint (LLM_API_BASE + LLM_API_KEY) — production.
  2. Local Next.js bridge route backed by z-ai-web-dev-sdk (sandbox default).
  3. None available → callers MUST use the deterministic fallback paths.

The LLM is used ONLY for understanding, planning suggestions and grounded
explanations. It never executes SQL or raw API calls — backend tools do.
"""
from __future__ import annotations

import json
import logging
import re

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


def _openai_chat(messages: list[dict], json_mode: bool) -> str | None:
    base = settings.LLM_API_BASE.rstrip("/")
    resp = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
        json={
            "model": settings.LLM_MODEL,
            "messages": messages,
            "temperature": 0.3,
            **({"response_format": {"type": "json_object"}} if json_mode else {}),
        },
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _bridge_chat(messages: list[dict], json_mode: bool) -> str | None:
    resp = requests.post(
        settings.LLM_BRIDGE_URL,
        json={"messages": messages, "json_mode": json_mode},
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json().get("content")


def available() -> bool:
    try:
        chat([{"role": "user", "content": "ping"}], timeout_short=True)
        return True
    except Exception:
        return False


def chat(messages: list[dict], json_mode: bool = False, timeout_short: bool = False) -> str | None:
    """Returns content or None when no LLM is available (callers fall back)."""
    timeout = settings.LLM_TIMEOUT_SECONDS
    if settings.LLM_API_BASE and settings.LLM_API_KEY:
        try:
            return _openai_chat(messages, json_mode)
        except Exception as exc:
            logger.warning("OpenAI-compatible LLM failed: %s", exc)
            return None
    if settings.LLM_BRIDGE_URL:
        try:
            return _bridge_chat(messages, json_mode)
        except Exception as exc:
            logger.warning("LLM bridge failed: %s", exc)
            return None
    return None


def chat_json(messages: list[dict]) -> dict | None:
    raw = chat(messages, json_mode=True)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None
