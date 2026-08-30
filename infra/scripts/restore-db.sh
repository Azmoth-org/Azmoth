#!/usr/bin/env bash
#
# Restore an Azmoth database dump. **This destroys the current contents of the target database.**
#
#   ./infra/scripts/restore-db.sh backups/azmoth-20260830T140000Z.dump
#
# Two safety properties, both deliberate:
#
#   1. It refuses to run unless the caller types the database name. A restore is not a command
#      anybody should be able to run by pressing up-arrow and enter, and a `--force` flag is
#      exactly the thing that ends up in someone's shell history.
#   2. It takes a safety dump of the CURRENT state first, before touching anything. A restore of the
#      wrong file is a recoverable mistake if the thing it replaced still exists somewhere, and an
#      unrecoverable one otherwise.
#
# `--clean --if-exists` drops the existing objects rather than merging into them: a restore that
# merged would leave rows from two different points in time in one table, which is worse than either
# state on its own and impossible to reason about afterwards.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$REPO_ROOT/infra/docker/docker-compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backups}"

POSTGRES_USER="${POSTGRES_USER:-azmoth}"
POSTGRES_DB="${POSTGRES_DB:-azmoth}"
SERVICE="${POSTGRES_SERVICE:-postgres}"

archive="${1:-}"
if [ -z "$archive" ]; then
  echo "usage: $0 <dump-file>" >&2
  echo >&2
  echo "available:" >&2
  ls -1t "$BACKUP_DIR"/*.dump 2>/dev/null | head -10 >&2 || echo "  (none in $BACKUP_DIR)" >&2
  exit 2
fi

if [ ! -s "$archive" ]; then
  echo "!! $archive does not exist or is empty" >&2
  exit 1
fi

cat <<WARNING

  This will REPLACE the contents of database '$POSTGRES_DB' with
  $archive

  Everything currently in it — proposals, approvals, audit events, batch results,
  API keys and usage records — is dropped and rebuilt from the archive.

WARNING

read -r -p "Type the database name ($POSTGRES_DB) to continue: " confirmation
if [ "$confirmation" != "$POSTGRES_DB" ]; then
  echo "aborted." >&2
  exit 1
fi

safety="$BACKUP_DIR/pre-restore-$(date -u +%Y%m%dT%H%M%SZ).dump"
mkdir -p "$BACKUP_DIR"
echo "==> taking a safety dump of the current state first"
if docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" \
     pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format=custom --no-owner \
     > "$safety" 2>/dev/null && [ -s "$safety" ]; then
  echo "    saved to $safety"
else
  # An empty or failed safety dump is not a reason to stop: restoring into a database that is
  # already broken is a normal thing to be doing. It IS a reason to say so loudly.
  rm -f "$safety"
  echo "    !! could not take a safety dump — the current database may be unreachable or empty."
  echo "       Continuing, but there is nothing to go back to."
fi

echo "==> restoring"
docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" \
  pg_restore --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --clean --if-exists --no-owner --exit-on-error \
  < "$archive"

echo "==> verifying"
docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" \
  psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --tuples-only --command \
  "SELECT 'restored: ' || count(*) || ' tables' FROM information_schema.tables WHERE table_schema='public';"

echo
echo "==> done. Restart the engine so it reconnects:  docker compose -f $COMPOSE_FILE restart engine"
