"""AudienceLens FastAPI application entrypoint."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import agent, audience, auth, campaigns, competitors, findings, integrations, research
from app.core.config import settings
from app.core.db import check_database

logging.basicConfig(level=settings.LOG_LEVEL,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = "/api/v1"
app.include_router(auth.router, prefix=API)
app.include_router(agent.router, prefix=API)
app.include_router(research.router, prefix=API)
app.include_router(audience.router, prefix=API)
app.include_router(competitors.router, prefix=API)
app.include_router(campaigns.router, prefix=API)
app.include_router(integrations.router, prefix=API)
app.include_router(findings.router, prefix=API)


@app.get("/")
def root():
    return {
        "ok": True,
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "health": "/api/v1/health",
        "docs": "/docs",
    }


@app.get("/api/v1/health")
def health():
    return {
        "ok": True,
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": "connected" if check_database() else "disconnected",
        "youtube_api": bool(settings.YOUTUBE_API_KEY),
        "google_oauth": bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET),
        "llm_configured": bool(settings.LLM_API_BASE or settings.LLM_BRIDGE_URL),
    }


@app.on_event("startup")
def _startup() -> None:
    from app.jobs.scheduler import start_scheduler

    start_scheduler()
