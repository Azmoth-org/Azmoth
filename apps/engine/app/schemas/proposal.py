"""A solver result becomes a **proposal**, never an invoice.

The engine produces a billing *draft*. A human with the right to bill approves it. That boundary
is the whole point of the status field: nothing leaves `DRAFT` without a named approver, and
nothing downstream may treat a `DRAFT` as chargeable.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

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

    @property
    def is_approved(self) -> bool:
        return self.status is ProposalStatus.APPROVED


class ApprovalRequest(BaseModel):
    approved_by: str = Field(min_length=1, description="Who is accepting responsibility.")
    note: str = ""


class RejectionRequest(BaseModel):
    rejected_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
