"""Audit many PADnext deliveries in one job, and roll the honest buckets up across them.

The audit itself is untouched. Every file in a batch goes through the same `audit_delivery` that
`POST /api/v1/padnext/audit` calls, with the same catalog, the same rule store and the same policy,
and the report stored for it is byte-identical to what the single-file endpoint would have
returned. This module is only about *what happens around* that call: persisting a job, walking its
files, and adding up the results.

Three things are worth knowing before changing anything here.

**A failed file is a result, not a crash.** The per-file audit is wrapped in a bare `except
Exception`, which is normally a smell and is deliberate here: this runs in a background task with
no caller to return an error to, and one unreadable container out of a hundred must not cost the
other ninety-nine their reports. The exception's type and message are written to the row, so the
failure is visible and named rather than swallowed. What is *not* caught per file is a failure of
the batch machinery itself — a database write that will not land — which marks the whole job
`FAILED`, because a roll-up computed over rows that may not have been saved is worse than none.

**The roll-up covers the files that were audited, and says so.** Failed files contribute no euros
to any bucket. `failed_file_count` therefore travels inside `BatchAggregateSummary` and not only on
the job, so the stored `aggregate_summary_json` still states what it speaks for when read on its
own later.

**The three buckets are never merged.** At batch scale the temptation to print one "€X at risk"
headline is strongest and the error is largest: `unconfirmed` is this engine's own rule-coverage
gap — 837 of 869 exclusion rules are machine-extracted and unenforced under the default policy — so
summing it across a year of invoices manufactures a six-figure accusation against a practice that
may be billing correctly. `BatchAggregateSummary` keeps the split and re-checks the identity.

**Known limitation: `BackgroundTasks` is not durable.** A job is processed in the same process that
accepted it, so a restart mid-batch abandons the run: the row is left at `PROCESSING`, or at
`PENDING` if the process died before the task's first write, with some files still `PENDING`. That
is the price of the MVP's no-Celery, no-Redis constraint and it is stated rather than hidden.

What is *not* left to the reader is the limbo that used to follow. `reap_interrupted_batches` runs
from the lifespan, before the server accepts a request, and closes every interruptible row as
`FAILED` with `error_message = "Interrupted by server restart"` — so an abandoned run is a batch
that visibly failed and says why, rather than one that appears to still be running. Re-uploading the
files produces a fresh batch. A durable queue is still the real fix when one is wanted; nothing here
pretends to be one, and the reaper's own single-process assumption is documented on the method.

## The bulk path, and how it differs

`POST /api/v1/audit/bulk` — the commercial surface — writes its archive to disk before answering,
and that one difference changes what the two paths can promise:

    POST /padnext/batch    files in memory   → a restart loses them → reaped as FAILED
    POST /audit/bulk       archive on disk   → a restart resumes it → requeued as PENDING

So the bulk half of this module is a small **database-backed queue** rather than a task that owns
its own payload. `batch_jobs` *is* the queue: `create_bulk_job` writes a `PENDING` row with
`upload_path` set, and `drain_pending_jobs` claims rows out of it with a conditional UPDATE
(`SET status='PROCESSING' WHERE status='PENDING'`), which is atomic on both dialects and needs no
`FOR UPDATE` and no lock server. A `BackgroundTask` only *triggers* the drain; it carries nothing,
so losing it loses no work — the row is still `PENDING` and the next drain, including the one at
startup, picks it up.

That is what makes `reap_interrupted_batches` branch on `upload_path`: an in-memory batch is dead
and is failed, a bulk job is resumable and is requeued. Deliveries already `COMPLETED` before the
interruption are not re-audited, because the drain only walks file rows that are still `PENDING`.

Within one job the deliveries are audited concurrently, bounded by `BULK_SOLVE_CONCURRENCY` (4).
The ceiling is about Soufflé rather than about Python: each audit is a subprocess, so unbounded
concurrency would let one 500-file upload start 500 solvers.

What this still is not is a distributed queue. The claim is atomic, so two processes cannot take
the same job — but nothing renews a lease, so a job claimed by a process that then dies stays
`PROCESSING` until a restart requeues it, and under `--workers > 1` that restart is the wrong
process's. `REAP_INTERRUPTED_BATCHES=false` is the switch for that deployment, and the honest
answer remains a real queue.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.config import Settings, get_settings
from app.db.models import BatchFileRecord, BatchJobRecord, as_utc, utcnow
from app.db.session import Database, get_database
from app.padnext import audit_delivery, read_delivery
from app.schemas.batch import (
    BatchAggregateSummary,
    BatchAuditAccepted,
    BatchAuditJob,
    BatchAuditJobList,
    BatchAuditJobSummary,
    BatchFileResult,
    BatchFileStatus,
    BatchJobStatus,
)
from app.schemas.padnext import PadnextAuditReport
from app.services.bulk_archive import ArchiveMember, read_member
from app.services.export import build_batch_zip
from app.services.uploads import discard_bulk_upload

# The actor vocabulary is defined once, next to the audit log that gave it meaning.
from app.services.proposal_store import SYSTEM_ACTOR

log = logging.getLogger(__name__)

#: Public batch handle: `batch_<16 hex>`. The same shape and the same 64 bits of entropy as
#: `prop_<hex>`, for the same reason — it is guessable-resistant and it is not the surrogate key.
BATCH_ID_HEX_DIGITS = 16

ZERO = Decimal("0.00")

#: Default and maximum page size for `GET /padnext/batch`.
#:
#: A ceiling for the same reason the rule review queue has one: a batch row carries its whole
#: `aggregate_summary`, so an unbounded listing grows with the table. `total` travels in the
#: response, so a page never hides how many batches exist.
#:
#: **The maximum was 500 and is now 100.** A request for `limit=200` that used to be served is now
#: a `422`. Lowered on purpose, for two reasons rather than one: 500 rows each carrying a full
#: roll-up is a response no screen renders and no reviewer reads, and the two list endpoints now
#: have to agree — a client that can page proposals and batches with one helper is worth more than
#: a ceiling nobody asked for. See `MAX_PROPOSAL_LIST_LIMIT`, which is the same number for a
#: stricter reason (a proposal row carries a whole solver result).
DEFAULT_BATCH_LIST_LIMIT = 50
MAX_BATCH_LIST_LIMIT = 100

#: The statuses a batch cannot still legitimately be in once the process that owned it is gone.
#:
#: `PENDING` belongs here as well as `PROCESSING`. A job is written `PENDING` by `create_batch` and
#: moved to `PROCESSING` by the background task, so a process that died between the `202` and the
#: task's first write leaves a `PENDING` row that nothing will ever pick up — the same permanent
#: limbo as an interrupted `PROCESSING` row, reached one step earlier.
INTERRUPTIBLE_STATUSES = (str(BatchJobStatus.PENDING), str(BatchJobStatus.PROCESSING))

#: What a reaped batch says happened to it. Written to `batch_jobs.error_message`, which the
#: listing and the detail endpoint both return, and which the batch screen already renders.
INTERRUPTED_MESSAGE = "Interrupted by server restart"


#: How many `PENDING` rows one claim attempt looks at before giving up.
#:
#: A bound rather than the whole queue, because the claim re-reads its candidates every time round
#: the drain loop: a queue of ten thousand would otherwise be re-selected in full for each job it
#: contains. Twenty is far more than a single-process MVP will ever have queued at once, and the
#: drain simply comes back for the next twenty.
_CLAIM_CANDIDATE_LIMIT = 20


@dataclass
class _ExpansionBudget:
    """How many more decompressed bytes one bulk job may produce.

    The declared sizes were already checked when the archive was inspected, in the request handler.
    This is the second guard, over the bytes that actually come out, because a declared size is a
    number the archive's author wrote and a zip bomb's declared size is a lie.

    **What it bounds exactly.** Up to `BULK_SOLVE_CONCURRENCY` members are decompressing at once
    and each is allowed the budget that remained when it started, so a determined bomb can overrun
    by a factor of the concurrency (4) before the counter catches up. That is stated rather than
    engineered away: the memory that actually matters is what is resident at one instant, and that
    is bounded by the same four members regardless. Making the reservation exact would mean
    serialising the extractions, which would cost every honest upload its parallelism to close a
    gap a factor of four wide.

    Not thread-safe and does not need to be: `spend` is called from the event loop after an
    `await`, never from inside the threadpool.
    """

    remaining: int

    def spend(self, count: int) -> None:
        self.remaining = max(0, self.remaining - count)


def new_batch_id() -> str:
    return f"batch_{uuid.uuid4().hex[:BATCH_ID_HEX_DIGITS]}"


class BatchNotFound(KeyError):
    def __init__(self, batch_id: str) -> None:
        super().__init__(batch_id)
        self.batch_id = batch_id


class EmptyBatch(ValueError):
    """A batch was submitted with no files. Refused rather than stored as an empty job."""


class BatchNotExportable(RuntimeError):
    """An export was asked for on a batch that has not finished.

    A running batch has an aggregate of "as far as we have got", and a `FAILED` one has none at
    all. Either would leave a billing centre holding a CSV whose totals are a snapshot of a moment
    nobody can identify, so both are refused rather than served with a caveat.
    """

    def __init__(self, batch_id: str, status: BatchJobStatus) -> None:
        super().__init__(
            f"Batch {batch_id} is {status}, not COMPLETED. Only a completed batch can be "
            "exported: a partial roll-up is not a document anyone should reconcile against."
        )
        self.batch_id = batch_id
        self.status = status


#: One upload as it reaches this layer: the client's filename and the bytes themselves.
#:
#: The bytes are read in the request handler and passed through, because `UploadFile` is closed as
#: soon as the response is sent — reading it inside the background task would find an empty stream.
#: Nothing is written to disk: an uploaded billing document lives in this process's memory for the
#: length of the job and nowhere else, which is also why the endpoint caps the total upload size.
Upload = tuple[str, bytes]


# ------------------------------------------------------------------------------------------
# the audit of one file
# ------------------------------------------------------------------------------------------


def audit_bytes(content: bytes, *, filename: str, pipe: Any) -> PadnextAuditReport:
    """Read one delivery and audit it — exactly what `POST /padnext/audit` does, minus the HTTP.

    Blocking: `audit_delivery` shells out to Soufflé. Callers on the event loop must hand this to
    `run_in_threadpool`, which is what `process_batch` does.

    Deliberately not refactored out of `app/api/padnext.py` and shared. That endpoint is frozen by
    the brief — it must keep working exactly as it does — and the way to guarantee that is to leave
    it alone rather than to reshape it around a second caller. What is shared is what matters:
    `read_delivery` and `audit_delivery` themselves, so the two paths cannot reach different
    verdicts about the same file.
    """
    delivery, read_findings = read_delivery(content, source_name=filename)
    return audit_delivery(
        delivery,
        catalog=pipe.catalog,
        rules=pipe.rules,
        souffle_run=pipe.souffle.run,
        read_findings=read_findings,
        settings=pipe.settings,
    )


def describe_failure(exc: BaseException) -> str:
    """The message stored on a failed file.

    The exception type is prefixed because the messages differ wildly in how self-describing they
    are — `RealDataRefused` says everything, a `KeyError` says almost nothing — and a user staring
    at one failed file out of a hundred needs to be able to tell "this file is not a PADnext
    delivery" from "the rules engine was not running".
    """
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


# ------------------------------------------------------------------------------------------
# the roll-up
# ------------------------------------------------------------------------------------------


def aggregate_reports(
    reports: Sequence[PadnextAuditReport],
    *,
    file_count: int,
    failed_file_count: int,
) -> BatchAggregateSummary:
    """Sum the honest buckets across the completed files.

    Pure, and separated from the store on purpose: the aggregation is the commercially load-bearing
    arithmetic in this feature, so it has to be testable without a database, a background task or a
    Soufflé binary. `tests/test_batch_audit.py` calls it directly with hand-built reports.

    Every total is a `Decimal` sum of exact `Decimal` inputs — no float touches money. The one
    float is `coverage_ratio`, which is a display ratio and is computed from the summed euros
    rather than as a mean of the per-file ratios: averaging ratios weights a €40 invoice the same
    as a €40,000 one, which is not a statement about the batch.
    """
    claimed = sum((r.claimed_total_eur for r in reports), ZERO)
    fine = sum((r.confirmed_fine_eur for r in reports), ZERO)
    wrong = sum((r.confirmed_wrong_eur for r in reports), ZERO)
    unconfirmed = sum((r.unconfirmed_eur for r in reports), ZERO)

    counts = {"confirmed_fine": 0, "confirmed_wrong": 0, "unconfirmed": 0}
    positions = 0
    for report in reports:
        positions += len(report.positions)
        for bucket, count in report.bucket_summary().items():
            counts[bucket] += count

    # Guarded rather than tried-and-excepted: a batch of empty deliveries claims nothing, and
    # "0 % of nothing was audited" is the honest answer, not a division error.
    coverage = float((fine + wrong) / claimed) if claimed > 0 else 0.0

    return BatchAggregateSummary(
        file_count=file_count,
        completed_file_count=len(reports),
        failed_file_count=failed_file_count,
        position_count=positions,
        confirmed_fine_positions=counts["confirmed_fine"],
        confirmed_wrong_positions=counts["confirmed_wrong"],
        unconfirmed_positions=counts["unconfirmed"],
        claimed_total_eur=claimed,
        confirmed_fine_eur=fine,
        confirmed_wrong_eur=wrong,
        unconfirmed_eur=unconfirmed,
        coverage_ratio=coverage,
    )


def risk_sort_key(result: BatchFileResult) -> tuple[int, Decimal, Decimal, str]:
    """Riskiest first: most `confirmed_wrong_eur`, then largest claim, then by name.

    Sorted in the engine rather than in the browser, and that is a rule rather than a preference.
    The web app is forbidden from doing arithmetic on money (`CONTRIBUTING.md`, hard rule 3) — the
    amounts are exact decimal strings precisely so JavaScript cannot round them — so a table sorted
    by `confirmed_wrong_eur` has to arrive already sorted.

    Files without a report sort last: a delivery that failed has no risk figure, and putting a
    zero-valued row above a €3,000 finding would misrepresent both.
    """
    report = result.report
    if report is None:
        return (1, ZERO, ZERO, result.filename)
    return (0, -report.confirmed_wrong_eur, -report.claimed_total_eur, result.filename)


# ------------------------------------------------------------------------------------------
# the store and the background task
# ------------------------------------------------------------------------------------------


def _to_file_result(record: BatchFileRecord, *, include_report: bool) -> BatchFileResult:
    report = None
    if include_report and record.report_json is not None:
        # Validated rather than passed through: `PadnextAuditReport` re-checks that the three
        # buckets reconcile, so a row corrupted between write and read fails here instead of
        # rendering a dashboard whose totals do not add up.
        report = PadnextAuditReport.model_validate(record.report_json)
    return BatchFileResult(
        filename=record.filename,
        status=BatchFileStatus(record.status),
        error_message=record.error_message,
        report=report,
    )


class BatchAuditService:
    """Everything a batch needs: create it, process it, read it back.

    One class rather than a store and a separate worker, because the two share every invariant —
    which statuses may follow which, and what "completed" means for the roll-up — and splitting
    them would put half the state machine in each. The seam that does matter is kept: no ORM object
    leaves a session, and the pipeline is injected.
    """

    def __init__(
        self,
        database: Database | None = None,
        pipeline_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._database = database
        self._pipeline_factory = pipeline_factory

        # One drain at a time within this process. Built here rather than at module scope because
        # an `asyncio.Lock` created before a loop exists binds to the wrong one in Python's older
        # semantics, and this class is instantiated lazily by `app.api.deps` inside a running app.
        # It is not the cross-process guard — see `_claim_next_bulk_job`, which is.
        self._drain_lock = asyncio.Lock()

    @property
    def database(self) -> Database:
        return self._database if self._database is not None else get_database()

    def pipeline(self) -> Any:
        if self._pipeline_factory is not None:
            return self._pipeline_factory()
        from app.api.deps import pipeline

        return pipeline()

    # -- create ----------------------------------------------------------------------------

    async def create_batch(
        self,
        uploads: Sequence[Upload],
        *,
        actor: str = SYSTEM_ACTOR,
        organization_id: str | None = None,
    ) -> tuple[BatchAuditAccepted, list[Upload]]:
        """Write the job and one row per file, all `PENDING`, in one transaction.

        Returns the `202` body together with the uploads re-keyed to the rows that were written, so
        the background task walks database rows it knows exist rather than re-deriving them from
        filenames — which are not unique within a batch and could not identify a row.

        `actor` is the Better Auth user id the web tier forwarded (`app.api.identity`), or `system`
        for a call that carried no session. It is stored on the job rather than in an audit event
        because `batch_jobs` has no audit log and should not grow one: a batch is a computation the
        engine ran, not a decision somebody took, and the only attribution question it raises is
        "whose queue is this".

        `organization_id` is the tenancy boundary and is written once, here. It is not on
        `BatchFileRecord`: a file is reachable only through its batch, so scoping the parent scopes
        the child, and a second copy of the tenant per file would be a fact with two places to
        disagree with itself. `None` writes a row no tenant's filter matches — see the note on the
        same default in `app.services.proposal_store.ProposalStore`.
        """
        if not uploads:
            raise EmptyBatch("A batch needs at least one file.")

        batch_id = new_batch_id()
        created_at = utcnow()
        job = BatchJobRecord(
            batch_id=batch_id,
            status=str(BatchJobStatus.PENDING),
            created_at=created_at,
            created_by=actor or SYSTEM_ACTOR,
            organization_id=organization_id,
        )
        records = [
            BatchFileRecord(job=job, filename=filename, status=str(BatchFileStatus.PENDING))
            for filename, _ in uploads
        ]

        async with self.database.session() as session:
            session.add(job)
            for record in records:
                session.add(record)
            await session.flush()
            file_ids = [record.id for record in records]

        log.info("batch %s accepted with %d file(s)", batch_id, len(uploads))
        return (
            BatchAuditAccepted(
                batch_id=batch_id,
                status=BatchJobStatus.PENDING,
                file_count=len(uploads),
                created_at=as_utc(created_at),
            ),
            list(zip(file_ids, uploads, strict=True)),
        )

    # -- read ------------------------------------------------------------------------------

    async def load_batch(
        self, batch_id: str, *, organization_id: str | None = None
    ) -> BatchAuditJob:
        """The job, its progress, and — once it is terminal — every file's report.

        Reports are withheld while the job is still running. A two-second poll over a hundred
        files would otherwise ship a hundred full audit reports on every tick, for a screen that
        is showing a progress bar and nothing else.

        A batch belonging to another organisation raises `BatchNotFound`, so the endpoint answers
        `404` rather than a permission error — the same reasoning as `ProposalStore.get_proposal`:
        `403` would confirm that a given `batch_…` id exists, and the screen that polls this one
        every two seconds must not be able to enumerate another practice's uploads.
        """
        statement = (
            select(BatchJobRecord)
            .where(BatchJobRecord.batch_id == batch_id)
            .options(selectinload(BatchJobRecord.files))
        )
        if organization_id is not None:
            statement = statement.where(BatchJobRecord.organization_id == organization_id)
        async with self.database.session() as session:
            job = (await session.execute(statement)).scalar_one_or_none()
            if job is None:
                raise BatchNotFound(batch_id)

            status = BatchJobStatus(job.status)
            terminal = status in {BatchJobStatus.COMPLETED, BatchJobStatus.FAILED}
            files = [_to_file_result(record, include_report=terminal) for record in job.files]
            files.sort(key=risk_sort_key)

            completed = sum(1 for f in files if f.status is BatchFileStatus.COMPLETED)
            failed = sum(1 for f in files if f.status is BatchFileStatus.FAILED)

            return BatchAuditJob(
                batch_id=job.batch_id,
                status=status,
                created_at=as_utc(job.created_at),
                completed_at=as_utc(job.completed_at),
                file_count=len(files),
                processed_file_count=completed + failed,
                completed_file_count=completed,
                failed_file_count=failed,
                error_message=job.error_message,
                aggregate_summary=(
                    BatchAggregateSummary.model_validate(job.aggregate_summary_json)
                    if job.aggregate_summary_json is not None
                    else None
                ),
                files=files,
            )

    async def list_batches(
        self,
        *,
        status: BatchJobStatus | None = None,
        created_after: datetime | None = None,
        limit: int = DEFAULT_BATCH_LIST_LIMIT,
        offset: int = 0,
        organization_id: str | None = None,
    ) -> BatchAuditJobList:
        """Batches newest first, as headers without their files, filtered and paged.

        The per-file counts come from one grouped query over `batch_files` rather than from
        `selectinload`ing every file of every listed batch. That is not a micro-optimisation: the
        rows being avoided each hold a whole `PadnextAuditReport` in a JSON column, so loading a
        page of fifty batches the obvious way would read every audit report in the table to print
        fifty numbers.

        Ordered by `created_at DESC` with `batch_id` as a tie-break. The tie-break is not
        decoration — `created_at` is stamped by the application clock, two batches accepted in the
        same microsecond are possible, and a listing whose order changed between two reads of the
        same data would make paging skip or repeat a row.

        `status` is the filter an operator actually reaches for: `PROCESSING` after a restart is
        "what is still running", `FAILED` is "what the reaper closed and why". `total` is recounted
        under the same filters, so it answers "how many failed", never "how many rows exist".

        `created_after` is **inclusive** — a batch stamped exactly at that instant is returned. That
        is the reading a date picker wants ("everything from the 1st"), and it is the one the
        parameter's OpenAPI description states, because "after" alone is ambiguous enough to get a
        boundary row silently dropped. A naive value is taken as UTC and an aware one converted to
        it (`as_utc`), which is what makes the comparison mean the same thing on both dialects:
        Postgres stores `timestamptz`, SQLite stores the naive UTC string `utcnow` wrote and would
        otherwise compare a `+02:00` wall clock against it.

        **The index only covers half of this.** `ix_batch_jobs_status_created_at` is
        `(status, created_at)`, so `status` alone and `status` with `created_after` are served by it;
        `created_after` on its own has no usable leading column and falls back to a scan plus sort.
        Left as is rather than fixed with a second index: at this MVP's table sizes the scan is
        cheaper than the write cost of an index, and adding one is a schema change.
        """
        limit = max(1, min(limit, MAX_BATCH_LIST_LIMIT))
        offset = max(0, offset)

        filters = []
        # The tenant filter first, and counted into `total` with everything else, so a practice's
        # batch count is its own. An equality rather than anything that also admits `NULL`: a row
        # written before `0006` belongs to no organisation and must not surface in every one.
        if organization_id is not None:
            filters.append(BatchJobRecord.organization_id == organization_id)
        if status is not None:
            filters.append(BatchJobRecord.status == str(status))
        if created_after is not None:
            filters.append(BatchJobRecord.created_at >= as_utc(created_after))

        async with self.database.session() as session:
            total = (
                await session.execute(
                    select(func.count()).select_from(BatchJobRecord).where(*filters)
                )
            ).scalar_one()

            page = (
                (
                    await session.execute(
                        select(BatchJobRecord)
                        .where(*filters)
                        .order_by(
                            BatchJobRecord.created_at.desc(),
                            BatchJobRecord.batch_id.desc(),
                        )
                        .limit(limit)
                        .offset(offset)
                    )
                )
                .scalars()
                .all()
            )

            #: `{job.id: {file_status: count}}` for the listed page only.
            counts: dict[uuid.UUID, dict[str, int]] = {}
            if page:
                grouped = await session.execute(
                    select(
                        BatchFileRecord.batch_job_id,
                        BatchFileRecord.status,
                        func.count(),
                    )
                    .where(BatchFileRecord.batch_job_id.in_([job.id for job in page]))
                    .group_by(BatchFileRecord.batch_job_id, BatchFileRecord.status)
                )
                for job_id, file_status, count in grouped:
                    counts.setdefault(job_id, {})[file_status] = count

            jobs: list[BatchAuditJobSummary] = []
            for job in page:
                by_status = counts.get(job.id, {})
                completed = by_status.get(str(BatchFileStatus.COMPLETED), 0)
                failed = by_status.get(str(BatchFileStatus.FAILED), 0)
                jobs.append(
                    BatchAuditJobSummary(
                        batch_id=job.batch_id,
                        status=BatchJobStatus(job.status),
                        created_at=as_utc(job.created_at),
                        completed_at=as_utc(job.completed_at),
                        file_count=sum(by_status.values()),
                        processed_file_count=completed + failed,
                        completed_file_count=completed,
                        failed_file_count=failed,
                        error_message=job.error_message,
                        aggregate_summary=(
                            BatchAggregateSummary.model_validate(job.aggregate_summary_json)
                            if job.aggregate_summary_json is not None
                            else None
                        ),
                    )
                )

            return BatchAuditJobList(jobs=jobs, total=total, limit=limit, offset=offset)

    # -- recovery --------------------------------------------------------------------------

    async def reap_interrupted_batches(self, *, message: str = INTERRUPTED_MESSAGE) -> list[str]:
        """Fail every batch a previous process left mid-flight. Returns the ids it closed.

        `BackgroundTasks` is not durable: a batch is processed in the process that accepted it, so a
        restart mid-run leaves `batch_jobs.status` at `PROCESSING` (or `PENDING`, if the process died
        before the task's first write) with no task alive to move it on. Nothing in the request path
        can notice — the row is a perfectly valid record of a run that will never continue — so the
        browser polls until `POLL_TIMEOUT_MS` and the row stays in limbo forever.

        This is the operator half of that story. It runs once from the lifespan, **before** the
        server accepts a request, which is what makes it safe: at that moment no batch can belong to
        this process, so every interruptible row is by construction a leftover.

        **The files are deliberately left `PENDING`.** Marking them `FAILED` would claim they were
        audited and rejected, which is the one thing that did not happen. `PENDING` under a `FAILED`
        job reads correctly — "we never got to this delivery" — and it keeps
        `processed_file_count` honest about how far the interrupted run had got.

        **No `aggregate_summary` is written.** The same refusal `_fail_quietly` makes: a roll-up over
        the files that happened to land before the process died is a number nobody can identify the
        moment of, and it is worse than none.

        **A bulk job is requeued, not reaped.** `POST /api/v1/audit/bulk` writes its archive to
        disk before answering, so an interrupted bulk job is not a run that can never continue — it
        is a run that has not finished, and its bytes are still there. Those rows go back to
        `PENDING` and the drain started by the lifespan resumes them; only the in-memory batches,
        whose payloads died with the process, are failed. The branch is `upload_path IS NOT NULL`,
        which is the whole reason that column exists. The returned list is the ids that were
        *failed*; the requeued ones are logged and are not in it, because the caller's question is
        "what did we have to give up on".

        **The honest limit: this assumes one process owns the table.** Under `--workers > 1`, or a
        rolling deploy where a new container starts while the old one is still draining, a starting
        process would reap a batch that is genuinely running on a sibling — turning a live job into a
        `FAILED` one. It is the same single-process assumption `refresh_pipeline_rules` already
        documents, and the same fix applies (a durable queue, or a shared lock), which is the Redis
        this MVP is not allowed to add. Set `REAP_INTERRUPTED_BATCHES=false` on a multi-worker
        deployment and reap from a single migration/admin step instead.
        """
        now = utcnow()

        async with self.database.session() as session:
            stranded = (
                (
                    await session.execute(
                        select(BatchJobRecord).where(
                            BatchJobRecord.status.in_(INTERRUPTIBLE_STATUSES)
                        )
                    )
                )
                .scalars()
                .all()
            )

            reaped: list[str] = []
            requeued: list[str] = []
            for job in stranded:
                previous = job.status

                # A bulk job's payload is still on disk, so this one is not a leftover to be
                # closed — it is work that has not happened yet. Back to `PENDING`, and the drain
                # the lifespan starts afterwards picks it up. The files that were already audited
                # keep their `COMPLETED` rows and their reports: the drain only walks the ones
                # still `PENDING`, so a restart costs the deliveries that were in flight and not
                # the ones that had landed.
                if job.upload_path:
                    job.status = str(BatchJobStatus.PENDING)
                    job.error_message = None
                    requeued.append(job.batch_id)
                    log.info(
                        "batch %s was %s at startup and its archive is still on disk — requeued",
                        job.batch_id,
                        previous,
                    )
                    continue

                job.status = str(BatchJobStatus.FAILED)
                job.error_message = message
                job.completed_at = now
                # Belt and braces: `BatchAuditJob` documents that a FAILED batch carries no
                # roll-up, and `_complete` writes the summary and the COMPLETED status in one
                # transaction — so a PROCESSING row with a stored summary should not exist. If one
                # somehow does, clearing it is right: a set of totals attached to a run that was
                # abandoned is a number somebody could reconcile against, which is the one thing
                # this whole feature refuses to produce.
                job.aggregate_summary_json = None
                reaped.append(job.batch_id)
                log.warning(
                    "batch %s was %s at startup and cannot be resumed — marked FAILED (%s)",
                    job.batch_id,
                    previous,
                    message,
                )

        if reaped:
            log.warning(
                "reaped %d interrupted batch(es): %s. Re-upload the files to audit them.",
                len(reaped),
                ", ".join(reaped),
            )
        if requeued:
            log.info(
                "requeued %d resumable bulk job(s): %s", len(requeued), ", ".join(requeued)
            )
        return reaped

    # -- process ---------------------------------------------------------------------------

    async def process_batch(self, batch_id: str, payloads: Iterable[tuple[uuid.UUID, Upload]]) -> None:
        """The background task. Audits each file, then rolls the batch up.

        Never raises. It runs after the response has been sent, so there is nobody to raise *to*:
        an escaping exception would be logged by the framework and the job row would stay
        `PROCESSING` forever. Instead the machinery's own failures are caught at the end and
        written to `batch_jobs.error_message`, where the polling client can see them.
        """
        payloads = list(payloads)
        try:
            await self._set_status(batch_id, BatchJobStatus.PROCESSING)

            pipe = self.pipeline()
            for file_id, (filename, content) in payloads:
                await self._audit_one_file(file_id, filename, content, pipe)

            await self._complete(batch_id)
        except Exception as exc:  # noqa: BLE001 - the batch machinery itself broke; see docstring
            log.exception("batch %s failed", batch_id)
            await self._fail_quietly(batch_id, describe_failure(exc))

    async def _audit_one_file(
        self, file_id: uuid.UUID, filename: str, content: bytes, pipe: Any
    ) -> None:
        """Audit one file and write its verdict. A failure here is recorded, not propagated."""
        try:
            report = await run_in_threadpool(audit_bytes, content, filename=filename, pipe=pipe)
        except Exception as exc:  # noqa: BLE001 - one bad file must not cost the batch its results
            log.warning("batch file %s (%s) failed: %s", file_id, filename, exc)
            await self._write_file_outcome(
                file_id,
                status=BatchFileStatus.FAILED,
                error_message=describe_failure(exc),
            )
            return

        await self._write_file_outcome(
            file_id,
            status=BatchFileStatus.COMPLETED,
            report_json=report.model_dump(mode="json"),
        )

    async def _write_file_outcome(
        self,
        file_id: uuid.UUID,
        *,
        status: BatchFileStatus,
        report_json: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        async with self.database.session() as session:
            record = await session.get(BatchFileRecord, file_id)
            if record is None:  # pragma: no cover - the row was written in the same process
                log.error("batch file %s vanished before its result could be written", file_id)
                return
            record.status = str(status)
            record.report_json = report_json
            record.error_message = error_message

    async def _set_status(self, batch_id: str, status: BatchJobStatus) -> None:
        async with self.database.session() as session:
            job = await self._require(session, batch_id)
            job.status = str(status)

    async def _complete(self, batch_id: str) -> None:
        """Aggregate what landed and close the job, in one transaction.

        The reports are read back out of the rows rather than accumulated in memory during the
        walk. It costs one query and it means the roll-up is computed from what was actually
        persisted — if a write had silently failed, the summary would show it instead of
        confidently restating a number the database does not hold.
        """
        statement = (
            select(BatchJobRecord)
            .where(BatchJobRecord.batch_id == batch_id)
            .options(selectinload(BatchJobRecord.files))
        )
        async with self.database.session() as session:
            job = (await session.execute(statement)).scalar_one_or_none()
            if job is None:
                raise BatchNotFound(batch_id)

            reports = [
                PadnextAuditReport.model_validate(record.report_json)
                for record in job.files
                if record.status == str(BatchFileStatus.COMPLETED) and record.report_json
            ]
            failed = sum(1 for r in job.files if r.status == str(BatchFileStatus.FAILED))

            summary = aggregate_reports(
                reports, file_count=len(job.files), failed_file_count=failed
            )
            job.aggregate_summary_json = summary.model_dump(mode="json")
            job.status = str(BatchJobStatus.COMPLETED)
            job.completed_at = utcnow()

        log.info(
            "batch %s completed: %d/%d files audited, claimed %s, confirmed_wrong %s, coverage %.1f%%",
            batch_id,
            summary.completed_file_count,
            summary.file_count,
            summary.claimed_total_eur,
            summary.confirmed_wrong_eur,
            summary.coverage_ratio * 100,
        )

    async def _fail_quietly(self, batch_id: str, message: str) -> None:
        """Mark the job `FAILED`, and give up quietly if even that write cannot land.

        The batch is already in a bad state; a second exception thrown out of the error path would
        replace a legible failure with a stack trace from the framework's task runner.
        """
        try:
            async with self.database.session() as session:
                job = await self._require(session, batch_id)
                job.status = str(BatchJobStatus.FAILED)
                job.error_message = message
                job.completed_at = utcnow()
        except Exception:  # noqa: BLE001 - see docstring
            log.exception("batch %s: could not record the failure either", batch_id)

    # -- the bulk path: a database-backed queue over the same table --------------------------

    async def create_bulk_job(
        self,
        members: Sequence[ArchiveMember],
        *,
        upload_path: Path | str,
        organization_id: str,
        batch_id: str,
        actor: str = SYSTEM_ACTOR,
    ) -> BatchAuditAccepted:
        """Enqueue an archive that is already on disk. One `PENDING` row per delivery inside it.

        The file rows are written **now**, from the archive's own directory, rather than by the
        worker once it opens it. That is what lets the very first status poll answer `0 / 12`
        instead of `0 / ?`, and it means the caller's `202` already tells them how many deliveries
        the engine agreed to audit — which is the number they will reconcile their own export
        against.

        `upload_path` is stored, and storing it is the difference between this and `create_batch`:
        it says the payload survived the response, so an interrupted run is resumable rather than
        lost. See `reap_interrupted_batches`.

        No `EmptyBatch` guard here, unlike `create_batch`. An archive with nothing auditable in it
        is refused earlier and more precisely, by `inspect_archive`, which can say *why* it found
        no deliveries — the caller almost always zipped a folder of PDFs.

        `batch_id` is supplied rather than minted here, which is the one place this differs from
        `create_batch` in a way worth explaining. The archive has to be written *under* the id
        before the row exists, so that a write failure leaves no job pointing at a file that is not
        there — which means the caller has to know the id first. It comes from `new_batch_id()`
        either way; the endpoint simply calls it one step earlier.
        """
        created_at = utcnow()
        job = BatchJobRecord(
            batch_id=batch_id,
            status=str(BatchJobStatus.PENDING),
            created_at=created_at,
            created_by=actor or SYSTEM_ACTOR,
            organization_id=organization_id,
            upload_path=str(upload_path),
        )

        async with self.database.session() as session:
            session.add(job)
            for member in members:
                session.add(
                    BatchFileRecord(
                        job=job, filename=member.name, status=str(BatchFileStatus.PENDING)
                    )
                )

        log.info(
            "bulk job %s queued with %d deliveries for organisation %s",
            batch_id,
            len(members),
            organization_id,
        )
        return BatchAuditAccepted(
            batch_id=batch_id,
            status=BatchJobStatus.PENDING,
            file_count=len(members),
            created_at=as_utc(created_at),
        )

    async def drain_pending_jobs(self, *, settings: Settings | None = None) -> list[str]:
        """Process every queued bulk job, oldest first. Returns the ids it ran. Never raises.

        This is the worker, and it is deliberately a *drain* rather than a task per job. The
        `BackgroundTask` a request schedules carries no payload — it only says "there may be work"
        — so two uploads arriving together schedule two drains, the first of which does both jobs
        and the second of which finds nothing. Losing a drain therefore loses nothing: the rows are
        still `PENDING`, and the next upload (or the next restart) sweeps them up. That is the
        property a task holding its own files cannot have.

        Serialised within the process by `_drain_lock`, so those two drains do not interleave and
        double-audit a job between the claim and the status write. Across processes the atomic
        claim does that job instead — see `_claim_next_bulk_job`.

        Never raises for the reason `process_batch` does not: it runs after a response has been
        sent, so an exception would be logged by the framework and leave a row `PROCESSING`
        forever. Each job's failure is written to its own row.
        """
        settings = settings or get_settings()
        processed: list[str] = []

        async with self._drain_lock:
            while True:
                claimed = await self._claim_next_bulk_job()
                if claimed is None:
                    return processed
                batch_id, upload_path = claimed
                processed.append(batch_id)
                try:
                    await self._process_bulk_job(batch_id, upload_path, settings=settings)
                except Exception as exc:  # noqa: BLE001 - see docstring
                    log.exception("bulk job %s failed", batch_id)
                    await self._fail_quietly(batch_id, describe_failure(exc))
                    # The archive is discarded on a failure too. The job is terminal either way,
                    # and keeping the bytes of a run nobody can resume is retention without a
                    # purpose. `RETAIN_BULK_UPLOADS=true` is what an operator debugging exactly
                    # this case turns on.
                    await run_in_threadpool(
                        discard_bulk_upload, upload_path, settings=settings
                    )

    async def _claim_next_bulk_job(self) -> tuple[str, str] | None:
        """Take the oldest queued job, or `None`. `(batch_id, upload_path)`.

        The claim is a conditional UPDATE —

            UPDATE batch_jobs SET status='PROCESSING' WHERE batch_id=? AND status='PENDING'

        — and the `rowcount` decides. That is atomic on Postgres and on SQLite alike, and it needs
        no `SELECT … FOR UPDATE` (which SQLite does not have) and no lock server (which this stack
        deliberately does not have). Two processes racing for the same row: exactly one sees
        `rowcount == 1` and runs it, the other sees `0` and moves on to the next candidate.

        Candidates are re-read on each call rather than fetched once into a list, because the list
        goes stale the moment another process claims something out of it.

        `upload_path IS NOT NULL` is the filter that keeps this away from the in-memory batch path:
        a `POST /padnext/batch` row is `PENDING` only for the moment between its `202` and its own
        task's first write, and a drain that claimed one would set it `PROCESSING` and then find
        nothing to process, because those bytes are in the other task's memory.
        """
        async with self.database.session() as session:
            candidates = (
                (
                    await session.execute(
                        select(BatchJobRecord.batch_id, BatchJobRecord.upload_path)
                        .where(
                            BatchJobRecord.status == str(BatchJobStatus.PENDING),
                            BatchJobRecord.upload_path.is_not(None),
                        )
                        .order_by(BatchJobRecord.created_at)
                        .limit(_CLAIM_CANDIDATE_LIMIT)
                    )
                )
                .all()
            )

            for batch_id, upload_path in candidates:
                result = await session.execute(
                    update(BatchJobRecord)
                    .where(
                        BatchJobRecord.batch_id == batch_id,
                        BatchJobRecord.status == str(BatchJobStatus.PENDING),
                    )
                    .values(status=str(BatchJobStatus.PROCESSING))
                )
                if result.rowcount == 1:
                    return batch_id, str(upload_path)

        return None

    async def _process_bulk_job(
        self, batch_id: str, upload_path: str, *, settings: Settings
    ) -> None:
        """Audit every delivery this job still owes, roll it up, and discard the archive.

        Only rows still `PENDING` are audited. On a first run that is all of them; on a resumed run
        it is the ones that were in flight when the process died, and the reports that had already
        landed are left exactly as they were. Re-auditing a completed file would be harmless
        arithmetically — the audit is deterministic — and would still be wrong: it would overwrite
        a stored report with a fresh one produced under a possibly newer catalog, so a single
        batch's rows could end up describing two different engine states.

        The archive is read once into memory and every delivery is extracted from that buffer.
        Re-opening the file per member would be tidier and would multiply the syscalls by the file
        count for no gain; the buffer is bounded by `MAX_BULK_ZIP_BYTES`.
        """
        archive_path = Path(upload_path)
        try:
            content = await run_in_threadpool(archive_path.read_bytes)
        except OSError as exc:
            # The row says the archive is here and it is not. Nothing to audit and nothing to
            # retry: a job whose payload is gone cannot be completed, and leaving it `PROCESSING`
            # would strand it. It is FAILED with a message that names the path, because the cause
            # is operational (a volume that was not mounted, a cleanup script) and the operator
            # reading the row is the person who can fix it.
            await self._fail_quietly(
                batch_id,
                f"Das hochgeladene Archiv ist nicht mehr lesbar ({archive_path}): {exc}. "
                "— The uploaded archive could no longer be read.",
            )
            return

        pending = await self._pending_files(batch_id)
        if pending:
            budget = _ExpansionBudget(remaining=settings.max_bulk_uncompressed_bytes)
            semaphore = asyncio.Semaphore(settings.bulk_solve_concurrency)
            # The audits run in parallel; the writes that record them do not. SQLite has one
            # writer by definition, and the in-memory configuration this suite runs on shares a
            # single connection through `StaticPool` — so four sessions committing at once is a
            # race on the dialect the engine is developed against and a lock contention on the one
            # it deploys to. Serialising just the write costs nothing worth measuring next to a
            # Soufflé run, and it keeps the parallelism where the time actually goes.
            write_lock = asyncio.Lock()
            pipe = self.pipeline()
            await asyncio.gather(
                *(
                    self._audit_archive_member(
                        file_id,
                        filename,
                        content=content,
                        pipe=pipe,
                        semaphore=semaphore,
                        budget=budget,
                        write_lock=write_lock,
                    )
                    for file_id, filename in pending
                )
            )

        await self._complete(batch_id)
        await run_in_threadpool(discard_bulk_upload, upload_path, settings=settings)

    async def _pending_files(self, batch_id: str) -> list[tuple[uuid.UUID, str]]:
        """`(id, filename)` for every delivery in this job that has not been audited yet."""
        async with self.database.session() as session:
            job = await self._require(session, batch_id)
            rows = (
                (
                    await session.execute(
                        select(BatchFileRecord.id, BatchFileRecord.filename).where(
                            BatchFileRecord.batch_job_id == job.id,
                            BatchFileRecord.status == str(BatchFileStatus.PENDING),
                        )
                    )
                )
                .all()
            )
        return [(row[0], row[1]) for row in rows]

    async def _audit_archive_member(
        self,
        file_id: uuid.UUID,
        filename: str,
        *,
        content: bytes,
        pipe: Any,
        semaphore: asyncio.Semaphore,
        budget: _ExpansionBudget,
        write_lock: asyncio.Lock,
    ) -> None:
        """Extract one delivery and audit it, holding a concurrency slot for both.

        The extraction is inside the semaphore as well as the audit, deliberately: decompression is
        the step that allocates, so letting five hundred of them run while four audits proceed
        would defeat the point of bounding anything. It also means at most
        `BULK_SOLVE_CONCURRENCY` members are held decompressed at once, which is the real memory
        ceiling on a job.

        A failure here is a result, exactly as in `_audit_one_file`: the row records what went
        wrong and the rest of the job continues. That is what makes one corrupt member out of a
        hundred a line in a report rather than a failed upload.

        Two separate limits, deliberately: `semaphore` bounds how much *work* runs at once and
        `write_lock` bounds how many *writes* do. Merging them would serialise the audits, which is
        the one thing that must stay parallel.
        """
        async with semaphore:
            try:
                delivery = await run_in_threadpool(
                    read_member, content, filename, max_bytes=budget.remaining
                )
                budget.spend(len(delivery))
                report = await run_in_threadpool(
                    audit_bytes, delivery, filename=filename, pipe=pipe
                )
            except Exception as exc:  # noqa: BLE001 - one bad member must not cost the job
                log.warning("bulk member %s (%s) failed: %s", file_id, filename, exc)
                async with write_lock:
                    await self._write_file_outcome(
                        file_id,
                        status=BatchFileStatus.FAILED,
                        error_message=describe_failure(exc),
                    )
                return

        # Outside the semaphore — the audit is done and its slot belongs to the next delivery —
        # and inside the write lock, which is a different resource. See `_process_bulk_job`.
        async with write_lock:
            await self._write_file_outcome(
                file_id,
                status=BatchFileStatus.COMPLETED,
                report_json=report.model_dump(mode="json"),
            )

    # -- export ----------------------------------------------------------------------------

    async def export_batch(self, batch_id: str, *, organization_id: str | None = None) -> bytes:
        """The finished batch as a ZIP of CSVs, built from the rows.

        Read-only and idempotent: it changes no status and writes no row, so a billing centre can
        re-download the same archive as often as it likes and get byte-identical output. That is
        deliberately unlike the proposal export, and the difference is not an inconsistency — a
        proposal export is a *decision* a named person takes, once, and the lifecycle records it. A
        batch export is a rendering of a computation that already finished; there is nothing for a
        second one to contradict.

        No audit event is written either, for the plain reason that `audit_events` is keyed to a
        proposal and a batch is not one. If batch access ever needs logging it needs its own table,
        not a foreign key bent to fit.
        """
        statement = (
            select(BatchJobRecord)
            .where(BatchJobRecord.batch_id == batch_id)
            .options(selectinload(BatchJobRecord.files))
        )
        if organization_id is not None:
            statement = statement.where(BatchJobRecord.organization_id == organization_id)
        async with self.database.session() as session:
            job = (await session.execute(statement)).scalar_one_or_none()
            if job is None:
                raise BatchNotFound(batch_id)

            status = BatchJobStatus(job.status)
            if status is not BatchJobStatus.COMPLETED:
                raise BatchNotExportable(batch_id, status)

            summary = (
                BatchAggregateSummary.model_validate(job.aggregate_summary_json)
                if job.aggregate_summary_json is not None
                else None
            )
            # Sorted the same way `load_batch` sorts, so the CSV and the screen agree on what
            # "riskiest first" means. A reconciler comparing the two must not have to re-sort.
            files = sorted(
                job.files,
                key=lambda record: risk_sort_key(_to_file_result(record, include_report=True)),
            )
            return build_batch_zip(job, files, summary)

    @staticmethod
    async def _require(session, batch_id: str) -> BatchJobRecord:
        statement = select(BatchJobRecord).where(BatchJobRecord.batch_id == batch_id)
        job = (await session.execute(statement)).scalar_one_or_none()
        if job is None:
            raise BatchNotFound(batch_id)
        return job


__all__ = [
    "DEFAULT_BATCH_LIST_LIMIT",
    "INTERRUPTED_MESSAGE",
    "INTERRUPTIBLE_STATUSES",
    "MAX_BATCH_LIST_LIMIT",
    "BatchAuditService",
    "BatchNotExportable",
    "BatchNotFound",
    "EmptyBatch",
    "Upload",
    "aggregate_reports",
    "audit_bytes",
    "describe_failure",
    "new_batch_id",
    "risk_sort_key",
]
