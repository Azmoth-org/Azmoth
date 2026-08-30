#!/usr/bin/env bash
#
# The pre-flight checklist, as a program rather than a page somebody reads down.
#
#     ./scripts/preflight.sh 20.79.12.34 --domain azmoth.app
#
# Run it from your laptop after scripts/deploy.sh. It checks from the OUTSIDE — which is the point:
# `docker compose ps` proves the containers are up, and proves nothing about what the internet can
# reach. Half of these checks are things only an off-box caller can answer.
#
# Exit status is 0 only if every check passes. Failures are printed with what to do about them.
#
# Checks marked [SEC] are the ones that would be a security incident rather than an outage. They are
# not skippable and a failure in any of them should stop the pilot.

set -uo pipefail   # NOT -e: a failing check must be reported and counted, not abort the run

HOST=""
DOMAIN="${DOMAIN:-azmoth.app}"
SSH_USER="${SSH_USER:-azmoth}"
REMOTE_ROOT=/opt/azmoth
RUN_RESTORE_TEST=true

while [ $# -gt 0 ]; do
  case "$1" in
    --domain)            DOMAIN="$2"; shift 2 ;;
    --user)              SSH_USER="$2"; shift 2 ;;
    --skip-restore-test) RUN_RESTORE_TEST=false; shift ;;
    -h|--help)
      echo "usage: ./scripts/preflight.sh <host> [--domain d] [--user u] [--skip-restore-test]"
      exit 0 ;;
    *) HOST="$1"; shift ;;
  esac
done

[ -n "$HOST" ] || { echo "usage: ./scripts/preflight.sh <host> [--domain azmoth.app]" >&2; exit 2; }

APP_HOST="app.$DOMAIN"
API_HOST="api.$DOMAIN"
SSH_TARGET="$SSH_USER@$HOST"
SSH_OPTS=(-o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new)

COMPOSE_CMD="cd $REMOTE_ROOT/repo && sudo COMPOSE_PROJECT_NAME=azmoth docker compose \
-f infra/docker/docker-compose.yml -f infra/docker/docker-compose.azure.yml"

pass=0; fail=0; skip=0

ok()    { printf '  \033[1;32m✓\033[0m %s\n' "$*"; pass=$((pass+1)); }
bad()   { printf '  \033[1;31m✗\033[0m %s\n' "$*"; fail=$((fail+1)); }
note()  { printf '      \033[2m%s\033[0m\n' "$*"; }
skipped(){ printf '  \033[1;33m–\033[0m %s\n' "$*"; skip=$((skip+1)); }
section(){ printf '\n\033[1;36m%s\033[0m\n' "$*"; }

# Is a TCP port open from here? Returns 0 when something accepts a connection.
port_open() {
  timeout 5 bash -c "exec 3<>/dev/tcp/$1/$2" 2>/dev/null
}

status_of() {
  curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$@" 2>/dev/null || echo "000"
}

printf '\n\033[1mPre-flight — %s (%s)\033[0m\n' "$DOMAIN" "$HOST"

# ── 1. Ports ──────────────────────────────────────────────────────────────────────────────────

section "1. What the internet can reach [SEC]"

for p in 80 443; do
  if port_open "$HOST" "$p"; then
    ok "port $p is open (it must be)"
  else
    bad "port $p is CLOSED — it must be open"
    [ "$p" = 80 ] && note "80 is not optional: Let's Encrypt's HTTP-01 challenge arrives on it."
    note "Check the NSG rule: az network nsg rule list -g azmoth-pilot --nsg-name azmoth-vm-nsg -o table"
  fi
done

# The requirement, stated directly. 8000 is the engine, which authenticates nobody — see
# apps/engine/app/api/tenancy.py. An open 8000 means anyone can POST a proposal as any practice.
for p in 8000 5432 3000 3001 8080; do
  label=$(case $p in 8000) echo "engine";; 5432) echo "postgres";; 3000) echo "web";;
                     3001) echo "marketing";; 8080) echo "adminer";; esac)
  if port_open "$HOST" "$p"; then
    bad "[SEC] port $p ($label) is OPEN and must not be"
    if [ "$p" = 8000 ]; then
      note "This is the whole reason the engine sits behind the web tier. Anyone reaching it can"
      note "forge X-Organization-ID and read or write any practice's records."
    fi
    note "Fix: confirm the deploy used docker-compose.azure.yml (it unpublishes these), then"
    note "     ssh $SSH_TARGET '$COMPOSE_CMD ps' — nothing but caddy may list a published port."
  else
    ok "port $p ($label) is closed"
  fi
done

# ── 2. TLS ────────────────────────────────────────────────────────────────────────────────────

section "2. TLS certificates"

