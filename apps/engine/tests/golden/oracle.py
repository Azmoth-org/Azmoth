"""Expected audit results, computed from the source data rather than from the engine.

Every number in a `expected.json` beside this file comes from here, and this module deliberately
imports **nothing from `app`**. It reads:

  * `data/catalogs/goae_current/goae.official.json` — `punkte`, `punktwert_cent`, `factor_bands`,
    `category`, `status`;
  * `data/rules/exclusions.csv`, `factor_caps.csv`, `specificity.csv`, `zielleistung.csv` and
    `zielleistung.manual.csv` — rule ids and legal bases, `verified=true` rows only;

and re-derives the money and the rule citations from the fee schedule's own arithmetic:

    Betrag = ROUND_HALF_UP(punkte × faktor × punktwert_cent / 100, cent)      § 5 Abs. 1 GOÄ

That independence is the whole point. An expectation produced by running the engine and writing
down what came out cannot fail when the engine is wrong; it can only fail when the engine changes.
So the verdict, bucket and finding rules below are a short transcription of what
`docs/api/PARTNER_API.md` and `app/schemas/padnext.py` *promise*, written against the data — not a
copy of `app/padnext/audit.py`. Where the engine disagrees with this module, the disagreement is a
finding to be investigated, and `docs/api/E2E_GOLDEN.md` records the ones that have been.

`Decimal` everywhere. There is no float in this file except `coverage_ratio`, which the contract
itself defines as a display ratio and never as money.

Run `python apps/engine/tests/golden/oracle.py --write` to regenerate every `expected.json`.
"""

from __future__ import annotations

import argparse
import csv
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

def _find_repo_root() -> Path:
    """The nearest ancestor holding both `logic/` and `data/`.

    Checkout:  …/TARGET_MONOREPO/apps/engine/tests/golden/oracle.py → …/TARGET_MONOREPO (4 parents up)
    Container: /srv/tests/golden/oracle.py                          → /srv (2 parents up)

    The Dockerfile (`apps/engine/Dockerfile`) copies `apps/engine/tests` to `/srv/tests` directly,
    so this file sits at a different depth inside the image than in a checkout. A fixed
    `parents[4]` assumed the checkout depth unconditionally and raised `IndexError` under `docker
    run … azmoth-engine:ci`. Walking up mirrors `app.config._find_repo_root`, which this module
    does not import — see the module docstring on why oracle.py imports nothing from `app`.
    """
    here = Path(__file__).resolve()
    for candidate in (here.parent, *here.parents):
        if (candidate / "logic").is_dir() and (candidate / "data").is_dir():
            return candidate
    raise RuntimeError(f"no ancestor of {here} holds both logic/ and data/")


#: `apps/engine/tests/golden/oracle.py` → the monorepo root (or `/srv` inside the CI image).
REPO_ROOT = _find_repo_root()
GOLDEN_DIR = Path(__file__).resolve().parent
CATALOG_PATH = REPO_ROOT / "data" / "catalogs" / "goae_current" / "goae.official.json"
#: The importer's residue file, read for one thing only: the rows it marked `typ:
#: prozent_zuschlag`. Those Ziffern — 441 and 5298 — are absent from the catalog because § 5 GOÄ
#: states them as a percentage of another Ziffer's einfacher Gebührensatz and gives them no
#: Punktzahl, so "not in the catalog" and "not modelled" are different claims about them and the
#: contract makes the second one. Read from `data/` like everything else here; the engine's own
#: reader is `app.catalog.Catalog._read_percentage_surcharges`, which this module may not import.
UNPARSED_ROWS_PATH = CATALOG_PATH.parent / "unparsed_rows.json"
RULES_DIR = REPO_ROOT / "data" / "rules"

PAD_NS = "{http://padinfo.de/ns/pad}"

#: The case directories, in the order `docs/api/E2E_GOLDEN.md` and the e2e script walk them.
CASES = (
    "case_a_known_answer",
    "case_b_verified_exclusion",
    "case_c_verified_factor_cap",
    "case_d_arithmetic_mismatch",
    "case_e_echtdaten_gate",
)

#: A regression fixture, not one of the five golden cases: the delivery that caught the
#: `positionsnr` collision bug (see `app/padnext/audit.py::audit_delivery`'s `errors_per_row` /
#: `verified_defects_per_row`). Same delivery as case C, except that both lines are numbered
#: `positionsnr="1"` in their own `<abrechnungsfall>` — which PADnext permits, since the number is
#: unique per case and not per delivery. `expected.json` here is what the contract requires, and
#: `tests/test_golden_cases.py::test_findings_are_attributed_per_delivery_and_not_per_positionsnr`
#: asserts the engine now gets it right, with no `xfail`.
BUG_CASES = ("bug_positionsnr_collision",)

