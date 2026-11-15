"""SQLAlchemy 2.x engine/session — PostgreSQL only.

DATABASE_URL (pooled runtime) and DIRECT_URL (migrations) target Neon in
production. There is deliberately no SQLite path.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    if not url.startswith("postgresql"):
        raise RuntimeError(
            "AudienceLens requires PostgreSQL (DATABASE_URL must be a postgresql+psycopg:// URL). "
            "SQLite is not supported by policy."
        )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        connect_args={"sslmode": "prefer"},
    )


engine = _make_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
