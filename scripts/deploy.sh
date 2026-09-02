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
#   2. Ships the source as a `git archive` of your current HEAD — for the compose files and the
#      Caddyfile, not for building.
#   3. Creates /opt/azmoth/shared/.env with generated secrets and the Neon URLs — ONCE.
#   4. Logs in to ghcr.io and PULLS the three images for this commit.
#   5. Runs `alembic upgrade head` against Neon's direct endpoint.
#   6. Starts the stack behind Caddy and waits for every container to report healthy.
#
# Re-running it is the normal way to deploy a change. It is safe: it pulls, migrates and restarts,
# and it does not touch the secrets.
#
# ── Nothing is built on the VM ────────────────────────────────────────────────────────────────
# This is the difference from every earlier version of this script, and it is what makes the VM a
# 2 GiB box costing EUR 15/month instead of a 4 GiB box costing EUR 30.
#
# .github/workflows/release-images.yml builds three images on a GitHub runner and pushes them to
# ghcr.io tagged with the commit sha:
#
#     ghcr.io/<owner>/azmoth-engine:<sha>       the FastAPI engine, with Soufflé and Clingo
#     ghcr.io/<owner>/azmoth-web:<sha>          the Next.js standalone bundle
#     ghcr.io/<owner>/azmoth-web-builder:<sha>  the web image's `builder` stage, for auth:migrate
#
# So the commit you deploy must have been pushed and its workflow must have finished. This script
# checks that the manifests exist before it touches the VM, because the alternative is discovering
# it after Docker is installed and the source is shipped.
#
# The third image looks like waste and is not: `web-auth-migrate` runs Better Auth's own migrator
# with pnpm and TypeScript, neither of which is in the traced runtime bundle. See the note on that
# service in infra/docker/docker-compose.azure.yml.
#
# ── Why the source is still shipped ───────────────────────────────────────────────────────────
# The images carry the application. The VM still needs the two compose files and the Caddyfile, and
# `git archive HEAD` sends exactly the commit you have checked out with no credential on the server.
# A `git clone` of a private repository means a deploy key living on a box with a public IP. It also
# cannot leak an ignored file: `git archive` carries tracked files only, so a local `.env`,
# `backups/*.dump` and `node_modules` are excluded by construction rather than by an rsync filter
# somebody has to maintain.
#
# `/opt/azmoth/RELEASE` records the commit, so `ssh <host> cat /opt/azmoth/RELEASE` answers "what is
# running" — and it is the same string as the image tag, which is what makes a rollback legible.
#
# ── The database is Neon's, and there are TWO connection strings ──────────────────────────────
# No Postgres container, no `postgres-data` volume, no POSTGRES_PASSWORD. Instead:
#
#   DATABASE_URL         the DIRECT (non-pooled) string. Used by `alembic upgrade head`, by Better
#                        Auth's migrator, by the engine at runtime, and by the backup job's pg_dump.
#   DATABASE_URL_POOLED  the POOLED string (host contains `-pooler`). Used ONLY by the web tier's
#                        Better Auth at runtime.
#
# Why the engine is on the direct one rather than the pooler — which is the opposite of what you
# would guess — is the long note on the `engine` service in
# infra/docker/docker-compose.azure.yml. The short version: SQLAlchemy's asyncpg dialect cannot be
# made safe behind a transaction-mode pooler without a Python change to `build_engine`.
#
# ── The secrets are written once and then never again ─────────────────────────────────────────
# This is the part a deploy script most often gets wrong, so it is worth being explicit.
#
# `BETTER_AUTH_SECRET` signs every session cookie. Regenerating it on each deploy signs sessions the
# next container cannot verify, and every user is silently logged out on every deploy.
#
# The Neon URLs are worse in a quieter way. Overwriting them with a different project's strings
# would point a running deployment at an empty database — which comes up perfectly healthy, migrates
# cleanly, and shows a practice none of their own records. So they are written on the first deploy
# and never rewritten. Moving to a different Neon project is a deliberate edit on the box.
#
# So: .env is created if absent and LEFT ALONE if present. It lives outside the release directory,
# at /opt/azmoth/shared/.env, so shipping a new source tree cannot overwrite it.
#
# ── The exceptions: SIGNUP_ALLOWLIST and DATABASE_URL_POOLED are backfilled ───────────────────
# "Created once, then never touched" has a failure mode of its own: a variable added to the
# repository after the first deploy never reaches a box that has already been deployed to, and the
# symptom is that a control which reads as wired up in git is absent in production.
#
# Two keys are therefore APPENDED to an existing .env when they are missing ENTIRELY. An existing
# key — whatever its value, including empty — is left exactly as it is.
#
#   SIGNUP_ALLOWLIST     not a secret, and the operator may have edited the guest list on the box.
#                        A deploy that silently reset it would be a regression dressed as a fix.
#   DATABASE_URL_POOLED  did not exist before Neon. Without it the web tier falls back to the direct
#                        endpoint, which works — so its absence is invisible rather than loud, which
#                        is exactly the kind of thing that stays absent for the life of a pilot.

set -euo pipefail

# ── Arguments ─────────────────────────────────────────────────────────────────────────────────

HOST=""
SSH_USER="${SSH_USER:-azmoth}"
DOMAIN="${DOMAIN:-azmoth.com}"
ACME_EMAIL="${ACME_EMAIL:-}"
SKIP_PULL=false

# Which images, and which tag. The registry namespace is derived from the git remote so that a fork
# deploys its own images rather than the upstream's; `--registry` overrides it.
GHCR_REGISTRY="${GHCR_REGISTRY:-}"
IMAGE_TAG="${IMAGE_TAG:-}"

# A GitHub personal access token with `read:packages` and NOTHING ELSE, for pulling private images.
# Read from the environment rather than a flag so it does not land in a shell history. If it is
# unset and the box has none, the script prompts for it without echoing.
#
# Scope matters: `read:packages` cannot push an image, cannot read the repository source, and cannot
# act on the account. It is the least a `docker pull` can be given. A classic token is used rather
# than a fine-grained one because fine-grained tokens have never covered organisation-owned
# packages reliably.
GHCR_TOKEN="${GHCR_TOKEN:-}"
GHCR_USER="${GHCR_USER:-}"

