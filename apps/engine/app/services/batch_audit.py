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
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

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
from app.services.export import build_batch_zip

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
DEFAULT_BATCH_LIST_LIMIT = 50
MAX_BATCH_LIST_LIMIT = 500

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

    @property
    def database(self) -> Database:
        return self._database if self._database is not None else get_database()

    def pipeline(self) -> Any:
        if self._pipeline_factory is not None:
            return self._pipeline_factory()
        from app.api.deps import pipeline

        return pipeline()

    # -- create ----------------------------------------------------------------------------

    async def create_batch(self, uploads: Sequence[Upload]) -> tuple[BatchAuditAccepted, list[Upload]]:
        """Write the job and one row per file, all `PENDING`, in one transaction.

        Returns the `202` body together with the uploads re-keyed to the rows that were written, so
        the background task walks database rows it knows exist rather than re-deriving them from
        filenames — which are not unique within a batch and could not identify a row.
        """
        if not uploads:
            raise EmptyBatch("A batch needs at least one file.")

        batch_id = new_batch_id()
        created_at = utcnow()
        job = BatchJobRecord(
            batch_id=batch_id,
            status=str(BatchJobStatus.PENDING),
            created_at=created_at,
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

    async def load_batch(self, batch_id: str) -> BatchAuditJob:
        """The job, its progress, and — once it is terminal — every file's report.

        Reports are withheld while the job is still running. A two-second poll over a hundred
        files would otherwise ship a hundred full audit reports on every tick, for a screen that
        is showing a progress bar and nothing else.
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
        self, *, limit: int = DEFAULT_BATCH_LIST_LIMIT, offset: int = 0
    ) -> BatchAuditJobList:
        """Batches newest first, as headers without their files.

        The per-file counts come from one grouped query over `batch_files` rather than from
        `selectinload`ing every file of every listed batch. That is not a micro-optimisation: the
        rows being avoided each hold a whole `PadnextAuditReport` in a JSON column, so loading a
        page of fifty batches the obvious way would read every audit report in the table to print
        fifty numbers.

        Ordered by `created_at DESC` with `batch_id` as a tie-break. The tie-break is not
        decoration — `created_at` is stamped by the application clock, two batches accepted in the
        same microsecond are possible, and a listing whose order changed between two reads of the
        same data would make paging skip or repeat a row.
        """
        limit = max(1, min(limit, MAX_BATCH_LIST_LIMIT))
        offset = max(0, offset)

        async with self.database.session() as session:
            total = (
                await session.execute(select(func.count()).select_from(BatchJobRecord))
            ).scalar_one()

            page = (
                (
                    await session.execute(
                        select(BatchJobRecord)
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
            for job in stranded:
                previous = job.status
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

    # -- export ----------------------------------------------------------------------------

    async def export_batch(self, batch_id: str) -> bytes:
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
