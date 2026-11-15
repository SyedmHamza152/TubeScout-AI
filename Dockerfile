FROM node:22-bookworm AS deps
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip && \
    rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json* ./
RUN npm ci
COPY backend/requirements.txt ./backend/requirements.txt
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r backend/requirements.txt

FROM node:22-bookworm AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-bookworm AS runner
WORKDIR /app
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    BACKEND_URL=http://127.0.0.1:8321 \
    PYTHONUNBUFFERED=1
COPY --from=deps /opt/venv /opt/venv
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/backend ./backend
EXPOSE 3000 8321
CMD ["sh", "-c", "cd /app/backend && (/opt/venv/bin/python -m alembic upgrade head || true) && /opt/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8321 & cd /app && exec node server.js"]
