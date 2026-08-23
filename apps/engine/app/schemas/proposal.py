"""A solver result becomes a **proposal**, never an invoice.

The engine produces a billing *draft*. A human with the right to bill approves it. That boundary
is the whole point of the status field: nothing leaves `DRAFT` without a named approver, and
nothing downstream may treat a `DRAFT` as chargeable.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import RuleCoverage, Warning_
from app.schemas.result import CodingResponse
from app.schemas.solver import MissingDocumentation


class ProposalStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPORTED = "EXPORTED"


class Proposal(BaseModel):
    """One solve, wrapped with everything a reviewer needs to accept or refuse it."""

    proposal_id: str
    case_id: str | None = None
    status: ProposalStatus = ProposalStatus.DRAFT
    created_at: datetime
    approved_at: datetime | None = None
    approved_by: str | None = None
    rejected_reason: str | None = None

    #: Identity of everything that produced the result. Two proposals with the same receipt hash
    #: were produced by the same data, the same logic and the same policy.
    receipt_hash: str
    catalog_version: str
    catalog_sha256: str = ""
    rules_version: str
    rules_hash: str = ""
    solver_version: str
    rules_engine_version: str = ""
    logic_version: str = ""

    solver_result: CodingResponse
    warnings: list[Warning_] = Field(default_factory=list)
    missing_documentation: list[MissingDocumentation] = Field(default_factory=list)

    #: How the solve ended: a Clingo result string, or `TIMEOUT_PARTIAL` when the hard timeout cut
    #: the search short and the returned model is the best found rather than a proven optimum.
    #:
    #: Promoted to the top level because it qualifies the whole proposal — a reviewer needs it in
    #: the header, next to the status and the receipt, not two levels down in the audit trail. The
    #: audit trail keeps its own copy: that is the immutable record of the run.
    solver_status: str = ""
    #: True when the solve was cancelled by `SOLVER_TIMEOUT_SECONDS`. Every hard rule still held.
    solver_timed_out: bool = False

    #: Rule-coverage transparency, flattened onto the proposal so it cannot be missed. The same
    #: numbers are in `rule_coverage`; these exist so a client cannot render a proposal without
    #: having seen them.
    enforced_rule_count: int = 0
    advisory_rule_count: int = 0
    unverified_rule_count: int = 0
    analog_candidate_count: int = 0
    suppressed_unverified_rule_count: int = 0
    rule_coverage: RuleCoverage | None = None

    #: True when the response was served from the content-addressed cache.
    cached: bool = False

    #: What the run that produced this result cost: `solve_time_ms` is pure Clingo search,
    #: `total_time_ms` is the whole symbolic pipeline. Flattened up from the audit trail for the
    #: same reason `solver_status` is — a reviewer reads them in the header, not two levels down —
    #: and derived from it in exactly one place, so the two can never disagree.
    #:
    #: They describe the *run*, not the request that served it. A `cached` proposal repeats the
    #: timings of the run that filled the cache, because that is the work the result came from;
    #: the lookup that served it took microseconds and is not a solve. Read `cached` first.
    #:
    #: Catalog and rule loading are not in either number: both loaders are `lru_cache`d, so a
    #: served request pays neither. `engine_cli.py solve --stats` reports startup separately, and
    #: `docs/performance_baseline.md` explains what that costs.
    solve_time_ms: float = 0.0
    total_time_ms: float = 0.0

    @property
    def is_approved(self) -> bool:
        return self.status is ProposalStatus.APPROVED


class ProposalList(BaseModel):
    """A page of proposals, newest first, and how many there are in total.

    This replaced a bare JSON array, and the reason is `total`. A listing that returned only what
    it was asked for could not tell a reviewer whether "50 Entwürfe" means fifty or the first fifty
    of nine hundred — and the one thing a review queue has to be able to say is how much is still
    waiting. `total` is therefore the count of everything matching the *filters*, not the page: with
    `status=DRAFT` it is the whole backlog, and it is what a "1–50 von 214" header reads.

    Same shape and same reasoning as `BatchAuditJobList`, with one deliberate difference: the field
    is `items`, not `proposals`. The batch listing shipped its rows as `jobs` before pagination
    existed here and renaming it would break a document already committed to
    `packages/contracts/`, so the two are not spelled the same. New envelopes use `items`.

    Rows are the full `Proposal`, not a reduced summary. That is a cost — every row carries its
    whole `solver_result` — and it is paid on purpose: the flattened rule-coverage counts exist so
    that a client *cannot* render a proposal without having seen them, and a listing model that
    dropped them would be the one place in the API where a draft appears without its coverage
    caveat. The `limit` ceiling of 100 is what bounds the payload instead.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[Proposal] = Field(default_factory=list)

    #: Every proposal matching the filters, not the length of `items`. See the class docstring.
    total: int = 0
    limit: int = 0
    offset: int = 0


class ApprovalRequest(BaseModel):
    approved_by: str = Field(min_length=1, description="Who is accepting responsibility.")
    note: str = ""


class RejectionRequest(BaseModel):
    rejected_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
