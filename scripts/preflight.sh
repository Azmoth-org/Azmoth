#!/usr/bin/env bash
#
# The pre-flight checklist, as a program rather than a page somebody reads down.
#
#     ./scripts/preflight.sh 20.79.12.34 --domain azmoth.com
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
DOMAIN="${DOMAIN:-azmoth.com}"
SSH_USER="${SSH_USER:-azmoth}"
REMOTE_ROOT=/opt/azmoth
RUN_DB_TEST=true

while [ $# -gt 0 ]; do
  case "$1" in
    --domain)            DOMAIN="$2"; shift 2 ;;
    --user)              SSH_USER="$2"; shift 2 ;;
    # `--skip-restore-test` is kept as an alias. It named a check that no longer exists — the
    # local-Postgres restore test — and anyone with it in a shell history or a CI job should get the
    # new behaviour rather than "unknown option".
    --skip-db-test|--skip-restore-test) RUN_DB_TEST=false; shift ;;
    -h|--help)
      echo "usage: ./scripts/preflight.sh <host> [--domain d] [--user u] [--skip-db-test]"
      exit 0 ;;
    *) HOST="$1"; shift ;;
  esac
done

[ -n "$HOST" ] || { echo "usage: ./scripts/preflight.sh <host> [--domain azmoth.com]" >&2; exit 2; }

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
#
# 5432, 3001 and 8080 are still checked even though nothing on this box could open them any more —
# the database is Neon's, the marketing site is Vercel's, and adminer is profiled out of the azure
# override. A check for a port that cannot be open is nearly free and catches the case this list
# exists for: somebody adding a service back.
for p in 8000 5432 3000 3001 8080; do
  label=$(case $p in 8000) echo "engine";; 5432) echo "postgres — external, nothing local";;
                     3000) echo "web";; 3001) echo "marketing — on Vercel, not here";;
                     8080) echo "adminer — profiled out";; esac)
  if port_open "$HOST" "$p"; then
    bad "[SEC] port $p ($label) is OPEN and must not be"
    if [ "$p" = 8000 ]; then
      note "This is the whole reason the engine sits behind the web tier. Anyone reaching it can"
      note "forge X-Organization-ID and read or write any practice's records."
    fi
    if [ "$p" = 5432 ]; then
      note "There is no Postgres on this box. Something else is listening on 5432 — find out what."
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

# TWO names, not four. `azmoth.com` and `www.azmoth.com` are Vercel's — see the check in § 2b,
# which asserts the opposite of what this loop asserts about them.
for n in "$APP_HOST" "$API_HOST"; do check_cert "$n"; done

code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "http://$APP_HOST/" 2>/dev/null || echo 000)"
if [ "$code" = "308" ] || [ "$code" = "301" ] || [ "$code" = "302" ]; then
  ok "http://$APP_HOST redirects to HTTPS ($code)"
else
  bad "http://$APP_HOST answered $code, expected a redirect to HTTPS"
fi

# ── 2b. The marketing site is somewhere else, and stays there [SEC] ───────────────────────────
#
# This replaces the old `https://www.$DOMAIN/ → 200 (marketing)` check, which had quietly become a
# FALSE GREEN: with the site on Vercel it passes whatever this VM is doing, so it reported the
# deployment healthy on the strength of a service the deployment has nothing to do with.
#
# Inverted, the same two requests are worth something. What can actually go wrong now is somebody
# pointing the apex or www A record at this VM — following, say, an old runbook. That takes the
# public site down AND makes Caddy request a certificate for a name Vercel already holds.

section "2b. azmoth.com is still served by Vercel, not by this VM [SEC]"

for n in "$DOMAIN" "www.$DOMAIN"; do
  resolved="$(dig +short "$n" A 2>/dev/null | tail -1)"
  if [ -z "$resolved" ]; then
    skipped "$n does not resolve to an A record (a CNAME to Vercel is normal — check by hand)"
  elif [ "$resolved" = "$HOST" ]; then
    bad "[SEC] $n resolves to THIS VM ($HOST). It must point at Vercel."
    note "This box has no marketing container and its Caddyfile has no site block for that name,"
    note "so the public site is down. Move the record back to Vercel. Do not 'fix' it by adding a"
    note "site block here — see the header of infra/docker/Caddyfile."
  else
    ok "$n → $resolved (not this VM)"
  fi
