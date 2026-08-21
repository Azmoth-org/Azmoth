"""The bridge: clinical entities -> candidate GOÄ Ziffern.

This is the only place where clinical vocabulary meets fee-schedule identifiers, and it is a
CSV lookup. No model runs here, nothing is inferred, and a Ziffer that is not in the loaded
catalog can never be proposed.

One entity may legitimately produce several candidates — a knee puncture matches both the
generic Nr. 300 and the knee-specific Nr. 301. Both are proposed on purpose: the choice between
them is a rule (``data/rules/specificity.csv``) applied by the Datalog layer, where it appears
in the proof tree, rather than a dictionary-ordering accident hidden in Python.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from app.catalog import Catalog
from app.config import MAPPING_PATH
from app.schemas import (
    AnalogRequest,
    ClinicalAct,
    ClinicalExtraction,
    CodeCandidate,
    Warning_,
)
from app.rules.rule_store import RuleStore

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def normalize_key(value: str | None) -> str:
    """Fold an identifier to canonical ASCII snake_case.

    'Vollständige-Untersuchung Organsystem' and 'vollstaendige_untersuchung_organsystem' must
    reach the table as the same key, whether they were typed by hand or produced by a model.
    """
    if not value:
        return ""
    folded = value.strip().lower().translate(_UMLAUTS)
    folded = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", folded).strip("_")


@dataclass(frozen=True)
class MappingRow:
    entity_type: str
    entity_subtype: str
    organ: str
    ziffer: str
    priority: int
    provenance: str
    notes: str = ""
    #: Which picker this type belongs in. Advisory only — the bridge derives an act's kind from
    #: where the entity appears in the JSON, not from this column. It exists so the UI can offer
    #: the right vocabulary in the right place instead of asking a user to type an identifier.
    kind: str = "procedure"
    label_de: str = ""
    label_en: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.entity_type, self.entity_subtype, self.organ)

    def label(self, lang: str = "de") -> str:
        return (self.label_en if lang == "en" else self.label_de) or self.entity_type


@lru_cache
def load_mapping(path: str | Path = MAPPING_PATH) -> tuple[MappingRow, ...]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"entity->Ziffer mapping not found at {path}")
    rows: list[MappingRow] = []
    with open(path, encoding="utf-8", newline="") as fh:
        for raw in csv.DictReader(fh):
            if not (raw.get("entity_type") or "").strip():
                continue
            # A row without a Ziffer cannot propose anything. Skipped rather than emitting an
            # empty code, which would reach Datalog as a nonexistent position.
            if not (raw.get("ziffer") or "").strip():
                continue
            rows.append(
                MappingRow(
                    entity_type=normalize_key(raw["entity_type"]),
                    entity_subtype=normalize_key(raw.get("entity_subtype")),
                    organ=normalize_key(raw.get("organ")),
                    ziffer=(raw.get("ziffer") or "").strip(),
                    priority=int(raw.get("priority") or 100),
                    provenance=(raw.get("provenance") or "illustrative").strip(),
                    notes=(raw.get("notes") or "").strip(),
                    kind=(raw.get("kind") or "procedure").strip(),
                    label_de=(raw.get("label_de") or "").strip(),
                    label_en=(raw.get("label_en") or "").strip(),
                )
            )
    return tuple(rows)


@dataclass
class BridgeResult:
    acts: list[ClinicalAct] = field(default_factory=list)
    candidates: list[CodeCandidate] = field(default_factory=list)
    analog_requests: list[AnalogRequest] = field(default_factory=list)
    warnings: list[Warning_] = field(default_factory=list)

    def ziffern(self) -> set[str]:
        return {c.ziffer for c in self.candidates}

    def act(self, act_id: str) -> ClinicalAct | None:
        return next((a for a in self.acts if a.act_id == act_id), None)

    def ziffern_for_entity(self, needle: str) -> set[str]:
        """Ziffern derived from an entity, addressed by its id or its type."""
        key = normalize_key(needle)
        act_ids = {
            a.act_id
            for a in self.acts
            if a.entity_id == needle or normalize_key(a.entity_type) == key
        }
        return {c.ziffer for c in self.candidates if c.act_id in act_ids}


def build_acts(extraction: ClinicalExtraction) -> list[ClinicalAct]:
    """Flatten an extraction into numbered clinical acts.

    Lab tests are modelled as ``entity_type='labor'`` with the analyte as the subtype, so the
    mapping table keeps a single (type, subtype, organ) shape throughout.
    """
    acts: list[ClinicalAct] = []

    def add(
        source: str,
        entity_id: str,
        entity_type: str,
        subtype: str | None,
        organ: str | None,
        description: str,
        confidence: Decimal,
    ) -> None:
        acts.append(
            ClinicalAct(
                act_id=f"a{len(acts) + 1}",
                entity_id=entity_id,
                source=source,  # type: ignore[arg-type]
                entity_type=normalize_key(entity_type),
                entity_subtype=normalize_key(subtype) or None,
                organ=normalize_key(organ) or None,
                description=description,
                confidence=confidence,
            )
        )

    if c := extraction.consultation:
        detail = c.type + (f" ({c.duration_minutes} Min)" if c.duration_minutes else "")
        add("consultation", c.id or "consultation", c.type, None, None, detail, c.confidence)

    for exam in extraction.examinations:
        add(
            "examination",
            exam.id or "",
            exam.type,
            None,
            exam.organ_system or (exam.organs[0] if exam.organs else None),
            f"{exam.type} ({exam.organ_system or '-'})",
            exam.confidence,
        )

    for proc in extraction.procedures:
        add(
            "procedure",
            proc.id or "",
            proc.type,
            proc.complexity if _subtype_is_complexity(proc.type) else None,
            proc.organ,
            proc.details or proc.type,
            proc.confidence,
        )

    for lab in extraction.lab_tests:
        add("lab_test", lab.id or "", "labor", lab.type, None, f"Labor: {lab.type}", lab.confidence)

    return acts


#: Entity types whose mapping is qualified by complexity rather than by anatomy.
_COMPLEXITY_QUALIFIED = {"exzision_hautgeschwulst", "wundversorgung", "chirurgisch"}


def _subtype_is_complexity(entity_type: str) -> bool:
    return normalize_key(entity_type) in _COMPLEXITY_QUALIFIED


#: Complexity value -> the mapping-table keys it also matches. Module level so the vocabulary
#: builder can invert it and offer only the complexities a given type actually maps.
COMPLEXITY_ALIASES: dict[str, list[str]] = {
    "einfach": ["einfach", "klein"],
    "mittel": ["mittel"],
    "komplex": ["komplex", "gross"],
}


def _complexity_aliases(complexity: str | None) -> list[str]:
    """'komplex' also matches a table row written as 'gross'."""
    return COMPLEXITY_ALIASES.get(complexity or "", [complexity or ""])


def candidates_for_act(act: ClinicalAct, mapping: tuple[MappingRow, ...]) -> list[MappingRow]:
    """Every mapping row matching an act, most specific key first.

    Keys are tried from most to least qualified. All matches are returned, not just the first:
    the generic and the specific candidate both reach the rules engine so that the specificity
    rule can be seen doing its work.
    """
    subtypes = (
        _complexity_aliases(act.entity_subtype)
        if _subtype_is_complexity(act.entity_type)
        else [act.entity_subtype or ""]
    )
    organs = [act.organ or "", ""]

    matches: dict[str, MappingRow] = {}
    for subtype in subtypes + [""]:
        for organ in organs:
            key = (act.entity_type, normalize_key(subtype), normalize_key(organ))
            for row in mapping:
                if row.key == key and row.ziffer not in matches:
                    matches[row.ziffer] = row
    return sorted(matches.values(), key=lambda r: (-r.priority, r.ziffer))


def map_extraction(
    extraction: ClinicalExtraction, catalog: Catalog, rules: RuleStore
) -> BridgeResult:
    result = BridgeResult()
    mapping = load_mapping()
    result.acts = build_acts(extraction)

    for act in result.acts:
        rows = candidates_for_act(act, mapping)
        admitted: list[MappingRow] = []

        for row in rows:
            # Hard invariant: never propose a Ziffer the loaded catalog does not contain.
            if not catalog.has(row.ziffer):
                result.warnings.append(
                    Warning_(
                        type="mapping_references_unknown_ziffer",
                        ziffer=row.ziffer,
                        severity="error",
                        message=(
                            f"Die Mapping-Tabelle verweist für '{act.entity_type}' auf "
                            f"GOÄ {row.ziffer}, die im geladenen Katalog "
                            f"({catalog.catalog_version}) nicht existiert. Der Kandidat wurde "
                            "verworfen; Mapping und Katalog sind nicht konsistent."
                        ),
                    )
                )
                continue
            if not catalog.is_active(row.ziffer):
                result.warnings.append(
                    Warning_(
                        type="mapping_references_inactive_ziffer",
                        ziffer=row.ziffer,
                        message=(
                            f"GOÄ {row.ziffer} ist im Katalog als nicht aktiv markiert und "
                            "wurde nicht vorgeschlagen."
                        ),
                    )
                )
                continue
            admitted.append(row)

        if admitted:
            for row in admitted:
                result.candidates.append(
                    CodeCandidate(
                        act_id=act.act_id,
                        ziffer=row.ziffer,
                        priority=row.priority,
                        confidence=act.confidence,
                        mapping_provenance=row.provenance,
                        mapping_notes=row.notes,
                    )
                )
            continue

        # No mapping. Three honest outcomes; never invent a code.
        analog = rules.analog_for(act.entity_type)
        if analog:
            result.analog_requests.append(
                AnalogRequest(
                    act_id=act.act_id,
                    entity_type=act.entity_type,
                    description=act.description,
                    confidence=act.confidence,
                )
            )
        else:
            result.warnings.append(
                Warning_(
                    type="unmapped_entity",
                    severity="warning",
                    message=(
                        f"Für die dokumentierte Leistung '{act.entity_type}'"
                        + (f" (Organ: {act.organ})" if act.organ else "")
                        + " existiert keine deterministische Zuordnung und kein "
                        "Analogkandidat. Die Leistung wurde NICHT abgerechnet und muss "
                        "manuell geprüft werden."
                    ),
                )
            )

    return result


def resolve_justifications(
    extraction: ClinicalExtraction, bridge: BridgeResult
) -> tuple[dict[str, list[tuple[str, str]]], list[tuple[str, str]], list[Warning_]]:
    """Bind each justification to the Ziffern it can support.

    Returns ``(per_ziffer, encounter_wide, warnings)`` with entries ``(severity, reason)``.
    A justification naming a service it cannot resolve is *not* silently widened to the whole
    invoice — that would let one documented difficulty inflate every line. It is reported.
    """
    per_ziffer: dict[str, list[tuple[str, str]]] = {}
    encounter_wide: list[tuple[str, str]] = []
    warnings: list[Warning_] = []

    # "What exists" is judged against the clinical acts, not the raw extraction. The acts are
    # derived from the extraction, so for real input the two agree — but an entity that produced
    # no act (a diagnosis, say) is not something a justification can attach to, and keying off
    # the acts makes that fall out naturally instead of needing a special case.
    known_ids = {a.entity_id for a in bridge.acts} | extraction.entity_ids()
    known_types = {normalize_key(a.entity_type) for a in bridge.acts}

    for factor in extraction.justification_factors:
        if not factor.applies_to:
            encounter_wide.append((factor.severity, factor.reason))
            continue

        for target in factor.applies_to:
            if target not in known_ids and normalize_key(target) not in known_types:
                warnings.append(
                    Warning_(
                        type="justification_target_unknown",
                        severity="warning",
                        message=(
                            f"Die Begründung '{factor.reason[:60]}' verweist auf "
                            f"'{target}', das in der Extraktion nicht vorkommt. Sie wurde "
                            "NICHT angewendet."
                        ),
                    )
                )
                continue
            ziffern = bridge.ziffern_for_entity(target)
            if not ziffern:
                warnings.append(
                    Warning_(
                        type="justification_target_not_billable",
                        severity="info",
                        message=(
                            f"Die Begründung verweist auf '{target}', dem keine Ziffer "
                            "zugeordnet ist. Sie wurde nicht angewendet."
                        ),
                    )
                )
                continue
            for ziffer in ziffern:
                per_ziffer.setdefault(ziffer, []).append((factor.severity, factor.reason))

    return per_ziffer, encounter_wide, warnings
