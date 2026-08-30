"""FastAPI surface.

Eight routers, one prefix (`/api/v1`), no UI. The engine serves an API and nothing else: the POC's
static pages, its demo endpoints and its experimental free-text path are deliberately absent — see
`docs/migration/MIGRATION_PLAN.md` §2.

**Two authentication boundaries, and they are not interchangeable.** Six of the routers are reached
by our own web tier through a trusted proxy that has already resolved a Better Auth session, and
they take their tenant from an asserted `X-Organization-ID` header (`app.api.tenancy`). The
`audit` router is the commercial surface: it is reached directly by a PVS vendor or a billing
centre over the internet, so it verifies an `X-API-Key` and takes the tenant from the *stored row*
rather than from anything in the request (`app.api.apikeys`). `settings_keys` is the seam between
them — it mints the keys, and it is behind the session, because a first key cannot be issued to a
caller who already has one. `docs/api/PARTNER_API.md` is the contract those two publish.

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

from app.api import (
    audit,
    catalog,
    demo,
    health,
    padnext,
    proposals,
    rules,
    settings_keys,
    solve,
)
from app.api.deps import batches, pipeline, reset_async, usage_meter
from app.api.errors import register_error_handlers
from app.config import LogFormat, get_settings
from app.core.limits import RequestSizeLimitMiddleware
from app.core.observability import RequestContextMiddleware, configure_logging
from app.db.session import get_database, init_models
from app.errors import ErrorResponse
from app.services.uploads import ensure_upload_root

settings = get_settings()

# One JSON object per line, with the request id on every one of them. Configured at import time
# rather than in the lifespan because the module-level work below (building the app, reading the
# settings) already logs, and those lines belong in the same stream as everything else.
configure_logging(debug=settings.debug, json_logs=settings.log_format is LogFormat.JSON)
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

    # The upload volume, before the first partner can post to it. A failure here is a log line
    # rather than a startup refusal: an engine that cannot write uploads still serves /solve,
    # /audit/single and every read endpoint, and taking the whole service down over one feature
    # would be the wrong trade. The bulk endpoint answers 503 on its own — see app/services/uploads.
    ensure_upload_root(settings)

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

    # Resume the bulk queue. `reap_interrupted_batches` above put every interrupted bulk job back
    # to `PENDING` (its archive is still on disk, unlike an in-memory batch's payloads), so this
    # picks up exactly the work a restart interrupted, plus anything queued and never drained.
    #
    # **Awaited here, before the server accepts a request, and that is not a stylistic choice.** An
    # earlier version started it as a background task so startup would not wait on a backlog, and
    # it was wrong on the default database: `DATABASE_URL` is SQLite, whose in-memory form shares
    # one connection through `StaticPool` and whose file form has exactly one writer. A drain
    # transacting while the first requests transact interleaves `BEGIN`/`COMMIT`/`ROLLBACK` on that
    # single connection, and a rollback issued by the drain discards the *request's* write — a
    # batch inserted by an endpoint that then vanished before its own background task could find
    # it. That is the same reasoning `reap_interrupted_batches` states for running where it does:
    # before anything is being served, nothing else is writing.
    #
    # The cost is stated rather than hidden: a large requeued backlog delays readiness, and a
    # container's healthcheck `start_period` has to cover it. `REAP_INTERRUPTED_BATCHES=false` is
    # the switch for a deployment that would rather resume from an admin step — it suppresses the
    # requeue above, and there is then nothing here to drain.
    resumed = await batches().drain_pending_jobs()
    if resumed:
        log.info("resumed %d queued bulk job(s) at startup: %s", len(resumed), ", ".join(resumed))

    try:
        yield
    finally:
        # Write out whatever the usage meter is still holding, BEFORE the pool it writes through is
        # disposed. `app.services.usage` buffers rows so the audit path pays no database round trip
        # per call; this is the other half of that bargain — a clean shutdown loses nothing, and
        # only a kill leaves the last few rows unwritten.
        pending = usage_meter().pending
        if pending:
            written = await usage_meter().flush()
            log.info("flushed %d of %d buffered usage row(s) on shutdown", written, pending)

        # Dispose the pool on the way out. Without this, `TestClient` in a suite of hundreds of
        # cases accumulates one engine — and on SQLite one open file handle — per app instance.
        await reset_async()


app = FastAPI(
    lifespan=lifespan,
    title="Azmoth GOÄ engine",
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
        "Rule coverage is **partial** — see `GET /api/v1/catalog`. **Synthetic data only.**\n\n"
        "**Errors.** Every non-2xx response carries `error_code` (stable, machine-readable), "
        "`message`, `details` and, where retrying could work, `retry_after` in seconds plus a "
        "`Retry-After` header. The complete catalog of codes is in `docs/errors.md`."
    ),
    openapi_tags=[
        {"name": "health", "description": "Liveness, versions and engine availability."},
        {"name": "solve", "description": "Clinical entities → a receipted DRAFT proposal."},
        {"name": "proposals", "description": "The human approval boundary."},
        {"name": "padnext", "description": "Audit an already-coded PADnext delivery."},
        {"name": "catalog", "description": "Catalog provenance and the mappable vocabulary."},
        {
            "name": "demo",
            "description": (
                "The public demo. Reachable without a credential, and — the property that "
                "makes that acceptable — it accepts no input: both endpoints audit one "
                "committed synthetic delivery whose path is a constant, so no request can "
                "cause this service to process a visitor's own data. Outside the partner "
                "contract in `docs/api/PARTNER_API.md`; see `app/api/demo.py`."
            ),
        },
        {
            "name": "audit",
            "description": (
                "**Die kommerzielle Schnittstelle.** PADnext hinein, JSON heraus, authentifiziert "
                "mit `X-API-Key`. Einzelprüfung synchron, Massenprüfung als ZIP im Hintergrund, "
                "Prüfbericht als PDF. Die Organisation ergibt sich aus dem Schlüssel — es gibt "
                "keinen Header, mit dem ein Aufrufer eine andere angeben könnte.\n\n"
                "**The commercial surface.** PADnext in, JSON out, authenticated by API key. One "
                "delivery synchronously, an archive of many in the background, and a printable "
                "report. The full contract is in `docs/api/PARTNER_API.md`."
            ),
        },
        {
            "name": "settings",
            "description": (
                "API-Schlüssel erzeugen, auflisten und widerrufen. Hinter der Sitzung, nicht "
                "hinter einem Schlüssel — der erste Schlüssel kann niemandem ausgestellt werden, "
                "der schon einen hat. — Mint, list and revoke API keys. Behind the session rather "
                "than behind a key, because a first key cannot be issued to a caller who already "
                "holds one."
            ),
        },
        {
            "name": "rules",
            "description": (
                "The rule verification workflow. Most of this engine's constraint rules were "
                "extracted from the GOÄ's prose automatically; one enforces nothing until a "
                "billing expert has verified it, and verifying one shrinks the `unconfirmed` "
                "bucket of every later audit. Decisions are stored in Postgres and merged onto the "
                "versioned CSVs at load time — the CSVs themselves are never written by this API."
                "\n\n"
                "**No count is quoted here on purpose.** How many rules are enforced changes every "
                "time a reviewer decides one, and a number written into a static document is a "
                "claim with no mechanism to stay true — this description carried a stale one for "
                "weeks. `GET /api/v1/rules/coverage` and `GET /api/v1/health` report the live "
                "figures, and every audit response carries them in `rule_coverage_detail`."
            ),
        },
    ],
)

# Every failure leaves through one of four handlers, so `error_code` / `message` / `details` /
# `retry_after` is on the body of every non-2xx response regardless of where it was raised. See
# app/api/errors.py, and docs/errors.md for the catalog itself.
register_error_handlers(app)

# Registered before anything else so an oversized body is refused at the perimeter, not after
# FastAPI has already buffered it. See app/core/limits.py for the Content-Length caveat.
#
# The two overrides are the endpoints whose own limit differs from the global 32 MiB: the bulk
# upload takes a larger archive, and the single partner audit takes a much smaller file. Both
# numbers come from the same settings the endpoints enforce, so the perimeter and the handler
# cannot disagree about them.
# Registered LAST and therefore running FIRST — Starlette applies middleware in reverse order of
# registration — so a request has an id before the size limiter can refuse it. A partner whose 60 MB
# upload was rejected can still quote an id, which is precisely the request somebody asks about.
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_bytes=settings.max_request_bytes,
    overrides=[
        (f"{API_PREFIX}/audit/bulk", settings.max_bulk_zip_bytes),
        (f"{API_PREFIX}/audit/single", settings.max_single_xml_bytes),
    ],
)

#: Declared on every router so `ErrorResponse` is in the OpenAPI document and therefore in the
#: generated TypeScript. Without this the envelope would be a shape clients discover by hitting it
#: in production, which is exactly the situation the catalog exists to end.
ERROR_RESPONSES: dict = {
    "4XX": {"model": ErrorResponse, "description": "See docs/errors.md for the codes."},
    "5XX": {"model": ErrorResponse, "description": "See docs/errors.md for the codes."},
}

app.add_middleware(RequestContextMiddleware)

for router in (health, solve, proposals, padnext, catalog, rules, audit, settings_keys, demo):
    app.include_router(router.router, prefix=API_PREFIX, responses=ERROR_RESPONSES)
