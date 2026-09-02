#!/usr/bin/env bash
#
# Dump the Neon database, verify the archive, encrypt it, and push it off this VM to Azure Blob
# Storage.
#
#     ./infra/scripts/backup-to-azure.sh
#
# Runs ON the VM, normally from cron.
#
# ── What changed when the database moved to Neon ──────────────────────────────────────────────
# This script used to wrap infra/scripts/backup-db.sh, which dumps by way of
# `docker compose exec -T postgres pg_dump`. There is no postgres container on this box any more,
# so that path is gone and the dump is taken over the network instead: a throwaway
# `postgres:17-alpine` container runs `pg_dump` against Neon's DIRECT endpoint.
#
# Three deliberate choices in that sentence:
#
#   * **A container, not a host package.** `pg_dump` must be at least as new as the server, and
#     Neon runs Postgres 17. Installing postgresql-client-17 on Ubuntu 22.04 means adding the PGDG
#     apt repository to a box whose whole point is that it runs three pulled images. A pinned image
#     is one line, is the same version on every run, and leaves nothing behind.
#
#   * **The DIRECT endpoint.** Neon's own guidance: use a direct connection for `pg_dump`. Through
#     the transaction-mode pooler a dump can see an inconsistent snapshot, because `pg_dump` holds
#     one transaction open across many statements and relies on session state the pooler does not
#     guarantee it keeps.
#
#   * **`--host` networking is not needed, but `--network host` is not used either.** The container
#     reaches Frankfurt over the default bridge, which is all an outbound TLS connection needs.
#
# infra/scripts/backup-db.sh and restore-db.sh are NOT deleted. They remain the correct tools for
# the local docker-compose stack, where there is a postgres container to exec into.
#
# ── Why an off-host copy at all, when Neon has point-in-time restore ──────────────────────────
# Because Neon's mechanisms all live inside the Neon project. Instant restore, snapshots and
# branches survive a dropped table; none of them survives a deleted project, a lapsed card, a
# compromised Neon login, or Neon's own policy that Free-plan projects idle for 90 days "are subject
# to deletion". docs/OPERATIONS.md § 2 has always required dumps to be kept off the same host as the
# database, and a managed provider is a host.
#
# On the Free plan the history window is six hours, capped at 1 GB. That is a rollback. This is the
# backup.
#
# ── Credentials: there are none on this box, except the one that has to be ────────────────────
# Blob authentication is the VM's system-assigned managed identity, granted "Storage Blob Data
# Contributor" on this container alone by infra/azure/provision.sh. `az login --identity` gets a
# short-lived token from the instance metadata endpoint. No storage account key is written to disk.
#
# The Neon connection string IS a long-lived credential and it does sit in
# /opt/azmoth/shared/.env (mode 600), because the engine cannot connect without it. Rotate it in
# the Neon console — "Reset password" on the role — and re-run scripts/deploy.sh.
#
# ── Encryption: the VM can encrypt, and cannot decrypt ────────────────────────────────────────
# A dump is a complete copy of every approval, audit event and API key hash — clinical data under
# the AVV. Azure encrypts blobs at rest with its own keys, which protects against a stolen disk in
# a datacentre and not against the container being made readable by a misconfiguration.
#
# So the dump is encrypted here, with `age`, to a PUBLIC key. The matching private key is never on
# this VM. A compromised VM can therefore write backups and cannot read back a single one — and
# neither can anyone who gets read access to the container.
#
# Generate the keypair on your LAPTOP, once:
#
#     age-keygen -o azmoth-backup.key
#     # → Public key: age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p
#
# Keep `azmoth-backup.key` in a password manager and NOWHERE ELSE. Put the public key on the VM:
#
#     echo 'AGE_RECIPIENT=age1ql3z...' >> /opt/azmoth/shared/.env
#
# Losing the private key means losing every backup. That is the trade, and it is stated here rather
# than discovered.

set -euo pipefail

SHARED_ENV="${SHARED_ENV:-/opt/azmoth/shared/.env}"
BACKUP_DIR="${BACKUP_DIR:-/opt/azmoth/backups}"

