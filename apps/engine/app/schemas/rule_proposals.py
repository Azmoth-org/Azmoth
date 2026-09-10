"""The contract for reporting a Ziffer this engine has no rule for at all.

Deliberately the smallest schema module in this package. There is no status, no queue and nothing
to page through — a report is a single write, and the only response a caller needs is confirmation
that it landed. See `app/db/models.py` on why this is a new table rather than a repurposing of
`rule_reviews` or `proposals`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: What `RuleProposalRequest.context` is capped at, and what `rule_proposals.context` is sized for.
#: 500 characters is enough for a sentence or two of "what I expected the engine to catch" and short
#: enough that this table cannot become a second, unbounded free-text log by accident.
MAX_CONTEXT_LENGTH = 500

#: `rule_proposals.ziffer` and `rule_proposals.receipt_hash` are sized to match.
MAX_ZIFFER_LENGTH = 16
MAX_RECEIPT_HASH_LENGTH = 64


class RuleProposalRequest(BaseModel):
    """One pilot's report that a Ziffer has no rule at all."""

    model_config = ConfigDict(extra="forbid")

    #: The GOÄ position the reporter says is missing a rule. Not validated against the loaded
    #: catalog — see `RuleProposalRecord` on why a typo'd or superseded Ziffer is still worth
    #: recording rather than refusing.
    ziffer: str = Field(min_length=1, max_length=MAX_ZIFFER_LENGTH)

    #: What the reporter expected the engine to catch. Required: a bare Ziffer with no context is
    #: not something the next reviewer can act on, and a textarea with nothing typed in it is
    #: indistinguishable from a form submitted by accident.
    context: str = Field(min_length=1, max_length=MAX_CONTEXT_LENGTH)

    #: The receipt of the audit report the reporter had open, if any. Optional: a pilot may notice a
    #: gap without a specific report in front of them.
    receipt_hash: str | None = Field(default=None, max_length=MAX_RECEIPT_HASH_LENGTH)

    @field_validator("ziffer", "context", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("receipt_hash", mode="before")
    @classmethod
    def _blank_receipt_is_none(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class RuleProposal(BaseModel):
    """A stored report, echoed back as confirmation of what was recorded."""

    model_config = ConfigDict(extra="forbid")

    id: str
    ziffer: str
    context: str
    receipt_hash: str | None = None
    created_at: datetime


__all__ = [
    "MAX_CONTEXT_LENGTH",
    "MAX_RECEIPT_HASH_LENGTH",
    "MAX_ZIFFER_LENGTH",
    "RuleProposal",
    "RuleProposalRequest",
]
