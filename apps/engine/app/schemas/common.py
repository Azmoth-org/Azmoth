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
    enforced_rule_count: int = 0
    advisory_rule_count: int = 0
    suppressed_unverified_rule_count: int = 0
    rule_coverage: str = "partial"
    rules_version: str = ""
    verified_share: str = "0/0"

    @property
    def has_advisory_rules(self) -> bool:
        return self.advisory_rule_count > 0
