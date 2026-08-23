"""A batch of PADnext deliveries, and the roll-up across them.

One file at a time answers "is this invoice defensible?". A year of files answers a different and
more valuable question — "is this practice's billing systematically wrong, and where?" — and that
is what a batch is for. Nothing about the audit itself changes: each file goes through exactly the
same `audit_delivery` the single-file endpoint calls, and the batch layer only decides what to do
with the reports afterwards.

**The three buckets survive aggregation, and that is the whole design constraint.** It would be
easy, and wrong, to roll a batch up into one headline "€X at risk". The single-file schema removed
that number on purpose (see `app.schemas.padnext` for what conflating the buckets cost), and a
batch makes the error worse rather than better: summing an engine's own coverage gap over a hundred
invoices produces a six-figure accusation against a practice whose billing may be entirely correct.
So `BatchAggregateSummary` carries the same three-way split, holds the same identity —

    confirmed_fine + confirmed_wrong + unconfirmed == claimed_total

— and enforces it in a validator, exactly as `PadnextAuditReport` does.

**The aggregate covers the files that were audited, and says which ones were not.** A file that
could not be read contributes nothing to any total, and `failed_file_count` is part of the summary
rather than only of the job around it, so a stored `aggregate_summary_json` read on its own still
says how much of the batch it speaks for.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import Dec
from app.schemas.padnext import PadnextAuditReport


class BatchJobStatus(StrEnum):
    """Where a batch is in its life.

    `FAILED` is deliberately narrow: it means the *batch itself* broke — the background task raised
    before it could finish, or the store refused a write — and there is no roll-up to show. A run in
    which every file failed to parse is `COMPLETED`, because the run did complete and its output is
    a hundred per-file error messages a user needs to read. Marking that `FAILED` would hide them
    behind a status that says "nothing to see".
    """

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BatchFileStatus(StrEnum):
    """Where one file in a batch is.

    No `PROCESSING`: files are audited one after another and the transition out of `PENDING` is a
    single write at the end of the file's audit. A per-file in-progress state would be a second
    write per file bought for nothing — the job's own `PROCESSING` already says work is happening,
    and the count of files still `PENDING` already says how much is left.
    """

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BatchAggregateSummary(BaseModel):
    """The honest buckets, rolled up across every file that could be audited.

    Every euro figure here is a sum of the identically-named field on the per-file
    `PadnextAuditReport`s, over files in status `COMPLETED`. Failed files are excluded from the
    money entirely — a file we could not read is not evidence of anything — and counted separately
    so the reader can see what the roll-up is missing.
    """

    model_config = ConfigDict(extra="forbid")

    #: How many files were uploaded, audited and refused. `completed + failed` is what has been
    #: processed so far; the frontend's "45 / 100" reads exactly these.
    file_count: int = 0
    completed_file_count: int = 0
    failed_file_count: int = 0

    #: Claimed positions across the completed files, and how they split by bucket. Counts, not
    #: money — the two answer different questions and a reader must be able to see both, because a
    #: single very large `confirmed_wrong` position and forty small ones are different problems.
    position_count: int = 0
    confirmed_fine_positions: int = 0
    confirmed_wrong_positions: int = 0
    unconfirmed_positions: int = 0

    #: What the completed files charge in total.
    claimed_total_eur: Dec = Decimal("0.00")

    #: Claimed euros on positions every applicable check passed, with at least one verified rule
    #: actually bearing on them. Green.
    confirmed_fine_eur: Dec = Decimal("0.00")
    #: Claimed euros shown to be non-chargeable as claimed on a verified basis. Red. The systemic
    #: figure this feature exists to produce — and still not a settled refund amount, for the same
    #: reason as the single-file field: a mutually exclusive pair puts both of its lines here.
    confirmed_wrong_eur: Dec = Decimal("0.00")
    #: Claimed euros no verified rule reached. Amber. **Not** a finding against the practice; it is
    #: the boundary of this engine's rule coverage, and at batch scale it will usually be the
    #: largest of the three. Presenting it as exposure is the overclaim the split exists to stop.
    unconfirmed_eur: Dec = Decimal("0.00")

    #: `(confirmed_fine + confirmed_wrong) / claimed_total` over the whole batch, in `[0.0, 1.0]`.
    #: Computed from the summed euros rather than averaged over the per-file ratios: a mean of
    #: ratios weights a €40 invoice the same as a €40,000 one and is not a statement about the
    #: batch. A float because it is a display ratio, never money.
    coverage_ratio: float = 0.0

    BUCKET_TOLERANCE_EUR: ClassVar[Decimal] = Decimal("0.01")

    @model_validator(mode="after")
    def _check_buckets_reconcile(self) -> BatchAggregateSummary:
        """The same refusal `PadnextAuditReport` makes, for the same reason.

        Each per-file report has already proved its own three buckets sum to its claimed total, and
        summation preserves that, so this can only fire if a file was added to one total and not to
        another — which would make every number a practice acts on wrong in a way no reader could
        detect.
        """
        bucketed = self.confirmed_fine_eur + self.confirmed_wrong_eur + self.unconfirmed_eur
        drift = abs(bucketed - self.claimed_total_eur)
        if drift > self.BUCKET_TOLERANCE_EUR:
            raise ValueError(
                f"Batch aggregate buckets do not reconcile: confirmed_fine "
                f"{self.confirmed_fine_eur} + confirmed_wrong {self.confirmed_wrong_eur} + "
                f"unconfirmed {self.unconfirmed_eur} = {bucketed}, but claimed_total is "
                f"{self.claimed_total_eur} (off by {drift}). Every completed file's claimed total "
                "must be added to exactly one set of buckets."
            )
        return self


class BatchFileResult(BaseModel):
    """One uploaded file and what became of it."""

    model_config = ConfigDict(extra="forbid")

    filename: str
    status: BatchFileStatus

    #: Why this file could not be audited. Present only on `FAILED`, and it is the reader's only
    #: account of what went wrong, so it carries the exception's own message rather than a generic
    #: "processing error".
    error_message: str | None = None

    #: The single-file report, byte-identical in shape to what `POST /padnext/audit` returns —
    #: which is what lets the batch screen reuse the single-file components unchanged.
    #:
    #: Omitted while the job is still running, so a two-second poll over a hundred files does not
    #: ship a hundred full reports each time. It is populated once the job reaches a terminal
    #: status; see `app.services.batch_audit.load_batch`.
    report: PadnextAuditReport | None = None


class BatchAuditJob(BaseModel):
    """A batch, its progress, and — once it is done — the roll-up and every file's report."""

    model_config = ConfigDict(extra="forbid")

    batch_id: str
    status: BatchJobStatus
    created_at: datetime
    completed_at: datetime | None = None

    file_count: int = 0
    #: Files that reached a terminal state, of either kind. What a progress indicator divides by
    #: `file_count`; kept as a field rather than left to the client to add up, because it must
    #: agree with the statuses in `files` and there is one place to make sure it does.
    processed_file_count: int = 0
    completed_file_count: int = 0
    failed_file_count: int = 0

    #: Why the batch itself failed. Distinct from a file's `error_message`: this one means no
    #: roll-up exists, not that one delivery was unreadable.
    error_message: str | None = None

    #: Present once the job is `COMPLETED`. Null while it runs, and null on a `FAILED` job — a
    #: batch whose processing broke half-way has no total worth showing.
    aggregate_summary: BatchAggregateSummary | None = None

    #: Every uploaded file. Ordered by `confirmed_wrong_eur` descending — riskiest first — so the
    #: table the UI renders is sorted by the engine and not by JavaScript parsing euro strings back
    #: into numbers. Files still pending, and files that failed, sort last; see
    #: `app.services.batch_audit.risk_sort_key`.
    files: list[BatchFileResult] = Field(default_factory=list)


