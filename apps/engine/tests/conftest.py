"""Shared fixtures.

The helpers let a test drive the symbolic layers with synthetic candidates, so a single rule can
be tested without going through the bridge or the catalog lookup. That separability is the
architectural claim, and the tests exercise it directly.

Cases and golden snapshots come from the monorepo's `logic/tests/` directory, resolved through
`app.config` rather than a path relative to this file, so the suite does not depend on which
directory pytest was invoked from or on where `LOGIC_DIR` points.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.api import deps
from app.bridge.entity_to_ziffer import BridgeResult
from app.catalog import load_catalog
from app.config import (
    CASES_DIR,
    GOLDEN_DIR,
    RULES_DATA_DIR,
    BaseFactorPolicy,
    ExtractionMode,
    Settings,
    UnverifiedRulePolicy,
)
from app.rules.rule_store import RuleStore
from app.schemas import ClinicalAct, ClinicalExtraction, CodeCandidate
from app.services.pipeline import Pipeline
from app.solvers.clingo_solver import ClingoSolver
from app.solvers.souffle_engine import SouffleEngine
from app.validation.validator import Validator

PADNEXT_DIR = CASES_DIR / "padnext"


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Explicit defaults, so a developer's .env can never change what the suite asserts."""
    return Settings(
        app_env="development",
        debug=False,
        extraction_mode=ExtractionMode.MANUAL,
        unverified_rule_policy=UnverifiedRulePolicy.WARN,
        base_factor_policy=BaseFactorPolicy.SCHWELLENWERT,
        solver_timeout_seconds=5.0,
        cache_enabled=True,
    )


@pytest.fixture(scope="session")
def catalog():
    return load_catalog()


@pytest.fixture(scope="session")
def rules(settings):
    return RuleStore.load(RULES_DATA_DIR, policy=settings.unverified_rule_policy)


@pytest.fixture
def souffle(settings, catalog, rules):
    engine = SouffleEngine(settings, catalog, rules)
    if not engine.available():
        pytest.skip("souffle binary not on PATH")
    return engine


@pytest.fixture
def solver(settings, catalog, rules):
    return ClingoSolver(settings, catalog, rules)


@pytest.fixture
def validator(settings, catalog, rules):
    return Validator(settings, catalog, rules)


@pytest.fixture
def pipeline(settings, catalog, rules):
    p = Pipeline(settings, catalog, rules)
    if not p.souffle.available():
        pytest.skip("souffle binary not on PATH")
    return p


@pytest.fixture
def client():
    """A TestClient over the real app, with the shared singletons rebuilt for each test.

    Resetting is what keeps the proposal-store tests independent of each other: the store is a
    process-wide singleton by design, so a test that approved something would otherwise be visible
    to the next one.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    deps.reset()
    with TestClient(app) as test_client:
        if not deps.pipeline().souffle.available():
            pytest.skip("souffle binary not on PATH")
        yield test_client
    deps.reset()


@pytest.fixture(scope="session")
def manual_case():
    def _load(name: str) -> dict:
        return json.loads((CASES_DIR / name / "input.json").read_text(encoding="utf-8"))

    return _load


@pytest.fixture(scope="session")
def expected_case():
    def _load(name: str) -> dict:
        return json.loads((CASES_DIR / name / "expected.json").read_text(encoding="utf-8"))

    return _load


@pytest.fixture(scope="session")
def golden_case():
    def _load(name: str) -> dict:
        path = GOLDEN_DIR / f"{name}.golden.normalized.json"
        return json.loads(path.read_text(encoding="utf-8"))

    return _load


# ------------------------------------------------------------------------------------------
# HTTP helpers
# ------------------------------------------------------------------------------------------


def solve_payload(client, extraction: dict, **extra) -> dict:
    """POST /api/v1/solve and return the CodingResponse inside the DRAFT proposal.

    The endpoint returns a `Proposal`; almost every assertion in the suite is about the invoice
    draft it wraps, so unwrapping once here keeps the tests about the engine rather than about the
    envelope. `solve_proposal` is there for the tests that are about the envelope.
    """
    response = client.post("/api/v1/solve", json={"extraction": extraction, **extra})
    assert response.status_code == 200, response.text
    return response.json()["solver_result"]


def solve_proposal(client, extraction: dict, **extra) -> dict:
    response = client.post("/api/v1/solve", json={"extraction": extraction, **extra})
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------------------------------------
# synthetic input helpers
# ------------------------------------------------------------------------------------------


def make_bridge(*specs: tuple[str, str, int, str]) -> BridgeResult:
    """Build a BridgeResult from ``(act_id, ziffer, priority, confidence)`` tuples.

    Several tuples sharing an ``act_id`` model one clinical act with competing candidates.
    """
    bridge = BridgeResult()
    seen: set[str] = set()
    for act_id, ziffer, priority, confidence in specs:
        if act_id not in seen:
            seen.add(act_id)
            bridge.acts.append(
                ClinicalAct(
                    act_id=act_id,
                    entity_id=act_id,
                    source="procedure",
                    entity_type=f"synthetic_{act_id}",
                    description=f"synthetic act {act_id}",
                    confidence=Decimal(confidence),
                )
            )
        bridge.candidates.append(
            CodeCandidate(
                act_id=act_id,
                ziffer=ziffer,
                priority=priority,
                confidence=Decimal(confidence),
                mapping_provenance="test",
            )
        )
    return bridge


def one_act_per_ziffer(*ziffern: str, confidence: str = "0.9") -> BridgeResult:
    """One act per Ziffer — the common case where nothing competes inside an act."""
    return make_bridge(
        *[(f"a{i}", z, 100, confidence) for i, z in enumerate(ziffern, start=1)]
    )


def make_extraction(setting: str = "ambulant", justifications: list[dict] | None = None):
    return ClinicalExtraction.model_validate(
        {
            "patient": {"age": 50, "sex": "m", "setting": setting},
            "justification_factors": justifications or [],
        }
    )
