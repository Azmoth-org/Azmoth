"""Boundary semantics for the three enforceable ADR-002 families, against the real corpus.

`tests/test_coverage_sprint_batch2.py` proves each shipped family fires at all: one blocked case
and one admitted case per family. This file is the sweep around the edge — at the limit, one
either side of it, and every way the input can be absent or unusual — because an off-by-one in a
`>=` or a band boundary is exactly the class of defect a two-point test cannot see.

Every test loads the shipped `data/rules/` through the `souffle` fixture, so a failure here means
the *data as committed* misbehaves, not that a hand-built fixture does.

Both halves of each outcome are asserted: the decision (`billable` / `blocked`) **and** the audit
trail the decision is justified by (`reason`, `rule_id`, `legal_basis`, `detail`). A block with
the right verdict and an empty `legal_basis` is not an auditable block, and this repository sells
auditability.

Two absences are load-bearing and are pinned here rather than left to documentation:

* `patient_age` / `patient_gender` are 0-or-1-row relations. Absent means *unknown*, and LAYER
  3.7/3.8 never treat unknown as a mismatch. Every restricted Ziffer is therefore **admitted**
  when the patient attribute is missing. That is permissive on the billing side and is the
  documented, deliberate reading ("silence is not evidence") — pinned so that a future change
  from "admit" to "block" has to be a decision somebody makes on purpose.
* `history_count` is empty for every caller that does not track patient history. With no history
  the Mengenbegrenzung layer concludes nothing, so a first claim is always admitted.
"""

from __future__ import annotations

import pytest

from app.schemas import ClinicalExtraction
from tests.conftest import make_bridge


def _extraction(*, age: int | None = None, sex: str | None = None, setting: str = "ambulant"):
    return ClinicalExtraction.model_validate(
        {"patient": {"age": age, "sex": sex, "setting": setting}, "justification_factors": []}
    )


def _blocked(result, ziffer: str):
    return next((b for b in result.blocked if b.ziffer == ziffer), None)


# ==============================================================================================
# Mengenbegrenzung — LAYER 3.5, `Count >= Max`
# ==============================================================================================

#: (Ziffer, max_count) exactly as `data/rules/quantity_limits.manual.csv` ships them.
QUANTITY_ROWS = [
    ("4", 1),
    ("380", 30),
    ("381", 20),
    ("382", 50),
    ("385", 20),
    ("386", 20),
    ("387", 40),
    ("388", 10),
    ("390", 20),
    ("807", 1),
    ("842", 1),
    ("860", 1),
    ("4601", 3),
]


@pytest.mark.parametrize(("ziffer", "max_count"), QUANTITY_ROWS)
def test_a_history_one_below_the_cap_is_admitted(souffle, ziffer, max_count):
    """`Count >= Max` blocks, so `Max - 1` prior occurrences must still admit the next claim."""
    result = souffle.run(
        _extraction(),
        make_bridge(("a1", ziffer, 100, "1.0")),
        history_counts={ziffer: max_count - 1},
    )
    assert ziffer in result.billable
    assert _blocked(result, ziffer) is None


@pytest.mark.parametrize(("ziffer", "max_count"), QUANTITY_ROWS)
def test_a_history_exactly_at_the_cap_is_blocked(souffle, ziffer, max_count):
    """The cap counts what is already on record: at `Max`, the next one is the overflow."""
    result = souffle.run(
        _extraction(),
        make_bridge(("a1", ziffer, 100, "1.0")),
        history_counts={ziffer: max_count},
    )
    assert ziffer not in result.billable
    blocked = _blocked(result, ziffer)
    assert blocked is not None
    assert blocked.reason == "quantity_exceeded"
    assert blocked.rule_id == f"cnt_man_{ziffer}"
    assert blocked.legal_basis, "a quantity block must carry the legal basis it rests on"
    assert blocked.detail == f"history_count:{max_count}/max:{max_count}"


@pytest.mark.parametrize(("ziffer", "max_count"), QUANTITY_ROWS)
def test_a_history_above_the_cap_is_blocked(souffle, ziffer, max_count):
    result = souffle.run(
        _extraction(),
        make_bridge(("a1", ziffer, 100, "1.0")),
        history_counts={ziffer: max_count + 5},
    )
    assert ziffer not in result.billable
    assert _blocked(result, ziffer).reason == "quantity_exceeded"


