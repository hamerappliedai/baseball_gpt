# Baseball GPT

Explore 150 years of major league baseball, Negro Leagues included, from the SABR
Lahman database. The site has two modes over the same documented Postgres marts:

- **Leaders** (`/leaders`): leaderboards served straight from SQL. No AI, so no token
  cost per visit.
- **Ask AI** (`/ask`): Claude writes and runs read-only queries, then answers from the
  results. Each question spends Claude API tokens.

A Vue 3 front end talks to a FastAPI backend. The plan for the token-free browse mode is
in [docs/browse-plan.md](docs/browse-plan.md).

```
baseball_gpt/
├── backend/            FastAPI app: browse API (browse.py, stats.py), Claude tool-use loop (agent.py),
│                       database access (db.py), schema prompt (schema.py)
├── frontend/           Vue 3 + Vite app: views/LeadersView.vue, views/AskView.vue, src/api.js
├── pipeline/           Downloads, verifies and loads the Lahman database (see pipeline/README.md)
├── transform/          dbt project: raw → staging → documented marts (see transform/README.md)
├── db/init/            Postgres init: pgvector extension and warehouse schemas
├── db/roles.sql        Read-only role the backend connects as
└── docker-compose.yml  Postgres 17 + pgvector on host port 5432
```

## Data

