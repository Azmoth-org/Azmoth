#!/usr/bin/env bash
#
# Dump the Neon database, verify the archive, encrypt it, and push it off this VM to Amazon S3.
#
#     ./infra/scripts/backup-to-s3.sh
#
# Runs ON the VM, normally from cron.
#
# This is the AWS mirror of infra/scripts/backup-to-azure.sh. Everything about WHAT is backed up and
# HOW it is protected is identical — the same pg_dump over the network, the same archive
# verification, the same age encryption to a key that is not on this box. Only the destination and
# the credential mechanism changed. That file is not deleted: a deployment still on Azure needs it.
#
# ── The dump is taken over the network, because there is no local Postgres ────────────────────
# This deployment has no postgres container to `docker compose exec` into — the database is Neon's —
# so the dump is taken over the network instead: a throwaway `postgres:17-alpine` container runs
# `pg_dump` against Neon's DIRECT endpoint.
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
#   * **The container reaches Frankfurt over the default bridge**, which is all an outbound TLS
#     connection needs. `--network host` is not used, and must not be: see the note on the
#     credential below.
#
# infra/scripts/backup-db.sh and restore-db.sh are NOT deleted either. They remain the correct tools
# for the local docker-compose stack, where there is a postgres container to exec into.
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
# One thing to be honest about after the move from Azure: Neon runs on AWS, so this bucket is now
# with the same PROVIDER as the database rather than a different one. It is still a different
# account, a different service and a different credential, which is what the requirement is about.
# A practice that wants provider diversity needs a third copy somewhere else, and that is a
# conversation to have rather than a thing to imply by silence.
#
# ── Credentials: there are none on this box, except the one that has to be ────────────────────
# S3 authentication is the EC2 instance profile that infra/aws/provision.sh attached — an IAM role
# granting s3:PutObject and s3:GetObject on THIS BUCKET'S objects and nothing else. The AWS CLI
# picks up short-lived, automatically rotated credentials from the instance metadata service. No
# access key is written to disk, and there is no `~/.aws/credentials` on this box.
#
# The metadata service is IMDSv2-only (`HttpTokens=required`) with a hop limit of 1, which is why
# `pg_dump` runs in a bridged container and `aws` runs on the host: a container on a bridge network
# is one hop further away and cannot reach the metadata service at all. That is deliberate. If you
# ever move the upload into a container, you will have raised the hop limit to do it, and you will
# have made the credential reachable from anything else running in Docker.
#
# What the role deliberately CANNOT do:
#   * s3:DeleteObject — this box cannot destroy a backup it already wrote. Retention is a bucket
#     lifecycle rule, set from your laptop.
#   * s3:ListBucket — so `aws s3 ls s3://$STORAGE_BUCKET` from here answers AccessDenied. That is
#     the policy working, not a misconfiguration. List from your laptop with your own credentials.
#
# The Neon connection string IS a long-lived credential and it does sit in
# /opt/azmoth/shared/.env (mode 600), because the engine cannot connect without it. Rotate it in
# the Neon console — "Reset password" on the role — and re-run scripts/deploy.sh.
#
# ── Encryption: the VM can encrypt, and cannot decrypt ────────────────────────────────────────
# A dump is a complete copy of every approval, audit event and API key hash — clinical data under
# the AVV. S3 encrypts objects at rest with its own keys, which protects against a stolen disk in a
# datacentre and not against the bucket being made readable by a misconfiguration.
#
# So the dump is encrypted here, with `age`, to a PUBLIC key. The matching private key is never on
# this VM. A compromised VM can therefore write backups and cannot read back a single one — and
# neither can anyone who gets read access to the bucket.
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

# The AWS CLI v2 pages its output, which in cron means a job that never finishes. Off.
export AWS_PAGER=""

SHARED_ENV="${SHARED_ENV:-/opt/azmoth/shared/.env}"
BACKUP_DIR="${BACKUP_DIR:-/opt/azmoth/backups}"

# Kept short. The object in S3 is the archive; local copies exist to make a same-day restore fast
# and to give the verification something to read.
LOCAL_RETENTION_DAYS="${LOCAL_RETENTION_DAYS:-7}"

# At least the server's major version. Neon is on Postgres 17; a pg_dump older than the server
# refuses with "server version mismatch", which is the one failure worth pinning against.
PGDUMP_IMAGE="${PGDUMP_IMAGE:-postgres:17-alpine}"