@pytest.mark.parametrize(("ziffer", "max_count"), QUANTITY_ROWS)
def test_no_history_at_all_admits_the_claim(souffle, ziffer, max_count):
    """The layer is inert without `history_count` — the state every production caller is in."""
    result = souffle.run(_extraction(), make_bridge(("a1", ziffer, 100, "1.0")))
    assert ziffer in result.billable


@pytest.mark.parametrize(("ziffer", "max_count"), QUANTITY_ROWS)
def test_an_explicitly_empty_history_admits_the_claim(souffle, ziffer, max_count):
    result = souffle.run(_extraction(), make_bridge(("a1", ziffer, 100, "1.0")), history_counts={})
    assert ziffer in result.billable


def test_a_zero_history_count_is_not_read_as_a_cap_hit(souffle):
    """`0 >= 1` is false; GOÄ 4's cap is 1, so an explicit zero must stay admitted."""
    result = souffle.run(
        _extraction(), make_bridge(("a1", "4", 100, "1.0")), history_counts={"4": 0}
    )
    assert "4" in result.billable


def test_history_for_a_different_ziffer_does_not_block(souffle):
    """`history_count` is keyed by Ziffer; 4601's history says nothing about 4."""
    result = souffle.run(
        _extraction(), make_bridge(("a1", "4", 100, "1.0")), history_counts={"4601": 99}
    )
    assert "4" in result.billable


def test_history_for_an_unclaimed_ziffer_is_dropped_from_the_fact_base(souffle):
    """`build_fact_rows` filters `history_count` to relevant Ziffern, so history about a Ziffer
    nobody claimed cannot block anything."""
    result = souffle.run(
        _extraction(), make_bridge(("a1", "4", 100, "1.0")), history_counts={"860": 50}
    )
    assert result.billable == ["4"]
    assert result.blocked == []


def test_a_ziffer_with_no_quantity_rule_is_never_quantity_blocked(souffle):
    """GOÄ 1 carries no `cnt_man_` row; no amount of history may invent a cap for it."""
    result = souffle.run(
        _extraction(), make_bridge(("a1", "1", 100, "1.0")), history_counts={"1": 500}
    )
    assert "1" in result.billable


def test_two_claims_of_the_same_ziffer_on_one_invoice_are_not_a_quantity_block(souffle):
    """LAYER 3.5 reads `history_count` — prior invoices — not the multiplicity of this one.
    Same-invoice repetition is a different question, and this layer must not answer it."""
    result = souffle.run(
        _extraction(),
        make_bridge(("a1", "4", 100, "1.0"), ("a2", "4", 100, "1.0")),
        history_counts={"4": 0},
    )
    assert "4" in result.billable
    assert _blocked(result, "4") is None


# ==============================================================================================
# Geschlecht — LAYER 3.7, `G != Allowed`
# ==============================================================================================

#: (Ziffer, allowed_gender) exactly as `data/rules/gender_restrictions.manual.csv` ships them.
GENDER_ROWS = [
    ("27", "w"),
    ("1700", "m"),
    ("1701", "m"),
    ("1702", "m"),
    ("1703", "m"),
    ("1704", "m"),
    ("1708", "m"),
    ("1709", "w"),
    ("1710", "w"),
    ("1711", "w"),
    ("1728", "m"),
    ("1729", "m"),
    ("1730", "w"),
    ("1731", "w"),
    ("1782", "w"),
]


@pytest.mark.parametrize(("ziffer", "allowed"), GENDER_ROWS)
def test_the_matching_gender_is_admitted(souffle, ziffer, allowed):
    result = souffle.run(_extraction(sex=allowed), make_bridge(("a1", ziffer, 100, "1.0")))
    assert ziffer in result.billable
    assert _blocked(result, ziffer) is None


