#!/usr/bin/env python3
"""Delete data that is older than the retention window. What cron runs at 03:30.

    python -m scripts.purge_old_data --dry-run    # report what would go, change nothing
    python -m scripts.purge_old_data              # do it
    python -m scripts.purge_old_data --days 30    # override DATA_RETENTION_DAYS for this run

DSGVO Art. 5 Abs. 1 lit. e (Speicherbegrenzung) requires that personal data be kept in identifiable
form no longer than is necessary. This engine held proposals, batch jobs and crash reports forever,
which is not a retention policy — it is the absence of one. This script is the policy, and
`DATA_RETENTION_DAYS` is its only knob.

What is deleted, in the order it has to happen so no foreign key is ever left dangling:

    1. batch_files    belonging to batch_jobs older than the window
    2. batch_jobs     older than the window, and the uploaded ZIP each one names on disk
    3. proposals      older than the window
    4. error_log      rows older than the window

**`audit_events` is never deleted, and that is the point of the whole exercise.** Art. 5 Abs. 1
lit. e creates the obligation to delete; Art. 5 Abs. 2 (Rechenschaftspflicht) creates a separate
obligation to be able to *demonstrate* compliance with it. A purge that erased its own record would
satisfy the first and make the second impossible, and "we deleted it, trust us" is not an answer to
a supervisory authority. So every purged proposal leaves a `DATA_PURGED` row behind naming what was
removed, when, and under which retention setting.

That is only possible because `0011` changed the foreign key from `ON DELETE CASCADE` to
`ON DELETE SET NULL` and gave `audit_events` a `target_id` that is a value rather than a join. Under
the original schema this script would have destroyed the log of every approval it touched. If you
are reading this while porting the purge somewhere else, that migration is not optional.

## The transaction, and the one thing that is not in it

Every statement runs in one transaction and either all of it lands or none of it does. Files are the
exception the filesystem imposes: `unlink` has no rollback. The ordering is chosen so the failure
modes stay safe rather than convenient —

* Files are deleted **inside** the transaction, after the rows. A file that cannot be deleted aborts
  the run and rolls the database back, so the rows that name those files are still there and the
  next run tries again. The alternative — commit first, then delete — trades that for orphaned
  archives that no row names, which `app.services.uploads` describes as unreachable and which are
  precisely the personal data this script exists to remove. An unreachable file is not a deleted
  file, and a purge that reports success while leaving one has lied.
* The reverse failure — files removed, transaction rolled back — leaves rows pointing at archives
  that are gone. Those jobs are old and terminal, nothing will try to resume them, and the next run
  purges the rows properly. `discard_bulk_upload` treats an already-missing file as success, which
  is what makes the retry converge.

## Idempotency

Running it twice does nothing the second time, and not because of a marker column: the second run's
`created_at < cutoff` predicate simply matches no rows, because the first run deleted them. Nothing
here is keyed on having-run-before, so a half-finished run that rolled back is not a special case to
recover from — it is just a run that deleted nothing, and the next one starts from the same place.

`DATA_PURGED` events are written only for proposals this run is actually deleting, so re-running
cannot accumulate duplicate audit rows for a proposal that is already gone.

## What this deliberately does NOT do

**It does not purge `batch_jobs` into the audit log.** `audit_events` is proposal-scoped by schema —
one row is "one thing that happened to one proposal" — and widening it to record batch deletions
would change what the table means for the sake of a symmetry nobody asked for. A batch purge is
recorded in this script's own output and in whatever the cron job's mail goes to. If a batch-level
legal record is needed, that is a second table, not a reinterpretation of this one.

**It does not skip a job that is still `PENDING` or `PROCESSING`.** A batch that has been processing
for ninety days is a zombie — `reap_interrupted_batches` closes the ones a restart left behind — and
making the purge conditional on a status field would mean a stuck row could keep patient billing
data past the retention window indefinitely. A compliance floor that a bad status can escape is not
a floor.

**It has no scheduler.** The engine does not grow a cron daemon; see the README for the crontab.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from sqlalchemy import Select, delete, func, select, update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.db.models import (  # noqa: E402
    AuditEvent,
    AuditEventType,
    BatchFileRecord,
    BatchJobRecord,
    ErrorLogRecord,
    ProposalRecord,
    utcnow,
)
from app.db.session import Database  # noqa: E402
from app.services.uploads import discard_bulk_upload  # noqa: E402

log = logging.getLogger("purge")

#: `actor` on a `DATA_PURGED` row. Uppercase, unlike `proposal_store.SYSTEM_ACTOR` (`system`), and
#: deliberately so: those rows are attributed to the engine acting on a user's behalf, this one to a
#: scheduled job acting on nobody's. Reading the log, "SYSTEM" is the only actor that is not a
#: request, and it should not be possible to mistake it for one.
PURGE_ACTOR = "SYSTEM"


class UploadsNotPurged(RuntimeError):
    """One or more archives could not be deleted, so the whole run is rolled back.

    Raised inside the transaction on purpose — see the module docstring on why a partial success
    here is worse than a clean failure. The message names every path, because the operator's next
    action is to look at exactly those.
    """


@dataclass
class PurgeReport:
    """What one run removed, or would have removed under `--dry-run`."""

    cutoff: datetime
    retention_days: int
    dry_run: bool
    batch_files: int = 0
    batch_jobs: int = 0
    proposals: int = 0
    error_log: int = 0
    uploads_deleted: int = 0
    uploads_failed: list[str] = field(default_factory=list)
    audit_events_written: int = 0

    @property
    def total_rows(self) -> int:
        return self.batch_files + self.batch_jobs + self.proposals + self.error_log

    def render(self) -> str:
        verb = "would delete" if self.dry_run else "deleted"
        return "\n".join(
            [
                f"retention: {self.retention_days} days — {verb} everything created before "
                f"{self.cutoff.isoformat()}",
                f"  batch_files       {self.batch_files:>8}",
                f"  batch_jobs        {self.batch_jobs:>8}",
                f"  proposals         {self.proposals:>8}",
                f"  error_log         {self.error_log:>8}",
                f"  uploads (disk)    {self.uploads_deleted:>8}",
                f"  audit_events      {self.audit_events_written:>8}  "
                f"({'would be ' if self.dry_run else ''}written, never deleted)",
            ]
        )


def cutoff_for(days: int, *, now: datetime | None = None) -> datetime:
    """The timestamp a row must predate to be purged.

    Split out and taking `now` so the suite can purge without waiting ninety days for a fixture to
    age. UTC throughout, matching `app.db.models.utcnow` — the whole schema is written in it.
    """
    return (now or utcnow()) - timedelta(days=days)


def _doomed_job_ids(cutoff: datetime) -> Select:
    """The `batch_jobs` this run is removing, as a subquery.

    One definition used by both the count and the `DELETE`, so the two can never disagree about
    which files belong to a job that is going.
    """
    return select(BatchJobRecord.id).where(BatchJobRecord.created_at < cutoff)


async def _count(session: AsyncSession, model: type, predicate) -> int:
    """`SELECT count(*)` — used only to report, never to decide what to delete.

    The counts and the `DELETE`s are separate statements against the same snapshot inside one
    transaction, so they agree; nothing branches on a count.
    """
    statement = select(func.count()).select_from(model).where(predicate)
    return int((await session.execute(statement)).scalar_one())


async def _purge(
    session: AsyncSession, settings: Settings, report: PurgeReport
) -> None:
    """Everything, in one transaction on the caller's session.

    Takes a session rather than opening one so that the transaction boundary belongs to the caller
    — `Database.session()` commits on a clean return and rolls back on any exception, which is
    exactly the all-or-nothing this needs and is not something to reimplement here.
    """
    cutoff = report.cutoff

    # -- 0. Read what is going, before anything is deleted ----------------------------------
    #
    # Both of these have to be materialised while the rows still exist: the proposal handles
    # because the audit rows are written from them, and the upload paths because after the
    # `batch_jobs` row is gone nothing on disk says which archive belonged to it.
    doomed_proposals = list(
        (
            await session.execute(
                select(ProposalRecord.id, ProposalRecord.proposal_id).where(
                    ProposalRecord.created_at < cutoff
                )
            )
        ).all()
    )
    doomed_uploads = list(
        (
            await session.execute(
                select(BatchJobRecord.upload_path).where(
                    BatchJobRecord.created_at < cutoff,
                    BatchJobRecord.upload_path.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    report.proposals = len(doomed_proposals)
    report.audit_events_written = len(doomed_proposals)
    report.batch_jobs = await _count(session, BatchJobRecord, BatchJobRecord.created_at < cutoff)
    report.error_log = await _count(session, ErrorLogRecord, ErrorLogRecord.occurred_at < cutoff)
    # Counted through the parent rather than by a date on `batch_files`, because there is no date on
    # `batch_files` — a file's age is its job's age, which is also what step 3 deletes by.
    report.batch_files = await _count(
        session,
        BatchFileRecord,
        BatchFileRecord.batch_job_id.in_(_doomed_job_ids(cutoff)),
    )

    if report.dry_run:
        report.uploads_deleted = len(doomed_uploads)
        return

    # -- 1. The audit record of the deletion, written before the deletion ---------------------
    #
    # Order matters for one reason only: `proposal_id` on these rows is `NULL` from the start, so
    # they carry no foreign key that a later `DELETE` could invalidate, and writing them first means
    # a failure anywhere below rolls them back with everything else. There is no window in which the
    # proposal is gone and its `DATA_PURGED` row is not yet written.
    detail = (
        f"Purged per retention policy after {report.retention_days} days"
    )
    now = utcnow()
    session.add_all(
        [
            AuditEvent(
                proposal_id=None,
                target_id=handle,
                event_type=str(AuditEventType.DATA_PURGED),
                actor=PURGE_ACTOR,
                timestamp=now,
                metadata_json={
                    "details": detail,
                    "retention_days": report.retention_days,
                    "cutoff": cutoff.isoformat(),
                    # The surrogate key too, so a row in a backup taken before the purge can still
                    # be tied to this event. `target_id` is the handle, which is what an outside
                    # question arrives phrased in; this is what an internal join needs.
                    "proposal_uuid": str(uuid_),
                },
            )
            for uuid_, handle in doomed_proposals
        ]
    )
    # Explicit, because the sessionmaker sets `autoflush=False`: without this the inserts would not
    # reach the database until commit, after the `DELETE`s below have already run.
    await session.flush()

    # -- 2. Release the audit log's pointer, by hand -------------------------------------------
    #
    # `0011` made this `ON DELETE SET NULL`, and on Postgres that alone would be enough. It is not
    # enough here: SQLite enforces foreign keys only under `PRAGMA foreign_keys=ON`, which
    # `app.db.session.build_engine` does not set, so on the development dialect a `DELETE` of a
    # proposal would leave `audit_events.proposal_id` pointing at nothing at all. Doing it
    # explicitly makes the two dialects behave identically and puts the intent in code rather than
    # in a constraint the reader has to go and look up.
    #
    # This is the only statement in the codebase that writes to a column of `audit_events`, and it
    # is an exception to append-only in the narrowest possible sense: it nulls a pointer to a row
    # that no longer exists. `event_type`, `actor`, `timestamp`, `target_id` and `metadata_json` —
    # everything the row actually *records* — are untouched, and `target_id` is precisely why the
    # row is still readable afterwards. The ORM guards in `app.db.models` still refuse any
    # mapper-level update; this is Core, and deliberately so.
    if doomed_proposals:
        await session.execute(
            update(AuditEvent)
            .where(AuditEvent.proposal_id.in_([uuid_ for uuid_, _ in doomed_proposals]))
            .values(proposal_id=None)
        )

    # -- 3. The rows, children first ------------------------------------------------------------
    await session.execute(
        delete(BatchFileRecord).where(BatchFileRecord.batch_job_id.in_(_doomed_job_ids(cutoff)))
    )
    await session.execute(delete(BatchJobRecord).where(BatchJobRecord.created_at < cutoff))
    await session.execute(delete(ProposalRecord).where(ProposalRecord.created_at < cutoff))
    await session.execute(delete(ErrorLogRecord).where(ErrorLogRecord.occurred_at < cutoff))

    # -- 4. The bytes on disk -------------------------------------------------------------------
    #
    # Still inside the transaction: a failure here must take the row deletions with it, so that the
    # archive is still named by a row the next run can find. `force=True` because
    # `RETAIN_BULK_UPLOADS` is a debugging convenience and this is a legal obligation — see
    # `app.services.uploads.discard_bulk_upload`.
    for path in doomed_uploads:
        if discard_bulk_upload(path, settings=settings, force=True):
            report.uploads_deleted += 1
        else:
            report.uploads_failed.append(str(path))

    if report.uploads_failed:
        raise UploadsNotPurged(
            f"{len(report.uploads_failed)} upload(s) could not be deleted, so nothing was "
            "committed — the rows naming them are intact and the next run will retry. Fix the "
            "permissions or remove them by hand: " + ", ".join(report.uploads_failed)
        )


async def run(
    *,
    days: int | None = None,
    dry_run: bool = False,
    settings: Settings | None = None,
    database: Database | None = None,
    now: datetime | None = None,
) -> PurgeReport:
    """One purge. Returns what it did; raises if it could not do all of it.

    `database` is injectable so the suite can hand in one pointed at a temporary file. When this
    builds its own it also disposes it, because a CLI that leaves a connection pool open exits with
    a warning from asyncpg.
    """
    settings = settings or get_settings()
    retention_days = days if days is not None else settings.data_retention_days
    report = PurgeReport(
        cutoff=cutoff_for(retention_days, now=now),
        retention_days=retention_days,
        dry_run=dry_run or not settings.retention_enabled,
    )

    if not settings.retention_enabled and not dry_run:
        log.warning(
            "RETENTION_ENABLED=false — reporting what is over the window and deleting nothing. "
            "This is the legal-hold switch; if that is not what you meant, set it back to true."
        )

    owned = database is None
    database = database or Database(settings)
    try:
        async with database.session() as session:
            await _purge(session, settings, report)
    finally:
        if owned:
            await database.dispose()

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="purge_old_data",
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be deleted and change nothing, in the database or on disk",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        metavar="N",
        help="override DATA_RETENTION_DAYS for this run (must be >= 1)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(format="%(levelname)s %(message)s", stream=sys.stderr)
    log.setLevel(logging.INFO)

    if args.days is not None and args.days < 1:
        log.error("--days must be at least 1; refusing to purge everything")
        return 2

    settings = get_settings()
    database = Database(settings)
    # Rendered without the password: this line goes to a cron mail.
    log.info("database: %s", database.url)

    async def once() -> PurgeReport:
        """Run and dispose inside one event loop.

        Both in here rather than two `asyncio.run` calls: the connection pool belongs to the loop
        that opened it, and disposing it from a second loop is how a clean run still manages to
        print `RuntimeError: Event loop is closed` at exit.
        """
        try:
            return await run(days=args.days, dry_run=args.dry_run, database=database)
        finally:
            await database.dispose()

    try:
        report = asyncio.run(once())
    except Exception as exc:  # noqa: BLE001 - this is a CLI boundary
        log.error("purge failed, nothing was committed: %s", exc)
        return 1

    print(report.render())
    if report.dry_run:
        print("\nnothing was changed (--dry-run or RETENTION_ENABLED=false)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