# Kept short. The blob is the archive; local copies exist to make a same-day restore fast and to
# give the verification something to read.
LOCAL_RETENTION_DAYS="${LOCAL_RETENTION_DAYS:-7}"

# At least the server's major version. Neon is on Postgres 17; a pg_dump older than the server
# refuses with "server version mismatch", which is the one failure worth pinning against.
PGDUMP_IMAGE="${PGDUMP_IMAGE:-postgres:17-alpine}"

# Pull configuration out of the deployment's own env file, so this script has no second copy of the
# storage account name or the connection string to go stale.
#
# ── The env file has to be shell-sourceable, and that is not automatic ────────────────────────
# A Neon connection string ends in a query string, typically
# '?sslmode=require&channel_binding=require'. An unquoted '&' in a sourced file is a background
# operator, and the resulting parse error abandons the REST OF THE FILE — so the symptom of an
# unquoted DATABASE_URL is not a broken database URL, it is this script reporting that
# STORAGE_ACCOUNT is unset. That is a genuinely confusing half-hour, so it is checked for by name.
#
# scripts/deploy.sh writes the value double-quoted. A hand-edit on the box is how it stops being so.
if [ -f "$SHARED_ENV" ]; then
  # shellcheck disable=SC1090  # the path is a deployment location, not a file in this repo
  if ! ( set -a; . "$SHARED_ENV" ) 2>/dev/null; then
    printf '\033[1;31m !! %s\033[0m\n' "$SHARED_ENV is not shell-sourceable." >&2
    cat >&2 <<HINT
   Almost certainly an unquoted value containing '&' — a Neon URL ends in
   '?sslmode=require&channel_binding=require', and unquoted that is a syntax error which
   abandons every line after it. Wrap the value in double quotes:

       DATABASE_URL="postgresql+asyncpg://...?sslmode=require&channel_binding=require"

   Docker Compose strips the quotes, so nothing else changes. Then check the file parses:
       bash -n $SHARED_ENV  ||  ( set -a; . $SHARED_ENV )
HINT
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090  # the path is a deployment location, not a file in this repo
  . "$SHARED_ENV"
  set +a
fi

STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-}"
BACKUP_CONTAINER="${BACKUP_CONTAINER:-db-backups}"
AGE_RECIPIENT="${AGE_RECIPIENT:-}"
DATABASE_URL="${DATABASE_URL:-}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31m !! %s\033[0m\n' "$*" >&2; exit 1; }

[ -n "$STORAGE_ACCOUNT" ] || die "STORAGE_ACCOUNT is not set.
   Add it to $SHARED_ENV:   echo 'STORAGE_ACCOUNT=azmothbackupxxxx' >> $SHARED_ENV"

[ -n "$DATABASE_URL" ] || die "DATABASE_URL is not set in $SHARED_ENV.
   This script dumps Neon over the network and needs the DIRECT (non-pooled) connection string.
   scripts/deploy.sh writes it; if it is missing, the deployment cannot be running either."

command -v az >/dev/null || die "the Azure CLI is not installed on this VM.
   curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash"

command -v docker >/dev/null || die "docker is not installed on this VM — pg_dump runs in a container."

# ── 0. Normalise the URL for libpq ────────────────────────────────────────────────────────────
# The stored value is a SQLAlchemy URL: the Python driver is part of the scheme, as
# `postgresql+asyncpg://…`. libpq does not understand that and answers
# "invalid URI scheme: postgresql+asyncpg". Strip the driver, exactly as apps/web/lib/auth-db.ts
# does for node-postgres, so one value serves all three consumers.
#
# Refuse a pooled URL outright rather than dumping through PgBouncer. `pg_dump` holds a single
# transaction open across hundreds of statements; a transaction-mode pooler does not promise to
# keep it on one server connection, and the result is a dump that restores into a state that never
# existed. The `-pooler` infix is Neon's own marker for the pooled endpoint.
PG_URL="${DATABASE_URL/+asyncpg/}"
PG_URL="${PG_URL/+psycopg2/}"