# The two Neon connection strings. Read from the environment for the same reason as the token: a
# connection string contains a password. On the first deploy they are required; afterwards they are
# already on the box and these stay empty.
DATABASE_URL="${DATABASE_URL:-}"
DATABASE_URL_POOLED="${DATABASE_URL_POOLED:-}"

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
                         app.<domain> and api.<domain> are derived from it.
                         <domain> and www.<domain> are Vercel's and are NOT touched.
  --acme-email <addr>    where Let's Encrypt sends renewal failures
                         (default: ops@<domain>)
  --signup-allowlist <list>
                         WHO MAY CREATE AN ACCOUNT. Comma-separated addresses; an entry
                         starting with '@' is a whole domain. This is the only thing
                         between /signup and the open internet.
                         (default: \$SIGNUP_ALLOWLIST, else admin@<domain>)
  --registry <ns>        GHCR namespace holding the images
                         (default: derived from the 'origin' remote)
  --tag <sha>            image tag to deploy       (default: the current HEAD commit)
                         Pass an older sha to ROLL BACK — see docs/deploy/RUNBOOK.md § 6.
  --skip-pull            restart with the images already on the box, do not pull
  -h, --help             this

environment (never passed as flags, because they are secrets):
  GHCR_TOKEN             a GitHub PAT with read:packages. Prompted for if absent.
  DATABASE_URL           Neon's DIRECT connection string.   Required on the FIRST deploy only.
  DATABASE_URL_POOLED    Neon's POOLED connection string.   Required on the FIRST deploy only.

examples:
  ./scripts/deploy.sh 20.79.12.34
  ./scripts/deploy.sh 20.79.12.34 --signup-allowlist "dr.b@praxis-nord.de,ops@azmoth.com"
  ./scripts/deploy.sh 20.79.12.34 --tag 6a3c14c        # roll back to an earlier image
  ./scripts/deploy.sh 20.79.12.34 --skip-pull
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --user)       SSH_USER="$2"; shift 2 ;;
    --domain)     DOMAIN="$2"; shift 2 ;;
    --acme-email) ACME_EMAIL="$2"; shift 2 ;;
    --signup-allowlist) SIGNUP_ALLOWLIST="$2"; shift 2 ;;
    --registry)   GHCR_REGISTRY="$2"; shift 2 ;;
    --tag)        IMAGE_TAG="$2"; shift 2 ;;
    --skip-pull)  SKIP_PULL=true; shift ;;
    # Kept as an alias so an old invocation does not die on "unknown option". It meant "do not
    # build on the box", and nothing builds on the box any more, so the nearest honest meaning is
    # "do not pull either — just restart".
    --skip-build) SKIP_PULL=true; shift ;;
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

# ── Resolve the images ────────────────────────────────────────────────────────────────────────
#
# The tag is the commit, so `docker compose ps`, /opt/azmoth/RELEASE and the GHCR tag all say the
# same thing. That equivalence is the whole reason a rollback is `--tag <older-sha>`.

if [ -z "$GHCR_REGISTRY" ]; then
  # ── Ask GitHub who owns this repository, not the git remote ─────────────────────────────────
  # The remote URL is the obvious source and it is the wrong one. GitHub keeps redirecting the old
  # URL after a repository is renamed or transferred, so `git remote get-url origin` can go on
  # saying `github.com/old-org/old-name` indefinitely while pushes land somewhere else entirely —
  # which is exactly the state this repository is in.
  #
  # That matters here and nowhere else in this script, because release-images.yml publishes to
  # `ghcr.io/${{ github.repository_owner }}` — the CURRENT owner. Deriving the namespace from a
  # stale remote would have this script look for images under a namespace nothing pushes to, and
  # report "at least one image is not in the registry" for a commit whose workflow went green.
  #
  # `gh` follows the redirect. The remote is the fallback for a machine without it.
  owner="$(gh repo view --json owner --jq .owner.login 2>/dev/null || true)"

  if [ -z "$owner" ]; then
    origin_url="$(git remote get-url origin 2>/dev/null || true)"
    owner="$(printf '%s' "$origin_url" \
      | sed -e 's#^git@[^:]*:##' -e 's#^https\?://[^/]*/##' -e 's#\.git$##' \
      | cut -d/ -f1)"
    [ -n "$owner" ] && warn "using the git remote's owner ('$owner') — gh is unavailable, so a
   renamed or transferred repository would give the wrong registry namespace. If the manifest
   check below says the images are missing for a commit whose workflow went green, that is why:
   pass --registry ghcr.io/<current-owner>."
  fi

  # Lowercased because GHCR namespaces are lowercase-only while a GitHub org name may be
  # capitalised — `Azmoth-org` publishes to `ghcr.io/azmoth-org`. release-images.yml applies the
  # same lowercasing, and the two must agree.
  owner="$(printf '%s' "$owner" | tr '[:upper:]' '[:lower:]')"

  [ -n "$owner" ] || die "could not work out which GitHub account owns this repository.
   Pass the namespace explicitly:  --registry ghcr.io/your-org"
  GHCR_REGISTRY="ghcr.io/$owner"
fi

IMAGE_TAG="${IMAGE_TAG:-$COMMIT}"
ENGINE_IMAGE="$GHCR_REGISTRY/azmoth-engine"
WEB_IMAGE="$GHCR_REGISTRY/azmoth-web"
WEB_BUILDER_IMAGE="$GHCR_REGISTRY/azmoth-web-builder"

echo "    registry $GHCR_REGISTRY"
echo "    tag      $IMAGE_TAG"

if [ "$IMAGE_TAG" != "$COMMIT" ]; then
  warn "deploying tag $IMAGE_TAG, which is NOT your HEAD ($(git rev-parse --short HEAD))."
  warn "The source shipped to the box comes from HEAD, so the compose files and Caddyfile will be"
  warn "HEAD's while the application images are $IMAGE_TAG's. That is correct for a rollback of the"
  warn "application; it is wrong if the infra files also changed. Check out the older commit if so."
fi

