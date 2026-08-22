"""The rule verification workflow's contract.

859 of this engine's 894 constraint rules were extracted from the GOÄ's prose automatically and are
therefore not enforced: under the default policy a machine-read rule may not suppress a chargeable
service until a human has checked it. That is the single largest reason the `unconfirmed` bucket in
a PADnext audit is as big as it is — it is not a statement about anyone's billing, it is the
boundary of what this engine has been allowed to conclude.

This module is the contract for the tool that shrinks that boundary. A billing expert works a queue
of unverified rules, reads the GOÄ sentence each was extracted from, and either verifies it — after
which it enforces exactly like a hand-curated rule and moves euros out of `unconfirmed` — or rejects
it, after which it never enforces under any policy.

Two things the shapes below are careful about.

**The queue shows the evidence, not a summary of it.** `ReviewableRule` carries the source quote in
full and the Ziffern the rule would act on. A reviewer deciding whether "Die Leistung nach Nummer 4
ist neben den Leistungen nach den Nummern 30, 34 … nicht berechnungsfähig" really means what the
extractor made of it needs the sentence, not a paraphrase — and a UI that only showed a rule id
would be asking for a rubber stamp.

**Verifying is a decision, not a preference.** `reviewed_by` is required for a decision, exactly as
`approved_by` is on an approval, because verifying a rule changes what every future audit concludes
about somebody's invoice. It is recorded, not authenticated; there is no login in front of any of
this yet (`docs/compliance/PRIVATE_DATA_WARNING.md`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import RuleCoverage

#: Which rule table a reviewable rule came from. A closed union so a client can label every value.
#:
#: `analog_candidate` is absent on purpose and it is the same absence the coverage counts make: an
#: Analogansatz candidate is an *offer* under § 6 Abs. 2 GOÄ and can never remove a position from an
#: invoice, so there is nothing for a reviewer to make safe. Putting them in the queue would pad it
#: with work that changes no outcome.
RuleKind = Literal["exclusion", "zielleistung", "specificity", "factor_cap"]

#: What a reviewer decided. Mirrors `app.rules.rule_store.RuleReviewStatus`.
ReviewStatus = Literal["VERIFIED", "REJECTED", "PENDING"]

#: The two statuses that require a name. `PENDING` is a bookmark, not a decision.
DECIDED_STATUSES = frozenset({"VERIFIED", "REJECTED"})


class ReviewableRule(BaseModel):
    """One rule as the review queue presents it — everything needed to decide, and nothing else."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    kind: RuleKind

    #: The GOÄ paragraph or Anmerkung the extractor attributed the rule to.
    legal_basis: str = ""
    #: The sentence it was extracted from, verbatim. The evidence a reviewer actually reads.
    quote: str = ""
    #: How it got here — `auto_extracted:ist_neben`, `manual`, and so on. A reviewer treats an
    #: `ist_neben` extraction differently from a hand-written rule, so the pattern is not hidden.
    source: str = ""

    #: The Ziffern this rule would act on, in the order the rule states them. Two for an exclusion
    #: (from, to), two for a Zielleistung (parent, child) or a specificity pair, one for a factor
    #: cap. A list rather than named fields because the queue is heterogeneous and a client that
    #: had to switch on `kind` to find the numbers would render four tables instead of one.
    ziffern: list[str] = Field(default_factory=list)
    #: What the Ziffern mean, keyed by the role the rule gives them — `from`/`to`,
    #: `parent`/`child`, `specific`/`general`, `ziffer`. So the UI can label them correctly.
    ziffer_roles: dict[str, str] = Field(default_factory=dict)

    #: Type-specific detail: `direction` for an exclusion, `max_factor` for a factor cap. Kept out
    #: of the top level so adding a rule type does not widen this model for every other one.
    detail: dict[str, Any] = Field(default_factory=dict)

    #: What the CSV itself says. `false` for everything in the queue, by construction — carried so
    #: a client reading a single rule outside the queue can still tell.
    csv_verified: bool = False
    #: The effective flag after reviews are merged. Also `false` throughout the queue.
    verified: bool = False
    #: `null` when nobody has touched this rule. `PENDING` when somebody parked it.
    review_status: ReviewStatus | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None


class RuleReviewQueue(BaseModel):
    """The rules still awaiting a decision, with enough context to show progress."""

    model_config = ConfigDict(extra="forbid")

    #: Every constraint rule the engine loaded — the denominator on the dashboard. 894 as shipped.
    total_constraint_rules: int = 0
    #: Rules with an effective `verified` flag: the CSV's own plus everything a reviewer promoted.
    verified_rule_count: int = 0
    #: The subset of those that a reviewer promoted. What the queue has achieved so far.
    review_verified_rule_count: int = 0
    #: Explicitly refused. Not enforced, and not counted as a coverage gap either.
    rejected_rule_count: int = 0
    #: How many rules are still undecided in total — which is `len(rules)` plus anything filtered
    #: out of this page by `kind`. Present so a filtered view can still show the real backlog.
    pending_rule_count: int = 0

    #: The queue itself, after any `kind` filter and `limit`.
    rules: list[ReviewableRule] = Field(default_factory=list)
    #: True when `limit` cut the list short — so a UI can say "showing 100 of 859" honestly rather
    #: than implying the backlog is the page.
    truncated: bool = False


class RuleReviewRequest(BaseModel):
    """A reviewer's verdict on one rule."""

    model_config = ConfigDict(extra="forbid")

    status: ReviewStatus
    #: Required for `VERIFIED` and `REJECTED`; optional for `PENDING`, which decides nothing.
    #: Verifying a rule changes what every future audit concludes about somebody's invoice, so an
    #: unattributed verification is not one — the same argument as `approved_by` on an approval.
    reviewed_by: str = ""
    #: Why. Optional but strongly wanted: the next reviewer to look at a neighbouring rule needs it.
    review_notes: str = ""

    @field_validator("reviewed_by", "review_notes", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _decisions_need_a_name(self) -> RuleReviewRequest:
        if self.status in DECIDED_STATUSES and not self.reviewed_by:
            raise ValueError(
                f"reviewed_by is required to mark a rule {self.status}. Verifying a rule changes "
                "what every future audit concludes about an invoice; an unattributed decision "
                "cannot be accounted for later. PENDING may be left unattributed."
            )
        return self


class RuleReviewResult(BaseModel):
    """The rule after the review was applied, plus the coverage it moved."""

    model_config = ConfigDict(extra="forbid")

    rule: ReviewableRule
    #: Recomputed from the merged rule store, so a client can update its progress bar from the
    #: same response rather than issuing a second request that could see a different world.
    coverage: RuleCoverage


__all__ = [
    "DECIDED_STATUSES",
    "ReviewStatus",
    "ReviewableRule",
    "RuleKind",
    "RuleReviewQueue",
    "RuleReviewRequest",
    "RuleReviewResult",
]
