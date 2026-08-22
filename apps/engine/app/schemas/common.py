"""Shared primitives every other schema module builds on.

Every factor, similarity and monetary value is a ``Decimal`` and serialises as a JSON *string*.
Floats never touch money or Steigerungsfaktoren.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, PlainSerializer

#: Decimal that serialises as a string, so no precision is lost crossing JSON.
Dec = Annotated[Decimal, PlainSerializer(str, return_type=str, when_used="json")]

Sex = Literal["m", "w", "d"]
Setting = Literal["ambulant", "stationaer", "belegarzt"]
Complexity = Literal["einfach", "mittel", "komplex"]
Severity = Literal["leicht", "mittel", "schwer"]

Severity_ = Literal["info", "warning", "error"]

#: Why a charged position carries the Steigerungsfaktor it does. Closed, and shared by
#: `FactorDecision.basis` and `InvoiceLine.factor_basis` so the two can never drift: they are the
#: same decision, reported once by the solver and once on the invoice line.
#:
#:   einfachsatz          1.0 — the § 5 Abs. 1 base rate
#:   schwellenwert        the threshold factor, lawful without a written justification (§ 5 Abs. 2)
#:   ueber_schwellenwert  above the threshold; requires a written reason (§ 12 Abs. 3)
#:   hoechstsatz          at the ceiling of the § 5 band
#:   capped               a Leistungslegende cap overrode the band
FactorBasis = Literal[
    "einfachsatz",
    "schwellenwert",
    "ueber_schwellenwert",
    "hoechstsatz",
    "capped",
]


class Warning_(BaseModel):
    """A non-fatal finding. Named with a trailing underscore to avoid the builtin."""

    type: str
    message: str
    ziffer: str | None = None
    severity: Severity_ = "warning"
    legal_basis: str = ""
    rule_id: str = ""


class ValidationViolation(BaseModel):
    code: str
    message: str
    ziffer: str | None = None
    legal_basis: str = ""


class RuleCoverage(BaseModel):
    """How much of the rule set is actually being enforced, on every response that has one.

    The API must never imply that unverified rules are enforced. ``enforced_rule_count`` is what
    can suppress a position; ``advisory_rule_count`` is what only warns. Under the default
    ``UNVERIFIED_RULE_POLICY=warn`` the advisory set is the automatically extracted majority, and
    a response carrying a non-zero advisory count also carries a warning saying so.
    """

    policy_for_unverified_rules: str

    #: Rules that CAN suppress a position. This is the only number that describes enforcement.
    enforced_rule_count: int = 0

    #: The sum of the two components below, kept so a caller can show one "advisory" figure
    #: without adding numbers itself. It is NOT a count of rules that blocked anything.
    advisory_rule_count: int = 0

    #: Constraint rules (exclusion, Zielleistung, specificity, factor cap) that no human has
    #: verified. Policy-independent: under `block` these are enforced, under `warn`/`ignore` they
    #: are not. Compare with `suppressed_unverified_rule_count`.
    unverified_rule_count: int = 0

    #: Analogansatz candidates (§ 6 Abs. 2 GOÄ). Offers, never constraints — one of these can
    #: never suppress a position, verified or not, under any policy.
    analog_candidate_count: int = 0

    #: The subset of `unverified_rule_count` that the current policy is holding out of the
    #: enforcement path. Equal to `unverified_rule_count` under `warn`/`ignore`, zero under `block`.
    suppressed_unverified_rule_count: int = 0

    rule_coverage: str = "partial"
    rules_version: str = ""
    verified_share: str = "0/0"

    @property
    def has_advisory_rules(self) -> bool:
        return self.advisory_rule_count > 0
