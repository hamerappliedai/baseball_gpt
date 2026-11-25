# DB settings come from .env (see .env.example); docker compose reads the same file.
-include .env
export

RELEASE ?= 2025
PIPELINE = cd pipeline && uv run bgpt-pipeline
DBT = cd transform && uv run dbt

.PHONY: db-up db-roles db-down db-shell build ingest fetch verify load transform embed migrate docs test backend-test search-eval user-add user-list image-build image-run aws-push aws-task aws-shell

db-up:            ## start Postgres + pgvector (host port 5432), wait until healthy, apply roles
	docker compose up -d --wait
	$(MAKE) --no-print-directory db-roles
	$(MAKE) --no-print-directory migrate

db-roles:         ## create/update the backend's database roles (idempotent)
	@test -n "$(READER_PASSWORD)" || (echo "Set READER_PASSWORD in .env (see .env.example)"; exit 1)
	@test -n "$(APP_PASSWORD)" || (echo "Set APP_PASSWORD in .env (see .env.example)"; exit 1)
	@echo "applying db/roles.sql"
	@docker compose exec -T db psql -q -v ON_ERROR_STOP=1 -U $(POSTGRES_USER) -d $(POSTGRES_DB) \
		-v reader_password='$(READER_PASSWORD)' -v app_password='$(APP_PASSWORD)' -f - < db/roles.sql

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

migrate:          ## apply db/migrations (accounts, sessions, usage) to the app schema
	$(PIPELINE) migrate

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

user-add:         ## create an Ask AI account: make user-add EMAIL=... NAME="..." [ADMIN=1] [GENERATE=1]
	@test -n "$(EMAIL)" -a -n "$(NAME)" || (echo 'usage: make user-add EMAIL=you@example.com NAME="Your Name" [ADMIN=1]'; exit 1)
	cd backend && .venv/bin/python manage.py user-add --email "$(EMAIL)" --name "$(NAME)" $(if $(ADMIN),--admin) $(if $(GENERATE),--generate-password)

user-list:        ## list Ask AI accounts with today's token use
	cd backend && .venv/bin/python manage.py user-list

image-build:      ## build the production images (deploy/app.Dockerfile, deploy/ops.Dockerfile)
	docker build -f deploy/app.Dockerfile -t baseball-gpt-app .
	docker build -f deploy/ops.Dockerfile -t baseball-gpt-ops .

image-run:        ## run the production app image against the local database on :8080
	docker compose --profile image up app

aws-push:         ## build the images for arm64 and push them to ECR: make aws-push [IMAGES="app ops"]
	deploy/aws-push.sh $(IMAGES)

aws-task:         ## run the ops image once on ECS: make aws-task CMD=first-load (see deploy/ops.sh)
	@test -n "$(CMD)" || (echo 'usage: make aws-task CMD=first-load|migrate|refresh-data|...'; exit 1)
	deploy/aws-task.sh $(CMD)

aws-shell:        ## a shell in a running app task (ECS Exec), e.g. for manage.py user-add
	deploy/aws-shell.sh