done

# And it should still be up, wherever it is. A 200 here is not a statement about the VM, which is
# why it is in its own section and not in § 4.
code="$(status_of "https://www.$DOMAIN/")"
if [ "$code" = "200" ]; then
  ok "https://www.$DOMAIN/ → 200 (served by Vercel)"
else
  bad "https://www.$DOMAIN/ → $code — the public site is not answering"
  note "This is a Vercel problem, not a VM problem. Check the Vercel dashboard, not the VM."
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

# ── 5. On the box ─────────────────────────────────────────────────────────────────────────────

section "5. On the box"

if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" true 2>/dev/null; then
  bad "cannot ssh to $SSH_TARGET — skipping every remaining check"
else
  containers="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$COMPOSE_CMD ps --format json" 2>/dev/null)"

  # THREE long-running services, and that is the whole list. `postgres` and `marketing` used to be
  # here; both are profiled out of docker-compose.azure.yml because the database is Neon's and the
  # public site is Vercel's. `engine-migrate` and `web-auth-migrate` are one-shots that exit 0 and
  # have no health status — they are checked by § 6 instead, by their effect on the schema.
  for svc in caddy web engine; do
    state="$(echo "$containers" | jq -r "select(.Service==\"$svc\") | .State" 2>/dev/null | head -1)"
    health="$(echo "$containers" | jq -r "select(.Service==\"$svc\") | .Health" 2>/dev/null | head -1)"
    if [ "$state" = "running" ] && { [ "$health" = "healthy" ] || [ -z "$health" ]; }; then
      ok "$svc is running${health:+ ($health)}"
    else
      bad "$svc is ${state:-missing}${health:+/$health}"
      note "ssh $SSH_TARGET '$COMPOSE_CMD logs --tail 50 $svc'"
    fi
  done

  # Nothing local should be listed at all beyond those three plus the exited one-shots. A `postgres`
  # container here means the deploy resolved the base file without the azure override.
  if echo "$containers" | jq -r '.Service' 2>/dev/null | grep -qx 'postgres'; then
    bad "[SEC] a 'postgres' container is running on this box"
    note "The azure override profiles it out, so the deploy did not use both -f flags. That means"
    note "the engine's port 8000 is probably published too — check § 1 above first."
  else
    ok "no local postgres container (the database is Neon's)"
  fi

  # [SEC] Who may create an account, read out of the RUNNING container rather than out of the .env
  # on disk. Those are two different questions: a value added to .env after the last `up -d` is not
  # in the process's environment, and the process's environment is what apps/web/lib/auth-allowlist.ts
  # actually reads. A stale container with an open door looks perfectly configured on disk.
  #
  # `printenv NAME` exits 1 when the variable is unset, so unset and empty are distinguished here —
  # they mean different things in the source (see the note on `null` vs `[]` in auth-allowlist.ts)
  # even though production refuses both.
  allowlist="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$COMPOSE_CMD exec -T web printenv SIGNUP_ALLOWLIST" 2>/dev/null | tr -d '\r')"
  if [ -n "$allowlist" ]; then
    ok "[SEC] sign-up allowlist is set in the running web container: $allowlist"
    case "$allowlist" in
      *@*) : ;;
      *) bad "[SEC] SIGNUP_ALLOWLIST does not look like an address list: '$allowlist'" ;;
    esac
    # A domain entry readmits everyone who can get an address at that domain. Legitimate for a
    # billing centre, and never what somebody meant to write for a two-person pilot.
    case ",$(printf '%s' "$allowlist" | tr -d ' ')," in
      *,@*) note "it contains a whole-domain entry — confirm that is deliberate" ;;
    esac
  else
    bad "[SEC] SIGNUP_ALLOWLIST is empty or unset in the running web container"
    note "Nobody can register — /signup refuses every address with SIGNUP_NOT_ALLOWED."
    note "Set it in $REMOTE_ROOT/shared/.env, copy it to repo/infra/docker/.env, then:"
    note "  ssh $SSH_TARGET '$COMPOSE_CMD up -d web'"
    note "Or redeploy: ./scripts/deploy.sh $HOST --signup-allowlist \"you@$DOMAIN\""
  fi

  # Swap. Nothing is built on this box any more, so this is runtime headroom rather than a build
  # crutch — a Soufflé solve that spikes on a 2 GiB machine must page rather than have the OOM
  # killer take the web container out from under somebody's approval.
  swap="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "free -m | awk '/Swap:/ {print \$2}'" 2>/dev/null)"
  if [ "${swap:-0}" -ge 2000 ]; then
    ok "${swap} MiB of swap present (headroom for a solver spike on 2 GiB)"
  else
    bad "only ${swap:-0} MiB of swap — an OOM kill would take out a running container"
    note "Re-run infra/azure/provision.sh, which configures a 4 GiB swapfile."
  fi

  # Memory in use. Meaningful now in a way it was not on a 4 GiB build box: if this is already near
  # the limit at rest, the next solve is the one that pages.
  memfree="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "free -m | awk '/Mem:/ {print \$7}'" 2>/dev/null)"
  if [ "${memfree:-0}" -ge 300 ]; then
    ok "${memfree} MiB memory available at rest"
  else
    bad "only ${memfree:-0} MiB available — this VM is too small for the running stack"
    note "Take the next rung of the VM_SIZE ladder in infra/azure/provision.sh's header:"
    note "  VM_SIZE=Standard_B2als_v2 ./infra/azure/provision.sh   (4 GiB, ~3.1 months of credit)"
  fi

  disk="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "df -h / | awk 'NR==2 {print \$5}'" 2>/dev/null | tr -d '%')"
  if [ "${disk:-100}" -lt 80 ]; then
    ok "root filesystem ${disk}% used"
  else
    bad "root filesystem ${disk}% used — Docker build cache is the usual culprit"
    note "ssh $SSH_TARGET 'sudo docker system prune -af --filter until=168h'"
  fi