#: Cases added after the five, each pinning one T2 defect from the pilot-readiness audit. Derived
#: through `expected_report` like the five — unlike case F and case G, whose expectations are
#: hand-computed because the oracle's generic walker cannot express a per-case fact base (see the
#: comment above their tests in `tests/test_golden_cases.py`). These two need nothing it cannot
#: express: case H turns on how the *duplicate* check is scoped, which this module now states
#: itself, and case I on a catalog fact read straight out of `data/`.
#:
#:   case_h_cross_invoice_duplicates  three patients, each billed GOÄ 1 once → zero duplicate
#:                                    warnings. The flat `delivery.positions()` walk produced two.
#:   case_i_percentage_surcharges     GOÄ 441 beside its base service → `surcharge_not_modelled`,
#:                                    not `unknown_ziffer`, and no error blaming the GOÄ edition.
#:   case_j_coverage_sprint_batch1    GOÄ 1473 beside GOÄ 1485 → `padnext_blocked_exclusion` on
#:                                    `excl_man_1473_1485` (docs/content/coverage-sprint-plan.md,
#:                                    batch 1). Neither Ziffer carried an enforced rule before that
#:                                    batch; this is the known-answer proof that the new CSV row
#:                                    actually suppresses the position it names.
REGRESSION_CASES = (
    "case_h_cross_invoice_duplicates",
    "case_i_percentage_surcharges",
    "case_j_coverage_sprint_batch1",
)

#: Case A's receipt canary. Not computable from the catalog — it is a SHA-256 over the engine's own
#: canonical output — so it is pinned as a *witness* rather than derived, and the golden test
#: additionally asserts two runs agree with each other. A move here means the catalog, the rule
#: tables, the logic, the solver, the policy or the response shape changed; `app/services/receipt.py`
#: documents which of those are expected to move it.
#:
#: Moved on 2026-09-12 by the coverage-sprint batch 1 rule additions (`docs/content/
#: coverage-sprint-plan.md`): 86 new enforced rules changed `rules_hash`, which the receipt covers,
#: while nothing about case A's own Ziffern, factors or amounts changed. Re-verified stable across
#: two runs before this value was updated — see `test_case_a_receipt_is_stable_across_runs`.
CASE_A_RECEIPT_PREFIX = "c8a8aed33dcc7cd9"


# ------------------------------------------------------------------------------------------
# the source data
# ------------------------------------------------------------------------------------------


def _rows(name: str) -> list[dict[str, str]]:
    path = RULES_DIR / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _is_verified(row: dict[str, str]) -> bool:
    return row.get("verified", "").strip().lower() == "true"


@dataclass(frozen=True)
class Catalog:
    punktwert_cent: Decimal
    punkte: dict[str, int]
    category: dict[str, str]
    status: dict[str, str]
    official_text: dict[str, str]
    bands: dict[str, dict[str, str]]
    special_bands: dict[str, dict[str, str]]
    version: str
    #: Ziffern the law defines as a percentage Zuschlag: in the catalog's residue file, not in the
    #: catalog. See `UNPARSED_ROWS_PATH`.
    percentage_surcharges: frozenset[str] = frozenset()

    def band(self, ziffer: str) -> dict[str, str]:
        if ziffer in self.special_bands:
            return self.special_bands[ziffer]
        return self.bands.get(self.category.get(ziffer, ""), {})

    def amount_eur(self, ziffer: str, faktor: Decimal, anzahl: int = 1) -> Decimal | None:
        """§ 5 Abs. 1 GOÄ. `None` when the Ziffer is not in the catalog at all."""
        punkte = self.punkte.get(ziffer)
        if punkte is None:
            return None
        cents = Decimal(punkte) * faktor * self.punktwert_cent
        return (cents / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP) * anzahl


def _load_percentage_surcharges() -> frozenset[str]:
    if not UNPARSED_ROWS_PATH.exists():
        return frozenset()
    payload = json.loads(UNPARSED_ROWS_PATH.read_text(encoding="utf-8"))
    return frozenset(
        str(row["ziffer"]).strip()
        for row in payload.get("rows", [])
        if row.get("typ") == "prozent_zuschlag" and str(row.get("ziffer", "")).strip()
    )


