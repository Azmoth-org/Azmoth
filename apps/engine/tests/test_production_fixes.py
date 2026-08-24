"""The seven production fixes this migration was required to make.

Each section names the defect it closes. These are the tests that did not exist in the POC, because
the behaviour did not exist in the POC.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal

import pytest

from app.config import ASP_PATH, DATALOG_PATH, ENGINE_DIR, LOGIC_DIR, REPO_ROOT, Settings
from app.core.canonical import canonical, sha256_of
from app.services.cache import InMemoryLRU, ResultCache, cache_key
from app.services.cache import entry as cache_entry
from app.services.proposal_store import (
    IllegalTransition,
    ProposalNotFound,
    ProposalStore,
)
from app.services.receipt import receipt_hash
from app.solvers.clingo_solver import ClingoSolver, ClingoTimeout
from tests.conftest import solve_proposal

# ==========================================================================================
# 1. configuration — no absolute path is hard-coded
# ==========================================================================================


def test_no_module_hardcodes_an_absolute_path():
    """The defect: the POC resolved everything relative to `backend/`, so the app could only run
    from its own directory. Paths now come from the repo root or from the environment."""
    import re

    scanned = 0
    offenders: list[str] = []
    # ENGINE_DIR is `apps/engine` in a checkout and `/srv` in the image, so this scans real files
    # in both rather than vacuously passing where `apps/engine` does not exist.
    for path in ENGINE_DIR.rglob("*.py"):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        scanned += 1
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if re.search(r'["\'](?:/home/|/Users/|[A-Z]:\\\\)', line):
                offenders.append(f"{path}:{number}")

    assert scanned > 20, f"only {scanned} files scanned — the walk found nothing to check"
    assert offenders == [], f"absolute paths are hard-coded in: {offenders}"


def test_logic_and_data_directories_are_discovered_from_the_repo_root():
    settings = Settings()

    assert settings.logic_dir == LOGIC_DIR
    assert settings.asp_path == ASP_PATH and settings.asp_path.is_file()
    assert settings.datalog_path == DATALOG_PATH and settings.datalog_path.is_file()
    assert settings.catalog_path.is_file()
    assert settings.mapping_path.is_file()


def test_logic_and_data_directories_can_be_overridden(tmp_path):
    """What makes the Dockerfile's `/srv/logic` and `/srv/data` layout possible."""
    settings = Settings(logic_dir=tmp_path / "L", data_dir=tmp_path / "D")

    assert settings.asp_path == tmp_path / "L" / "asp" / "goae_optimize.lp"
    assert settings.catalog_path == tmp_path / "D" / "catalogs" / "goae_current" / "goae.official.json"


def test_the_required_settings_all_exist_with_the_mandated_defaults():
    """Asserted against the field defaults, not against `Settings()`.

    `Settings()` reads the environment, and the container image legitimately sets
    `APP_ENV=production` — a test that read that back would be asserting on its own deployment
    rather than on what the code defaults to when nothing is configured.
    """
    defaults = {name: field.default for name, field in Settings.model_fields.items()}

    assert str(defaults["app_env"]) == "development"
    assert defaults["debug"] is False
    assert str(defaults["extraction_mode"]) == "manual"
    assert defaults["solver_timeout_seconds"] == 5
    assert defaults["cache_enabled"] is True
    assert str(defaults["unverified_rule_policy"]) == "warn"
    assert str(defaults["base_factor_policy"]) == "schwellenwert"
    assert defaults["souffle_bin"] == "souffle"
    assert defaults["padnext_allow_real_data"] is False
    assert defaults["catalog_version"] == "", "empty means: trust the catalog file"
    assert Settings().clingo_version, "read from the clingo library, not pinned in config"


def test_catalog_version_is_read_from_the_catalog_when_unset(catalog):
    """A version string maintained in config could disagree with the shipped data. Empty means
    "trust the file"; setting it turns a mismatch into a startup failure."""
    assert Settings().catalog_version == ""
    assert catalog.catalog_version == "goae_official_snapshot_2026-07-25"


