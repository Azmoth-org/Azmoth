"""FastAPI surface.

Six routers, one prefix (`/api/v1`), no UI. The engine serves an API and nothing else: the POC's
static pages, its demo endpoints and its experimental free-text path are deliberately absent — see
`docs/migration/MIGRATION_PLAN.md` §2.

No solver ever runs on the event loop. Soufflé is a subprocess and Clingo runs in-process; both
block, so a solve either sits in a plain `def` path function (which FastAPI dispatches to its
threadpool) or is handed to that same pool explicitly with `run_in_threadpool` — which is what
`/solve` does now that it also has to await a database write. Either way the loop stays free;
running a solve directly in an `async def` would serialise the whole service behind it.

The database is opened and closed by the lifespan, not on first use, so a bad `DATABASE_URL` fails
at startup rather than on somebody's first approval.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import catalog, health, padnext, proposals, rules, solve
from app.api.deps import batches, pipeline, reset_async
from app.config import get_settings
from app.core.limits import RequestSizeLimitMiddleware
from app.db.session import get_database, init_models

settings = get_settings()

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    p = pipeline()

    # Before anything else: a service that cannot record an approval must not accept one. The
    # connection is opened here rather than lazily so that a wrong DATABASE_URL, a missing
    # migration or an unreachable Postgres is a startup failure with a stack trace, instead of a
    # 500 on the first reviewer who presses Freigeben.
    database = get_database()
    await init_models(database)
    if not settings.database_is_durable:
        log.warning(
            "database is %s (%s) — a single-file store with one writer and no encryption at rest. "
            "Fine for development and the test suite; set DATABASE_URL to Postgres for anything "
            "an approval has to survive in.",
            settings.database_backend,
            database.url,
        )

    # Merge the stored rule reviews into the rule store before anything can solve against it. At
    # startup rather than lazily: a first request that raced the merge would be answered under the
    # CSVs' own verification state, and "the first invoice after a restart was audited against
    # different rules" is not a sentence anyone wants to have to explain.
    from app.services.rule_reviews import refresh_pipeline_rules

    await refresh_pipeline_rules(p)

    # Close batches a previous process abandoned. Here — after the schema exists and before the
    # server accepts anything — because that is the only moment at which a `PENDING` or `PROCESSING`
    # batch row is guaranteed not to belong to this process, and is therefore guaranteed to be a
    # leftover of one that died. A batch is audited by a `BackgroundTask` that does not survive its
    # process, so without this the row stays in limbo forever and the screen polling it can only
    # time out. See `BatchAuditService.reap_interrupted_batches` for why this assumes one worker.
    if settings.reap_interrupted_batches:
        await batches().reap_interrupted_batches()
    else:
        log.info(
            "batch recovery disabled (REAP_INTERRUPTED_BATCHES=false) — an interrupted batch will "
            "stay PENDING/PROCESSING until something else closes it"
        )

    if not p.souffle.available():
        log.error(
            "Soufflé binary '%s' not found — /solve and /padnext/audit will fail. See README.",
            settings.souffle_bin,
        )
    for path in (settings.datalog_path, settings.asp_path):
        if not path.is_file():
            log.error("logic program missing: %s (set LOGIC_DIR)", path)

    # An expected snapshot that does not match the shipped data is a silent wrong-answer bug, so
    # it is a startup failure rather than a log line.
    if settings.catalog_version and settings.catalog_version != p.catalog.catalog_version:
        raise RuntimeError(
            f"CATALOG_VERSION={settings.catalog_version!r} does not match the loaded catalog "
            f"{p.catalog.catalog_version!r} at {settings.catalog_path}."
        )

    coverage = p.rule_coverage()
    log.info(
        "ready: env=%s mode=%s catalog=%s (%d Ziffern) coverage=%s rules=%d enforced / "
        "%d advisory (%d unverified, policy=%s) souffle=%s clingo=%s logic=%s cache=%s timeout=%ss",
        settings.app_env,
        settings.extraction_mode,
        p.catalog.catalog_version,
        len(p.catalog.ziffern),
        p.catalog.rule_coverage,
        coverage.enforced_rule_count,
        coverage.advisory_rule_count,
        coverage.suppressed_unverified_rule_count,
        settings.unverified_rule_policy,
        p.souffle.version() or "MISSING",
        p.clingo.version,
        settings.logic_version[:12],
        "on" if p.cache.enabled else "off",
        settings.solver_timeout_seconds,
    )
    log.info("database: %s (durable=%s)", database.url, settings.database_is_durable)
    try:
        yield
    finally:
        # Dispose the pool on the way out. Without this, `TestClient` in a suite of hundreds of
        # cases accumulates one engine — and on SQLite one open file handle — per app instance.
        await reset_async()


app = FastAPI(
    lifespan=lifespan,
    title="Govatax GOÄ engine",
    version="0.3.0",
    description=(
        "GOÄ coding where the legal reasoning is symbolic and auditable.\n\n"
        "`POST /api/v1/solve` takes structured clinical entities — no model runs anywhere in this "
        "service. A Soufflé Datalog program decides what is certainly chargeable, a Clingo ASP "
        "program resolves what genuinely requires a choice under a hard timeout, an independent "
        "validation pass re-checks the result, and every line carries a proof tree with rule ids "
        "and paragraph references.\n\n"
        "**The response is a DRAFT proposal, not an invoice.** It leaves `DRAFT` only when a named "
        "person approves it. Every response carries `receipt_hash` (SHA-256 over the catalog, the "
        "rule tables, the logic programs, the solver versions, the policy and the input) and the "
        "rule-coverage counts: `enforced_rule_count` is what can suppress a position, "
        "`advisory_rule_count` is what only warns.\n\n"
        "The catalog is imported from the official GOÄ published at gesetze-im-internet.de. "
        "Rule coverage is **partial** — see `GET /api/v1/catalog`. **Synthetic data only.**"
    ),
    openapi_tags=[
        {"name": "health", "description": "Liveness, versions and engine availability."},
        {"name": "solve", "description": "Clinical entities → a receipted DRAFT proposal."},
        {"name": "proposals", "description": "The human approval boundary."},
        {"name": "padnext", "description": "Audit an already-coded PADnext delivery."},
        {"name": "catalog", "description": "Catalog provenance and the mappable vocabulary."},
        {
            "name": "rules",
            "description": (
                "The rule verification workflow. 859 of 894 constraint rules were extracted from "
                "the GOÄ's prose automatically and enforce nothing until a billing expert verifies "
                "them; verifying one shrinks the `unconfirmed` bucket of every later audit. "
                "Decisions are stored in Postgres and merged onto the versioned CSVs at load "
                "time — the CSVs themselves are never written by this API."
            ),
        },
    ],
)

# Registered before anything else so an oversized body is refused at the perimeter, not after
# FastAPI has already buffered it. See app/core/limits.py for the Content-Length caveat.
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.max_request_bytes)

app.include_router(health.router, prefix=API_PREFIX)
app.include_router(solve.router, prefix=API_PREFIX)
app.include_router(proposals.router, prefix=API_PREFIX)
app.include_router(padnext.router, prefix=API_PREFIX)
app.include_router(catalog.router, prefix=API_PREFIX)
app.include_router(rules.router, prefix=API_PREFIX)
