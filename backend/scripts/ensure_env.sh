#!/usr/bin/env bash
# AudienceLens environment bootstrap (idempotent).
# Starts the sandbox PostgreSQL (pgserver) and applies Alembic migrations.
# In production, point DATABASE_URL/DIRECT_URL at Neon and skip pgserver.
set -u
cd "$(dirname "$0")/.."

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://audlens:audlens@127.0.0.1:5433/audlens}"
export DIRECT_URL="${DIRECT_URL:-$DATABASE_URL}"

# 1. start embedded PostgreSQL if the sandbox port is closed
if ! (exec 3<>/dev/tcp/127.0.0.1/5433) 2>/dev/null; then
  python3 scripts/start_pg.py >> /tmp/audlens_pg.log 2>&1 || true
  for i in $(seq 1 30); do
    (exec 3<>/dev/tcp/127.0.0.1/5433) 2>/dev/null && break
    sleep 1
  done
fi

# 2. migrations
if alembic upgrade head >> /tmp/audlens_migrate.log 2>&1; then
  echo "migrations: ok"
else
  echo "migrations: FAILED (see /tmp/audlens_migrate.log)"
  exit 1
fi

# 3. sanity check the API URL
python3 - <<'PY'
import os
from sqlalchemy import create_engine, text
url = os.environ["DATABASE_URL"].replace("+psycopg", "+psycopg")
engine = create_engine(url, pool_pre_ping=True)
with engine.connect() as conn:
    conn.execute(text("SELECT 1"))
print("database: ok")
PY