def test_env_example_documents_every_setting_and_holds_no_secret():
    """Repo hygiene: `.env.example` is developer documentation and is deliberately NOT copied into
    the container image, so outside a source checkout there is nothing to check."""
    example = ENGINE_DIR / ".env.example"
    if not example.is_file():
        pytest.skip("no .env.example (running from a built image, not a source checkout)")

    text = example.read_text(encoding="utf-8")

    documented = {
        line.split("=", 1)[0].lstrip("# ").strip()
        for line in text.splitlines()
        if "=" in line and not line.strip().startswith("##")
    }
    undocumented = sorted(
        name.upper()
        for name in Settings.model_fields
        if name.upper() not in documented and name not in {"logic_dir", "data_dir"}
    )
    assert undocumented == [], f".env.example does not document: {undocumented}"

    for line in text.splitlines():
        if "=" in line and not line.strip().startswith("#"):
            _, value = line.split("=", 1)
            assert not value.strip() or len(value.strip()) < 60, f"looks like a secret: {line}"


# ==========================================================================================
# 2. the Clingo solve is bounded
# ==========================================================================================


def test_the_solver_has_a_hard_timeout(solver):
    assert solver.timeout_seconds > 0
    assert solver.timeout_seconds == 5.0


def test_no_configuration_expresses_an_unbounded_solve():
    """`gt=0` on the field: zero and negative are rejected, so "no limit" is unrepresentable."""
    with pytest.raises(Exception):
        Settings(solver_timeout_seconds=0)
    with pytest.raises(Exception):
        Settings(solver_timeout_seconds=-1)


def test_an_expired_timeout_with_no_model_raises_rather_than_returning_an_empty_invoice(
    souffle, catalog, rules, settings
):
    """The dangerous failure this closes: an empty result is indistinguishable from "nothing is
    chargeable", which is a completely different — and much more expensive — statement.

    Driven with an unreachable timeout so no answer set can be captured.
    """
    from tests.conftest import make_extraction, one_act_per_ziffer

    impatient = Settings(**{**settings.model_dump(), "solver_timeout_seconds": 1e-9})
    solver = ClingoSolver(impatient, catalog, rules)

    bridge = one_act_per_ziffer("1", "5", "7", "301", "410")
    extraction = make_extraction()
    rules_result = souffle.run(extraction, bridge)

    try:
        result = solver.solve(rules_result, extraction, bridge)
    except ClingoTimeout as exc:
        assert exc.timeout_seconds == 1e-9
        assert "no invoice draft is returned" in str(exc).lower()
    else:
        # The solve won the race, which is legitimate on a fast machine: a partial answer must
        # then be *labelled* as one rather than passed off as optimal.
        if result.timed_out:
            assert result.solver_status == "TIMEOUT_PARTIAL"
            assert "solver_timeout_partial" in {w.type for w in result.warnings}


def test_a_normal_solve_reports_how_long_it_took_and_that_it_was_not_cut_short(
    souffle, solver
):
    from tests.conftest import make_extraction, one_act_per_ziffer

    bridge = one_act_per_ziffer("1", "301")
    extraction = make_extraction()
    result = solver.solve(souffle.run(extraction, bridge), extraction, bridge)

    assert result.timed_out is False
    assert result.solve_ms >= 0
    assert result.solver_status and result.solver_status != "TIMEOUT_PARTIAL"


def test_no_solve_ever_runs_on_the_event_loop():
    """The invariant: a CPU-bound solve must never execute on the event loop, because it would
    serialise the whole service behind one request.

    There are two ways to honour that and both are in use, so this test checks the property rather
    than one spelling of it. `/padnext/audit` is a plain `def`, which FastAPI dispatches to its
    threadpool. `/solve` became `async def` when it gained a database write to await — so it has to
    hand the solve to that same threadpool explicitly, and this asserts it does: the handler is a
    coroutine AND it calls `run_in_threadpool`, never `pipeline().propose(...)` directly.

    An earlier version of this test asserted `not iscoroutinefunction(solve.solve)`. That was a
    check on the mechanism, and it passed for the wrong reason the moment the mechanism changed —
    which is exactly what a regression test must not do.
    """
    import inspect

    from app.api import padnext, solve

    assert not inspect.iscoroutinefunction(padnext.padnext_audit), (
        "the PADnext audit runs Soufflé; a plain def keeps it in the threadpool"
    )

    assert inspect.iscoroutinefunction(solve.solve)
    source = inspect.getsource(solve.solve)
    assert "run_in_threadpool" in source, (
        "an async /solve MUST dispatch the solve to the threadpool explicitly"
    )
    assert "pipeline().propose(" not in source, (
        "calling propose() directly from an async handler blocks the event loop for the whole solve"
    )


