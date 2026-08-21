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
