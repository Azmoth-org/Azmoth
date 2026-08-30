"""Shared fixtures.

The helpers let a test drive the symbolic layers with synthetic candidates, so a single rule can
be tested without going through the bridge or the catalog lookup. That separability is the
architectural claim, and the tests exercise it directly.

Cases and golden snapshots come from the monorepo's `logic/tests/` directory, resolved through
`app.config` rather than a path relative to this file, so the suite does not depend on which
directory pytest was invoked from or on where `LOGIC_DIR` points.

**The database.** `DATABASE_URL` is forced to in-memory SQLite here, at import time — before
`app.main` is imported and before `get_settings()` is first called — so a developer's `.env` or a
`DATABASE_URL` exported for a psql session can never point the suite at a real database and write
test proposals into it. In-memory rather than a file for a reason that is also the isolation
mechanism: for SQLite, the connection *is* the database, so every new engine gets an empty one and
a test cannot see the proposals of the test before it. `tests/test_db_persistence.py` is the
exception — it needs a store that outlives its connection, so it builds a file-backed one in
`tmp_path` and reopens it.

**The organisation header.** Every proposal and batch endpoint requires `X-Organization-ID` and
answers `403` without it (`app.api.tenancy`), so the `client` fixture sets one on every request:
`TEST_ORGANIZATION_ID`. That is not a way around the check — it is what a real caller does, and the
suite is a real caller. The tests that are *about* the boundary build their own clients with
different ids, or with none, and live in `tests/test_tenancy.py`.

**Uploads.** `UPLOAD_DIR` is forced to a fresh temporary directory here, for the same reason and at
the same moment. Its default is `<repo>/data/uploads`, and `data/` is where the versioned catalog
and rule tables live — a test run that wrote bulk uploads into it would drop untracked billing files
into a directory git tracks. The directory is removed at interpreter exit.

This means the suite does not exercise Postgres. `POSTGRES_TEST_URL` is honoured by
`tests/test_db_persistence.py`, which runs the same assertions against a real server when one is
pointed at — see that module for the command. CI runs SQLite; the dialect-specific behaviour
(JSONB, `FOR UPDATE`, timezone-aware timestamps) is what that variable is for.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import tempfile
from decimal import Decimal

import pytest

# Set before any `app.*` import below, because `Settings` reads the environment once and
# `get_settings()` caches it. Assignment rather than `setdefault`: an inherited DATABASE_URL must be
# overridden, not respected — a suite that wrote test proposals into a real database because the
# shell happened to export one would be a serious accident.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["DATABASE_AUTO_CREATE"] = "true"

# And the same guard for the one other thing the engine writes outside the database. `UPLOAD_DIR`
# defaults to the repo's own `data/` directory, which holds the versioned catalog and rule tables —
# a suite that wrote bulk uploads in there would put untracked billing files inside data git
# tracks, and `git status` would be the first anyone heard of it. Set before any `app.*` import for
# the same reason as DATABASE_URL: `Settings` reads the environment once.
_UPLOAD_ROOT = tempfile.mkdtemp(prefix="azmoth-test-uploads-")
os.environ["UPLOAD_DIR"] = _UPLOAD_ROOT
atexit.register(shutil.rmtree, _UPLOAD_ROOT, True)

# The container image sets APP_ENV=production, and CI runs this suite inside it. Two production
# guards would fire on that: `create_all` is refused in production (the schema must come from a
# migration) and so is a non-Postgres DATABASE_URL. Both are correct for a running service and both
# are wrong for a test run, which is not a deployment — so the suite says what it is. It is also why
# `test_the_required_settings_all_exist_with_the_mandated_defaults` asserts on field defaults rather
# than on `Settings()`: the environment here belongs to the harness, not to the product.
os.environ["APP_ENV"] = "development"

# The suite's schema baseline. `strict` is the application default, but the pilot deployment sets
# `PADNEXT_SCHEMA_POLICY=warn` in `infra/docker/.env`, and a developer who exported it into their
# shell would silently turn every "this malformed delivery is refused" assertion into a test of the
# escape hatch — the suite would still pass, and it would have stopped guarding the thing it exists
# to guard. Assignment rather than `setdefault`, for the same reason as DATABASE_URL above: an
# inherited value must be overridden, not respected. The `warn` and `off` cases are tested by
# passing `schema_policy=` explicitly, or through the `warn_client` fixture in
# `tests/test_padnext_schema.py`, which sets this variable itself and clears the settings cache.
os.environ["PADNEXT_SCHEMA_POLICY"] = "strict"

from app.api import deps
from app.api.tenancy import ORGANIZATION_ID_HEADER
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
from app.db.session import Database
from app.rules.rule_store import RuleStore
from app.schemas import ClinicalAct, ClinicalExtraction, CodeCandidate
from app.services.pipeline import Pipeline
from app.services.proposal_store import ProposalStore
from app.solvers.clingo_solver import ClingoSolver
from app.solvers.souffle_engine import SouffleEngine
from app.validation.validator import Validator

PADNEXT_DIR = CASES_DIR / "padnext"


#: The organisation every request from the `client` fixture acts for.
#:
#: Shaped like a Better Auth id — 32 characters of its alphabet — rather than something like
#: `test-org`, so nothing in the suite can come to depend on a tenant id being human-readable. One
#: id for the whole fixture, because a test that wants two practices wants `tests/test_tenancy.py`,
#: where the second one is the point rather than a detail.
TEST_ORGANIZATION_ID = "org7Kd2Vn8Qs4Rt6Yw1Zx3Bc5Ef9Gh0J"


def _engines_required() -> bool:
    """Whether a missing solver binary should FAIL the run instead of skipping it.

    Skipping is right on a laptop without Soufflé installed, and dangerous in CI: a run that
    skipped every rules-engine test looks exactly like a run that passed them. Set
    `REQUIRE_ENGINES=1` where the binaries are guaranteed — the container image, CI — and the
    absence becomes a failure that names itself.

    This replaces an earlier attempt that parsed pytest's skip count out of its own output. That
    check could not work: `pytest.ini` already passes `-q`, so CI's second `-q` made it `-qq`, at
    which pytest prints no summary line at all. The count was always empty, so the guard passed
    unconditionally — including the case it existed to catch.
    """
    return os.getenv("REQUIRE_ENGINES", "").strip().lower() in {"1", "true", "yes"}


def _no_souffle(settings) -> str:
    return (
        f"Soufflé binary {settings.souffle_bin!r} is not on PATH, so every test that drives the "
        "rules engine would be skipped."
    )


def _require_or_skip(settings) -> None:
    if _engines_required():
        pytest.fail(
            f"REQUIRE_ENGINES is set but {_no_souffle(settings)} Install it (apps/engine/README.md) "
            "or run the suite inside the engine image, where it is guaranteed.",
            pytrace=False,
        )
    pytest.skip(_no_souffle(settings))


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
        database_url="sqlite+aiosqlite:///:memory:",
        database_auto_create=True,
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
        _require_or_skip(settings)
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
        _require_or_skip(settings)
    return p


@pytest.fixture
async def database(settings) -> Database:
    """An isolated in-memory database with both tables created, disposed afterwards.

    For the tests that drive the store directly rather than through HTTP. It is not the singleton:
    it is handed to `ProposalStore(database)` explicitly, so nothing global is touched and a
    failure here cannot leak into a test that uses `client`.
    """
    db = Database(settings)
    await db.create_all()
    try:
        yield db
    finally:
        await db.dispose()


@pytest.fixture
async def store(database) -> ProposalStore:
    return ProposalStore(database)


@pytest.fixture
def client():
    """A TestClient over the real app, with the shared singletons rebuilt for each test.

    Carries `X-Organization-ID` on every request. Without it every proposal and batch call in the
    suite would be a `403`: the header is required, and this fixture stands in for the web tier,
    which sets it from the session's active practice. See `TEST_ORGANIZATION_ID`.

    Resetting is what keeps the proposal-store tests independent of each other. It used to be about
    a process-wide dictionary; it is now about the connection pool. `TestClient.__enter__` runs the
    lifespan, which builds a `Database` and creates the schema, and `__exit__` disposes it — and
    because `DATABASE_URL` is in-memory SQLite, disposing the engine destroys the database. Each
    test therefore starts from an empty `proposals` table without anything having to delete rows.

    The pre-emptive `deps.reset()` is belt and braces: the lifespan's own teardown already ran it,
    but a test that raised inside the `with` block must not hand its pipeline to the next one.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    deps.reset()
    with TestClient(app, headers={ORGANIZATION_ID_HEADER: TEST_ORGANIZATION_ID}) as test_client:
        if not deps.pipeline().souffle.available():
            _require_or_skip(deps.pipeline().settings)
        yield test_client
    deps.reset()


def approve(client, proposal_id: str, by: str = "Dr. Beispiel", note: str = "") -> dict:
    """POST an approval and return the updated proposal, failing loudly if it was refused."""
    response = client.post(
        f"/api/v1/proposals/{proposal_id}/approve", json={"approved_by": by, "note": note}
    )
    assert response.status_code == 200, response.text
    return response.json()


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
