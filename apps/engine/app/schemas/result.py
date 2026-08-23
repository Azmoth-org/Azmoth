"""The invoice draft and its audit trail — what the validation layer produces."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.case import ClinicalExtraction
from app.schemas.common import Dec, FactorBasis, RuleCoverage, Warning_
from app.schemas.facts import BlockedCode, Conflict, ProofStep
from app.schemas.solver import AnalogDecision, MissingDocumentation


class InvoiceLine(BaseModel):
    ziffer: str
    official_text: str
    punkte: int
    category: str | None
    factor: Dec
    #: Closed union, identical to `FactorDecision.basis` — a client can label every value.
    factor_basis: FactorBasis
    factor_legal_basis: str = ""
    justification_required: bool = False
    justification_present: bool = False
    justification: str | None = None
    confidence: Dec
    status: Literal["billable", "billable_analog"] = "billable"
    is_analog: bool = False
    analog_for: str | None = None
    amount_cent_unrounded: Dec = Decimal(0)
    amount_eur: Dec = Decimal(0)
    amount_eur_before_minderung: Dec = Decimal(0)
    minderung_applied: bool = False
    proof: list[ProofStep] = Field(default_factory=list)
    catalog_provenance: str = "official"
    text_quality: str = "ok"


class Totals(BaseModel):
    punkte: int = 0
    amount_cent_unrounded: Dec = Decimal(0)
    amount_eur_before_minderung: Dec = Decimal(0)
    amount_eur: Dec = Decimal(0)
    minderung_applied: bool = False
    minderung_rate: Dec = Decimal(0)
    punktwert_cent: Dec = Decimal("5.82873")
    rounding_policy: str = "ROUND_HALF_UP"
    rounding_legal_basis: str = ""


class Coding(BaseModel):
    proposed_codes: list[InvoiceLine] = Field(default_factory=list)
    blocked_codes: list[BlockedCode] = Field(default_factory=list)
    analog_codes: list[AnalogDecision] = Field(default_factory=list)
    conflicts_arbitrated: list[Conflict] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)
    missing_documentation: list[MissingDocumentation] = Field(default_factory=list)
    total: Totals = Field(default_factory=Totals)


class AuditTrailEntry(BaseModel):
    ziffer: str
    steps: list[ProofStep] = Field(default_factory=list)


class AuditTrail(BaseModel):
    extraction_mode: str
    extraction_model: str = "manual"
    extraction_confidence_avg: Dec = Decimal("1.0")
    catalog_version: str = ""
    catalog_source: str = ""
    catalog_sha256: str = ""
    rule_coverage: str = "partial"
    rules_version: str = ""
    rules_engine: str = "souffle"
    rules_engine_version: str = ""
    optimizer: str = "clingo"
    optimizer_version: str = ""
    logic_version: str = ""
    unverified_rule_policy: str = "warn"
    base_factor_policy: str = "schwellenwert"
    llm_saw_goae_catalog: bool = False
    rule_summary: dict = Field(default_factory=dict)
    #: The same counts as `rule_summary`, typed, so a client cannot misread them.
    rule_coverage_detail: RuleCoverage | None = None
    solver_status: str = ""
    timestamp: datetime
    per_code: list[AuditTrailEntry] = Field(default_factory=list)
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    #: Pure Clingo search: what `ctl.solve()` itself cost, with grounding and fact generation
    #: excluded. This is the number that a rule change is allowed to move.
    solve_time_ms: float = 0.0
    #: The whole symbolic run this trail describes — bridge, Soufflé, grounding, search,
    #: verification and validation. Always >= `solve_time_ms`.
    #:
    #: Both are measurements, not results. `app.core.canonical` strips them, so they cannot move
    #: a receipt hash or a cache key, and the golden snapshots do not see them.
    total_time_ms: float = 0.0


class CodingResponse(BaseModel):
    """The invoice draft itself. Wrapped in a `Proposal` by the API."""

    extraction: ClinicalExtraction
    coding: Coding
    audit_trail: AuditTrail
