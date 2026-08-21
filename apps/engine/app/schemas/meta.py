"""Health, catalog provenance, and the clinical vocabulary the bridge can actually map."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import RuleCoverage


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    app_env: str
    extraction_mode: str
    catalog_version: str
    rule_coverage: str
    souffle_available: bool
    souffle_version: str = ""
    clingo_version: str = ""
    logic_version: str = ""
    catalog_ziffern: int = 0
    rules_enforced: int = 0
    unverified_rules_not_enforced: int = 0
    solver_timeout_seconds: float = 0.0
    cache_enabled: bool = True
    cache_entries: int = 0


class CatalogSource(BaseModel):
    name: str = ""
    publisher: str = ""
    url: str = ""
    retrieved_at: str = ""
    sha256_raw: str = ""
    legal_status: str = ""


class CatalogResponse(BaseModel):
    """Catalog provenance and coverage — deliberately not the full 2000-entry dump."""

    #: `coverage_detail` and `rounding` are the importer's own report and the statutory rounding
    #: block, passed through verbatim rather than re-typed, so a new field in the data cannot go
    #: missing from the API.
    model_config = ConfigDict(extra="allow")

    catalog_version: str
    rules_version: str = ""
    catalog_sha256: str = ""
    ziffern: int = 0
    active_ziffern: int = 0
    rule_coverage: str = "partial"
    provenance_breakdown: dict[str, int] = Field(default_factory=dict)
    punktwert_cent: str = ""
    rounding: dict = Field(default_factory=dict)
    source: CatalogSource = Field(default_factory=CatalogSource)
    overrides_applied: int = 0
    text_quality_flagged: int = 0
    imported_rules: dict = Field(default_factory=dict)
    rule_coverage_detail: RuleCoverage | None = None
    coverage_detail: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class LabelledOption(BaseModel):
    """An option with one display label: an organ, a subtype, a complexity qualifier.

    Organ and subtype names are clinical vocabulary and are deliberately NOT translated — the same
    reason GOÄ service texts are not. `ziffern` is informational, so a picker can show which
    position a choice leads to; the engine still decides.
    """

    value: str
    label: str
    ziffern: list[str] = Field(default_factory=list)


class BilingualOption(BaseModel):
    """An option whose label is interface text, so it exists in both languages."""

    value: str
    label_de: str
    label_en: str


class ComplexityRef(BaseModel):
    """A complexity an entity type actually has a mapping row for.

    Carries no label on purpose: the display text for `einfach` / `mittel` / `komplex` is the same
    everywhere and lives once in the top-level `complexities` list. Repeating it per entity type
    would be three ways for the same word to disagree with itself.
    """

    value: str
    ziffern: list[str] = Field(default_factory=list)


class EntityTypeOption(BaseModel):
    """One thing a user can record, with exactly the choices that map to something."""

    entity_type: str
    kind: Literal["consultation", "examination", "lab_test", "procedure"]
    label_de: str
    label_en: str
    ziffern: list[str] = Field(default_factory=list)
    organs: list[LabelledOption] = Field(default_factory=list)
    subtypes: list[LabelledOption] = Field(default_factory=list)
    complexities: list[ComplexityRef] = Field(default_factory=list)
    complexity_qualified: bool = False
    requires_organ: bool = False
    requires_subtype: bool = False
    analog_only: bool = False
    notes: str = ""


class VocabularyResponse(BaseModel):
    """What `GET /api/v1/vocabulary` returns.

    Declared as a model rather than a bare dict for one concrete reason: an endpoint with no
    OpenAPI schema cannot have a TypeScript client generated for it, so the front end wrote one by
    hand and got the shape wrong in three ways — `entity_types` declared as a flat array when the
    API returns a mapping keyed by kind, options keyed on `value` rather than `entity_type`, and an
    invented `sexes` list. None of it failed a type check on either side.

    `entity_types` is a mapping so a UI can group the pickers without re-deriving groups.
    """

    catalog_version: str
    settings: list[BilingualOption]
    complexities: list[BilingualOption]
    severities: list[BilingualOption]
    entity_types: dict[str, list[EntityTypeOption]]
    counts: dict[str, int]


class ZifferResponse(BaseModel):
    """One catalog position, with the rules that touch it."""

    model_config = ConfigDict(extra="allow")

    ziffer: str
    official_text: str
    punkte: int
    category: str | None = None
    section: str | None = None
    section_title: str | None = None
    status: str = "active"
    provenance: str = "official"
    rule_coverage: str = "partial"
    text_quality: str = "ok"
    minderung_exempt: bool = False
    factor_band: dict = Field(default_factory=dict)
    factor_cap: dict | None = None
    annotations: list[str] = Field(default_factory=list)
    exclusions_enforced: list[dict] = Field(default_factory=list)