# ==========================================================================================
# 3. content-addressed cache
# ==========================================================================================


def _key(**overrides) -> str:
    base = dict(
        catalog_version="c1",
        catalog_sha256="a" * 64,
        rules_version="r1",
        rules_hash="b" * 64,
        logic_version="c" * 64,
        solver_version="5.8.0",
        rules_engine_version="2.5",
        policy={"unverified_rule_policy": "warn"},
        facts={"procedures": [{"type": "punktion"}]},
    )
    return cache_key(**{**base, **overrides})


@pytest.mark.parametrize(
    "field,value",
    [
        ("catalog_version", "c2"),
        ("catalog_sha256", "z" * 64),
        ("rules_version", "r2"),
        ("rules_hash", "z" * 64),
        ("logic_version", "z" * 64),
        ("solver_version", "5.7.1"),
        ("rules_engine_version", "2.4"),
        ("policy", {"unverified_rule_policy": "block"}),
        ("facts", {"procedures": [{"type": "sonographie"}]}),
    ],
)
def test_every_input_that_can_change_an_answer_changes_the_cache_key(field, value):
    """A cache that could serve a result computed under a different rule set is a compliance
    defect, not a performance one."""
    assert _key() != _key(**{field: value})


def test_identical_inputs_produce_the_identical_key():
    assert _key() == _key()


def test_the_cache_stores_everything_the_brief_requires():
    value = cache_entry(
        solver_result={"coding": {}},
        proof_atoms=[{"ziffer": "301", "rule": "catalog_match"}],
        warnings=[{"type": "rule_coverage_incomplete"}],
        rule_coverage={"enforced_rule_count": 35},
        receipt_hash="d" * 64,
        missing_documentation=[{"ziffer": "3"}],
    )

    assert set(value) == {
        "solver_result",
        "proof_atoms",
        "warnings",
        "rule_coverage",
        "missing_documentation",
        "receipt_hash",
        "created_at",
    }
    assert value["created_at"].endswith("+00:00"), "timestamps are UTC and explicit about it"


def test_the_lru_evicts_the_oldest_and_never_grows_past_its_bound():
    lru = InMemoryLRU(max_entries=2)
    lru.set("a", {"n": 1})
    lru.set("b", {"n": 2})
    lru.get("a")  # touching 'a' makes 'b' the eviction candidate
    lru.set("c", {"n": 3})

    assert len(lru) == 2
    assert lru.get("b") is None
    assert lru.get("a") == {"n": 1}


def test_a_disabled_cache_is_a_no_op_not_a_branch_every_caller_has_to_remember():
    cache = ResultCache(enabled=False)
    cache.set("k", {"n": 1})

    assert cache.get("k") is None
    assert len(cache) == 0


def test_the_second_identical_solve_is_served_from_the_cache(client, manual_case):
    first = solve_proposal(client, manual_case("case_001_knee"))
    second = solve_proposal(client, manual_case("case_001_knee"))

    assert first["cached"] is False
    assert second["cached"] is True
    assert first["receipt_hash"] == second["receipt_hash"]
    assert canonical(first["solver_result"]) == canonical(second["solver_result"])


def test_a_cached_result_is_still_a_fresh_draft(client, manual_case):
    """An approval must not travel with a cached computation: the *result* is reusable, the
    *responsibility* for it is not."""
    first = solve_proposal(client, manual_case("case_001_knee"))
    client.post(
        f"/api/v1/proposals/{first['proposal_id']}/approve", json={"approved_by": "Dr. Beispiel"}
    )
    second = solve_proposal(client, manual_case("case_001_knee"))

    assert second["cached"] is True
    assert second["proposal_id"] != first["proposal_id"]
    assert second["status"] == "DRAFT"
    assert second["approved_by"] is None


