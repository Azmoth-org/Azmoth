#!/usr/bin/env bash
#
# Deploy Azmoth to the Azure VM, from your laptop, in one command.
#
#     ./scripts/deploy.sh 20.79.x.x
#     ./scripts/deploy.sh azmoth-vm.example.com --domain azmoth.com
#
# Provision first with infra/azure/provision.sh, and point DNS at the address it prints BEFORE
# running this — Caddy gets certificates over HTTP-01, which only works once the names resolve.
#
# ── What it does ──────────────────────────────────────────────────────────────────────────────
#   1. Checks the VM is reachable and installs Docker + the Compose plugin if they are missing.
#   2. Ships the source as a `git archive` of your current HEAD.
#   3. Creates infra/docker/.env with generated secrets — ONCE. See the warning below.
#   4. Builds the images one service at a time and starts the stack behind Caddy.
#   5. Waits for every container to report healthy and prints what to check.
#
# Re-running it is the normal way to deploy a change. It is safe: it rebuilds and restarts, and it
# does not touch the database volume or the secrets.
#
# ── Why the source is shipped rather than cloned ──────────────────────────────────────────────
# `git archive HEAD` sends exactly the commit you have checked out, and needs no credential on the
# server. A `git clone` of a private repository means a deploy key or a token living on a box with
# a public IP, to buy a `git pull` this script does not need. It also cannot leak an ignored file:
# `git archive` carries tracked files only, so a local `.env`, `backups/*.dump` and `node_modules`
# are excluded by construction rather than by an rsync filter somebody has to maintain.
#
# The cost is that the VM has no git history. `azmoth-release` on the server records the commit, so
# `ssh <host> cat /opt/azmoth/RELEASE` still answers "what is running".
#
# ── The secrets are generated once and then never again ───────────────────────────────────────
# This is the part a deploy script most often gets wrong, so it is worth being explicit.
#
# `BETTER_AUTH_SECRET` signs every session cookie. Regenerating it on each deploy signs sessions the
# next container cannot verify, and every user is silently logged out on every deploy.
#
# `POSTGRES_PASSWORD` is worse. The postgres image sets the password only when it initialises an
# EMPTY data directory. On the second deploy the volume already exists, initdb is skipped, and a new
# password in .env is simply never applied — so the engine connects with a password the database
# does not have, and the stack comes up with `password authentication failed` for a value that looks
# correct in the file. Rotating it is a deliberate `ALTER ROLE`, not a side effect of deploying.
#
# So: .env is created if absent and LEFT ALONE if present. It lives outside the release directory,
# at /opt/azmoth/shared/.env, so shipping a new source tree cannot overwrite it.
#
# ── The one exception: SIGNUP_ALLOWLIST is backfilled ─────────────────────────────────────────
# "Created once, then never touched" has a failure mode of its own: a variable added to the
# repository after the first deploy never reaches a box that has already been deployed to, and the
# symptom is that a security control which reads as wired up in git is absent in production.
#
# SIGNUP_ALLOWLIST is not a secret and regenerating it costs nothing, so it is APPENDED to an
# existing .env when the key is missing entirely. An existing key — whatever its value, including
# empty — is left exactly as it is: the operator may have edited it on the box to add a pilot user,
# and a deploy that silently reset the guest list would be worse than one that adds nothing.

set -euo pipefail

# ── Arguments ─────────────────────────────────────────────────────────────────────────────────

HOST=""
SSH_USER="${SSH_USER:-azmoth}"
DOMAIN="${DOMAIN:-azmoth.com}"
ACME_EMAIL="${ACME_EMAIL:-}"
SKIP_BUILD=false

# Who may create an account on the deployed box. Inherited from the environment so that CI or a
# personal shell profile can carry the pilot list rather than it living in a flag somebody has to
# remember; `--signup-allowlist` overrides it. Empty here means "derive a default and shout about
# it" — see the resolution below, after DOMAIN is known.
SIGNUP_ALLOWLIST="${SIGNUP_ALLOWLIST:-}"

