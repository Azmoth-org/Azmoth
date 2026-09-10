#!/usr/bin/env bash
#
# Add one address (or a whole @domain) to the pilot's sign-up allowlist, from any machine with SSH
# access to the VM — no manual SSH session, no manual edit, no manual restart.
#
#     ./scripts/allow-signup.sh dr.b@praxis-nord.de
#     AZURE_HOST=20.79.12.34 ./scripts/allow-signup.sh dr.b@praxis-nord.de
#     ./scripts/allow-signup.sh '@praxis-nord.de' 20.79.12.34
#
# This scripts the edit scripts/deploy.sh already tells an operator to make by hand, next to
# SIGNUP_ALLOWLIST in its generated .env: "edit SIGNUP_ALLOWLIST in /opt/azmoth/shared/.env and
# restart the web service." See that file's header and apps/web/lib/auth-allowlist.ts for what
# this variable controls, why an unset list admits nobody, and why comparison is
# case-insensitive — this script matches that comparison so it does not add a case-variant
# duplicate of an address that is already allowed.
#
# ── What it does ──────────────────────────────────────────────────────────────────────────────
#   1. Validates the entry is a shape auth-allowlist.ts actually recognises: an exact
#      'local@domain.tld' address, or a whole '@domain.tld'.
#   2. SSHes to the VM and appends it to SIGNUP_ALLOWLIST in /opt/azmoth/shared/.env — unless an
#      equivalent entry is already there, in which case running this is a no-op rather than a
#      duplicate. Safe to run twice with the same address.
#   3. Rewrites /opt/azmoth/repo/infra/docker/.env the same way deploy.sh's own step 4 does — by
#      concatenating shared/.env and shared/release.env — because that file, not shared/.env, is
#      what Compose actually reads.
#   4. Restarts just the web service (`docker compose up -d web`, not a full re-deploy) so the new
#      list takes effect. The value is read at request time; nothing is rebuilt or pulled.
#
# ── Host and SSH ──────────────────────────────────────────────────────────────────────────────
# Same connection method as scripts/deploy.sh (same SSH_OPTS, same default user), and the same
# AZURE_HOST / AZURE_USER environment variables the Makefile's azure-* targets already use — so
# if you have AZURE_HOST exported for `make deploy` / `make azure-logs`, this needs nothing else.

set -euo pipefail

EMAIL="${1:-}"
HOST="${2:-${AZURE_HOST:-}}"
SSH_USER="${SSH_USER:-${AZURE_USER:-azmoth}}"
REMOTE_ROOT=/opt/azmoth

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m !! %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31m !! %s\033[0m\n' "$*" >&2; exit 1; }

[ -n "$EMAIL" ] || die "usage: ./scripts/allow-signup.sh <email-or-@domain> [host]

   examples:
     ./scripts/allow-signup.sh dr.b@praxis-nord.de 20.79.12.34
     AZURE_HOST=20.79.12.34 ./scripts/allow-signup.sh dr.b@praxis-nord.de"

# Same shape apps/web/lib/auth-allowlist.ts recognises: a whole '@domain.tld', or one exact
# 'local@domain.tld'. Same quote/'$' refusal as deploy.sh's own --signup-allowlist check — both
# characters would break out of the double-quoted value once it is written into the .env file.
# Checked before the host is even required, so a typo'd address fails fast either way.
case "$EMAIL" in
  *\'*|*\"*|*'$'*) die "may not contain quotes or '\$': $EMAIL" ;;
esac
case "$EMAIL" in
  @*.*)  warn "'$EMAIL' admits EVERY address at that domain." ;;
  *@*.*) : ;;
  *) die "not an address or an @domain: '$EMAIL' (expected 'user@company.de' or '@company.de')" ;;
esac

[ -n "$HOST" ] || die "no host given, and \$AZURE_HOST is unset.

     ./scripts/allow-signup.sh $EMAIL <host>
       or
     AZURE_HOST=<host> ./scripts/allow-signup.sh $EMAIL"

SSH_TARGET="$SSH_USER@$HOST"
SSH_OPTS=(-o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new)

say "Checking the VM is reachable"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" true 2>/dev/null \
  || die "cannot ssh to $SSH_TARGET.
   - is the firewall's SSH rule still pointing at your current IP?
   - is your key loaded?  ssh-add -l
   - is the user right? pass a second argument or set SSH_USER (default: azmoth)"
echo "    ok"

