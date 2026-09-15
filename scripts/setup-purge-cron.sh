#!/usr/bin/env bash
#
# Turn on the nightly retention purge. Run ONCE on the VM, after the first successful deploy.
#
#     ssh azmoth@<host>
#     /opt/azmoth/repo/scripts/setup-purge-cron.sh
#
# It installs one crontab entry: `docker compose … exec engine python -m scripts.purge_old_data`,
# at 03:30 — after the 02:00 backup (§ 5.4's `setup-backups.sh`) and off the traffic peak. It takes
# no action against the database itself; the last thing it prints is the `--dry-run` command, so the
# first real look at what is over the retention window is a deliberate act you read, not a cron mail
# nobody opens.
#
# ── Why this exists ────────────────────────────────────────────────────────────────────────────
# `infra/docker/docker-compose.yml` has documented `DATA_RETENTION_DAYS` and `RETENTION_ENABLED`
# since the engine gained `scripts/purge_old_data.py`, and the comment beside them has always said
# "the host's crontab runs it" — DSGVO Art. 5 Abs. 1 lit. e (Speicherbegrenzung) is not satisfied by
# a script that exists, only by one that runs. Nothing installed it. `apps/engine/README.md`
# documents the cron *line*; this is what actually puts it in a crontab, the same relationship
# `setup-backups.sh` has to the backup line in `docs/deploy/RUNBOOK.md`.
#
# ── Why this is a separate script and not part of deploy.sh ───────────────────────────────────
# `deploy.sh` runs on every push and must stay unattended; a crontab is host state that a redeploy
# must not rewrite behind an operator's back, the same argument `setup-backups.sh` makes for the
# backup entry. This is idempotent for the same reason that one is: re-running it replaces its own
# marked line rather than adding a second, so running it because you are unsure whether the purge is
# already scheduled is always safe.
#
# ── What this script deliberately does not do ─────────────────────────────────────────────────
# It does not set `DATA_RETENTION_DAYS` or `RETENTION_ENABLED` — those are already in
# `/opt/azmoth/shared/.env`, written by `deploy.sh` from `infra/docker/docker-compose.yml`'s
# defaults or an operator's override, and this script has no opinion on the retention window. It
# also does not run the purge itself, for the reason `setup-backups.sh` gives about the first
# backup: the first purge should be a `--dry-run` an operator reads, not a side effect of enabling
# the schedule.

set -euo pipefail

REMOTE_ROOT="${REMOTE_ROOT:-/opt/azmoth}"
REPO_DIR="${REPO_DIR:-$REMOTE_ROOT/repo}"
COMPOSE_FILES=(-f infra/docker/docker-compose.yml -f infra/docker/docker-compose.aws.yml)
CRON_LOG="${CRON_LOG:-/var/log/azmoth-retention.log}"

# 03:30 local time — after the 02:00 backup `setup-backups.sh` installs and off the traffic peak.
# The ordering matters: a purge is irreversible, and the night's backup is what you restore from if
# the retention window turns out to have been set wrong. Matches `apps/engine/README.md`'s § Retention.
CRON_SCHEDULE="${CRON_SCHEDULE:-30 3 * * *}"

