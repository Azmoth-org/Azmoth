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

And one deliberate addition:

**No euro is called "at risk" without a verified reason.** `PadnextAuditReport` splits the claimed
total three ways — `confirmed_fine_eur`, `confirmed_wrong_eur`, `unconfirmed_eur` — because the
engine enforces a subset of the GOÄ and must not present the boundary of its own rule coverage as a
defect in someone's invoice. "We have no verified rule for this Ziffer" and "this position violates
a rule we verified" are different statements about different money, and only the second one is a
refund. See the comment above those fields for what conflating them cost.
"""

from __future__ import annotations

from decimal import Decimal
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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

#: Which of the three honest financial buckets a claimed position falls into.
#:
#: The distinction that matters is *epistemic*, not clinical: it is about what this engine can
#: actually demonstrate, not about how likely a position is to be wrong.
#:
#:   confirmed_wrong  a verified rule, the versioned catalog, or the fee schedule's own arithmetic
#:                    shows the position is not chargeable as claimed. Defensible in a dispute.
#:   confirmed_fine   every check that bears on the position passed, and at least one *verified*
#:                    rule actually bore on it. Safe to bill.
#:   unconfirmed      we cannot say either way — no verified rule maps to this Ziffer, or the only
#:                    rules that do are advisory (`verified=false`) and therefore not enforced.
#:                    NOT a claim that the position is wrong.
PositionBucket = Literal["confirmed_fine", "confirmed_wrong", "unconfirmed"]


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

    #: Which financial bucket this position's claimed euros were counted into. Distinct from
    #: `verdict` and from `accepted_as_claimed`, and the distinction is the point: `verdict` says
    #: what the *enforced* rules concluded, while this says how much weight that conclusion can
    #: bear. A position the rules did not confirm is `blocked` in the verdict but only
    #: `unconfirmed` here, because "no verified rule kept it" is not evidence that it is wrong.
    bucket: PositionBucket = "unconfirmed"
    #: Why this position landed in that bucket, in the language a Rechnungsprüfer would use.
    bucket_reason: str = ""
    #: Rule ids of *verified* rules that actually bore on this position — that is, rules a human
    #: has confirmed AND whose every Ziffer appears on this invoice. A position cannot be
    #: `confirmed_fine` with this list empty: nothing checked it.
    verified_rule_ids: list[str] = Field(default_factory=list)
    #: Rule ids of unverified (`verified=false`) rules that bear on this invoice and could have
    #: suppressed this position had the policy enforced them. A non-empty list is exactly why a
    #: position that passed every enforced check still cannot be called safe.
    advisory_rule_ids: list[str] = Field(default_factory=list)


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
    #: Claimed euros on positions we could not price at all (unknown Ziffer, other fee schedule).
    unpriceable_claimed_eur: Dec = Decimal("0.00")

    # -- the three honest buckets ----------------------------------------------------------
    #
    # `at_risk_eur` used to live here, defined as `claimed_total − defensible_total`. It was
    # removed rather than kept as an alias, and the reason is the whole point of these fields.
    #
    # That subtraction silently merged two things a practice must be able to tell apart: euros we
    # can *prove* are not chargeable, and euros we simply have no verified rule to judge. Because
    # 837 of the 869 exclusion rules are machine-extracted and unverified — and therefore not
    # enforced under the default policy — the second group is the large one. A clinic uploading a
    # year of invoices would have been told that most of its revenue was "at risk", when almost
    # all of that figure was the engine's own incomplete rule coverage. That is not a conservative
    # estimate; it is a false statement about the invoice, and it is the kind of number that
    # destroys trust in an audit the first time a payer disputes it.
    #
    # So the money is split three ways instead, and the split is by what we can demonstrate:
    #
    #     confirmed_fine + confirmed_wrong + unconfirmed == claimed_total
    #
    # Each position contributes its *claimed* euros to exactly one bucket, which is what makes the
    # identity hold exactly (see `_check_buckets_reconcile`). Recomputed euros are reported
    # separately by `recomputed_total_eur` and `defensible_total_eur`.

    #: Claimed euros on positions where every check that bears on them passed AND at least one
    #: verified rule actually bore on them. Safe to bill. Green.
    confirmed_fine_eur: Dec = Decimal("0.00")
    #: Claimed euros on positions shown to be wrong on a *verified* basis — a verified exclusion or
    #: Zielleistung rule, a factor above the § 5 Höchstsatz, a missing § 12 Abs. 3 justification, or
    #: an amount that does not recompute from the versioned catalog. This is the refund exposure,
    #: and the only figure here that may be presented as one. Red.
    #:
    #: One caveat worth stating rather than burying, because it is the one way this figure can read
    #: high. A mutually exclusive pair — the bundled example charges both GOÄ 5 and GOÄ 7, which
    #: cancel — puts *both* lines here, because each is genuinely not chargeable *as claimed* and
    #: the engine deliberately refuses to guess which one the practice meant to keep. The invoice
    #: must be revised either way, but the cash a payer would actually claw back is the pair minus
    #: whichever line is kept. So treat this as "euros that cannot be billed as submitted", which is
    #: what it measures, and not as a settled refund amount.
    confirmed_wrong_eur: Dec = Decimal("0.00")
    #: Claimed euros we cannot judge either way: no verified rule maps to the Ziffer, the only rules
    #: that do are advisory, or the position is outside this engine's scope. These positions are
    #: **not** findings against the practice — they are gaps in our rule coverage, and they need
    #: human review or rule verification. Yellow/grey.
    unconfirmed_eur: Dec = Decimal("0.00")
    #: Share of `claimed_total_eur` this audit could actually reach a verdict on:
    #: `(confirmed_fine + confirmed_wrong) / claimed_total`, in `[0.0, 1.0]`. The honest headline
    #: number — it says how much of the invoice was audited, not how much of it is wrong. A float
    #: because it is a display ratio, never money and never an input to an arithmetic check.
    coverage_ratio: float = 0.0

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

    #: Tolerance for the bucket identity below. The three buckets are built by adding the same
    #: `Decimal` `gesamtbetrag` values the claimed total is built from, so they agree exactly and
    #: this is slack, not a working allowance — a cent of drift means a position was double-counted
    #: or dropped, which is a bug, not a rounding artefact.
    BUCKET_TOLERANCE_EUR: ClassVar[Decimal] = Decimal("0.01")

    @model_validator(mode="after")
    def _check_buckets_reconcile(self) -> PadnextAuditReport:
        """Refuse to exist as a report whose buckets do not add up to what was claimed.

        A report is a financial statement about someone's invoice. If the three buckets do not sum
        to the claimed total, then some position's euros were counted twice or not at all, and
        every number downstream — the coverage ratio, the refund exposure a practice acts on — is
        wrong in a way no reader could detect. Failing loudly here is the cheapest place to catch
        it: by construction the sum is exact, so this can only fire on a genuine bug.
        """
        bucketed = self.confirmed_fine_eur + self.confirmed_wrong_eur + self.unconfirmed_eur
        drift = abs(bucketed - self.claimed_total_eur)
        if drift > self.BUCKET_TOLERANCE_EUR:
            raise ValueError(
                f"PADnext audit buckets do not reconcile: confirmed_fine "
                f"{self.confirmed_fine_eur} + confirmed_wrong {self.confirmed_wrong_eur} + "
                f"unconfirmed {self.unconfirmed_eur} = {bucketed}, but claimed_total is "
                f"{self.claimed_total_eur} (off by {drift}). Every claimed position must land in "
                "exactly one bucket."
            )
        return self

    @property
    def has_errors(self) -> bool:
        return any(f.severity == "error" for f in self.findings)

    def summary(self) -> dict[str, int]:
        counts = {"chargeable": 0, "blocked": 0, "out_of_scope": 0, "unknown_ziffer": 0}
        for position in self.positions:
            counts[position.verdict] += 1
        return counts

    def bucket_summary(self) -> dict[str, int]:
        """How many positions landed in each bucket, alongside `summary()`'s verdict counts."""
        counts: dict[str, int] = {"confirmed_fine": 0, "confirmed_wrong": 0, "unconfirmed": 0}
        for position in self.positions:
            counts[position.bucket] += 1
        return counts
