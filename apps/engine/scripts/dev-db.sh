#!/usr/bin/env bash
# A local SQLite database that only Alembic ever touches — for exercising migrations directly
# without installing Postgres, and without the "table already exists" error documented below.
#
# ---------------------------------------------------------------------------------------------
# Why this script exists, and why it is not just `alembic upgrade head`
# ---------------------------------------------------------------------------------------------
# `DATABASE_URL` defaults to `sqlite+aiosqlite:///./test.db` and `DATABASE_AUTO_CREATE` defaults
# to true (see app/config.py) — deliberately, so `uvicorn app.main:app` and `pytest` need no setup
# at all. The first time either runs, `init_models()` builds every table in `./test.db` with
# `Base.metadata.create_all`, and that database then has no `alembic_version` row: `create_all`
# has never heard of Alembic.
#
# Run `alembic upgrade head` against that same file next and it starts from nothing — migration
# `0001` tries `CREATE TABLE proposals` on a table that is already there, and dies with
# "table proposals already exists". That is almost certainly the error that sent you here; it is
# also documented in docs/architecture/DATABASE.md and apps/engine/alembic/README.md, whose fix is
# "delete the file, or `alembic stamp head`, before switching a dev database over" — correct, but
# a thing to remember every time.
#
# The actual fix is not to weaken `init_models`'s guard: it exists to stop `create_all` from ever
# touching a durable (Postgres) database, which is a real production incident this codebase has
# already had once (see tests/test_migration_recovery.py) — loosening it would reopen that. It is
# to give the two workflows separate files, so they can never collide: `./test.db` stays
# create_all's, and this script owns `./dev.db`, migrated by Alembic and nothing else.
set -euo pipefail

cd "$(dirname "$0")/.."

# Prefer the project's own virtualenv, same convention as scripts/test-all.sh — falling back to
# whatever is on PATH for a shell that has already activated one.
ALEMBIC="./.venv/bin/alembic"
[[ -x "$ALEMBIC" ]] || ALEMBIC="alembic"
PYTHON="./.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="python3"

DEV_DB_FILE="./dev.db"

# Forced, not defaulted: this script has exactly one job, and reading a developer's `DATABASE_URL`
# out of the environment here would silently point "reset" at whatever database that names,
# including a real one. `apps/engine/.env` is still respected by every other command
# (`uvicorn`, `pytest`, a bare `alembic upgrade head`) — pydantic-settings loads it directly, no
# shell sourcing required — this script alone opts out of it on purpose.
export DATABASE_URL="sqlite+aiosqlite:///${DEV_DB_FILE}"
export DATABASE_AUTO_CREATE=false

usage() {
  cat <<EOF
Usage: $(basename "$0") {reset|migrate|status|diagnose|shell}

Manages ${DEV_DB_FILE} — a SQLite database dedicated to Alembic, separate from the ./test.db that
'uvicorn app.main:app' and 'pytest' create for themselves. See the comment at the top of this file.

  reset     delete ${DEV_DB_FILE} and run every migration from scratch
  migrate   run pending migrations against ${DEV_DB_FILE}
  status    show the revision ${DEV_DB_FILE} is stamped at
  diagnose  why 'upgrade head' would fail on a table that already exists (scripts/migrate.py --diagnose)
  shell     open a sqlite3 shell on ${DEV_DB_FILE}

Docs: ../../docs/architecture/DATABASE.md
EOF
}

case "${1:-}" in
  reset)
    echo "Deleting ${DEV_DB_FILE}..."
    rm -f "$DEV_DB_FILE"
    echo "Running every migration..."
    "$ALEMBIC" upgrade head
    ;;
  migrate)
    echo "Running pending migrations against ${DEV_DB_FILE}..."
    "$ALEMBIC" upgrade head
    ;;
  status)
    "$ALEMBIC" current
    ;;
  diagnose)
    "$PYTHON" scripts/migrate.py --diagnose
    ;;
  shell)
    command -v sqlite3 >/dev/null || {
      echo "sqlite3 is not installed. Query ${DEV_DB_FILE} with any SQLite client instead." >&2
      exit 1
    }
    sqlite3 "$DEV_DB_FILE"
    ;;
  *)
    usage
    exit 1
    ;;
esac