def load_catalog() -> Catalog:
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    ziffern = raw["ziffern"]
    return Catalog(
        punktwert_cent=Decimal(str(raw["punktwert_cent"])),
        punkte={z["ziffer"]: z["punkte"] for z in ziffern if z.get("punkte") is not None},
        category={z["ziffer"]: z.get("category", "") for z in ziffern},
        status={z["ziffer"]: z.get("status", "") for z in ziffern},
        official_text={z["ziffer"]: z.get("official_text", "") for z in ziffern},
        bands=raw["factor_bands"],
        special_bands=raw.get("special_factor_ziffern", {}),
        version=raw["catalog_version"],
        percentage_surcharges=_load_percentage_surcharges(),
    )


@dataclass(frozen=True)
class ExclusionRow:
    rule_id: str
    from_ziffer: str
    to_ziffer: str
    mutual: bool
    legal_basis: str
    verified: bool


@dataclass(frozen=True)
class CapRow:
    rule_id: str
    ziffer: str
    max_factor: Decimal
    legal_basis: str
    verified: bool


@dataclass(frozen=True)
class PairRow:
    """A `specificity` or `zielleistung` row — two Ziffern, the second one loses."""

    rule_id: str
    wins: str
    loses: str
    legal_basis: str
    verified: bool


@dataclass(frozen=True)
class Rules:
    exclusions: tuple[ExclusionRow, ...]
    caps: tuple[CapRow, ...]
    pairs: tuple[PairRow, ...]

    def any_direction_exists(self, a: str, b: str) -> bool:
        """Is there *any* exclusion row saying `a` excludes `b`, verified or not?

        `logic/datalog/goae_rules.dl` LAYER 3 decides a one-way exclusion only when the table
        carries no row for the reverse direction — `!exclusion(_, B, A, _)`, with no `verified`
        filter on it. So a golden case has to be built from a pair that is one-way in the *table*,
        not merely one-way among the verified rows.
        """
        return any(r.from_ziffer == a and r.to_ziffer == b for r in self.exclusions)

    def cap_for(self, ziffer: str) -> CapRow | None:
        for row in self.caps:
            if row.ziffer == ziffer and row.verified:
                return row
        return None


def _legal_basis_of(rules: Rules, rule_id: str) -> str:
    """The `legal_basis` column of whichever rule table carries `rule_id`."""
    for row in (*rules.exclusions, *rules.caps, *rules.pairs):
        if row.rule_id == rule_id:
            return row.legal_basis
    return ""


def load_rules() -> Rules:
    exclusions = tuple(
        ExclusionRow(
            rule_id=r["rule_id"],
            from_ziffer=r["from_ziffer"],
            to_ziffer=r["to_ziffer"],
            mutual=r["direction"].strip() == "mutual",
            legal_basis=r.get("legal_basis", ""),
            verified=_is_verified(r),
        )
        # Both files, like `app.rules.rule_store.EXCLUSIONS_FILES`: `exclusions.manual.csv` is
        # not auto-extracted residue, it is the other half of the same table, and a golden case
        # built only from `exclusions.csv` would silently never exercise a hand-curated rule.
        for name in ("exclusions.csv", "exclusions.manual.csv")
        for r in _rows(name)
    )
    caps = tuple(
        CapRow(
            rule_id=r["rule_id"],
            ziffer=r["ziffer"],
            max_factor=Decimal(r["max_factor"]),
            legal_basis=r.get("legal_basis", ""),
            verified=_is_verified(r),
        )
        for r in _rows("factor_caps.csv")
    )
    pairs = tuple(
        [
            PairRow(
                rule_id=r["rule_id"],
                wins=r["specific_ziffer"],
                loses=r["general_ziffer"],
                legal_basis=r.get("legal_basis", ""),
                verified=_is_verified(r),
            )
            for r in _rows("specificity.csv")
        ]
        + [
            PairRow(
                rule_id=r["rule_id"],
                wins=r["parent_ziffer"],
                loses=r["child_ziffer"],
                legal_basis=r.get("legal_basis", ""),
                verified=_is_verified(r),
            )
            for name in ("zielleistung.csv", "zielleistung.manual.csv")
            for r in _rows(name)
        ]
    )
    return Rules(exclusions=exclusions, caps=caps, pairs=pairs)


# ------------------------------------------------------------------------------------------
# the delivery
# ------------------------------------------------------------------------------------------


@dataclass
class ClaimedPosition:
    positionsnr: str
    ziffer: str
    go: str
    faktor: Decimal | None
    anzahl: int
    punktzahl: int | None
    gesamtbetrag: Decimal | None


