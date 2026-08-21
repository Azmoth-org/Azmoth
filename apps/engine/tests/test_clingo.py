"""Solver tests: arbitration, the factor ladder, Analogansatz, and a brute-force cross-check."""

from __future__ import annotations

import itertools
from decimal import Decimal

import pytest

from app.config import BaseFactorPolicy, Settings
from app.schemas import AnalogRequest, RulesResult
from app.solvers.clingo_solver import ClingoError, ClingoSolver
from tests.conftest import make_bridge, make_extraction, one_act_per_ziffer


def factors(result) -> dict[str, Decimal]:
    return {f.ziffer: f.factor for f in result.factors}


def solve(souffle, solver, bridge, extraction):
    rules_result = souffle.run(extraction, bridge)
    return solver.solve(rules_result, extraction, bridge)


def justified(target: str, severity: str) -> list[dict]:
    return [{"reason": f"synthetic {severity} justification", "severity": severity,
             "applies_to": [target]}]


# ------------------------------------------------------------------------------------------
# smoke
# ------------------------------------------------------------------------------------------


def test_clingo_smoke(souffle, solver):
    result = solve(souffle, solver, one_act_per_ziffer("410"), make_extraction())

    assert result.solver_status == "SAT"
    assert result.billed == ["410"]
    assert result.models_enumerated >= 1
    assert factors(result)["410"] == Decimal("2.3")


def test_solver_never_invents_a_position(souffle, solver, catalog):
    result = solve(souffle, solver, one_act_per_ziffer("7", "410"), make_extraction())

    for ziffer in result.billed:
        assert catalog.has(ziffer)
    assert set(result.billed) <= {"7", "410"}


# ------------------------------------------------------------------------------------------
# arbitration
# ------------------------------------------------------------------------------------------


def test_mutual_conflict_resolves_to_exactly_one_position(souffle, solver):
    bridge = make_bridge(("a1", "5", 100, "0.8"), ("a2", "7", 100, "0.95"), ("a3", "410", 100, "1.0"))

    result = solve(souffle, solver, bridge, make_extraction())

    assert "410" in result.billed
    assert len({"5", "7"} & set(result.billed)) == 1


def test_arbitration_prefers_the_better_documented_code_over_the_better_paid_one(
    souffle, solver, catalog
):
    """The claim that this is not a revenue maximiser, written as an executable assertion.

    Nr. 8 (260 points) is worth more than Nr. 7 (160). Here Nr. 7 carries the stronger
    documentary basis, so Nr. 7 must win — money is only a tiebreaker between options that are
    equally well evidenced.
    """
    assert catalog.get("8").punkte > catalog.get("7").punkte

    bridge = make_bridge(("a1", "7", 100, "1.0"), ("a2", "8", 100, "0.55"))
    result = solve(souffle, solver, bridge, make_extraction())

    assert result.billed == ["7"]
    assert [d.ziffer for d in result.dropped] == ["8"]


def test_revenue_breaks_ties_only_when_evidence_and_specificity_are_equal(souffle, solver):
    bridge = make_bridge(("a1", "7", 100, "0.9"), ("a2", "8", 100, "0.9"))

    result = solve(souffle, solver, bridge, make_extraction())

    assert result.billed == ["8"], "equal evidence and specificity, so the higher value wins"


def test_arbitration_never_drops_both_sides_of_a_conflict(souffle, solver):
    """The @4 objective: a documented service must not vanish from the invoice entirely."""
    result = solve(souffle, solver, one_act_per_ziffer("5", "7"), make_extraction())

    assert len({"5", "7"} & set(result.billed)) == 1


def test_a_four_member_cluster_yields_exactly_one_charged_position(souffle, solver):
    bridge = make_bridge(
        ("a1", "5", 100, "0.5"), ("a2", "6", 100, "0.6"),
        ("a3", "7", 100, "0.7"), ("a4", "8", 100, "0.9"),
    )

    result = solve(souffle, solver, bridge, make_extraction())

    assert len({"5", "6", "7", "8"} & set(result.billed)) == 1
    assert result.billed == ["8"], "best evidence in the cluster"


