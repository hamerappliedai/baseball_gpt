# DB settings come from .env (see .env.example); docker compose reads the same file.
-include .env
export

RELEASE ?= 2025
PIPELINE = cd pipeline && uv run bgpt-pipeline
DBT = cd transform && uv run dbt

.PHONY: db-up db-down db-shell build ingest fetch verify load transform docs test

db-up:            ## start Postgres + pgvector (host port 5432) and wait until healthy
	docker compose up -d --wait

db-down:
	docker compose down

db-shell:
	docker compose exec db psql -U $(POSTGRES_USER) $(POSTGRES_DB)

build: ingest transform   ## everything: download, verify, load raw, then build and test the marts

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

docs:             ## generate and serve dbt docs (lineage graph) on :8080
	$(DBT) docs generate --profiles-dir . && $(DBT) docs serve --profiles-dir . --port 8080

test:             ## pipeline unit/integration tests (dbt data tests run in `make transform`)
	cd pipeline && uv run pytest -q
