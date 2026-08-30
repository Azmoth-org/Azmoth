#!/usr/bin/env bash
#
# Take a verified dump and push it off this VM, to Azure Blob Storage.
#
#     ./infra/scripts/backup-to-azure.sh
#
# Runs ON the VM, normally from cron. It wraps `infra/scripts/backup-db.sh` rather than replacing
# it — that script already dumps in custom format and proves the archive is readable by listing its
# table of contents, and a backup script that skips the verification produces files nobody has
# opened until the day they need one.
#
# ── Why Blob Storage and not a second disk ────────────────────────────────────────────────────
# A data disk attached to this VM is deleted with this VM. docs/OPERATIONS.md already says to keep
# dumps off the same host as the database, and a disk in the same resource group is the same host
# for every failure that actually happens: the VM is deleted, the resource group is deleted, the
# subscription lapses when the credit runs out. A blob survives all three, costs about EUR 0.01 per
# gigabyte-month in the Cool tier, and is in the same EU region for the same AVV reason the VM is.
#
# ── Credentials: there are none on this box ───────────────────────────────────────────────────
# Authentication is the VM's system-assigned managed identity, granted "Storage Blob Data
# Contributor" on this container alone by infra/azure/provision.sh. `az login --identity` gets a
# short-lived token from the instance metadata endpoint. No storage account key is written to disk,
# which matters more than usual here because the credential would otherwise sit next to the dumps.
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

REPO_ROOT="${REPO_ROOT:-/opt/azmoth/repo}"
SHARED_ENV="${SHARED_ENV:-/opt/azmoth/shared/.env}"
BACKUP_DIR="${BACKUP_DIR:-/opt/azmoth/backups}"

# Kept short. The blob is the archive; local copies exist to make a same-day restore fast and to
# give the verification something to read.
LOCAL_RETENTION_DAYS="${LOCAL_RETENTION_DAYS:-7}"

# Pull configuration out of the deployment's own env file, so this script has no second copy of the
# storage account name to go stale.
if [ -f "$SHARED_ENV" ]; then
  set -a
  # shellcheck disable=SC1090  # the path is a deployment location, not a file in this repo
  . "$SHARED_ENV"
  set +a
fi

STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-}"
BACKUP_CONTAINER="${BACKUP_CONTAINER:-db-backups}"
AGE_RECIPIENT="${AGE_RECIPIENT:-}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31m !! %s\033[0m\n' "$*" >&2; exit 1; }

[ -n "$STORAGE_ACCOUNT" ] || die "STORAGE_ACCOUNT is not set.
   Add it to $SHARED_ENV:   echo 'STORAGE_ACCOUNT=azmothbackupxxxx' >> $SHARED_ENV"

command -v az >/dev/null || die "the Azure CLI is not installed on this VM.
   curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash"

# ── 1. Dump ───────────────────────────────────────────────────────────────────────────────────

say "1/5 dumping and verifying"
mkdir -p "$BACKUP_DIR"

cd "$REPO_ROOT"
BACKUP_DIR="$BACKUP_DIR" \
COMPOSE_FILE="$REPO_ROOT/infra/docker/docker-compose.yml" \
COMPOSE_PROJECT_NAME=azmoth \
  ./infra/scripts/backup-db.sh

DUMP="$(ls -t "$BACKUP_DIR"/*.dump 2>/dev/null | head -1)"
[ -n "$DUMP" ] || die "backup-db.sh reported success but produced no file"
echo "    $DUMP ($(du -h "$DUMP" | cut -f1))"

# ── 2. Encrypt ────────────────────────────────────────────────────────────────────────────────

say "2/5 encrypting"

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

# ── 3. Authenticate ───────────────────────────────────────────────────────────────────────────

say "3/5 authenticating with the VM's managed identity"
az login --identity --output none 2>/dev/null \
  || die "az login --identity failed.
   The VM has no managed identity, or it has no role on the container. Re-run
   infra/azure/provision.sh from your laptop, which assigns both."
echo "    ok — no credential is stored on this VM"

# ── 4. Upload ─────────────────────────────────────────────────────────────────────────────────
# Blobs are laid out by date, so listing a month is a prefix query rather than a scan:
#     db-backups/2026/08/azmoth-20260830T031500Z.dump.age

say "4/5 uploading"
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

# Read it back. Same principle as backup-db.sh verifying its own archive: an upload that reported
# success and stored nothing is exactly the failure a backup process must not have.
REMOTE_SIZE="$(az storage blob show \
  --account-name "$STORAGE_ACCOUNT" --container-name "$BACKUP_CONTAINER" --name "$BLOB" \
  --auth-mode login --query properties.contentLength --output tsv 2>/dev/null || echo 0)"
LOCAL_SIZE="$(stat -c%s "$UPLOAD")"

[ "$REMOTE_SIZE" = "$LOCAL_SIZE" ] \
  || die "the uploaded blob is $REMOTE_SIZE bytes and the local file is $LOCAL_SIZE. Not a backup."
echo "    verified: $REMOTE_SIZE bytes, matching the local file"

# ── 5. Prune locally ──────────────────────────────────────────────────────────────────────────
# Only the local copies. Blobs are never deleted by this script — retention in the container is a
# lifecycle-management policy, so that a compromised VM cannot delete the backups it just wrote.
#
#   az storage account management-policy create --account-name "$STORAGE_ACCOUNT" ...

say "5/5 pruning local copies older than $LOCAL_RETENTION_DAYS days"
removed="$(find "$BACKUP_DIR" -name 'azmoth-*.dump*' -mtime "+$LOCAL_RETENTION_DAYS" -print -delete | wc -l)"
echo "    removed $removed, kept $(find "$BACKUP_DIR" -name 'azmoth-*.dump*' | wc -l)"

df -h / | awk 'NR==2 {printf "    disk: %s used of %s (%s)\n", $3, $2, $5}'

say "done"