def test_the_losing_position_is_reported_with_a_reason_and_rule(souffle, solver):
    bridge = make_bridge(("a1", "7", 100, "1.0"), ("a2", "8", 100, "0.55"))

    result = solve(souffle, solver, bridge, make_extraction())
    dropped = result.dropped[0]

    assert dropped.reason == "conflict_lost"
    assert dropped.blocked_by == "7"
    assert dropped.rule_id
    assert "Dokumentationslage" in dropped.explanation


# ------------------------------------------------------------------------------------------
# hard constraints hold in the solver too
# ------------------------------------------------------------------------------------------


def test_solver_never_charges_a_component_with_its_parent(souffle, solver):
    result = solve(souffle, solver, one_act_per_ziffer("301", "200"), make_extraction())

    assert result.billed == ["301"]


def test_solver_never_charges_two_excluded_positions_together(souffle, solver, rules):
    result = solve(
        souffle, solver, one_act_per_ziffer("5", "7", "650", "651"), make_extraction()
    )
    billed = set(result.billed)

    for rule in rules.exclusions:
        assert not (rule.from_ziffer in billed and rule.to_ziffer in billed), (
            f"GOÄ {rule.from_ziffer} and {rule.to_ziffer} charged together despite {rule.rule_id}"
        )


def test_contradictory_rule_set_is_reported_before_the_solver_sees_it(solver):
    """A one-way exclusion between two positions the rules engine both proved chargeable would
    surface as a bare UNSAT. The pre-check turns it into a readable error."""
    rules_result = RulesResult(billable=["5", "7"])

    with pytest.raises(ClingoError, match="Rule set inconsistency"):
        solver.solve(rules_result, make_extraction(), make_bridge())


# ------------------------------------------------------------------------------------------
# Steigerungsfaktor ladder
# ------------------------------------------------------------------------------------------


def test_default_factor_policy_schwellenwert(souffle, solver):
    """§ 5 Abs. 2 GOÄ: factors up to the Schwellenwert need no written justification, so that is
    the defensible default. Billing 1.0 would undercharge for no legal benefit."""
    result = solve(souffle, solver, one_act_per_ziffer("7"), make_extraction())

    assert factors(result)["7"] == Decimal("2.3")
    assert result.factors[0].basis == "schwellenwert"
    assert result.factors[0].justification_required is False


def test_default_factor_policy_einfachsatz(souffle, catalog, rules):
    conservative = ClingoSolver(
        Settings(base_factor_policy=BaseFactorPolicy.EINFACHSATZ), catalog, rules
    )
    extraction = make_extraction()
    bridge = one_act_per_ziffer("7")
    rules_result = souffle.run(extraction, bridge)

    result = conservative.solve(rules_result, extraction, bridge)

    assert factors(result)["7"] == Decimal("1")
    assert result.factors[0].basis == "einfachsatz"


def test_leicht_justification_stays_at_the_schwellenwert(souffle, solver):
    extraction = make_extraction(justifications=justified("synthetic_a1", "leicht"))
    result = solve(souffle, solver, one_act_per_ziffer("7"), extraction)

    assert factors(result)["7"] == Decimal("2.3")


def test_mittel_justification_steps_above_the_schwellenwert(souffle, solver):
    extraction = make_extraction(justifications=justified("synthetic_a1", "mittel"))
    result = solve(souffle, solver, one_act_per_ziffer("7"), extraction)
    decision = result.factors[0]

    assert decision.factor == Decimal("2.6")
    assert decision.basis == "ueber_schwellenwert"
    assert decision.justification_required is True
    assert decision.justification == "synthetic mittel justification"


def test_schwer_justification_reaches_the_hoechstsatz(souffle, solver):
    extraction = make_extraction(justifications=justified("synthetic_a1", "schwer"))
    result = solve(souffle, solver, one_act_per_ziffer("7"), extraction)

    assert factors(result)["7"] == Decimal("3.5")
    assert result.factors[0].basis == "hoechstsatz"


def test_category_m_factor_never_exceeds_max(souffle, solver, catalog):
    """Abschnitt M: Schwellenwert 1.15, Höchstsatz 1.3 (§ 5 Abs. 4). 1.15 + 0.3 = 1.45 would be
    unlawful, so the cap has to bind or every lab line becomes illegal."""
    band = catalog.factor_band("3550")
    assert (band.threshold, band.max) == (Decimal("1.15"), Decimal("1.3"))

    for severity in ("leicht", "mittel", "schwer"):
        extraction = make_extraction(justifications=justified("synthetic_a1", severity))
        result = solve(souffle, solver, one_act_per_ziffer("3550"), extraction)

        assert factors(result)["3550"] <= Decimal("1.3"), severity