# The deployment's own files have to be COMMITTED, not merely present.
#
# `git archive HEAD` ships tracked files at HEAD, so a Caddyfile that exists in the working tree but
# has never been committed is simply absent on the server — and the failure lands late and
# obscurely: the source is shipped, Docker is installed, the build runs for twenty minutes, and then
# compose reports a missing file. Checking here costs nothing and names the actual problem.
#
# The list is what the DEPLOYMENT needs, which is now a shorter list than it was: backup-db.sh and
# restore-db.sh drive `docker compose exec postgres` and are local-stack tools, so they are no
# longer required at HEAD for a deploy to work. backup-to-azure.sh replaces them on the VM.
missing=""
for f in \
  infra/docker/docker-compose.yml \
  infra/docker/docker-compose.azure.yml \
  infra/docker/Caddyfile \
  infra/scripts/backup-to-azure.sh
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
# a retry backoff, so it is worth saying out loud before the deploy rather than after it.
#
# TWO names. `azmoth.com` and `www.azmoth.com` are Vercel's, and the check on them below is the
# OPPOSITE of the one on these two: they must NOT point here.
say "Checking DNS"
dns_ok=true
for name in "$APP_HOST" "$API_HOST"; do
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

# ── The marketing site must NOT be pointed here ───────────────────────────────────────────────
# A refusal rather than a warning, and the only DNS condition in this script that is fatal.
#
# If the apex or www resolves to this VM, the public site is already down: there is no `marketing`
# container in this deployment and the Caddyfile has no site block for those names, so Caddy answers
# them with its default site. Continuing would also have Caddy request a Let's Encrypt certificate
# for a name Vercel already holds one for, burning one of five weekly duplicates.
say "Checking the marketing site is still Vercel's"
for name in "$DOMAIN" "www.$DOMAIN"; do
  resolved="$(dig +short "$name" A 2>/dev/null | tail -1)"
  if [ "$resolved" = "$HOST" ]; then
    die "$name resolves to THIS VM ($HOST), and it must not.
   azmoth.com and www.azmoth.com are served by Vercel. This box has no marketing container.
   Move those A records back to Vercel before deploying — the public site is down right now.
   Do NOT 'fix' this by adding a site block to infra/docker/Caddyfile; see that file's header."
  fi
  printf '    %-24s %s\n' "$name" "${resolved:-no A record (a CNAME to Vercel is normal)}"
done

# ── The registry credential ───────────────────────────────────────────────────────────────────
# Needed on the box to pull private images, and needed here to check the manifests exist.
#
# Prompted for rather than defaulted, and read with `-s` so it is not echoed and does not land in
# the terminal's scrollback. It is stored in /opt/azmoth/shared/.env (mode 600) because
# `docker pull` on an unattended restart has to work without a human.
#
# Skipped entirely on a re-deploy where the box already has one — the same "written once" doctrine
# as the other secrets.

if [ -z "$GHCR_USER" ]; then
  # `gh` knows who you are; fall back to the registry namespace, which is right for a personal
  # account and wrong-but-harmless for an org (any org member's login authenticates).
  GHCR_USER="$(gh api user --jq .login 2>/dev/null || true)"
  GHCR_USER="${GHCR_USER:-${GHCR_REGISTRY#ghcr.io/}}"
fi

# Does the box already hold a token? Asked before prompting, so a routine re-deploy is silent.
box_has_token=false
if ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "grep -q '^GHCR_TOKEN=..*' '$REMOTE_ROOT/shared/.env' 2>/dev/null"; then
  box_has_token=true
fi

if [ -z "$GHCR_TOKEN" ] && [ "$box_has_token" = false ]; then
  say "GitHub registry token"
  cat >&2 <<'TOKENHELP'
    The VM needs a token to pull the private images. Create a CLASSIC personal access
    token with the single scope `read:packages` and nothing else:

        https://github.com/settings/tokens/new?scopes=read:packages&description=azmoth-vm-pull

    read:packages cannot push an image, cannot read the repository source, and cannot
    act on the account. It is the least a `docker pull` can be given.

TOKENHELP
  read -r -s -p "    Paste it (not echoed): " GHCR_TOKEN
  echo
  [ -n "$GHCR_TOKEN" ] || die "no token given, and the box has none — the pull would fail"
fi

# ── Do the images for this tag actually exist? ────────────────────────────────────────────────
# Asked HERE, from the laptop, over the registry API, because the alternative is finding out after
# Docker has been installed and the source shipped. The usual cause is a commit that was not pushed,
# or one whose release-images workflow has not finished yet.
#
# Read-only and stateless: it fetches a scoped pull token and HEADs the manifest, rather than
# `docker login`, which would rewrite the operator's ~/.docker/config.json as a side effect of a
# check.
if [ -n "$GHCR_TOKEN" ] && command -v jq >/dev/null 2>&1; then
  say "Checking the images exist in $GHCR_REGISTRY"
  ghcr_repo_path() { printf '%s' "${1#ghcr.io/}"; }

  manifest_exists() {
    local repo bearer
    repo="$(ghcr_repo_path "$1")"
    bearer="$(curl -fsS -u "$GHCR_USER:$GHCR_TOKEN" \
      "https://ghcr.io/token?service=ghcr.io&scope=repository:$repo:pull" 2>/dev/null \
      | jq -r '.token // empty')"
    [ -n "$bearer" ] || return 2
    curl -fsS -o /dev/null -H "Authorization: Bearer $bearer" \
      -H 'Accept: application/vnd.oci.image.index.v1+json' \
      -H 'Accept: application/vnd.oci.image.manifest.v1+json' \
      -H 'Accept: application/vnd.docker.distribution.manifest.list.v2+json' \
      -H 'Accept: application/vnd.docker.distribution.manifest.v2+json' \
      "https://ghcr.io/v2/$repo/manifests/$2" 2>/dev/null
  }

  images_ok=true
  for img in "$ENGINE_IMAGE" "$WEB_IMAGE" "$WEB_BUILDER_IMAGE"; do
    if manifest_exists "$img" "$IMAGE_TAG"; then
      printf '    %-52s \033[1;32mpresent\033[0m\n' "$(basename "$img"):${IMAGE_TAG:0:12}"
    else
      rc=$?
      if [ "$rc" = 2 ]; then
        warn "could not authenticate to ghcr.io as '$GHCR_USER' — skipping the manifest check."
        warn "Confirm the token has read:packages. The pull on the VM will tell you for certain."
        images_ok=true
        break
      fi
      printf '    %-52s \033[1;31mMISSING\033[0m\n' "$(basename "$img"):${IMAGE_TAG:0:12}"
      images_ok=false
    fi
  done

  if [ "$images_ok" = false ]; then
    die "at least one image is not in the registry at tag $IMAGE_TAG.

   The images are built by .github/workflows/release-images.yml on push. Either this commit
   was never pushed, or its workflow has not finished (or failed).

       git push origin $BRANCH
       gh run list --workflow=release-images.yml --limit 5
       gh run watch

   Then re-run this. To deploy an OLDER image that does exist:  --tag <sha>"
  fi
