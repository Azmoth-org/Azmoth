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

    #: Rule-coverage transparency, flattened onto the proposal so it cannot be missed.
    enforced_rule_count: int = 0
    advisory_rule_count: int = 0
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