@dataclass
class BillingCase:
    """One `<abrechnungsfall>`: the invoice it sits in, and the lines billed on it.

    The unit the engine grounds a Soufflé run in, and — since the duplicate-Ziffer fix — the unit a
    repeated Ziffer is judged against. Kept here so this module can state that expectation without
    reading `app/padnext/audit.py`, which it may not import.
    """

    rechnungs_id: str
    positions: list[ClaimedPosition]


@dataclass
class ParsedDelivery:
    echtdaten_declared: str | None
    invoice_ids: list[str]
    positions: list[ClaimedPosition]
    #: The same lines as `positions`, still grouped by the `<abrechnungsfall>` they were billed on
    #: and in the same document order, so `positions == [p for c in cases for p in c.positions]`.
    cases: list[BillingCase] = field(default_factory=list)


def _text(element: ET.Element, tag: str) -> str | None:
    found = element.find(f"{PAD_NS}{tag}")
    if found is None or found.text is None:
        return None
    stripped = found.text.strip()
    return stripped or None


def parse_delivery(path: Path) -> ParsedDelivery:
    """Read the claimed lines out of a delivery with the standard library only.

    Just enough of PADnext ADL to state an expectation: the `@echtdaten` declaration, the invoice
    ids, and each `<goziffer>`'s Ziffer, factor, quantity, punktzahl and claimed amount. No patient
    field is read, for the same reason `app/schemas/padnext.py` does not model one.
    """
    def _position(goziffer: ET.Element) -> ClaimedPosition:
        faktor = _text(goziffer, "faktor")
        anzahl = _text(goziffer, "anzahl")
        punktzahl = _text(goziffer, "punktzahl")
        betrag = _text(goziffer, "gesamtbetrag")
        return ClaimedPosition(
            positionsnr=goziffer.get("positionsnr", ""),
            ziffer=goziffer.get("ziffer", ""),
            go=goziffer.get("go", "GOÄ"),
            faktor=Decimal(faktor) if faktor else None,
            anzahl=int(anzahl) if anzahl else 1,
            punktzahl=int(punktzahl) if punktzahl else None,
            gesamtbetrag=Decimal(betrag) if betrag else None,
        )

    root = ET.fromstring(path.read_bytes())

    # Walked as a tree rather than with `root.iter(goziffer)`, so the `<abrechnungsfall>` a line was
    # billed on survives the parse. Flattening it away here is what let the duplicate-Ziffer
    # expectation below compare two patients' invoices with each other.
    cases: list[BillingCase] = []
    for invoice in root.iter(f"{PAD_NS}rechnung"):
        for case in invoice.iter(f"{PAD_NS}abrechnungsfall"):
            cases.append(
                BillingCase(
                    rechnungs_id=invoice.get("id", ""),
                    positions=[_position(g) for g in case.iter(f"{PAD_NS}goziffer")],
                )
            )

    return ParsedDelivery(
        echtdaten_declared=root.get("echtdaten"),
        invoice_ids=[inv.get("id", "") for inv in root.iter(f"{PAD_NS}rechnung")],
        positions=[p for case in cases for p in case.positions],
        cases=cases,
    )


# ------------------------------------------------------------------------------------------
# the expectation
# ------------------------------------------------------------------------------------------


@dataclass
class ExpectedPosition:
    positionsnr: str
    ziffer: str
    punkte: int | None
    claimed_faktor: str | None
    claimed_amount_eur: str | None
    recomputed_amount_eur: str | None
    amount_delta_eur: str | None
    verdict: str
    bucket: str
    blocked_by: str | None
    verified_rule_ids: list[str] = field(default_factory=list)
    cited_rule_ids: list[str] = field(default_factory=list)


