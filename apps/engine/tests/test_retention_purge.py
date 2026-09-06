"""The retention purge — and the one property the whole feature exists to guarantee.

`scripts/purge_old_data.py` deletes proposals, batches and crash reports past
`DATA_RETENTION_DAYS`. The interesting assertions here are not that it deletes things; they are that
it leaves `audit_events` standing while doing so, that it is safe to run twice, and that it commits
nothing at all when any part of it fails.

The purge is exercised through `run(...)` with an injected `Database` rather than through the
process entry point, so a test can hand it an isolated database and a fixed `now`. `main()` is a
thin argparse wrapper over the same function.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.db.models import (
    AuditEvent,
    AuditEventType,
    BatchFileRecord,
    BatchJobRecord,
    ErrorLogRecord,
    ProposalRecord,
)
from app.db.session import Database
from app.services.proposal_store import ProposalStore
from scripts.purge_old_data import PURGE_ACTOR, UploadsNotPurged, cutoff_for, run
from tests.factories import make_proposal

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)

#: Comfortably outside a 30-day window, and comfortably inside it.
ANCIENT = NOW - timedelta(days=400)
RECENT = NOW - timedelta(days=3)


@pytest.fixture
def retention_settings(tmp_path) -> Settings:
    """A file-backed database and an upload root under `tmp_path`.

    A file rather than `:memory:` because the purge opens its own session against the same
    `Database`, and because the upload half of it has to write real bytes somewhere.
    """
    return Settings(
        app_env="development",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'retention.db'}",
        database_auto_create=True,
        upload_dir=tmp_path / "uploads",
        data_retention_days=30,
        retention_enabled=True,
    )


@pytest.fixture
async def db(retention_settings) -> Database:
    database = Database(retention_settings)
    await database.create_all()
    try:
        yield database
    finally:
        await database.dispose()


async def _aged_proposal(db: Database, *, created_at: datetime, decided: bool = True) -> str:
    """A proposal stamped into the past, with a real audit trail behind it.

    Created through `ProposalStore` rather than by inserting rows, so the events under test are the
    ones the application actually writes — including the `target_id` the purge depends on.
    """
    store = ProposalStore(db)
    created = await store.create_proposal(make_proposal(created_at=created_at))
    if decided:
        await store.approve_proposal(created.proposal_id, approved_by="Dr. Approver")

    # `created_at` is write-once through the store, so the ageing is done here.
    async with db.session() as session:
        record = (
            await session.execute(
                select(ProposalRecord).where(ProposalRecord.proposal_id == created.proposal_id)
            )
        ).scalar_one()
        record.created_at = created_at
    return created.proposal_id


async def _aged_batch(
    db: Database, *, created_at: datetime, upload: bool = False, settings: Settings | None = None
) -> tuple[uuid.UUID, str | None]:
    """A batch job with one file, optionally with a real ZIP on disk."""
    batch_id = f"batch_{uuid.uuid4().hex[:16]}"
    path = None
    if upload:
        assert settings is not None
        directory = settings.bulk_upload_dir / "org_test" / batch_id
        directory.mkdir(parents=True)
        archive = directory / "upload.zip"
        archive.write_bytes(b"PK\x05\x06" + b"\0" * 18)
        path = str(archive)

    async with db.session() as session:
        job = BatchJobRecord(
            batch_id=batch_id,
            status="COMPLETED",
            created_at=created_at,
            organization_id="org_test",
            upload_path=path,
        )
        session.add(job)
        await session.flush()
        session.add(
            BatchFileRecord(
                batch_job_id=job.id, filename="delivery.padx", status="COMPLETED"
            )
        )
        job_id = job.id
    return job_id, path


async def _aged_error(db: Database, *, occurred_at: datetime) -> None:
    async with db.session() as session:
        session.add(
            ErrorLogRecord(
                request_id=uuid.uuid4().hex[:16],
                occurred_at=occurred_at,
                exception_type="ZeroDivisionError",
                message="boom",
            )
        )


async def _counts(db: Database) -> dict[str, int]:
    async with db.session() as session:

        async def n(model) -> int:
            return int(
                (await session.execute(select(func.count()).select_from(model))).scalar_one()
            )

        return {
            "proposals": await n(ProposalRecord),
            "audit_events": await n(AuditEvent),
            "batch_jobs": await n(BatchJobRecord),
            "batch_files": await n(BatchFileRecord),
            "error_log": await n(ErrorLogRecord),
        }


# ==========================================================================================
# the compliance guarantee
# ==========================================================================================


async def test_the_audit_log_survives_the_proposal_it_describes(db, retention_settings):
    """The single most important assertion in this file.

    Under the pre-`0011` schema — `ON DELETE CASCADE` — deleting the proposal would have taken its
    `CREATED` and `APPROVED` rows with it, and the deletion would have left no evidence it had ever
    happened. DSGVO Art. 5 Abs. 2 requires the operator to be able to demonstrate compliance, and a
    purge that erases its own record cannot.
    """
    handle = await _aged_proposal(db, created_at=ANCIENT)
    before = await _counts(db)
    assert before["proposals"] == 1
    assert before["audit_events"] == 2  # CREATED, APPROVED

    report = await run(settings=retention_settings, database=db, now=NOW)

    assert report.proposals == 1
    after = await _counts(db)
    assert after["proposals"] == 0

    # Two original events, still there, plus the new DATA_PURGED row.
    assert after["audit_events"] == 3

    async with db.session() as session:
        events = (
            (
                await session.execute(
                    select(AuditEvent)
                    .where(AuditEvent.target_id == handle)
                    .order_by(AuditEvent.timestamp)
                )
            )
            .scalars()
            .all()
        )

    assert [event.event_type for event in events] == ["CREATED", "APPROVED", "DATA_PURGED"]
    # Every one of them is now orphaned by the foreign key and readable anyway, which is the whole
    # reason `target_id` is a value rather than a join.
    assert all(event.proposal_id is None for event in events)
    assert events[1].actor == "Dr. Approver"


async def test_the_purge_writes_a_data_purged_event_that_says_what_it_did(db, retention_settings):
    """The row a supervisory authority is shown: what, when, by whom, under which policy."""
    handle = await _aged_proposal(db, created_at=ANCIENT, decided=False)

    await run(settings=retention_settings, database=db, now=NOW)

    async with db.session() as session:
        event = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == str(AuditEventType.DATA_PURGED)
                )
            )
        ).scalar_one()

    assert event.target_id == handle
    assert event.actor == PURGE_ACTOR == "SYSTEM"
    assert event.metadata_json["details"] == "Purged per retention policy after 30 days"
    assert event.metadata_json["retention_days"] == 30
    assert event.metadata_json["cutoff"] == cutoff_for(30, now=NOW).isoformat()


async def test_audit_events_are_never_deleted_even_when_they_are_the_oldest_thing_there(
    db, retention_settings
):
    """There is no `--purge-audit-log`, and the count only ever goes up.

    The events here are far older than the window — the purge does not look at their age at all,
    because their age is not a reason to delete them.
    """
    await _aged_proposal(db, created_at=ANCIENT)

    await run(settings=retention_settings, database=db, now=NOW)
    first = await _counts(db)

    # A second run over a database that now contains nothing but audit rows.
    await run(settings=retention_settings, database=db, now=NOW + timedelta(days=3650))

    assert (await _counts(db))["audit_events"] == first["audit_events"]


# ==========================================================================================
# what is and is not in the window
# ==========================================================================================


async def test_recent_data_is_left_alone(db, retention_settings):
    await _aged_proposal(db, created_at=RECENT)
    await _aged_batch(db, created_at=RECENT)
    await _aged_error(db, occurred_at=RECENT)

    report = await run(settings=retention_settings, database=db, now=NOW)

    assert (report.proposals, report.batch_jobs, report.batch_files, report.error_log) == (
        0,
        0,
        0,
        0,
    )
    assert await _counts(db) == {
        "proposals": 1,
        "audit_events": 2,
        "batch_jobs": 1,
        "batch_files": 1,
        "error_log": 1,
    }


async def test_children_go_before_parents_and_every_table_is_covered(db, retention_settings):
    await _aged_proposal(db, created_at=ANCIENT)
    await _aged_batch(db, created_at=ANCIENT)
    await _aged_error(db, occurred_at=ANCIENT)

    report = await run(settings=retention_settings, database=db, now=NOW)

    assert (report.batch_files, report.batch_jobs, report.proposals, report.error_log) == (
        1,
        1,
        1,
        1,
    )
    remaining = await _counts(db)
    assert remaining["batch_files"] == 0
    assert remaining["batch_jobs"] == 0
    assert remaining["proposals"] == 0
    assert remaining["error_log"] == 0


async def test_a_row_on_the_boundary_is_kept(db, retention_settings):
    """`created_at < cutoff`, strictly. A row exactly at the boundary is inside the window."""
    await _aged_proposal(db, created_at=cutoff_for(30, now=NOW), decided=False)

    report = await run(settings=retention_settings, database=db, now=NOW)

    assert report.proposals == 0


async def test_days_overrides_the_setting(db, retention_settings):
    await _aged_proposal(db, created_at=NOW - timedelta(days=45), decided=False)

    kept = await run(settings=retention_settings, database=db, now=NOW, days=90, dry_run=True)
    assert kept.proposals == 0

    purged = await run(settings=retention_settings, database=db, now=NOW, days=10)
    assert purged.proposals == 1


# ==========================================================================================
# safety
# ==========================================================================================


async def test_running_it_twice_does_nothing_the_second_time(db, retention_settings):
    """Idempotent, and without a marker column: the predicate simply matches nothing."""
    await _aged_proposal(db, created_at=ANCIENT)
    await _aged_batch(db, created_at=ANCIENT)

    first = await run(settings=retention_settings, database=db, now=NOW)
    after_first = await _counts(db)

    second = await run(settings=retention_settings, database=db, now=NOW)

    assert first.total_rows > 0
    assert second.total_rows == 0
    # In particular, no second DATA_PURGED row for a proposal that is already gone.
    assert await _counts(db) == after_first


async def test_dry_run_changes_nothing_and_still_reports(db, retention_settings):
    from pathlib import Path as FsPath

    _, archive = await _aged_batch(
        db, created_at=ANCIENT, upload=True, settings=retention_settings
    )
    await _aged_proposal(db, created_at=ANCIENT)
    before = await _counts(db)

    report = await run(settings=retention_settings, database=db, now=NOW, dry_run=True)

    assert report.dry_run is True
    assert (report.proposals, report.batch_jobs, report.batch_files) == (1, 1, 1)
    assert report.uploads_deleted == 1  # what it *would* remove
    assert await _counts(db) == before
    assert FsPath(archive).exists()


async def test_retention_enabled_false_is_a_legal_hold(db, retention_settings):
    """The switch an operator flips during a dispute. Reports, deletes nothing, exits cleanly."""
    held = retention_settings.model_copy(update={"retention_enabled": False})
    await _aged_proposal(db, created_at=ANCIENT)
    before = await _counts(db)

    report = await run(settings=held, database=db, now=NOW)

    assert report.dry_run is True
    assert report.proposals == 1
    assert await _counts(db) == before


# ==========================================================================================
# files on disk
# ==========================================================================================


async def test_the_uploaded_archive_goes_with_the_job(db, retention_settings):
    from pathlib import Path

    _, path = await _aged_batch(
        db, created_at=ANCIENT, upload=True, settings=retention_settings
    )
    assert Path(path).exists()

    report = await run(settings=retention_settings, database=db, now=NOW)

    assert report.uploads_deleted == 1
    assert not Path(path).exists()
    assert not Path(path).parent.exists()


async def test_retain_bulk_uploads_does_not_override_the_retention_policy(db, retention_settings):
    """The debug flag is about the next few days; the retention window is a legal obligation.

    An operator who turned `RETAIN_BULK_UPLOADS` on in March and forgot must not thereby have opted
    the deployment out of deleting anything.
    """
    from pathlib import Path

    retaining = retention_settings.model_copy(update={"retain_bulk_uploads": True})
    _, path = await _aged_batch(db, created_at=ANCIENT, upload=True, settings=retaining)

    report = await run(settings=retaining, database=db, now=NOW)

    assert report.uploads_deleted == 1
    assert not Path(path).exists()


async def test_a_file_that_cannot_be_deleted_rolls_the_whole_run_back(
    db, retention_settings, monkeypatch
):
    """Nothing is committed, so the rows still name the files and the next run tries again.

    The alternative — commit the rows, leave the archive — produces a file no row names, which is
    unreachable through the application and is exactly the personal data the purge exists to remove.
    """
    await _aged_proposal(db, created_at=ANCIENT)
    await _aged_batch(db, created_at=ANCIENT, upload=True, settings=retention_settings)
    before = await _counts(db)

    import scripts.purge_old_data as purge_module

    monkeypatch.setattr(purge_module, "discard_bulk_upload", lambda *a, **k: False)

    with pytest.raises(UploadsNotPurged):
        await run(settings=retention_settings, database=db, now=NOW)

    assert await _counts(db) == before
