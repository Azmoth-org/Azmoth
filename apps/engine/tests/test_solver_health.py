"""`/health` proves the solvers work, rather than reporting that they are installed.

The endpoint used to answer two questions: does `souffle` resolve on `PATH`, and what does
`clingo.__version__` say. Both are true of a container in which nothing can be solved — a binary
with a broken dynamic link resolves and dies on `exec`, and the Python `clingo` wheel imports and
reports a version whether or not its native grounder can ground anything. Each of those presented as
`status: "ok"` and then failed on the first coding request, which is the worst moment to find out.

So each solver is now handed a trivial program and has to produce the right answer. These tests pin
what that is worth:

**A probe that solves is `ok`, with a time.** Both engines, through the real code path — Clingo
grounded and solved in-process, Soufflé through an actual subprocess.

**A probe that cannot run is `unavailable`, not a crash.** A health endpoint that raises when a
dependency is missing tells an orchestrator nothing except that the process is up, which is the one
thing it could already see.

**A solver that is present and wrong is `failed`, and degrades the service.** This is the case the
old check could not see at all, and the reason the module exists.

**The overall `status` stays `ok` / `degraded`.** The Docker healthcheck tests `status == "ok"` and
the dashboard branches on the same pair, so the two literals are a contract. `solvers` is where the
new detail went, precisely so nothing already reading this had to change.

**The probes are cached.** The Soufflé probe spawns a process; a page that renders the health card
twice must not spawn two.
"""

from __future__ import annotations

import pytest

from app.api import deps
from app.config import Settings
from app.services.solver_probe import (
    PROBE_TTL_SECONDS,
    SolverProbe,
    probe_clingo,
    probe_solvers,
    probe_souffle,
    reset_probe_cache,
)


@pytest.fixture(autouse=True)
def _clean_probe_cache():
    """Every test here starts and ends with an empty cache.

    Autouse, because the cache is process-wide: a test that asserted on a *missing* binary would
    otherwise poison the next one for `PROBE_TTL_SECONDS`, and the failure would look like a flake
    that depends on how fast the suite runs.
    """
    reset_probe_cache()
    yield
    reset_probe_cache()


# ==========================================================================================
# a probe that solves
# ==========================================================================================


def test_the_clingo_probe_grounds_and_solves(settings):
    """In-process, through `Control` → `add` → `ground` → `solve` — the sequence a real solve uses.

    A version string proves none of that, which is exactly why this exists.
    """
    probe = probe_clingo(settings)

    assert probe.status == "ok", probe.detail
    assert probe.version, "a probe that solved should be able to say which version did"
    assert probe.probe_time_ms > 0, "a duration of exactly zero means it was not measured"
    assert probe.detail == "", "detail is for explaining a failure"


def test_the_souffle_probe_runs_the_binary_and_reads_its_output(settings, souffle):
    """`souffle` is the fixture that skips this on a machine without the binary.

    The probe writes a two-line Datalog program, runs it and reads back the relation it printed. All
    three steps matter: a `--version` call would prove the process starts, and would not prove the
    interpreter evaluates.
    """
    probe = probe_souffle(settings)

    assert probe.status == "ok", probe.detail
    assert probe.probe_time_ms > 0


def test_probe_solvers_reports_both_under_their_names(settings, souffle):
    probes = probe_solvers(settings, force=True)

    assert set(probes) == {"clingo", "souffle"}
    assert all(probe.ok for probe in probes.values()), probes


# ==========================================================================================
# a probe that cannot run
# ==========================================================================================


def test_a_missing_souffle_binary_is_unavailable_rather_than_an_exception(settings):
    """`unavailable`, with a sentence naming the variable to set. Never a raised exception.

    A health endpoint that throws when a dependency is missing reports only that the process is up,
    which is the one fact an orchestrator could already see for itself.
    """
    absent = settings.model_copy(update={"souffle_bin": "souffle-that-is-not-installed"})

    probe = probe_souffle(absent)

    assert probe.status == "unavailable"
    assert "souffle-that-is-not-installed" in probe.detail
    assert "SOUFFLE_BIN" in probe.detail, "the detail has to say what to do about it"


def test_a_binary_that_exits_non_zero_is_failed_not_unavailable(settings, tmp_path):
    """The distinction the old availability check could not draw.

    `unavailable` is "not installed here" — a deployment built wrong. `failed` is "installed and it
    does not work", which is a different problem with a different fix, and the one most worth
    waking somebody for. A shell script that resolves on `PATH` and exits 1 is exactly the shape of
    a Soufflé with a broken dynamic link.
    """
    broken = tmp_path / "souffle"
    broken.write_text("#!/bin/sh\necho 'cannot load shared libraries' >&2\nexit 127\n")
    broken.chmod(0o755)

    probe = probe_souffle(settings.model_copy(update={"souffle_bin": str(broken)}))

    assert probe.status == "failed", probe
    assert "127" in probe.detail
    assert "cannot load shared libraries" in probe.detail


def test_a_binary_that_exits_zero_and_derives_nothing_is_failed(settings, tmp_path):
    """The subtlest failure, and the reason the probe reads the output file at all.

    A `souffle` that exits 0 without evaluating anything passes every check short of looking at what
    it produced. `/solve` would then return "nothing is chargeable" for every encounter — a wrong
    answer rather than an error, which is the worst kind this engine can give.
    """
    silent = tmp_path / "souffle"
    silent.write_text("#!/bin/sh\nexit 0\n")
    silent.chmod(0o755)

    probe = probe_souffle(settings.model_copy(update={"souffle_bin": str(silent)}))

    assert probe.status == "failed", probe
    assert "probe(1)" in probe.detail