fi

# ── 6. Neon: reachable, on the right endpoints, and migrated ──────────────────────────────────
#
# This replaces the local-Postgres restore test, which cannot run here: it built a scratch database
# with `docker compose exec postgres psql`, and there is no postgres container. It also could not be
# ported — creating a throwaway database inside the Neon project on every preflight would burn the
# Free plan's compute allowance and, on a metered plan, cost money to prove something Neon's own
# instant-restore already covers.
#
# What matters instead is that the three things the split-endpoint design depends on are actually
# true in the RUNNING containers:
#
#   1. the engine reaches Neon at all, and on Postgres rather than the SQLite default
#   2. the engine is on the DIRECT endpoint and `web` is on the POOLED one — not the reverse, and
#      not both on one, because the failure that swap produces is intermittent and load-dependent
#   3. `alembic current` equals `alembic heads` — the schema is at the newest revision the deployed
#      image carries, not merely at *some* revision
#
# (3) is the one the old check could not make. `alembic current` printing a revision proved a
# migration had run at some point; it did not prove the container was not running an older image
# against a newer database, or a newer image against a database the migration step failed to
# advance. A missing column at runtime looks like an application bug for about an hour.
#
# Verifying an actual RESTORE is now § 7's manual step and OPERATIONS.md § 7.7, because it needs the
# age private key, which is deliberately not on this VM or in CI.

section "6. The Neon database [SEC for the endpoint split]"

if [ "$RUN_DB_TEST" != "true" ]; then
  skipped "database checks (--skip-db-test)"
elif ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" true 2>/dev/null; then
  skipped "database checks — no SSH"
else
  # One round trip, reported as parseable lines. `python -c` inside the engine container rather than
  # psql on the host: this reads the settings the PROCESS resolved, which is the only version of
  # "which database is it on" that matters. A value edited into .env after the last `up -d` is not
  # in the process's environment.
  db_out="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$COMPOSE_CMD exec -T engine python -c \"
import asyncio, urllib.parse
from app.config import get_settings
s = get_settings()
print('BACKEND', s.database_backend)
print('DURABLE', s.database_is_durable)
print('APPENV', s.app_env.value if hasattr(s.app_env, 'value') else s.app_env)
host = urllib.parse.urlsplit(s.database_url.replace('+asyncpg', '')).hostname or ''
print('HOST', host)
print('POOLED', '-pooler.' in host)
from sqlalchemy import text
from app.db.session import build_engine
async def probe():
    eng = build_engine(s)
    try:
        async with eng.connect() as c:
            print('SELECT1', (await c.execute(text('select 1'))).scalar_one())
            print('SERVERVER', (await c.execute(text('show server_version'))).scalar_one())
    finally:
        await eng.dispose()
