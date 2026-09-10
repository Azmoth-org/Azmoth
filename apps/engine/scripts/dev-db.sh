#!/usr/bin/env bash
# The migration interface for local dev — a thin wrapper around Alembic that makes DATABASE_URL
# explicit and visible on every run, so a migration can never silently land in the wrong database.
#
# ---------------------------------------------------------------------------------------------
# Why this script exists
# ---------------------------------------------------------------------------------------------
# `app.config.Settings.database_url` defaults to `sqlite+aiosqlite:///./test.db` so that `uvicorn`
# and `pytest` need no setup at all — that default is deliberate and this script does not change
# it. It is exactly the wrong default for Alembic: `apps/engine/alembic/env.py` now refuses to run
# at all when `DATABASE_URL` is not in the environment (see the check there), because the old
# behaviour — silently falling back to that same SQLite default — is how a migration ends up
# creating tables in `./test.db` while the service goes on querying Postgres and finds none of
# them: "relation does not exist", with nothing in the log naming the actual mistake.
#
# This script is what sets `DATABASE_URL` correctly so that check never fires for the normal case:
#
#   ./scripts/dev-db.sh upgrade head            Postgres — docker compose's local container by
#                                                default, or whatever DATABASE_URL is already set to
#   ./scripts/dev-db.sh --sqlite upgrade head   a dedicated local SQLite file instead, for
#                                                exercising a migration without installing Postgres
#
# `--sqlite` targets its own file, `./dev.db`, and never `./test.db` — sharing that file with
# `create_all` is a second, older trap: `./test.db` gets built with no `alembic_version` row the
# first time `uvicorn`/`pytest` runs, and Alembic then tries to create tables that are already
# there. See docs/architecture/DATABASE.md#running-migrations for both traps in one place.
set -euo pipefail

cd "$(dirname "$0")/.."

# Prefer the project's own virtualenv, same convention as scripts/test-all.sh — falling back to
# whatever is on PATH for a shell that has already activated one.
ALEMBIC="./.venv/bin/alembic"
[[ -x "$ALEMBIC" ]] || ALEMBIC="alembic"
PYTHON="./.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="python3"

#: Matches infra/docker/docker-compose.yml's own `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`
#: defaults (all `azmoth`) and its published port — what
#: `docker compose -f infra/docker/docker-compose.yml up -d postgres` gives you on the host.
POSTGRES_DEV_URL="postgresql+asyncpg://azmoth:azmoth@localhost:5432/azmoth"

#: Alembic-only, and never `./test.db` — see the module comment above.
SQLITE_DEV_URL="sqlite+aiosqlite:///./dev.db"

# A `DATABASE_URL` already exported (a real staging database, a non-default local Postgres port)
# is respected; only the unset case defaults to the local container.
DATABASE_URL="${DATABASE_URL:-$POSTGRES_DEV_URL}"

if [[ "${1:-}" == "--sqlite" ]]; then
  DATABASE_URL="$SQLITE_DEV_URL"
  shift
fi

export DATABASE_URL
# This script's only job is driving Alembic. `DATABASE_AUTO_CREATE` must not also try to build the
# schema behind its back — see app/db/session.py::init_models.
export DATABASE_AUTO_CREATE=false

# Mask a password in `scheme://user:pass@host/db` so it is safe to paste this line into a bug
# report. `|` as the sed delimiter rather than `/` or `#`, either of which can appear in a URL or a
# password and would silently break the substitution instead of failing loudly.
masked=$(printf '%s' "$DATABASE_URL" | sed -E 's|(://[^:/@]+):[^@/]+@|\1:****@|')
echo "database: $masked"

if [[ -z "${1:-}" ]]; then
  cat <<EOF

Usage: $(basename "$0") [--sqlite] <alembic-subcommand> [args...]

  $(basename "$0") upgrade head              apply everything, against the Postgres container
  $(basename "$0") current                   what revision that database is at
  $(basename "$0") revision -m "description" a new migration, after editing app/db/models.py
  $(basename "$0") --sqlite upgrade head     the same, against a dedicated local ./dev.db instead

Convenience shortcuts, with or without --sqlite:

  $(basename "$0") reset      drop everything and re-apply from scratch
  $(basename "$0") diagnose   why 'upgrade head' would fail on a table that already exists
  $(basename "$0") shell      open a client on the target database

Anything else is passed straight through to alembic.

Postgres container: docker compose -f ../../infra/docker/docker-compose.yml up -d postgres
Docs: ../../docs/architecture/DATABASE.md
EOF
  exit 1
fi

case "$1" in
  reset)
    if [[ "$DATABASE_URL" == sqlite* ]]; then
      file="${DATABASE_URL#sqlite+aiosqlite:///}"
      echo "Deleting $file..."
      rm -f "$file"
    else
      echo "DATABASE_URL is Postgres — 'reset' does not drop a live database for you." >&2
      echo "Drop and recreate it yourself, or 'docker compose down -v' the postgres volume," >&2
      echo "then: $(basename "$0") upgrade head" >&2
      exit 1
    fi
    echo "Running every migration..."
    "$ALEMBIC" upgrade head
    ;;
  diagnose)
    "$PYTHON" scripts/migrate.py --diagnose
    ;;
  shell)
    if [[ "$DATABASE_URL" == sqlite* ]]; then
      command -v sqlite3 >/dev/null || {
        echo "sqlite3 is not installed. Query ${DATABASE_URL#sqlite+aiosqlite:///} with any SQLite client instead." >&2
        exit 1
      }
      sqlite3 "${DATABASE_URL#sqlite+aiosqlite:///}"
    else
      echo "Not SQLite — connect a client to: $masked"
      echo "(e.g. docker compose -f ../../infra/docker/docker-compose.yml exec postgres psql -U azmoth -d azmoth)"
    fi
    ;;
  *)
    # Passed straight through — `upgrade head`, `current`, `revision -m "…"`, `downgrade -1`, …
    "$ALEMBIC" "$@"
    ;;
esac