elif ! command -v jq >/dev/null 2>&1; then
  warn "jq is not installed locally, so the registry manifest check is skipped."
  warn "A missing image will surface as a failed 'docker compose pull' on the VM instead."
else
  warn "no token in this shell (the box has one), so the registry manifest check is skipped."
  warn "A missing image will surface as a failed 'docker compose pull' on the VM instead."
fi

# ── 1. Bootstrap the VM ───────────────────────────────────────────────────────────────────────
# Idempotent, and it prints what it skipped. Docker comes from Docker's own apt repository rather
# than Ubuntu's `docker.io` package: the latter is older and, more to the point, does not carry the
# `docker-compose-plugin` this deployment needs at v2.24 or newer.

say "1/5 Bootstrapping the VM (Docker, Compose, firewall)"

ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "REMOTE_ROOT='$REMOTE_ROOT' bash -s" <<'BOOTSTRAP'
set -euo pipefail

# jq, unconditionally and first. The deploy step below parses `docker compose config --format json`
# and `ps --format json` with it, and it used to be installed only inside the "Docker is missing"
# branch — so a box that already had Docker could reach a jq-dependent assertion without jq. The
# symptom was an empty published-ports check that silently passed.
if ! command -v jq >/dev/null 2>&1; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq jq
  echo "    installed jq"
fi

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

# `age` and the Azure CLI, for infra/scripts/backup-to-azure.sh. Installed here rather than left as
# a manual step in the runbook, because the backup job is the thing most likely to be set up "later"
# and a missing binary is one more reason for later never to arrive. Both are no-ops on a re-deploy.
#
# Note what is NOT installed: postgresql-client. The backup job runs pg_dump in a pinned
# `postgres:17-alpine` container instead, because pg_dump must be at least as new as Neon's server
# and Ubuntu 22.04 ships 14 — adding the PGDG apt repository to buy that is a lot of moving parts
# for one command. See infra/scripts/backup-to-azure.sh.
if ! command -v age >/dev/null 2>&1; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq age \
    && echo "    installed age (encrypts backups to a public key)" \
    || echo "    !! could not install age — backups will refuse to run until it is present"
fi

if ! command -v az >/dev/null 2>&1; then
  echo "    installing the Azure CLI (for the backup job's managed-identity login)..."
  curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash >/dev/null 2>&1 \
    && echo "    installed $(az version --query '\"azure-cli\"' -o tsv 2>/dev/null || echo 'azure-cli')" \
    || echo "    !! could not install the Azure CLI — backups will refuse to run until it is present"
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

# Is this the first deploy? The answer decides whether the Neon strings are required.
box_has_env=false
if ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "[ -s '$REMOTE_ROOT/shared/.env' ]" 2>/dev/null; then
  box_has_env=true
fi

# ── Validate the Neon connection strings before anything else ─────────────────────────────────
#
# Checked here, on the laptop, while somebody is still watching a terminal. Getting these the wrong
# way round is the mistake this deployment is most exposed to, and it does not fail loudly: the
# engine on the pooled endpoint works fine until it is under concurrency, at which point it raises
# intermittent DuplicatePreparedStatementError — see the note on the `engine` service in
# infra/docker/docker-compose.azure.yml. Alembic on the pooled endpoint is similarly fine until it
# is not.
#
# Neon marks the pooled endpoint with a `-pooler` infix in the hostname, which is what makes this
# checkable at all.
if [ "$box_has_env" = false ]; then
  if [ -z "$DATABASE_URL" ] || [ -z "$DATABASE_URL_POOLED" ]; then
    die "this is the first deploy to $HOST, so both Neon connection strings are required.

   Create the project in the Neon console — region aws-eu-central-1 (AWS Europe, Frankfurt) —
   then copy BOTH strings from Connect, and re-run:

       DATABASE_URL='postgresql+asyncpg://USER:PW@ep-xxx.eu-central-1.aws.neon.tech/azmoth?sslmode=require' \\
       DATABASE_URL_POOLED='postgresql+asyncpg://USER:PW@ep-xxx-pooler.eu-central-1.aws.neon.tech/azmoth?sslmode=require' \\
         ./scripts/deploy.sh $HOST

   The difference between them is the '-pooler' in the hostname. docs/deploy/RUNBOOK.md § 3
   is the click-by-click version."
  fi
fi

check_neon_url() {
  local label="$1" url="$2" want_pooler="$3"
  [ -n "$url" ] || return 0

  case "$url" in
    postgresql://*|postgres://*|postgresql+asyncpg://*) : ;;
    *) die "$label does not look like a Postgres URL: ${url%%:*}://…
   Expected postgresql:// or postgresql+asyncpg://" ;;
  esac

  # Quotes are rejected because the value is written into the env file wrapped in double quotes —
  # which it has to be, so that the '&' in Neon's query string survives being sourced by a shell.
  # A quote character inside it would close that wrapping early.
  case "$url" in
    *\'*|*\"*) die "$label contains a quote character, which this deployment cannot carry safely.
   The value is stored double-quoted so that the '&' in Neon's query string survives being sourced
   by a shell. Reset the role's password in the Neon console to get one without quotes." ;;
  esac

  # `$` in a value inside a compose .env file is interpolated by Compose, so a password containing
  # one would silently connect with a different password. Caught here rather than discovered as an
  # authentication failure against a database that is definitely up.
  case "$url" in
    *'$'*) die "$label contains a '\$', which Docker Compose would interpolate in the .env file.
   Reset the role's password in the Neon console to get one without it." ;;
  esac

  local host_part
  host_part="${url#*@}"
  host_part="${host_part%%/*}"

  if [ "$want_pooler" = yes ]; then
    case "$host_part" in
      *-pooler.*) : ;;
      *) die "$label should be the POOLED string, but its host has no '-pooler': $host_part
   In the Neon console's Connect dialog, turn 'Connection pooling' ON to get it.
   DATABASE_URL is the direct one; DATABASE_URL_POOLED is the pooled one." ;;
    esac
  else
    case "$host_part" in
      *-pooler.*) die "$label is the POOLED string (host contains '-pooler'): $host_part
   DATABASE_URL must be the DIRECT one — it is what runs 'alembic upgrade head' and what the
   engine's asyncpg pool uses, and neither is safe through a transaction-mode pooler.
   Turn 'Connection pooling' OFF in the Connect dialog to get the direct string." ;;
      *) : ;;
    esac
  fi

  echo "    $label ok — $host_part"
}