def test_the_strongest_justification_wins_when_several_apply(souffle, solver):
    extraction = make_extraction(
        justifications=justified("synthetic_a1", "leicht") + justified("synthetic_a1", "schwer")
    )
    result = solve(souffle, solver, one_act_per_ziffer("7"), extraction)

    assert factors(result)["7"] == Decimal("3.5")


def test_a_justification_only_raises_the_line_it_names(souffle, solver):
    """One documented difficulty must not inflate every line on the invoice."""
    bridge = make_bridge(("a1", "301", 100, "1.0"), ("a2", "410", 100, "1.0"))
    extraction = make_extraction(justifications=justified("synthetic_a1", "mittel"))

    result = solve(souffle, solver, bridge, extraction)

    assert factors(result) == {"301": Decimal("2.6"), "410": Decimal("2.3")}


def test_an_unbound_justification_applies_to_the_whole_encounter(souffle, solver):
    extraction = make_extraction(
        justifications=[{"reason": "Notfall", "severity": "schwer", "applies_to": []}]
    )
    result = solve(souffle, solver, one_act_per_ziffer("301", "410"), extraction)

    assert factors(result) == {"301": Decimal("3.5"), "410": Decimal("3.5")}


def test_every_charged_position_gets_exactly_one_factor(souffle, solver):
    result = solve(
        souffle, solver, one_act_per_ziffer("1", "7", "301", "410", "3550"), make_extraction()
    )

    assert sorted(factors(result)) == sorted(result.billed)


def test_factor_carries_its_legal_basis(souffle, solver):
    result = solve(souffle, solver, one_act_per_ziffer("3550"), make_extraction())

    assert "§ 5 Abs. 4" in result.factors[0].legal_basis


# ------------------------------------------------------------------------------------------
# Analogansatz (§ 6 Abs. 2 GOÄ)
# ------------------------------------------------------------------------------------------


def _with_analog(souffle, extraction, bridge, entity_type="optische_kohaerenztomographie"):
    rules_result = souffle.run(extraction, bridge)
    rules_result.analog_requests = [
        AnalogRequest(act_id="x1", entity_type=entity_type, confidence=Decimal("1.0"))
    ]
    return rules_result


def test_analog_selection_picks_the_most_equivalent_position(souffle, solver, rules):
    best = max(rules.analog_for("optische_kohaerenztomographie"), key=lambda c: c.similarity)
    extraction = make_extraction()
    bridge = one_act_per_ziffer("1")

    result = solver.solve(_with_analog(souffle, extraction, bridge), extraction, bridge)

    assert [a.ziffer for a in result.analogs] == [best.target_ziffer]


def test_analog_line_has_proof_and_warning(souffle, solver, validator, catalog, rules):
    """§ 6 Abs. 2 charging is a judgement call, so the line must be labelled and flagged."""
    from app.services.pipeline import Pipeline

    pipeline = Pipeline(validator.settings, catalog, rules)
    extraction = make_extraction()
    bridge = one_act_per_ziffer("1")
    rules_result = _with_analog(souffle, extraction, bridge)
    optimization = solver.solve(rules_result, extraction, bridge)

    verification_bridge = validator.build_verification_bridge(optimization)
    verification = pipeline.apply_rules(
        extraction,
        verification_bridge,
        proposed_factors={f.ziffer: f.factor for f in optimization.factors},
    )
    coding, _audit = validator.build(
        extraction, rules_result, optimization, bridge, verification=verification
    )

    analog_line = next(line for line in coding.proposed_codes if line.is_analog)
    assert analog_line.status == "billable_analog"
    assert analog_line.analog_for == "optische_kohaerenztomographie"
    assert analog_line.proof, "an analog line must still carry a proof tree"
    assert any(step.rule == "analogansatz" for step in analog_line.proof)
    assert any(step.rule == "catalog_match" for step in analog_line.proof)

    assert coding.analog_codes[0].requires_human_review is True
    warning = next(w for w in coding.warnings if w.type == "analogansatz_requires_human_review")
    assert "§ 6 Abs. 2" in warning.legal_basis
    assert "ÄRZTLICH ZU PRÜFEN" in warning.message


