"""Coverage-sprint batch 3: the *Allgemeine Bestimmungen* rules, run against the real engine.

See `docs/content/coverage-sprint-report-batch3.md`. Batch 3 recovered the GOÄ's 50 section-level
provisions — the paragraphs printed under a chapter heading, which `scripts/import_goae.py` drops
because they belong to no single Ziffer — and turned seventeen of them into 497 exclusion rows and
18 factor caps (`scripts/build_batch3_rules.py`).

Like `tests/test_coverage_sprint_batch2.py` and unlike `tests/test_complex_constraints.py`, every
test here runs against the **real corpus** through the `souffle` fixture. Batch 3's rows are
generated rather than typed, which removes transcription error and introduces a different one: a
misread `PROVISIONS` entry is wrong 182 times, silently, and a generator emits perfectly
well-formed CSV for a sentence it read wrong. Nothing but claiming the Ziffern on an invoice and
watching the engine catches that.

Each provision gets three cases, which is what "tested" has to mean for an exclusion:

  * **positive** — the two Ziffern together: the rule fires, and cites itself;
  * **negative** — the blocked Ziffer *alone*: it bills, so the rule is a statement about a pair
    and not a blanket ban on a position;
  * **boundary** — the nearest Ziffer *outside* the cited range or list: nothing fires, so the
    expansion is exactly what the sentence says and not one position wider.

The boundary case is the one that earns its keep. "410 bis 418" and "410 bis 420" produce
identical-looking CSV, pass every citation check (the quote is verbatim either way) and differ
only in whether GOÄ 420 is silently unbillable beside every single-organ ultrasound.

**On the Ziffern chosen.** Several obvious picks are unusable here and the substitutes are not
arbitrary: GOÄ 412, 413, 250a, K 1 and K 2 carry *batch 2* age restrictions, so an extraction
with no `patient.age` has them blocked by `age_man_*` before any batch-3 rule is reached. Where
one of those is the point of the test (the K 1 / K 2 caps) the extraction carries an age; where it
is only a stand-in (a second sonography position, a lettered sibling inside a range) an
unrestricted Ziffer is used instead, so a failure here means a batch-3 rule moved and cannot mean
a batch-2 rule did.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.schemas import ClinicalExtraction
from tests.conftest import make_extraction, one_act_per_ziffer


def _extraction(*, age: int | None = None, sex: str | None = None):
    return ClinicalExtraction.model_validate(
        {"patient": {"age": age, "sex": sex, "setting": "ambulant"}, "justification_factors": []}
    )


def _blocked(result, ziffer: str):
    return next((b for b in result.blocked if b.ziffer == ziffer), None)


# ==========================================================================================
# Abschnitt B, Nr. 8 — the general examination swallows its organ-specific parts
# "Neben einer Leistung nach Nummer 5, 6, 7 oder 8 sind die Leistungen nach den Nummern 600,
#  601, 1203, 1204, 1228, 1240, 1400, 1401 und 1414 nicht berechnungsfähig."
# ==========================================================================================


def test_the_hearing_test_is_blocked_beside_the_general_examination(souffle):
    result = souffle.run(make_extraction(), one_act_per_ziffer("6", "1400"))

    assert result.billable == ["6"]
    blocked = _blocked(result, "1400")
    assert blocked is not None, "GOÄ 1400 should be blocked beside GOÄ 6"
    assert blocked.rule_id == "excl_b3_6_1400"
    assert blocked.legal_basis == "GOÄ Allgemeine Bestimmungen zu Abschnitt B, Nr. 8"


def test_the_hearing_test_bills_on_its_own(souffle):
    """The negative half: GOÄ 1400 is not an unbillable position, it is unbillable *beside* 5–8."""
    result = souffle.run(make_extraction(), one_act_per_ziffer("1400"))

    assert result.billable == ["1400"]
    assert result.blocked == []


def test_a_ziffer_next_to_the_cited_list_is_untouched(souffle):
    """GOÄ 602 sits immediately after two cited numbers (600, 601) and is not one of them.

    This provision names a *list*, not a range. Reading "600, 601, …" as "600 bis 601" happens to
    be harmless; reading it as "600 bis 617" — the end of the Herz/Kreislauf block — would make a
    dozen cardiological positions silently unbillable beside a routine examination, and would look
    exactly like this test's setup until the test ran.
    """
    result = souffle.run(make_extraction(), one_act_per_ziffer("6", "602"))

    assert sorted(result.billable) == ["6", "602"]
    assert result.blocked == []


# ==========================================================================================
# Abschnitt C VI, Nr. 3 — the sonography positions are mutually exclusive
# "Leistungen nach den Nummern 410 bis 418 sind nicht nebeneinander berechnungsfähig."
# ==========================================================================================


def test_two_sonography_positions_cannot_stand_beside_each_other(souffle):
    """A mutual pair: Soufflé refuses to pick a winner and hands the cluster to the ASP solver,
    so the assertion is that the conflict is *seen*, not which side happens to survive."""
    result = souffle.run(make_extraction(), one_act_per_ziffer("410", "415"))

    conflicts = {frozenset((c.ziffer_a, c.ziffer_b)) for c in result.conflicts}
    assert frozenset(("410", "415")) in conflicts
    assert result.billable == [], "a mutual conflict is arbitrated by the ASP solver, not here"


def test_one_sonography_position_alone_is_billable(souffle):
    result = souffle.run(make_extraction(), one_act_per_ziffer("415"))

    assert result.billable == ["415"]
    assert result.conflicts == []


def test_the_sonography_range_stops_at_418(souffle):
    """GOÄ 420 ("bis zu drei weitere Organe") is the next sonography position after 418 and is
    deliberately outside this provision's range — the GOÄ caps 420 elsewhere, per Sitzung, a
    window this engine cannot evaluate (batch 2 §4). An off-by-one in the expansion would make
    420 unbillable beside every single-organ scan, which is the common case, not an edge case."""
    result = souffle.run(make_extraction(), one_act_per_ziffer("415", "420"))

    assert sorted(result.billable) == ["415", "420"]
    assert result.conflicts == []


# ==========================================================================================
# Abschnitt L III — arthroscopy swallows the joint puncture
# "Neben den Leistungen nach den Nummern 2189 bis 2196 sind die Leistungen nach den Nummern
#  300 bis 302 sowie 3300 nicht berechnungsfähig."
# ==========================================================================================


def test_the_knee_puncture_is_blocked_beside_the_arthroscopy(souffle):
    result = souffle.run(make_extraction(), one_act_per_ziffer("2189", "301"))

    assert result.billable == ["2189"]
    blocked = _blocked(result, "301")
    assert blocked is not None
    assert blocked.rule_id == "excl_b3_2189_301"
    assert blocked.legal_basis == "GOÄ Allgemeine Bestimmungen zu Abschnitt L III"


def test_the_knee_puncture_alone_is_billable(souffle):
    result = souffle.run(make_extraction(), one_act_per_ziffer("301"))

    assert result.billable == ["301"]
    assert result.blocked == []


def test_the_blocked_side_stops_at_302(souffle):
    """GOÄ 303 is the next puncture position after "300 bis 302" and is not named.

    The tighter of the two boundaries this provision has: 300–302 are joint punctures and 303 is
    the puncture of a bursa or abscess, which an arthroscopy does not contain. One position of
    over-expansion here is a wrong rejection on a real invoice, not a theoretical one.
    """
    result = souffle.run(make_extraction(), one_act_per_ziffer("2189", "303"))

    assert sorted(result.billable) == ["2189", "303"]
    assert result.blocked == []


def test_the_arthroscopy_side_stops_at_2196(souffle):
    """GOÄ 2203 is the first position past the cited range that exists in this catalog (2197–2202
    are unoccupied numbers), and it is a Luxation reduction, not an arthroscopy."""
    result = souffle.run(make_extraction(), one_act_per_ziffer("2203", "301"))

    assert sorted(result.billable) == ["2203", "301"]
    assert result.blocked == []


# ==========================================================================================
# Anmerkung zu GOÄ 435 — the intensive-care position, and the 182 it absorbs
# ==========================================================================================


def test_the_intensive_care_position_absorbs_a_consultation(souffle):
    """The single largest provision in the batch: 182 exclusion edges off one Ziffer.

    GOÄ 1 (Beratung) is inside "1 bis 56" and is the most-billed position in the whole fee
    schedule, so this is the pair a billing office meets first.
    """
    result = souffle.run(make_extraction(), one_act_per_ziffer("435", "1"))

    assert result.billable == ["435"]
    blocked = _blocked(result, "1")
    assert blocked is not None
    assert blocked.rule_id == "excl_b3_435_1"
    assert blocked.legal_basis == "GOÄ Anmerkung zu Nummer 435"


def test_the_intensive_care_position_absorbs_the_sentences_last_number(souffle):
    """GOÄ 3055 is the sentence's final named number, after twenty-one ranges. If the token list
    were truncated anywhere, this is the edge that would be missing."""
    result = souffle.run(make_extraction(), one_act_per_ziffer("435", "3055"))

    assert result.billable == ["435"]
    assert _blocked(result, "3055") is not None


def test_a_position_past_every_435_range_still_bills(souffle):
    """GOÄ 3300 is in none of the sentence's ranges — the last one ends at 1733, and 3055 is named
    alone afterwards. A range expansion that ran past its endpoint would catch it."""
    result = souffle.run(make_extraction(), one_act_per_ziffer("435", "3300"))

    assert sorted(result.billable) == ["3300", "435"]
    assert result.blocked == []


def test_a_letter_suffixed_sibling_inside_a_435_range_is_not_swept_in(souffle):
    """GOÄ 265a sits numerically inside "250 bis 268" and is written nowhere in the sentence.

    Quarantined on purpose (report §4): reading a lettered sibling into a plainly-numbered range
    is an interpretation, and the same sentence shows the GOÄ naming one explicitly where it means
    to ("270 bis 286a" — which *is* encoded). Under-blocking is the safe direction; this pins
    which direction was taken, so a later batch changes it deliberately and not by accident.
    """
    result = souffle.run(make_extraction(), one_act_per_ziffer("435", "265a"))

    assert sorted(result.billable) == ["265a", "435"]
    assert result.blocked == []


def test_the_explicitly_named_suffixed_endpoint_is_swept_in(souffle):
    """The other half of the rule above: "270 bis 286a" names 286a, so 286a is encoded."""
    result = souffle.run(make_extraction(), one_act_per_ziffer("435", "286a"))

    assert result.billable == ["435"]
    blocked = _blocked(result, "286a")
    assert blocked is not None
    assert blocked.rule_id == "excl_b3_435_286a"


# ==========================================================================================
# Factor caps — "nur mit dem einfachen Gebührensatz berechnungsfähig"
# ==========================================================================================

#: 1.1× is not a Steigerungssatz any § 5 band rounds to, so a finding at this factor cannot be a
#: chapter band doing the cap's work. The five span four different provisions.
CAPPED = (("A", None), ("E", None), ("K1", 2), ("K2", 2), ("5480", None), ("5485", None))


@pytest.mark.parametrize("ziffer,age", CAPPED)
def test_a_capped_position_above_the_single_rate_is_invalid(souffle, ziffer, age):
    result = souffle.run(
        _extraction(age=age),
        one_act_per_ziffer(ziffer),
        proposed_factors={ziffer: Decimal("1.1")},
    )

    assert result.factor_invalid == [ziffer]


@pytest.mark.parametrize("ziffer,age", CAPPED)
def test_the_same_position_at_the_single_rate_is_fine(souffle, ziffer, age):
    result = souffle.run(
        _extraction(age=age),
        one_act_per_ziffer(ziffer),
        proposed_factors={ziffer: Decimal("1.0")},
    )

    assert result.factor_invalid == []
    assert result.factor_needs_justification == []


def test_the_cap_did_not_leak_onto_the_position_after_the_range(souffle):
    """GOÄ 5486 is the next Ergänzungsleistung after the cited "5480 bis 5485" and is not capped.

    1.8× is above the single rate and inside Abschnitt O's § 5 band, so it must pass — which it
    only does if the cap stopped where the sentence stops.
    """
    result = souffle.run(
        make_extraction(), one_act_per_ziffer("5486"), proposed_factors={"5486": Decimal("1.8")}
    )

    assert result.factor_invalid == []


# ==========================================================================================
# Mutual Zuschlag groups — the two sentences that point at each other
# ==========================================================================================


def test_the_two_zuschlag_groups_exclude_each_other(souffle):
    """"Neben den Zuschlägen nach den Buchstaben A bis D sowie K 1 dürfen die Zuschläge nach den
    Buchstaben E bis J sowie K 2 nicht berechnet werden." — and, in the neighbouring provision,
    the same sentence with the two groups swapped. Two sentences, so `direction: mutual`."""
    result = souffle.run(make_extraction(), one_act_per_ziffer("A", "F"))

    conflicts = {frozenset((c.ziffer_a, c.ziffer_b)) for c in result.conflicts}
    assert frozenset(("A", "F")) in conflicts


def test_two_zuschlaege_from_the_same_group_are_not_in_conflict_by_this_rule(souffle):
    """A and D are both in the first group. The provision encoded here relates the *groups*, not
    members of one — whatever else constrains A beside D (and something does: GOÄ A's own
    Anmerkung, batch 1's `excl_man_A_D`) must not come from this batch."""
    result = souffle.run(make_extraction(), one_act_per_ziffer("A", "D"))

    from_batch3 = [
        b for b in result.blocked if (b.rule_id or "").startswith("excl_b3_")
    ]
    assert from_batch3 == []