# Pull configuration out of the deployment's own env file, so this script has no second copy of the
# bucket name or the connection string to go stale.
#
# ── The env file has to be shell-sourceable, and that is not automatic ────────────────────────
# A Neon connection string ends in a query string, typically
# '?sslmode=require&channel_binding=require'. An unquoted '&' in a sourced file is a background
# operator, and the resulting parse error abandons the REST OF THE FILE — so the symptom of an
# unquoted DATABASE_URL is not a broken database URL, it is this script reporting that
# STORAGE_BUCKET is unset. That is a genuinely confusing half-hour, so it is checked for by name.
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

STORAGE_BUCKET="${STORAGE_BUCKET:-}"
# The key prefix inside the bucket. The Azure script had a container for this; a bucket has no
# containers, so the same separation is a prefix — which is also what makes listing a month a prefix
# query rather than a scan.
BACKUP_PREFIX="${BACKUP_PREFIX:-db-backups}"
AGE_RECIPIENT="${AGE_RECIPIENT:-}"
DATABASE_URL="${DATABASE_URL:-}"

# Normally unset and picked up from the instance metadata service, which knows which region this
# instance is in. Defaulted anyway so that a box whose IMDS lookup is slow does not fail with the
# unhelpful "You must specify a region".
AWS_REGION="${AWS_REGION:-eu-central-1}"
export AWS_REGION
export AWS_DEFAULT_REGION="$AWS_REGION"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31m !! %s\033[0m\n' "$*" >&2; exit 1; }

[ -n "$STORAGE_BUCKET" ] || die "STORAGE_BUCKET is not set.
   This is the S3 bucket infra/aws/provision.sh created; it prints the name in its final banner.
   Add it to $SHARED_ENV:   echo 'STORAGE_BUCKET=azmoth-backups-xxxxxx' >> $SHARED_ENV"

[ -n "$DATABASE_URL" ] || die "DATABASE_URL is not set in $SHARED_ENV.
   This script dumps Neon over the network and needs the DIRECT (non-pooled) connection string.
   scripts/deploy.sh writes it; if it is missing, the deployment cannot be running either."

command -v aws >/dev/null || die "the AWS CLI is not installed on this VM.
   sudo snap install aws-cli --classic
   scripts/deploy.sh installs it during bootstrap; a box provisioned before that needs it by hand."

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
    echo "    !! This dump — every approval and audit event — goes up protected only by S3's"
    echo "    !! at-rest encryption and the bucket being private. Set AGE_RECIPIENT."
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

# ── 4. Confirm the instance profile ───────────────────────────────────────────────────────────
# There is no login step. The Azure script needed `az login --identity`; the AWS CLI resolves the
# instance profile through the metadata service on its own, so the equivalent here is asking WHO it
# resolved to — which is worth doing, because the failure without it lands at the upload as an
# AccessDenied that reads like a policy problem when it is actually "this box has no role at all".

say "4/6 checking the instance profile"
CALLER_ARN="$(aws sts get-caller-identity --query Arn --output text 2>/dev/null || true)"

[ -n "$CALLER_ARN" ] || die "the AWS CLI could not authenticate.
   On this VM that means the instance profile is missing or the metadata service is unreachable.
   Re-run infra/aws/provision.sh from your laptop, which attaches it. Check by hand with:
       TOKEN=\$(curl -sX PUT http://169.254.169.254/latest/api/token \\
         -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
       curl -s -H \"X-aws-ec2-metadata-token: \$TOKEN\" \\
         http://169.254.169.254/latest/meta-data/iam/security-credentials/"

case "$CALLER_ARN" in
  *:assumed-role/*)
    echo "    ok — ${CALLER_ARN##*/} via an assumed role; no credential is stored on this VM" ;;
  *)
    # Not fatal: a long-lived key works, and refusing would strand an operator debugging by hand.
    # Said loudly, because it means there IS a credential on this box that outlives a reboot.
    echo "    !! authenticated as $CALLER_ARN, which is NOT an instance-profile role."
    echo "    !! Something configured a long-lived access key on this VM. That key sits next to the"
    echo "    !! dumps it protects and does not expire. Remove ~/.aws/credentials and re-run"
    echo "    !! infra/aws/provision.sh, which attaches the role instead." ;;
