"""The coverage-sprint's four new constraint families: Mengenbegrenzung, Zeitbeziehung, Geschlecht,
Alter. See `docs/content/adr-002-complex-constraints.md`.

Every Soufflé-level test here builds its own `RuleStore` by hand, from nothing — the same pattern
`tests/test_padnext.py::_synthetic_rules` and `tests/test_souffle.py::
test_block_policy_enforces_unverified_rules` already use — rather than loading `data/rules/*.csv`.
Two reasons, and both matter:

1. **Isolation.** `data/rules/` carries no rows for these four rule types (see the ADR's
   "shipped, not yet materialised" note on why not), so a CSV-backed test would either need to add
   real rows — reintroducing the exact blast-radius risk against the shared golden suite the ADR
   documents avoiding — or test nothing at all.
2. **The Mengenbegrenzung golden test itself.** The task is to prove a violation is *caught*, which
   is a property of `logic/datalog/goae_rules.dl` and `app/solvers/souffle_facts.py`, not of the
   CSV loader — `tests/test_complex_constraints.py::test_rule_store_loads_the_four_new_families`
   below is what proves the CSV half works, on a temporary directory of its own.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.config import UnverifiedRulePolicy
from app.rules.rule_store import (
    AgeRestrictionRule,
    GenderRestrictionRule,
    QuantityLimitRule,
    RuleStore,
    TimeRelationRule,
)
from app.schemas import ClinicalExtraction
from app.schemas.facts import ClinicalAct, CodeCandidate
from tests.conftest import make_bridge


def _extraction(*, age: int | None = None, sex: str | None = None, setting: str = "ambulant"):
    return ClinicalExtraction.model_validate(
        {
            "patient": {"age": age, "sex": sex, "setting": setting},
            "justification_factors": [],
        }
    )


def _dated_bridge(*specs: tuple[str, str, str]):
    """`(act_id, ziffer, service_date)` triples — like `one_act_per_ziffer`, but with a date."""
    bridge = make_bridge()
    for act_id, ziffer, service_date in specs:
        bridge.acts.append(
            ClinicalAct(
                act_id=act_id,
                entity_id=act_id,
                source="procedure",
                entity_type=f"synthetic_{act_id}",
                confidence=Decimal("1"),
                service_date=service_date,
            )
        )
        bridge.candidates.append(
            CodeCandidate(act_id=act_id, ziffer=ziffer, priority=100, confidence=Decimal("1"))
        )
    return bridge


def _engine(settings, catalog, rules: RuleStore):
    from app.solvers.souffle_engine import SouffleEngine

    engine = SouffleEngine(settings, catalog, rules)
    if not engine.available():
        pytest.skip("souffle not available")
    return engine


# ==========================================================================================
# Mengenbegrenzung — the golden test
# ==========================================================================================
#
# GOÄ 4601 (real catalog Ziffer): "Eine mehr als dreimalige Berechnung der Leistung nach Nummer
# 4601 im Behandlungsfall ist nicht zulässig." — max 3 per Behandlungsfall (a calendar quarter).
# The synthetic patient history: three prior occurrences already recorded this quarter. The
# invoice: one more claim of the same Ziffer. The engine must catch the violation.

QUANTITY_RULE = QuantityLimitRule(
    rule_id="cnt_test_4601",
    ziffer="4601",
    max_count=3,
    window="behandlungsfall",
    legal_basis="GOÄ Anmerkung zu Nummer 4601",
    quote=(
        "Eine mehr als dreimalige Berechnung der Leistung nach Nummer 4601 im Behandlungsfall "
        "ist nicht zulässig."
    ),
    verified=True,
    verified_at="2026-09-12",
    source="manual_verification",
)


def test_quantity_limit_blocks_the_occurrence_that_would_exceed_the_cap(settings, catalog):
    """The golden case: a synthetic patient history at the cap, and an invoice that would break it."""
    rules = RuleStore(policy=UnverifiedRulePolicy.WARN, quantity_limits=[QUANTITY_RULE])
    engine = _engine(settings, catalog, rules)

    result = engine.run(
        _extraction(),
        make_bridge(("a1", "4601", 100, "1.0")),
        history_counts={"4601": 3},  # already billed 3 times this Behandlungsfall
    )

    assert result.billable == []
    blocked = next(b for b in result.blocked if b.ziffer == "4601")
    assert blocked.reason == "quantity_exceeded"
    assert blocked.rule_id == "cnt_test_4601"
    assert blocked.legal_basis == "GOÄ Anmerkung zu Nummer 4601"


def test_quantity_limit_admits_the_occurrence_below_the_cap(settings, catalog):
    rules = RuleStore(policy=UnverifiedRulePolicy.WARN, quantity_limits=[QUANTITY_RULE])
    engine = _engine(settings, catalog, rules)

    result = engine.run(
        _extraction(), make_bridge(("a1", "4601", 100, "1.0")), history_counts={"4601": 2}
    )

    assert result.billable == ["4601"]
    assert result.blocked == []


def test_quantity_limit_is_silent_when_no_history_is_supplied(settings, catalog):
    """The common case today: no caller tracks patient history, so the layer stays fully inert —
    exactly as if the rule did not exist, even though it is loaded."""
    rules = RuleStore(policy=UnverifiedRulePolicy.WARN, quantity_limits=[QUANTITY_RULE])
    engine = _engine(settings, catalog, rules)

    result = engine.run(_extraction(), make_bridge(("a1", "4601", 100, "1.0")))

    assert result.billable == ["4601"]


def test_an_unverified_quantity_limit_does_not_block_under_the_default_policy(settings, catalog):
    unverified = QuantityLimitRule(
        rule_id="cnt_test_unverified",
        ziffer="4601",
        max_count=3,
        legal_basis="GOÄ Anmerkung zu Nummer 4601",
        verified=False,
    )
    rules = RuleStore(policy=UnverifiedRulePolicy.WARN)
    admitted = rules._admit(unverified, sink=rules.quantity_limits_suppressed)
    assert admitted is False
    assert unverified in rules.quantity_limits_suppressed


# ==========================================================================================
# Zeitbeziehung
# ==========================================================================================


def test_same_day_time_relation_blocks_the_named_loser(settings, catalog):
    rule = TimeRelationRule(
        rule_id="tr_test_7_410",
        ziffer_a="7",
        ziffer_b="410",
        relation="same_day_excludes",
        legal_basis="Synthetische Zeitbeziehung",
        verified=True,
    )
    rules = RuleStore(policy=UnverifiedRulePolicy.WARN, time_relations=[rule])
    engine = _engine(settings, catalog, rules)

    result = engine.run(_extraction(), _dated_bridge(("a1", "7", "2026-01-05"), ("a2", "410", "2026-01-05")))

    assert result.billable == ["7"]
    blocked = next(b for b in result.blocked if b.ziffer == "410")
    assert blocked.reason == "time_relation"
    assert blocked.blocked_by == "7"


def test_same_day_time_relation_does_not_fire_across_different_dates(settings, catalog):
    rule = TimeRelationRule(
        rule_id="tr_test_7_410",
        ziffer_a="7",
        ziffer_b="410",
        relation="same_day_excludes",
        legal_basis="Synthetische Zeitbeziehung",
        verified=True,
    )
    rules = RuleStore(policy=UnverifiedRulePolicy.WARN, time_relations=[rule])
    engine = _engine(settings, catalog, rules)

    result = engine.run(
        _extraction(), _dated_bridge(("a1", "7", "2026-01-05"), ("a2", "410", "2026-06-20"))
    )

    assert set(result.billable) == {"7", "410"}


def test_min_hours_apart_is_advisory_only_and_never_blocks(settings, catalog):
    """The engine cannot know the actual clock time from a claimed date alone — see the ADR
    §Zeitbeziehung. A same-day match under this relation kind is a warning, never a block."""
    rule = TimeRelationRule(
        rule_id="tr_test_min_hours",
        ziffer_a="7",
        ziffer_b="410",
        relation="min_hours_apart",
        min_hours=4,
        legal_basis="Synthetische Zeitbeziehung",
        verified=True,
    )
    rules = RuleStore(policy=UnverifiedRulePolicy.WARN, time_relations=[rule])
    engine = _engine(settings, catalog, rules)

    result = engine.run(
        _extraction(), _dated_bridge(("a1", "7", "2026-01-05"), ("a2", "410", "2026-01-05"))
    )

    assert set(result.billable) == {"7", "410"}, "advisory findings must never remove a position"
    assert any(w.type == "time_relation_advisory" for w in result.warnings)


# ==========================================================================================
# Geschlecht
# ==========================================================================================
# GOÄ 1051 (real catalog Ziffer): "Beistand bei einer Fehlgeburt ohne operative Hilfe" — an
# obstetric service that is, as a matter of anatomy, never rendered for a male patient.

GENDER_RULE = GenderRestrictionRule(
    rule_id="gr_test_1051",
    ziffer="1051",
    allowed_gender="w",
    legal_basis="Leistungslegende Nr. 1051 (Geburtshilfe und Gynäkologie)",
    verified=True,
)


def test_gender_restriction_blocks_a_mismatched_patient(settings, catalog):
    rules = RuleStore(policy=UnverifiedRulePolicy.WARN, gender_restrictions=[GENDER_RULE])
    engine = _engine(settings, catalog, rules)

    result = engine.run(_extraction(sex="m"), make_bridge(("a1", "1051", 100, "1.0")))

    assert result.billable == []
    blocked = next(b for b in result.blocked if b.ziffer == "1051")
    assert blocked.reason == "gender_restricted"
    assert blocked.rule_id == "gr_test_1051"


def test_gender_restriction_admits_a_matching_patient(settings, catalog):
    rules = RuleStore(policy=UnverifiedRulePolicy.WARN, gender_restrictions=[GENDER_RULE])
    engine = _engine(settings, catalog, rules)

    result = engine.run(_extraction(sex="w"), make_bridge(("a1", "1051", 100, "1.0")))

    assert result.billable == ["1051"]


def test_gender_restriction_does_not_fire_when_gender_is_unknown(settings, catalog):
    """Absence is not evidence — the same reading LAYER 3 already gives an unknown `datum`."""
    rules = RuleStore(policy=UnverifiedRulePolicy.WARN, gender_restrictions=[GENDER_RULE])
    engine = _engine(settings, catalog, rules)

    result = engine.run(_extraction(sex=None), make_bridge(("a1", "1051", 100, "1.0")))

    assert result.billable == ["1051"]


# ==========================================================================================
# Alter
# ==========================================================================================
# GOÄ 26 (real catalog Ziffer): "Untersuchung zur Früherkennung von Krankheiten bei einem Kind
# bis zum vollendeten 14. Lebensjahr" — a paediatric screening capped at 13 inclusive.

AGE_RULE = AgeRestrictionRule(
    rule_id="age_test_26",
    ziffer="26",
    min_age=None,
    max_age=13,
    legal_basis="Leistungslegende Nr. 26",
    verified=True,
)


def test_age_restriction_blocks_a_patient_outside_the_band(settings, catalog):
    rules = RuleStore(policy=UnverifiedRulePolicy.WARN, age_restrictions=[AGE_RULE])
    engine = _engine(settings, catalog, rules)

    result = engine.run(_extraction(age=42), make_bridge(("a1", "26", 100, "1.0")))

    assert result.billable == []
    blocked = next(b for b in result.blocked if b.ziffer == "26")
    assert blocked.reason == "age_restricted"
    assert blocked.rule_id == "age_test_26"


def test_age_restriction_admits_a_patient_within_the_band(settings, catalog):
    rules = RuleStore(policy=UnverifiedRulePolicy.WARN, age_restrictions=[AGE_RULE])
    engine = _engine(settings, catalog, rules)

    result = engine.run(_extraction(age=8), make_bridge(("a1", "26", 100, "1.0")))

    assert result.billable == ["26"]


def test_age_restriction_does_not_fire_when_age_is_unknown(settings, catalog):
    rules = RuleStore(policy=UnverifiedRulePolicy.WARN, age_restrictions=[AGE_RULE])
    engine = _engine(settings, catalog, rules)

    result = engine.run(_extraction(age=None), make_bridge(("a1", "26", 100, "1.0")))

    assert result.billable == ["26"]


# ==========================================================================================
# RuleStore — loading the four new CSV families
# ==========================================================================================


def test_rule_store_loads_the_four_new_families(tmp_path: Path):
    (tmp_path / "quantity_limits.manual.csv").write_text(
        "rule_id,ziffer,max_count,window,legal_basis,quote,verified,verified_at,source\n"
        "cnt_1,4601,3,behandlungsfall,GOÄ Anmerkung zu Nummer 4601,quote,true,2026-09-12,"
        "manual_verification\n",
        encoding="utf-8",
    )
    (tmp_path / "time_relations.manual.csv").write_text(
        "rule_id,ziffer_a,ziffer_b,relation,min_hours,legal_basis,quote,verified,verified_at,"
        "source\ntr_1,7,410,same_day_excludes,0,basis,quote,false,,ai_verified:test\n",
        encoding="utf-8",
    )
    (tmp_path / "gender_restrictions.manual.csv").write_text(
        "rule_id,ziffer,allowed_gender,legal_basis,quote,verified,verified_at,source\n"
        "gr_1,1051,w,basis,quote,true,2026-09-12,manual_verification\n",
        encoding="utf-8",
    )
    (tmp_path / "age_restrictions.manual.csv").write_text(
        "rule_id,ziffer,min_age,max_age,legal_basis,quote,verified,verified_at,source\n"
        "age_1,26,,13,basis,quote,true,2026-09-12,manual_verification\n",
        encoding="utf-8",
    )

    store = RuleStore.load(tmp_path, policy=UnverifiedRulePolicy.WARN)

    assert store.quantity_limit("4601") == QuantityLimitRule(
        rule_id="cnt_1",
        ziffer="4601",
        max_count=3,
        window="behandlungsfall",
        legal_basis="GOÄ Anmerkung zu Nummer 4601",
        quote="quote",
        verified=True,
        verified_at="2026-09-12",
        source="manual_verification",
        csv_verified=True,
    )
    # The one unverified row loads, but is held back by the default `warn` policy — the same
    # safety property every other rule type has, applied here through the same `_admit`.
    assert store.time_relations == []
    assert any(r.rule_id == "tr_1" for r in store.time_relations_suppressed)

    assert store.gender_restriction("1051").allowed_gender == "w"
    age_rule = store.age_restriction("26")
    assert age_rule.min_age is None
    assert age_rule.max_age == 13


def test_rule_store_with_reviews_carries_the_new_families_forward_unchanged(tmp_path: Path):
    """`with_reviews` must not silently drop these four lists — see the comment on the merge."""
    (tmp_path / "quantity_limits.manual.csv").write_text(
        "rule_id,ziffer,max_count,window,legal_basis,quote,verified,verified_at,source\n"
        "cnt_1,4601,3,behandlungsfall,basis,quote,true,2026-09-12,manual_verification\n",
        encoding="utf-8",
    )
    store = RuleStore.load(tmp_path, policy=UnverifiedRulePolicy.WARN)
    reviewed = store.with_reviews({})

    assert reviewed.quantity_limit("4601") is not None


def test_rule_store_restrict_to_keeps_only_rules_touching_the_case(tmp_path: Path):
    (tmp_path / "quantity_limits.manual.csv").write_text(
        "rule_id,ziffer,max_count,window,legal_basis,quote,verified,verified_at,source\n"
        "cnt_1,4601,3,behandlungsfall,basis,quote,true,2026-09-12,manual_verification\n"
        "cnt_2,26,1,behandlungsfall,basis,quote,true,2026-09-12,manual_verification\n",
        encoding="utf-8",
    )
    store = RuleStore.load(tmp_path, policy=UnverifiedRulePolicy.WARN)
    restricted = store.restrict_to({"4601"})

    assert [r.ziffer for r in restricted.quantity_limits] == ["4601"]
