"""Liveness that actually tells you whether the engine can answer.

`status` is `degraded` when Soufflé is missing, because a container whose rules engine is absent
answers HTTP perfectly and fails every coding request. That distinction is the point of the
endpoint; the Docker healthcheck reads exactly these two fields.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import pipeline
from app.config import get_settings
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    p = pipeline()
    return HealthResponse(
        status="ok" if p.souffle.available() else "degraded",
        app_env=str(settings.app_env),
        extraction_mode=str(settings.extraction_mode),
        catalog_version=p.catalog.catalog_version,
        rule_coverage=p.catalog.rule_coverage,
        souffle_available=p.souffle.available(),
        souffle_version=p.souffle.version(),
        clingo_version=p.clingo.version,
        logic_version=settings.logic_version,
        catalog_ziffern=len(p.catalog.ziffern),
        rules_enforced=len(p.rules.exclusions),
        unverified_rules_not_enforced=len(p.rules.suppressed),
        solver_timeout_seconds=settings.solver_timeout_seconds,
        cache_enabled=p.cache.enabled,
        cache_entries=len(p.cache),
    )