class BatchAuditJobSummary(BaseModel):
    """One batch as a listing row: the header, without the files.

    Deliberately not `BatchAuditJob` with `files` left empty. A listing of fifty batches, each
    carrying every delivery's full `PadnextAuditReport`, is megabytes of JSON to render a table of
    fifty rows — and a client handed a `BatchAuditJob` with an empty `files` list could not tell
    "this batch has no files" from "this response does not carry them". A separate model makes the
    absence structural: there is no `files` field to misread.

    The per-file counts are still here, because "3 von 10 geprüft" is the one thing a listing has to
    be able to say, and they are computed from `batch_files` rather than read out of
    `aggregate_summary` — which is null while a job runs and on a job that failed, exactly the two
    cases where a reader most wants to know how far it got.
    """

    model_config = ConfigDict(extra="forbid")

    batch_id: str
    status: BatchJobStatus
    created_at: datetime
    completed_at: datetime | None = None

    file_count: int = 0
    processed_file_count: int = 0
    completed_file_count: int = 0
    failed_file_count: int = 0

    #: Why the batch itself failed. On a batch reaped after a restart this carries that reason, so a
    #: listing is where an operator finds out a run was interrupted rather than having to open it.
    error_message: str | None = None

    #: The stored roll-up, present only on a `COMPLETED` batch. Carried in the listing because it is
    #: what makes the list useful — a reader scanning for the batch with the largest
    #: `confirmed_wrong_eur` should not have to open each one.
    aggregate_summary: BatchAggregateSummary | None = None


class BatchAuditJobList(BaseModel):
    """A page of batches, newest first, and how many there are in total.

    `total` is the whole table, not the page. A listing that only reported what it returned would
    let a `limit` silently become "how many batches exist" — the same reason
    `RuleReviewQueue.pending_rule_count` reports the real backlog rather than the page.
    """

    model_config = ConfigDict(extra="forbid")

    jobs: list[BatchAuditJobSummary] = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    offset: int = 0


class BatchAuditAccepted(BaseModel):
    """The `202` body: the handle to poll, and nothing that is not known yet.

    Deliberately not a `BatchAuditJob` with empty fields. A response that carried a zeroed
    `aggregate_summary` would invite a client to render €0.00 across the dashboard for the second
    before its first poll returns.
    """

    model_config = ConfigDict(extra="forbid")

    batch_id: str
    status: BatchJobStatus = BatchJobStatus.PENDING
    file_count: int = 0
    created_at: datetime


__all__ = [
    "BatchAggregateSummary",
    "BatchAuditAccepted",
    "BatchAuditJob",
    "BatchAuditJobList",
    "BatchAuditJobSummary",
    "BatchFileResult",
    "BatchFileStatus",
    "BatchJobStatus",
]
