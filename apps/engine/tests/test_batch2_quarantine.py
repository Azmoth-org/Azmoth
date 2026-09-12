"""The quarantine list from `docs/content/coverage-sprint-report-batch2.md` §3, enforced.

The batch 2 report examined 81 Mengenbegrenzung, 5 Zeitbeziehung, 18 Geschlecht and 36 Alter
candidate sentences and shipped 37 of them. The other 103 were held out for a stated reason —
an unsupported window, a qualitative age word with no number, a permissive sentence that would
invert if encoded as an exclusion, a regex false positive.

A quarantine that lives only in prose decays: the next batch re-runs the same scan, sees the same
sentence, and has nothing that says "this one was looked at and rejected, here is why". So the
list is transcribed here as data and checked two ways.

**Not encoded.** No quarantined Ziffer may carry a rule in the family it was quarantined *for*.
The check is deliberately family-scoped, because several Ziffern are quarantined in one family
and shipped in another, and conflating them would be wrong in both directions:

    GOÄ 26   quarantined for Mengenbegrenzung ("je Kalenderjahr"), shipped for Alter
    GOÄ 807  quarantined for Alter (qualitative "Kind"), shipped for Mengenbegrenzung
    GOÄ 887  quarantined for both, shipped for neither

**Not executed.** Claiming a quarantined Ziffer through the real engine must not produce a block
from the layer it was held out of. This is the half that catches an accidental re-encoding: a row
added in a future batch under the wrong window would pass a "no rule exists" assertion the moment
the rule exists, and would still have to explain itself to the engine-level test below.
"""

from __future__ import annotations

import pytest

from app.schemas import ClinicalExtraction
from tests.conftest import make_bridge

# ==============================================================================================
# §3 of the report, transcribed. Grouped by the stated reason, because the reason is the content.
# ==============================================================================================

QUARANTINED_QUANTITY: dict[str, tuple[str, ...]] = {
    "conditional justification duty, not a prohibition": ("3", "4610"),
    "unsupported window — je Sitzung / je Behandlungstag": (
        "351", "360", "361", "420", "440", "442", "443", "444", "445", "446", "447", "448",
        "449", "569", "626", "627", "628", "629", "5111", "5135", "5190", "5265", "5315",
        "5316", "5328", "5335", "5442",
    ),
    "unsupported window — je Kalenderjahr or a stated N-month period": (
        "15", "21", "26", "30", "31", "33", "34",
    ),
    "conditioned on 'aus demselben Untersuchungsmaterial' — not visible on an invoice line": (
        "3511", "3550", "4530", "4531", "4533", "4538", "4539", "4551", "4715", "4716",
    ),
    "conditioned on distinguishing the fungus species ('je Pilz')": ("4717",),
    "caps group-session participants, not one patient's billing frequency": (
        "847", "862", "864", "871", "887",
    ),
    "anti-fragmentation of one imaging event, not a cross-quarter cap": (
        "5000", "5011", "5021", "5031", "5035",
    ),
    "cross-code cumulative total, not one Ziffer's own count": ("391",),
    "once per simultaneously-treated group, not a per-patient repeat cap": ("560",),
    "ambiguous or undefined window": ("77", "430", "5803", "5851"),
    "not a rule about this Ziffer — a pricing-provenance footnote": (
        "4572", "4573", "4574", "4575", "4576",
    ),
}

QUARANTINED_TIME_RELATION: dict[str, tuple[str, ...]] = {
    "permissive, not exclusionary — encoding it would forbid what the text authorises": (
        "45", "46",
    ),
    "names no specific counterpart Ziffer to relate to": ("247",),
    "stated in minutes; TimeRelationRule.min_hours is whole hours": ("726",),
    "regex false positive ('Binnenohrmuskeln' contains 'binnen')": ("1407",),
}

QUARANTINED_GENDER: dict[str, tuple[str, ...]] = {
    "one optional organ system within a general comprehensive exam, not a gate": ("6", "7"),
    "illustrative example specimen source ('z.B.'), not an eligibility restriction": ("4851",),
}

QUARANTINED_AGE: dict[str, tuple[str, ...]] = {
    "'Neugeborenes' with no number — whole years cannot express ~0–28 days": (
        "25", "281", "283", "566", "1040", "2571", "3287",
    ),
    "qualitative 'Kind'/'Jugendlicher' with no attached number": (
        "807", "817", "835", "885", "886", "887", "1080", "1123a", "1294",
    ),
    "qualitative 'Säugling'/'Kleinkind' with no attached number": (
        "716", "717", "2505", "2525", "3127", "3171", "3189",
    ),
    "illustrative example only ('z.B. bei einem Säugling')": ("2429",),
    "part of a conditional fee adjustment, not a gate on who may be billed": ("30",),
    "explicitly a guideline, not a cutoff ('in der Regel')": ("1406",),
    "numeric band exists only by reference to an external statute": ("32",),
}