check_neon_url DATABASE_URL        "$DATABASE_URL"        no
check_neon_url DATABASE_URL_POOLED "$DATABASE_URL_POOLED" yes

# Both strings should be the same project and database, differing only by the pooler infix. Not
# fatal — a deliberate split across two Neon projects is conceivable — but it is far more likely to
# be a paste from the wrong project, which produces a deployment where sign-in and the audit log
# live in different databases.
if [ -n "$DATABASE_URL" ] && [ -n "$DATABASE_URL_POOLED" ]; then
  if [ "${DATABASE_URL/-pooler/}" != "${DATABASE_URL_POOLED/-pooler/}" ]; then
    warn "the two Neon strings differ by more than the '-pooler' infix."
    warn "If they are different projects, Better Auth's users and the engine's audit log will be in"
    warn "different databases and an audit row's actor will not resolve to a person."
    read -r -p "Continue anyway? [y/N] " reply
    [ "$reply" = "y" ] || [ "$reply" = "Y" ] || die "aborted"
  fi
fi

# ── Build the candidate .env locally, and send it over STDIN ───────────────────────────────────
#
# Over stdin, deliberately, rather than as `ssh host "VAR='$SECRET' bash -s"`. That form puts the
# value in the remote process's command line, where `ps` can read it for as long as the step runs.
# A Neon connection string and a registry token both belong in a file with mode 600 and nowhere
# else, including transiently.
#
# It is a CANDIDATE, not the answer. The remote step below decides what to do with it: install it
# wholesale on a first deploy, or take only the keys that are missing from an existing file.

BETTER_AUTH_SECRET_NEW="$(openssl rand -base64 32)"

candidate="$(cat <<ENVFILE
# Generated by scripts/deploy.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ).
#
# ** DO NOT REGENERATE ANY OF THE SECRETS BELOW. **
#
# BETTER_AUTH_SECRET signs session cookies: a new value logs every user out.
#
# The Neon URLs point at the project holding every proposal, approval and audit event. Replacing
# them with another project's strings gives you a deployment that comes up healthy, migrates
# cleanly, and shows a practice none of their own records. Moving to a different project is a
# deliberate edit here, not a side effect of deploying.
#
# Back this file up somewhere other than this VM. It is now the ONLY copy of the credentials that
# can read the database — losing it makes the encrypted dumps in Blob Storage unrestorable.

# -- hostnames Caddy serves ------------------------------------------------------------------
# TWO. azmoth.com and www.azmoth.com are Vercel's; this box must not serve or request
# certificates for them. See the header of infra/docker/Caddyfile.
APP_DOMAIN_HOST=$APP_HOST
API_DOMAIN_HOST=$API_HOST
ACME_EMAIL=$ACME_EMAIL

# -- the database: Neon, external, aws-eu-central-1 (Frankfurt) ------------------------------
# TWO strings, and they are not interchangeable.
#
# DATABASE_URL is the DIRECT (non-pooled) endpoint. Used by:
#   - 'alembic upgrade head'            (engine-migrate)   Neon: use direct for migrations
#   - Better Auth's table creation      (web-auth-migrate)  same reason — it is DDL
#   - the engine at runtime             (engine)            asyncpg is not pooler-safe
#   - pg_dump                           (backup-to-azure.sh) a dump needs one snapshot
#
# DATABASE_URL_POOLED is the POOLED endpoint — the host with '-pooler' in it. Used by:
#   - Better Auth at runtime            (web)               node-postgres, connection-per-request
#
# Rotate by resetting the role's password in the Neon console, editing BOTH lines here, then
# re-running scripts/deploy.sh. Neon has no ALTER ROLE for you to run.
#
# ** THE QUOTES ARE LOAD-BEARING. DO NOT REMOVE THEM. **
# A Neon connection string ends in a query string — typically
# '?sslmode=require&channel_binding=require' — and an unquoted '&' in a file that gets sourced by a
# shell is a background operator. This file IS sourced by a shell, in three places:
# infra/scripts/backup-to-azure.sh, the registry-login step of scripts/deploy.sh, and the
# 'make azure-psql' target. Unquoted, the '&' is a parse error that abandons the rest of the file —
# so the symptom is not "the database URL is truncated", it is "every variable after this line is
# empty", which presents as the backup job claiming STORAGE_ACCOUNT is unset.
# Docker Compose strips the surrounding quotes, so nothing downstream sees them.
DATABASE_URL="$DATABASE_URL"
DATABASE_URL_POOLED="$DATABASE_URL_POOLED"

# -- pulling the images ----------------------------------------------------------------------
# A GitHub classic PAT with the single scope read:packages. It cannot push an image, read the
# repository source, or act on the account. Rotate it at
# https://github.com/settings/tokens whenever you like — nothing here depends on its value
# surviving, only on it being valid at 'docker compose pull' time.
GHCR_USER="$GHCR_USER"
GHCR_TOKEN="$GHCR_TOKEN"

# -- authentication --------------------------------------------------------------------------
BETTER_AUTH_SECRET=$BETTER_AUTH_SECRET_NEW

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