def expected_report(path: Path, *, catalog: Catalog, rules: Rules) -> dict:
    """The report the contract says this delivery must produce.

    The order of the bucket tests is the one `app/schemas/padnext.py` documents and
    `docs/api/PARTNER_API.md` §2 publishes: proof that a position is wrong first, then every reason
    we cannot speak, and only a line that survives all of them is called safe.
    """
    delivery = parse_delivery(path)
    claimed_ziffern = {p.ziffer for p in delivery.positions}

    # Which VERIFIED rules bore on this invoice at all. A rule bears only if every Ziffer it names
    # is claimed; a verified rule is credited to both of its endpoints, because the solver answered
    # for both. Unverified rules are credited only to the side they would have suppressed.
    verified_by_ziffer: dict[str, list[str]] = {}
    advisory_by_ziffer: dict[str, list[str]] = {}

    def _credit(target: dict[str, list[str]], ziffern: tuple[str, ...], rule_id: str) -> None:
        for ziffer in ziffern:
            bucket = target.setdefault(ziffer, [])
            if rule_id and rule_id not in bucket:
                bucket.append(rule_id)

    for excl in rules.exclusions:
        named = (excl.from_ziffer, excl.to_ziffer)
        if not set(named) <= claimed_ziffern:
            continue
        loses = named if excl.mutual else (excl.to_ziffer,)
        _credit(*((verified_by_ziffer, named) if excl.verified else (advisory_by_ziffer, loses)),
                excl.rule_id)
    for pair in rules.pairs:
        named = (pair.wins, pair.loses)
        if not set(named) <= claimed_ziffern:
            continue
        loses = (pair.loses,)
        _credit(*((verified_by_ziffer, named) if pair.verified else (advisory_by_ziffer, loses)),
                pair.rule_id)
    for cap in rules.caps:
        if cap.ziffer not in claimed_ziffern:
            continue
        _credit(verified_by_ziffer if cap.verified else advisory_by_ziffer, (cap.ziffer,),
                cap.rule_id)

    # One-way suppression, exactly as LAYER 3 of the datalog decides it: A excludes B, and the
    # table carries no row for B excluding A.
    blocked: dict[str, tuple[str, str]] = {}  # loser ziffer -> (winner ziffer, rule_id)
    for excl in rules.exclusions:
        if not excl.verified or excl.mutual:
            continue
        if not {excl.from_ziffer, excl.to_ziffer} <= claimed_ziffern:
            continue
        if rules.any_direction_exists(excl.to_ziffer, excl.from_ziffer):
            continue  # the table is ambiguous about the direction; the solver refuses to decide
        blocked[excl.to_ziffer] = (excl.from_ziffer, excl.rule_id)
    for pair in rules.pairs:
        if pair.verified and {pair.wins, pair.loses} <= claimed_ziffern:
            blocked.setdefault(pair.loses, (pair.wins, pair.rule_id))

    positions: list[ExpectedPosition] = []
    findings: list[dict] = []
    claimed_total = ZERO
    recomputed_total = ZERO
    comparable_claimed = ZERO
    unpriceable_claimed = ZERO
    buckets = {"confirmed_fine": ZERO, "confirmed_wrong": ZERO, "unconfirmed": ZERO}

    for position in delivery.positions:
        claimed = position.gesamtbetrag
        claimed_total += claimed or ZERO
        recomputed = (
            catalog.amount_eur(position.ziffer, position.faktor, position.anzahl)
            if position.faktor is not None
            else None
        )
        in_catalog = position.ziffer in catalog.punkte
        cited: list[str] = []
        verified_defects: list[str] = []

        if recomputed is None:
            unpriceable_claimed += claimed or ZERO
        else:
            recomputed_total += recomputed
            if claimed is not None:
                comparable_claimed += claimed

        # § 5 Abs. 1 GOÄ: the Leistungslegende cap, then the chapter Höchstsatz. The band is the
        # stricter statement about the schedule as a whole, so it wins when both are broken.
        band = catalog.band(position.ziffer)
        cap = rules.cap_for(position.ziffer)
        over_band = (
            position.faktor is not None
            and band.get("max")
            and position.faktor > Decimal(band["max"])
        )
        over_cap = cap is not None and position.faktor is not None and position.faktor > cap.max_factor
        if over_band or over_cap:
            rule_id = "" if over_band or cap is None else cap.rule_id
            verified_defects.append("padnext_factor_above_maximum")
            if rule_id:
                cited.append(rule_id)
            findings.append(
                {
                    "type": "padnext_factor_above_maximum",
                    "severity": "error",
                    "positionsnr": position.positionsnr,
                    "ziffer": position.ziffer,
                    "rule_id": rule_id,
                    "legal_basis": (
                        band.get("legal_basis", "§ 5 Abs. 1 GOÄ")
                        if over_band or cap is None
                        else cap.legal_basis
                    ),
                }
            )

        # Pure arithmetic against the versioned catalog. No rule judgement, and no tolerance:
        # a cent is a cent (§ 5 Abs. 1 Satz 4 GOÄ).
        delta = None
        if recomputed is not None and claimed is not None:
            delta = claimed - recomputed
            if delta != 0:
                verified_defects.append("padnext_amount_mismatch")
                findings.append(
                    {
                        "type": "padnext_amount_mismatch",
                        "severity": "error",
                        "positionsnr": position.positionsnr,
                        "ziffer": position.ziffer,
                        "rule_id": "",
                        "legal_basis": "§ 5 Abs. 1 GOÄ",
                    }
                )

        suppressed = blocked.get(position.ziffer)
        if suppressed:
            # `PadnextFinding`: "every non-chargeable position produces at least one". The rule id
            # is the citation a payer's dispute turns on, so the expectation names it.
            cited.append(suppressed[1])
            findings.append(
                {
                    "type": "padnext_blocked_exclusion",
                    "severity": "error",
                    "positionsnr": position.positionsnr,
                    "ziffer": position.ziffer,
                    "rule_id": suppressed[1],
                    "legal_basis": _legal_basis_of(rules, suppressed[1]),
                }
            )

        if not in_catalog and position.ziffer in catalog.percentage_surcharges:
            # Not `unknown_ziffer`. The Ziffer is absent from the catalog because the law gives it
            # no Punktzahl, not because the importer lost it, and the contract's two sentences say
            # different things to a billing centre: one is about their export, the other about this
            # engine's coverage. Same `unconfirmed` bucket — a surcharge is no more judged than an
            # unknown Ziffer is — and the finding is `info`, because there is nothing to correct.
            verdict, bucket, blocked_by = "surcharge_not_modelled", "unconfirmed", None
            findings.append(
                {
                    "type": "padnext_surcharge_not_modelled",
                    "severity": "info",
                    "positionsnr": position.positionsnr,
                    "ziffer": position.ziffer,
                    "rule_id": "",
                    "legal_basis": "§ 5 GOÄ",
                }
            )
        elif not in_catalog:
            verdict, bucket, blocked_by = "unknown_ziffer", "unconfirmed", None
        elif suppressed:
            verdict, blocked_by = "blocked", suppressed[0]
            bucket = "confirmed_wrong"
        else:
            verdict, blocked_by = "chargeable", None
            bucket = "unconfirmed"

        if verified_defects:
            bucket = "confirmed_wrong"
        elif verdict == "chargeable":
            if advisory_by_ziffer.get(position.ziffer):
                bucket = "unconfirmed"
            elif verified_by_ziffer.get(position.ziffer):
                bucket = "confirmed_fine"
            else:
                bucket = "unconfirmed"

        buckets[bucket] += claimed or ZERO
        positions.append(
            ExpectedPosition(
                positionsnr=position.positionsnr,
                ziffer=position.ziffer,
                punkte=catalog.punkte.get(position.ziffer),
                claimed_faktor=str(position.faktor) if position.faktor is not None else None,
                claimed_amount_eur=str(claimed) if claimed is not None else None,
                recomputed_amount_eur=str(recomputed) if recomputed is not None else None,
                amount_delta_eur=str(delta) if delta is not None else None,
                verdict=verdict,
                bucket=bucket,
                blocked_by=blocked_by,
                verified_rule_ids=sorted(verified_by_ziffer.get(position.ziffer, [])),
                cited_rule_ids=sorted(set(cited)),
            )
        )

    # A Ziffer claimed twice **on one `<abrechnungsfall>`** is reported once: the rule evaluation is
    # Ziffer-keyed within a billing case, so it cannot see the second line, and a reader is entitled
    # to know that. Severity `warning` — it says the check was coarser than the invoice, not that a
    # line is wrong — so it moves no euro into `confirmed_wrong`.
    #
    # Attributed to the *repeat* line, not the first one: the first line is the one the Ziffer-keyed
    # rule check actually judged, and the repeat is the one nothing was said about.
    #
    # **Scoped to the billing case, and that scope is the expectation.** A delivery of twenty
    # invoices in which each patient is billed GOÄ 1 once has no repeat anywhere — one Ziffer per
    # case, twenty separate rule evaluations, nothing folded away and so nothing to warn about. This
    # module used to walk `delivery.positions()` flat and produce nineteen warnings for that
    # delivery, exactly as the engine did; both were wrong, and an oracle that shares the engine's
    # bug cannot catch it. `case_h_cross_invoice_duplicates/` is the delivery that pins this.
    for case in delivery.cases:
        seen: set[str] = set()
        for position in case.positions:
            if position.ziffer in seen:
                findings.append(
                    {
                        "type": "padnext_duplicate_ziffer",
                        "severity": "warning",
                        "positionsnr": position.positionsnr,
                        "ziffer": position.ziffer,
                        "rule_id": "",
                        "legal_basis": "",
                    }
                )
            seen.add(position.ziffer)

    # The engine reports one global `advisory_rules_present` finding whenever the rule set holds
    # any advisory rule at all, which it does at this rules_version. Its counts are read from
    # `rule_coverage_detail` on the response and are explicitly not a contract
    # (`docs/api/PARTNER_API.md` §2), so the expectation names the type and not the numbers.
    findings.append({"type": "advisory_rules_present", "severity": "warning", "positionsnr": None,
                     "ziffer": None, "rule_id": "", "legal_basis": ""})

    judged = buckets["confirmed_fine"] + buckets["confirmed_wrong"]
    coverage = float(judged / claimed_total) if claimed_total else 0.0

    return {
        "invoice_ids": delivery.invoice_ids,
        "echtdaten_declared": delivery.echtdaten_declared,
        "catalog_version": catalog.version,
        "claimed_total_eur": str(claimed_total),
        "recomputed_total_eur": str(recomputed_total),
        "comparable_claimed_eur": str(comparable_claimed),
        "arithmetic_delta_eur": str(comparable_claimed - recomputed_total),
        "unpriceable_claimed_eur": str(unpriceable_claimed),
        "confirmed_fine_eur": str(buckets["confirmed_fine"]),
        "confirmed_wrong_eur": str(buckets["confirmed_wrong"]),
        "unconfirmed_eur": str(buckets["unconfirmed"]),
        "coverage_ratio": round(coverage, 4),
        "finding_types": sorted({f["type"] for f in findings}),
        "findings": findings,
        "positions": [vars(p) for p in positions],
    }


