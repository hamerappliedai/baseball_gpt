# DB settings come from .env (see .env.example); docker compose reads the same file.
-include .env
export

RELEASE ?= 2025
PIPELINE = cd pipeline && uv run bgpt-pipeline

.PHONY: db-up db-down db-shell build fetch verify load test

db-up:            ## start Postgres + pgvector (host port 5432) and wait until healthy
	docker compose up -d --wait

db-down:
	docker compose down

db-shell:
	docker compose exec db psql -U $(POSTGRES_USER) $(POSTGRES_DB)

build: db-up      ## download, verify and load the release into the raw schema
	$(PIPELINE) build --release $(RELEASE)

fetch:
	$(PIPELINE) fetch --release $(RELEASE)

verify:
	$(PIPELINE) verify --release $(RELEASE)

load:
	$(PIPELINE) load --release $(RELEASE)

test:
	cd pipeline && uv run pytest -q