def test_analog_position_avoids_colliding_with_a_directly_charged_one(souffle, solver, rules):
    """Nr. 750 is the best analog for OCT, but if it is already charged directly the solver must
    fall back rather than charge the same position twice for two different services."""
    best = max(rules.analog_for("optische_kohaerenztomographie"), key=lambda c: c.similarity)
    extraction = make_extraction()
    bridge = one_act_per_ziffer(best.target_ziffer)

    result = solver.solve(_with_analog(souffle, extraction, bridge), extraction, bridge)

    assert result.analogs[0].ziffer != best.target_ziffer
    assert result.warnings == []


def test_analog_positions_count_towards_the_total(souffle, solver, catalog):
    extraction = make_extraction()
    bridge = one_act_per_ziffer("1")

    result = solver.solve(_with_analog(souffle, extraction, bridge), extraction, bridge)
    analog_ziffer = result.analogs[0].ziffer

    assert result.total_punkte == catalog.get("1").punkte + catalog.get(analog_ziffer).punkte
    assert analog_ziffer in factors(result)


# ------------------------------------------------------------------------------------------
# differential test against brute force
# ------------------------------------------------------------------------------------------

#: Small sets whose optimum can be enumerated by hand.
BRUTEFORCE_CASES = [
    ("5", "7"),
    ("5", "6", "7"),
    ("650", "651"),
    ("422", "423"),
    ("301", "200"),
    ("7", "410", "659"),
    ("5", "7", "410"),
]


@pytest.mark.parametrize("ziffern", BRUTEFORCE_CASES)
def test_clingo_matches_bruteforce_for_small_cases(souffle, solver, catalog, rules, ziffern):
    """Enumerate every subset, filter by the hard constraints, score with the same lexicographic
    objective, and check the solver agrees.

    This is the check that the ASP encoding means what the prose says it means. If the objective
    ordering in goae_optimize.lp were wrong — revenue ahead of evidence, say — the two would
    disagree here.
    """
    confidences = {z: Decimal("0.5") + Decimal("0.1") * i for i, z in enumerate(ziffern)}
    bridge = make_bridge(*[(f"a{i}", z, 100, str(confidences[z])) for i, z in enumerate(ziffern, 1)])

    extraction = make_extraction()
    rules_result = souffle.run(extraction, bridge)
    result = solver.solve(rules_result, extraction, bridge)

    fixed = set(rules_result.billable)
    optional = set(rules_result.arbitration_candidates)
    conflict_pairs = [(c.ziffer_a, c.ziffer_b) for c in rules_result.conflicts]

    def legal(selection: set[str]) -> bool:
        for rule in rules.exclusions:
            if rule.from_ziffer in selection and rule.to_ziffer in selection:
                return False
        for zrule in rules.zielleistung:
            if zrule.parent_ziffer in selection and zrule.child_ziffer in selection:
                return False
        return True

    def score(selection: set[str]) -> tuple[int, int, int, int]:
        covered = sum(1 for a, b in conflict_pairs if a in selection or b in selection)
        evidence = sum(int(confidences[z] * 100) for z in selection if z in confidences)
        specificity = sum(100 for _ in selection)
        points = sum(catalog.get(z).punkte for z in selection)
        return (covered, evidence, specificity, points)

    best_score = None
    best_sets: list[set[str]] = []
    for size in range(len(optional) + 1):
        for chosen in itertools.combinations(sorted(optional), size):
            selection = fixed | set(chosen)
            if not legal(selection):
                continue
            value = score(selection)
            if best_score is None or value > best_score:
                best_score, best_sets = value, [selection]
            elif value == best_score:
                best_sets.append(selection)

    assert best_score is not None, "brute force found no legal selection"
    assert set(result.billed) in best_sets, (
        f"solver chose {sorted(result.billed)} scoring {score(set(result.billed))}, "
        f"brute force optimum is {[sorted(s) for s in best_sets]} scoring {best_score}"
    )


def test_result_reports_solver_metadata(souffle, solver):
    result = solve(souffle, solver, one_act_per_ziffer("5", "7"), make_extraction())

    assert result.solver_status == "SAT"
    assert result.models_enumerated >= 1
    assert result.objective
