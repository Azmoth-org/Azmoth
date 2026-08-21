"""What we keep from a PADnext file, and what an audit of one produces.

PADnext is the XML interchange format for German private billing between a practice and its
Verrechnungsstelle (PVS). Its payload carries billing positions that have *already been coded* —
GO number, factor, quantity, amount. So a PADnext file is not an input to the coding pipeline; it
is a claim to be checked against it. That is what `app.padnext.audit` does.

Two deliberate omissions, both load-bearing:

**No patient identity is parsed.** A real `abrechnungsfall` carries name, address and date of
birth. None of it is needed to decide whether a position is chargeable, so none of it is read into
these models. There is no field here that could hold a name, and a test asserts that.

**No pricing is trusted.** The spec is explicit that PADnext performs no valuation ("Eine Bewertung
der Leistung erfolgt nicht") and that `punktzahl` / `punktwert` / `gesamtbetrag` are carried *für
Kontrollzwecke* — for checking. So we recompute from our own catalog and report the difference
rather than believing the file.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Dec, RuleCoverage, Setting

#: PADnext 10.4 Behandlungsart → the setting our § 6a rules understand. Codes 3 and 4 (vor- and
#: nachstationär) are deliberately absent: whether they attract the Minderung is a question the
#: engine must not answer by guessing, so they raise a finding instead of silently picking one.
BEHANDLUNGSART_TO_SETTING: dict[str, Setting] = {
    "0": "ambulant",
    "1": "stationaer",
    "2": "stationaer",
}

BEHANDLUNGSART_LABEL: dict[str, str] = {
    "0": "ambulante Behandlung",
    "1": "stationäre Behandlung",
    "2": "stationäre Mitbehandlung",
    "3": "vorstationäre Behandlung",
    "4": "nachstationäre Behandlung",
    "5": "Konsiliarbehandlung",
}


class PadnextPosition(BaseModel):
    """One `<goziffer>` — a claimed billing line, exactly as the file states it."""

    model_config = ConfigDict(extra="forbid")

    positionsnr: str
    go: str = "GOÄ"
    ziffer: str
    analog_for: str | None = None
    datum: str | None = None
    anzahl: int = 1
    text: str = ""
    faktor: Dec | None = None
    einzelbetrag: Dec | None = None
    begruendung: str | None = None
    minderungssatz: Dec | None = None
    punktzahl: int | None = None
    punktwert: Dec | None = None
    gesamtbetrag: Dec | None = None

    @property
    def is_analog(self) -> bool:
        return self.analog_for is not None

    @property
    def is_goae(self) -> bool:
        """GOZ (dental) and EBM positions are out of scope and must be reported, not ignored."""
        return self.go.upper() in {"GOÄ", "GOAE", "GOAE_1982"}


class PadnextCase(BaseModel):
    """One `<abrechnungsfall>`, stripped of everything that identifies a person."""

    model_config = ConfigDict(extra="forbid")

    behandlungsart: str | None = None
    vertragsart: str | None = None
    minderungssatz: Dec | None = None
    positions: list[PadnextPosition] = Field(default_factory=list)
    #: `<positionen posanzahl="…">` — the spec says it exists for consistency checks, so we run one.
    declared_position_count: int | None = None


class PadnextInvoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: str = ""
    cases: list[PadnextCase] = Field(default_factory=list)


class PadnextDelivery(BaseModel):
    """A parsed delivery: the payload, plus whatever the order file told us about it."""

    model_config = ConfigDict(extra="forbid")

    nachrichtentyp: str = ""
    version: str = ""
    #: `@echtdaten` — false means test data. See `audit.py` for why we refuse the true case.
    echtdaten: bool | None = None
    declared_invoice_count: int | None = None
    invoices: list[PadnextInvoice] = Field(default_factory=list)
    #: Names of the files found inside a `.padx` container, for the audit trail.
    container_members: list[str] = Field(default_factory=list)
    source_name: str = ""

    def positions(self) -> list[PadnextPosition]:
        return [p for inv in self.invoices for case in inv.cases for p in case.positions]


class PadnextFinding(BaseModel):
    """Something the audit noticed. Every non-chargeable position produces at least one."""

    model_config = ConfigDict(extra="forbid")

    type: str
    severity: Literal["info", "warning", "error"] = "warning"
    message: str
    positionsnr: str | None = None
    ziffer: str | None = None
    legal_basis: str = ""
    rule_id: str = ""
    claimed: str | None = None
    recomputed: str | None = None


class PadnextAuditedPosition(BaseModel):
    """A claimed position, with our verdict on it."""

    model_config = ConfigDict(extra="forbid")

    positionsnr: str
    ziffer: str
    go: str
    is_analog: bool = False
    in_catalog: bool = False
    official_text: str = ""
    #: What the *suppression rules* concluded: chargeable = kept, blocked = a rule removed it,
    #: out_of_scope = not GOÄ, unknown_ziffer = not in the catalog.
    verdict: Literal["chargeable", "blocked", "out_of_scope", "unknown_ziffer"] = "chargeable"
    #: Narrower than `verdict == "chargeable"`: also false when anything else about the line is
    #: wrong — an illegal factor, a missing § 12 Abs. 3 reason, an amount that does not recompute.
    #: A line can survive every suppression rule and still not be billable *as claimed*, and it is
    #: this flag, not the verdict, that `defensible_total_eur` is built from.
    accepted_as_claimed: bool = False
    reason: str = ""
    blocked_by: str | None = None
    proof: list[str] = Field(default_factory=list)

    claimed_faktor: Dec | None = None
    claimed_amount_eur: Dec | None = None
    recomputed_amount_eur: Dec | None = None
    amount_delta_eur: Dec | None = None

    punkte: int | None = None
    factor_within_band: bool | None = None
    justification_required: bool = False
    justification_present: bool = False
    legal_basis: str = ""


class PadnextAuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str = ""
    nachrichtentyp: str = ""
    echtdaten: bool | None = None
    setting: Setting = "ambulant"
    setting_source: str = ""

    positions: list[PadnextAuditedPosition] = Field(default_factory=list)
    findings: list[PadnextFinding] = Field(default_factory=list)

    #: What the file itself charges, across every position including ones we cannot price.
    claimed_total_eur: Dec = Decimal("0.00")
    #: Our recomputation, over the positions we could price at all.
    recomputed_total_eur: Dec = Decimal("0.00")
    #: The file's claim restricted to those same positions — the only fair comparison basis.
    comparable_claimed_eur: Dec = Decimal("0.00")
    #: Pure arithmetic error: comparable_claimed − recomputed. Ignores whether a line is allowed.
    arithmetic_delta_eur: Dec = Decimal("0.00")
    #: Recomputed, counting only positions the rules confirmed. What this invoice can defend.
    defensible_total_eur: Dec = Decimal("0.00")
    #: claimed_total − defensible_total. What a Rechnungsprüfer could challenge.
    at_risk_eur: Dec = Decimal("0.00")
    #: Claimed euros on positions we could not price at all (unknown Ziffer, other fee schedule).
    unpriceable_claimed_eur: Dec = Decimal("0.00")

    catalog_version: str = ""
    catalog_sha256: str = ""
    rules_version: str = ""
    logic_version: str = ""

    #: Rule-coverage transparency. An audit that suppressed an unverified rule must say so, or a
    #: reader would take "no finding" for "the rules confirmed it".
    enforced_rule_count: int = 0
    advisory_rule_count: int = 0
    suppressed_unverified_rule_count: int = 0
    rule_coverage_detail: RuleCoverage | None = None

    #: SHA-256 over catalog identity + rule identity + the claimed positions + our verdicts, so a
    #: report can be tied to the exact data and policy that produced it.
    receipt_hash: str = ""

    @property
    def has_errors(self) -> bool:
        return any(f.severity == "error" for f in self.findings)

    def summary(self) -> dict[str, int]:
        counts = {"chargeable": 0, "blocked": 0, "out_of_scope": 0, "unknown_ziffer": 0}
        for position in self.positions:
            counts[position.verdict] += 1
        return counts