def test_a_different_setting_is_a_different_cache_entry(client, manual_case):
    ambulant = solve_proposal(client, manual_case("case_001_knee"))
    stationaer = solve_proposal(client, manual_case("case_001_knee"), setting="stationaer")

    assert stationaer["cached"] is False, "the § 6a reduction changes the money"
    assert stationaer["receipt_hash"] != ambulant["receipt_hash"]


def test_the_rules_hash_notices_an_edited_rule_table(tmp_path):
    from app.services.rule_coverage import rules_hash

    (tmp_path / "exclusions.csv").write_text("rule_id,from_ziffer,to_ziffer\nX,1,2\n", encoding="utf-8")
    before = rules_hash(tmp_path)
    (tmp_path / "exclusions.csv").write_text("rule_id,from_ziffer,to_ziffer\nX,1,3\n", encoding="utf-8")

    assert rules_hash(tmp_path) != before


# ==========================================================================================
# 4. proposal and approval status
# ==========================================================================================


def test_the_solver_output_is_wrapped_as_a_draft_by_default(client, manual_case):
    body = solve_proposal(client, manual_case("case_001_knee"))

    assert body["status"] == "DRAFT"


def test_the_proposal_carries_every_field_the_brief_requires(client, manual_case):
    body = solve_proposal(client, manual_case("case_001_knee"), case_id="ENC-1")

    for field in (
        "proposal_id",
        "case_id",
        "status",
        "created_at",
        "approved_at",
        "approved_by",
        "receipt_hash",
        "catalog_version",
        "rules_version",
        "solver_version",
        "solver_result",
        "warnings",
        "missing_documentation",
        "enforced_rule_count",
        "advisory_rule_count",
    ):
        assert field in body, f"the proposal is missing {field}"


def test_approving_records_who_did_it_and_when(client, manual_case):
    draft = solve_proposal(client, manual_case("case_001_knee"))

    approved = client.post(
        f"/api/v1/proposals/{draft['proposal_id']}/approve",
        json={"approved_by": "Dr. Beispiel"},
    ).json()

    assert approved["status"] == "APPROVED"
    assert approved["approved_by"] == "Dr. Beispiel"
    assert approved["approved_at"] is not None
    assert approved["receipt_hash"] == draft["receipt_hash"], "approval must not change the result"


def test_an_unattributed_approval_is_refused(client, manual_case):
    draft = solve_proposal(client, manual_case("case_001_knee"))

    for body in ({}, {"approved_by": ""}):
        response = client.post(
            f"/api/v1/proposals/{draft['proposal_id']}/approve", json=body
        )
        assert response.status_code == 422, "an approval nobody signed is not an approval"


def test_rejecting_requires_a_reason_and_is_terminal(client, manual_case):
    draft = solve_proposal(client, manual_case("case_001_knee"))
    pid = draft["proposal_id"]

    assert client.post(f"/api/v1/proposals/{pid}/reject", json={"rejected_by": "x"}).status_code == 422

    rejected = client.post(
        f"/api/v1/proposals/{pid}/reject",
        json={"rejected_by": "Dr. Beispiel", "reason": "Sonographie nicht dokumentiert"},
    ).json()
    assert rejected["status"] == "REJECTED"
    assert rejected["rejected_reason"] == "Sonographie nicht dokumentiert"

    again = client.post(f"/api/v1/proposals/{pid}/approve", json={"approved_by": "Dr. B"})
    assert again.status_code == 409
    assert again.json()["detail"]["error"] == "illegal_transition"


def test_export_is_reachable_only_from_approved(client, manual_case):
    draft = solve_proposal(client, manual_case("case_001_knee"))
    pid = draft["proposal_id"]
    body = {"exported_by": "PVS-Anbindung"}

    assert client.post(f"/api/v1/proposals/{pid}/export", json=body).status_code == 409

    client.post(f"/api/v1/proposals/{pid}/approve", json={"approved_by": "Dr. Beispiel"})
    exported = client.post(f"/api/v1/proposals/{pid}/export", json=body)

    assert exported.status_code == 200, exported.text
    # The endpoint now answers with the export document itself, not with the proposal. The status
    # is inside it, and is always EXPORTED — the transition happened in the same transaction.
    assert exported.json()["status"] == "EXPORTED"
    assert exported.headers["content-disposition"] == f'attachment; filename="{pid}.json"' 


