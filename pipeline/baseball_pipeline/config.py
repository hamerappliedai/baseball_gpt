"""Paths and connection settings, overridable through environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

PIPELINE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PIPELINE_DIR.parent

# The repo-root .env, shared with docker compose. Variables already set in the
# shell take precedence over the file.
load_dotenv(REPO_ROOT / ".env")

# Pinned per-release manifests (committed). One JSON file per release year.
RELEASES_DIR = PIPELINE_DIR / "releases"

# Downloaded CSVs (git-ignored). <cache>/<release>/<file>.
CACHE_DIR = Path(os.environ.get("BGPT_CACHE_DIR", REPO_ROOT / ".cache" / "lahman"))

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://bgpt:bgpt@localhost:5432/baseball"
)

RAW_SCHEMA = "raw"