esac

# ── 5. Upload ─────────────────────────────────────────────────────────────────────────────────
# Objects are laid out by date, so listing a month is a prefix query rather than a scan:
#     s3://<bucket>/db-backups/2026/09/azmoth-20260902T031500Z.dump.age
#
# A timestamped key means this can never destroy an earlier backup, and the check below makes that
# a guarantee rather than a convention. `aws s3 cp` has no `--overwrite false` — S3 PUT is
# last-writer-wins — so the key is asked about first. Two things back that up: the bucket is
# versioned, so an overwrite would leave the old version retrievable, and the instance profile has
# no s3:DeleteObject, so nothing here can remove one either way.

say "5/6 uploading"
KEY="$BACKUP_PREFIX/$(date -u +%Y/%m)/$(basename "$UPLOAD")"

if aws s3api head-object --bucket "$STORAGE_BUCKET" --key "$KEY" >/dev/null 2>&1; then
  die "s3://$STORAGE_BUCKET/$KEY already exists, and this script will not overwrite a backup.
   The key carries a UTC timestamp to the second, so this means the job ran twice in the same
   second — or the clock went backwards. Neither is routine; look before re-running."
fi

# `--only-show-errors` because this runs from cron: the default progress meter writes carriage
# returns that turn a mailed log into an unreadable single line.
#
# No `--sse` flag: the bucket has default encryption (SSE-S3) applied by infra/aws/provision.sh, so
# the object is encrypted at rest whether or not the caller asks. Passing it here would also be the
# only thing standing between an operator and an unencrypted object if they ever copied a file up by
# hand, which is exactly why it belongs on the bucket instead.
#
# No storage class either. STANDARD_IA is cheaper per GB and carries a 30-day minimum billing
# duration and a 128 KB minimum object size — on a pilot's few GB the saving is cents and the
# early-deletion penalty is a real trap. Transition on age with a bucket lifecycle rule if it ever
# matters; do not pick a class per upload.
aws s3 cp "$UPLOAD" "s3://$STORAGE_BUCKET/$KEY" --only-show-errors \
  || die "upload failed.
   AccessDenied here means the instance profile does not grant s3:PutObject on this bucket. Check
   from your laptop:
       aws iam get-role-policy --role-name azmoth-vm-backup-role --policy-name s3-backup-write
   Re-running infra/aws/provision.sh reapplies the policy."

echo "    s3://$STORAGE_BUCKET/$KEY"

# Read it back. Same principle as the archive verification above: an upload that reported success
# and stored nothing is exactly the failure a backup process must not have.
REMOTE_SIZE="$(aws s3api head-object --bucket "$STORAGE_BUCKET" --key "$KEY" \
  --query ContentLength --output text 2>/dev/null || echo 0)"
LOCAL_SIZE="$(stat -c%s "$UPLOAD")"

[ "$REMOTE_SIZE" = "$LOCAL_SIZE" ] \
  || die "the uploaded object is $REMOTE_SIZE bytes and the local file is $LOCAL_SIZE. Not a backup."
echo "    verified: $REMOTE_SIZE bytes, matching the local file"

# ── 6. Prune locally ──────────────────────────────────────────────────────────────────────────
# Only the local copies. Objects in S3 are never deleted by this script — the instance profile has
# no s3:DeleteObject, so a compromised VM cannot delete the backups it just wrote even if this file
# were edited to try. Retention in the bucket is a lifecycle rule, set from your laptop:
#
#   aws s3api put-bucket-lifecycle-configuration --bucket "$STORAGE_BUCKET" ...
#
# Mind that the bucket is versioned: a lifecycle rule that expires current versions leaves
# noncurrent ones behind unless it also has a NoncurrentVersionExpiration. A rule that appears to
# delete old backups and does not is worse than no rule, because it is believed.

say "6/6 pruning local copies older than $LOCAL_RETENTION_DAYS days"
removed="$(find "$BACKUP_DIR" -name 'azmoth-*.dump*' -mtime "+$LOCAL_RETENTION_DAYS" -print -delete | wc -l)"
echo "    removed $removed, kept $(find "$BACKUP_DIR" -name 'azmoth-*.dump*' | wc -l)"

df -h / | awk 'NR==2 {printf "    disk: %s used of %s (%s)\n", $3, $2, $5}'

say "done"