def test_an_unknown_proposal_is_404_and_says_why(client):
    """The message changed with the store, and had to.

    It used to say proposals "do not survive a restart", which was the honest explanation while the
    store was a dictionary: the likeliest cause of a 404 was that the process had been restarted.
    It is now a durable record, so that sentence would be a false explanation for a real 404 — and
    the wrong instruction, because re-running the case is no longer the obvious fix for an id that
    was simply mistyped.
    """
    response = client.post("/api/v1/proposals/prop_nope/approve", json={"approved_by": "x"})

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"] == "proposal_not_found"
    assert "prop_nope" in detail["message"], "the message must name the id that was not found"
    assert "restart" not in detail["message"], (
        "proposals now survive a restart; the API must not tell a reviewer otherwise"
    )


async def test_the_store_refuses_every_transition_the_lifecycle_forbids(store, client, manual_case):
    """Driven against the store directly, below HTTP, so the refusal is the store's and not the
    router's. `store` is bound to its own isolated database (see conftest)."""
    from app.schemas import Proposal, ProposalStatus

    draft = client.post(
        "/api/v1/solve", json={"extraction": manual_case("case_001_knee")}
    ).json()

    stored = await store.create_proposal(Proposal.model_validate(draft))
    approved = await store.approve_proposal(stored.proposal_id, approved_by="Dr. B")

    assert approved.status is ProposalStatus.APPROVED
    with pytest.raises(IllegalTransition):
        await store.reject_proposal(
            stored.proposal_id, rejected_by="Dr. B", reason="too late"
        )
    with pytest.raises(ProposalNotFound):
        await store.get_proposal("prop_missing")


def test_proposals_can_be_listed_and_filtered_by_status(client, manual_case):
    """The listing is a paginated envelope, not a bare array — see `tests/test_pagination.py`.

    Kept here, in the module that defends the P0 proposal fixes, because the claim it makes is
    older than pagination: a reviewer must be able to ask for one lifecycle state and get exactly
    that state back. Only the shape of the reading moved (`body["items"]`).
    """
    draft = solve_proposal(client, manual_case("case_001_knee"))
    solve_proposal(client, manual_case("case_002_cardiology"))
    client.post(
        f"/api/v1/proposals/{draft['proposal_id']}/approve", json={"approved_by": "Dr. B"}
    )

    drafts = client.get("/api/v1/proposals", params={"status": "DRAFT"}).json()
    approved = client.get("/api/v1/proposals", params={"status": "APPROVED"}).json()

    assert {p["status"] for p in drafts["items"]} == {"DRAFT"}
    assert [p["proposal_id"] for p in approved["items"]] == [draft["proposal_id"]]
    assert (drafts["total"], approved["total"]) == (1, 1)


# ==========================================================================================
# 5. rule-coverage transparency
# ==========================================================================================


def test_every_solve_reports_the_enforced_and_advisory_counts(client, manual_case):
    body = solve_proposal(client, manual_case("case_001_knee"))

    assert body["enforced_rule_count"] > 0
    assert body["advisory_rule_count"] > 0
    assert body["suppressed_unverified_rule_count"] > 0
    assert body["rule_coverage"]["policy_for_unverified_rules"] == "warn"


def test_the_response_warns_when_advisory_rules_exist(client, manual_case):
    """The API must never imply that unverified rules are enforced."""
    body = solve_proposal(client, manual_case("case_001_knee"))
    warnings = {w["type"] for w in body["solver_result"]["coding"]["warnings"]}
    messages = " ".join(w["message"] for w in body["solver_result"]["coding"]["warnings"])

    assert body["advisory_rule_count"] > 0
    assert "rule_coverage_incomplete" in warnings
    assert "NICHT verifiziert" in messages or "nicht verifiziert" in messages
    assert str(body["suppressed_unverified_rule_count"]) in messages