say "Sending the address to $HOST"
# Two ssh calls, not one with a heredoc fed by a pipe: a heredoc on an ssh invocation replaces the
# process's stdin, so anything piped in ahead of it is discarded and the remote command never
# sees it (same reasoning as the two-call GHCR_TOKEN update in scripts/deploy.sh). So: one call
# whose stdin carries the address, then one call whose stdin is the logic.
CANDIDATE="$REMOTE_ROOT/shared/.allow-signup.candidate"
printf '%s' "$EMAIL" | ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
  "umask 077 && cat > '$CANDIDATE'" \
  || die "could not send the address to $SSH_TARGET"

say "Updating SIGNUP_ALLOWLIST and restarting web"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "REMOTE_ROOT='$REMOTE_ROOT' bash -s" <<'REMOTE'
set -euo pipefail

ENV_FILE="$REMOTE_ROOT/shared/.env"
RELEASE_ENV="$REMOTE_ROOT/shared/release.env"
COMPOSE_ENV="$REMOTE_ROOT/repo/infra/docker/.env"
CANDIDATE="$REMOTE_ROOT/shared/.allow-signup.candidate"

# The candidate holds the address handed to this run. Remove it on every exit path, including a
# failure — nothing here is secret, but there is no reason to leave a stray file behind either.
trap 'rm -f "$CANDIDATE"' EXIT

[ -s "$CANDIDATE" ] || { echo "!! the address did not arrive" >&2; exit 1; }
NEW_ENTRY="$(cat "$CANDIDATE")"

[ -f "$ENV_FILE" ] || {
  echo "!! $ENV_FILE does not exist — has this box ever been deployed with scripts/deploy.sh?" >&2
  exit 1
}

# Strip exactly one layer of surrounding double quotes — the same quoting deploy.sh writes it with.
CURRENT="$(grep '^SIGNUP_ALLOWLIST=' "$ENV_FILE" | tail -1 | cut -d= -f2- || true)"
CURRENT="${CURRENT%\"}"; CURRENT="${CURRENT#\"}"

# Comparison mirrors apps/web/lib/auth-allowlist.ts: case-insensitive, so this does not add a
# case-variant duplicate of an address (or domain) that is already on the list.
NEW_ENTRY_LC="$(printf '%s' "$NEW_ENTRY" | tr '[:upper:]' '[:lower:]')"
already_present=false
for entry in $(printf '%s' "$CURRENT" | tr ',' ' '); do
  entry_lc="$(printf '%s' "$entry" | tr '[:upper:]' '[:lower:]')"
  if [ "$entry_lc" = "$NEW_ENTRY_LC" ]; then
    already_present=true
    break
  fi
done

if [ "$already_present" = true ]; then
  echo "    '$NEW_ENTRY' is already on the allowlist — nothing to change"
else
  if [ -z "$CURRENT" ]; then
    UPDATED="$NEW_ENTRY"
  else
    UPDATED="$CURRENT,$NEW_ENTRY"
  fi
  umask 077
  tmp="$(mktemp "$(dirname "$ENV_FILE")/.env.XXXXXX")"
  grep -v '^SIGNUP_ALLOWLIST=' "$ENV_FILE" > "$tmp" || true
  printf 'SIGNUP_ALLOWLIST="%s"\n' "$UPDATED" >> "$tmp"
  mv "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "    added '$NEW_ENTRY' to SIGNUP_ALLOWLIST"
fi

[ -f "$RELEASE_ENV" ] || {
  echo "!! $RELEASE_ENV is missing — no prior scripts/deploy.sh release to fold in" >&2
  exit 1
}
[ -d "$(dirname "$COMPOSE_ENV")" ] || {
  echo "!! $(dirname "$COMPOSE_ENV") is missing — has scripts/deploy.sh run at least once?" >&2
  exit 1
}

# Compose reads .env from the directory holding its compose file, which is this concatenation —
# not shared/.env by itself. Same construction as scripts/deploy.sh step 4.
umask 077
cat "$ENV_FILE" "$RELEASE_ENV" > "$COMPOSE_ENV"
chmod 600 "$COMPOSE_ENV"
echo "    rewrote $COMPOSE_ENV"

cd "$REMOTE_ROOT/repo"
export COMPOSE_PROJECT_NAME=azmoth
sudo -E docker compose \
  -f infra/docker/docker-compose.yml \
  -f infra/docker/docker-compose.azure.yml \
  up -d web
echo "    web service restarted"

echo
echo "    current SIGNUP_ALLOWLIST:"
grep '^SIGNUP_ALLOWLIST=' "$ENV_FILE" | tail -1 | sed 's/^/      /'
REMOTE

say "Done"
