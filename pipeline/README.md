# Data pipeline

Turns the SABR Lahman Baseball Database into a Postgres warehouse that the chat
backend can query.

```
download → verify → load raw → transform (phase 2) → embed (phase 4)
```

Phase 1, in this package, covers the first three stages.

## Run it

```bash
make build        # starts Postgres, then downloads, verifies and loads release 2025
make test         # unit tests + integration tests against the docker Postgres
make db-shell     # psql into the warehouse
```

Postgres runs from `docker-compose.yml` (image `pgvector/pgvector:pg17`) on host
port **5432**. Connection settings live in the repo-root `.env` (copy it from
[`.env.example`](../.env.example)), which docker compose, the Makefile and the pipeline
all read. The pipeline connects with `DATABASE_URL`.

## Stages

**Download.** SABR publishes each release as a public Box folder. Box has no
unauthenticated API for folders, so the pipeline downloads each file by its Box
file id via Box's shared-file endpoint. Files are cached in `.cache/lahman/<release>/`
(git-ignored) and written atomically, so a crash never leaves a half-written file.

**Verify.** SABR publishes no checksums, so the pipeline pins its own:
[`releases/2025.json`](releases/2025.json) records each file's Box id, size,
SHA-256, CSV header and row count. Every download and every load is checked
against it, and a cached file that fails is downloaded again. A file that changes
upstream fails the build instead of quietly changing the answers.

**Load raw.** Every CSV becomes a table in the `raw` schema, in one transaction
(readers see the old data until the new load commits; a failure rolls back the
whole thing). Raw is deliberately a faithful copy:

- every column is `text`, names are only lowercased (`2B` → `"2b"`); typing and
  renaming belong in staging, where a bad cast can't lose data on the way in;
- the UTF-8 byte-order mark on `People.csv`, `Teams.csv` and others is stripped
  (otherwise the first column would be named `﻿id`);
- empty fields become `NULL`: a pre-1954 batter's sacrifice flies are unknown, not 0;
- loaded row counts are checked against the manifest;
- `raw._load_log` records the release, file, hash and row count behind each table.

## Pinning a new release

When SABR publishes the next release, take the folder id from the "Comma-delimited
version" link on <https://sabr.org/lahman-database/> (`sabr.box.com/s/<id>`):

```bash
cd pipeline && uv run bgpt-pipeline discover --release 2026 --box-shared-name <id>
```

`discover` lists the folder, downloads everything and writes `releases/2026.json`.
It fails if any table disappeared, lost columns, or shrank by more than 10% since the
previous release, because Lahman only adds history. Review the manifest diff and commit it.