# ------------------------------------------------------------------------------------------
# comparing a live report against an expectation
# ------------------------------------------------------------------------------------------

#: `coverage_ratio` is the one number in a report that is a float, because the contract defines it
#: as a display ratio and never as money. Compared to four places, which is what a UI shows.
RATIO_PLACES = 4

#: The euro fields compared as `Decimal`. Every one of them arrives as a decimal string precisely so
#: that a cent survives the trip, so a comparison that went through `float` would throw away the
#: property being tested.
MONEY_FIELDS = (
    "claimed_total_eur",
    "recomputed_total_eur",
    "comparable_claimed_eur",
    "arithmetic_delta_eur",
    "unpriceable_claimed_eur",
    "confirmed_fine_eur",
    "confirmed_wrong_eur",
    "unconfirmed_eur",
)


def compare_report(report: dict, expected: dict) -> list[str]:
    """Every way a live report differs from its expectation, as human sentences.

    Returns an empty list when they agree. Shared by `tests/test_golden_cases.py` and
    `scripts/e2e_partner_api.py` on purpose: two implementations of "does this match" would
    eventually disagree about what the golden files mean, and the one that ran in CI would win by
    accident rather than on the merits.

    Positions are compared **in document order** rather than by `positionsnr`. That number is unique
    within an `<abrechnungsfall>` and not across a delivery, so keying on it would quietly pair up
    the wrong lines in a multi-invoice case — which is exactly the defect
    `tests/golden/bug_positionsnr_collision/` was built to catch, and now guards as a regression.
    """
    problems: list[str] = []

    if report.get("invoice_ids") != expected["invoice_ids"]:
        problems.append(
            f"invoice_ids: {report.get('invoice_ids')!r} != {expected['invoice_ids']!r}"
        )
    if report.get("catalog_version") != expected["catalog_version"]:
        problems.append(
            f"catalog_version: {report.get('catalog_version')!r} != "
            f"{expected['catalog_version']!r} — the golden euro figures belong to another catalog"
        )

    for name in MONEY_FIELDS:
        got, want = report.get(name), expected[name]
        if got is None or Decimal(got) != Decimal(want):
            problems.append(f"{name}: {got} != {want}")

    # The identity the contract publishes. Checked here as well as by the response schema, because
    # this is the assertion a partner's own reconciliation performs.
    try:
        three = (
            Decimal(report["confirmed_fine_eur"])
            + Decimal(report["confirmed_wrong_eur"])
            + Decimal(report["unconfirmed_eur"])
        )
        if three != Decimal(report["claimed_total_eur"]):
            problems.append(
                f"buckets do not reconcile: {three} != {report['claimed_total_eur']}"
            )
    except (KeyError, TypeError):
        problems.append("buckets missing from the report")

    ratio = report.get("coverage_ratio")
    if ratio is None or round(ratio, RATIO_PLACES) != round(expected["coverage_ratio"], RATIO_PLACES):
        problems.append(f"coverage_ratio: {ratio} != {expected['coverage_ratio']}")

    live_findings = report.get("findings") or []
    types = sorted({f["type"] for f in live_findings})
    if types != expected["finding_types"]:
        problems.append(f"finding types: {types} != {expected['finding_types']}")

    # Position, Ziffer and rule id, all three. A rule citation is what a payer's dispute turns on,
    # so it is asserted rather than sampled.
    live = [(f["type"], f["positionsnr"], f["ziffer"], f["rule_id"]) for f in live_findings]
    for finding in expected["findings"]:
        wanted = (finding["type"], finding["positionsnr"], finding["ziffer"], finding["rule_id"])
        if wanted not in live:
            problems.append(f"missing finding {wanted}; report has {live}")

    live_positions = report.get("positions") or []
    if len(live_positions) != len(expected["positions"]):
        problems.append(
            f"position count: {len(live_positions)} != {len(expected['positions'])}"
        )
        return problems

    for got, want in zip(live_positions, expected["positions"]):
        where = f"position {want['positionsnr']} (GOÄ {want['ziffer']})"
        for name in ("positionsnr", "ziffer", "punkte", "verdict", "bucket", "blocked_by"):
            if got.get(name) != want[name]:
                problems.append(f"{where}: {name} {got.get(name)!r} != {want[name]!r}")
        if got.get("verified_rule_ids") != want["verified_rule_ids"]:
            problems.append(
                f"{where}: verified_rule_ids {got.get('verified_rule_ids')} != "
                f"{want['verified_rule_ids']}"
            )
        for name in ("claimed_faktor", "claimed_amount_eur", "recomputed_amount_eur"):
            live_value, wanted_value = got.get(name), want[name]
            if wanted_value is None:
                if live_value is not None:
                    problems.append(f"{where}: {name} {live_value!r} != None")
            elif live_value is None or Decimal(live_value) != Decimal(wanted_value):
                problems.append(f"{where}: {name} {live_value} != {wanted_value}")

    return problems


