"""Rule-coverage transparency.

The engine enforces a *subset* of the GOÄ. 837 of the exclusion rules were extracted from the fee
schedule's prose automatically and are unverified; under the default `UNVERIFIED_RULE_POLICY=warn`
they suppress nothing and only warn. A response that did not say so would let a reader take
"no finding" for "the rules confirmed it".

So every solve and every audit carries the three counts and, when the advisory set is non-empty, a
warning saying that unverified rules are NOT enforced.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.rules.rule_store import RuleStore
from app.schemas.common import RuleCoverage, Warning_


def build(rules: RuleStore, *, rule_coverage: str = "partial", rules_version: str = "") -> RuleCoverage:
    summary = rules.summary()
    return RuleCoverage(
        policy_for_unverified_rules=summary["policy_for_unverified_rules"],
        enforced_rule_count=(
            summary["exclusions_enforced"]
            + summary["zielleistung_enforced"]
            + summary["specificity_enforced"]
            + summary["factor_caps_enforced"]
        ),
        #: Analog candidates are offers, not constraints — they are always loaded and can never
        #: suppress anything, so they are advisory by construction, alongside every unverified
        #: rule the policy kept out of the enforcement path.
        advisory_rule_count=summary["analog_candidates"] + summary["unverified_rules_not_enforced"],
        suppressed_unverified_rule_count=summary["unverified_rules_not_enforced"],
        rule_coverage=rule_coverage,
        rules_version=rules_version,
        verified_share=summary["verified_share"],
    )


def warnings_for(coverage: RuleCoverage) -> list[Warning_]:
    """The warning the brief requires whenever advisory rules exist."""
    out: list[Warning_] = []
    if coverage.advisory_rule_count:
        out.append(
            Warning_(
                type="advisory_rules_present",
                severity="warning",
                message=(
                    f"{coverage.enforced_rule_count} Regeln werden durchgesetzt; "
                    f"{coverage.advisory_rule_count} Regeln sind nur beratend "
                    f"({coverage.suppressed_unverified_rule_count} davon nicht verifiziert und "
                    f"unter Policy '{coverage.policy_for_unverified_rules}' NICHT blockierend). "
                    "Nicht verifizierte Regeln unterdrücken keine Position – das Ergebnis darf "
                    "nicht als vollständige Regelprüfung gelesen werden."
                ),
            )
        )
    return out


def rules_hash(directory: Path) -> str:
    """SHA-256 over the rule tables themselves.

    A `rules_version` string is maintained by a human and can lag an edit; this cannot. Editing one
    cell of one CSV changes the cache key and the receipt.
    """
    digest = hashlib.sha256()
    if directory.is_dir():
        for path in sorted(directory.glob("*.csv")):
            digest.update(path.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()