def _flat(groups: dict[str, tuple[str, ...]]) -> list[str]:
    return [ziffer for members in groups.values() for ziffer in members]


def _cases(groups: dict[str, tuple[str, ...]]) -> list[tuple[str, str]]:
    return [(z, reason) for reason, members in groups.items() for z in members]


def _extraction(*, age: int | None = None, sex: str | None = None):
    return ClinicalExtraction.model_validate(
        {"patient": {"age": age, "sex": sex, "setting": "ambulant"}, "justification_factors": []}
    )


# ==============================================================================================
# The list itself matches the report's stated totals
# ==============================================================================================


@pytest.mark.parametrize(
    ("groups", "expected", "family"),
    [
        (QUARANTINED_QUANTITY, 68, "Mengenbegrenzung"),
        (QUARANTINED_TIME_RELATION, 5, "Zeitbeziehung"),
        (QUARANTINED_GENDER, 3, "Geschlecht"),
        (QUARANTINED_AGE, 27, "Alter"),
    ],
)
def test_the_transcribed_quarantine_matches_the_reported_count(groups, expected, family):
    """§3 publishes a count per family; the transcription must add up to it, with no duplicates
    inside a family."""
    flat = _flat(groups)
    assert len(flat) == expected, f"{family}: transcribed {len(flat)}, report says {expected}"
    assert len(set(flat)) == expected, f"{family}: duplicate Ziffer in the quarantine list"


def test_every_quarantined_ziffer_exists_in_the_catalog(catalog):
    """A quarantine entry naming a Ziffer that does not exist would be a transcription error,
    and would make the 'not encoded' checks below vacuous for that row."""
    missing = [
        z
        for groups in (
            QUARANTINED_QUANTITY, QUARANTINED_TIME_RELATION, QUARANTINED_GENDER, QUARANTINED_AGE
        )
        for z in _flat(groups)
        if catalog.get(z) is None
    ]
    assert missing == [], f"quarantined Ziffern absent from the catalog: {sorted(set(missing))}"


# ==============================================================================================
# Not encoded — family-scoped
# ==============================================================================================


@pytest.mark.parametrize(("ziffer", "reason"), _cases(QUARANTINED_QUANTITY))
def test_a_quarantined_quantity_ziffer_has_no_quantity_rule(rules, ziffer, reason):
    encoded = {r.ziffer for r in rules.quantity_limits}
    assert ziffer not in encoded, f"GOÄ {ziffer} was quarantined ({reason}) but carries a rule"


@pytest.mark.parametrize(("ziffer", "reason"), _cases(QUARANTINED_GENDER))
def test_a_quarantined_gender_ziffer_has_no_gender_rule(rules, ziffer, reason):
    encoded = {r.ziffer for r in rules.gender_restrictions}
    assert ziffer not in encoded, f"GOÄ {ziffer} was quarantined ({reason}) but carries a rule"


@pytest.mark.parametrize(("ziffer", "reason"), _cases(QUARANTINED_AGE))
def test_a_quarantined_age_ziffer_has_no_age_rule(rules, ziffer, reason):
    encoded = {r.ziffer for r in rules.age_restrictions}
    assert ziffer not in encoded, f"GOÄ {ziffer} was quarantined ({reason}) but carries a rule"


@pytest.mark.parametrize(("ziffer", "reason"), _cases(QUARANTINED_TIME_RELATION))
def test_a_quarantined_time_relation_ziffer_has_no_time_rule(rules, ziffer, reason):
    named = {z for r in rules.time_relations for z in (r.ziffer_a, r.ziffer_b)}
    assert ziffer not in named, f"GOÄ {ziffer} was quarantined ({reason}) but carries a rule"


def test_quarantining_in_one_family_does_not_block_shipping_in_another(rules):
    """The three overlaps are real and intended; pinned so a future tightening of the checks
    above cannot quietly delete a shipped rule to satisfy a quarantine entry."""
    assert "26" in {r.ziffer for r in rules.age_restrictions}
    assert "26" not in {r.ziffer for r in rules.quantity_limits}

    assert "807" in {r.ziffer for r in rules.quantity_limits}
    assert "807" not in {r.ziffer for r in rules.age_restrictions}

    assert "887" not in {r.ziffer for r in rules.quantity_limits}
    assert "887" not in {r.ziffer for r in rules.age_restrictions}