check_cert() {
  local name="$1"
  local out
  out="$(echo | timeout 15 openssl s_client -connect "$name:443" -servername "$name" 2>/dev/null \
        | openssl x509 -noout -issuer -subject -dates 2>/dev/null)"

  if [ -z "$out" ]; then
    bad "$name — no certificate could be retrieved"
    note "Either DNS does not point here yet, or Caddy has not issued one."
    note "ssh $SSH_TARGET '$COMPOSE_CMD logs caddy | tail -50'"
    return
  fi

  local issuer end
  issuer="$(echo "$out" | grep '^issuer=' | sed 's/^issuer=//')"
  end="$(echo "$out" | grep '^notAfter=' | sed 's/^notAfter=//')"

  # A self-signed certificate is what Caddy serves while issuance is failing. It is the single most
  # likely wrong state here, and from a browser it looks like a scary warning rather than "ACME is
  # in a backoff", so it is worth naming explicitly.
  if echo "$issuer" | grep -qi "let's encrypt\|ISRG"; then
    local days_left
    days_left=$(( ( $(date -d "$end" +%s 2>/dev/null || echo 0) - $(date +%s) ) / 86400 ))
    if [ "$days_left" -gt 0 ]; then
      ok "$name — Let's Encrypt, $days_left days left"
    else
      bad "$name — certificate has EXPIRED ($end)"
    fi
  else
    bad "$name — not a Let's Encrypt certificate. Issuer: $issuer"
    note "Caddy serves its own self-signed certificate when ACME fails. Check the logs and that"
    note "port 80 is reachable and the name resolves to $HOST."
  fi
}

for n in "$APP_HOST" "$API_HOST" "$DOMAIN" "www.$DOMAIN"; do check_cert "$n"; done

code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "http://$APP_HOST/" 2>/dev/null || echo 000)"
if [ "$code" = "308" ] || [ "$code" = "301" ] || [ "$code" = "302" ]; then
  ok "http://$APP_HOST redirects to HTTPS ($code)"
else
  bad "http://$APP_HOST answered $code, expected a redirect to HTTPS"
fi

# ── 3. The api. allowlist ─────────────────────────────────────────────────────────────────────

section "3. api.$DOMAIN exposes the partner API and nothing else [SEC]"

# Should be reachable: the partner surface, refusing for want of a key rather than 404ing.
code="$(status_of -X POST "https://$API_HOST/api/v1/audit/single" -H 'Content-Type: application/xml' --data '<x/>')"
if [ "$code" = "401" ]; then
  ok "POST /api/v1/audit/single without a key → 401 (reachable, and refusing)"
elif [ "$code" = "404" ]; then
  bad "POST /api/v1/audit/single → 404 — the partner API is not reachable at all"
  note "Check the handle blocks in infra/docker/Caddyfile."
else
  bad "POST /api/v1/audit/single → $code, expected 401"
fi

code="$(status_of "https://$API_HOST/api/v1/health")"
[ "$code" = "200" ] && ok "GET /api/v1/health → 200" || bad "GET /api/v1/health → $code, expected 200"

code="$(status_of "https://$API_HOST/openapi.json")"
[ "$code" = "200" ] && ok "GET /openapi.json → 200 (integrators can generate a client)" \
                    || bad "GET /openapi.json → $code, expected 200"

# Must NOT be reachable. These authenticate by an asserted header, so on a public host they are an
# anonymous write path into an append-only audit log.
for path in \
  "/api/v1/solve" \
  "/api/v1/proposals" \
  "/api/v1/padnext/audit" \
  "/api/v1/settings/api-keys" \
  "/api/v1/rules" \
  "/api/v1/demo"
do
  code="$(status_of "https://$API_HOST$path")"
  if [ "$code" = "404" ]; then
    ok "$path → 404 (not published)"
  else
    bad "[SEC] $path → $code — this endpoint is EXPOSED and authenticates nobody"
    note "Anyone can call it and name any organisation they like. See the header of"
    note "infra/docker/Caddyfile and apps/engine/app/api/tenancy.py."
  fi
done

# ── 4. The application ────────────────────────────────────────────────────────────────────────

section "4. The application"

code="$(status_of "https://$APP_HOST/api/health")"
[ "$code" = "200" ] && ok "https://$APP_HOST/api/health → 200" \
                    || bad "https://$APP_HOST/api/health → $code, expected 200"

# Every screen is behind a login. A 200 on / from an unauthenticated caller would mean the
# middleware is not gating.
code="$(status_of "https://$APP_HOST/")"
if [ "$code" = "307" ] || [ "$code" = "302" ] || [ "$code" = "200" ]; then
  ok "https://$APP_HOST/ answered $code"
  [ "$code" = "200" ] && note "200 here is the sign-in page rendering; confirm in a browser that it is not the app."