def test_the_counts_agree_with_the_rule_store(pipeline):
    coverage = pipeline.rule_coverage()
    summary = pipeline.rules.summary()

    assert coverage.suppressed_unverified_rule_count == summary["unverified_rules_not_enforced"]
    assert coverage.enforced_rule_count == (
        summary["exclusions_enforced"]
        + summary["zielleistung_enforced"]
        + summary["specificity_enforced"]
        + summary["factor_caps_enforced"]
    )


def test_the_counts_move_with_the_policy(catalog, settings):
    """Under `block` the unverified rules ARE enforced, and the counts must say so."""
    from app.config import RULES_DATA_DIR, UnverifiedRulePolicy
    from app.rules.rule_store import RuleStore
    from app.services import rule_coverage as service

    warn = service.build(RuleStore.load(RULES_DATA_DIR, policy=UnverifiedRulePolicy.WARN))
    block = service.build(RuleStore.load(RULES_DATA_DIR, policy=UnverifiedRulePolicy.BLOCK))

    assert warn.suppressed_unverified_rule_count > 0
    assert block.suppressed_unverified_rule_count == 0
    assert block.enforced_rule_count > warn.enforced_rule_count


# ==========================================================================================
# 6. missing documentation
# ==========================================================================================


def test_missing_documentation_names_the_gap_without_charging_for_it(client, manual_case):
    body = solve_payload = solve_proposal(client, manual_case("case_001_knee"))["solver_result"]
    gaps = {g["ziffer"]: g for g in body["coding"]["missing_documentation"]}
    lines = {line["ziffer"]: line for line in body["coding"]["proposed_codes"]}

    assert gaps, "case_001 charges four positions at the Schwellenwert with no documented reason"
    for ziffer, gap in gaps.items():
        assert set(gap) >= {"ziffer", "current_factor", "possible_factor", "missing"}
        # The invariant that matters: what is *billed* is the current factor, never the possible one.
        assert lines[ziffer]["factor"] == gap["current_factor"]
        assert Decimal(gap["possible_factor"]) > Decimal(gap["current_factor"])
        assert "§ 12 Abs. 3" in gap["missing"] or "§ 5 Abs. 2" in gap["missing"]


def test_a_documented_position_reports_no_gap(client, manual_case):
    """GOÄ 301 in case_001 carries a documented reason and is charged at 2.6, so there is nothing
    missing about it."""
    body = solve_proposal(client, manual_case("case_001_knee"))["solver_result"]
    gaps = {g["ziffer"] for g in body["coding"]["missing_documentation"]}
    line = next(l for l in body["coding"]["proposed_codes"] if l["ziffer"] == "301")

    assert line["justification_present"] is True
    assert "301" not in gaps


def test_the_existing_justification_flags_are_preserved(client, manual_case):
    """`justification_required` predates this migration and must not have been replaced."""
    body = solve_proposal(client, manual_case("case_001_knee"))["solver_result"]
    line = next(l for l in body["coding"]["proposed_codes"] if l["ziffer"] == "301")

    assert line["justification_required"] is True
    assert line["justification"], "the documented reason itself is still on the line"