# ==============================================================================================
# Not executed — against the real engine
# ==============================================================================================

#: A sample across every quarantine reason, kept small because each case spawns Soufflé. The
#: exhaustive "no rule exists" assertions above cover all 103; these prove the engine agrees.
ENGINE_SAMPLE_QUANTITY = ("3", "440", "26", "4530", "4717", "847", "5000", "391", "560", "77", "4572")


@pytest.mark.parametrize("ziffer", ENGINE_SAMPLE_QUANTITY)
def test_a_quarantined_quantity_ziffer_is_not_capped_by_the_engine(souffle, ziffer):
    """No history, however large, may block a Ziffer whose cap was held out — the engine must
    not infer a limit from a sentence nobody encoded."""
    result = souffle.run(
        _extraction(), make_bridge(("a1", ziffer, 100, "1.0")), history_counts={ziffer: 999}
    )
    quantity_blocks = [
        b for b in result.blocked if b.ziffer == ziffer and b.reason == "quantity_exceeded"
    ]
    assert quantity_blocks == [], f"GOÄ {ziffer} was quantity-blocked despite being quarantined"


@pytest.mark.parametrize("ziffer", ("6", "7", "4851"))
@pytest.mark.parametrize("sex", ("m", "w", "d"))
def test_a_quarantined_gender_ziffer_is_not_gender_blocked(souffle, ziffer, sex):
    """GOÄ 4851's "z.B. aus dem Genitale der Frau" must not become a female-only gate."""
    result = souffle.run(_extraction(sex=sex), make_bridge(("a1", ziffer, 100, "1.0")))
    gender_blocks = [
        b for b in result.blocked if b.ziffer == ziffer and b.reason == "gender_restricted"
    ]
    assert gender_blocks == [], f"GOÄ {ziffer} was gender-blocked for sex={sex}"


@pytest.mark.parametrize("ziffer", ("25", "807", "716", "2429", "1406", "32"))
@pytest.mark.parametrize("age", (0, 7, 42, 90))
def test_a_quarantined_age_ziffer_is_not_age_blocked(souffle, ziffer, age):
    """"Neugeborenes", "Säugling" and "in der Regel bis zum vollendeten 7. Lebensjahr" were all
    held out. None of them may become a band the engine enforces at any age."""
    result = souffle.run(_extraction(age=age), make_bridge(("a1", ziffer, 100, "1.0")))
    age_blocks = [b for b in result.blocked if b.ziffer == ziffer and b.reason == "age_restricted"]
    assert age_blocks == [], f"GOÄ {ziffer} was age-blocked at age {age}"


def test_no_clinical_fact_is_invented_for_a_patient_with_no_attributes(souffle):
    """The conservative-behaviour claim, stated as one assertion: with age and sex both unknown
    and no history supplied — the state every PADnext audit is in — none of the three Batch 2
    layers may contribute a block to any Ziffer they name."""
    sampled = ["4", "4601", "27", "1700", "26", "250a", "K1"]
    result = souffle.run(
        _extraction(),
        make_bridge(*[(f"a{i}", z, 100, "1.0") for i, z in enumerate(sampled)]),
    )
    batch2_reasons = {"quantity_exceeded", "gender_restricted", "age_restricted"}
    offenders = [(b.ziffer, b.reason) for b in result.blocked if b.reason in batch2_reasons]
    assert offenders == [], f"a Batch 2 layer fired without the fact it needs: {offenders}"


# ==============================================================================================
# The public counts do not include quarantined or advisory functionality
# ==============================================================================================


def test_quarantined_ziffern_are_not_in_the_published_enforced_count(rules):
    """`enforced_rule_count` sums exclusions/Zielleistung/specificity/factor caps only, so no
    Batch 2 row — shipped or quarantined — can inflate it."""
    assert rules.enforced_rule_count() == (
        len(rules.exclusions)
        + len(rules.zielleistung)
        + len(rules.specificity)
        + len(rules.factor_caps)
    )
    for family in ("quantity_limits", "gender_restrictions", "age_restrictions", "time_relations"):
        for rule in getattr(rules, family):
            assert rule not in rules.constraint_rules()


def test_the_advisory_time_relation_kind_is_not_counted_as_enforced(rules):
    """`min_hours_apart` never removes a position. With zero rows it cannot be miscounted today;
    the assertion exists so that shipping one later has to confront this line."""
    advisory = [r for r in rules.time_relations if r.relation == "min_hours_apart"]
    assert advisory == []
    assert all(r not in rules.constraint_rules() for r in rules.time_relations)