usage() {
  cat <<USAGE
usage: ./scripts/deploy.sh <host> [options]

  <host>                 IP address or hostname of the Azure VM

  --user <name>          SSH user                      (default: $SSH_USER)
  --domain <domain>      apex domain                   (default: $DOMAIN)
                         app.<domain>, api.<domain> and www.<domain> are derived from it
  --acme-email <addr>    where Let's Encrypt sends renewal failures
                         (default: ops@<domain>)
  --signup-allowlist <list>
                         WHO MAY CREATE AN ACCOUNT. Comma-separated addresses; an entry
                         starting with '@' is a whole domain. This is the only thing
                         between /signup and the open internet.
                         (default: \$SIGNUP_ALLOWLIST, else admin@<domain>)
  --skip-build           restart with the images already on the box, do not rebuild
  -h, --help             this

examples:
  ./scripts/deploy.sh 20.79.12.34
  ./scripts/deploy.sh 20.79.12.34 --domain azmoth.com --acme-email ops@azmoth.com
  ./scripts/deploy.sh 20.79.12.34 --signup-allowlist "dr.b@praxis-nord.de,ops@azmoth.com"
  ./scripts/deploy.sh 20.79.12.34 --skip-build
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --user)       SSH_USER="$2"; shift 2 ;;
    --domain)     DOMAIN="$2"; shift 2 ;;
    --acme-email) ACME_EMAIL="$2"; shift 2 ;;
    --signup-allowlist) SIGNUP_ALLOWLIST="$2"; shift 2 ;;
    --skip-build) SKIP_BUILD=true; shift ;;
    -h|--help)    usage; exit 0 ;;
    -*)           echo "!! unknown option: $1" >&2; usage >&2; exit 2 ;;
    *)            [ -z "$HOST" ] || { echo "!! more than one host given" >&2; exit 2; }
                  HOST="$1"; shift ;;
  esac
done

[ -n "$HOST" ] || { echo "!! no host given" >&2; usage >&2; exit 2; }

APP_HOST="app.$DOMAIN"
API_HOST="api.$DOMAIN"
ACME_EMAIL="${ACME_EMAIL:-ops@$DOMAIN}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

REMOTE_ROOT=/opt/azmoth
SSH_TARGET="$SSH_USER@$HOST"
SSH_OPTS=(-o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new)

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m !! %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31m !! %s\033[0m\n' "$*" >&2; exit 1; }

# ── Resolve and check the sign-up allowlist ───────────────────────────────────────────────────
#
# This is the one value in the generated .env that is a security control rather than a setting, so
# it is resolved here — before a single byte is shipped — and checked rather than trusted.
#
# The default is `admin@<domain>`: one address, at the domain being deployed, which whoever runs
# this can actually receive mail at. It is deliberately NOT empty and deliberately NOT a domain
# entry. Empty admits nobody and would present as "the pilot cannot sign up" an hour after DNS
# propagates; `@<domain>` would admit anybody who can get an address at the company domain.
#
# The format check is not pedantry. A typo here does not fail loudly — it produces a deployment
# where the intended user is refused and the message deliberately does not say why (see
# SIGNUP_REFUSED_MESSAGE in apps/web/lib/auth-allowlist.ts, which will not distinguish
# "misconfigured" from "not on the list" to a stranger at a form). That is the correct behaviour
# for the app and a terrible way to find out you wrote a comma where you meant a dot. So it is
# caught here, where the operator is still watching a terminal.
if [ -z "$SIGNUP_ALLOWLIST" ]; then
  SIGNUP_ALLOWLIST="admin@$DOMAIN"
  warn "no --signup-allowlist given; defaulting to '$SIGNUP_ALLOWLIST'."
  warn "That is the ONLY address that will be able to register. Re-run with"
  warn "  --signup-allowlist \"dr.b@praxis-nord.de,admin@$DOMAIN\""
  warn "or edit SIGNUP_ALLOWLIST in /opt/azmoth/shared/.env and restart the web service."
fi

case "$SIGNUP_ALLOWLIST" in
  # A quote or a '$' would be interpolated by Compose or would end the shell quoting that carries
  # this value over ssh. Neither can appear in a legitimate address.
  *\'*|*\"*|*'$'*) die "--signup-allowlist may not contain quotes or '\$': $SIGNUP_ALLOWLIST" ;;
esac

# Split on commas and whitespace, exactly as apps/web/lib/auth-allowlist.ts does, and check each
# entry in the same two shapes it recognises: '@domain.tld' or 'local@domain.tld'.
allowlist_count=0
for entry in $(printf '%s' "$SIGNUP_ALLOWLIST" | tr ',' ' '); do
  case "$entry" in
    @*.*) warn "'$entry' admits EVERY address at that domain. Prefer exact addresses." ;;
    *@*.*) : ;;   # one exact address: a local part, an '@', and a dotted domain after it
    *) die "not an address or an @domain in --signup-allowlist: '$entry'" ;;
  esac
  allowlist_count=$((allowlist_count + 1))
