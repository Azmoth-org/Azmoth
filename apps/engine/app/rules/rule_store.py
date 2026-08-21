"""Rule loading with provenance and an explicit policy for unverified rules.

Every rule carries where it came from, which sentence of the GOÄ supports it, and whether a
human has confirmed it. That last flag is not decoration: the bulk of the exclusion rules were
extracted from the fee schedule's prose automatically, and a machine-read rule must not be
allowed to suppress a chargeable service until someone has checked it.

``UNVERIFIED_RULE_POLICY`` decides what unverified rules do:

    warn    (default)  the rule does not suppress anything; the response carries a warning
    block              the rule is enforced exactly like a verified one
    ignore             the rule is dropped entirely and counted
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from app.config import RULES_DATA_DIR, UnverifiedRulePolicy, get_settings

EXCLUSIONS_FILES = ("exclusions.csv", "exclusions.manual.csv")
ZIELLEISTUNG_FILES = ("zielleistung.csv", "zielleistung.manual.csv")
SPECIFICITY_FILES = ("specificity.csv", "specificity.manual.csv")
ANALOG_FILES = ("analog_candidates.csv", "analog_candidates.manual.csv")
FACTOR_CAP_FILES = ("factor_caps.csv", "factor_caps.manual.csv")


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


@dataclass(frozen=True)
class Rule:
    rule_id: str
    legal_basis: str = ""
    quote: str = ""
    verified: bool = False
    verified_at: str = ""
    source: str = ""

    @property
    def provenance(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "legal_basis": self.legal_basis,
            "quote": self.quote,
            "verified": self.verified,
            "verified_at": self.verified_at,
            "source": self.source,
        }


@dataclass(frozen=True)
class ExclusionRule(Rule):
    from_ziffer: str = ""
    to_ziffer: str = ""
    direction: str = "one_way"

    @property
    def is_mutual(self) -> bool:
        return self.direction == "mutual"


@dataclass(frozen=True)
class ZielleistungRule(Rule):
    parent_ziffer: str = ""
    child_ziffer: str = ""


@dataclass(frozen=True)
class SpecificityRule(Rule):
    specific_ziffer: str = ""
    general_ziffer: str = ""


@dataclass(frozen=True)
class AnalogCandidateRule(Rule):
    source_entity_type: str = ""
    target_ziffer: str = ""
    similarity: Decimal = Decimal(0)


@dataclass(frozen=True)
class FactorCapRule(Rule):
    ziffer: str = ""
    max_factor: Decimal = Decimal(1)


@dataclass
class RuleStore:
    policy: UnverifiedRulePolicy = UnverifiedRulePolicy.WARN
    exclusions: list[ExclusionRule] = field(default_factory=list)
    zielleistung: list[ZielleistungRule] = field(default_factory=list)
    specificity: list[SpecificityRule] = field(default_factory=list)
    analog_candidates: list[AnalogCandidateRule] = field(default_factory=list)
    factor_caps: list[FactorCapRule] = field(default_factory=list)
    #: Rules loaded but not enforced because they are unverified and the policy says so.
    suppressed: list[Rule] = field(default_factory=list)
    files_loaded: list[str] = field(default_factory=list)

    # -- policy ----------------------------------------------------------------------------

    def _admit(self, rule: Rule) -> bool:
        """Decide whether a rule may actually constrain an invoice."""
        if rule.verified:
            return True
        if self.policy is UnverifiedRulePolicy.BLOCK:
            return True
        # warn and ignore both keep the rule out of the enforcement path; the difference is
        # whether the caller is told about it.
        self.suppressed.append(rule)
        return False

    # -- loading ---------------------------------------------------------------------------

    @classmethod
    def load(
        cls,
        directory: Path = RULES_DATA_DIR,
        policy: UnverifiedRulePolicy | None = None,
    ) -> RuleStore:
        store = cls(policy=policy or get_settings().unverified_rule_policy)

        for name in EXCLUSIONS_FILES:
            for row in store._rows(directory / name):
                rule = ExclusionRule(
                    **store._base(row),
                    from_ziffer=row["from_ziffer"].strip(),
                    to_ziffer=row["to_ziffer"].strip(),
                    direction=(row.get("direction") or "one_way").strip() or "one_way",
                )
                if store._admit(rule):
                    store.exclusions.append(rule)

        for name in ZIELLEISTUNG_FILES:
            for row in store._rows(directory / name):
                rule = ZielleistungRule(
                    **store._base(row),
                    parent_ziffer=row["parent_ziffer"].strip(),
                    child_ziffer=row["child_ziffer"].strip(),
                )
                if store._admit(rule):
                    store.zielleistung.append(rule)

        for name in SPECIFICITY_FILES:
            for row in store._rows(directory / name):
                rule = SpecificityRule(
                    **store._base(row),
                    specific_ziffer=row["specific_ziffer"].strip(),
                    general_ziffer=row["general_ziffer"].strip(),
                )
                if store._admit(rule):
                    store.specificity.append(rule)

        for name in ANALOG_FILES:
            for row in store._rows(directory / name):
                rule = AnalogCandidateRule(
                    **store._base(row),
                    source_entity_type=row["source_entity_type"].strip(),
                    target_ziffer=row["target_ziffer"].strip(),
                    similarity=Decimal(str(row.get("similarity") or "0")),
                )
                # Analog candidates are *offers*, not constraints: an unverified candidate
                # cannot wrongly suppress anything, and every analog line carries a
                # human-review warning regardless. So they are always loaded.
                store.analog_candidates.append(rule)

        for name in FACTOR_CAP_FILES:
            for row in store._rows(directory / name):
                rule = FactorCapRule(
                    **store._base(row),
                    ziffer=row["ziffer"].strip(),
                    max_factor=Decimal(str(row.get("max_factor") or "1.0")),
                )
                if store._admit(rule):
                    store.factor_caps.append(rule)

        return store

    def _rows(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        with open(path, encoding="utf-8", newline="") as fh:
            rows = [row for row in csv.DictReader(fh) if any((v or "").strip() for v in row.values())]
        self.files_loaded.append(path.name)
        return rows

    @staticmethod
    def _base(row: dict) -> dict:
        return {
            "rule_id": (row.get("rule_id") or "").strip(),
            "legal_basis": (row.get("legal_basis") or "").strip(),
            "quote": (row.get("quote") or "").strip(),
            "verified": _truthy(row.get("verified")),
            "verified_at": (row.get("verified_at") or "").strip(),
            "source": (row.get("source") or "").strip(),
        }

    # -- queries ---------------------------------------------------------------------------

    def exclusion_edges(self) -> list[tuple[str, str]]:
        return [(r.from_ziffer, r.to_ziffer) for r in self.exclusions]

    def mutual_pairs(self) -> set[tuple[str, str]]:
        """Unordered mutual pairs, normalised so each appears once."""
        edges = set(self.exclusion_edges())
        pairs = set()
        for rule in self.exclusions:
            a, b = rule.from_ziffer, rule.to_ziffer
            if rule.is_mutual or (b, a) in edges:
                pairs.add((a, b) if a < b else (b, a))
        return pairs

    def exclusion_rule(self, a: str, b: str) -> ExclusionRule | None:
        for rule in self.exclusions:
            if rule.from_ziffer == a and rule.to_ziffer == b:
                return rule
        return None

    def zielleistung_rule(self, parent: str, child: str) -> ZielleistungRule | None:
        for rule in self.zielleistung:
            if rule.parent_ziffer == parent and rule.child_ziffer == child:
                return rule
        return None

    def specificity_rule(self, specific: str, general: str) -> SpecificityRule | None:
        for rule in self.specificity:
            if rule.specific_ziffer == specific and rule.general_ziffer == general:
                return rule
        return None

    def factor_cap(self, ziffer: str) -> FactorCapRule | None:
        for rule in self.factor_caps:
            if rule.ziffer == ziffer:
                return rule
        return None

    def analog_for(self, entity_type: str) -> list[AnalogCandidateRule]:
        return sorted(
            (r for r in self.analog_candidates if r.source_entity_type == entity_type),
            key=lambda r: (-r.similarity, r.target_ziffer),
        )

    def rule_by_id(self, rule_id: str) -> Rule | None:
        for group in (
            self.exclusions,
            self.zielleistung,
            self.specificity,
            self.analog_candidates,
            self.factor_caps,
        ):
            for rule in group:
                if rule.rule_id == rule_id:
                    return rule
        return None

    def restrict_to(self, ziffern: set[str]) -> RuleStore:
        """A view containing only rules whose every endpoint is in ``ziffern``.

        Used to keep Datalog fact files and ASP grounding proportional to the case rather than
        to the 2000-plus entry catalog.
        """
        return RuleStore(
            policy=self.policy,
            exclusions=[
                r for r in self.exclusions if r.from_ziffer in ziffern and r.to_ziffer in ziffern
            ],
            zielleistung=[
                r
                for r in self.zielleistung
                if r.parent_ziffer in ziffern and r.child_ziffer in ziffern
            ],
            specificity=[
                r
                for r in self.specificity
                if r.specific_ziffer in ziffern and r.general_ziffer in ziffern
            ],
            analog_candidates=list(self.analog_candidates),
            factor_caps=[r for r in self.factor_caps if r.ziffer in ziffern],
            suppressed=list(self.suppressed),
            files_loaded=list(self.files_loaded),
        )

    def summary(self) -> dict:
        return {
            "policy_for_unverified_rules": str(self.policy),
            "files_loaded": sorted(self.files_loaded),
            "exclusions_enforced": len(self.exclusions),
            "exclusions_mutual": len(self.mutual_pairs()),
            "zielleistung_enforced": len(self.zielleistung),
            "specificity_enforced": len(self.specificity),
            "factor_caps_enforced": len(self.factor_caps),
            "analog_candidates": len(self.analog_candidates),
            "unverified_rules_not_enforced": len(self.suppressed),
            "verified_share": (
                f"{sum(1 for r in self.exclusions if r.verified)}/{len(self.exclusions)}"
                if self.exclusions
                else "0/0"
            ),
        }


@lru_cache
def load_rules(
    directory: str | Path = RULES_DATA_DIR, policy: UnverifiedRulePolicy | None = None
) -> RuleStore:
    return RuleStore.load(Path(directory), policy)
