# syntax=docker/dockerfile:1
#
# PRODUCTION image. For local development see apps/web/Dockerfile.dev instead — this one has no
# bind-mount story and rebuilds on every source change, which is correct for what ships and wrong for
# iterating.
#
# Build context is the MONOREPO ROOT, not this directory — the same rule as the engine's Dockerfile
# and for the same kind of reason: this app imports `@workspace/ui` and `@workspace/contracts`, which
# live outside apps/web, and the pnpm lockfile that pins the whole graph lives at the root. From the
# repo root:
#
#     docker build -f apps/web/Dockerfile -t govatax-web:0.3.0 .
#
# or use infra/docker/docker-compose.yml, which sets the context correctly.
#
# Three stages: `deps` installs, `builder` builds, `runner` carries neither pnpm nor node_modules.
# The split is not tidiness — it is what keeps the shipped image to the traced server bundle instead
# of a workspace-wide node_modules holding turbo, eslint, typescript and the tailwind toolchain.

# Node 22 to match CI (.github/workflows/ci.yml sets node-version: 22) and the root package.json's
# `engines.node >= 20`. Pinned to a minor, like every other version in this repository: a Next build
# is sensitive to the Node it ran on, and "latest" is not a version.
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
FROM base AS deps
# node-gyp's toolchain, for `better-sqlite3`. Its published prebuilds are glibc binaries and this is
# a musl image, so `prebuild-install` misses and it compiles from source — without these three the
# install fails outright. They cost a layer that is never shipped: `runner` starts from a clean base
# and copies only the traced bundle.
#
# It is here for the development path rather than for this image's own use: `lib/auth-db.ts` refuses
# a SQLite `AUTH_DATABASE_URL` under NODE_ENV=production, so what actually runs here is `pg`. Making
# the driver optional to save the layer would mean an install that succeeds or fails depending on
# the host's libc, which is a worse trade than two minutes of compile in a discarded stage.
RUN apk add --no-cache python3 make g++
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY apps/web/package.json apps/web/
COPY packages/contracts/package.json packages/contracts/
COPY packages/eslint-config/package.json packages/eslint-config/
COPY packages/typescript-config/package.json packages/typescript-config/
COPY packages/ui/package.json packages/ui/
# --frozen-lockfile so the image cannot resolve a dependency graph the lockfile does not describe.
# The same flag CI uses, for the same reason.
RUN pnpm install --frozen-lockfile


# --- builder: `next build` with output: "standalone" ----------------------------------------
FROM base AS builder
# node_modules from the layer above, then the source on top. `.dockerignore` excludes
# **/node_modules, so this COPY cannot clobber what was just installed.
COPY --from=deps /repo ./
COPY . .

# `pnpm --filter web build` rather than `turbo build`: turbo would start a daemon and try to write a
# cache into a layer that is thrown away, and there is nothing to orchestrate — `@workspace/ui` and
# `@workspace/contracts` are consumed as source (see their `exports` maps) and have no build step.
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter web build


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
# There is deliberately NO ENGINE_BASE_URL default. `lib/engine.ts` falls back to
# http://localhost:8000, which is correct for `pnpm dev` on a laptop and always wrong inside a
# container — there is no engine on the container's own loopback. The deployment supplies it
# (docker-compose.yml sets http://engine:8000); getting it wrong then shows up as the engine being
# unreachable on a screen that says so, rather than as a silent fallback to a host that cannot exist.
#
# For the same reason there is no AUTH_DATABASE_URL and no BETTER_AUTH_SECRET default. Both are
# required at run time and both are refused rather than defaulted under NODE_ENV=production (see
# `lib/auth-db.ts` and `lib/auth.ts`): a generated-per-boot signing key invalidates every session on
# every deploy, and a defaulted database silently writes password hashes to a file in the container.
# The schema those two need is created by `pnpm --filter web auth:migrate`, which compose runs as a
# one-shot service before this one starts.

WORKDIR /srv

# Non-root, at the same uid as the engine's runtime user so the two containers are consistent to
# read about and to give volumes to. Created before the COPYs so `--chown` can name it.
RUN addgroup --system --gid 10001 nextjs \
    && adduser --system --uid 10001 --ingroup nextjs --shell /sbin/nologin nextjs

# Two path facts, both easy to get wrong and both verified against a real build:
#
#   1. `.next/` is written inside the app, so the standalone tree is at apps/web/.next/standalone —
#      NOT at the repo root. `outputFileTracingRoot` changes the layout *inside* standalone, not
#      where next puts .next.
#   2. Inside that tree the monorepo's shape is preserved, so the entrypoint is apps/web/server.js
#      (hence the CMD at the bottom) and the two directories below must land relative to it.
#
# `next build` copies neither `static` nor `public` into standalone — that is documented Next
# behaviour, not an oversight here.
COPY --from=builder --chown=10001:10001 /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=10001:10001 /repo/apps/web/.next/static ./apps/web/.next/static
# `public/` holds only a .gitkeep today. Copied anyway, so that an asset added later is served by
# the image instead of silently missing from it.
COPY --from=builder --chown=10001:10001 /repo/apps/web/public ./apps/web/public

USER 10001

EXPOSE 3000

# Asks the Next.js server whether it can serve a request, and nothing more. Deliberately NOT a page
# and deliberately not a proxy to the engine: `/` renders live engine data, so a healthcheck pointed
# at it would report this container unhealthy — and have it restarted — every time the engine
# restarted. See app/api/health/route.ts.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:3000/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "apps/web/server.js"]