done
[ "$allowlist_count" -gt 0 ] || die "--signup-allowlist parsed to nothing usable"

# ── Local preflight ───────────────────────────────────────────────────────────────────────────

say "Checking the local tree"

git rev-parse --git-dir >/dev/null 2>&1 || die "not a git repository"

COMMIT="$(git rev-parse HEAD)"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if [ -n "$(git status --porcelain)" ]; then
  # A warning rather than a refusal. `git archive HEAD` ships the COMMIT, so uncommitted work is
  # silently left behind — which is a confusing way to discover that your fix did not deploy.
  warn "the working tree has uncommitted changes, and they will NOT be deployed."
  warn "git archive ships HEAD ($(git rev-parse --short HEAD)). Commit first if you meant to."
  git status --short | sed 's/^/      /' >&2
  echo
  read -r -p "Deploy HEAD anyway? [y/N] " reply
  [ "$reply" = "y" ] || [ "$reply" = "Y" ] || die "aborted"
fi

echo "    branch  $BRANCH"
echo "    commit  $(git rev-parse --short HEAD)"

# The deployment's own files have to be COMMITTED, not merely present.
#
# `git archive HEAD` ships tracked files at HEAD, so a Caddyfile that exists in the working tree but
# has never been committed is simply absent on the server — and the failure lands late and
# obscurely: the source is shipped, Docker is installed, the build runs for twenty minutes, and then
# compose reports a missing file. Checking here costs nothing and names the actual problem.
missing=""
for f in \
  infra/docker/docker-compose.yml \
  infra/docker/docker-compose.azure.yml \
  infra/docker/Caddyfile \
  infra/scripts/backup-db.sh \
  infra/scripts/restore-db.sh
do
  git cat-file -e "HEAD:$f" 2>/dev/null || missing="$missing $f"
done

if [ -n "$missing" ]; then
  echo >&2
  for f in $missing; do echo "   missing at HEAD: $f" >&2; done
  die "the files above are not committed, so they would not be deployed.
   git archive ships what is committed, not what is in your working tree.

       git add$missing
       git commit -m 'infra: the Azure deployment'"
fi
echo "    deployment files present at HEAD"

