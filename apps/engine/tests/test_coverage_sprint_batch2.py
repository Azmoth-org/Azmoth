"""Coverage-sprint batch 2: the first real, materialized rows in `quantity_limits.manual.csv`,
`gender_restrictions.manual.csv` and `age_restrictions.manual.csv` — see
`docs/content/adr-002-complex-constraints.md` and `docs/content/coverage-sprint-report-batch2.md`.

Unlike `tests/test_complex_constraints.py` (which deliberately hand-builds a `RuleStore` per test
to isolate the Datalog layer from `data/rules/`), every test here loads the real corpus through the
`rules`/`souffle` fixtures. The point of this file is the opposite one: prove the *shipped data*,
not just the mechanism, actually fires — a citation that parses but was never loaded against the
real engine is not a tested rule.

`time_relations.manual.csv` carries no rows this batch (§3.3 of the ADR, and the batch 2 report):
this scan found zero "nicht am selben Tag" / "innerhalb von … Tagen" sentences between two named
Ziffern anywhere in `goae_current`. The Zeitbeziehung golden pair therefore stays the synthetic one
in `test_complex_constraints.py` — there is no real citation yet to replace it with.
"""

from __future__ import annotations

import uuid
from datetime import date

from app.schemas import ClinicalExtraction
from app.services.patient_history import BilledOccurrence, quarter_counts, record_occurrences
from tests.conftest import make_bridge


def _extraction(*, age: int | None = None, sex: str | None = None, setting: str = "ambulant"):
    return ClinicalExtraction.model_validate(
        {
            "patient": {"age": age, "sex": sex, "setting": setting},
            "justification_factors": [],
        }
    )


# ==========================================================================================
# Mengenbegrenzung — GOÄ 4601, `cnt_man_4601` in `data/rules/quantity_limits.manual.csv`
# ==========================================================================================


def test_the_real_4601_quantity_limit_blocks_the_fourth_claim(souffle):
    """"Eine mehr als dreimalige Berechnung der Leistung nach Nummer 4601 im Behandlungsfall ist
    nicht zulässig." — three prior occurrences on record, one more on the invoice, blocked."""
    result = souffle.run(
        _extraction(),
        make_bridge(("a1", "4601", 100, "1.0")),
        history_counts={"4601": 3},
    )

    assert result.billable == []
    blocked = next(b for b in result.blocked if b.ziffer == "4601")
    assert blocked.reason == "quantity_exceeded"
    assert blocked.rule_id == "cnt_man_4601"
    assert blocked.legal_basis == "GOÄ Anmerkung zu Nummer 4601"


def test_the_real_4601_quantity_limit_admits_the_third_claim(souffle):
    result = souffle.run(
        _extraction(), make_bridge(("a1", "4601", 100, "1.0")), history_counts={"4601": 2}
    )

    assert result.billable == ["4601"]
    assert result.blocked == []


# ==========================================================================================
# Geschlecht — GOÄ 27, `gr_man_27` in `data/rules/gender_restrictions.manual.csv`
# ==========================================================================================


def test_the_real_27_gender_restriction_blocks_a_male_patient(souffle):
    """"Untersuchung einer Frau zur Früherkennung von Krebserkrankungen ..." — GOÄ 27 is defined as
    an examination of a woman; a male patient cannot be billed for it."""
    result = souffle.run(_extraction(sex="m"), make_bridge(("a1", "27", 100, "1.0")))

    assert result.billable == []
    blocked = next(b for b in result.blocked if b.ziffer == "27")
    assert blocked.reason == "gender_restricted"
    assert blocked.rule_id == "gr_man_27"


def test_the_real_27_gender_restriction_admits_a_female_patient(souffle):
    result = souffle.run(_extraction(sex="w"), make_bridge(("a1", "27", 100, "1.0")))

    assert result.billable == ["27"]
    assert result.blocked == []


# ==========================================================================================
# Alter — GOÄ 26, `age_man_26` in `data/rules/age_restrictions.manual.csv`
# ==========================================================================================