asyncio.run(probe())
\"" 2>&1)"

  if echo "$db_out" | grep -q '^SELECT1 1$'; then
    ok "the engine can query Neon (select 1 round-tripped)"
    note "server_version $(echo "$db_out" | awk '/^SERVERVER/ {print $2}')"
  else
    bad "the engine could NOT query the database"
    note "This is the check that fails when Neon's compute is suspended and the resume timed out,"
    note "when the connection string is wrong, or when the Free plan's compute allowance is spent"
    note "(which drops existing connections and refuses new ones until the next billing period)."
    echo "$db_out" | tail -12 | sed 's/^/        /'
  fi

  if echo "$db_out" | grep -q '^DURABLE True$'; then
    ok "the engine is on a durable Postgres database ($(echo "$db_out" | awk '/^BACKEND/ {print $2}'))"
  else
    bad "the engine is NOT on Postgres — approvals would not be durable"
  fi

  # [SEC] The endpoint split. See the long note in docker-compose.azure.yml on the engine service:
  # SQLAlchemy+asyncpg cannot be made safe behind a transaction-mode pooler without a Python change,
  # so the engine on `-pooler` is a latent intermittent DuplicatePreparedStatementError, not a
  # working configuration that happens to be slower.
  if echo "$db_out" | grep -q '^POOLED False$'; then
    ok "[SEC] the engine is on Neon's DIRECT endpoint ($(echo "$db_out" | awk '/^HOST/ {print $2}'))"
  elif echo "$db_out" | grep -q '^POOLED True$'; then
    bad "[SEC] the engine is on Neon's POOLED endpoint — swap DATABASE_URL and DATABASE_URL_POOLED"
    note "asyncpg mints named prepared statements that a transaction-mode pooler mishandles. The"
    note "symptom is intermittent DuplicatePreparedStatementError under concurrency, not a clean"
    note "failure now. DATABASE_URL must be the direct string; the pooled one is DATABASE_URL_POOLED."
  else
    bad "could not determine which Neon endpoint the engine is using"
  fi

  # The other half of the split: Better Auth SHOULD be pooled. A warning rather than a failure —
  # node-postgres on the direct endpoint is correct, just chattier.
  auth_url="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$COMPOSE_CMD exec -T web printenv AUTH_DATABASE_URL" 2>/dev/null | tr -d '\r')"
  case "$auth_url" in
    *-pooler.*) ok "the web tier is on Neon's POOLED endpoint (correct for Better Auth)" ;;
    "")         bad "AUTH_DATABASE_URL is unset in the running web container — sign-in cannot work" ;;
    *)          skipped "the web tier is on the direct endpoint, not the pooler"
                note "Correct but chattier: every route handler opens its own connection. Set"
                note "DATABASE_URL_POOLED in $REMOTE_ROOT/shared/.env and 'up -d web'." ;;
  esac

  # The migration-version check the old restore test could not make.
  mig_out="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$COMPOSE_CMD exec -T engine sh -c 'alembic current 2>/dev/null; echo ---; alembic heads 2>/dev/null'" 2>/dev/null)"
  # `alembic current` prints "<rev> (head)" when it is at head, and just "<rev>" when it is behind.
  # Comparing the bare revision ids against `heads` is what catches "behind", so the suffix and any
  # branch labels are stripped from both sides before the comparison.
  cur_rev="$(echo "$mig_out"  | sed -n '1,/^---$/p' | grep -oE '^[0-9a-z_]+' | sort -u | tr '\n' ' ' | xargs || true)"
  head_rev="$(echo "$mig_out" | sed -n '/^---$/,$p'  | grep -oE '^[0-9a-z_]+' | sort -u | tr '\n' ' ' | xargs || true)"

  if [ -z "$cur_rev" ]; then
    bad "alembic current returned nothing — the schema may never have been migrated"
    note "ssh $SSH_TARGET '$COMPOSE_CMD run --rm engine-migrate'"
  elif [ "$cur_rev" = "$head_rev" ]; then
    ok "schema is at head ($cur_rev)"
  else
    bad "schema is at '$cur_rev' but this image's head is '$head_rev'"
    note "The engine is querying a database the migration step did not advance. A missing column"
    note "at runtime looks like an application bug for about an hour. Re-run the migration:"
    note "  ssh $SSH_TARGET '$COMPOSE_CMD run --rm engine-migrate'"
  fi

  # A backup that has actually been taken, rather than a script that exists. Nothing here takes one
  # — that would dump clinical data on every preflight — so this asks the cheaper question.
  newest="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "ls -t $REMOTE_ROOT/backups/*.dump* 2>/dev/null | head -1" 2>/dev/null)"
  if [ -n "$newest" ]; then
    age_days="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "echo \$(( ( \$(date +%s) - \$(stat -c %Y '$newest') ) / 86400 ))" 2>/dev/null)"
    if [ "${age_days:-999}" -le 2 ]; then
      ok "newest local dump is ${age_days}d old ($(basename "$newest"))"
    else
      bad "newest local dump is ${age_days} days old — the cron job is not running"
      note "ssh $SSH_TARGET 'crontab -l'  and see docs/OPERATIONS.md § 7.6"
    fi
  else
    bad "no dump has ever been taken on this box"
    note "Neon's Free-plan history window is SIX HOURS. That is a rollback, not a backup."
    note "Install the cron job — nothing does it for you. docs/OPERATIONS.md § 7.6:"
    note "  15 3 * * * $REMOTE_ROOT/repo/infra/scripts/backup-to-azure.sh >> /var/log/azmoth-backup.log 2>&1"
  fi
fi


# ── 7. Things a script cannot check ───────────────────────────────────────────────────────────

section "7. Do these by hand"

cat <<MANUAL
      □ Sign up, sign in, sign out in a browser at https://$APP_HOST
        — and confirm an address NOT on SIGNUP_ALLOWLIST is refused
      □ Upload a PADnext delivery and confirm the report renders
      □ Confirm a delivery with no 'echtdaten' attribute is refused with
        ECHTDATEN_UNDECLARED, and that scripts/anonymize_padnext.py produces one
        that is accepted. This is the pilot's data-protection boundary; it is
        worth seeing it work once rather than assuming it.
      □ Confirm 'schema_warnings' appears on a report from a non-conforming export
        (PADNEXT_SCHEMA_POLICY=warn is the pilot setting)
      □ Mint an API key in Einstellungen → API-Schlüssel, then from your laptop:
            curl -sS -X POST https://$API_HOST/api/v1/audit/single \\
              -H "X-API-Key: azm_live_..." -H 'Content-Type: application/xml' \\
              --data-binary @delivery.xml | jq .
      □ Copy /opt/azmoth/shared/.env somewhere off this VM (a password manager).
        It now holds BOTH Neon connection strings — without them the encrypted
        dumps in Blob Storage are files nobody can restore anywhere.
      □ Store the 'age' private key. Losing it loses every backup.
      □ Schedule the backup — nothing does it for you:
            ssh $SSH_TARGET 'crontab -l'
      □ RESTORE DRILL, once, by hand. This is the check § 6 cannot make: it
        needs the age private key, which is deliberately not on the VM or in CI.
        docs/OPERATIONS.md § 7.7 is the procedure — download a blob, decrypt it
        locally, 'pg_restore --list' it, and restore into a scratch Neon branch
        rather than over the live database.
      □ In the Neon console: confirm the project region is aws-eu-central-1
        (Frankfurt) and NOT a US region. It cannot be changed after creation.
      □ In the Neon console: set a spend limit, or watch the Free plan's compute
        allowance. Exhausting it DROPS live connections and refuses new ones
        until the next billing period — the pilot goes down, not degrades.
      □ Name every sub-processor in docs/AVV_TECHNICAL_ANNEX_DRAFT.md § 5.2,
        which used to say there are none. There are now four:
        Microsoft Azure (germanywestcentral), Neon/Databricks and AWS
        (aws-eu-central-1), and Vercel (azmoth.com).
      □ Request an executable AVV/DPA from Databricks for the Neon project.
        The self-serve neon.com/dpa is a click-accept schedule, not a signed
        contract, and a practice's lawyer will ask for the latter.
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
