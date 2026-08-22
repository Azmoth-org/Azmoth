"""The four contract changes made after the Review UI was built.

Each closed a gap where the frontend had to work around the API: an aggregate it could not
decompose, an implicit join, an open string it could not label exhaustively, and a field buried two
levels below where it is read. None of them changed a billing value — `test_golden_snapshot.py`
enforces that separately, and has no allow-list for changed values.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import RULES_DATA_DIR, UnverifiedRulePolicy
from app.rules.rule_store import RuleStore
from app.schemas.common import FactorBasis
from app.services import rule_coverage as rule_coverage_service
from tests.conftest import solve_payload, solve_proposal

# ==========================================================================================
# 1. the advisory count is decomposable
# ==========================================================================================


def test_advisory_count_splits_into_its_two_components(pipeline):
    """The frontend previously had to hedge its wording, because `advisory_rule_count` lumped two
    different things together and the API exposed no way to tell them apart."""
    coverage = pipeline.rule_coverage()

    assert coverage.analog_candidate_count > 0
    assert coverage.suppressed_unverified_rule_count > 0
    assert (
        coverage.advisory_rule_count
        == coverage.analog_candidate_count + coverage.suppressed_unverified_rule_count
    ), "the advisory total must remain exactly the sum of its published parts"


def test_unverified_count_is_policy_independent_and_suppressed_count_is_not():
    """The distinction the two fields exist for.

    `unverified_rule_count` counts rules no human has checked — a property of the data.
    `suppressed_unverified_rule_count` counts the ones the current policy is holding out of
    enforcement — a property of the configuration. Under `block` they diverge, and a reader who
    conflated them would think switching policy had verified 859 rules.
    """
    warn = rule_coverage_service.build(
        RuleStore.load(RULES_DATA_DIR, policy=UnverifiedRulePolicy.WARN)
    )
    block = rule_coverage_service.build(
        RuleStore.load(RULES_DATA_DIR, policy=UnverifiedRulePolicy.BLOCK)
    )

    assert warn.unverified_rule_count == block.unverified_rule_count > 0, (
        "verification status is a property of the data, not of the policy"
    )
    assert warn.suppressed_unverified_rule_count == warn.unverified_rule_count
    assert block.suppressed_unverified_rule_count == 0
    assert block.enforced_rule_count > warn.enforced_rule_count


def test_analog_candidates_are_never_counted_as_enforced_or_unverified_constraints(rules):
    """An analog candidate is an offer under § 6 Abs. 2 GOÄ. It cannot suppress a position under
    any policy, so it must not appear in either constraint count."""
    coverage = rule_coverage_service.build(rules)

    assert coverage.analog_candidate_count == len(rules.analog_candidates)
    assert coverage.unverified_rule_count == rules.unverified_constraint_rule_count()

    # The analog rows in the shipped data are themselves unverified, so a naive implementation
    # would sweep them into the constraint figure. Proved by construction rather than by
    # arithmetic: strip the analog candidates out and the constraint count must not move.
    unverified_analogs = sum(1 for r in rules.analog_candidates if not r.verified)
    assert unverified_analogs > 0, (
        "the fixtures no longer contain an unverified analog candidate, so this test would pass "
        "vacuously — pick a different witness before trusting it"
    )

    without_analogs = RuleStore(
        policy=rules.policy,
        exclusions=list(rules.exclusions),
        zielleistung=list(rules.zielleistung),
        specificity=list(rules.specificity),
        analog_candidates=[],
        factor_caps=list(rules.factor_caps),
        suppressed=list(rules.suppressed),
        files_loaded=list(rules.files_loaded),
    )
    stripped = rule_coverage_service.build(without_analogs)

    assert stripped.unverified_rule_count == coverage.unverified_rule_count
    assert stripped.enforced_rule_count == coverage.enforced_rule_count
    assert stripped.analog_candidate_count == 0
    assert stripped.advisory_rule_count == coverage.advisory_rule_count - unverified_analogs


def test_the_split_is_published_on_the_proposal_and_the_coverage_object(client, manual_case):
    body = solve_proposal(client, manual_case("case_001_knee"))

    for field in ("unverified_rule_count", "analog_candidate_count"):
        assert field in body, f"the proposal is missing {field}"
        assert body[field] == body["rule_coverage"][field], (
            f"{field} disagrees between the proposal and its rule_coverage object"
        )


def test_the_coverage_warning_names_both_components(pipeline):
    coverage = pipeline.rule_coverage()
    warnings = rule_coverage_service.warnings_for(coverage)

    assert warnings, "advisory rules exist, so a warning must be emitted"
    message = warnings[0].message
    assert str(coverage.suppressed_unverified_rule_count) in message
    assert str(coverage.analog_candidate_count) in message
    assert "Analogkandidaten" in message


# ==========================================================================================
# 2. a blocked position carries its own proof
# ==========================================================================================


def test_every_blocked_position_carries_its_own_proof(client, manual_case):
    """Previously the client had to join `audit_trail.per_code` by Ziffer to explain a block."""
    body = solve_payload(client, manual_case("case_001_knee"))
    blocked = body["coding"]["blocked_codes"]

    assert blocked, "case_001 blocks three positions"
    for entry in blocked:
        assert "proof" in entry, f"GOÄ {entry['ziffer']} has no proof field"
        assert entry["proof"], f"GOÄ {entry['ziffer']} is blocked with an empty proof"
        for step in entry["proof"]:
            assert step["ziffer"] == entry["ziffer"]
            assert step["rule"]


def test_the_blocked_proof_matches_the_audit_trail_exactly(client, manual_case):
    """Both are built from one helper, so they cannot drift. If this fails, one of the two paths
    changed and a client would get a different answer depending on where it looked."""
    body = solve_payload(client, manual_case("case_001_knee"))
    per_code = {entry["ziffer"]: entry["steps"] for entry in body["audit_trail"]["per_code"]}

    for entry in body["coding"]["blocked_codes"]:
        assert entry["proof"] == per_code[entry["ziffer"]], (
            f"GOÄ {entry['ziffer']}: blocked_codes[].proof and per_code disagree"
        )


def test_a_suppression_proof_names_the_rule_that_did_it(client, manual_case):
    """The point of carrying the proof: a reviewer can see *which* rule removed the position."""
    body = solve_payload(client, manual_case("case_001_knee"))
    by_ziffer = {entry["ziffer"]: entry for entry in body["coding"]["blocked_codes"]}

    rules_for = lambda z: {step["rule"] for step in by_ziffer[z]["proof"]}  # noqa: E731

    assert "blocked_zielleistung" in rules_for("200"), "the dressing is a Zielleistung component"
    assert "blocked_less_specific" in rules_for("300"), "Nr. 301 is the specific position"
    assert "conflict_pending_arbitration" in rules_for("5"), "Nr. 5 lost the arbitration to Nr. 7"


@pytest.mark.parametrize(
    "name", ["case_001_knee", "case_002_cardiology", "case_003_dermatology"]
)
def test_no_blocked_position_is_ever_unexplained(client, manual_case, name):
    body = solve_payload(client, manual_case(name))

    for entry in body["coding"]["blocked_codes"]:
        assert entry["explanation"], f"{name}: GOÄ {entry['ziffer']} blocked without prose"
        assert entry["proof"], f"{name}: GOÄ {entry['ziffer']} blocked without a proof"


# ==========================================================================================
# 3. factor_basis is a closed union
# ==========================================================================================


def test_factor_basis_is_a_closed_union_in_the_published_schema(client):
    """An open string cannot be labelled exhaustively by a client; a union can."""
    schema = client.get("/openapi.json").json()
    line = schema["components"]["schemas"]["InvoiceLine"]["properties"]["factor_basis"]

    assert "enum" in line, "factor_basis is still an open string in the contract"
    assert set(line["enum"]) == {
        "einfachsatz",
        "schwellenwert",
        "ueber_schwellenwert",
        "hoechstsatz",
        "capped",
    }


def test_the_invoice_line_and_the_solver_decision_share_one_union():
    """Two names for one decision, so they must be one type.

    Asserted on the annotations rather than the OpenAPI document: `FactorDecision` is internal —
    it lives on `OptimizationResult`, which no endpoint returns — so it has no published schema to
    compare. Identity of the annotation is the stronger claim anyway: not "the two lists happen to
    match today" but "there is only one list".
    """
    from app.schemas import FactorDecision, InvoiceLine

    line = InvoiceLine.model_fields["factor_basis"].annotation
    decision = FactorDecision.model_fields["basis"].annotation

    assert line is decision is FactorBasis


def test_every_emitted_factor_basis_is_inside_the_union(client, manual_case):
    """The values did not change — only the type did. A renamed value would move the money."""
    import typing

    allowed = set(typing.get_args(FactorBasis))

    for name in ("case_001_knee", "case_002_cardiology", "case_003_dermatology"):
        body = solve_payload(client, manual_case(name))
        for line in body["coding"]["proposed_codes"]:
            assert line["factor_basis"] in allowed, (
                f"{name}: GOÄ {line['ziffer']} has factor_basis "
                f"{line['factor_basis']!r}, outside the declared union"
            )


def test_a_value_outside_the_union_is_rejected():
    """The type is load-bearing, not decorative: an unknown basis must fail validation rather than
    reach a client that has no label for it."""
    from pydantic import ValidationError

    from app.schemas import FactorDecision

    with pytest.raises(ValidationError):
        FactorDecision(
            ziffer="1",
            factor=Decimal("2.3"),
            basis="documented_difficulty",  # plausible, and not one of ours
            threshold=Decimal("2.3"),
            max_factor=Decimal("3.5"),
        )


# ==========================================================================================
# 4. solver_status is readable from the top level
# ==========================================================================================


def test_solver_status_is_on_the_proposal(client, manual_case):
    """The UI header shows it beside the status and the receipt; it should not have to reach into
    solver_result.audit_trail to find it."""
    body = solve_proposal(client, manual_case("case_001_knee"))

    assert "solver_status" in body
    assert body["solver_status"], "an empty status tells a reviewer nothing"
    assert body["solver_timed_out"] is False


def test_the_promoted_status_agrees_with_the_audit_trail(client, manual_case):
    """The audit trail keeps its own copy — that is the immutable record. The two must match."""
    body = solve_proposal(client, manual_case("case_001_knee"))

    assert body["solver_status"] == body["solver_result"]["audit_trail"]["solver_status"]


def test_the_status_survives_a_cache_hit(client, manual_case):
    """A cached proposal is rebuilt from the stored result, so a field read off the audit trail must
    still be present the second time."""
    first = solve_proposal(client, manual_case("case_002_cardiology"))
    second = solve_proposal(client, manual_case("case_002_cardiology"))

    assert second["cached"] is True
    assert second["solver_status"] == first["solver_status"]
    assert second["solver_timed_out"] == first["solver_timed_out"]


def test_timed_out_is_derived_from_the_status_not_guessed(pipeline, manual_case):
    """`solver_timed_out` must mean exactly "the status is TIMEOUT_PARTIAL" — no second source of
    truth about whether the solver was cut short."""
    from app.schemas import ClinicalExtraction

    extraction = ClinicalExtraction.model_validate(manual_case("case_001_knee"))
    proposal = pipeline.propose(extraction)

    assert proposal.solver_timed_out == (proposal.solver_status == "TIMEOUT_PARTIAL")
    assert proposal.solver_timed_out is False, "a 5 s budget is not reached by a ~30 ms solve"