@pytest.mark.parametrize(("ziffer", "allowed"), GENDER_ROWS)
def test_the_opposite_gender_is_blocked_with_a_full_audit_trail(souffle, ziffer, allowed):
    other = "m" if allowed == "w" else "w"
    result = souffle.run(_extraction(sex=other), make_bridge(("a1", ziffer, 100, "1.0")))

    assert ziffer not in result.billable
    blocked = _blocked(result, ziffer)
    assert blocked is not None
    assert blocked.reason == "gender_restricted"
    assert blocked.rule_id == f"gr_man_{ziffer}"
    assert blocked.legal_basis, "a gender block must carry the legal basis it rests on"
    assert blocked.detail == f"patient_gender:{other}/allowed:{allowed}"


@pytest.mark.parametrize(("ziffer", "allowed"), GENDER_ROWS)
def test_an_unknown_gender_is_admitted_not_blocked(souffle, ziffer, allowed):
    """`patient_gender` absent = unknown, and unknown is never a mismatch. This is the state
    every PADnext audit is in today: `_build_group_audit_input` builds `Patient(setting=...)`
    and never sets `sex`."""
    result = souffle.run(_extraction(sex=None), make_bridge(("a1", ziffer, 100, "1.0")))
    assert ziffer in result.billable
    assert _blocked(result, ziffer) is None


@pytest.mark.parametrize(("ziffer", "allowed"), GENDER_ROWS)
def test_a_divers_patient_is_blocked_by_every_gendered_ziffer(souffle, ziffer, allowed):
    """`Sex` is `m`/`w`/`d`, and LAYER 3.7 blocks on any `G != Allowed` — so `d` is blocked by
    every row in the family, including the urological ones whose restriction is anatomical
    rather than administrative.

    This is what the shipped rules do; it is not obviously what they should do, and neither
    ADR-002 nor the batch 2 report takes a position on `d`. Pinned so the behaviour is visible
    and any change to it is deliberate — see the validation report's open questions.
    """
    result = souffle.run(_extraction(sex="d"), make_bridge(("a1", ziffer, 100, "1.0")))
    assert ziffer not in result.billable
    blocked = _blocked(result, ziffer)
    assert blocked.reason == "gender_restricted"
    assert blocked.detail == f"patient_gender:d/allowed:{allowed}"


def test_a_ziffer_with_no_gender_rule_is_never_gender_blocked(souffle):
    for sex in ("m", "w", "d", None):
        result = souffle.run(_extraction(sex=sex), make_bridge(("a1", "1", 100, "1.0")))
        assert "1" in result.billable, f"GOÄ 1 blocked for sex={sex!r}"


def test_gender_rules_do_not_leak_across_ziffern(souffle):
    """A male patient claiming 1700 (male-only) and 1730 (female-only) together loses exactly
    one of them."""
    result = souffle.run(
        _extraction(sex="m"), make_bridge(("a1", "1700", 100, "1.0"), ("a2", "1730", 100, "1.0"))
    )
    assert result.billable == ["1700"]
    assert [b.ziffer for b in result.blocked] == ["1730"]


# ==============================================================================================
# Alter — LAYER 3.8, `Age < MinAge` or `Age > MaxAge`
# ==============================================================================================

#: (Ziffer, min_age, max_age) exactly as `data/rules/age_restrictions.manual.csv` ships them.
#: `None` is the unbounded side, emitted as the `NO_MIN_AGE`/`NO_MAX_AGE` sentinel.
AGE_ROWS = [
    ("26", 2, 13),
    ("250a", None, 7),
    ("273", None, 3),
    ("412", None, 1),
    ("413", None, 1),
    ("1063", None, 9),
    ("5041", None, 13),
    ("K1", None, 3),
    ("K2", None, 3),
]


@pytest.mark.parametrize(("ziffer", "min_age", "max_age"), AGE_ROWS)
def test_an_age_exactly_at_the_upper_bound_is_admitted(souffle, ziffer, min_age, max_age):
    """`max_age` is inclusive: "bis zum vollendeten 14. Lebensjahr" is satisfied at 13."""
    result = souffle.run(_extraction(age=max_age), make_bridge(("a1", ziffer, 100, "1.0")))
    assert ziffer in result.billable


