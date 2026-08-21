"""The vocabulary the bridge understands, published for the UI.

Without this, a user has to type identifiers like `vollstaendige_untersuchung_organsystem` and
guess which organs are valid for a puncture. A typo produces an `unmapped_entity` warning and the
service is simply not charged — a silent under-billing that looks like a successful request.

Deriving the pickers from the same CSV the bridge reads removes that entire class of error: the
UI can only offer combinations that map to something. It is generated, never hand-maintained, so
it cannot drift from the mapping table.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.bridge.entity_to_ziffer import (
    COMPLEXITY_ALIASES,
    _COMPLEXITY_QUALIFIED,
    load_mapping,
)
from app.catalog import Catalog
from app.rules.rule_store import RuleStore


@dataclass
class OrganOption:
    value: str
    label: str
    #: Ziffern this organ can produce for the entity type it is listed under, so the UI can show
    #: "→ GOÄ 301" next to the choice. Purely informational; the engine still decides.
    ziffern: list[str] = field(default_factory=list)


@dataclass
class EntityTypeOption:
    entity_type: str
    kind: str
    label_de: str
    label_en: str
    organs: list[OrganOption] = field(default_factory=list)
    subtypes: list[OrganOption] = field(default_factory=list)
    #: Only the complexities this type actually has a mapping row for. Offering all three would
    #: let a user pick one that maps to nothing — the service would then silently not be charged.
    complexities: list[OrganOption] = field(default_factory=list)
    ziffern: list[str] = field(default_factory=list)
    complexity_qualified: bool = False
    requires_organ: bool = False
    #: True when every mapping row for this type carries a subtype (lab analytes). Without one the
    #: bridge matches nothing, so the form has to insist rather than let it charge zero.
    requires_subtype: bool = False
    analog_only: bool = False
    notes: str = ""


def _titlecase(value: str) -> str:
    """`wirbelgelenk` -> `Wirbelgelenk`. Display only; the submitted value stays the identifier."""
    return value.replace("_", " ").strip().capitalize() if value else value


def build_vocabulary(catalog: Catalog, rules: RuleStore) -> dict:
    mapping = load_mapping()

    by_type: dict[str, EntityTypeOption] = {}
    for row in mapping:
        option = by_type.get(row.entity_type)
        if option is None:
            option = EntityTypeOption(
                entity_type=row.entity_type,
                kind=row.kind,
                label_de=row.label_de or row.entity_type,
                label_en=row.label_en or row.label_de or row.entity_type,
                complexity_qualified=row.entity_type in _COMPLEXITY_QUALIFIED,
                notes=row.notes,
            )
            by_type[row.entity_type] = option

        if row.ziffer not in option.ziffern and catalog.has(row.ziffer):
            option.ziffern.append(row.ziffer)

        # A row can qualify on BOTH a subtype and an organ (an excision is keyed on size *and*
        # on skin). Recording only one of them left the other off the form, and the bridge then
        # matched nothing — an offered combination that silently charges nothing.
        for bucket, target in ((option.subtypes, row.entity_subtype), (option.organs, row.organ)):
            if not target:
                continue
            existing = next((o for o in bucket if o.value == target), None)
            if existing is None:
                existing = OrganOption(value=target, label=_titlecase(target))
                bucket.append(existing)
            if row.ziffer not in existing.ziffern and catalog.has(row.ziffer):
                existing.ziffern.append(row.ziffer)

    for option in by_type.values():
        # The CSV enumerates every valid organ per type explicitly (a knee puncture carries its
        # own rows for both Nr. 300 and Nr. 301), so there is no group fallback to expand here.
        option.organs.sort(key=lambda o: o.label)
        option.subtypes.sort(key=lambda o: o.label)
        # For a complexity-qualified type the "subtypes" ARE the complexity aliases
        # ("klein"/"gross"), which the complexity picker already covers. Offering both would ask
        # the same question twice, with the second answer silently ignored.
        if option.complexity_qualified:
            # The "subtypes" here are complexity aliases ("klein"/"gross"). Translate them back
            # into the complexity values the schema accepts, and offer only those.
            alias_to_complexity = {
                alias: complexity
                for complexity, aliases in COMPLEXITY_ALIASES.items()
                for alias in aliases
            }
            seen: dict[str, OrganOption] = {}
            for sub in option.subtypes:
                complexity = alias_to_complexity.get(sub.value)
                if complexity is None:
                    continue
                entry = seen.setdefault(
                    complexity, OrganOption(value=complexity, label=complexity)
                )
                for ziffer in sub.ziffern:
                    if ziffer not in entry.ziffern:
                        entry.ziffern.append(ziffer)
            option.complexities = sorted(seen.values(), key=lambda o: o.value)
            option.subtypes = []
        option.ziffern.sort()
        # If every mapping row for this type is organ-qualified, an organ is not optional.
        option.requires_organ = bool(option.organs) and not any(
            row.entity_type == option.entity_type and not row.organ for row in mapping
        )
        option.requires_subtype = bool(option.subtypes) and not any(
            row.entity_type == option.entity_type and not row.entity_subtype for row in mapping
        )

    # Entity types with no mapping at all but a § 6 Abs. 2 analog candidate. Offering them is the
    # difference between a user discovering the analog path and silently losing the service.
    for rule in rules.analog_candidates:
        entity_type = rule.source_entity_type
        if entity_type in by_type:
            continue
        by_type[entity_type] = EntityTypeOption(
            entity_type=entity_type,
            kind="procedure",
            label_de=f"{_titlecase(entity_type)} (Analogansatz § 6 Abs. 2)",
            label_en=f"{_titlecase(entity_type)} (analogous, § 6 (2) GOÄ)",
            analog_only=True,
            notes="Keine eigene Gebührenziffer; wird analog berechnet und ist ärztlich zu prüfen.",
        )

    def dump(option: EntityTypeOption) -> dict:
        return {
            "entity_type": option.entity_type,
            "kind": option.kind,
            "label_de": option.label_de,
            "label_en": option.label_en,
            "ziffern": option.ziffern,
            "complexity_qualified": option.complexity_qualified,
            "requires_organ": option.requires_organ,
            "requires_subtype": option.requires_subtype,
            "analog_only": option.analog_only,
            "notes": option.notes,
            "organs": [
                {"value": o.value, "label": o.label, "ziffern": o.ziffern}
                for o in option.organs
            ],
            "subtypes": [
                {"value": o.value, "label": o.label, "ziffern": o.ziffern} for o in option.subtypes
            ],
            "complexities": [
                {"value": o.value, "ziffern": o.ziffern} for o in option.complexities
            ],
        }

    grouped: dict[str, list[dict]] = {}
    for option in sorted(by_type.values(), key=lambda o: (o.kind, o.label_de)):
        grouped.setdefault(option.kind, []).append(dump(option))

    return {
        "catalog_version": catalog.catalog_version,
        "settings": [
            {"value": "ambulant", "label_de": "ambulant", "label_en": "outpatient (ambulant)"},
            {
                "value": "stationaer",
                "label_de": "stationär −25 %",
                "label_en": "inpatient (stationär) −25 %",
            },
            {
                "value": "belegarzt",
                "label_de": "belegärztlich −15 %",
                "label_en": "attending physician (belegärztlich) −15 %",
            },
        ],
        "complexities": [
            {"value": "einfach", "label_de": "einfach", "label_en": "simple"},
            {"value": "mittel", "label_de": "mittel", "label_en": "moderate"},
            {"value": "komplex", "label_de": "komplex", "label_en": "complex"},
        ],
        "severities": [
            {"value": "leicht", "label_de": "leicht", "label_en": "minor"},
            {"value": "mittel", "label_de": "mittel", "label_en": "moderate"},
            {"value": "schwer", "label_de": "schwer", "label_en": "major"},
        ],
        "entity_types": grouped,
        "counts": {kind: len(options) for kind, options in grouped.items()},
    }