case "$PG_URL" in
  *-pooler.*)
    die "DATABASE_URL points at Neon's POOLED endpoint (the host contains '-pooler').
   pg_dump must use the DIRECT endpoint — a transaction-mode pooler cannot guarantee the single
   snapshot a dump depends on, and Neon says so explicitly.
   Fix $SHARED_ENV: DATABASE_URL is the direct string, DATABASE_URL_POOLED is the pooled one." ;;
esac

# ── 1. Dump ───────────────────────────────────────────────────────────────────────────────────
# Custom format (`-Fc`), not plain SQL: compressed, selectively restorable, and listable without a
# server — which is what makes the verification in step 2 possible at all.

say "1/6 dumping Neon over the network"
mkdir -p "$BACKUP_DIR"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP="$BACKUP_DIR/azmoth-$stamp.dump"

# The URL reaches pg_dump as an environment variable, not as an argument, so it does not appear in
# `ps` output on the host while the dump runs. Note the SINGLE quotes around the `sh -c` script:
# `$PGURL` must be expanded by the container's shell, from the container's environment. Double
# quotes would expand it here instead, on a host where it is unset, and pg_dump would be handed an
# empty `--dbname` and try to connect to a local socket.
#
# `--no-owner`: the role names are Neon's and a restore target may not have them.
# `--no-privileges`: same reasoning for GRANTs.
pgdump_err="$(mktemp)"
trap 'rm -f "$pgdump_err"' EXIT

if ! docker run --rm -e PGURL="$PG_URL" "$PGDUMP_IMAGE" \
      sh -c 'pg_dump --dbname "$PGURL" --format=custom --no-owner --no-privileges' \
      > "$DUMP" 2>"$pgdump_err"; then
  echo "    pg_dump stderr:" >&2
  sed 's/^/      /' "$pgdump_err" >&2 || true
  rm -f "$DUMP"
  die "pg_dump failed. If this is the first request in a while, Neon's compute was suspended and
   the connection timed out during resume — re-run. If it says 'server version mismatch', raise
   PGDUMP_IMAGE above the Neon server's major version."
fi

if [ ! -s "$DUMP" ]; then
  rm -f "$DUMP"
  die "the dump is empty — refusing to keep a file that would restore nothing"
fi
echo "    $DUMP ($(du -h "$DUMP" | cut -f1))"

# ── 2. Verify the archive is readable ─────────────────────────────────────────────────────────
# This is the half that matters, and it is inherited from backup-db.sh rather than dropped with it.
# A backup script that only runs pg_dump produces a file nobody has opened, and the first time
# anyone opens it is the day they need it. `pg_restore --list` reads the table of contents back and
# needs no server, so a truncated or corrupt dump fails here rather than during an incident.

say "2/6 verifying the archive"
tables="$(docker run --rm -i "$PGDUMP_IMAGE" pg_restore --list < "$DUMP" 2>/dev/null \
  | grep -c "TABLE DATA" || true)"

if [ "${tables:-0}" -eq 0 ]; then
  echo "    !! the archive lists no table data. Either the database is empty, or the dump is bad." >&2
  echo "       Keeping $DUMP for inspection, but do NOT treat it as a backup." >&2
  exit 1
fi
echo "    readable, $tables tables with data"

# ── 3. Encrypt ────────────────────────────────────────────────────────────────────────────────

say "3/6 encrypting"

if [ -z "$AGE_RECIPIENT" ]; then
  if [ "${ALLOW_UNENCRYPTED_BACKUP:-0}" = "1" ]; then
    # Explicitly chosen, so it proceeds — but it is recorded in the log that cron mails, because
    # "we meant to set that up later" is how it stays unset for the life of the pilot.
    echo "    !! AGE_RECIPIENT is not set and ALLOW_UNENCRYPTED_BACKUP=1."
    echo "    !! This dump — every approval and audit event — goes up protected only by Azure's"
    echo "    !! at-rest encryption and the container being private. Set AGE_RECIPIENT."
    UPLOAD="$DUMP"
  else
    die "AGE_RECIPIENT is not set, so this dump would be uploaded unencrypted.
   A dump is a complete copy of every approval and audit event the deployment holds.

   Generate a keypair on your LAPTOP (not here):   age-keygen -o azmoth-backup.key
   Put the PUBLIC key here:  echo 'AGE_RECIPIENT=age1...' >> $SHARED_ENV
   Keep the private key in a password manager.

   To upload unencrypted anyway:  ALLOW_UNENCRYPTED_BACKUP=1 $0"
  fi