@pytest.mark.parametrize(("ziffer", "min_age", "max_age"), AGE_ROWS)
def test_one_year_above_the_upper_bound_is_blocked(souffle, ziffer, min_age, max_age):
    result = souffle.run(_extraction(age=max_age + 1), make_bridge(("a1", ziffer, 100, "1.0")))
    assert ziffer not in result.billable
    blocked = _blocked(result, ziffer)
    assert blocked is not None
    assert blocked.reason == "age_restricted"
    assert blocked.rule_id == f"age_man_{ziffer}"
    assert blocked.legal_basis, "an age block must carry the legal basis it rests on"
    assert f"patient_age:{max_age + 1}" in blocked.detail


@pytest.mark.parametrize(("ziffer", "min_age", "max_age"), AGE_ROWS)
def test_an_age_well_below_the_upper_bound_is_admitted_unless_a_min_applies(
    souffle, ziffer, min_age, max_age
):
    """A newborn is inside every one of these bands except GOÄ 26's, whose `min_age` is 2."""
    result = souffle.run(_extraction(age=0), make_bridge(("a1", ziffer, 100, "1.0")))
    if min_age is None:
        assert ziffer in result.billable
    else:
        assert ziffer not in result.billable


@pytest.mark.parametrize(("ziffer", "min_age", "max_age"), AGE_ROWS)
def test_an_unknown_age_is_admitted_not_blocked(souffle, ziffer, min_age, max_age):
    """`patient_age` absent = unknown. This is the state every PADnext audit is in: the ADR is
    explicit that age is not derivable from a delivery without parsing a date of birth."""
    result = souffle.run(_extraction(age=None), make_bridge(("a1", ziffer, 100, "1.0")))
    assert ziffer in result.billable
    assert _blocked(result, ziffer) is None


@pytest.mark.parametrize("ziffer", [z for z, lo, _ in AGE_ROWS if lo is None])
def test_an_unbounded_lower_side_never_blocks_a_young_patient(souffle, ziffer):
    """`NO_MIN_AGE = 0` is the sentinel, and `Age < 0` is unsatisfiable for a valid
    `Patient.age` — so an empty `min_age` cannot block anybody."""
    for age in (0, 1):
        result = souffle.run(_extraction(age=age), make_bridge(("a1", ziffer, 100, "1.0")))
        assert ziffer in result.billable, f"{ziffer} blocked at age {age} with no min_age"


def test_the_upper_sentinel_does_not_cap_a_real_patient(souffle):
    """`NO_MAX_AGE = 999` sits above `Patient.age`'s `le=130`, so a rule with only a `min_age`
    can never block on the upper side. GOÄ 26 is the only shipped row with a lower bound, and it
    has an upper bound too — so this is asserted against the sentinel's arithmetic directly."""
    from app.solvers.souffle_facts import NO_MAX_AGE, NO_MIN_AGE

    assert NO_MIN_AGE == 0
    assert NO_MAX_AGE == 999
    result = souffle.run(_extraction(age=130), make_bridge(("a1", "1", 100, "1.0")))
    assert "1" in result.billable


@pytest.mark.parametrize("age", [-1, 131, 200])
def test_an_age_outside_the_contract_is_rejected_before_the_engine(age):
    """`Patient.age` is `ge=0, le=130`. An impossible age is a validation error, not a silently
    clamped fact — the engine never sees it."""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        _extraction(age=age)


def test_goae_26_blocks_a_one_year_old(souffle):
    """The shipped `age_man_26` carries `min_age: 2`, so a one-year-old is refused GOÄ 26.

    This is a **finding**, pinned as the behaviour that actually ships rather than as the
    behaviour that is correct. `min_age` was read out of "Die Leistung nach Nummer 26 ist ab dem
    vollendeten 2. Lebensjahr je Kalenderjahr höchstens einmal berechnungsfähig." — a sentence
    that limits how *often* the service may be billed from age 2 onward. It does not exclude
    younger children, and the Leistungslegende bounds only the upper side ("bei einem Kind bis
    zum vollendeten 14. Lebensjahr"). See the validation report, finding F1: if that row is
    corrected, this test is the one that must change with it, deliberately.
    """
    result = souffle.run(_extraction(age=1), make_bridge(("a1", "26", 100, "1.0")))
    assert "26" not in result.billable
    blocked = _blocked(result, "26")
    assert blocked.reason == "age_restricted"
    assert blocked.rule_id == "age_man_26"
    assert blocked.detail == "patient_age:1/band:2-13"


