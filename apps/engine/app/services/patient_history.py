"""The Mengenbegrenzung ledger: how many times a patient has already billed a Ziffer this quarter.

See `docs/content/adr-002-complex-constraints.md` for the full design. In short: every other
constraint the rules engine evaluates (an exclusion, a Zielleistung, a factor cap) is decidable
from the one invoice in front of it. "Has this Ziffer already been billed three times this
Behandlungsfall" is a fact about a patient *across* invoices, and `app.solvers.souffle_engine` is
deliberately stateless per call — so the count is assembled here, in Postgres, and handed to
Soufflé as a plain fact (`history_count`) exactly the way a chosen factor is handed in as
`proposed_factor`.

**This module never sees a name, an address or a date of birth**, and it must not start: see
`app.schemas.padnext`'s module docstring and `PatientZifferHistoryRecord`'s class docstring for why
that invariant exists and what `patient_pseudonym` is allowed to be instead.

**Nothing calls this module today.** Wiring it into a live request path — `app.padnext.audit` or
the proposal-approval flow — is deliberately left for a follow-up: doing so changes what enters the
fact base for every existing PADnext delivery that would carry a pseudonym, which under the current
receipt design (`app/services/receipt.py`) is exactly the kind of change that has to be made on
purpose, reviewed, and accompanied by a fresh look at what a patient-linked ledger means for the
DSGVO posture stated in `docs/content/social-bank.md` #21 — there is no AVV in force yet, and this
table's very first real row would be the first time this engine holds anything longitudinal about
an identifiable (if pseudonymous) patient. What is here is the mechanism: correct, tested, and
inert until a caller opts in.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PatientZifferHistoryRecord
from app.db.session import Database


@dataclass(frozen=True)
class BilledOccurrence:
    """One claimed Ziffer, on one date, for the patient a pseudonym names."""

    ziffer: str
    service_date: date


def behandlungsfall_bounds(on: date) -> tuple[date, date]:
    """The calendar quarter `on` falls in, as `[start, end]` inclusive on both sides.

    § 21 GOÄ's `Behandlungsfall` is defined as the whole of one calendar quarter, not a rolling
    window from the first occurrence — so "this quarter" means Jan-Mar / Apr-Jun / Jul-Sep / Oct-Dec
    regardless of which day within it a patient was first seen.
    """
    quarter_start_month = 3 * ((on.month - 1) // 3) + 1
    start = date(on.year, quarter_start_month, 1)
    if quarter_start_month == 10:
        end = date(on.year, 12, 31)
    else:
        next_quarter_start = date(on.year, quarter_start_month + 3, 1)
        end = next_quarter_start - timedelta(days=1)
    return start, end


async def quarter_counts(
    database: Database,
    *,
    organization_id: str,
    patient_pseudonym: str,
    ziffern: Sequence[str],
    as_of: date,
) -> dict[str, int]:
    """`{ziffer: how many times already recorded for this patient in the Behandlungsfall `as_of`
    falls in}` — exactly the shape `app.solvers.souffle_facts.build_fact_rows` wants for
    `history_counts`.

    Ziffern with no recorded occurrence are omitted rather than written as `0`: Datalog's
    `history_count` relation reads absence as "untracked", which is what it is here too, and an
    explicit `0` row would cost a fact for every Ziffer on an invoice a patient has never been
    billed before, for no gain — `blocked_quantity` needs `Count >= Max` and `Max` is at least 1, so
    a Ziffer this query never mentions can never satisfy it.
    """
    if not ziffern:
        return {}
    start, end = behandlungsfall_bounds(as_of)
    async with database.session() as session:
        rows = (
            (
                await session.execute(
                    select(
                        PatientZifferHistoryRecord.ziffer,
                        func.count(),
                    )
                    .where(
                        PatientZifferHistoryRecord.organization_id == organization_id,
                        PatientZifferHistoryRecord.patient_pseudonym == patient_pseudonym,
                        PatientZifferHistoryRecord.ziffer.in_(list(ziffern)),
                        PatientZifferHistoryRecord.service_date >= start,
                        PatientZifferHistoryRecord.service_date <= end,
                    )
                    .group_by(PatientZifferHistoryRecord.ziffer)
                )
            )
            .all()
        )
    return {ziffer: count for ziffer, count in rows}


async def record_occurrences(
    session: AsyncSession,
    *,
    organization_id: str,
    patient_pseudonym: str,
    occurrences: Sequence[BilledOccurrence],
    proposal_id: uuid.UUID | None = None,
) -> None:
    """Append one row per billed occurrence. Never updates or removes an existing row.

    Takes an open `AsyncSession` rather than a `Database` — this is one write among several a
    caller makes when a draft is approved (write the ledger rows, mark the proposal `APPROVED`,
    record the audit event), and all of it must commit or roll back together. `quarter_counts`
    above takes a `Database` instead because a read that decides what to show has no such sibling
    write to stay atomic with.
    """
    for occurrence in occurrences:
        session.add(
            PatientZifferHistoryRecord(
                organization_id=organization_id,
                patient_pseudonym=patient_pseudonym,
                ziffer=occurrence.ziffer,
                service_date=occurrence.service_date,
                proposal_id=proposal_id,
            )
        )