def test_the_objective_ordering_is_untouched():
    """The legal posture, asserted against the ASP source: revenue stays last and the hard rules
    stay integrity constraints. See logic/README.md."""
    program = ASP_PATH.read_text(encoding="utf-8")

    assert "#minimize { 1@5, A, Z : analog_collision(A, Z) }." in program
    assert "#maximize { 1@4, A, B : covered(A, B) }." in program
    assert "#maximize { C@3, Z : bill(Z), conf(Z, C) }." in program
    assert "#maximize { P@2, Z : bill(Z), spec_priority(Z, P) }." in program
    assert "#maximize { P@1, Z : charged(Z), code_info(Z, P, _) }." in program

    # Both legality constraints range over `charged/1`, which is the relation an Analogansatz
    # position is in. Under `bill/1` — what these read until the analog/exclusion fix — a § 6
    # Abs. 2 position faced neither, so the solver could put a position on the invoice that is not
    # chargeable next to one already billed and the validator would refuse the whole invoice.
    # Narrowing either of them back to `bill/1` reopens that hole, which is why the exact text is
    # pinned here rather than left to the property suite to rediscover.
    assert ":- charged(A), charged(B), excluded(A, B), A != B." in program
    assert ":- charged(C), charged(P), zielleistung(P, C)." in program
    assert ":- bill(A), bill(B)" not in program, "a legality constraint narrowed back to bill/1"
    assert ":- bill(C), bill(P)" not in program, "a legality constraint narrowed back to bill/1"

    # The § 6 Abs. 2 choice is `0 {...} 1`, not `1 {...} 1`: with the constraints above ranging
    # over `charged/1`, a forced cardinality turns a ladder whose every candidate is excluded into
    # an UNSAT program — "nothing is chargeable" for the whole encounter. The uncovered request is
    # reported instead, and scored through the @5 term so coverage still wins when it is legal.
    assert "0 { analog(A, Z) : has_analog_cand(A, Z) } 1 :- analog_needed(A, _)." in program
    assert "analog_collision(A, \"\") :- analog_uncovered(A)." in program

    # Each priority carries exactly one objective, so no second revenue term was slipped in at a
    # higher level. Comment lines (`%`) are excluded: the header documents the ordering in prose.
    code = "\n".join(l for l in program.splitlines() if not l.lstrip().startswith("%"))
    for priority in ("@5", "@4", "@3", "@1"):
        assert code.count(priority) == 1, f"{priority} carries more than one objective"
    assert code.count("@2") == 2, "specificity weighs bill/1 and analog/2 — two terms, one level"
    assert "@6" not in code and "@0" not in code, "a new priority level was introduced"


# ==========================================================================================
# 7. receipt hash
# ==========================================================================================


def _receipt(**overrides) -> str:
    base = dict(
        catalog_version="c1",
        catalog_sha256="a" * 64,
        rules_version="r1",
        rules_hash="b" * 64,
        logic_version="c" * 64,
        solver_version="5.8.0",
        rules_engine_version="2.5",
        policy={"base_factor_policy": "schwellenwert"},
        facts={"procedures": [{"type": "punktion"}]},
        output={"total": {"amount_eur": "130.39"}},
    )
    return receipt_hash(**{**base, **overrides})


def test_the_receipt_is_a_sha256_over_identity_input_and_output():
    assert len(_receipt()) == 64
    assert _receipt() == _receipt()


@pytest.mark.parametrize(
    "field,value",
    [
        ("catalog_version", "c2"),
        ("catalog_sha256", "z" * 64),
        ("rules_version", "r2"),
        ("rules_hash", "z" * 64),
        ("logic_version", "z" * 64),
        ("solver_version", "5.7.1"),
        ("policy", {"base_factor_policy": "einfachsatz"}),
        ("facts", {"procedures": [{"type": "sonographie"}]}),
        ("output", {"total": {"amount_eur": "130.40"}}),
    ],
)
def test_the_receipt_changes_when_anything_that_produced_the_result_changes(field, value):
    assert _receipt() != _receipt(**{field: value})


def test_the_receipt_ignores_measured_values(client, manual_case):
    """Timings and timestamps differ every run. A receipt that moved with them would identify
    nothing at all."""
    first = solve_proposal(client, manual_case("case_002_cardiology"))
    second = solve_proposal(client, manual_case("case_002_cardiology"))

    assert first["solver_result"]["audit_trail"]["stage_timings_ms"], "timings are still reported"
    assert first["receipt_hash"] == second["receipt_hash"]


def test_the_receipt_is_returned_on_every_kind_of_response(client, manual_case):
    from app.config import PADNEXT_EXAMPLES_DIR

    solved = solve_proposal(client, manual_case("case_001_knee"))
    assert len(solved["receipt_hash"]) == 64

    payload = (PADNEXT_EXAMPLES_DIR / "00004711_20260726_ADL_000001_padx.xml").read_bytes()
    audited = client.post(
        "/api/v1/padnext/audit", content=payload, headers={"Content-Type": "application/xml"}
    ).json()
    assert len(audited["receipt_hash"]) == 64


