# Plan: a no-LLM browse mode

Status: approved; milestones 1 (Browse API + Leaders page), 2 (player search + player pages) and 3 (standings) done. Decisions (2026-11-12):

- **Stats:** only what Lahman provides. Derived stats are computed from Lahman columns;
  nothing else is added (no WAR).
- **No franchise pages.**
- **Hosting:** AWS, with a real Postgres database (RDS). Deployment comes after phase 4.
- **Ask AI gating:** a login backed by a users table. See Accounts and gating.

## Goal

Most visitors should be able to explore the data without calling Claude, so that a
public deployment costs only hosting. The site gets two modes over the same `marts`
tables:

| Mode | What it does | Per-request cost |
|---|---|---|
| **Browse** (new, public) | leaderboards, player search, player pages, standings | none (SQL only) |
| **Ask AI** (existing, gated later) | Claude writes and runs SQL, then answers | Claude tokens |

Browse is also where phase 4's embeddings are shown off. The sentence-transformers model
runs on our own server, so nickname-aware search costs nothing per query.

## Principles

- **Users never send SQL.** Each endpoint runs a fixed, parameterized query. Values such
  as a stat or league that pick a column or table come from an allow-list in Python and
  are inserted with `psycopg.sql.Identifier`, never by string formatting.
- **Same safety boundary as the chat.** Queries connect as `bgpt_reader`: read-only
  transaction, statement timeout, `marts` only.
- **The marts are the API.** Browse pages read the dbt tables directly, with no new
  transforms, except possibly search indexes (see Search).
- **The data is static between releases**, so responses are cached hard (see Caching).

## Pages (frontend)

`vue-router` is added. The header gets navigation (**Leaders · Players · Standings · Ask
AI**) and a player search box that is always visible.

| Route | Page | Data |
|---|---|---|
| `/` | Home: search box, a few featured leaderboards, link to Ask AI | `/api/meta`, `/api/leaderboard` |
| `/leaders` | Leaderboard builder | `/api/leaderboard` |
| `/players/:playerId` | Player page | `/api/players/{id}` |
| `/standings/:season?` | Season standings and postseason | `/api/standings/{season}` |
| `/ask` | The current chat | `/api/chat` |

Filters are stored in the URL query string (e.g.
`/leaders?stat=hr&scope=season&from=1920&to=1960`), so every view can be shared as a
link. Player names in every table link to their player page.

### Leaderboard builder

Controls:
- **Category:** Batting or Pitching.
- **Stat:** from the stat catalogue.
- **Scope:** Single season or Career.
- **Seasons:** a from–to range, with presets: All, Modern (1947+), Live-ball
  (1920–1946), Dead-ball (1901–1919), 19th century.
- **League:** All, AL, NL, Negro Leagues, or one specific league.
- **Qualified only:** a toggle, forced on for rate stats.

The table has rank (ties share a rank), player, season or years, team(s), the stat
(highlighted) and supporting columns. For example, an HR board shows G, PA and HR; an
ERA board shows IP, W-L and ERA. It shows 50 rows with "load more".

### Player page

- **Header:** name, years active, position, bats/throws, born and died, Hall of Fame
  badge, a Negro Leagues badge where relevant, and teams.
- **Batting:** season-by-season table with a career totals row.
- **Pitching:** season-by-season table, shown only if the player pitched.
- **Fielding:** games by position, as a compact summary.
- **Postseason:** totals by round.
- **Honors:** awards, All-Star selections, top award-vote finishes, Hall of Fame voting
  history.
- An **"Ask AI about this player"** link prefills the chat. It is gated like the rest of
  Ask AI.

### Standings

- **Selector:** pick a season.
- **Standings:** grouped by league and then division, with W, L, PCT, GB, run
  differential and Pythagorean W-L.
- **Postseason:** bracket for that year, from `postseason_series`.
- **Teams:** each team links to a filtered leaderboard
  (`/leaders?team=NYA&season=1927`). That filter is a later addition.

## API (backend)

All endpoints are new, in a `backend/browse.py` `APIRouter` mounted at `/api`. Responses
are typed with Pydantic models. Invalid parameters return 422.

### `GET /api/meta`

Feeds the dropdowns on every page:
- the season range (1871–2025);
- leagues from `leagues`, with `is_negro_leagues` and `is_independent_clubs`;
- the stat catalogue: key, label, category, format, sort direction and whether it is a
  rate stat.

### `GET /api/leaderboard`

| Param | Values | Default |
|---|---|---|
| `category` | `batting` \| `pitching` | `batting` |
| `stat` | key from the catalogue | `hr` / `so` |
| `scope` | `season` \| `career` | `season` |
| `from`, `to` | 1871–2025 | full range |
| `league` | `all` \| `negro` \| a `league_id` | `all` |
| `qualified` | bool | true for rate stats |
| `limit`, `offset` | ≤ 100 | 50, 0 |

Which table answers each query:

