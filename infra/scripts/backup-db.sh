#!/usr/bin/env bash
#
# Dump the Azmoth Postgres database to a timestamped file, and prove the file is readable.
#
# The second half is the point. A backup script that only runs `pg_dump` produces a file nobody has
# opened, and the first time anyone opens it is the day they need it. This one reads the archive's
# table of contents back with `pg_restore --list` and fails if that does not work — so a corrupt or
# truncated dump is a red build step, not a discovery during an incident.
#
#   ./infra/scripts/backup-db.sh                    # → ./backups/azmoth-<utc>.dump
#   BACKUP_DIR=/mnt/backups ./infra/scripts/backup-db.sh
#
# Custom format (`-Fc`), not plain SQL: it is compressed, it can be restored selectively, and
# `pg_restore` can list it without a server — which is what makes the verification above possible.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$REPO_ROOT/infra/docker/docker-compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backups}"

POSTGRES_USER="${POSTGRES_USER:-azmoth}"
POSTGRES_DB="${POSTGRES_DB:-azmoth}"

# The compose service name, so this works against the dev stack too by pointing COMPOSE_FILE at it.
SERVICE="${POSTGRES_SERVICE:-postgres}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$BACKUP_DIR/azmoth-$stamp.dump"

mkdir -p "$BACKUP_DIR"

echo "==> dumping $POSTGRES_DB from service '$SERVICE'"
# `exec -T` because there is no TTY in CI, and the dump goes to stdout so it lands on the host
# rather than inside a container that a redeploy will delete.
docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" \
  pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format=custom --no-owner \
  > "$target"

if [ ! -s "$target" ]; then
  echo "!! the dump is empty — refusing to keep a file that would restore nothing" >&2
  rm -f "$target"
  exit 1
fi

echo "==> verifying the archive is readable"
# Read the table of contents back. This catches a truncated or corrupt dump, which is the failure a
# backup script most needs to catch and the one it usually does not.
tables="$(docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" \
  pg_restore --list < "$target" | grep -c "TABLE DATA" || true)"

if [ "$tables" -eq 0 ]; then
  echo "!! the archive lists no table data. Either the database is empty, or the dump is bad." >&2
  echo "   Keeping $target for inspection, but do NOT treat it as a backup." >&2
  exit 1
fi

size="$(du -h "$target" | cut -f1)"
echo "==> ok: $target ($size, $tables tables with data)"
echo
echo "Restore it with:  ./infra/scripts/restore-db.sh $target"
