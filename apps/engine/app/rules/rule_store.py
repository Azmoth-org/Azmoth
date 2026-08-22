"""Rule loading with provenance and an explicit policy for unverified rules.

Every rule carries where it came from, which sentence of the GOÄ supports it, and whether a
human has confirmed it. That last flag is not decoration: the bulk of the exclusion rules were
extracted from the fee schedule's prose automatically, and a machine-read rule must not be
allowed to suppress a chargeable service until someone has checked it.

``UNVERIFIED_RULE_POLICY`` decides what unverified rules do:

    warn    (default)  the rule does not suppress anything; the response carries a warning
    block              the rule is enforced exactly like a verified one
    ignore             the rule is dropped entirely and counted

**Reviews are a second source of the verified flag, and this module stays ignorant of where they
come from.** A billing expert working the review queue can promote a machine-extracted rule to
verified, or reject it outright, and those decisions live in Postgres — the CSVs are versioned
source data and are never written by the API. The merge happens here, in `with_reviews`, which takes
a plain mapping of `rule_id -> RuleReviewStatus` and returns a **new** store with the policy re-run
over it. No database, no `await`, nothing that would stop `import app.rules` working on a machine
with no Postgres; `app.services.rule_reviews` is the layer that reads the table and calls this.

Two things that merge decides, and they are not symmetrical:

* `VERIFIED` sets `verified` to true, so every existing reader — the admission policy below, the
  bucket classifier in `app.padnext.audit`, the coverage counts — sees a verified rule without
  knowing a review happened. That is the whole point: verifying a rule must shrink the
  `unconfirmed` bucket by exactly the mechanism a manually curated rule already does.
* `REJECTED` is stronger than "not verified". It means a human read the machine-extracted rule and
  said it is wrong, so it is never enforced — **including under `policy=block`**, which enforces
  merely-unverified rules. A rule nobody has checked and a rule somebody has refused are different
  things, and only the first is a gap in coverage.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import StrEnum
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



class RuleReviewStatus(StrEnum):
    """What a human decided about one rule.

    `PENDING` exists so a reviewer can park a rule they have looked at and cannot decide — it reads
    exactly like no review at all to the merge below, which is deliberate: an undecided rule is
    still an unchecked rule, and pretending otherwise would shrink the honest `unconfirmed` bucket
    without anyone having confirmed anything.
    """

    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


#: Review statuses that mean "a human has taken a position". `PENDING` is deliberately absent.
_DECIDED_STATUSES = frozenset({str(RuleReviewStatus.VERIFIED), str(RuleReviewStatus.REJECTED)})


@dataclass(frozen=True)
class Rule:
    rule_id: str
    legal_basis: str = ""
    quote: str = ""
    #: The **effective** flag: true when the CSV says so, or when a review verified it. Everything
    #: downstream reads this and needs to know nothing about reviews — see the module docstring.
    verified: bool = False
    verified_at: str = ""
    source: str = ""

    #: What the CSV itself claimed, before any review. Kept because `verified` is now effective and
    #: a reader has to be able to tell a rule a human curated by hand from one a human promoted out
    #: of the machine-extracted pile — they are equally enforced and not equally old.
    csv_verified: bool = False
    #: "" when no review row exists. Otherwise one of `RuleReviewStatus`.
    review_status: str = ""
    #: Who decided. Recorded, never authenticated — this service has no login.
    reviewed_by: str = ""

    @property
    def rejected(self) -> bool:
        """A human read this rule and refused it. Stronger than "not verified"; never enforced."""
        return self.review_status == str(RuleReviewStatus.REJECTED)

    @property
    def provenance(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "legal_basis": self.legal_basis,
            "quote": self.quote,
            "verified": self.verified,
            "verified_at": self.verified_at,
            "source": self.source,
            "csv_verified": self.csv_verified,
            "review_status": self.review_status,
            "reviewed_by": self.reviewed_by,
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


def _reviewed(rule: Rule, reviews: Mapping[str, RuleReviewStatus | str]) -> Rule:
    """Apply one review decision to one rule, or return it untouched.

    `VERIFIED` sets the effective flag and stamps `verified_at` with the review marker rather than
    the CSV's date, because the CSV never claimed a date for a rule it did not verify — leaving it
    empty would make a reviewed rule look unverified to anything that reads that field.

    `REJECTED` clears the effective flag even if the CSV said true. That case should not arise from
    the review queue, which only offers CSV-unverified rules, but the endpoint takes any rule id and
    the semantics have to be decided somewhere: a human's explicit refusal outranks a CSV cell.

    `PENDING` and an absent review are the same thing on purpose. See `RuleReviewStatus`.
    """
    status = reviews.get(rule.rule_id)
    if status is None:
        return rule

    status = str(status)
    if status == str(RuleReviewStatus.VERIFIED):
        return replace(rule, verified=True, review_status=status, verified_at="by_review")
    if status == str(RuleReviewStatus.REJECTED):
        return replace(rule, verified=False, review_status=status)
    return rule


@dataclass(frozen=True)
class SourceRules:
    """Every rule exactly as the CSVs state it — before policy, before reviews.

    Kept alongside the enforcement lists because the policy has to be *re-runnable*. Promoting a
    rule out of `suppressed` when a reviewer verifies it means deciding admission again for the
    whole set, and reconstructing "the whole set" by concatenating the enforcement lists with
    `suppressed` and sorting the result back into categories by `isinstance` would be a guess that
    happens to work today. This is the same information, stated once, immutably.
    """

    exclusions: tuple[ExclusionRule, ...] = ()
    zielleistung: tuple[ZielleistungRule, ...] = ()
    specificity: tuple[SpecificityRule, ...] = ()
    analog_candidates: tuple[AnalogCandidateRule, ...] = ()
    factor_caps: tuple[FactorCapRule, ...] = ()
    files_loaded: tuple[str, ...] = ()

    def constraint_rules(self) -> tuple[Rule, ...]:
        """Every rule that *could* suppress a position, in a stable order.

        Analog candidates are absent, and that is the same distinction the coverage counts make:
        a candidate is an offer under § 6 Abs. 2 GOÄ and can never remove a position from an
        invoice, so it is not something a reviewer needs to verify before it is safe.
        """
        return (
            *self.exclusions,
            *self.zielleistung,
            *self.specificity,
            *self.factor_caps,
        )


@dataclass
class RuleStore:
    policy: UnverifiedRulePolicy = UnverifiedRulePolicy.WARN
    exclusions: list[ExclusionRule] = field(default_factory=list)
    zielleistung: list[ZielleistungRule] = field(default_factory=list)
    specificity: list[SpecificityRule] = field(default_factory=list)
    analog_candidates: list[AnalogCandidateRule] = field(default_factory=list)
    factor_caps: list[FactorCapRule] = field(default_factory=list)
    #: Rules loaded but not enforced — unverified under the policy, or rejected by a reviewer.
    suppressed: list[Rule] = field(default_factory=list)
    files_loaded: list[str] = field(default_factory=list)
    #: What the CSVs said, so `with_reviews` can decide admission again from scratch.
    source: SourceRules = field(default_factory=SourceRules)

    # -- policy ----------------------------------------------------------------------------

    def _admit(self, rule: Rule) -> bool:
        """Decide whether a rule may actually constrain an invoice.

        Order matters. Rejection is checked first because it outranks everything, including
        `policy=block`: `block` exists to enforce rules nobody has *looked at*, and a rule somebody
        has looked at and refused is the opposite of that.
        """
        if rule.rejected:
            self.suppressed.append(rule)
            return False
        if rule.verified:
            return True
        if self.policy is UnverifiedRulePolicy.BLOCK:
            return True
        # warn and ignore both keep the rule out of the enforcement path; the difference is
        # whether the caller is told about it.
        self.suppressed.append(rule)
        return False

    # -- reviews ---------------------------------------------------------------------------

    def with_reviews(self, reviews: Mapping[str, RuleReviewStatus | str]) -> RuleStore:
        """A new store with the review decisions merged in and the policy re-run over the result.

        Pure and synchronous. It takes a mapping, not a database, so the rules layer never learns
        that Postgres exists and `import app.rules` keeps working without one —
        `app.services.rule_reviews` is what reads the table and calls this.

        Returns a new store rather than mutating: the pipeline holds one for the process lifetime
        and hands it to Soufflé, Clingo and the validator at construction, so a store that changed
        under them mid-solve would make the three disagree about what the rules are.
        """
        merged = SourceRules(
            exclusions=tuple(_reviewed(r, reviews) for r in self.source.exclusions),
            zielleistung=tuple(_reviewed(r, reviews) for r in self.source.zielleistung),
            specificity=tuple(_reviewed(r, reviews) for r in self.source.specificity),
            # Reviewed too, so the flag is honest, but never admitted or suppressed by policy.
            analog_candidates=tuple(_reviewed(r, reviews) for r in self.source.analog_candidates),
            factor_caps=tuple(_reviewed(r, reviews) for r in self.source.factor_caps),
            files_loaded=self.source.files_loaded,
        )
        return RuleStore._from_source(merged, self.policy)

    @classmethod
    def _from_source(cls, source: SourceRules, policy: UnverifiedRulePolicy) -> RuleStore:
        """Run the admission policy over a parsed rule set. The one place `_admit` is called."""
        store = cls(policy=policy, source=source, files_loaded=list(source.files_loaded))
        store.exclusions = [r for r in source.exclusions if store._admit(r)]
        store.zielleistung = [r for r in source.zielleistung if store._admit(r)]
        store.specificity = [r for r in source.specificity if store._admit(r)]
        store.factor_caps = [r for r in source.factor_caps if store._admit(r)]
        # Analog candidates are *offers*, not constraints: an unverified candidate cannot wrongly
        # suppress anything, and every analog line carries a human-review warning regardless. So
        # they bypass `_admit` entirely and are always loaded.
        store.analog_candidates = list(source.analog_candidates)
        return store

    # -- loading ---------------------------------------------------------------------------

    @classmethod
    def load(
        cls,
        directory: Path = RULES_DATA_DIR,
        policy: UnverifiedRulePolicy | None = None,
    ) -> RuleStore:
        """Parse the CSVs and run the admission policy. No reviews — see `with_reviews`."""
        return cls._from_source(
            cls._parse(directory), policy or get_settings().unverified_rule_policy
        )

    @classmethod
    def _parse(cls, directory: Path) -> SourceRules:
        """CSV → `SourceRules`. Parsing only: no policy decision is taken here."""
        loader = cls()
        exclusions, zielleistung, specificity, analog, factor_caps = [], [], [], [], []

        for name in EXCLUSIONS_FILES:
            for row in loader._rows(directory / name):
                exclusions.append(
                    ExclusionRule(
                        **loader._base(row),
                        from_ziffer=row["from_ziffer"].strip(),
                        to_ziffer=row["to_ziffer"].strip(),
                        direction=(row.get("direction") or "one_way").strip() or "one_way",
                    )
                )

        for name in ZIELLEISTUNG_FILES:
            for row in loader._rows(directory / name):
                zielleistung.append(
                    ZielleistungRule(
                        **loader._base(row),
                        parent_ziffer=row["parent_ziffer"].strip(),
                        child_ziffer=row["child_ziffer"].strip(),
                    )
                )

        for name in SPECIFICITY_FILES:
            for row in loader._rows(directory / name):
                specificity.append(
                    SpecificityRule(
                        **loader._base(row),
                        specific_ziffer=row["specific_ziffer"].strip(),
                        general_ziffer=row["general_ziffer"].strip(),
                    )
                )

        for name in ANALOG_FILES:
            for row in loader._rows(directory / name):
                analog.append(
                    AnalogCandidateRule(
                        **loader._base(row),
                        source_entity_type=row["source_entity_type"].strip(),
                        target_ziffer=row["target_ziffer"].strip(),
                        similarity=Decimal(str(row.get("similarity") or "0")),
                    )
                )

        for name in FACTOR_CAP_FILES:
            for row in loader._rows(directory / name):
                factor_caps.append(
                    FactorCapRule(
                        **loader._base(row),
                        ziffer=row["ziffer"].strip(),
                        max_factor=Decimal(str(row.get("max_factor") or "1.0")),
                    )
                )

        return SourceRules(
            exclusions=tuple(exclusions),
            zielleistung=tuple(zielleistung),
            specificity=tuple(specificity),
            analog_candidates=tuple(analog),
            factor_caps=tuple(factor_caps),
            files_loaded=tuple(loader.files_loaded),
        )

    def _rows(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        with open(path, encoding="utf-8", newline="") as fh:
            rows = [row for row in csv.DictReader(fh) if any((v or "").strip() for v in row.values())]
        self.files_loaded.append(path.name)
        return rows

    @staticmethod
    def _base(row: dict) -> dict:
        csv_verified = _truthy(row.get("verified"))
        return {
            "rule_id": (row.get("rule_id") or "").strip(),
            "legal_basis": (row.get("legal_basis") or "").strip(),
            "quote": (row.get("quote") or "").strip(),
            # Equal at parse time; `with_reviews` is the only thing that makes them differ.
            "verified": csv_verified,
            "csv_verified": csv_verified,
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
        """Any loaded rule by id, enforced or not.

        `suppressed` is searched last and was not searched at all before the review workflow. The
        addition cannot change what the solvers see: they call this to name a rule that *fired*,
        and a suppressed rule is absent from the Datalog facts, so it can never appear in solver
        output. What it does fix is the review path, which has to be able to look up precisely the
        rules that are not enforced — those are the ones a reviewer is there to decide about.
        """
        for group in (
            self.exclusions,
            self.zielleistung,
            self.specificity,
            self.analog_candidates,
            self.factor_caps,
            self.suppressed,
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
            # Carried unfiltered: a restricted view is a grounding optimisation for one case, not a
            # different rule set, and `with_reviews` on one would otherwise silently widen it back.
            source=self.source,
        )

    def unverified_constraint_rule_count(self) -> int:
        """Rules that *could* constrain an invoice and that nobody has decided about.

        Independent of policy on purpose. Under `warn` and `ignore` these sit in `suppressed`;
        under `block` they sit in the enforcement lists. The count is the same either way — what
        the policy changes is whether they may suppress a position, which is what
        `unverified_rules_not_enforced` reports.

        **Rejected rules are excluded.** They are not enforced, but they are not a gap either: a
        human read them and said no. Counting a refusal as "unverified" would mean the review
        queue could never empty — a reviewer working through 859 rules and rejecting half of them
        would watch the number they are trying to reduce stay where it was.

        Analog candidates are excluded too: they are offers under § 6 Abs. 2 GOÄ, never
        constraints, and they are counted separately.
        """
        return sum(1 for rule in self.constraint_rules() if not rule.verified and not rule.rejected)

    def constraint_rules(self) -> list[Rule]:
        """Every loaded rule that could suppress a position — enforced or not.

        Built from the lists rather than from `source`, so it is correct for a store assembled by
        hand or narrowed by `restrict_to` as well as one that came out of `load`. Analog candidates
        are absent for the same reason they are everywhere else here: an offer under § 6 Abs. 2 GOÄ
        can never remove a position, so it is not something a reviewer has to clear.
        """
        return [
            *self.exclusions,
            *self.zielleistung,
            *self.specificity,
            *self.factor_caps,
            *self.suppressed,
        ]

    def rejected_rule_count(self) -> int:
        """Constraint rules a reviewer explicitly refused. Never enforced under any policy."""
        return sum(1 for rule in self.suppressed if rule.rejected)

    def review_verified_rule_count(self) -> int:
        """Enforced rules that are verified *because of a review* rather than because of the CSV.

        The number the review dashboard is really about: how much of the queue has been worked
        through and is now actually doing something.
        """
        return sum(
            1
            for group in (self.exclusions, self.zielleistung, self.specificity, self.factor_caps)
            for rule in group
            if rule.verified and not rule.csv_verified
        )

    def constraint_rule_count(self) -> int:
        """The denominator the review dashboard counts towards. 894 in the shipped data."""
        return len(self.constraint_rules())

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
            "unverified_rules_not_enforced": len(self.suppressed) - self.rejected_rule_count(),
            "unverified_constraint_rules": self.unverified_constraint_rule_count(),
            "rejected_rules": self.rejected_rule_count(),
            "review_verified_rules": self.review_verified_rule_count(),
            "total_constraint_rules": self.constraint_rule_count(),
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