| scope | league filter | table |
|---|---|---|
| season | `all` | `batting_seasons` / `pitching_seasons` |
| season | specific or `negro` | `batting_league_seasons` / `pitching_league_seasons` |
| career | any | `batting_careers` / `pitching_careers` |

Qualification:
- Season rate stats filter on `qualifies_batting_title` / `qualifies_era_title`.
- Career rate stats filter on `qualifies_career_leaders`.

The `*_league_seasons` tables are needed for league filters because a player traded
between leagues in one season qualifies per league (the dbt rule).

Limitations:
- Career boards cover whole careers. The year range keeps players whose careers overlap
  it (`first_season <= to AND last_season >= from`); it does not trim their totals to
  that window. The UI says so.
- A true "career totals within an era" board would need aggregating `*_seasons` on the
  fly. That is possible later but not in v1.

Ranking is `RANK() OVER (ORDER BY stat <dir>)`, so ties share a rank. `NULLS LAST`
always.

**Stat catalogue (v1).** It lives in Python and is served by `/api/meta`.

- **Batting.** Counting stats: G, PA, H, 2B, 3B, HR, R, RBI, SB, BB, SO, TB. Rate stats:
  AVG, OBP, SLG, OPS.
- **Pitching.** Counting stats: W, SV, G, GS, CG, SHO, IP (sorted on `ipouts`), SO.
  Rate stats: ERA, WHIP, SO/9, BB/9, SO/BB, W-L%. ERA, WHIP and BB/9 sort ascending.

Formatting is done on the client: `.300` for averages, two decimals for ERA and WHIP,
`ip_display` for innings.

### `GET /api/players?q=...&limit=10`

Typeahead search. It returns `player_id`, `full_name`, `first_season`–`last_season`,
`primary_position`, `teams` and `is_hall_of_famer`.

In v1 the search is SQL only. Each match gets a rank, best first:
1. exact `full_name`;
2. `name_last` prefix;
3. `full_name` `ILIKE '%q%'`;
4. `name_given` match (for example "George Herman").

Ties break on `games_played DESC`, so the famous player comes first.

To keep this fast, a `pg_trgm` GIN index on `players.full_name` would be created by a
dbt post-hook. The extension goes in `db/init`. At 24k rows, plain `ILIKE` is probably
fast enough, so we measure first.

Phase 4 keeps the same contract but swaps the implementation. See Search below.

### `GET /api/players/{player_id}`

One response with a section per table. All queries share one connection and one
read-only transaction.

- `players` row (bio, HOF, Negro Leagues flag)
- `batting_seasons` + `batting_careers`
- `pitching_seasons` + `pitching_careers`
- `fielding_seasons` grouped by position
- `postseason_batting` / `postseason_pitching` grouped by `season`, `round_name`
- `awards`, `all_star_selections`, `award_voting` (top-5 finishes), `hall_of_fame_voting`

It returns 404 for an unknown id.

### `GET /api/standings/{season}`

- `team_seasons` for the season, ordered by league, division and rank. GB is computed in
  SQL against the division leader.
- `postseason_series` for that season, ordered by `stage_order`.

### Database access

`db.run_query` stays as Claude's path: arbitrary SQL through a named cursor. A new
`db.fetch(sql, params) -> list[dict]` serves the parameterized browse queries. It uses
the same pool, `READ ONLY` transaction and timeout, with `psycopg.rows.dict_row`.

### Caching

- **In the backend:** an in-memory LRU cache (`functools`-style, keyed on validated
  params) for leaderboards, players and standings. It is bounded by entry count and
  cleared on restart. A data reload means a restart anyway.
- **In HTTP:** `Cache-Control: public, max-age=86400`, plus an `ETag` built from the
  loaded release (`raw._load_log`). A CDN in front would then absorb most traffic.

## Search: v1, then phase 4

The search endpoint's contract never changes; only the matching improves.

1. **v1 (this plan):** SQL ranking, as above.
2. **Phase 4, baseline:** a `vectors.player_aliases` table built by a pipeline step.
   - It holds one row per alias: full name, given name, "First Last" variants, and
     nicknames where we have a source.
   - Each row has an embedding (`vector(384)`) from a small pretrained
     sentence-transformers model with an HNSW index.
   - A search embeds the query once and combines nearest neighbours with the SQL match
     (hybrid ranking).
3. **Phase 5:** fine-tune the model on name/alias pairs, then show measured gains over
   the baseline (recall@k on a held-out set) on an about page.

The embedding model runs inside the backend process on CPU. This affects deployment:
- it needs roughly 300–600 MB more RAM for `torch` plus the model;
- it adds about 10–30 ms per search query.

That is still zero tokens.

## Accounts and gating (separate milestone)

Browse stays public and needs no login. Ask AI requires one.

### Data: a new `app` schema, outside dbt

The warehouse schemas (`raw`, `staging`, `marts`, `vectors`) are rebuilt by the pipeline
and dbt, so user data can't live there. A new `app` schema is managed by plain,
numbered SQL migrations (`db/migrations/001_users.sql`, ...) that a small runner applies
in order. The applied versions are recorded in `app.schema_migrations`.

