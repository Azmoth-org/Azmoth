#!/bin/sh
# Container entrypoint for the DEV image: check the install, then exec whatever was asked for.
#
# The counterpart to apps/engine/scripts/docker-entrypoint.sh, and an ENTRYPOINT for the same
# reason: compose is free to override `command:`, and a `CMD ["sh","-c","check && next dev"]` would
# be replaced wholesale by that override — silently skipping the check in exactly the setup it
# exists for. As an entrypoint it runs first whatever the command is.
#
# `exec` matters: without it this shell stays as PID 1 and swallows SIGTERM, so `docker stop` waits
# out its grace period and then kills the dev server instead of letting it shut down.
#
# Set CHECK_DEPS=false to skip the staleness check.

set -e

# First, because it is the failure that costs the most time to read: compose masks node_modules with
# an anonymous volume, so the code is current while the install is as old as that volume. Without
# this, a missing package is a per-request resolution error that `next dev` catches — the container
# stays up, the healthcheck fails forever, and `docker ps` says `Up (unhealthy)` rather than naming
# anything. See scripts/check-deps.mjs, which also explains why `--build` alone does not fix it.
if [ "${CHECK_DEPS:-true}" = "true" ]; then
    node /repo/apps/web/scripts/check-deps.mjs
fi

exec "$@"
