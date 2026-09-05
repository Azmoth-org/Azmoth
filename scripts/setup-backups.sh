#!/usr/bin/env bash
#
# Turn on nightly encrypted backups. Run ONCE on the VM, after the first successful deploy.
#
#     ssh azmoth@<host>
#     /opt/azmoth/repo/scripts/setup-backups.sh
#
# It does three things and nothing else: it asks for the age public key that backups will be
# encrypted to, writes that key and the S3 bucket name into /opt/azmoth/shared/.env, and installs a
# crontab entry that runs infra/scripts/backup-to-s3.sh at 02:00 every day. It takes no backup
# itself — the last thing it prints is the command to take one, so that the first backup is a
# deliberate act you watch succeed rather than something that silently did or did not happen at 2am.
#
# ── Why this is a separate script and not part of deploy.sh ───────────────────────────────────
# Because it needs a secret that only exists on somebody's laptop, and deploy.sh is designed to be
# run repeatedly and unattended. An interactive prompt inside it would be a deployment that hangs in
# CI. This runs once, on the box, by a human who has the key in front of them.
#
# It is also idempotent, which matters more than it sounds: the natural thing to do when unsure
# whether backups are on is to run this again, and doing so must not install a second cron entry or
# corrupt an env file that a running deployment is reading.
#
# ── What the age key is, and why this script cannot generate it ───────────────────────────────
# Backups are encrypted with age before they leave the VM, to a PUBLIC key. The matching PRIVATE key
# is what decrypts them, and it must not be on this machine: a VM that holds both the backups' key
# and the backups is a VM whose compromise loses the backups too, which is most of the reason to
# have off-box backups at all.
#
# So the keypair is generated on YOUR LAPTOP:
#
#     age-keygen -o azmoth-backup.key
#
# That file contains both halves. Put it in a password manager and nowhere else. The line it prints
# starting `age1...` is the public half, and it is what this script asks for. Losing the private key
# means every backup ever taken is permanently unreadable — there is no recovery path, by design.
#
# ── What this script deliberately does not do ─────────────────────────────────────────────────
# It does not create the S3 bucket (infra/aws/provision.sh does, and prints the name), it does not
# grant the instance profile permission to write to it (same), and it does not install the AWS CLI
# (deploy.sh does during bootstrap). Each of those failures produces a clear error from
# backup-to-s3.sh itself, which is the script that actually needs them; duplicating the checks here
# would mean two places to update when one of them changes.

set -euo pipefail

REMOTE_ROOT="${REMOTE_ROOT:-/opt/azmoth}"
SHARED_ENV="${SHARED_ENV:-$REMOTE_ROOT/shared/.env}"
BACKUP_SCRIPT="${BACKUP_SCRIPT:-$REMOTE_ROOT/repo/infra/scripts/backup-to-s3.sh}"
BACKUP_DIR="${BACKUP_DIR:-$REMOTE_ROOT/backups}"
CRON_LOG="${CRON_LOG:-/var/log/azmoth-backup.log}"

# 02:00 local time. Chosen for the obvious reason and one less obvious one: it is outside any German
# practice's working hours, and it is before the 03:00–04:00 window that a default unattended-upgrades
# configuration reboots in, so a backup is taken before the box might restart rather than after.
CRON_SCHEDULE="${CRON_SCHEDULE:-0 2 * * *}"