# -- backups (infra/scripts/backup-to-azure.sh) ----------------------------------------------
# Fill these in after provisioning; the backup job refuses to run without them, deliberately.
#   STORAGE_ACCOUNT   the account infra/azure/provision.sh created
#   AGE_RECIPIENT     the PUBLIC half of a keypair generated on your LAPTOP. The private half
#                     must never be on this VM — that is what makes a compromised host unable to
#                     read back a single backup.  age-keygen -o azmoth-backup.key
# STORAGE_ACCOUNT=
# BACKUP_CONTAINER=db-backups
# AGE_RECIPIENT=
ENVFILE
)"

# TWO ssh calls, and the split is not stylistic. A heredoc on an ssh invocation REPLACES the
# process's stdin, so `printf … | ssh host "bash -s" <<'SCRIPT'` does not deliver the piped data at
# all — the remote `bash -s` reads the heredoc and the pipe is discarded. (shellcheck SC2259 catches
# exactly this; it is how the bug was found rather than shipped.) The remote `cat > candidate` would
# then have written the setup script itself into the file meant to hold the credentials.
#
# So: one call whose stdin is the candidate and whose command is trivial, then one call whose stdin
# is the logic.
printf '%s\n' "$candidate" | ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
  "umask 077 && cat > '$REMOTE_ROOT/shared/.env.candidate' && chmod 600 '$REMOTE_ROOT/shared/.env.candidate'" \
  || die "could not write the candidate env file to $SSH_TARGET"

ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "REMOTE_ROOT='$REMOTE_ROOT' bash -s" <<'ENVSETUP'
set -euo pipefail

ENV_FILE="$REMOTE_ROOT/shared/.env"
CANDIDATE="$REMOTE_ROOT/shared/.env.candidate"

umask 077   # neither file may be world-readable for even an instant

# The candidate holds live credentials. Remove it on every exit path, including a failure — a
# readable copy of the secrets left lying around is worse than the failure that stranded it.
trap 'rm -f "$CANDIDATE"' EXIT

[ -s "$CANDIDATE" ] || { echo "!! the candidate env file did not arrive" >&2; exit 1; }

if [ -f "$ENV_FILE" ]; then
  echo "    $ENV_FILE exists — keeping it, and keeping the secrets in it"
  echo "    (regenerating BETTER_AUTH_SECRET logs everyone out; overwriting the Neon URLs points"
  echo "     the deployment at a different database — see the header of scripts/deploy.sh)"

  # ── Backfill: only keys that are ABSENT, and only with a non-empty value ────────────────────
  #
  # A key added to the repository after the first deploy never reaches a box that has already been
  # deployed to, and the symptom is a control that reads as wired up in git and is missing in
  # production. So a missing key is added.
  #
  # An EXISTING key is never rewritten, whatever its value including empty: the operator may have
  # edited the guest list or rotated a token on the box, and a deploy that silently reset either
  # would be a regression dressed as a fix.
  #
  # The `grep -q '^KEY='` is anchored so a commented-out line does not count as present. The
  # non-empty test on the candidate side matters for a re-deploy, where DATABASE_URL was not passed
  # in this shell and the candidate's value is blank — backfilling that would blank the real one.
  for key in SIGNUP_ALLOWLIST DATABASE_URL DATABASE_URL_POOLED GHCR_USER GHCR_TOKEN; do
    if grep -q "^$key=" "$ENV_FILE"; then
      echo "    $key already set — left untouched"
      continue
    fi
    line="$(grep "^$key=" "$CANDIDATE" || true)"
    value="${line#*=}"
    # Strip one layer of surrounding double quotes for the emptiness test only; the line is
    # appended verbatim so the quoting the candidate chose is preserved.
    probe="${value%\"}"; probe="${probe#\"}"
    if [ -z "$probe" ]; then
      echo "    !! $key is MISSING here and was not supplied — set it by hand in $ENV_FILE"
      continue
    fi
    printf '\n# -- added by deploy.sh on %s --\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$ENV_FILE"
    printf '%s\n' "$line" >> "$ENV_FILE"
    case "$key" in
      GHCR_TOKEN|DATABASE_URL|DATABASE_URL_POOLED)
        echo "    $key was MISSING and has been appended (value not printed)" ;;
      *)
        echo "    $key was MISSING and has been appended: $value" ;;
    esac
  done
else
  echo "    generating $ENV_FILE"
  mv "$CANDIDATE" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "    generated, mode 600, owner $USER"
fi

# Nothing may reach the release directory that is not needed there, so the release-scoped values —
# which change on every deploy and are not secret — live in their own file rather than being
# rewritten into the one holding the credentials.
echo "    release.env is written by the next step"
ENVSETUP

# ── 4. Build and start ────────────────────────────────────────────────────────────────────────

say "4/5 Pulling, migrating and starting"

# The release-scoped values — which image, which tag — change on every deploy and are not secrets,
# so they live in their own file rather than being rewritten into the one holding the credentials.
# `repo/infra/docker/.env` is the concatenation of the two, which is what Compose reads.
#
# Passed on the command line rather than over stdin, unlike the secrets: an image reference in `ps`
# output is not a disclosure.
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "
      REMOTE_ROOT='$REMOTE_ROOT' SKIP_PULL='$SKIP_PULL' \
      ENGINE_IMAGE='$ENGINE_IMAGE' WEB_IMAGE='$WEB_IMAGE' \
      WEB_BUILDER_IMAGE='$WEB_BUILDER_IMAGE' IMAGE_TAG='$IMAGE_TAG' \
      bash -s" <<'DEPLOY'
set -euo pipefail

umask 077
RELEASE_ENV="$REMOTE_ROOT/shared/release.env"
cat > "$RELEASE_ENV" <<RELEASEFILE
# Written by scripts/deploy.sh on every deploy. NOT secret, and NOT preserved between deploys —
# unlike $REMOTE_ROOT/shared/.env, which is. Editing this by hand is pointless; it is overwritten.
#
# The tag is the git commit, which is also what $REMOTE_ROOT/RELEASE holds. That equivalence is
# what makes a rollback legible: ./scripts/deploy.sh <host> --tag \$(older sha).
ENGINE_IMAGE=$ENGINE_IMAGE
WEB_IMAGE=$WEB_IMAGE
WEB_BUILDER_IMAGE=$WEB_BUILDER_IMAGE
IMAGE_TAG=$IMAGE_TAG
RELEASEFILE
chmod 600 "$RELEASE_ENV"