def test_a_ziffer_with_no_age_rule_is_never_age_blocked(souffle):
    for age in (0, 1, 50, 130, None):
        result = souffle.run(_extraction(age=age), make_bridge(("a1", "1", 100, "1.0")))
        assert "1" in result.billable, f"GOÄ 1 blocked at age {age!r}"


# ==============================================================================================
# Zeitbeziehung — no shipped rows; prove the layer stays silent
# ==============================================================================================


def test_the_shipped_corpus_has_no_time_relation_rules(rules):
    """`time_relations.manual.csv` is header-only this batch. The file must still be loaded —
    that is what the parity hardening in `test_golden_snapshot.py` exists to allow."""
    assert rules.time_relations == []
    assert "time_relations.manual.csv" in rules.files_loaded


def test_no_time_window_is_inferred_for_ziffern_billed_on_the_same_day(souffle):
    """With zero rules loaded, LAYER 3.6 must conclude nothing — no block and no advisory — even
    for two Ziffern that do sit in the same clinical family."""
    result = souffle.run(
        _extraction(),
        make_bridge(("a1", "380", 100, "1.0"), ("a2", "381", 100, "1.0")),
    )
    assert set(result.billable) == {"380", "381"}
    assert [b for b in result.blocked if b.reason == "time_relation_blocked"] == []


def test_no_time_relation_advisory_is_produced(souffle):
    """`min_hours_apart` is advisory-only and has no rows either; nothing may appear."""
    result = souffle.run(
        _extraction(),
        make_bridge(("a1", "385", 100, "1.0"), ("a2", "386", 100, "1.0")),
    )
    assert set(result.billable) == {"385", "386"}
    assert result.blocked == []


# ==============================================================================================
# Layer ordering — a block in an earlier layer must not be masked by a later one
# ==============================================================================================


def test_gender_and_age_can_block_the_same_ziffer_independently(souffle):
    """GOÄ 26 has an age rule and no gender rule; GOÄ 27 has a gender rule and no age rule.
    Claiming both as a 42-year-old man loses both, each for its own reason."""
    result = souffle.run(
        _extraction(age=42, sex="m"),
        make_bridge(("a1", "26", 100, "1.0"), ("a2", "27", 100, "1.0")),
    )
    assert result.billable == []
    reasons = {b.ziffer: b.reason for b in result.blocked}
    assert reasons == {"26": "age_restricted", "27": "gender_restricted"}


def test_the_three_families_name_pairwise_disjoint_ziffern(rules):
    """No shipped Ziffer carries rules from two Batch 2 families at once — 13 + 15 + 9 Ziffern,
    37 distinct.

    Worth pinning for two reasons. It is why the coverage arithmetic can add the three families
    without double-counting inside the batch (the overlap that *does* exist is with the older
    exclusion/Zielleistung/specificity/factor-cap rules, and is handled separately). And it is
    why cross-layer precedence between 3.5, 3.7 and 3.8 cannot be exercised against real data at
    all: there is no Ziffer for which two of these layers could both fire. The synthetic
    fixtures in `tests/test_complex_constraints.py` are the only place that ordering is tested.
    """
    quantity = {r.ziffer for r in rules.quantity_limits}
    gender = {r.ziffer for r in rules.gender_restrictions}
    age = {r.ziffer for r in rules.age_restrictions}

    assert quantity & gender == set()
    assert quantity & age == set()
    assert gender & age == set()
    assert len(quantity | gender | age) == 37


def test_a_blocked_ziffer_is_reported_exactly_once(souffle):
    """Whatever the reason, one Ziffer produces one `BlockedCode` — a position reported twice
    would double-count in the review UI and in the audit trail."""
    result = souffle.run(
        _extraction(age=42, sex="m"),
        make_bridge(("a1", "26", 100, "1.0"), ("a2", "27", 100, "1.0")),
    )
    ziffern = [b.ziffer for b in result.blocked]
    assert sorted(ziffern) == ["26", "27"]
    assert len(ziffern) == len(set(ziffern))