The corpus is the [SABR Lahman Baseball Database](https://sabr.org/lahman-database/)
(CC BY-SA 3.0). It is not committed to git. The pipeline downloads it and checks each
file against a pinned SHA-256 hash. With Docker running:

```bash
cp .env.example .env
```

Set `READER_PASSWORD` in `.env`, and the same password in `READER_DATABASE_URL`. Then:

```bash
make build
```

This downloads and verifies the release and loads it into `raw`. It then creates the
read-only role and builds and tests the `marts` tables with dbt. Details are in
[pipeline/README.md](pipeline/README.md) and [transform/README.md](transform/README.md).

## Setup

You need an Anthropic API key and Node 18+ (Vite 5 is pinned so Node 21 works).

Backend:

```bash
cd backend && uv venv .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
```

Put your key in `backend/.env` (git-ignored). The backend loads it at startup with
python-dotenv:

```bash
cp backend/.env.example backend/.env
```

Then edit `backend/.env` and set `ANTHROPIC_API_KEY=sk-ant-...`. The backend also reads
`READER_DATABASE_URL` from the repo-root `.env`. A variable already exported in your
shell takes precedence over both files.

Frontend:

```bash
cd frontend && npm install
```

## Run (development, with hot reload)

Terminal 1, the API on :8000:

```bash
cd backend && .venv/bin/python -m uvicorn app:app --reload --port 8000
```

Terminal 2, the UI on :5173 (it forwards `/api` to :8000):

```bash
cd frontend && npm run dev
```

Open http://localhost:5173. `GET /api/health` reports the model and whether the
database is reachable.

## Run (single server)

```bash
cd frontend && npm run build
```

```bash
cd backend && .venv/bin/python app.py
```

FastAPI serves the built UI from `frontend/dist`. Open http://localhost:8000.

## Tests

```bash
make test
```

```bash
make backend-test
```

`make test` runs the pipeline tests. `make backend-test` runs the backend tests:
- the SQL tool and the browse API run against the live database (these are skipped if
  it isn't running). The browse tests check known records and reject bad parameters;
- the tool-use loop runs against a scripted fake Claude client, so no API calls are made.

dbt data tests run as part of `make transform`.

## Browse API (no AI)

| Endpoint | Returns |
|---|---|
| `GET /api/meta` | season range, leagues, era presets and the stat catalogue, for the dropdowns |
| `GET /api/leaderboard` | a ranked leaderboard; ties share a rank |

`/api/leaderboard` takes these parameters:
- `category` (`batting`/`pitching`)
- `stat`
- `scope` (`season`/`career`)
- `from` and `to`
- `league` (`all`, `negro`, or a `league_id`)
- `qualified`
- `limit` (at most 100) and `offset`

Example: `/api/leaderboard?category=pitching&stat=era&from=1947`.

How it stays safe and fast:
- **No user SQL.** Each request runs a fixed, parameterized query as the same read-only
  `bgpt_reader` role. Stats and leagues are checked against an allow-list in
  `stats.py`, which holds only Lahman stats. Unknown values get a 422.
- **Qualification.** Rate stats (AVG, ERA, ...) always use the dbt qualification flags.
- **Caching.** Responses are cached in memory and sent with an `ETag` and
  `Cache-Control: public, max-age=3600` (`BROWSE_CACHE_SECONDS`), so a browser or CDN
  can reuse them.

The UI keeps every filter in the URL, so any leaderboard can be shared as a link.

## How Ask AI answers

1. **Schema prompt.** At startup, `schema.py` reads the table and column comments that
   dbt wrote to Postgres (`persist_docs`). It renders them into the system prompt, so
   the dbt docs are the single source of truth for what Claude knows about the data.
   Columns that appear with the same meaning in several tables go into a shared
   glossary instead of being repeated. The whole block is prompt-cached.
2. **Tool-use loop.** `agent.py` gives Claude one tool, `run_sql`, which takes
   `{purpose, query}`. It streams each response and runs the queries Claude asks for.
   It sends the results back, as one tool-result message per round, and repeats until
   Claude answers. After `MAX_TOOL_ROUNDS` rounds it sets `tool_choice: none` to force
   an answer.
3. **Query safety.** The backend connects as `bgpt_reader`, and that role's privileges
   are the security boundary:
   - it has `SELECT` on `marts` only, no access to `raw` or `staging`, and no `TEMP`/`CREATE`;
   - it is read-only by default.

   In addition, each query:
   - runs in a `READ ONLY` transaction that is always rolled back;
   - has a `statement_timeout`;
   - runs through a server-side cursor, so only a single `SELECT`/`VALUES` statement is
     accepted;
   - returns at most `SQL_MAX_ROWS` rows to Claude.

   Errors go back to Claude as tool errors so it can fix the query.
4. **Streaming to the UI.** The backend relays Server-Sent Events:
   - `text` chunks;
   - `query` and `query_result`, which the UI shows as a collapsible list of the SQL it
     ran, with row counts;
   - `error` and `done`.

   The front end reads the `fetch` body as a stream (`EventSource` can't POST), renders
   Markdown and sanitizes it with DOMPurify.

5. **Background knowledge, labeled.** Every statistic must come from a query. Claude may
   add short context the database can't hold, such as why something happened, events or
   nicknames, from its own knowledge. That context goes only in one blockquote that
   starts with "**Background (not from the database):**", and the UI styles it as a
   separate callout.

Other details:
- Tool inputs stream eagerly (`eager_input_streaming`) and are validated before running.
- Server-side refusal fallback (`fallbacks="default"`) is enabled.
- The conversation lives in the browser and is sent with every request. Nothing is
  stored on the server.

## Configuration

Set these in the environment or in `backend/.env`:

| Variable | Default | Notes |
|---|---|---|
| `CLAUDE_MODEL` | `claude-opus-5-5` | e.g. `claude-sonnet-5-5` for lower cost |
| `CLAUDE_EFFORT` | `medium` | `low` / `medium` / `high` / `xhigh` / `max` |
| `CLAUDE_MAX_TOKENS` | `64000` | per-reply output cap |
| `MAX_TOOL_ROUNDS` | `8` | query rounds before Claude must answer |
| `SQL_TIMEOUT_MS` | `5000` | per-query statement timeout |
| `SQL_MAX_ROWS` | `200` | rows returned to Claude per query |
| `BROWSE_CACHE_SECONDS` | `3600` | `Cache-Control` max-age for browse API responses |

These live in the repo-root `.env`:

| Variable | Notes |
|---|---|
| `READER_PASSWORD` | password for the `bgpt_reader` role, applied by `make db-up` / `make db-roles` |
| `READER_DATABASE_URL` | connection string the backend uses (must contain the same password) |