# Compose reads `.env` from the directory holding the compose file. Concatenated rather than
# symlinked because shipping a new release replaces that directory, and a symlink whose target is
# outside it is exactly the sort of thing a `rm -rf` of the release directory would follow.
cat "$REMOTE_ROOT/shared/.env" "$RELEASE_ENV" > "$REMOTE_ROOT/repo/infra/docker/.env"
chmod 600 "$REMOTE_ROOT/repo/infra/docker/.env"
echo "    .env + release.env installed into repo/infra/docker/.env"

cd "$REMOTE_ROOT/repo"

# A stable project name, so containers are `azmoth-web-1` rather than named after whatever
# directory the compose file happened to be in. The volumes are unaffected either way — they carry
# explicit `name:` values in the compose file — so this is about legible `docker ps` output.
export COMPOSE_PROJECT_NAME=azmoth
COMPOSE=(sudo -E docker compose \
  -f infra/docker/docker-compose.yml \
  -f infra/docker/docker-compose.azure.yml)

# ── Assert what this stack resolves to, before starting it ──────────────────────────────────────
# Cheap, and it catches the two mistakes that would otherwise be discovered by a port scan or by a
# practice seeing an empty database:
#
#   * a `postgres` service in the resolved config means the azure override was not applied, which
#     also means the engine's port 8000 is published on a public IP
#   * more than the three expected published ports means the same thing
echo
echo "    resolved services:"
resolved_services="$("${COMPOSE[@]}" config --services 2>/dev/null | sort | tr '\n' ' ')"
echo "      $resolved_services"

for forbidden in postgres marketing adminer; do
  if printf '%s' "$resolved_services" | tr ' ' '\n' | grep -qx "$forbidden"; then
    echo "!! '$forbidden' is in the resolved config and must not be." >&2
    echo "   docker-compose.azure.yml profiles it out; this deploy did not apply the override." >&2
    exit 1
  fi
done

published="$("${COMPOSE[@]}" config --format json 2>/dev/null \
  | jq -r '[.services[].ports // [] | .[] | .published] | sort | unique | join(",")' 2>/dev/null || echo '?')"
echo "    published ports: ${published:-none}"
case "$published" in
  '80,443'|'443,80'|'?') echo "    ok — only Caddy publishes" ;;
  *) echo "!! unexpected published ports: $published — expected only 80 and 443" >&2
     echo "   Something republished a port. Check infra/docker/docker-compose.azure.yml." >&2
     exit 1 ;;
esac

# ── Registry login ─────────────────────────────────────────────────────────────────────────────
# The token is read out of the env file rather than passed in, so it stays in exactly one place on
# this box. `--password-stdin` rather than `-p`, so it is not in the command line or in
# ~/.docker/config.json's shell history equivalent.
#
# The credential is written to root's ~/.docker/config.json by this login, base64-encoded. That is
# a second copy of the token on the box and it is unavoidable if unattended restarts are to pull —
# which is why the scope is read:packages and nothing else.
if [ "$SKIP_PULL" != "true" ]; then
  set -a
  # shellcheck disable=SC1091  # a deployment location, not a file in this repo
  . "$REMOTE_ROOT/shared/.env"
  set +a

  if [ -n "${GHCR_TOKEN:-}" ]; then
    printf '%s' "$GHCR_TOKEN" \
      | sudo docker login ghcr.io --username "${GHCR_USER:-x}" --password-stdin >/dev/null
    echo "    logged in to ghcr.io as ${GHCR_USER:-x}"
  else
    echo "    !! no GHCR_TOKEN in $REMOTE_ROOT/shared/.env — the pull will fail for private images"
  fi

  echo
  echo "    pulling $IMAGE_TAG..."
  # `pull` and not `up --pull always`: a failure here must stop before anything is restarted. The
  # running stack keeps serving the previous tag while this fails, which is the whole point of
  # separating the two steps.
  if ! "${COMPOSE[@]}" pull --quiet; then
    echo >&2
    echo "!! docker compose pull failed." >&2
    echo "   The previous release is still running and still serving — nothing was restarted." >&2
    echo >&2
    echo "   Most likely: the images for $IMAGE_TAG are not in the registry, or the token has" >&2
    echo "   expired. Check:" >&2
    echo "     gh run list --workflow=release-images.yml --limit 5" >&2
    echo "     https://github.com/settings/tokens        (read:packages, not expired)" >&2
    exit 1
  fi
  echo "    pulled"
else
  echo "    --skip-pull: using the images already on the box"
fi

# ── Migrate, as its own step ───────────────────────────────────────────────────────────────────
# `alembic upgrade head` against Neon's DIRECT endpoint, on every deploy, before anything that
# queries the schema is (re)started.
#
# `run --rm` rather than letting `up` order it, so that its output and its exit code land HERE,
# where somebody is watching, rather than in a container log that has to be dug out. A migration
# that fails must stop the deploy — the previous release is still running against the old schema,
# and that is a working system.
#
# Idempotent: on a deploy with no new migrations, alembic finds itself at head and does nothing.
echo
echo "    ── migrating (alembic upgrade head, on the DIRECT endpoint) ──"
if ! "${COMPOSE[@]}" run --rm engine-migrate; then
  echo >&2
  echo "!! the migration failed. NOTHING was restarted — the previous release is still serving." >&2
  echo >&2
  echo "   If this is the first request in a while, Neon's compute was suspended and the resume" >&2
  echo "   timed out; re-running is the fix. If Neon's Free-plan compute allowance is exhausted," >&2
  echo "   new connections are refused until the next billing period — check the Neon console." >&2
  echo >&2
  echo "   Current revision, if it can be read:" >&2
  "${COMPOSE[@]}" run --rm --entrypoint alembic engine-migrate current 2>&1 | sed 's/^/     /' >&2 || true
  exit 1
fi

# Better Auth's own migrator, on the direct endpoint too. Separate from the alembic step because it
# is a different tool with a disjoint table set — see the base compose file's note.
echo
echo "    ── migrating (Better Auth tables) ──"
if ! "${COMPOSE[@]}" run --rm web-auth-migrate; then
  echo >&2
  echo "!! Better Auth's migration failed. The engine's schema IS migrated; the session tables" >&2
  echo "   may not be, which presents as a 500 on the sign-in form." >&2
  exit 1
