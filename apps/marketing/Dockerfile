# syntax=docker/dockerfile:1
#
# PRODUCTION image for the marketing site. For local development see apps/marketing/Dockerfile.dev
# instead — this one has no bind-mount story and rebuilds on every source change, which is correct
# for what ships and wrong for iterating.
#
# Build context is the MONOREPO ROOT, the same rule as apps/web/Dockerfile and for the same reason:
# this app imports `@workspace/ui`, which lives outside apps/marketing, and the pnpm lockfile that
# pins the whole graph lives at the root. From the repo root:
#
#     docker build -f apps/marketing/Dockerfile -t azmoth-marketing:0.3.0 .
#
# or use infra/docker/docker-compose.yml, which sets the context correctly.
#
# Three stages: `deps` installs, `builder` builds, `runner` carries neither pnpm nor node_modules.
# The split is what keeps the shipped image to the traced server bundle instead of a
# workspace-wide node_modules holding turbo, eslint, typescript and the tailwind toolchain.
#
# ── One thing to know before changing this file ────────────────────────────────────────────────
# Every page on this site is statically prerendered, so the address of the product app is baked
# into the HTML at BUILD time. It is a build argument below, NOT a runtime environment variable:
# setting APP_URL on the container has no effect on a page that was already rendered. Changing
# where "Anmelden" points means rebuilding this image. See apps/marketing/src/lib/site.ts.
# ───────────────────────────────────────────────────────────────────────────────────────────────

# Node 22.14, pinned to a minor, matching apps/web/Dockerfile, apps/web/Dockerfile.dev and CI
# (.github/workflows/ci.yml sets node-version: 22). Deliberately NOT the Node 20 a fresh Next.js
# scaffold suggests: a Next build is sensitive to the Node it ran on, and an image built on a
# different major than the one CI tests against is how "works in CI" stops meaning anything.
FROM node:22.14-alpine AS base
# pnpm comes from corepack, which reads the exact version out of the root package.json's
# `packageManager` field — so the image cannot build with a different pnpm than CI and the developer
# use. Installing pnpm from npm by hand is how those three drift apart.
RUN corepack enable
WORKDIR /repo


# --- deps: the workspace's node_modules, cached on the manifests alone ----------------------
# Only manifests and the lockfile are copied here, so this layer is rebuilt when a dependency
# changes and reused when application code changes. Copying the source first would make every edit
# re-run a full install.
#
# No build toolchain (python3/make/g++) here, unlike apps/web/Dockerfile: that is there for
# `better-sqlite3`, a native addon this app does not have. It has no database at all.
FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY apps/marketing/package.json apps/marketing/
COPY packages/eslint-config/package.json packages/eslint-config/
COPY packages/typescript-config/package.json packages/typescript-config/
COPY packages/ui/package.json packages/ui/
# `--filter marketing...` installs this app and what it depends on, not the whole workspace: apps/web
# and apps/engine have no business being resolved for a build that cannot use them.
#
# `--frozen-lockfile` so the image cannot resolve a dependency graph the lockfile does not describe.
# The same flag CI uses, for the same reason.
RUN pnpm install --frozen-lockfile --filter marketing...


# --- builder: `next build` with output: "standalone" ----------------------------------------
FROM base AS builder

# The address of the product app, baked in at build time — see the note at the top of this file.
# Defaulted to the production domain so a plain `docker build` produces a correct image; a preview
# or a staging deploy overrides it:
#
#     docker build -f apps/marketing/Dockerfile --build-arg APP_URL=https://app.staging.azmoth.de .
#
# NEXT_PUBLIC_APP_URL is accepted as an alias by lib/site.ts, so either name works; APP_URL is
# preferred because it never reaches the client bundle.
ARG APP_URL="https://app.azmoth.de"
ARG NEXT_PUBLIC_SITE_URL="https://www.azmoth.de"
ENV APP_URL=${APP_URL} \
    NEXT_PUBLIC_SITE_URL=${NEXT_PUBLIC_SITE_URL}

# node_modules from the layer above, then the source on top. `.dockerignore` excludes
# **/node_modules, so this COPY cannot clobber what was just installed.
COPY --from=deps /repo ./
COPY . .

# `pnpm --filter marketing build` rather than `turbo run build --filter=marketing`: turbo would
# start a daemon and try to write a cache into a layer that is thrown away, and there is nothing
# here to orchestrate. `@workspace/ui` is consumed as source (see its `exports` map) and has no
# build step of its own — nothing in `packages/` needs building before this app does.
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter marketing build


# --- runner: the traced bundle, and nothing else --------------------------------------------
FROM node:22.14-alpine AS runner
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# HOSTNAME=0.0.0.0 is required, not cosmetic: the standalone server binds localhost by default,
# which inside a container means nothing outside it can connect and the published port answers
# ECONNREFUSED.
#
# There are no other variables to set. This app has no database, no session, no secret and no
# upstream service — which is the whole reason the marketing site was separated from apps/web.
# NEXT_PUBLIC_GA_MEASUREMENT_ID is the one thing a deployment may want, and it belongs at build
# time like every other NEXT_PUBLIC_ value; unset means no analytics script is ever loaded and the
# cookie banner does not appear.

WORKDIR /srv

# Non-root, at the same uid as apps/web's and the engine's runtime user, so every container in the
# stack is consistent to read about and to give volumes to. Created before the COPYs so `--chown`
# can name it.
RUN addgroup --system --gid 10001 nextjs \
    && adduser --system --uid 10001 --ingroup nextjs --shell /sbin/nologin nextjs

# Two path facts, both easy to get wrong and both verified against a real build:
#
#   1. `.next/` is written inside the app, so the standalone tree is at
#      apps/marketing/.next/standalone — NOT at the repo root. `outputFileTracingRoot` changes the
#      layout *inside* standalone, not where next puts .next.
#   2. Inside that tree the monorepo's shape is preserved, so the entrypoint is
#      apps/marketing/server.js (hence the CMD at the bottom) and the two directories below must
#      land relative to it.
#
# `next build` copies neither `static` nor `public` into standalone — that is documented Next
# behaviour, not an oversight here. `public/` matters on this app in a way it does not on apps/web:
# it holds the favicon, the web manifest and llms.txt.
COPY --from=builder --chown=10001:10001 /repo/apps/marketing/.next/standalone ./
COPY --from=builder --chown=10001:10001 /repo/apps/marketing/.next/static ./apps/marketing/.next/static
COPY --from=builder --chown=10001:10001 /repo/apps/marketing/public ./apps/marketing/public

USER 10001

EXPOSE 3000

# The homepage itself. Unlike apps/web there is no /api/health to ask and none is needed: this app
# renders no live data and depends on no other service, so a page that returns 200 genuinely means
# the site is up.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "apps/marketing/server.js"]
