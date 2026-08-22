#!/bin/sh
# Container entrypoint: migrate, then exec whatever was asked for.
#
# An ENTRYPOINT rather than a chained CMD, because `docker-compose.yml` overrides `command:` (to add
# `--reload`) and a `CMD ["sh","-c","migrate && uvicorn …"]` would be replaced wholesale by that
# override — silently skipping migrations in exactly the environment where the schema changes most
# often. As an entrypoint, the migration runs first whatever the command is.
#
# `exec` matters: without it this shell stays as PID 1 and swallows SIGTERM, so `docker stop` waits
# out its ten-second grace period and then kills uvicorn mid-request instead of letting it drain.
#
# Set RUN_MIGRATIONS=false to skip the migration step — for `docker compose run engine python -m
# pytest` (the suite manages its own schema) or when a deploy pipeline migrates in a separate job.

set -e

if [ "${RUN_MIGRATIONS:-true}" != "true" ]; then
    echo "entrypoint: RUN_MIGRATIONS=$RUN_MIGRATIONS — skipping alembic upgrade head" >&2
elif [ -z "${DATABASE_URL:-}" ]; then
    # No database configured, so there is nothing to migrate. This is the case for the image's
    # non-server uses — `python scripts/engine_cli.py check`, `python -m pytest` (the suite forces
    # its own in-memory URL) — and skipping keeps them working without every caller having to know
    # about RUN_MIGRATIONS.
    #
    # It is NOT a way to start the server without a database: app startup then refuses outright
    # under APP_ENV=production (app/db/session.py::assert_production_database), naming the variable.
    # So a missing DATABASE_URL still fails loudly; it just fails at the right layer.
    echo "entrypoint: DATABASE_URL is not set — nothing to migrate." >&2
    echo "entrypoint: this is expected for one-off commands; the API itself will refuse to start." >&2
else
    # `migrate.py` waits for the database to accept a login before it does anything: the engine and
    # Postgres start together under compose, and Postgres accepts TCP a moment before it will accept
    # a login.
    python /srv/scripts/migrate.py --wait "${MIGRATION_WAIT_SECONDS:-60}"
fi

exec "$@"