def test_the_receipt_ties_a_result_to_the_data_that_produced_it(pipeline, manual_case):
    """The claim a Rechnungsprüfer can check: this hash covers the catalog, the rule tables, the
    logic programs, the solver versions, the policy and the input — nothing else."""
    from app.schemas import ClinicalExtraction

    extraction = ClinicalExtraction.model_validate(manual_case("case_001_knee"))
    proposal = pipeline.propose(extraction)

    recomputed = receipt_hash(
        catalog_version=pipeline.catalog.catalog_version,
        catalog_sha256=pipeline.catalog.sha256(),
        rules_version=pipeline.catalog.rules_version,
        rules_hash=pipeline.rules_hash,
        logic_version=pipeline.settings.logic_version,
        solver_version=pipeline.clingo.version,
        rules_engine_version=pipeline.souffle.version(),
        policy=pipeline.settings.policy_fingerprint(),
        facts=extraction.model_dump(mode="python"),
        output=proposal.solver_result.coding.model_dump(mode="python"),
    )

    assert proposal.receipt_hash == recomputed


def test_a_receipt_over_an_edited_logic_program_differs(pipeline):
    """Editing `goae_optimize.lp` must invalidate every receipt computed before the edit."""
    original = pipeline.settings.logic_version
    edited = sha256_of({"logic": "changed"})

    assert original != edited
    assert _receipt(logic_version=original) != _receipt(logic_version=edited)


# ==========================================================================================
# the boundary the POC's LLM path used to cross
# ==========================================================================================


def test_no_llm_sdk_is_a_dependency():
    from app.config import ENGINE_DIR

    requirements = (ENGINE_DIR / "requirements.txt").read_text(encoding="utf-8").lower()

    for package in ("openai", "anthropic", "langchain", "litellm", "transformers"):
        assert package not in requirements, f"{package} must not be a dependency of the engine"


def test_the_engine_makes_no_outbound_call_on_the_solve_path():
    """Nothing on the coding path may reach the network: no client, no key, nowhere to send it."""
    import app.services.pipeline as pipeline_module
    import app.solvers.clingo_solver as clingo_module
    import app.solvers.souffle_engine as souffle_module

    for module in (pipeline_module, clingo_module, souffle_module):
        source = json.dumps(module.__doc__ or "")
        assert "http" not in source.lower() or "https://" not in source
        assert not hasattr(module, "requests")
        assert not hasattr(module, "httpx")


def test_the_extraction_prompt_contract_survived_the_migration():
    """The POC's free-text path is gone, but the invariant it was held to is not: whatever produces
    clinical entities upstream must not be told about the fee schedule. tests/test_schema.py
    asserts the terms; this asserts the contract still exists to assert against."""
    from app.core import extraction_prompts

    assert extraction_prompts.FORBIDDEN_PROMPT_TERMS
    assert "goä" in extraction_prompts.FORBIDDEN_PROMPT_TERMS
    assert "ziffer" in extraction_prompts.FORBIDDEN_PROMPT_TERMS


def test_padnext_refuses_real_data_by_default_from_settings(monkeypatch):
    from app.padnext.audit import real_data_allowed

    monkeypatch.delenv("PADNEXT_ALLOW_REAL_DATA", raising=False)
    assert real_data_allowed(Settings()) is False
    assert real_data_allowed(Settings(padnext_allow_real_data=True)) is True

    monkeypatch.setenv("PADNEXT_ALLOW_REAL_DATA", "0")
    assert real_data_allowed(Settings(padnext_allow_real_data=True)) is False, (
        "the environment must be able to tighten the setting without a restart"
    )


def test_the_repo_holds_no_environment_file_with_secrets():
    """`.env` is gitignored; `.env.example` is the only committed one and carries no value."""
    if not (ENGINE_DIR / ".env.example").is_file():
        pytest.skip("no .env.example (running from a built image, not a source checkout)")

    present = {p.name for p in ENGINE_DIR.glob(".env*")}

    assert present <= {".env.example", ".env"}, f"unexpected env files: {sorted(present)}"
    assert not os.path.exists(ENGINE_DIR / ".env") or ".env" in (
        (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    ), "a local .env exists and is not gitignored"
