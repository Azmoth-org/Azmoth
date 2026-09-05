"""`GET /health` — the cheap probe, at the root, for whatever is watching this container.

## Why this exists next to `/api/v1/health`

`app.api.health` already answers a question called "health", and it is a genuinely different
question. That endpoint hands each solver a program and waits for the right answer back, which for
Soufflé means spawning a subprocess; it also reports the catalog version, the rule counts, the cache
size and the solver timeout. That is the right answer to *"the engine is behaving strangely, what is
it running?"* — and the wrong answer to *"is the engine up?"*, which an uptime monitor asks every
thirty seconds for the life of the deployment.

Splitting them rather than adding a `?cheap=1` to the existing one also protects two committed
readers. `HealthResponse.status` is tested for `== "ok"` by the compose healthcheck in
`infra/docker/docker-compose.yml` and branched on by the dashboard's System Health card, and its
docstring says as much. Folding a database probe into that field would mean a Neon cold start —
which resolves itself in a second or two — marking the container unhealthy and getting it restarted
by Compose, which fixes nothing and drops whatever was in flight. So the database verdict lives
here, on an endpoint with no such reader, and the solver verdict stays there.

## What it actually checks

1. **That this process can answer at all.** Reaching the function body is the check; there is no
   cheaper way to state it and no way for it to be wrong.
2. **That the database answers.** A literal `SELECT 1` through a real session, not a question to
   the connection pool. The pool will happily report a connection it has not used since before a
   failover — `pool_pre_ping` exists precisely because that connection is dead and the pool cannot
   tell — so anything short of executing a statement cannot distinguish "we hold a socket" from
   "Neon just answered us".

The database probe is the one that can be slow, so it is bounded: `DB_PROBE_TIMEOUT_S` is well under
any sensible monitor interval, because a health check that can hang is a health check that turns one
slow dependency into a pile of stuck connections.

## The status code is the verdict

A failed probe answers `503`, not a `200` carrying `"status": "degraded"`. Every reader that matters
here — Caddy's active health checks, a Docker `healthcheck:`, an external uptime monitor — branches
on the status line, and making them parse JSON to notice a failure is how a monitor ends up green
through an outage. The body says *which* check failed; the code says *that* one did.

## No tenant, and nothing tenant-specific in the answer

For the same reason `/api/v1/health` takes no `X-Organization-ID`: this is what a supervisor calls,
and a health check that needed a tenant would report every container unhealthy forever. Nothing in
the response describes anybody's data — it describes this process and its connection to a database.
"""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.db.session import get_database
from app.schemas import DatabaseHealth, LivenessResponse

log = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

#: How long the `SELECT 1` may take before the probe calls the database unreachable.
#:
#: Five seconds, and the number is chosen against the *monitor's* interval rather than against
#: Postgres. A probe that can block for thirty seconds does not report a slow database; it reports
#: nothing at all until long after the monitor has given up, and meanwhile every poll that arrived
#: in the interim is holding a connection open. Five is comfortably above a Neon cold start's usual
#: couple of seconds and comfortably below the ten-second interval Caddy is configured with.
DB_PROBE_TIMEOUT_S = 5.0


async def probe_database() -> DatabaseHealth:
    """Run `SELECT 1` and report what happened. Never raises.

    Never, because it is called from a health endpoint: an exception escaping here would be rendered
    by the error handlers as a `500` with an `INTERNAL_ERROR` envelope, and a monitor reading that
    learns "the engine is broken" when the truthful answer is the far more specific "the engine is
    fine and its database is not". The difference is the first thing an operator wants at 3am.

    `BaseException` is deliberately *not* caught — a `CancelledError` from the client hanging up
    belongs to the caller, and swallowing it here would report a healthy database on a request that
    never completed.
    """
    database = get_database()
    started = time.perf_counter()

    try:
        async with asyncio.timeout(DB_PROBE_TIMEOUT_S):
            async with database.session() as session:
                await session.execute(text("SELECT 1"))
    except TimeoutError:
        elapsed_ms = (time.perf_counter() - started) * 1000
        # ERROR rather than WARNING: this is the line that should page somebody. It names the URL
        # with the password already hidden (`Database.url` renders it that way) because "which
        # database" is the question a wrong DATABASE_URL and an unreachable one both raise, and the
        # exception text alone cannot tell them apart.
        log.error(
            "health: database probe timed out after %.0f ms (limit %.1f s) against %s",
            elapsed_ms,
            DB_PROBE_TIMEOUT_S,
            database.url,
        )
        return DatabaseHealth(
            status="failed",
            latency_ms=round(elapsed_ms, 2),
            url=database.url,
            detail=(
                f"No response within {DB_PROBE_TIMEOUT_S:.0f}s. The database is unreachable or "
                "saturated."
            ),
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        log.error(
            "health: database probe failed after %.0f ms against %s: %s: %s",
            elapsed_ms,
            database.url,
            type(exc).__name__,
            exc,
        )
        return DatabaseHealth(
            status="failed",
            latency_ms=round(elapsed_ms, 2),
            url=database.url,
            # The exception type alongside its text. `OperationalError` and `InterfaceError` send an
            # operator to entirely different places — the first is usually credentials or a firewall,
            # the second a connection that died mid-flight — and the message alone often says
            # neither.
            detail=f"{type(exc).__name__}: {exc}",
        )

    elapsed_ms = (time.perf_counter() - started) * 1000
    # DEBUG on the happy path, on purpose. This endpoint is polled every ten seconds by Caddy and
    # again by whatever else is watching; an INFO line per poll is roughly nine thousand lines a day
    # that say nothing happened, and it would bury the ERROR above when it finally appears.
    log.debug("health: database ok in %.0f ms", elapsed_ms)
    return DatabaseHealth(status="ok", latency_ms=round(elapsed_ms, 2), url=database.url)


@router.get(
    "/health",
    response_model=LivenessResponse,
    summary="Liveness: is this process answering, and does its database answer",
    responses={
        200: {"description": "The process answered and the database answered."},
        503: {"description": "The process answered; the database did not. See `database.detail`."},
    },
)
async def liveness(response: Response) -> LivenessResponse:
    """`200` when the engine can serve and reach Postgres, `503` when it cannot reach Postgres.

    An `async def` with no threadpool hop: the only work is one awaited round trip, so there is
    nothing blocking to keep off the event loop. That is the opposite of `/api/v1/health`, which is
    a plain `def` precisely *because* its Soufflé probe blocks — see the docstring there.

    Setting `response.status_code` rather than raising: an `HTTPException` would be rendered by
    `app.api.errors` into the standard error envelope, and this endpoint's contract is that it
    always returns a `LivenessResponse`. A monitor that has to parse one of two shapes depending on
    the outcome is a monitor that will parse the wrong one on the day it matters.
    """
    database = await probe_database()

    if database.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return LivenessResponse(status="degraded", database=database)

    return LivenessResponse(status="ok", database=database)


__all__ = ["DB_PROBE_TIMEOUT_S", "liveness", "probe_database", "router"]
