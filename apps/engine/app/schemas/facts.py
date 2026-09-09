"""The symbolic layer: what the bridge proposes and what the Datalog rules engine concludes.

These are the facts the solver reasons over. Nothing here decides money.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Dec, Warning_


class ClinicalAct(BaseModel):
    """One chargeable-in-principle thing that happened."""

    act_id: str
    entity_id: str
    source: Literal["consultation", "examination", "procedure", "lab_test"]
    entity_type: str
    entity_subtype: str | None = None
    organ: str | None = None
    description: str = ""
    confidence: Dec = Decimal("1.0")
    #: The Leistungsdatum this act was actually rendered on, `YYYY-MM-DD`, or `None` when unknown.
    #:
    #: Feeds `datum` in `logic/datalog/goae_rules.dl` via `app/solvers/souffle_facts.py`, so a
    #: "neben" (alongside) exclusion can be restricted to services rendered on the same date
    #: instead of matching on Ziffer alone regardless of when either was claimed. `None` for every
    #: caller that does not track dates — the callsite the rule was written for, a single
    #: clinical encounter, has no use for it and the relation stays empty either way.
    service_date: str | None = None


class CodeCandidate(BaseModel):
    act_id: str
    ziffer: str
    priority: int = 100
    confidence: Dec = Decimal("1.0")
    mapping_provenance: str = ""
    mapping_notes: str = ""


class AnalogRequest(BaseModel):
    act_id: str
    entity_type: str
    description: str = ""
    confidence: Dec = Decimal("1.0")


class ProofStep(BaseModel):
    ziffer: str
    rule: str
    detail: str = ""
    rule_id: str = ""
    legal_basis: str = ""


class BlockedCode(BaseModel):
    ziffer: str
    official_text: str = ""
    reason: Literal[
        "exclusion",
        "mutual_exclusion",
        "zielleistung",
        "less_specific",
        "unknown_ziffer",
        "inactive_ziffer",
        "conflict_lost",
    ]
    detail: str = ""
    blocked_by: str | None = None
    rule_id: str = ""
    legal_basis: str = ""
    explanation: str = ""
    reconciled_with_final_invoice: bool = True

    #: `True` when this exclusion matched two claimed Ziffern known — from `datum` — to have been
    #: rendered on different service dates. "Neben" (alongside) is a clinical term, the two
    #: services performed at once, and `False`/default covers both a proven same-date match and
    #: the common case where at least one side's date is unknown, which is not evidence either
    #: way. Only ever `True` for `reason="exclusion"`; the other reasons have no date dimension.
    cross_date: bool = False

    #: Why this position is not on the invoice, as Datalog derived it.
    #:
    #: The same steps also appear in `audit_trail.per_code`, which covers charged and blocked
    #: positions alike. They are repeated here because a client should not have to know that join
    #: exists: a blocked position and its reason belong together. The validator fills this in
    #: alongside the per-position audit entry, from the same source, so the two cannot disagree.
    proof: list[ProofStep] = Field(default_factory=list)


class Conflict(BaseModel):
    ziffer_a: str
    ziffer_b: str
    rule_id: str = ""
    legal_basis: str = ""


class RulesResult(BaseModel):
    proposed: list[CodeCandidate] = Field(default_factory=list)
    billable: list[str] = Field(default_factory=list)
    arbitration_candidates: list[str] = Field(default_factory=list)
    blocked: list[BlockedCode] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    proof: list[ProofStep] = Field(default_factory=list)
    analog_requests: list[AnalogRequest] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)
    factor_needs_justification: list[str] = Field(default_factory=list)
    factor_invalid: list[str] = Field(default_factory=list)
    souffle_stdout: str = ""
