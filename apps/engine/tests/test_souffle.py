"""Rules-engine tests. Each drives Soufflé directly with synthetic candidates.

The Ziffern used here are real positions from the imported official catalog, and the rules under
test are the human-verified subset in ``data/rules/*.manual.csv``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import Settings, UnverifiedRulePolicy
from app.rules.rule_store import RuleStore
from app.solvers.souffle_engine import SouffleEngine, SouffleError
from tests.conftest import make_bridge, make_extraction, one_act_per_ziffer


def blocked_map(result):
    return {b.ziffer: (b.reason, b.blocked_by) for b in result.blocked}


# ------------------------------------------------------------------------------------------
# smoke
# ------------------------------------------------------------------------------------------


def test_souffle_smoke(souffle):
    """The engine is present, can evaluate, and reaches a conclusion."""
    assert souffle.available()
    assert souffle.version().startswith("2.")

    result = souffle.run(make_extraction(), one_act_per_ziffer("410"))

    assert result.billable == ["410"]
    assert result.blocked == []
    assert result.proof, "a conclusion without a proof is not a conclusion"


def test_single_position_is_chargeable(souffle):
    result = souffle.run(make_extraction(), one_act_per_ziffer("7"))

    assert result.billable == ["7"]


# ------------------------------------------------------------------------------------------
# mutual exclusion — the rule that naive Datalog gets wrong
# ------------------------------------------------------------------------------------------


def test_mutual_exclusion_does_not_block_both_codes(souffle):
    """Nr. 5 and Nr. 7 exclude each other under the official Anmerkungen to Nr. 5-8.

    Under plain negation-as-failure each would block the other and BOTH would disappear,
    silently destroying a chargeable service. The engine must defer instead of concluding.
    """
    result = souffle.run(make_extraction(), one_act_per_ziffer("5", "7"))

    assert result.billable == [], "neither may be concluded chargeable on its own"
    assert result.arbitration_candidates == ["5", "7"], "both must survive for the solver"
    assert "5" not in blocked_map(result)
    assert "7" not in blocked_map(result)
    assert [(c.ziffer_a, c.ziffer_b) for c in result.conflicts] == [("5", "7")]


def test_mutual_conflict_carries_its_rule_and_legal_basis(souffle):
    result = souffle.run(make_extraction(), one_act_per_ziffer("5", "7"))
    conflict = result.conflicts[0]

    assert conflict.rule_id.startswith("excl_man_")
    assert "Nummer" in conflict.legal_basis or "GOÄ" in conflict.legal_basis


def test_whole_mutual_cluster_is_deferred_not_decimated(souffle):
    """Nr. 5, 6, 7, 8 form one cluster; all four must reach the solver."""
    result = souffle.run(make_extraction(), one_act_per_ziffer("5", "6", "7", "8"))

    assert result.billable == []
    assert result.arbitration_candidates == ["5", "6", "7", "8"]


def test_ekg_cluster_is_mutual(souffle):
    """Nr. 650-653: 'Die Leistungen ... sind nicht nebeneinander berechnungsfähig.'"""
    result = souffle.run(make_extraction(), one_act_per_ziffer("650", "651"))

    assert result.arbitration_candidates == ["650", "651"]


def test_echo_cluster_is_mutual(souffle):
    """Nr. 422-424 likewise."""
    result = souffle.run(make_extraction(), one_act_per_ziffer("422", "423"))

    assert result.arbitration_candidates == ["422", "423"]


def test_unrelated_positions_do_not_conflict(souffle):
    result = souffle.run(make_extraction(), one_act_per_ziffer("7", "410", "659"))

    assert result.billable == ["410", "659", "7"]
    assert result.conflicts == []


# ------------------------------------------------------------------------------------------
# specificity
# ------------------------------------------------------------------------------------------


def test_more_specific_position_wins_within_one_act(souffle):
    """A knee puncture matches Nr. 300 (a joint) and Nr. 301 (a knee joint)."""
    bridge = make_bridge(("a1", "301", 100, "1.0"), ("a1", "300", 80, "1.0"))

    result = souffle.run(make_extraction(), bridge)

    assert result.billable == ["301"]
    assert blocked_map(result)["300"] == ("less_specific", "301")


def test_specificity_block_names_the_rule_that_caused_it(souffle):
    bridge = make_bridge(("a1", "301", 100, "1.0"), ("a1", "300", 80, "1.0"))

    result = souffle.run(make_extraction(), bridge)
    blocked = next(b for b in result.blocked if b.ziffer == "300")

    assert blocked.rule_id == "spec_301_300"
    assert blocked.legal_basis


def test_specificity_does_not_apply_across_separate_acts(souffle):
    """Two different joints punctured are two chargeable services, not a contest."""
    bridge = make_bridge(("a1", "301", 100, "1.0"), ("a2", "300", 80, "1.0"))

    result = souffle.run(make_extraction(), bridge)

    assert result.billable == ["300", "301"]


# ------------------------------------------------------------------------------------------
# Zielleistungsprinzip (§ 4 Abs. 2a GOÄ)
# ------------------------------------------------------------------------------------------


def test_zielleistung_blocks_the_component(souffle):
    """Nr. 200 (Verband) is a component of a puncture per the Allgemeine Bestimmung."""
    result = souffle.run(make_extraction(), one_act_per_ziffer("301", "200"))

    assert result.billable == ["301"]
    assert blocked_map(result)["200"] == ("zielleistung", "301")


def test_zielleistung_block_cites_paragraph_4_abs_2a(souffle):
    result = souffle.run(make_extraction(), one_act_per_ziffer("301", "200"))
    blocked = next(b for b in result.blocked if b.ziffer == "200")

    assert "§ 4 Abs. 2a" in blocked.legal_basis
    assert blocked.rule_id.startswith("ziel_")


def test_component_is_chargeable_when_the_parent_is_absent(souffle):
    result = souffle.run(make_extraction(), one_act_per_ziffer("200"))

    assert result.billable == ["200"]


# ------------------------------------------------------------------------------------------
# unverified-rule policy
# ------------------------------------------------------------------------------------------


def test_unverified_rules_do_not_block_under_the_default_policy(settings, catalog):
    """The safety posture: a machine-read rule must not suppress a chargeable service.

    The rule under test is chosen from whatever the store is actually holding back, rather than
    named. It used to name the auto-extracted Nr. 21 -> Nr. 1 edge, which was fine until a
    verification pass verified it — at which point the test failed for the one reason that is not a
    regression. What is being asserted is a property of the policy, not of any particular rule, so
    the test now reads the property off the store and skips honestly if the backlog is ever empty.
    """
    warn_rules = RuleStore.load(policy=UnverifiedRulePolicy.WARN)
    engine = SouffleEngine(settings, catalog, warn_rules)
    if not engine.available():
        pytest.skip("souffle not available")

    held_back = next(
        (
            r
            for r in warn_rules.suppressed
            if not r.verified
            and getattr(r, "from_ziffer", "")
            and catalog.has(r.from_ziffer)
            and catalog.has(r.to_ziffer)
            and r.from_ziffer != r.to_ziffer
        ),
        None,
    )
    if held_back is None:
        pytest.skip("no unverified exclusion left in the shipped data to exercise the policy with")

    result = engine.run(
        make_extraction(), one_act_per_ziffer(held_back.from_ziffer, held_back.to_ziffer)
    )

    assert set(result.billable) == {held_back.from_ziffer, held_back.to_ziffer}, (
        f"{held_back.rule_id} is unverified and must not block under policy=warn"
    )


def test_block_policy_enforces_unverified_rules(catalog):
    """The same input under UNVERIFIED_RULE_POLICY=block does suppress."""
    settings = Settings(unverified_rule_policy=UnverifiedRulePolicy.BLOCK)
    block_rules = RuleStore.load(policy=UnverifiedRulePolicy.BLOCK)
    engine = SouffleEngine(settings, catalog, block_rules)
    if not engine.available():
        pytest.skip("souffle not available")

    result = engine.run(make_extraction(), one_act_per_ziffer("21", "1"))

    assert "1" not in result.billable
    assert blocked_map(result)["1"][0] in {"exclusion", "mutual_exclusion"}


def test_policy_choice_is_reported(settings):
    warn = RuleStore.load(policy=UnverifiedRulePolicy.WARN).summary()
    block = RuleStore.load(policy=UnverifiedRulePolicy.BLOCK).summary()

    assert warn["policy_for_unverified_rules"] == "warn"
    assert warn["unverified_rules_not_enforced"] > 0
    assert block["exclusions_enforced"] > warn["exclusions_enforced"]


# ------------------------------------------------------------------------------------------
# factor validation (§ 5, § 12 Abs. 3 GOÄ)
# ------------------------------------------------------------------------------------------


def test_factor_above_threshold_needs_justification(souffle):
    """Nr. 7 is Abschnitt B: Schwellenwert 2.3. A factor of 3.0 is lawful but needs a reason."""
    result = souffle.run(
        make_extraction(), one_act_per_ziffer("7"), proposed_factors={"7": Decimal("3.0")}
    )

    assert result.factor_needs_justification == ["7"]
    assert result.factor_invalid == []


def test_factor_above_maximum_is_invalid(souffle):
    result = souffle.run(
        make_extraction(), one_act_per_ziffer("7"), proposed_factors={"7": Decimal("4.0")}
    )

    assert result.factor_invalid == ["7"]
    assert any(w.type == "factor_above_hoechstsatz" for w in result.warnings)


def test_factor_at_threshold_needs_no_justification(souffle):
    result = souffle.run(
        make_extraction(), one_act_per_ziffer("7"), proposed_factors={"7": Decimal("2.3")}
    )

    assert result.factor_needs_justification == []
    assert result.factor_invalid == []


def test_lab_section_has_its_own_much_tighter_band(souffle):
    """Nr. 3550 is Abschnitt M: § 5 Abs. 4 caps it at 1.3. A factor that is unremarkable for
    Abschnitt B is unlawful here."""
    result = souffle.run(
        make_extraction(), one_act_per_ziffer("3550"), proposed_factors={"3550": Decimal("2.3")}
    )

    assert result.factor_invalid == ["3550"]


def test_nummer_437_takes_the_lab_band_although_it_sits_in_abschnitt_c(souffle, catalog):
    """§ 5 Abs. 4 names Nummer 437 individually, next to Abschnitt M."""
    assert catalog.get("437").category == "M"

    result = souffle.run(
        make_extraction(), one_act_per_ziffer("437"), proposed_factors={"437": Decimal("2.0")}
    )

    assert result.factor_invalid == ["437"]


def test_histology_is_not_capped_like_the_lab_section(souffle, catalog):
    """Abschnitt N is NOT in § 5 Abs. 4. Capping it at 1.3 would undercharge every line."""
    assert catalog.get("4800").section == "N"

    result = souffle.run(
        make_extraction(), one_act_per_ziffer("4800"), proposed_factors={"4800": Decimal("2.3")}
    )

    assert result.factor_invalid == []


# ------------------------------------------------------------------------------------------
# § 6a Minderung
# ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "setting,expected", [("ambulant", "0"), ("stationaer", "0.25"), ("belegarzt", "0.15")]
)
def test_minderung_rate_per_setting(catalog, setting, expected):
    assert catalog.minderung_rate(setting) == Decimal(expected)


@pytest.mark.parametrize("setting,applies", [("ambulant", False), ("stationaer", True), ("belegarzt", True)])
def test_minderung_is_detected_for_the_setting(souffle, setting, applies):
    result = souffle.run(make_extraction(setting=setting), one_act_per_ziffer("7"))
    steps = [s for s in result.proof if s.rule == "minderung_applicable"]

    assert bool(steps) is applies


# ------------------------------------------------------------------------------------------
# proof tree
# ------------------------------------------------------------------------------------------


def test_every_chargeable_position_gets_a_full_positive_proof(souffle):
    result = souffle.run(make_extraction(), one_act_per_ziffer("7", "410"))

    for ziffer in result.billable:
        rules = {s.rule for s in result.proof if s.ziffer == ziffer}
        assert {
            "catalog_match",
            "most_specific_candidate",
            "not_zielleistung_component",
            "not_excluded",
            "no_unresolved_conflict",
        } <= rules, f"GOÄ {ziffer} proof is incomplete: {rules}"


def test_blocked_positions_get_a_negative_proof_naming_the_blocker(souffle):
    result = souffle.run(make_extraction(), one_act_per_ziffer("301", "200"))
    steps = [(s.rule, s.detail) for s in result.proof if s.ziffer == "200"]

    assert ("blocked_zielleistung", "301") in steps


def test_proof_steps_carry_rule_ids_for_rule_driven_conclusions(souffle):
    result = souffle.run(make_extraction(), one_act_per_ziffer("301", "200"))
    step = next(s for s in result.proof if s.ziffer == "200" and s.rule == "blocked_zielleistung")

    assert step.rule_id
    assert step.legal_basis


# ------------------------------------------------------------------------------------------
# failure modes are never silent
# ------------------------------------------------------------------------------------------


def test_a_position_missing_from_the_catalog_is_reported_not_ignored(souffle):
    result = souffle.run(make_extraction(), one_act_per_ziffer("99999"))

    assert result.billable == []
    assert blocked_map(result)["99999"][0] == "unknown_ziffer"
    assert any(w.severity == "error" for w in result.warnings)


def test_missing_souffle_binary_raises_a_useful_error(catalog, rules):
    broken = SouffleEngine(Settings(souffle_bin="souffle-does-not-exist"), catalog, rules)

    with pytest.raises(SouffleError, match="not found on PATH"):
        broken.run(make_extraction(), one_act_per_ziffer("7"))


def test_fact_files_are_arity_checked(catalog, rules, tmp_path):
    """A malformed fact row must fail loudly, not shift every following column."""
    from app.solvers.souffle_facts import FactGenerationError, _write

    with pytest.raises(FactGenerationError, match="expected arity"):
        _write(tmp_path / "ziffer.facts", [("7", 160)], 4)


def test_tabs_in_values_are_stripped_so_columns_cannot_shift(tmp_path):
    from app.solvers.souffle_facts import _write

    _write(tmp_path / "act.facts", [("a1", "proc\tedure", "punk\ntion")], 3)
    line = (tmp_path / "act.facts").read_text(encoding="utf-8").strip()

    assert line.count("\t") == 2, "a tab inside a value would create a phantom column"