else
  command -v age >/dev/null || die "age is not installed.
   sudo apt-get install -y age        # Ubuntu 22.04 has it in universe"

  UPLOAD="$DUMP.age"
  # `-r`, a recipient's public key. There is no passphrase and nothing to decrypt with on this box.
  age -r "$AGE_RECIPIENT" -o "$UPLOAD" "$DUMP"
  echo "    encrypted to $UPLOAD ($(du -h "$UPLOAD" | cut -f1))"
  echo "    decrypt with:  age -d -i azmoth-backup.key $(basename "$UPLOAD") > restored.dump"
fi

# ── 4. Authenticate ───────────────────────────────────────────────────────────────────────────

say "4/6 authenticating with the VM's managed identity"
az login --identity --output none 2>/dev/null \
  || die "az login --identity failed.
   The VM has no managed identity, or it has no role on the container. Re-run
   infra/azure/provision.sh from your laptop, which assigns both."
echo "    ok — no credential is stored on this VM"

# ── 5. Upload ─────────────────────────────────────────────────────────────────────────────────
# Blobs are laid out by date, so listing a month is a prefix query rather than a scan:
#     db-backups/2026/09/azmoth-20260902T031500Z.dump.age
#
# `--overwrite false` and a timestamped name together mean this can never destroy an earlier
# backup, and it also avoids Cool tier's early-deletion penalty: overwriting a blob counts as a
# delete, so a daily job that reused one name would be billed 30 days of storage for each of them.

say "5/6 uploading"
BLOB="$(date -u +%Y/%m)/$(basename "$UPLOAD")"

az storage blob upload \
  --account-name "$STORAGE_ACCOUNT" \
  --container-name "$BACKUP_CONTAINER" \
  --name "$BLOB" \
  --file "$UPLOAD" \
  --auth-mode login \
  --overwrite false \
  --output none \
  || die "upload failed. Check the role assignment:
   az role assignment list --scope <container-id> --output table"

echo "    $BACKUP_CONTAINER/$BLOB"

# Read it back. Same principle as the archive verification above: an upload that reported success
# and stored nothing is exactly the failure a backup process must not have.
REMOTE_SIZE="$(az storage blob show \
  --account-name "$STORAGE_ACCOUNT" --container-name "$BACKUP_CONTAINER" --name "$BLOB" \
  --auth-mode login --query properties.contentLength --output tsv 2>/dev/null || echo 0)"
LOCAL_SIZE="$(stat -c%s "$UPLOAD")"

[ "$REMOTE_SIZE" = "$LOCAL_SIZE" ] \
  || die "the uploaded blob is $REMOTE_SIZE bytes and the local file is $LOCAL_SIZE. Not a backup."
echo "    verified: $REMOTE_SIZE bytes, matching the local file"

# ── 6. Prune locally ──────────────────────────────────────────────────────────────────────────
# Only the local copies. Blobs are never deleted by this script — retention in the container is a
# lifecycle-management policy, so that a compromised VM cannot delete the backups it just wrote.
#
#   az storage account management-policy create --account-name "$STORAGE_ACCOUNT" ...
#
# Mind Cool tier's 30-day minimum storage duration when writing that policy: expiring a blob at 7
# days is billed as though it lived for 30.

say "6/6 pruning local copies older than $LOCAL_RETENTION_DAYS days"
removed="$(find "$BACKUP_DIR" -name 'azmoth-*.dump*' -mtime "+$LOCAL_RETENTION_DAYS" -print -delete | wc -l)"
echo "    removed $removed, kept $(find "$BACKUP_DIR" -name 'azmoth-*.dump*' | wc -l)"

df -h / | awk 'NR==2 {printf "    disk: %s used of %s (%s)\n", $3, $2, $5}'

say "done"