def load_expected(case: str) -> dict:
    """The committed `expected.json` for one case."""
    return json.loads((GOLDEN_DIR / case / "expected.json").read_text(encoding="utf-8"))


def delivery_bytes(case: str) -> bytes:
    return (GOLDEN_DIR / case / "delivery_padx.xml").read_bytes()


# ------------------------------------------------------------------------------------------
# per-case wrapping: what the HTTP layer must do, beyond the report
# ------------------------------------------------------------------------------------------


def build(case: str) -> dict:
    """The complete `expected.json` for one case, report plus HTTP expectation."""
    catalog, rules = load_catalog(), load_rules()
    delivery = GOLDEN_DIR / case / "delivery_padx.xml"

    if case == "case_e_echtdaten_gate":
        # The gate, not a report. `@echtdaten` is absent, which `app/schemas/padnext.py` is explicit
        # is **not** "probably test data": it is unknown, and unknown is refused. The envelope's
        # `error_code` stays the most fundamental problem (`docs/api/PARTNER_API.md` §5) while the
        # batched list under `details.errors` names every problem, this one included.
        anonymised = expected_report(
            GOLDEN_DIR / "case_a_known_answer" / "delivery_padx.xml", catalog=catalog, rules=rules
        )
        return {
            "case": case,
            "delivery": delivery.name,
            "http_status": 422,
            "error_code": "ECHTDATEN_UNDECLARED",
            "batched_error_codes_include": ["echtdaten_undeclared"],
            "batched_blocking_error_count_at_least": 1,
            "after_anonymisation": {
                "http_status": 200,
                "report": anonymised,
                "note": (
                    "scripts/anonymize_padnext.py stamps echtdaten=\"false\" and rebuilds the "
                    "payload from its allowlist, so the audit is case A's again."
                ),
            },
        }

    expected = {
        "case": case,
        "delivery": delivery.name,
        "http_status": 200,
        "report": expected_report(delivery, catalog=catalog, rules=rules),
    }
    if case == "case_a_known_answer":
        expected["receipt_hash_prefix"] = CASE_A_RECEIPT_PREFIX
        expected["receipt_hash_stable_across_runs"] = True
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="rewrite every expected.json")
    args = parser.parse_args()

    for case in (*CASES, *BUG_CASES, *REGRESSION_CASES):
        payload = build(case)
        target = GOLDEN_DIR / case / "expected.json"
        rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        if args.write:
            target.write_text(rendered, encoding="utf-8")
            print(f"wrote {target.relative_to(REPO_ROOT)}")
        else:
            current = target.read_text(encoding="utf-8") if target.exists() else ""
            state = "up to date" if current == rendered else "STALE — run with --write"
            print(f"{target.relative_to(REPO_ROOT)}: {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
