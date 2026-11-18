# The web app: FastAPI backend + built Vue frontend + the search embedding model.
#   docker build -f deploy/app.Dockerfile -t baseball-gpt-app .
# Settings come from the environment (see .env.example); nothing secret is baked in.

# --- 1. Build the Vue app --------------------------------------------------------
FROM node:22-bookworm-slim AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. Python runtime -----------------------------------------------------------
FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf \
    EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2

# CPU-only torch: the GPU build is several GB larger and there's no GPU on Fargate.
COPY backend/requirements.txt /tmp/requirements.txt
RUN uv pip install --system --no-cache --torch-backend cpu -r /tmp/requirements.txt

# Bake the embedding model into the image so tasks never download it at start-up.
RUN python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer(os.environ['EMBED_MODEL'], device='cpu')" \
 && chmod -R a+rX /opt/hf
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

WORKDIR /app/backend
COPY backend/ ./
COPY --from=web /src/frontend/dist /app/frontend/dist

RUN useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
# One worker per task: scale with more tasks, not processes (the model is ~100 MB per process).
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