Tables:

- **`app.users`:**
  - `id`;
  - `email` (citext, unique);
  - `password_hash`;
  - `display_name`;
  - `role` (`user` | `admin`);
  - `is_active`;
  - `daily_token_limit`, nullable to use the default;
  - `created_at` and `last_login_at`.
- **`app.sessions`:** `id` (random 256-bit token, stored hashed), `user_id`,
  `created_at`, `expires_at`, `last_seen_at`, `user_agent`. Server-side sessions can be
  revoked, which JWTs can't easily be.
- **`app.chat_usage`:** `user_id`, `created_at`, `model`, `input_tokens`,
  `output_tokens`, `cache_read_tokens`, `tool_rounds`. One row per question, written from
  the `usage` in each response. It feeds the daily budget and an admin usage view.

### Roles

| Role | Can do |
|---|---|
| `bgpt_reader` | unchanged: `SELECT` on `marts` only. Claude's SQL and Browse use it, so Claude can never see `app` |
| `bgpt_app` (new) | `SELECT/INSERT/UPDATE/DELETE` on `app` only, no warehouse access. Used only by the auth and usage code |
| `bgpt` (owner) | migrations, pipeline, dbt |

### Auth flow

- **Passwords:** hashed with Argon2id (`argon2-cffi`).
- **Login:** `POST /api/auth/login` sets an `HttpOnly`, `Secure`, `SameSite=Lax` session
  cookie. `POST /api/auth/logout` deletes the session. `GET /api/auth/me` returns the
  current user, or 401.
- **Login protection:** a rate limit per IP and per email, and the same generic error for
  a wrong email and a wrong password.
- **Chat protection:** `/api/chat` depends on the current user. It returns 401 without a
  session, and 429 once the user's daily token budget is used up.
- **Accounts:** created by an admin, through a `make user-add` CLI or a minimal admin
  page. There's no public sign-up in v1, because each account can spend tokens. An
  invite-link sign-up can come later.

### Cost controls (kept from the earlier draft)

- **Spending cap** on the API key in the Anthropic Console. This is the hard backstop.
- **Per-user limits:** a rate limit (for example 20 questions an hour) and a daily token
  budget from `app.chat_usage`. Conversations are capped at N turns.
- **Model choice by env**, for example Sonnet with `CLAUDE_EFFORT=low` in production.

## Testing

- **API tests against the live database** (skipped if it is down). Each checks known
  values:
  - season HR leader is Bonds 2001, 73;
  - career hits leader is Rose;
  - the Gehrig player page shows 2,721 hits and 493 HR;
  - 1927 AL standings have the Yankees first at 110-44;
  - a Negro Leagues filter returns only `is_negro_leagues` leagues;
  - qualified ERA boards contain only qualified rows.
- **Validation tests:**
  - an unknown stat, a bad league or `limit=10000` returns 422;
  - SQL-looking input in `q` is treated as plain text.
- **Frontend:** the build passes. A small smoke test drives the main pages in the
  browser pane.

## Milestones (one PR each)

1. **Browse API + Leaders page:**
   - `db.fetch`, the stat catalogue, `/api/meta`, `/api/leaderboard` and caching;
   - router and nav;
   - the leaderboard builder;
   - Ask AI moved to `/ask`.
2. **Player search + player pages:** `/api/players` (SQL search), `/api/players/{id}`,
   the header typeahead, and the player page.
3. **Standings:** `/api/standings/{season}` and the standings page.
4. **Phase 4 embeddings:** aliases, baseline model, pgvector index and hybrid search.
5. **Accounts and Ask AI gating:**
   - the `app` schema, migrations and the `bgpt_app` role;
   - login, logout and sessions;
   - `make user-add`;
   - usage tracking, rate limits and the daily budget;
   - the login UI.
6. **Deployment on AWS:** see below.

Deployment waits for phase 4. Milestone 5 lands before it, so Ask AI is never public
without a login.

## AWS deployment (milestone 6, outline)

To be detailed when we get there:

- **Database:** RDS for PostgreSQL 17 with the `pgvector` extension. RDS supports it, but
  `db/init` won't run there, so its SQL moves into a bootstrap script and the
  migrations. It sits in a private subnet.
- **App:** one container image with FastAPI and the built Vue app, on ECS Fargate (or App
  Runner) behind an ALB with HTTPS (ACM). Size the tasks for the embedding model, about
  1 GB of memory.
- **Secrets:** the Anthropic key and the database passwords go in AWS Secrets Manager and
  are injected as env vars, not `.env` files.
- **Data load:** the pipeline and dbt run as a one-off task, or from a machine with
  access, against RDS. After that, apply roles and migrations.
- **CDN:** CloudFront in front, so the cached browse responses rarely reach the app.
- **Infrastructure as code:** Terraform or CDK. To be decided.
