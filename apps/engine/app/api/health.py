"""Liveness that actually tells you whether the engine can answer.

The endpoint has always been more than a `200 OK`, and it is now more than an inventory. It used to
report that the Soufflé binary resolved on `PATH` and what `clingo.__version__` said — two facts
that are true of a container in which nothing can be solved. A binary with a broken dynamic link
resolves and dies on `exec`; a Python wheel imports and reports a version whether or not its native
grounder works. Both present as `status: "ok"` and then fail on the first coding request.

So `solvers` carries a *probe*: each engine is handed a trivial program and has to produce the right
answer, with the wall time it took to do so. `app.services.solver_probe` holds the programs and the
reasoning about caching them; the reason they are here is that this is the endpoint an orchestrator
and an operator both read, and "installed" was never the question either of them was asking.

`status` is `degraded` when either solver is not `ok`, which is a widening of what it used to mean:
previously only a missing Soufflé binary degraded it, and a Soufflé that was present and broken
reported healthy. The two values themselves are unchanged, deliberately — the Docker healthcheck in
`infra/docker/docker-compose.yml` tests `status == "ok"` and the dashboard's System Health card
branches on the same pair, so renaming `ok` to `healthy` would break two committed readers to gain a
synonym. The new detail is in `solvers`, where it does not disturb anything already reading this.

**No organisation header.** Every proposal and batch endpoint requires one (`app.api.tenancy`); this
one must not. It is what the container healthcheck calls, and a healthcheck that needed a tenant
would report every container unhealthy forever. There is nothing tenant-specific in the response —
it describes the process, not anybody's data.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import pipeline
from app.config import get_settings
from app.schemas import HealthResponse, SolverHealth
from app.services.solver_probe import probe_solvers

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Versions, coverage, and whether both solvers just solved something.

    A plain `def`, so FastAPI dispatches it to the threadpool. That is load-bearing rather than
    incidental: the Soufflé probe spawns a subprocess and blocks on it, and running that on the
    event loop would stall every other request for the length of an interpreter start. It is also
    why the probes are cached — see `app.services.solver_probe`.
    """
    settings = get_settings()
    p = pipeline()
    probes = probe_solvers(settings)

    solvers = {
        name: SolverHealth(
            status=probe.status,
            probe_time_ms=probe.probe_time_ms,
            version=probe.version,
            detail=probe.detail,
        )
        for name, probe in probes.items()
    }

    # Both solvers, not just Soufflé. A Clingo that cannot ground makes `/solve` fail exactly as
    # surely as a missing rules engine does, and a status that stayed `ok` through it would be the
    # same blind spot this endpoint was extended to close.
    healthy = all(probe.ok for probe in probes.values())

    return HealthResponse(
        status="ok" if healthy else "degraded",
        app_env=str(settings.app_env),
        extraction_mode=str(settings.extraction_mode),
        catalog_version=p.catalog.catalog_version,
        rule_coverage=p.catalog.rule_coverage,
        # Kept, and deliberately not replaced by `solvers["souffle"].status`. This says the binary
        # resolves; the probe says it works. A container where the two disagree is the failure worth
        # naming, and it can only be named while both are reported.
        souffle_available=p.souffle.available(),
        # From the probe rather than a second `--version` subprocess: the probe already ran one and
        # cached it, and two spawns per health check to print one string is a cost with no reader.
        souffle_version=probes["souffle"].version,
        clingo_version=probes["clingo"].version or p.clingo.version,
        logic_version=settings.logic_version,
        catalog_ziffern=len(p.catalog.ziffern),
        rules_enforced=len(p.rules.exclusions),
        unverified_rules_not_enforced=len(p.rules.suppressed),
        solver_timeout_seconds=settings.solver_timeout_seconds,
        cache_enabled=p.cache.enabled,
        cache_entries=len(p.cache),
        solvers=solvers,
    )