# ==========================================================================================
# the caching
# ==========================================================================================


def test_a_second_call_inside_the_ttl_reuses_the_first_result(settings, souffle, monkeypatch):
    """The Soufflé probe spawns a process. A page that renders the health card twice must not.

    Asserted by counting calls rather than by timing, which would be a flaky way to say the same
    thing on a loaded machine.
    """
    calls = {"n": 0}
    real = probe_souffle

    def counted(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr("app.services.solver_probe.probe_souffle", counted)

    probe_solvers(settings)
    probe_solvers(settings)

    assert calls["n"] == 1


def test_force_bypasses_the_cache(settings, souffle, monkeypatch):
    calls = {"n": 0}
    real = probe_souffle

    def counted(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr("app.services.solver_probe.probe_souffle", counted)

    probe_solvers(settings, force=True)
    probe_solvers(settings, force=True)

    assert calls["n"] == 2


def test_the_ttl_is_shorter_than_the_docker_healthcheck_interval():
    """A number with a reason, asserted so the reason survives someone tuning it.

    The healthcheck in `infra/docker/docker-compose.yml` polls every 30 s. A cache that outlived
    that interval would let a supervisor's poll be answered from a page render's cached result — so
    a solver that broke would be reported healthy for a whole cycle, which defeats the point of
    polling at all.
    """
    assert PROBE_TTL_SECONDS < 30


# ==========================================================================================
# the endpoint
# ==========================================================================================


def test_health_reports_a_probe_for_each_solver(client):
    body = client.get("/api/v1/health").json()

    assert set(body["solvers"]) == {"clingo", "souffle"}
    for name, solver in body["solvers"].items():
        assert solver["status"] == "ok", f"{name}: {solver['detail']}"
        assert solver["probe_time_ms"] >= 0
        assert solver["version"], name


def test_the_top_level_status_is_still_ok_and_degraded(client):
    """Not `healthy`. Two committed readers branch on these two literals — the Docker healthcheck
    (`status == "ok"`) and the dashboard's System Health card — so widening the vocabulary would
    break both to gain a synonym."""
    from app.schemas import HealthResponse

    literal = HealthResponse.model_fields["status"].annotation

    assert set(getattr(literal, "__args__", ())) == {"ok", "degraded"}
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_a_failing_solver_degrades_the_service(client, monkeypatch):
    """The widening this change makes to what `degraded` means.

    It used to be "the Soufflé binary is missing". A Soufflé that was present and broken reported
    `ok`, and so did a Clingo that could not ground — even though `/solve` fails just as completely
    for either. Now any solver that is not `ok` degrades the whole answer.
    """
    monkeypatch.setattr(
        "app.api.health.probe_solvers",
        lambda *args, **kwargs: {
            "clingo": SolverProbe(status="ok", probe_time_ms=1.0, version="5.8.0"),
            "souffle": SolverProbe(
                status="failed", probe_time_ms=3.0, detail="exit 127: cannot load shared libraries"
            ),
        },
    )

    body = client.get("/api/v1/health").json()

    assert body["status"] == "degraded"
    assert body["solvers"]["souffle"]["status"] == "failed"
    # And the reason travels, because "degraded" on its own sends an operator to read logs.
    assert "127" in body["solvers"]["souffle"]["detail"]


def test_the_health_endpoint_needs_no_organisation(client):
    """Restated here as well as in `test_tenancy.py`, because it is the property that would be
    broken by someone tidily adding the dependency to every router: the container healthcheck calls
    this, and a tenant requirement would mark every container unhealthy forever."""
    from fastapi.testclient import TestClient

    from app.main import app

    deps.reset()
    with TestClient(app) as unscoped:
        assert unscoped.get("/api/v1/health").status_code == 200
    deps.reset()


def test_the_probe_never_raises_whatever_the_solver_does(settings, monkeypatch):
    """A diagnostic that can take down the endpoint reporting it is worse than no diagnostic.

    `clingo` is a native extension, so the interesting failures arrive from C++ as types this
    codebase has no reason to enumerate — which is why the handler is a bare `except Exception` and
    why that deserves a test rather than a comment.
    """

    def explode(*args, **kwargs):
        raise RuntimeError("the grounder segfaulted, metaphorically")

    monkeypatch.setattr("clingo.Control", explode)

    probe = probe_clingo(settings)

    assert probe.status == "failed"
    assert "grounder segfaulted" in probe.detail


def test_settings_can_be_copied_with_a_different_binary():
    """Guards the mechanism the failure tests above are built on.

    They all work by handing `probe_souffle` a `Settings` with `souffle_bin` pointed at a script. If
    `model_copy` ever stopped producing a usable `Settings`, every one of those tests would pass
    while probing the real binary — a suite that looks green and checks nothing.
    """
    copied = Settings(database_url="sqlite+aiosqlite:///:memory:").model_copy(
        update={"souffle_bin": "/nowhere/souffle"}
    )

    assert copied.souffle_bin == "/nowhere/souffle"
