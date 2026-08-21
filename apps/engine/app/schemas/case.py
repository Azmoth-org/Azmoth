"""The frozen input contract: clinical entities only.

No Ziffer, no factor, no money, no billing vocabulary at all — including in docstrings and field
descriptions, because Pydantic copies those into the JSON schema, and that schema is exactly what
would be handed to a model the moment extraction moved to structured outputs.
``tests/test_schema.py::test_extraction_schema_has_no_billing_fields`` enforces this, and
``tests/test_schema.py::test_openapi_extraction_component_has_no_billing_fields`` enforces it
again on the shape actually published to clients.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import Complexity, Dec, Setting, Severity, Sex


class _Entity(BaseModel):
    """Base for extracted clinical entities."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(default=None, description="Stable identifier, assigned if omitted.")
    confidence: Dec = Field(default=Decimal("1.0"))

    @field_validator("confidence", mode="before")
    @classmethod
    def _as_decimal(cls, v):
        return Decimal(str(v))

    @field_validator("confidence")
    @classmethod
    def _in_range(cls, v: Decimal) -> Decimal:
        if not (Decimal("0") <= v <= Decimal("1")):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return v


class Patient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age: int | None = Field(default=None, ge=0, le=130)
    sex: Sex | None = None
    setting: Setting = "ambulant"


class Consultation(_Entity):
    type: str = Field(min_length=1)
    duration_minutes: int | None = Field(default=None, ge=0)


class Examination(_Entity):
    type: str = Field(min_length=1)
    organ_system: str | None = None
    organs: list[str] = Field(default_factory=list)
    complexity: Complexity = "mittel"


class Procedure(_Entity):
    type: str = Field(min_length=1)
    organ: str | None = None
    details: str = ""
    complexity: Complexity = "mittel"


class LabTest(_Entity):
    type: str = Field(min_length=1)


class Diagnosis(_Entity):
    text: str = Field(min_length=1)


# NOTE — no docstring on purpose; see the module docstring. What this is: a clinical
# circumstance that may support a higher multiplier downstream under § 5 Abs. 2 GOÄ. The
# author states the clinical reason and how pronounced it was, and names which service(s) it
# refers to. No number is ever proposed here.
class JustificationFactor(_Entity):
    reason: str = Field(min_length=1)
    severity: Severity = "leicht"
    applies_to: list[str] = Field(
        default_factory=list,
        description="Entity ids or entity types this refers to. Empty = the whole encounter.",
    )

    @field_validator("applies_to", mode="before")
    @classmethod
    def _accept_scalar(cls, v):
        # A single string is accepted and normalised to a list, because writing one by hand is
        # the common case and silently ignoring it would lose a documented justification.
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


class ClinicalExtraction(BaseModel):
    """Manual clinical entities. The pipeline's only input."""

    model_config = ConfigDict(extra="forbid")

    patient: Patient = Field(default_factory=Patient)
    consultation: Consultation | None = None
    examinations: list[Examination] = Field(default_factory=list)
    procedures: list[Procedure] = Field(default_factory=list)
    lab_tests: list[LabTest] = Field(default_factory=list)
    diagnoses: list[Diagnosis] = Field(default_factory=list)
    justification_factors: list[JustificationFactor] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def _assign_ids(self) -> ClinicalExtraction:
        """Give every entity a stable id so justifications can point at one precisely."""
        if self.consultation and not self.consultation.id:
            self.consultation.id = "consultation"
        for prefix, group in (
            ("exam", self.examinations),
            ("proc", self.procedures),
            ("lab", self.lab_tests),
            ("dx", self.diagnoses),
            ("just", self.justification_factors),
        ):
            for index, entity in enumerate(group, start=1):
                if not entity.id:
                    entity.id = f"{prefix}_{index}"
        return self

    def entity_ids(self) -> set[str]:
        ids = {self.consultation.id} if self.consultation and self.consultation.id else set()
        for group in (self.examinations, self.procedures, self.lab_tests):
            ids |= {e.id for e in group if e.id}
        return ids

    def entity_types(self) -> set[str]:
        types = {self.consultation.type} if self.consultation else set()
        for group in (self.examinations, self.procedures, self.lab_tests):
            types |= {e.type for e in group}
        return types

    def average_confidence(self) -> Decimal:
        scores: list[Decimal] = []
        if self.consultation:
            scores.append(self.consultation.confidence)
        for group in (self.examinations, self.procedures, self.lab_tests, self.diagnoses):
            scores.extend(e.confidence for e in group)
        if not scores:
            return Decimal("0")
        return (sum(scores) / Decimal(len(scores))).quantize(Decimal("0.0001"))


class SolveRequest(BaseModel):
    """``POST /api/v1/solve`` — clinical entities in, an auditable draft out.

    Accepts either the envelope ``{"extraction": {...}, "setting": ...}`` or a bare extraction
    posted directly, because ``curl -d @logic/tests/cases/case_001_knee/input.json`` is the
    obvious thing to reach for and the case files are bare extractions.
    """

    model_config = ConfigDict(extra="forbid")

    extraction: ClinicalExtraction
    setting: Setting | None = Field(
        default=None, description="Overrides patient.setting; drives § 6a Minderung."
    )
    case_id: str | None = Field(
        default=None,
        description="Caller's identifier for this encounter, echoed onto the proposal.",
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_bare_extraction(cls, data):
        """Wrap a bare extraction before ``extra="forbid"`` rejects every clinical field.

        Keyed on "contains at least one extraction field" rather than "contains only extraction
        fields", so a bare extraction with a typo is still wrapped and the error names the one
        bad field instead of listing every clinical field as unexpected.
        """
        if not isinstance(data, dict) or "extraction" in data:
            return data
        if set(data) & set(ClinicalExtraction.model_fields):
            return {"extraction": data}
        return data