fi

echo
echo "    starting..."
# `--remove-orphans` matters more than usual on this deploy: a box that was running the previous
# architecture has `postgres` and `marketing` containers that are no longer in the project, and
# leaving a postgres container running would leave a stale copy of clinical data on the disk.
"${COMPOSE[@]}" up -d --remove-orphans

echo
echo "    waiting for containers to report healthy (up to 5 minutes)..."
# Polls the healthchecks the compose files already define rather than sleeping a fixed time. The
# engine loads a 1 MB catalog on start, so 'up' is a long way from 'serving'.
deadline=$(( $(date +%s) + 300 ))
while :; do
  # The one-shots exit 0 and have no health status and never will. They already ran, above, and
  # their failure would have stopped the deploy.
  unhealthy="$("${COMPOSE[@]}" ps --format json 2>/dev/null \
    | jq -r 'select(.Service != "web-auth-migrate" and .Service != "engine-migrate")
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

# Free the disk of images from previous releases. Deliberately `image prune` and not
# `system prune -a`: the latter would take the `caddy-data` volume's parent nothing, but it would
# also remove the previous release's images — which are exactly what a rollback pulls back down.
# `--filter until=168h` keeps a week of them, which is a week of rollback targets.
echo
echo "    pruning images older than a week (a week of rollback targets is kept)"
sudo docker image prune -f --filter "until=168h" 2>/dev/null | tail -1 || true
df -h / | awk 'NR==2 {printf "    disk: %s used of %s (%s)\n", $3, $2, $5}'
DEPLOY

# ── 5. Verify ─────────────────────────────────────────────────────────────────────────────────

say "5/5 Verifying"

ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "REMOTE_ROOT='$REMOTE_ROOT' bash -s" <<'VERIFY'
set -euo pipefail
cd "$REMOTE_ROOT/repo"
export COMPOSE_PROJECT_NAME=azmoth
COMPOSE=(sudo -E docker compose \
  -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.azure.yml)

echo "    the engine reached Neon, on the right endpoint, and the schema is at head:"
# Read out of the RUNNING container rather than out of the .env on disk. Those are two different
# questions: a value edited after the last `up -d` is not in the process's environment, and the
# process's environment is what actually decides which database this deployment uses.
"${COMPOSE[@]}" exec -T engine python -c "
import urllib.parse
from app.config import get_settings
s = get_settings()
host = urllib.parse.urlsplit(s.database_url.replace('+asyncpg', '')).hostname or ''
print('      backend  :', s.database_backend)
print('      durable  :', s.database_is_durable)
print('      APP_ENV  :', s.app_env)
print('      db host  :', host)
assert s.database_is_durable, 'NOT Postgres — approvals would not be durable'
# The endpoint split, asserted rather than assumed. asyncpg behind a transaction-mode pooler fails
# intermittently and under load, so it would not show up here as anything at all.
assert '-pooler.' not in host, (
    'the engine is on Neons POOLED endpoint. DATABASE_URL must be the DIRECT string; '
    'the pooled one belongs in DATABASE_URL_POOLED and is for the web tier only.'
)
" || { echo "!! the engine's database configuration is wrong — see above" >&2; exit 1; }

cur="$("${COMPOSE[@]}" exec -T engine alembic current 2>/dev/null | grep -oE '^[0-9a-z_]+' | head -1)"
head_rev="$("${COMPOSE[@]}" exec -T engine alembic heads 2>/dev/null | grep -oE '^[0-9a-z_]+' | head -1)"
echo "      migration: ${cur:-none} (head: ${head_rev:-unknown})"
if [ -n "$cur" ] && [ -n "$head_rev" ] && [ "$cur" != "$head_rev" ]; then
  echo "!! the schema is BEHIND this image's head — a missing column at runtime looks like an" >&2
  echo "   application bug. The migration step reported success, so this is worth understanding" >&2
  echo "   before letting traffic at it." >&2
  exit 1
fi

# Better Auth is meant to be on the POOLED endpoint — the other half of the split. A note rather
# than an assertion: the direct endpoint is correct there too, just chattier.
auth_host="$("${COMPOSE[@]}" exec -T web printenv AUTH_DATABASE_URL 2>/dev/null | sed -e 's#.*@##' -e 's#/.*##' | tr -d '\r')"
case "$auth_host" in
  *-pooler.*) echo "      web tier : $auth_host (pooled — correct for Better Auth)" ;;
  "")         echo "      web tier : AUTH_DATABASE_URL is UNSET — sign-in cannot work" ;;
  *)          echo "      web tier : $auth_host (direct; set DATABASE_URL_POOLED to use the pooler)" ;;
esac

echo
echo "    published ports on this host (only Caddy's 80/443 should appear):"
sudo ss -ltnp 2>/dev/null | grep -E 'docker|caddy' | awk '{print "      " $4}' | sort -u || true
VERIFY

cat <<DONE

────────────────────────────────────────────────────────────────────────────────
  Deployed ${IMAGE_TAG:0:7} ($BRANCH) to $HOST

      https://$APP_HOST          the application
      https://$API_HOST/docs     the partner API contract

  Not this box, and not affected by this deploy:
      https://www.$DOMAIN        the marketing site — Vercel
      the database                                 — Neon, aws-eu-central-1

  Certificates take a few seconds on first boot. If a name does not resolve
  yet, Caddy retries with a backoff — watch it with:

      ssh $SSH_TARGET 'cd $REMOTE_ROOT/repo && sudo docker compose \\
        -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.azure.yml \\
        logs -f caddy'

  NOW RUN THE PRE-FLIGHT CHECKLIST — it checks the things this script cannot,
  including that port 8000 really is closed from the outside:

      ./scripts/preflight.sh $HOST --domain $DOMAIN

  To roll back to the previous release:

      ./scripts/deploy.sh $HOST --tag <previous-sha>

  A rollback is a pull and a restart, not a rebuild — but it does NOT undo a
  migration. If this deploy added one, check that the older image tolerates the
  newer schema before rolling back. docs/deploy/RUNBOOK.md § 6.
────────────────────────────────────────────────────────────────────────────────

DONE
