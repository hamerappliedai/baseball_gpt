# One-off database jobs: bootstrap, roles, migrations and the data pipeline
# (download Lahman, load raw, dbt, embeddings). Runs against any Postgres given
# libpq settings (PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE); see deploy/ops.sh.
#   docker build -f deploy/ops.Dockerfile -t baseball-gpt-ops .
#   docker run --rm -e PGHOST=... baseball-gpt-ops first-load

FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /usr/local/bin/uv

# psql runs db/bootstrap.sql and db/roles.sql (it uses psql's \gexec and variables).
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf \
    EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2 \
    BGPT_CACHE_DIR=/tmp/lahman

WORKDIR /app

# dbt in its own virtualenv, pinned by transform/uv.lock.
COPY transform/pyproject.toml transform/uv.lock /app/transform/
RUN cd /app/transform \
 && uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/dbt.txt \
 && uv venv /opt/dbt \
 && uv pip install --python /opt/dbt/bin/python --no-cache -r /tmp/dbt.txt

# The pipeline, editable so it finds db/migrations and pipeline/releases in /app.
# CPU-only torch, as in the app image.
COPY pipeline/ /app/pipeline/
RUN uv pip install --system --no-cache --torch-backend cpu -e /app/pipeline
RUN python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer(os.environ['EMBED_MODEL'], device='cpu')"
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

COPY transform/ /app/transform/
COPY db/ /app/db/
COPY deploy/ops.sh /usr/local/bin/ops

RUN useradd --system --uid 10001 --create-home ops \
 && chown -R ops /app/transform \
 && chmod -R a+rX /opt/hf
USER ops

ENTRYPOINT ["ops"]
CMD ["help"]