def test_the_real_26_age_restriction_blocks_a_patient_above_the_band(souffle):
    """"... bei einem Kind bis zum vollendeten 14. Lebensjahr ..." plus "... ab dem vollendeten 2.
    Lebensjahr ..." — GOÄ 26 is banded to ages 2 through 13 inclusive; a 42-year-old is outside it."""
    result = souffle.run(_extraction(age=42), make_bridge(("a1", "26", 100, "1.0")))

    assert result.billable == []
    blocked = next(b for b in result.blocked if b.ziffer == "26")
    assert blocked.reason == "age_restricted"
    assert blocked.rule_id == "age_man_26"


def test_the_real_26_age_restriction_admits_a_patient_inside_the_band(souffle):
    result = souffle.run(_extraction(age=8), make_bridge(("a1", "26", 100, "1.0")))

    assert result.billable == ["26"]
    assert result.blocked == []


# ==========================================================================================
# Mengenbegrenzung across two invoices — `patient_ziffer_history`, real GOÄ 4601 rule
# ==========================================================================================


async def test_a_fourth_4601_claim_is_blocked_by_history_recorded_across_two_earlier_invoices(
    database, souffle
):
    """The scenario the ADR's mechanism exists for, run end to end: two earlier invoices for one
    patient recorded three occurrences of GOÄ 4601 between them this Behandlungsfall, and a third
    invoice's claim of a fourth is caught by the real, shipped `cnt_man_4601` rule — not a synthetic
    one built by hand.

    Invoice 1 (approved 2026-07-10): one claim of GOÄ 4601.
    Invoice 2 (approved 2026-08-04): two more claims of GOÄ 4601, same Behandlungsfall.
    Invoice 3 (2026-09-12, under test): one more claim. `quarter_counts` reads the two prior
    invoices back as `{"4601": 3}`, exactly what the golden single-invoice test above asserts by
    hand — the only difference here is that the history came from Postgres, not a test literal.
    """
    organization_id = "org-batch2-e2e"
    patient_pseudonym = "patient-batch2-e2e"

    async with database.session() as session:
        await record_occurrences(
            session,
            organization_id=organization_id,
            patient_pseudonym=patient_pseudonym,
            occurrences=[BilledOccurrence("4601", date(2026, 7, 10))],
            proposal_id=uuid.uuid4(),
        )
    async with database.session() as session:
        await record_occurrences(
            session,
            organization_id=organization_id,
            patient_pseudonym=patient_pseudonym,
            occurrences=[
                BilledOccurrence("4601", date(2026, 8, 4)),
                BilledOccurrence("4601", date(2026, 8, 4)),
            ],
            proposal_id=uuid.uuid4(),
        )

    history = await quarter_counts(
        database,
        organization_id=organization_id,
        patient_pseudonym=patient_pseudonym,
        ziffern=["4601"],
        as_of=date(2026, 9, 12),
    )
    assert history == {"4601": 3}, "sanity check: two invoices really did add up to three"

    result = souffle.run(
        _extraction(), make_bridge(("a1", "4601", 100, "1.0")), history_counts=history
    )

    assert result.billable == []
    blocked = next(b for b in result.blocked if b.ziffer == "4601")
    assert blocked.reason == "quantity_exceeded"
    assert blocked.rule_id == "cnt_man_4601"


async def test_a_second_patient_in_the_same_practice_is_unaffected(database, souffle):
    """The ledger is per-patient: a different pseudonym in the same organisation has no history,
    so the same third claim of GOÄ 4601 is admitted."""
    organization_id = "org-batch2-e2e"

    async with database.session() as session:
        await record_occurrences(
            session,
            organization_id=organization_id,
            patient_pseudonym="patient-batch2-e2e",
            occurrences=[
                BilledOccurrence("4601", date(2026, 7, 10)),
                BilledOccurrence("4601", date(2026, 8, 4)),
                BilledOccurrence("4601", date(2026, 8, 4)),
            ],
        )

    history = await quarter_counts(
        database,
        organization_id=organization_id,
        patient_pseudonym="patient-batch2-other",
        ziffern=["4601"],
        as_of=date(2026, 9, 12),
    )
    assert history == {}

    result = souffle.run(
        _extraction(), make_bridge(("a1", "4601", 100, "1.0")), history_counts=history
    )

    assert result.billable == ["4601"]
    assert result.blocked == []
