"""FastAPI surface.

Five routers, one prefix (`/api/v1`), no UI. The engine serves an API and nothing else: the POC's
static pages, its demo endpoints and its experimental free-text path are deliberately absent — see
`docs/migration/MIGRATION_PLAN.md` §2.

Every path function that reaches a solver is a plain `def`. Soufflé is a subprocess and Clingo runs
in-process; both block. FastAPI dispatches sync path functions to its threadpool, so the event loop
stays free. Declaring them `async def` would serialise the whole service behind one solve.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import catalog, health, padnext, proposals, solve
from app.api.deps import pipeline
from app.config import get_settings
from app.core.limits import RequestSizeLimitMiddleware

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
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Catalys GOÄ engine",
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
