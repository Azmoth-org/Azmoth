"""The Mengenbegrenzung ledger: writing occurrences, and counting them back per Behandlungsfall.

See `app.services.patient_history` and `docs/content/adr-002-complex-constraints.md`.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.config import Settings
from app.db.session import Database
from app.services.patient_history import (
    BilledOccurrence,
    behandlungsfall_bounds,
    quarter_counts,
    record_occurrences,
)


@pytest.fixture
async def db() -> Database:
    database = Database(
        Settings(database_url="sqlite+aiosqlite:///:memory:", database_auto_create=True)
    )
    await database.create_all()
    try:
        yield database
    finally:
        await database.dispose()


# ------------------------------------------------------------------------------------------
# the quarter window
# ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "on,expected_start,expected_end",
    [
        (date(2026, 1, 5), date(2026, 1, 1), date(2026, 3, 31)),
        (date(2026, 2, 28), date(2026, 1, 1), date(2026, 3, 31)),
        (date(2026, 4, 1), date(2026, 4, 1), date(2026, 6, 30)),
        (date(2026, 6, 30), date(2026, 4, 1), date(2026, 6, 30)),
        (date(2026, 9, 12), date(2026, 7, 1), date(2026, 9, 30)),
        (date(2026, 10, 1), date(2026, 10, 1), date(2026, 12, 31)),
        (date(2026, 12, 31), date(2026, 10, 1), date(2026, 12, 31)),
    ],
)
def test_behandlungsfall_bounds_is_the_calendar_quarter(on, expected_start, expected_end):
    assert behandlungsfall_bounds(on) == (expected_start, expected_end)


# ------------------------------------------------------------------------------------------
# recording and reading occurrences back
# ------------------------------------------------------------------------------------------


async def test_a_fresh_patient_has_no_recorded_history(db):
    counts = await quarter_counts(
        db,
        organization_id="org-1",
        patient_pseudonym="patient-abc",
        ziffern=["4601"],
        as_of=date(2026, 9, 12),
    )
    assert counts == {}


async def test_recorded_occurrences_are_counted_within_the_same_quarter(db):
    async with db.session() as session:
        await record_occurrences(
            session,
            organization_id="org-1",
            patient_pseudonym="patient-abc",
            occurrences=[
                BilledOccurrence("4601", date(2026, 7, 3)),
                BilledOccurrence("4601", date(2026, 8, 14)),
                BilledOccurrence("4601", date(2026, 9, 1)),
            ],
        )

    counts = await quarter_counts(
        db,
        organization_id="org-1",
        patient_pseudonym="patient-abc",
        ziffern=["4601"],
        as_of=date(2026, 9, 12),
    )
    assert counts == {"4601": 3}


async def test_an_occurrence_in_a_different_quarter_does_not_count(db):
    async with db.session() as session:
        await record_occurrences(
            session,
            organization_id="org-1",
            patient_pseudonym="patient-abc",
            occurrences=[BilledOccurrence("4601", date(2026, 3, 31))],
        )

    counts = await quarter_counts(
        db,
        organization_id="org-1",
        patient_pseudonym="patient-abc",
        ziffern=["4601"],
        as_of=date(2026, 4, 1),
    )
    assert counts == {}


async def test_two_patients_in_the_same_practice_do_not_share_history(db):
    async with db.session() as session:
        await record_occurrences(
            session,
            organization_id="org-1",
            patient_pseudonym="patient-a",
            occurrences=[BilledOccurrence("4601", date(2026, 9, 1))],
        )

    counts = await quarter_counts(
        db,
        organization_id="org-1",
        patient_pseudonym="patient-b",
        ziffern=["4601"],
        as_of=date(2026, 9, 12),
    )
    assert counts == {}


async def test_two_organisations_do_not_share_a_patient_pseudonym(db):
    """The same opaque token from two different practices names two different patients."""
    async with db.session() as session:
        await record_occurrences(
            session,
            organization_id="org-1",
            patient_pseudonym="patient-abc",
            occurrences=[BilledOccurrence("4601", date(2026, 9, 1))],
        )

    counts = await quarter_counts(
        db,
        organization_id="org-2",
        patient_pseudonym="patient-abc",
        ziffern=["4601"],
        as_of=date(2026, 9, 12),
    )
    assert counts == {}


async def test_a_ziffer_never_billed_is_omitted_not_zero(db):
    """Absence, not an explicit 0 — see the docstring on why `history_count` reads that way."""
    async with db.session() as session:
        await record_occurrences(
            session,
            organization_id="org-1",
            patient_pseudonym="patient-abc",
            occurrences=[BilledOccurrence("4601", date(2026, 9, 1))],
        )

    counts = await quarter_counts(
        db,
        organization_id="org-1",
        patient_pseudonym="patient-abc",
        ziffern=["4601", "34"],
        as_of=date(2026, 9, 12),
    )
    assert "34" not in counts
    assert counts["4601"] == 1
