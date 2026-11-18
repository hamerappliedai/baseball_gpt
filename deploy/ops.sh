#!/bin/sh
# Database jobs for the ops image. Connection: libpq variables (PGHOST, PGPORT,
# PGUSER, PGPASSWORD, PGDATABASE), as the database owner (the RDS master user on
# AWS). `roles` also needs READER_PASSWORD and APP_PASSWORD.
set -eu

usage() {
  cat <<'USAGE'
usage: ops <command>
  bootstrap     extensions and warehouse schemas (db/bootstrap.sql)
  roles         bgpt_reader and bgpt_app roles and grants (db/roles.sql)
  migrate       app schema migrations (accounts, sessions, usage)
  load          download, verify and load the Lahman release into raw
  transform     dbt: seeds, staging views, marts and data tests
  embed         player-name embeddings for search
  first-load    all of the above, in order: a new database, ready to serve
  refresh-data  load + transform + embed + roles (a new Lahman release)
  psql          an interactive psql session
USAGE
}

: "${PGHOST:?set PGHOST}" "${PGUSER:?set PGUSER}" "${PGPASSWORD:?set PGPASSWORD}"
export PGPORT="${PGPORT:-5432}" PGDATABASE="${PGDATABASE:-baseball}"
export PGSSLMODE="${PGSSLMODE:-prefer}"
RELEASE="${RELEASE:-2025}"

# The pipeline takes a URL; dbt takes POSTGRES_* (transform/profiles.yml).
DATABASE_URL=$(python -c 'import os, urllib.parse as u; q=u.quote
print(f"postgresql://{q(os.environ["PGUSER"], safe="")}:{q(os.environ["PGPASSWORD"], safe="")}@{os.environ["PGHOST"]}:{os.environ["PGPORT"]}/{os.environ["PGDATABASE"]}?sslmode={os.environ["PGSSLMODE"]}")')
export DATABASE_URL POSTGRES_HOST="$PGHOST" POSTGRES_PORT="$PGPORT" POSTGRES_USER="$PGUSER" \
       POSTGRES_PASSWORD="$PGPASSWORD" POSTGRES_DB="$PGDATABASE"

step() { echo; echo "==> $*"; }

bootstrap() { step bootstrap; psql -q -v ON_ERROR_STOP=1 -f /app/db/bootstrap.sql; }
roles() {
  step roles
  : "${READER_PASSWORD:?set READER_PASSWORD}" "${APP_PASSWORD:?set APP_PASSWORD}"
  psql -q -v ON_ERROR_STOP=1 -v reader_password="$READER_PASSWORD" -v app_password="$APP_PASSWORD" \
       -f /app/db/roles.sql
}
migrate()   { step migrate;   bgpt-pipeline migrate; }
load()      { step "load (release $RELEASE)"; bgpt-pipeline build --release "$RELEASE"; }
transform() { step transform; cd /app/transform && /opt/dbt/bin/dbt build --profiles-dir . && cd - >/dev/null; }
embed()     { step embed;     bgpt-pipeline embed; }

case "${1:-help}" in
  bootstrap|roles|migrate|load|transform|embed) "$1" ;;
  # Roles run again after the warehouse is built so the reader's grants cover
  # the new tables (default privileges cover them too; this is belt and braces).
  first-load)   bootstrap; roles; migrate; load; transform; embed; roles ;;
  refresh-data) load; transform; embed; roles ;;
  psql)         exec psql ;;
  help|-h|--help) usage ;;
  *) usage; exit 2 ;;
esac
echo; echo "done: $1"