else
  bad "https://$APP_HOST/ → $code"
fi

# `useSecureCookies` is on under NODE_ENV=production (apps/web/lib/auth.ts). If the cookie comes
# back without Secure, the image is not running as production and the session cookie would travel
# over plain HTTP.
cookie="$(curl -sSI --max-time 15 "https://$APP_HOST/api/auth/get-session" 2>/dev/null | grep -i '^set-cookie:' || true)"
if [ -z "$cookie" ]; then
  skipped "no session cookie on an anonymous request — check Secure/HttpOnly after signing in"
elif echo "$cookie" | grep -qi 'secure'; then
  ok "session cookie carries Secure"
else
  bad "[SEC] a cookie was set WITHOUT Secure — it would be sent over plain HTTP"
fi

code="$(status_of "https://www.$DOMAIN/")"
[ "$code" = "200" ] && ok "https://www.$DOMAIN/ → 200 (marketing)" \
                    || bad "https://www.$DOMAIN/ → $code, expected 200"

# ── 5. On the box ─────────────────────────────────────────────────────────────────────────────

section "5. On the box"

if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" true 2>/dev/null; then
  bad "cannot ssh to $SSH_TARGET — skipping every remaining check"
else
  containers="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$COMPOSE_CMD ps --format json" 2>/dev/null)"

  for svc in caddy web engine postgres marketing; do
    state="$(echo "$containers" | jq -r "select(.Service==\"$svc\") | .State" 2>/dev/null | head -1)"
    health="$(echo "$containers" | jq -r "select(.Service==\"$svc\") | .Health" 2>/dev/null | head -1)"
    if [ "$state" = "running" ] && { [ "$health" = "healthy" ] || [ -z "$health" ]; }; then
      ok "$svc is running${health:+ ($health)}"
    else
      bad "$svc is ${state:-missing}${health:+/$health}"
      note "ssh $SSH_TARGET '$COMPOSE_CMD logs --tail 50 $svc'"
    fi
  done

  # The same check `make verify-db` runs: the engine must be on Postgres, not on the SQLite default.
  if ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$COMPOSE_CMD exec -T engine python -c \
     'from app.config import get_settings; assert get_settings().database_is_durable'" 2>/dev/null; then
    ok "the engine is on a durable Postgres database"
  else
    bad "the engine is NOT on Postgres — approvals would not survive a redeploy"
  fi

  migration="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$COMPOSE_CMD exec -T engine alembic current" 2>/dev/null | tail -1)"
  [ -n "$migration" ] && ok "alembic current: $migration" || bad "alembic current returned nothing"

  # Swap. Without it a later rebuild on this 4 GiB box is OOM-killed at exit 137 with no message.
  swap="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "free -m | awk '/Swap:/ {print \$2}'" 2>/dev/null)"
  if [ "${swap:-0}" -ge 2000 ]; then
    ok "${swap} MiB of swap present (the build needs it)"
  else
    bad "only ${swap:-0} MiB of swap — the next 'next build' will likely be OOM-killed"
    note "Re-run infra/azure/provision.sh, which configures a 4 GiB swapfile."
  fi

  disk="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "df -h / | awk 'NR==2 {print \$5}'" 2>/dev/null | tr -d '%')"
  if [ "${disk:-100}" -lt 80 ]; then
    ok "root filesystem ${disk}% used"
  else
    bad "root filesystem ${disk}% used — Docker build cache is the usual culprit"
    note "ssh $SSH_TARGET 'sudo docker system prune -af --filter until=168h'"
  fi
fi

# ── 6. Backup and restore ─────────────────────────────────────────────────────────────────────

section "6. Backups actually restore"

if [ "$RUN_RESTORE_TEST" != "true" ]; then
  skipped "restore test (--skip-restore-test)"
elif ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" true 2>/dev/null; then
  skipped "restore test — no SSH"
else
  # Take a real backup. The script verifies its own dump with `pg_restore --list` and fails if the
  # archive is unreadable, so a pass here means a file that can actually be opened.
  if ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
     "cd $REMOTE_ROOT/repo && sudo COMPOSE_PROJECT_NAME=azmoth BACKUP_DIR=$REMOTE_ROOT/backups \
      COMPOSE_FILE=infra/docker/docker-compose.yml ./infra/scripts/backup-db.sh" >/dev/null 2>&1; then
    ok "make backup-db produced a verified dump"
  else
    bad "the backup script failed"
    note "ssh $SSH_TARGET 'cd $REMOTE_ROOT/repo && sudo BACKUP_DIR=$REMOTE_ROOT/backups ./infra/scripts/backup-db.sh'"
  fi

  # Restore it into a scratch database and compare row counts. This is the check that distinguishes
  # "a file exists" from "a backup". It never touches the live database — the restore target is a
  # database created and dropped inside this block.
  echo "      restoring the newest dump into a scratch database..."
  # The heredoc is deliberately UNquoted: $REMOTE_ROOT is a local variable and has to be expanded
  # here, on the client. Everything meant to run on the server is escaped as \$ — check that before
  # editing this block, because an unescaped $ silently becomes an empty string on the far side.
  # shellcheck disable=SC2087
  restore_out="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -s" <<RESTORE 2>&1