say "Checking the VM is reachable"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" true 2>/dev/null \
  || die "cannot ssh to $SSH_TARGET.
   - is the NSG's SSH rule still pointing at your current IP? Your ISP may have changed it.
     Re-run: MY_IP=\$(curl -s https://api.ipify.org) ./infra/azure/provision.sh
   - is your key loaded?  ssh-add -l"
echo "    ok"

# DNS is checked, not enforced: split-horizon resolvers and a CDN in front are both legitimate
# reasons for these to look wrong from a laptop. Getting it wrong costs a failed ACME issuance and
# a retry backoff, so it is worth saying out loud before the build rather than after it.
say "Checking DNS"
dns_ok=true
for name in "$APP_HOST" "$API_HOST" "$DOMAIN" "www.$DOMAIN"; do
  resolved="$(dig +short "$name" A 2>/dev/null | tail -1)"
  if [ -z "$resolved" ]; then
    printf '    %-24s \033[1;33mdoes not resolve\033[0m\n' "$name"
    dns_ok=false
  else
    printf '    %-24s %s\n' "$name" "$resolved"
  fi
done

if [ "$dns_ok" = false ]; then
  warn "some names do not resolve yet. Caddy will fail to get certificates for those and retry"
  warn "with a backoff — the stack still comes up, but over plain HTTP until DNS is fixed."
  read -r -p "Continue anyway? [y/N] " reply
  [ "$reply" = "y" ] || [ "$reply" = "Y" ] || die "aborted"
fi

# ── 1. Bootstrap the VM ───────────────────────────────────────────────────────────────────────
# Idempotent, and it prints what it skipped. Docker comes from Docker's own apt repository rather
# than Ubuntu's `docker.io` package: the latter is older and, more to the point, does not carry the
# `docker-compose-plugin` this deployment needs at v2.24 or newer.

say "1/5 Bootstrapping the VM (Docker, Compose, firewall)"

ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "REMOTE_ROOT='$REMOTE_ROOT' bash -s" <<'BOOTSTRAP'
set -euo pipefail

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "    docker $(docker --version | awk '{print $3}' | tr -d ,) and compose already installed"
else
  echo "    installing Docker from Docker's apt repository..."
  export DEBIAN_FRONTEND=noninteractive

  # `apt-get update` can race cloud-init's own unattended-upgrade on a freshly created VM, which
  # presents as "Could not get lock /var/lib/dpkg/lock-frontend". Wait it out rather than fail.
  for i in $(seq 1 30); do
    if sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; then
      echo "    waiting for another apt process to finish ($i/30)..."
      sleep 10
    else
      break
    fi
  done

  sudo apt-get update -qq
  sudo apt-get install -y -qq ca-certificates curl gnupg jq

  sudo install -m 0755 -d /etc/apt/keyrings
  if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
  fi

  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

  sudo apt-get update -qq
  sudo apt-get install -y -qq \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  sudo systemctl enable --now docker
  echo "    installed $(docker --version)"
fi

# `!reset` in docker-compose.azure.yml is what unpublishes the engine's port 8000. It is a Compose
# merge tag added in v2.24; on an older Compose the tag is not understood and `ports` would MERGE
# instead — quietly republishing 8000 on a public box. Refuse rather than deploy that.
COMPOSE_VER="$(docker compose version --short 2>/dev/null | sed 's/^v//')"
COMPOSE_MAJOR="${COMPOSE_VER%%.*}"
COMPOSE_MINOR="$(echo "$COMPOSE_VER" | cut -d. -f2)"
if [ "${COMPOSE_MAJOR:-0}" -lt 2 ] || { [ "$COMPOSE_MAJOR" -eq 2 ] && [ "${COMPOSE_MINOR:-0}" -lt 24 ]; }; then
  echo "!! docker compose $COMPOSE_VER is too old — v2.24+ is required for the '!reset' merge tag" >&2
  echo "   Without it the engine's port 8000 would stay published on a public IP." >&2
  exit 1
fi
echo "    docker compose $COMPOSE_VER (>= 2.24, '!reset' supported)"

# The user runs docker without sudo from an interactive session AFTER this. This script keeps using
# sudo throughout, because group membership does not apply to the session that granted it.
if ! id -nG "$USER" | tr ' ' '\n' | grep -qx docker; then
  sudo usermod -aG docker "$USER"
  echo "    added $USER to the docker group (effective at your next login)"
fi

# ufw as a third layer, behind the NSG and behind not publishing the ports at all.
#
# Note what it does NOT do: Docker's published ports bypass ufw entirely by writing their own
# DOCKER-USER chain rules, so ufw would not have closed 8000 if compose still published it. That is
# what docker-compose.azure.yml is for. This is here for anything installed on the host later.
if command -v ufw >/dev/null 2>&1; then
  sudo ufw allow 22/tcp   >/dev/null 2>&1 || true
  sudo ufw allow 80/tcp   >/dev/null 2>&1 || true
  sudo ufw allow 443/tcp  >/dev/null 2>&1 || true
  sudo ufw --force enable >/dev/null 2>&1 || true
  echo "    ufw: 22, 80, 443 allowed; default deny incoming"
fi

# Unattended security updates. A box with a public IP and a pilot's worth of clinical data should
# not be waiting on someone to remember to run apt upgrade.
if ! dpkg -s unattended-upgrades >/dev/null 2>&1; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq unattended-upgrades
  sudo dpkg-reconfigure -f noninteractive unattended-upgrades
  echo "    unattended security upgrades enabled"
fi

sudo mkdir -p "$REMOTE_ROOT/shared" "$REMOTE_ROOT/repo" "$REMOTE_ROOT/backups"
sudo chown -R "$USER:$USER" "$REMOTE_ROOT"
BOOTSTRAP

# ── 2. Ship the source ────────────────────────────────────────────────────────────────────────

say "2/5 Shipping the source (commit $(git rev-parse --short HEAD))"

# The release directory is replaced wholesale rather than extracted over: a file deleted in this
# commit must disappear from the server, and `tar -x` over an existing tree would leave it there.
# `.env` is not in the archive and does not live here, so nothing of value is in the directory
# being replaced.
git archive --format=tar HEAD \
  | ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "
      set -euo pipefail
      rm -rf '$REMOTE_ROOT/repo.new'
      mkdir -p '$REMOTE_ROOT/repo.new'
      tar -x -C '$REMOTE_ROOT/repo.new'
      rm -rf '$REMOTE_ROOT/repo.old'
      # An 'if', not '[ -d x ] && mv': under 'set -e' a false test as the whole of an AND-list
      # exits the script, so the first deploy — when there is no previous release to move aside —
      # would abort here with no error message.
      if [ -d '$REMOTE_ROOT/repo' ]; then
        mv '$REMOTE_ROOT/repo' '$REMOTE_ROOT/repo.old'
      fi
      mv '$REMOTE_ROOT/repo.new' '$REMOTE_ROOT/repo'
      rm -rf '$REMOTE_ROOT/repo.old'
      echo '$COMMIT' > '$REMOTE_ROOT/RELEASE'
      echo \"    \$(find '$REMOTE_ROOT/repo' -type f | wc -l) files\"
    "

# ── 3. Secrets ────────────────────────────────────────────────────────────────────────────────

say "3/5 Environment and secrets"

ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "
      REMOTE_ROOT='$REMOTE_ROOT' \
      DOMAIN='$DOMAIN' APP_HOST='$APP_HOST' API_HOST='$API_HOST' ACME_EMAIL='$ACME_EMAIL' \
      SIGNUP_ALLOWLIST='$SIGNUP_ALLOWLIST' \
      bash -s" <<'ENVSETUP'
set -euo pipefail

ENV_FILE="$REMOTE_ROOT/shared/.env"

if [ -f "$ENV_FILE" ]; then
  echo "    $ENV_FILE exists — keeping it, and keeping the secrets in it"
  echo "    (regenerating BETTER_AUTH_SECRET logs everyone out; regenerating POSTGRES_PASSWORD"
  echo "     is never applied to an existing volume and only breaks the connection — see the"
  echo "     header of scripts/deploy.sh)"

  # The one backfill. A box deployed before the allowlist existed has no SIGNUP_ALLOWLIST line at
  # all, and Compose would hand the web container "" — which admits nobody, so the pilot would find
  # they cannot register. Add the key if and only if it is ABSENT. `grep -q '^SIGNUP_ALLOWLIST='`
  # is anchored so a commented-out line does not count as present, and an existing key is never
  # rewritten: the operator may have edited the guest list on the box, and a deploy that reset it
  # would be a regression dressed as a fix.
  if grep -q '^SIGNUP_ALLOWLIST=' "$ENV_FILE"; then
    echo "    SIGNUP_ALLOWLIST already set in $ENV_FILE — left untouched"
    echo "    (edit it there and 'docker compose ... up -d web' to change who may register)"
  else
    printf '\n# -- who may create an account (added by deploy.sh) --------------------------------------\n' >> "$ENV_FILE"
    printf '# Comma-separated. An entry starting with @ admits a whole domain. EMPTY ADMITS NOBODY.\n' >> "$ENV_FILE"
    printf '# See apps/web/lib/auth-allowlist.ts.\n' >> "$ENV_FILE"
    printf 'SIGNUP_ALLOWLIST="%s"\n' "$SIGNUP_ALLOWLIST" >> "$ENV_FILE"
    echo "    SIGNUP_ALLOWLIST was MISSING and has been appended: $SIGNUP_ALLOWLIST"
  fi
else
  echo "    generating $ENV_FILE"

  # Hex, not base64, for the database password. It is substituted into a URL —
  # postgresql+asyncpg://azmoth:PASSWORD@postgres:5432/azmoth — where '/', '+', '@' and '=' all
  # mean something. 32 hex characters is 128 bits and needs no URL-encoding anywhere.
  POSTGRES_PASSWORD="$(openssl rand -hex 32)"

  # base64 is correct here: this one is read as an opaque string, never parsed as a URL. Compose
  # interpolates ${...} in a .env value, and base64's alphabet contains no '$', so it is safe
  # unquoted.
  BETTER_AUTH_SECRET="$(openssl rand -base64 32)"

  umask 077   # the file must not be world-readable before a single byte is written to it
  cat > "$ENV_FILE" <<ENVFILE
# Generated by scripts/deploy.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ).
#
# ** DO NOT REGENERATE THE TWO SECRETS BELOW. **
# BETTER_AUTH_SECRET signs session cookies: a new value logs every user out.
# POSTGRES_PASSWORD is applied by the postgres image only when it initialises an EMPTY data
# directory, so a new value here is never applied to the existing volume — it just stops the
# engine connecting. Rotating it is an ALTER ROLE plus an edit here, in that order.
#
# Back this file up somewhere other than this VM. Losing it does not lose the database, but it
# does mean working out the password from a running container before you can ever restart it.

# -- hostnames Caddy serves ------------------------------------------------------------------
APP_DOMAIN_HOST=$APP_HOST
API_DOMAIN_HOST=$API_HOST
MARKETING_DOMAIN_HOST=$DOMAIN
ACME_EMAIL=$ACME_EMAIL

# -- public URLs baked into the marketing build ----------------------------------------------
# BUILD arguments, not runtime variables: every marketing page is statically prerendered, so
# changing either of these needs a rebuild of that service, not a restart.
APP_URL=https://$APP_HOST
MARKETING_SITE_URL=https://www.$DOMAIN

# -- database --------------------------------------------------------------------------------
POSTGRES_USER=azmoth
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=azmoth

# -- authentication --------------------------------------------------------------------------
BETTER_AUTH_SECRET=$BETTER_AUTH_SECRET

# ** WHO MAY CREATE AN ACCOUNT. **
# There is no invitation flow and no email verification behind this line — it is the whole of the
# admission control on a box with a public IP. Comma-separated; an entry starting with '@' admits
# every address at that domain. EMPTY ADMITS NOBODY, which is the intended failure rather than a
# bug: see apps/web/lib/auth-allowlist.ts.
#
# Changing it is an edit here plus:
#     cd $REMOTE_ROOT/repo && docker compose ... up -d web
# The value is read at request time, so no rebuild is needed — only a restart of the web service.
SIGNUP_ALLOWLIST="$SIGNUP_ALLOWLIST"

# Leave EMPTY unless you enable Google sign-in. Better Auth derives the origin per request and
# apps/web/lib/auth.ts already trusts Caddy's x-forwarded-host, so the proxy needs nothing here.
# A value that does not match the browser's origin makes every sign-in answer 403 INVALID_ORIGIN.
# For Google: set it to https://$APP_HOST and register
# https://$APP_HOST/api/auth/callback/google as an Authorised redirect URI.
BETTER_AUTH_URL=

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# -- engine ----------------------------------------------------------------------------------
APP_ENV=production
DEBUG=false
UNVERIFIED_RULE_POLICY=warn
BASE_FACTOR_POLICY=schwellenwert
SOLVER_TIMEOUT_SECONDS=5
CACHE_ENABLED=true

# The pilot setting. A real, slightly non-conforming PVS export is audited anyway and every
# framing violation lands on the report as schema_warnings rather than being refused at the door
# with a 422 the partner cannot act on. Set back to 'strict' when the pilot ends.
# See infra/docker/.env.example for the full reasoning.
PADNEXT_SCHEMA_POLICY=warn
ENVFILE

  chmod 600 "$ENV_FILE"
  echo "    generated, mode 600, owner $USER"
fi

# The compose files read `.env` from their own directory. It is copied rather than symlinked
# because shipping a new release replaces that directory, and a symlink's target being outside it
# is exactly the sort of thing a `rm -rf` of the release directory would follow.
install -m 600 "$ENV_FILE" "$REMOTE_ROOT/repo/infra/docker/.env"
echo "    installed into repo/infra/docker/.env"
ENVSETUP

# ── 4. Build and start ────────────────────────────────────────────────────────────────────────

say "4/5 Building and starting"

ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "
      REMOTE_ROOT='$REMOTE_ROOT' SKIP_BUILD='$SKIP_BUILD' bash -s" <<'DEPLOY'
set -euo pipefail

cd "$REMOTE_ROOT/repo"

# A stable project name, so containers are `azmoth-web-1` rather than named after whatever
# directory the compose file happened to be in. The volumes are unaffected either way — they carry
# explicit `name:` values in the compose file — so this is about legible `docker ps` output.
export COMPOSE_PROJECT_NAME=azmoth
COMPOSE=(sudo -E docker compose \
  -f infra/docker/docker-compose.yml \
  -f infra/docker/docker-compose.azure.yml)

if [ "$SKIP_BUILD" != "true" ]; then
  # ── One service at a time, deliberately ────────────────────────────────────────────────────
  # Compose builds in parallel by default. On a 4 GiB box, two concurrent `next build`s (web and
  # marketing) peak past the machine and the loser is OOM-killed — which surfaces as exit code 137
  # and no error message, and is usually misdiagnosed as a broken Dockerfile.
  #
  # Sequential is slower on the first deploy and roughly free afterwards, because the layers that
  # dominate the time are cached on the manifests alone.
  #
  # `web-auth-migrate` is not built here: it is the `builder` target of the very image `web` just
  # built, so it is already in the cache and compose will not recompile it.
  for svc in engine web marketing; do
    echo
    echo "    ── building $svc ──"
    "${COMPOSE[@]}" build "$svc"
  done
fi

echo
echo "    starting..."
"${COMPOSE[@]}" up -d --remove-orphans

echo
echo "    waiting for containers to report healthy (up to 5 minutes)..."
# Polls the healthchecks the compose files already define rather than sleeping a fixed time. The
# engine migrates and loads a 1 MB catalog on start, so 'up' is a long way from 'serving'.
deadline=$(( $(date +%s) + 300 ))
while :; do
  # `web-auth-migrate` is a one-shot that exits 0; it has no health status and never will.
  unhealthy="$("${COMPOSE[@]}" ps --format json 2>/dev/null \
    | jq -r 'select(.Service != "web-auth-migrate")
             | select(.Health != "healthy" and .Health != "")
             | .Service' | sort -u | tr '\n' ' ')"

  if [ -z "${unhealthy// /}" ]; then
    echo "    all healthy"
    break
  fi

  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo
    echo "!! still not healthy after 5 minutes: $unhealthy" >&2
    echo >&2
    "${COMPOSE[@]}" ps >&2
    echo >&2
    echo "   logs from the services that did not come up:" >&2
    for svc in $unhealthy; do
      echo "   ── $svc ──" >&2
      "${COMPOSE[@]}" logs --tail 40 "$svc" >&2
    done
    exit 1
  fi

  printf '.'
  sleep 5
done

echo
"${COMPOSE[@]}" ps
DEPLOY

# ── 5. Verify ─────────────────────────────────────────────────────────────────────────────────

say "5/5 Verifying"

ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "REMOTE_ROOT='$REMOTE_ROOT' bash -s" <<'VERIFY'
set -euo pipefail
cd "$REMOTE_ROOT/repo"
export COMPOSE_PROJECT_NAME=azmoth
COMPOSE=(sudo -E docker compose \
  -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.azure.yml)

echo "    the engine is on Postgres and migrated:"
"${COMPOSE[@]}" exec -T engine python -c "
from app.config import get_settings
s = get_settings()
print('      backend  :', s.database_backend)
print('      durable  :', s.database_is_durable)
print('      APP_ENV  :', s.app_env)
assert s.database_is_durable, 'NOT Postgres — approvals would not be durable'
" || { echo "!! the engine is not on a durable database" >&2; exit 1; }
"${COMPOSE[@]}" exec -T engine alembic current 2>/dev/null | sed 's/^/      migration: /'

echo
echo "    published ports on this host (only Caddy's 80/443 should appear):"
sudo ss -ltnp 2>/dev/null | grep -E 'docker|caddy' | awk '{print "      " $4}' | sort -u || true
VERIFY

cat <<DONE

────────────────────────────────────────────────────────────────────────────────
  Deployed $(git rev-parse --short HEAD) ($BRANCH) to $HOST

      https://$APP_HOST          the application
      https://www.$DOMAIN        the marketing site
      https://$API_HOST/docs     the partner API contract

  Certificates take a few seconds on first boot. If a name does not resolve
  yet, Caddy retries with a backoff — watch it with:

      ssh $SSH_TARGET 'cd $REMOTE_ROOT/repo && sudo docker compose \\
        -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.azure.yml \\
        logs -f caddy'

  NOW RUN THE PRE-FLIGHT CHECKLIST — it checks the things this script cannot,
  including that port 8000 really is closed from the outside:

      ./scripts/preflight.sh $HOST --domain $DOMAIN
────────────────────────────────────────────────────────────────────────────────

DONE