# The marker that makes this idempotent — same role `CRON_MARKER` plays in setup-backups.sh.
CRON_MARKER="# azmoth-nightly-retention-purge"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[1;33m!!\033[0m %s\n' "$*" >&2; }
die()  { printf '\n\033[1;31m !! %s\033[0m\n' "$*" >&2; exit 1; }

# ── 0. Refuse to run somewhere this cannot possibly work ──────────────────────────────────────

[ "$(id -u)" -ne 0 ] || die "run this as the deployment user, not as root.

   The crontab has to belong to the user \`deploy.sh\` and the other aws-* targets already run
   'sudo docker compose' as — installing it under root's crontab would be a second identity with
   its own, un-audited access to the same containers.

       su - azmoth -c '$0'"

[ -d "$REPO_DIR" ] || die "$REPO_DIR does not exist.

   That is where deploy.sh checks out the repository. Deploy first, then run this."

[ -f "$REPO_DIR/infra/docker/docker-compose.yml" ] || die "$REPO_DIR/infra/docker/docker-compose.yml is missing.

   REPO_DIR does not look like a checkout of this repository. Pass the right one:
       REPO_DIR=/path/to/repo $0"

command -v docker >/dev/null || die "docker is not installed or not on PATH for $(id -un)."

command -v crontab >/dev/null || die "crontab is not installed.

       sudo apt-get install -y cron && sudo systemctl enable --now cron"

say "Nightly retention purge (DSGVO Art. 5 Abs. 1 lit. e)"
echo "    repo:        $REPO_DIR"
echo "    schedule:    $CRON_SCHEDULE  (03:30 daily, this box's local time — after the 02:00 backup)"
echo "    log:         $CRON_LOG"

# ── 1. Confirm the engine service is actually reachable ──────────────────────────────────────
#
# Not a hard requirement — a fresh box may not have `up` running yet — but worth telling the
# operator rather than silently installing a cron entry that will fail every night until they
# notice. `--dry-run` further down is the real verification; this is a cheaper, earlier hint.

say "1/2  Checking the engine container"

cd "$REPO_DIR"
if sudo COMPOSE_PROJECT_NAME=azmoth docker compose "${COMPOSE_FILES[@]}" \
    exec -T engine python -c "" >/dev/null 2>&1; then
  ok "engine container is up and reachable"
else
  warn "could not exec into the 'engine' service right now (is 'docker compose up -d' running?)."
  warn "the cron entry will still be installed — it runs nightly and does not need this to"
  warn "succeed at setup time — but run the --dry-run command this script prints once the stack"
  warn "is up, to confirm before trusting the schedule."
fi

# ── 2. The cron entry ──────────────────────────────────────────────────────────────────────────
#
# Same shape as setup-backups.sh's step 4: read the existing crontab, drop any line this script
# previously wrote, append the current one, install a PATH so `docker` and `sudo` resolve the same
# way from cron as they do from an interactive shell.

say "2/2  Installing the cron job for $(id -un)"

mkdir -p "$(dirname "$CRON_LOG")" 2>/dev/null || true
if ! touch "$CRON_LOG" 2>/dev/null; then
  warn "cannot write $CRON_LOG; falling back to \$HOME/azmoth-retention.log"
  CRON_LOG="$HOME/azmoth-retention.log"
fi

PURGE_COMMAND="cd $REPO_DIR && sudo COMPOSE_PROJECT_NAME=azmoth docker compose ${COMPOSE_FILES[*]} exec -T engine python -m scripts.purge_old_data"
CRON_ENTRY="$CRON_SCHEDULE $PURGE_COMMAND >> $CRON_LOG 2>&1  $CRON_MARKER"

EXISTING="$(crontab -l 2>/dev/null || true)"
NEW_CRONTAB="$(printf '%s\n' "$EXISTING" | grep -Fv "$CRON_MARKER" || true)"

if ! printf '%s\n' "$NEW_CRONTAB" | grep -q '^PATH='; then
  NEW_CRONTAB="$(printf 'SHELL=/bin/bash\nPATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin\n%s' "$NEW_CRONTAB")"
fi

printf '%s\n%s\n' "$NEW_CRONTAB" "$CRON_ENTRY" | grep -v '^$' | crontab - \
  || die "crontab refused the new entry; nothing was installed."

ok "installed"
crontab -l | grep -F "$CRON_MARKER" | sed 's/^/      /'

# ── Done ──────────────────────────────────────────────────────────────────────────────────────

cat <<DONE

$(printf '\033[1;32m==> The retention purge is scheduled.\033[0m')

    Read what it would do BEFORE 03:30 finds out for you:

        cd $REPO_DIR && sudo COMPOSE_PROJECT_NAME=azmoth docker compose ${COMPOSE_FILES[*]} \\
          exec -T engine python -m scripts.purge_old_data --dry-run

    \`DATA_RETENTION_DAYS\` and \`RETENTION_ENABLED\` come from $REMOTE_ROOT/shared/.env — see
    infra/docker/docker-compose.yml for their defaults and apps/engine/README.md § Retention for
    what each run deletes and what it never does (\`audit_events\`).

    Logs:      $CRON_LOG
    Schedule:  crontab -l
    Disable:   crontab -l | grep -Fv '$CRON_MARKER' | crontab -

DONE
