"""The timing metrics on the response, and the `--stats` breakdown behind them.

Nothing here asserts a millisecond value. A test that pinned one would fail on a loaded CI box and
teach everyone to ignore it; what these assert is that the numbers *exist*, are internally
consistent (a part is never larger than its whole), and — the part that actually matters — that
they are stripped by `app.core.canonical`, so a measurement can never move a receipt hash, a cache
key or a golden snapshot.

The one bound with a real threshold behind it is `solve_time_ms < 1000`, which is the "slow case"
line documented in `docs/performance_baseline.md`. The golden cases measure around 0.5 ms, so this
has three orders of magnitude of headroom and only fires on a genuine regression.
"""

from __future__ import annotations

import importlib.util
import io
from contextlib import redirect_stdout

import pytest

from app.config import CASES_DIR, ENGINE_DIR
from app.core.canonical import VOLATILE_KEYS, canonical, sha256_of
from tests.conftest import solve_proposal

#: The documented "slow case" threshold. See docs/performance_baseline.md § 6.
SLOW_SOLVE_MS = 1000.0

CASE = CASES_DIR / "case_001_knee" / "input.json"


def _cli():
    spec = importlib.util.spec_from_file_location(
        "engine_cli", ENGINE_DIR / "scripts" / "engine_cli.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ==========================================================================================
# the two payload metrics
# ==========================================================================================


def test_the_proposal_reports_solve_and_total_time(client, manual_case):
    proposal = solve_proposal(client, manual_case("case_001_knee"))

    assert proposal["solve_time_ms"] > 0, "a fresh solve must report the search it actually ran"
    assert proposal["total_time_ms"] > 0
    assert proposal["total_time_ms"] >= proposal["solve_time_ms"], (
        "the request cannot be shorter than the search inside it"
    )
    assert proposal["solve_time_ms"] < SLOW_SOLVE_MS, (
        f"case_001 crossed the documented slow threshold of {SLOW_SOLVE_MS} ms — it normally "
        "solves in well under 1 ms, so this is a regression, not a busy machine"
    )


def test_the_proposal_metrics_are_the_audit_trail_metrics(client, manual_case):
    """One fact, one place. The proposal flattens the audit trail's numbers up to the header the
    way it already flattens `solver_status`; a flattened copy that disagreed with its source would
    be worse than not having it."""
    proposal = solve_proposal(client, manual_case("case_001_knee"))
    audit = proposal["solver_result"]["audit_trail"]

    assert audit["solve_time_ms"] > 0
    assert audit["total_time_ms"] >= audit["solve_time_ms"]
    assert proposal["solve_time_ms"] == audit["solve_time_ms"]
    assert proposal["total_time_ms"] == audit["total_time_ms"]


def test_the_metrics_survive_the_database_round_trip(client, manual_case):
    """`POST /solve` returns the row it wrote, not the object in hand. A metric that existed only
    on the way in would read as 0.0 to every client and nobody would notice."""
    created = solve_proposal(client, manual_case("case_001_knee"))

    fetched = client.get(f"/api/v1/proposals/{created['proposal_id']}")
    assert fetched.status_code == 200, fetched.text
    reread = fetched.json()

    assert reread["solve_time_ms"] == created["solve_time_ms"] > 0
    assert reread["total_time_ms"] == created["total_time_ms"] > 0


def test_the_stage_breakdown_separates_grounding_from_search(client, manual_case):
    """`clingo` as one number cannot distinguish a big program from a hard search, and the two
    have opposite remedies. The three sub-stages are what `--stats` and the baseline doc read."""
    audit = solve_proposal(client, manual_case("case_001_knee"))["solver_result"]["audit_trail"]
    stages = audit["stage_timings_ms"]

    for stage in ("bridge", "souffle", "clingo", "souffle_verification", "validation"):
        assert stage in stages, f"the pre-existing stage {stage!r} disappeared"
    for stage in ("clingo_build_facts", "clingo_ground", "clingo_solve"):
        assert stage in stages, f"missing sub-stage {stage!r}"
        assert stages[stage] >= 0

    assert stages["clingo_solve"] == pytest.approx(audit["solve_time_ms"])
    assert stages["clingo"] >= stages["clingo_ground"] + stages["clingo_solve"], (
        "the three sub-stages are measured inside the clingo stage, so they cannot exceed it"
    )


def test_a_cache_hit_repeats_the_timings_of_the_run_it_serves(client, manual_case):
    """The metrics describe the run, not the request. Two proposals served from one cached result
    therefore carry identical timings — and `cached` is what tells a reader the second one did not
    spend them. A monitor that averaged these without reading `cached` would be measuring the
    cache-hit rate, not the engine."""
    case = manual_case("case_001_knee")
    first = solve_proposal(client, case)
    second = solve_proposal(client, case)

    assert first["cached"] is False and second["cached"] is True
    assert second["solve_time_ms"] == first["solve_time_ms"] > 0
    assert second["total_time_ms"] == first["total_time_ms"] > 0


# ==========================================================================================
# the grounding statistics
# ==========================================================================================


def test_clingo_statistics_reach_the_optimization_result(pipeline, manual_case):
    from app.schemas import ClinicalExtraction

    extraction = ClinicalExtraction.model_validate(manual_case("case_001_knee"))
    _coding, _audit, _rules, optimization = pipeline.run_symbolic(extraction)

    grounding = optimization.grounding
    assert grounding is not None, (
        "clingo.Control.statistics returned nothing — if a clingo upgrade renamed a key the "
        "reader degrades to None by design, but then --stats and the baseline doc lose their "
        "grounding numbers and this needs re-wiring, not deleting"
    )
    assert grounding.atoms > 0 and grounding.rules > 0
    assert grounding.rules_minimize > 0, "the five objective levels must be in the ground program"
    assert grounding.fact_lines > 0
    assert grounding.program_bytes > grounding.fact_lines
    assert optimization.ground_ms > 0 and optimization.build_ms >= 0


def test_the_grounding_statistics_are_not_in_the_response(client, manual_case):
    """Diagnostics about how the answer was computed, deliberately not part of the answer. They
    reach the CLI off the solver; a client gets the two timing numbers and nothing else."""
    proposal = solve_proposal(client, manual_case("case_001_knee"))

    assert "grounding" not in proposal
    assert "grounding" not in proposal["solver_result"]["audit_trail"]


# ==========================================================================================
# measurements must never become part of the answer
# ==========================================================================================


def test_the_new_metrics_are_normalised_away():
    assert "solve_time_ms" in VOLATILE_KEYS, "a measurement must not move a receipt hash"
    assert "total_time_ms" in VOLATILE_KEYS
    assert "ground_ms" in VOLATILE_KEYS
    assert "build_ms" in VOLATILE_KEYS


def test_two_runs_that_differ_only_in_timing_are_the_same_result():
    a = {"coding": {"total": {"amount_eur": "130.39"}}, "solve_time_ms": 0.4, "total_time_ms": 77.1}
    b = {"coding": {"total": {"amount_eur": "130.39"}}, "solve_time_ms": 9.9, "total_time_ms": 812.0}

    assert canonical(a) == canonical(b)
    assert sha256_of(a) == sha256_of(b)


def test_the_same_case_solved_twice_keeps_one_receipt(client, manual_case):
    """The end-to-end version of the check above, through the real response shape."""
    case = manual_case("case_001_knee")
    first = solve_proposal(client, case)
    second = solve_proposal(client, dict(case))

    assert first["receipt_hash"] == second["receipt_hash"]
    assert canonical(first["solver_result"]) == canonical(second["solver_result"])


# ==========================================================================================
# the CLI flag
# ==========================================================================================


def test_cli_stats_prints_the_breakdown():
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = _cli().main(["solve", str(CASE), "--stats"])
    out = buffer.getvalue()

    assert code == 0
    for line in (
        "catalog + rules load",
        "input parse + schema validation",
        "clingo ground",
        "clingo solve",
        "solve_time_ms (payload)",
        "total_time_ms (payload, pipeline)",
        "TOTAL end-to-end",
        "ground program (clingo statistics)",
    ):
        assert line in out, f"--stats no longer reports {line!r}"


def test_cli_without_stats_prints_no_breakdown():
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = _cli().main(["solve", str(CASE)])

    assert code == 0
    assert "TIMING" not in buffer.getvalue(), "the breakdown must be opt-in"


def test_cli_stats_composes_with_json():
    """`--json` emits the payload a client would get; `--stats` adds the breakdown after it, so
    piping the JSON out and reading the timings still works."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = _cli().main(["solve", str(CASE), "--json", "--stats"])
    out = buffer.getvalue()

    assert code == 0
    assert '"solve_time_ms"' in out and '"total_time_ms"' in out
    assert out.index('"solve_time_ms"') < out.index("TIMING"), "the JSON must come first"