# The marker that makes this idempotent. `crontab` has no notion of a named entry, so re-running
# without this would append a second identical line and the backup would run twice a night — which
# is not merely wasteful: backup-to-s3.sh refuses to overwrite an existing object, so the second run
# fails and mails a spurious error every single night.
CRON_MARKER="# azmoth-nightly-backup"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[1;33m!!\033[0m %s\n' "$*" >&2; }
die()  { printf '\n\033[1;31m !! %s\033[0m\n' "$*" >&2; exit 1; }

# ── 0. Refuse to run somewhere this cannot possibly work ──────────────────────────────────────
#
# Checked up front rather than discovered halfway through, because a half-configured backup is worse
# than an unconfigured one: it looks enabled.

[ "$(id -u)" -ne 0 ] || die "run this as the deployment user, not as root.

   The cron job must belong to the user that owns $REMOTE_ROOT and can talk to Docker —
   root's crontab would run backup-to-s3.sh as root, which then writes root-owned files into
   $BACKUP_DIR that the deployment user cannot clean up.

       su - azmoth -c '$0'"

[ -f "$SHARED_ENV" ] || die "$SHARED_ENV does not exist.

   That file is created by scripts/deploy.sh on the first deploy, and it holds the database URL
   this backup reads. Deploy first, then run this."

[ -r "$SHARED_ENV" ] && [ -w "$SHARED_ENV" ] || die "$SHARED_ENV is not writable by $(id -un).

   It is mode 600 and owned by the deployment user. Run this as that user."

[ -x "$BACKUP_SCRIPT" ] || die "$BACKUP_SCRIPT is missing or not executable.

   It ships with the repo, so this usually means the path is wrong for this box — pass the right
   one:   BACKUP_SCRIPT=/path/to/backup-to-s3.sh $0"

command -v crontab >/dev/null || die "crontab is not installed.

       sudo apt-get install -y cron && sudo systemctl enable --now cron"

# ── 1. Read what is already configured ────────────────────────────────────────────────────────
#
# Sourced in a subshell so that a value in the env file cannot clobber a variable this script is
# using — `BACKUP_DIR` is set in both, and picking up the deployment's copy silently would be a
# surprise. Only the two values this script cares about are carried back out.
#
# The `set -a` / `set +a` pair and the parse check mirror backup-to-s3.sh, and for the reason its
# comment gives at length: an unquoted '&' in a Neon URL is a syntax error that abandons the rest of
# the file, so the symptom of a bad DATABASE_URL line is an unrelated variable appearing to be unset.

if ! ( set -a; . "$SHARED_ENV" ) >/dev/null 2>&1; then
  die "$SHARED_ENV is not shell-sourceable.

   Almost certainly an unquoted value containing '&' — a Neon URL ends in
   '?sslmode=require&channel_binding=require', and unquoted that is a syntax error which
   abandons every line after it. Wrap the value in double quotes:

       DATABASE_URL=\"postgresql+asyncpg://...?sslmode=require&channel_binding=require\"

   Docker Compose strips the quotes, so nothing else changes."
fi

existing_value() {
  # shellcheck disable=SC1090  # a deployment path, not a file in this repo
  ( set -a; . "$SHARED_ENV" >/dev/null 2>&1; printf '%s' "${!1:-}" )
}

CURRENT_RECIPIENT="$(existing_value AGE_RECIPIENT)"
CURRENT_BUCKET="$(existing_value STORAGE_BUCKET)"

say "Nightly encrypted backups → S3"
echo "    env file:    $SHARED_ENV"
echo "    backup job:  $BACKUP_SCRIPT"
echo "    schedule:    $CRON_SCHEDULE  (02:00 daily, this box's local time)"

# ── 2. The age recipient ──────────────────────────────────────────────────────────────────────

say "1/4  Encryption key"

prompt_recipient() {
  # Everything this function prints except the key itself goes to stderr, because the caller reads
  # its stdout: `RECIPIENT="$(prompt_recipient)"`. A heredoc on stdout here lands *inside* the
  # captured value, and the result is an AGE_RECIPIENT line containing the entire help text — which
  # is exactly what happened before this comment existed.
  cat >&2 <<'EXPLAIN'
    Backups are encrypted on this VM before upload, to an age PUBLIC key. The private half
    must NOT be on this machine — generate the pair on your laptop and keep it in a password
    manager:

        age-keygen -o azmoth-backup.key

    Paste the PUBLIC key here. It is the line beginning 'age1'.

EXPLAIN

  local entered=""
  local attempt
  for attempt in 1 2 3; do
    # `read -r` so a backslash in the value is literal, and prompting on stderr so that stdout stays
    # clean if anybody ever pipes this script's output somewhere.
    printf '    AGE_RECIPIENT: ' >&2
    if ! read -r entered; then
      die "no input (stdin is closed).

   This script is interactive by design — it asks for a secret. To set the key without a prompt:
       AGE_RECIPIENT=age1... $0"
    fi
    entered="${entered#"${entered%%[![:space:]]*}"}"   # trim leading whitespace
    entered="${entered%"${entered##*[![:space:]]}"}"   # trim trailing whitespace

    # A shape check, not a cryptographic one. An age X25519 recipient is bech32: 'age1' followed by
    # 58 lowercase-alphanumeric characters. Catching a truncated paste or the PRIVATE key here is
    # worth the three lines — the alternative is discovering it at 2am tomorrow, in a cron mail
    # nobody reads, with no backup taken.
    if [[ "$entered" == AGE-SECRET-KEY-* ]]; then
      warn "that is the PRIVATE key. It must never be on this VM — paste the 'age1...' line instead."
      continue
    fi
    if [[ ! "$entered" =~ ^age1[0-9a-z]{58}$ ]]; then
      warn "that does not look like an age public key (expected 'age1' + 58 characters, got ${#entered})."
      continue
    fi

    printf '%s' "$entered"
    return 0
  done

  die "three attempts, no valid key. Nothing was written."
}

if [ -n "${AGE_RECIPIENT:-}" ]; then
  # Passed in the environment — the non-interactive path, for a re-run from a configuration
  # management tool. Not validated against the regex above on purpose: an operator who set it
  # explicitly has made a choice, and this script is not the place to second-guess a key format age
  # itself will reject in one line.
  RECIPIENT="$AGE_RECIPIENT"
  ok "using AGE_RECIPIENT from the environment"
elif [ -n "$CURRENT_RECIPIENT" ]; then
  echo "    $SHARED_ENV already has a key:  ${CURRENT_RECIPIENT:0:16}…"
  printf '    Replace it? Every backup taken so far was encrypted to the OLD key, and\n'
  printf '    replacing it does NOT make them readable with the new one. [y/N]: ' >&2
  read -r replace || replace=""
  if [[ "$replace" =~ ^[Yy]$ ]]; then
    RECIPIENT="$(prompt_recipient)"
  else
    RECIPIENT="$CURRENT_RECIPIENT"
    ok "keeping the existing key"
  fi
else
  RECIPIENT="$(prompt_recipient)"
fi

# ── 3. The bucket ─────────────────────────────────────────────────────────────────────────────

say "2/4  S3 bucket"

if [ -n "${STORAGE_BUCKET:-}" ]; then
  BUCKET="$STORAGE_BUCKET"
  ok "using STORAGE_BUCKET from the environment"
elif [ -n "$CURRENT_BUCKET" ]; then
  BUCKET="$CURRENT_BUCKET"
  ok "already configured: $BUCKET"
else
  echo "    The bucket infra/aws/provision.sh created. It prints the name in its final banner,"
  echo "    and it looks like 'azmoth-backups-a1b2c3'."
  echo
  printf '    STORAGE_BUCKET: ' >&2
  read -r BUCKET || die "no input (stdin is closed)."
  BUCKET="${BUCKET#"${BUCKET%%[![:space:]]*}"}"
  BUCKET="${BUCKET%"${BUCKET##*[![:space:]]}"}"
  # Strip a pasted s3:// prefix rather than rejecting it. Pasting the URI is the natural mistake and
  # the intent is unambiguous; failing on it would be pedantry.
  BUCKET="${BUCKET#s3://}"
  BUCKET="${BUCKET%/}"

  # S3 bucket naming rules, minus the ones that cannot be checked cheaply. This catches a pasted
  # ARN, a bucket with a path on the end, and an empty line.
  [[ "$BUCKET" =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]] \
    || die "'$BUCKET' is not a valid S3 bucket name (3–63 chars, lowercase letters, digits, '-' and '.')."
fi

# ── 4. Write the env file ─────────────────────────────────────────────────────────────────────
#
# Rewritten through a temporary file and moved into place, rather than edited or appended to. Three
# reasons, in ascending order of how bad the alternative is:
#
#   * Appending duplicates a key. The last one wins when sourced, so the file stops saying what it
#     means and a later hand-edit of the "wrong" line does nothing.
#   * `sed -i` on a live file truncates it for an instant. A container restarting in that instant
#     reads a partial env — and this file holds DATABASE_URL and the auth secret.
#   * `mv` within one filesystem is atomic. A reader sees the old file or the new one, never half.

say "3/4  Writing $SHARED_ENV"

TMP_ENV="$(mktemp "${SHARED_ENV}.XXXXXX")"
# The trap covers every exit path including the `die`s above this point in the file's execution.
trap 'rm -f "$TMP_ENV"' EXIT
chmod 600 "$TMP_ENV"

# Preserve the file's own permissions and owner rather than assuming 600/current-user: mktemp made
# the file, so it has this user's umask, and the original may legitimately differ.
if command -v chown >/dev/null 2>&1; then
  chown --reference="$SHARED_ENV" "$TMP_ENV" 2>/dev/null || true
fi
chmod --reference="$SHARED_ENV" "$TMP_ENV" 2>/dev/null || chmod 600 "$TMP_ENV"

# Everything except the two keys being set, in the original order, then the two keys. `grep -v` on
# an anchored pattern so a line like `OLD_AGE_RECIPIENT=` is not caught by accident.
grep -Ev '^[[:space:]]*(AGE_RECIPIENT|STORAGE_BUCKET)=' "$SHARED_ENV" > "$TMP_ENV" || true

# Values are double-quoted for the reason backup-to-s3.sh documents at length: this file is sourced
# by shell, and Compose strips the quotes, so quoting costs nothing and prevents the '&' class of
# failure. Neither of these two values can currently contain a metacharacter — that is not a reason
# to write the one line that would break if it ever did.
{
  printf '\n'
  printf '# Nightly backups. Written by scripts/setup-backups.sh on %s.\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  printf '# AGE_RECIPIENT is a PUBLIC key. The private half is not on this machine and must not be.\n'
  printf 'AGE_RECIPIENT="%s"\n' "$RECIPIENT"
  printf 'STORAGE_BUCKET="%s"\n' "$BUCKET"
} >> "$TMP_ENV"

# Prove the result parses before it replaces anything. A file that does not source is a deployment
# that will not restart, and this is the last moment at which that is still recoverable.
( set -a; . "$TMP_ENV" ) >/dev/null 2>&1 \
  || die "the rewritten env file does not parse; $SHARED_ENV was NOT modified."

mv "$TMP_ENV" "$SHARED_ENV"
trap - EXIT
ok "AGE_RECIPIENT   ${RECIPIENT:0:16}…"
ok "STORAGE_BUCKET  $BUCKET"

# ── 5. The cron entry ─────────────────────────────────────────────────────────────────────────
#
# Installed with `crontab`, not by dropping a file in /etc/cron.d. The whole reason is the one the
# root check at the top gives: /etc/cron.d entries name the user they run as and would need sudo to
# write, and this job must run as the deployment user — the one in the `docker` group, and the one
# owning $BACKUP_DIR. A user crontab is that by construction.

say "4/4  Installing the cron job for $(id -un)"

mkdir -p "$(dirname "$CRON_LOG")" 2>/dev/null || true
if ! touch "$CRON_LOG" 2>/dev/null; then
  # Not fatal. cron mails a job's output to the user when it cannot be redirected, so the run still
  # happens and its output still goes somewhere — just not where this expected.
  warn "cannot write $CRON_LOG; falling back to $BACKUP_DIR/backup.log"
  CRON_LOG="$BACKUP_DIR/backup.log"
  mkdir -p "$BACKUP_DIR"
fi

# `SHELL` and `PATH` are set in the crontab itself. cron's default PATH is /usr/bin:/bin, which does
# not include /snap/bin — where `sudo snap install aws-cli --classic` puts the AWS CLI, and
# therefore exactly the binary this job cannot run without. A backup job that works by hand and
# fails from cron is nearly always this.
CRON_ENTRY="$CRON_SCHEDULE $BACKUP_SCRIPT >> $CRON_LOG 2>&1  $CRON_MARKER"

# Read the existing crontab, drop any line this script previously wrote, append the current one.
# `|| true` because `crontab -l` exits non-zero when the user has no crontab at all, which is the
# normal state on a fresh box and not an error.
EXISTING="$(crontab -l 2>/dev/null || true)"
NEW_CRONTAB="$(printf '%s\n' "$EXISTING" | grep -Fv "$CRON_MARKER" || true)"

if ! printf '%s\n' "$NEW_CRONTAB" | grep -q '^PATH='; then
  NEW_CRONTAB="$(printf 'SHELL=/bin/bash\nPATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin\n%s' "$NEW_CRONTAB")"
fi

printf '%s\n%s\n' "$NEW_CRONTAB" "$CRON_ENTRY" | grep -v '^$' | crontab - \
  || die "crontab refused the new entry; nothing was installed. The env file was still written."

ok "installed"
crontab -l | grep -F "$CRON_MARKER" | sed 's/^/      /'

# ── Done ──────────────────────────────────────────────────────────────────────────────────────

cat <<DONE

$(printf '\033[1;32m==> Backups are configured.\033[0m')

    Take the first one NOW, and watch it succeed. Do not wait for 02:00 to find out whether the
    bucket permissions are right — that is the whole point of doing this step by hand:

        $BACKUP_SCRIPT

    Then confirm the object landed:

        aws s3 ls s3://$BUCKET/db-backups/ --recursive | tail

    And — the step everyone skips — verify you can actually DECRYPT one, on your laptop, with the
    private key. An untested backup is a hypothesis:

        aws s3 cp s3://$BUCKET/db-backups/<year>/<month>/<file>.dump.age .
        age -d -i azmoth-backup.key <file>.dump.age > restored.dump
        pg_restore --list restored.dump | head

    Logs:      $CRON_LOG
    Schedule:  crontab -l
    Disable:   crontab -l | grep -Fv '$CRON_MARKER' | crontab -

DONE
