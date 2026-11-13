# DB settings come from .env (see .env.example); docker compose reads the same file.
-include .env
export

RELEASE ?= 2025
PIPELINE = cd pipeline && uv run bgpt-pipeline
DBT = cd transform && uv run dbt

.PHONY: db-up db-roles db-down db-shell build ingest fetch verify load transform embed docs test backend-test search-eval

db-up:            ## start Postgres + pgvector (host port 5432), wait until healthy, apply roles
	docker compose up -d --wait
	$(MAKE) --no-print-directory db-roles

db-roles:         ## create/update the backend's read-only role (idempotent)
	@test -n "$(READER_PASSWORD)" || (echo "Set READER_PASSWORD in .env (see .env.example)"; exit 1)
	@echo "applying db/roles.sql"
	@docker compose exec -T db psql -q -v ON_ERROR_STOP=1 -U $(POSTGRES_USER) -d $(POSTGRES_DB) \
		-v reader_password='$(READER_PASSWORD)' -f - < db/roles.sql

db-down:
	docker compose down

db-shell:
	docker compose exec db psql -U $(POSTGRES_USER) $(POSTGRES_DB)

build: ingest transform embed   ## everything: download, verify, load raw, build and test the marts, embed names

ingest: db-up     ## download, verify and load the release into the raw schema
	$(PIPELINE) build --release $(RELEASE)

fetch:
	$(PIPELINE) fetch --release $(RELEASE)

verify:
	$(PIPELINE) verify --release $(RELEASE)

load:
	$(PIPELINE) load --release $(RELEASE)

transform:        ## dbt: seeds, staging views, marts and all data tests
	$(DBT) build --profiles-dir .

embed:            ## embed player names + nicknames into vectors.player_aliases (downloads the model once)
	$(PIPELINE) embed

docs:             ## generate and serve dbt docs (lineage graph) on :8080
	$(DBT) docs generate --profiles-dir . && $(DBT) docs serve --profiles-dir . --port 8080

test:             ## pipeline unit/integration tests (dbt data tests run in `make transform`)
	cd pipeline && uv run pytest -q

backend-test:     ## backend tests (SQL tool against the running DB, agent loop with a fake Claude)
	cd backend && .venv/bin/python -m pytest -q

search-eval:      ## compare plain SQL vs hybrid player search on labeled queries
	cd backend && .venv/bin/python eval/search_eval.py
