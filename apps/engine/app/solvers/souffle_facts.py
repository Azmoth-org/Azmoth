"""Generate Soufflé ``.facts`` files from the catalog, the rule store and a bridge result.

Soufflé fact files are tab-separated with *unquoted* symbol fields — the default reader takes
each field literally, so a quoted value arrives with the quotes attached. A tab or newline
inside a value would silently shift every following column, so those are stripped rather than
trusted, and every generated file is validated for arity before Soufflé is invoked.

All non-integers are scaled by 100, because Datalog numbers are 64-bit integers: factor 2.3 is
written 230, confidence 0.94 as 94.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from app.bridge.entity_to_ziffer import BridgeResult
from app.catalog import Catalog
from app.schemas import ClinicalExtraction
from app.rules.rule_store import RuleStore

SCALE = 100

#: Every relation declared ``.input`` in goae_rules.dl, with its arity. Soufflé aborts if a
#: fact file is missing, so all of them are always written — empty when there is nothing to say.
INPUT_RELATIONS: dict[str, int] = {
    "ziffer": 4,
    "exclusion": 4,
    "zielleistung": 3,
    "specificity": 3,
    "act": 3,
    "candidate": 4,
    "sf_band": 3,
    "sf_override": 3,
    "factor_cap": 3,
    "proposed_factor": 2,
    "patient_setting": 1,
    "minderung_rate": 2,
    "minderung_exempt": 1,
}

_UNSAFE = re.compile(r"[\t\r\n]+")


class FactGenerationError(RuntimeError):
    pass


def scale(value: Decimal | float | int | str) -> int:
    """0.94 -> 94, 2.3 -> 230, 1.15 -> 115. Decimal throughout, so 1.15 cannot become 114."""
    return int(
        (Decimal(str(value)) * SCALE).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def unscale(value: int | str) -> Decimal:
    return (Decimal(str(value)) / SCALE).normalize()


def _sanitize(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return _UNSAFE.sub(" ", str(value)).strip()


def _write(path: Path, rows: list[tuple], arity: int) -> None:
    for row in rows:
        if len(row) != arity:
            raise FactGenerationError(
                f"{path.name}: expected arity {arity}, got {len(row)} in row {row!r}"
            )
    lines = ["\t".join(_sanitize(field) for field in row) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def build_fact_rows(
    catalog: Catalog,
    rules: RuleStore,
    bridge: BridgeResult,
    extraction: ClinicalExtraction,
    proposed_factors: dict[str, Decimal] | None = None,
) -> dict[str, list[tuple]]:
    """Assemble every input relation.

    Only the Ziffern and rules that this case can possibly touch are emitted. The catalog holds
    2000-plus positions; shipping all of them into every Datalog run would make each request pay
    for the whole fee schedule.
    """
    relevant = bridge.ziffern()
    # Analog candidates can become chargeable, so their targets must be in the fact base too.
    for request in bridge.analog_requests:
        relevant |= {r.target_ziffer for r in rules.analog_for(request.entity_type)}
    # Anything named by a rule touching a relevant Ziffer must be present as well, or Datalog
    # cannot see the relationship at all.
    for rule in rules.exclusions:
        if rule.from_ziffer in relevant or rule.to_ziffer in relevant:
            relevant |= {rule.from_ziffer, rule.to_ziffer}
    for zrule in rules.zielleistung:
        if zrule.parent_ziffer in relevant or zrule.child_ziffer in relevant:
            relevant |= {zrule.parent_ziffer, zrule.child_ziffer}
    for srule in rules.specificity:
        if srule.specific_ziffer in relevant or srule.general_ziffer in relevant:
            relevant |= {srule.specific_ziffer, srule.general_ziffer}
    relevant |= set((proposed_factors or {}).keys())

    ziffer_rows: list[tuple] = []
    for ziffer in sorted(relevant):
        entry = catalog.get(ziffer)
        if entry is None:
            continue  # reported by the bridge as unknown_ziffer; nothing to say to Datalog
        ziffer_rows.append(
            (entry.ziffer, entry.punkte, entry.category or "UNKNOWN", 1 if entry.is_active else 0)
        )

    setting = extraction.patient.setting

    return {
        "ziffer": ziffer_rows,
        "exclusion": [
            (r.rule_id, r.from_ziffer, r.to_ziffer, 1 if r.is_mutual else 0)
            for r in rules.exclusions
            if r.from_ziffer in relevant and r.to_ziffer in relevant
        ],
        "zielleistung": [
            (r.rule_id, r.parent_ziffer, r.child_ziffer)
            for r in rules.zielleistung
            if r.parent_ziffer in relevant and r.child_ziffer in relevant
        ],
        "specificity": [
            (r.rule_id, r.specific_ziffer, r.general_ziffer)
            for r in rules.specificity
            if r.specific_ziffer in relevant and r.general_ziffer in relevant
        ],
        "act": [(a.act_id, a.source, a.entity_type) for a in bridge.acts],
        "candidate": [
            (c.act_id, c.ziffer, c.priority, scale(c.confidence)) for c in bridge.candidates
        ],
        "sf_band": [
            (letter, scale(band.threshold), scale(band.max))
            for letter, band in sorted(catalog.factor_bands.items())
        ],
        "sf_override": [
            (ziffer, scale(band.threshold), scale(band.max))
            for ziffer, band in sorted(catalog.special_factor_ziffern.items())
            if ziffer in relevant
        ],
        "factor_cap": [
            (r.rule_id, r.ziffer, scale(r.max_factor))
            for r in rules.factor_caps
            if r.ziffer in relevant
        ],
        "proposed_factor": [
            (ziffer, scale(factor)) for ziffer, factor in sorted((proposed_factors or {}).items())
        ],
        "patient_setting": [(setting,)],
        "minderung_rate": [
            (name, scale(catalog.minderung_rate(name)))
            for name in ("ambulant", "stationaer", "belegarzt")
        ],
        "minderung_exempt": [
            (ziffer,) for ziffer in sorted(relevant) if catalog.minderung_exempt(ziffer)
        ],
    }


def write_fact_files(
    fact_dir: Path,
    catalog: Catalog,
    rules: RuleStore,
    bridge: BridgeResult,
    extraction: ClinicalExtraction,
    proposed_factors: dict[str, Decimal] | None = None,
) -> dict[str, int]:
    """Write every ``.input`` relation into ``fact_dir``. Returns row counts per relation."""
    fact_dir.mkdir(parents=True, exist_ok=True)
    rows = build_fact_rows(catalog, rules, bridge, extraction, proposed_factors)

    missing = set(INPUT_RELATIONS) - set(rows)
    if missing:
        raise FactGenerationError(
            f"fact generator does not cover every .input relation: {sorted(missing)}"
        )
    extra = set(rows) - set(INPUT_RELATIONS)
    if extra:
        raise FactGenerationError(f"fact generator produced unknown relations: {sorted(extra)}")

    for relation, arity in INPUT_RELATIONS.items():
        _write(fact_dir / f"{relation}.facts", rows[relation], arity)

    return {relation: len(rows[relation]) for relation in INPUT_RELATIONS}


def read_relation(output_dir: Path, relation: str) -> list[list[str]]:
    path = output_dir / f"{relation}.csv"
    if not path.exists():
        return []
    return [
        line.split("\t")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
