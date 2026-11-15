"""Policy tests: provenance labels, no demo/synthetic entry points."""
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[1]

FORBIDDEN_SNIPPETS = [
    "SYNTHETIC DEMO DATA",
    "demo_seeder",
    "seed_if_empty",
    "innertube",
    "youtubei/v1",
    "sqlite://",
]


def test_no_synthetic_or_demo_code():
    offenders = []
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or "alembic/versions" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for snippet in FORBIDDEN_SNIPPETS:
            if snippet in text:
                offenders.append(f"{path.name}: {snippet}")
    assert offenders == [], f"Forbidden demo/synthetic/scraping code found: {offenders}"


def test_database_url_is_postgres_only():
    from app.core.config import settings

    assert settings.DATABASE_URL.startswith("postgresql"), "DATABASE_URL must be PostgreSQL"
    assert settings.direct_url.startswith("postgresql"), "DIRECT_URL must be PostgreSQL"


def test_db_engine_rejects_sqlite():
    from app.core.db import _make_engine

    try:
        _make_engine("sqlite:///tmp/test.db")
        raise AssertionError("SQLite engine creation must be rejected")
    except RuntimeError:
        pass
