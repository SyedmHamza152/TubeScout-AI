"""Application configuration.

All settings come from environment variables (backend/.env when present).
Secrets are never hardcoded. Database is PostgreSQL ONLY:
  - DATABASE_URL: runtime connections (Neon pooled endpoint in production)
  - DIRECT_URL:   Alembic migrations (Neon direct endpoint in production)
No SQLite fallback exists anywhere in this codebase.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


def _env_file_value(key: str) -> str | None:
    """Read a key from backend/.env (highest trust for DB endpoints)."""
    try:
        for line in (BACKEND_DIR / ".env").read_text().splitlines():
            if line.strip().startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


def _postgres_or_env_file(inherited: str, key: str) -> str:
    """Policy: DATABASE_URL/DIRECT_URL must be PostgreSQL (Neon in production).

    Some hosts export unrelated DATABASE_URL values (e.g. sandbox defaults for
    other frameworks); those are ignored in favour of backend/.env.
    """
    if inherited.startswith("postgresql"):
        return inherited
    from_file = _env_file_value(key)
    if from_file and from_file.startswith("postgresql"):
        return from_file
    return inherited


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    APP_NAME: str = "AudienceLens"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "YouTube Audience & Campaign Intelligence Platform"
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "sandbox"

    BACKEND_PORT: int = 8321

    # --- Database: PostgreSQL only (Neon in production) ---
    DATABASE_URL: str = "postgresql+psycopg://audlens:audlens@127.0.0.1:5433/audlens"
    DIRECT_URL: str = ""  # falls back to DATABASE_URL when unset

    @model_validator(mode="after")
    def _force_postgres_db_urls(self) -> "Settings":
        self.DATABASE_URL = _postgres_or_env_file(self.DATABASE_URL, "DATABASE_URL")
        self.DIRECT_URL = _postgres_or_env_file(self.DIRECT_URL, "DIRECT_URL")
        return self

    # --- Security ---
    SECRET_KEY: str = "audlens-dev-secret-change-me"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7

    # --- YouTube Data API v3 ---
    YOUTUBE_API_KEY: str = ""
    YOUTUBE_DAILY_QUOTA: int = 10000  # default quota for a fresh Google Cloud project

    # --- Google Ads (per-workspace OAuth; developer token is app-level) ---
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_ADS_DEVELOPER_TOKEN: str = ""
    OAUTH_REDIRECT_URI: str = "http://localhost:8321/api/v1/integrations/google/callback"

    # --- LLM (research agent brain) ---
    # Option A: OpenAI-compatible endpoint
    LLM_API_BASE: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    # Option B: local Next.js bridge route backed by z-ai-web-dev-sdk
    LLM_BRIDGE_URL: str = "http://127.0.0.1:3000/api/llm/chat"
    LLM_TIMEOUT_SECONDS: float = 60.0

    # --- Collection defaults (per research session) ---
    DEFAULT_MAX_VIDEOS: int = 40
    DEFAULT_MAX_COMMENTS_PER_VIDEO: int = 60
    DEFAULT_COMMENT_TOTAL_CAP: int = 2000
    MAX_VIDEOS_HARD_CAP: int = 200
    MAX_COMMENTS_HARD_CAP: int = 10000

    # --- Refresh scheduler ---
    REFRESH_ENABLED: bool = True
    REFRESH_INTERVAL_MINUTES: int = 360

    # --- Market defaults ---
    DEFAULT_MARKET: str = "PK"
    DEFAULT_CURRENCY: str = "PKR"

    # --- Embedding provider ---
    # hashing  -> deterministic sklearn HashingVectorizer+SVD (always available)
    # st       -> sentence-transformers (optional, only if installed)
    EMBEDDING_PROVIDER: str = "hashing"
    EMBEDDING_MODEL: str = "paraphrase-multilingual-mpnet-base-v2"
    EMBEDDING_DIM: int = 128

    # --- Paths ---
    DATA_DIR: str = str(BACKEND_DIR / "data")

    @property
    def direct_url(self) -> str:
        return self.DIRECT_URL or self.DATABASE_URL


settings = Settings()
