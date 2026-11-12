# Transform layer (dbt)

Turns the `raw` schema the pipeline loads into the `marts` tables Claude queries.

```
raw (text, as published)  →  staging (typed views)  →  marts (documented tables)
```

```bash
make transform    # dbt build: seeds, staging, marts, then every data test
make docs         # lineage graph and column docs at http://localhost:8080
```

`make build` runs ingest and transform together. dbt reads its connection from
the repo-root `.env`, which the Makefile exports.

## Staging (`staging` schema, views)

One view per raw table (`stg_batting`, `stg_people`, ...): columns cast to real
types, renamed to snake_case (`2B` → `doubles`, `yearID` → `season`), and
`Y`/`N` flags turned into booleans. Nothing is filtered or aggregated. The
seeds `seed_leagues` and `seed_postseason_rounds` add names for league and
round codes that the Lahman files only give as ids.

## Marts (`marts` schema, tables)

| Table | Grain |
|---|---|
| `players` | person (players, managers, executives); start here to resolve a name |
| `leagues`, `franchises` | league; franchise across relocations |
| `team_seasons` | team × season |
| `batting_seasons`, `pitching_seasons` | player × season, all stints combined |
| `batting_league_seasons`, `pitching_league_seasons` | player × season × league, for league leaders |
| `batting_careers`, `pitching_careers` | player |
| `fielding_seasons` | player × season × position |
| `postseason_series`, `postseason_batting`, `postseason_pitching` | series; player × season × round |
| `awards`, `award_voting`, `hall_of_fame_voting`, `all_star_selections` | award / ballot / selection |
| `manager_seasons`, `salaries`, `player_colleges` | manager × team × season; player × team × season; player × school |

Choices worth knowing:

- **Stints are summed.** A player traded mid-season has one Lahman row per team.
  `*_seasons` sums them (McGwire 1997: 58 HR); `*_league_seasons` sums within a
  league (34 AL, 24 NL), which is what league leaderboards need.
- **Rate stats are recomputed** from counting stats in one place
  ([macros/stats.sql](macros/stats.sql)), not taken from Lahman's ERA columns.
  Unrecorded components (e.g. sacrifice flies before 1954) count as 0 in
  PA/OBP, while the counting stat itself stays NULL (unknown, not zero).
- **Title qualification** uses the modern rules for every era: 3.1 PA per team
  game for batting, 1 inning per team game for ERA. Independent clubs (IND,
  EAS, WES) aren't leagues, so their seasons never qualify.
- **Every column is documented** in [models/marts/_marts.yml](models/marts/_marts.yml)
  (shared stat definitions in [_stat_docs.md](models/marts/_stat_docs.md)) and
  `persist_docs` writes those descriptions into Postgres as column comments.
  The backend builds Claude's schema description from the database, so the
  docs and the data can't drift apart.

## Tests

`dbt build` fails if any test fails:

- **Grain and keys:** every model's key is unique; ids resolve to `players`,
  `franchises`, `leagues` and postseason rounds.
- **Known records** ([tests/known_records.sql](tests/known_records.sql)): Bonds
  762, Ruth 714, Rose 4,256 hits, Williams .406, Gibson 1.12, McGwire's 1997
  split, the 1997 AL home run leader, and more.
- **Reconciliation** ([tests/marts_reconcile_with_staging.sql](tests/marts_reconcile_with_staging.sql)):
  rolling stints up to seasons, league-seasons and careers neither drops nor
  double-counts anything.
- **Sanity** ([tests/stat_sanity.sql](tests/stat_sanity.sql)): no impossible
  lines (more hits than at bats, ...). One known error in the Lahman release
  itself is allowlisted, with a comment, rather than patched.
