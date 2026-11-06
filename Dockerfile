# Project Two Lead Hunter – jeden kontejner (Next.js frontend + FastAPI backend + worker + plánovač)
# Použití: Hugging Face Spaces (port 7860), Render, VPS…  Viz DEPLOY.md

# ---------- 1) build frontendu ----------
FROM node:22-bookworm-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build && npm prune --omit=dev

# ---------- 2) runtime ----------
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    NEXT_TELEMETRY_DISABLED=1 \
    LEADHUNTER_IN_DOCKER=1 \
    DATA_DIR=/app/data \
    PORT=7860

RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*
COPY --from=web /usr/local/bin/node /usr/local/bin/node

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY backend/ backend/
COPY --from=web /app/frontend frontend
COPY deploy/start.sh /app/start.sh

# Hugging Face Spaces spouští kontejner jako uživatel 1000
RUN useradd -m -u 1000 user \
    && mkdir -p /app/data \
    && chown -R user:user /app/data /app/frontend/.next \
    && chmod -R a+rX /ms-playwright
USER user

EXPOSE 7860
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||7860)+'/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["bash", "/app/start.sh"]