set -uo pipefail
cd $REMOTE_ROOT/repo
C="sudo COMPOSE_PROJECT_NAME=azmoth docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.azure.yml exec -T postgres"
DUMP=\$(ls -t $REMOTE_ROOT/backups/*.dump 2>/dev/null | head -1)
[ -n "\$DUMP" ] || { echo "NO_DUMP"; exit 1; }

\$C psql -U azmoth -d postgres -q \
  -c "DROP DATABASE IF EXISTS azmoth_restore_test;" \
  -c "CREATE DATABASE azmoth_restore_test;" >/dev/null 2>&1
\$C pg_restore -U azmoth -d azmoth_restore_test --no-owner --exit-on-error < "\$DUMP" >/dev/null 2>&1 \
  || { echo "RESTORE_FAILED"; \$C psql -U azmoth -d postgres -q -c "DROP DATABASE IF EXISTS azmoth_restore_test;" >/dev/null 2>&1; exit 1; }

mismatch=0
for t in proposals audit_events batch_jobs api_keys; do
  live=\$(\$C psql -U azmoth -d azmoth              -tAc "SELECT count(*) FROM \$t" 2>/dev/null | tr -d '[:space:]')
  rest=\$(\$C psql -U azmoth -d azmoth_restore_test -tAc "SELECT count(*) FROM \$t" 2>/dev/null | tr -d '[:space:]')
  echo "ROW \$t \${live:-?} \${rest:-?}"
  [ "\$live" = "\$rest" ] || mismatch=1
done
\$C psql -U azmoth -d postgres -q -c "DROP DATABASE azmoth_restore_test;" >/dev/null 2>&1
[ \$mismatch -eq 0 ] && echo "MATCH" || echo "MISMATCH"
RESTORE
)"

  if echo "$restore_out" | grep -q "NO_DUMP"; then
    bad "no dump to restore"
  elif echo "$restore_out" | grep -q "RESTORE_FAILED"; then
    bad "pg_restore FAILED — this backup would not have saved you"
  elif echo "$restore_out" | grep -q "^MATCH$"; then
    echo "$restore_out" | awk '/^ROW/ {printf "      %-14s live=%-6s restored=%-6s\n", $2, $3, $4}'
    ok "restored into a scratch database; every row count matched"
  else
    echo "$restore_out" | awk '/^ROW/ {printf "      %-14s live=%-6s restored=%-6s\n", $2, $3, $4}'
    bad "row counts did not match after restore"
  fi
fi

# ── 7. Things a script cannot check ───────────────────────────────────────────────────────────

section "7. Do these by hand"

cat <<MANUAL
      □ Sign up, sign in, sign out in a browser at https://$APP_HOST
      □ Upload a PADnext delivery and confirm the report renders
      □ Confirm 'schema_warnings' appears on a report from a non-conforming export
        (PADNEXT_SCHEMA_POLICY=warn is the pilot setting)
      □ Mint an API key in Einstellungen → API-Schlüssel, then from your laptop:
            curl -sS -X POST https://$API_HOST/api/v1/audit/single \\
              -H "X-API-Key: azm_live_..." -H 'Content-Type: application/xml' \\
              --data-binary @delivery.xml | jq .
      □ Copy /opt/azmoth/shared/.env somewhere off this VM (a password manager)
      □ Schedule the backup — nothing does it for you:
            ssh $SSH_TARGET 'crontab -l'
      □ Name Microsoft Azure (region germanywestcentral) as a processor in
        docs/AVV_TECHNICAL_ANNEX_DRAFT.md §5.2, which currently says there are none
MANUAL

# ── Result ────────────────────────────────────────────────────────────────────────────────────

printf '\n────────────────────────────────────────────────────────────\n'
printf '  \033[1;32m%d passed\033[0m   \033[1;31m%d failed\033[0m   \033[1;33m%d skipped\033[0m\n' "$pass" "$fail" "$skip"
printf '────────────────────────────────────────────────────────────\n\n'

if [ "$fail" -gt 0 ]; then
  echo "Not ready. Fix the ✗ lines above — anything marked [SEC] before the pilot sees traffic."
  exit 1
fi
echo "Ready."
