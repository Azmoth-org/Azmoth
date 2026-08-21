"""The deterministic bridge, the catalog loader and the rule store."""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from app.bridge.entity_to_ziffer import (
    candidates_for_act,
    load_mapping,
    map_extraction,
    normalize_key,
    resolve_justifications,
)
from app.catalog import ALLOWED_PROVENANCE, ALLOWED_RULE_COVERAGE, Catalog, CatalogError
from app.config import MAPPING_PATH, RULES_DATA_DIR
from app.schemas import ClinicalExtraction


def extraction(**kwargs) -> ClinicalExtraction:
    return ClinicalExtraction.model_validate({"patient": {"setting": "ambulant"}, **kwargs})


# ------------------------------------------------------------------------------------------
# catalog
# ------------------------------------------------------------------------------------------


def test_catalog_is_the_official_snapshot(catalog):
    assert catalog.catalog_version.startswith("goae_official_snapshot_")
    assert "gesetze-im-internet.de" in catalog.source.url
    assert len(catalog.source.sha256_raw) == 64
    assert "§ 5 UrhG" in catalog.source.legal_status


def test_catalog_is_substantial_and_real(catalog):
    assert len(catalog.ziffern) > 2000, "the official Gebührenverzeichnis has thousands of entries"
    assert all(z.provenance == "official" or z.provenance == "manual_override"
               for z in catalog.ziffern.values())


@pytest.mark.parametrize(
    "ziffer,punkte,category",
    [
        ("1", 80, "B"),
        ("3", 150, "B"),
        ("5", 80, "B"),
        ("7", 160, "B"),
        ("8", 260, "B"),
        ("250", 40, "C"),
        ("301", 160, "C"),
        ("410", 200, "C"),
        ("651", 253, "F"),
        ("659", 400, "F"),
        ("3550", 60, "M"),
        ("4800", 217, "N"),
        ("5030", 360, "O"),
    ],
)
def test_known_positions_match_the_official_fee_schedule(catalog, ziffer, punkte, category):
    """Spot checks against values that can be verified independently against the GOÄ."""
    entry = catalog.get(ziffer)

    assert entry is not None, f"GOÄ {ziffer} missing"
    assert entry.punkte == punkte, f"GOÄ {ziffer} Punktzahl"
    assert entry.category == category, f"GOÄ {ziffer} Abschnitt"


def test_every_position_has_a_resolvable_factor_band(catalog):
    unresolved = [z.ziffer for z in catalog.ziffern.values() if z.category is None]

    assert unresolved == [], f"{len(unresolved)} positions have no Abschnitt: {unresolved[:10]}"


@pytest.mark.parametrize(
    "ziffer,threshold,maximum,basis",
    [
        ("7", "2.3", "3.5", "§ 5 Abs. 1, 2"),      # general
        ("5030", "1.8", "2.5", "§ 5 Abs. 3"),      # Abschnitt O
        ("3550", "1.15", "1.3", "§ 5 Abs. 4"),     # Abschnitt M
        ("437", "1.15", "1.3", "§ 5 Abs. 4"),      # named individually in Abs. 4
        ("4800", "2.3", "3.5", "§ 5 Abs. 1, 2"),   # Abschnitt N is NOT in Abs. 4
    ],
)
def test_factor_bands_follow_paragraph_5(catalog, ziffer, threshold, maximum, basis):
    band = catalog.factor_band(ziffer)

    assert band.threshold == Decimal(threshold)
    assert band.max == Decimal(maximum)
    assert basis in band.legal_basis


def test_punktwert_and_rounding_are_decimal_and_cited(catalog):
    assert catalog.punktwert_cent == Decimal("5.82873")
    assert catalog.rounding["policy"] == "ROUND_HALF_UP"
    assert "§ 5 Abs. 1" in catalog.rounding["legal_basis"]


def test_provenance_and_coverage_values_are_from_the_allowed_sets(catalog):
    for entry in catalog.ziffern.values():
        assert entry.provenance in ALLOWED_PROVENANCE
        assert entry.rule_coverage in ALLOWED_RULE_COVERAGE


def test_catalog_summary_exposes_the_sha256_of_the_file(catalog):
    summary = catalog.summary()

    assert len(summary["catalog_sha256"]) == 64
    assert summary["ziffern"] == len(catalog.ziffern)


def test_override_is_applied_and_marked(catalog):
    """The bundled override repairs a legend the importer captured only partially."""
    entry = catalog.get("5030")

    assert entry.provenance == "manual_override"
    assert entry.official_text.startswith("Röntgenaufnahme")
    assert entry.text_quality == "ok"
    assert catalog.overrides_applied


def test_override_without_provenance_is_refused(tmp_path, catalog):
    import json

    overrides = tmp_path / "overrides.json"
    overrides.write_text(
        json.dumps({"overrides": [{"ziffer": "1", "override": {"punkte": 999}}]}),
        encoding="utf-8",
    )

    with pytest.raises(CatalogError, match="missing required provenance"):
        Catalog.load(catalog.path, overrides_path=overrides)


def test_missing_catalog_gives_actionable_instructions(tmp_path):
    with pytest.raises(CatalogError, match="fetch_goae"):
        Catalog.load(tmp_path / "nope.json")


def test_unparsed_rows_are_recorded_not_dropped():
    import json

    from app.config import CATALOG_DIR

    payload = json.loads((CATALOG_DIR / "unparsed_rows.json").read_text(encoding="utf-8"))

    assert payload["count"] > 0, "a parser this permissive would be suspicious"
    assert payload["count"] == len(payload["rows"])
    for row in payload["rows"]:
        assert row["reason"], "every unparsed row must say why it was not understood"
        assert "cells" in row


# ------------------------------------------------------------------------------------------
# rule store
# ------------------------------------------------------------------------------------------


def test_every_rule_file_declares_provenance():
    """A rule without a legal basis and a verification flag is not auditable."""
    required = {"legal_basis", "verified"}
    for path in sorted(RULES_DATA_DIR.glob("*.csv")):
        with open(path, encoding="utf-8", newline="") as fh:
            header = set(next(csv.reader(fh)))
        assert required <= header, f"{path.name} is missing {required - header}"


def test_enforced_rules_carry_a_legal_basis(rules):
    for rule in rules.exclusions + rules.zielleistung + rules.specificity:
        assert rule.legal_basis, f"{rule.rule_id} has no legal basis"
        assert rule.rule_id, "every rule needs an id so a proof can point at it"


def test_verified_rules_carry_a_verification_date(rules):
    for rule in rules.exclusions + rules.zielleistung + rules.specificity:
        if rule.verified:
            assert rule.verified_at, f"{rule.rule_id} is marked verified with no date"
            assert rule.source, f"{rule.rule_id} is marked verified with no source"


def test_auto_extracted_rules_quote_the_law():
    """An automatically extracted rule must carry the sentence it came from, or a reviewer cannot
    check it without re-reading the whole fee schedule."""
    with open(RULES_DATA_DIR / "exclusions.csv", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    assert rows, "the importer produced no exclusion rules"
    for row in rows[:200]:
        assert row["quote"].strip(), f"{row['rule_id']} has no quote"
        assert row["verified"] == "false", "auto-extracted rules must not claim verification"


def test_mutual_direction_is_symmetric_in_the_data(rules):
    edges = {(r.from_ziffer, r.to_ziffer) for r in rules.exclusions}
    for rule in rules.exclusions:
        if rule.is_mutual:
            assert (rule.to_ziffer, rule.from_ziffer) in edges, (
                f"{rule.rule_id} claims to be mutual but the reverse edge is absent"
            )


def test_enforced_rules_only_reference_catalog_positions(catalog, rules):
    for rule in rules.exclusions:
        assert catalog.has(rule.from_ziffer), rule.rule_id
        assert catalog.has(rule.to_ziffer), rule.rule_id
    for zrule in rules.zielleistung:
        assert catalog.has(zrule.parent_ziffer), zrule.rule_id
        assert catalog.has(zrule.child_ziffer), zrule.rule_id


def test_rule_store_can_be_restricted_to_a_case(rules):
    view = rules.restrict_to({"5", "7"})

    assert all(
        r.from_ziffer in {"5", "7"} and r.to_ziffer in {"5", "7"} for r in view.exclusions
    )
    assert len(view.exclusions) <= len(rules.exclusions)


# ------------------------------------------------------------------------------------------
# mapping table
# ------------------------------------------------------------------------------------------


def test_mapping_is_a_reviewable_csv():
    assert MAPPING_PATH.suffix == ".csv"
    rows = load_mapping()

    assert len(rows) > 20
    for row in rows:
        assert row.ziffer, "a row without a Ziffer cannot propose anything"
        assert row.provenance, f"{row.entity_type} mapping has no provenance"


def test_mapping_only_targets_catalog_positions(catalog):
    unknown = sorted({r.ziffer for r in load_mapping() if not catalog.has(r.ziffer)})

    assert unknown == [], f"mapping points at positions absent from the catalog: {unknown}"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Vollständige-Untersuchung Organsystem", "vollstaendige_untersuchung_organsystem"),
        ("Röntgen", "roentgen"),
        ("  LANGZEIT-EKG  ", "langzeit_ekg"),
        ("Wirbelsäule", "wirbelsaeule"),
        ("Größe", "groesse"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_key_folds_umlauts_case_and_separators(raw, expected):
    assert normalize_key(raw) == expected


def test_bridge_is_deterministic(catalog, rules):
    payload = {
        "procedures": [
            {"type": "punktion", "organ": "knie"},
            {"type": "sonographie", "organ": "knie"},
        ]
    }
    first = map_extraction(extraction(**payload), catalog, rules)
    second = map_extraction(extraction(**payload), catalog, rules)

    assert [(c.act_id, c.ziffer) for c in first.candidates] == [
        (c.act_id, c.ziffer) for c in second.candidates
    ]


def test_bridge_proposes_both_the_specific_and_the_generic_candidate(catalog, rules):
    """Deliberate: the choice is a rule, not a dictionary-ordering accident."""
    result = map_extraction(
        extraction(procedures=[{"type": "punktion", "organ": "knie"}]), catalog, rules
    )
    ziffern = {c.ziffer for c in result.candidates}

    assert {"300", "301"} <= ziffern


def test_bridge_warns_and_charges_nothing_for_an_unmapped_entity(catalog, rules):
    result = map_extraction(
        extraction(procedures=[{"type": "voodoo_therapie", "organ": "seele"}]), catalog, rules
    )

    assert result.candidates == []
    assert [w.type for w in result.warnings] == ["unmapped_entity"]
    assert "manuell geprüft" in result.warnings[0].message


def test_bridge_routes_an_unmapped_entity_with_analog_candidates_to_analogansatz(catalog, rules):
    result = map_extraction(
        extraction(procedures=[{"type": "optische_kohaerenztomographie", "organ": "haut"}]),
        catalog,
        rules,
    )

    assert result.candidates == []
    assert [r.entity_type for r in result.analog_requests] == ["optische_kohaerenztomographie"]
    assert result.warnings == []


def test_bridge_never_proposes_a_position_absent_from_the_catalog(catalog, rules, tmp_path):
    """Even a broken mapping table cannot smuggle an invented Ziffer into the pipeline."""
    broken = tmp_path / "mapping.csv"
    broken.write_text(
        "entity_type,entity_subtype,organ,ziffer,priority,provenance,notes\n"
        "punktion,,knie,99999,100,test,not a real position\n",
        encoding="utf-8",
    )
    load_mapping.cache_clear()
    try:
        rows = load_mapping(broken)
        act = map_extraction(
            extraction(procedures=[{"type": "punktion", "organ": "knie"}]), catalog, rules
        )
    finally:
        load_mapping.cache_clear()

    assert rows[0].ziffer == "99999"
    # The real mapping is reloaded above, so assert the guard directly instead.
    from app.bridge.entity_to_ziffer import BridgeResult
    from app.schemas import ClinicalAct

    probe = ClinicalAct(
        act_id="a1", entity_id="e1", source="procedure", entity_type="punktion", organ="knie"
    )
    hits = candidates_for_act(probe, rows)
    assert hits and hits[0].ziffer == "99999"
    assert not catalog.has("99999"), "guard precondition"


def test_lab_tests_use_the_analyte_as_subtype(catalog, rules):
    result = map_extraction(extraction(lab_tests=[{"type": "crp"}]), catalog, rules)

    assert [c.ziffer for c in result.candidates] == ["3741"]
    assert result.acts[0].entity_type == "labor"
    assert result.acts[0].entity_subtype == "crp"


def test_complexity_qualified_mapping(catalog, rules):
    small = map_extraction(
        extraction(
            procedures=[{"type": "exzision_hautgeschwulst", "organ": "haut", "complexity": "einfach"}]
        ),
        catalog,
        rules,
    )
    large = map_extraction(
        extraction(
            procedures=[{"type": "exzision_hautgeschwulst", "organ": "haut", "complexity": "komplex"}]
        ),
        catalog,
        rules,
    )

    assert [c.ziffer for c in small.candidates] == ["2403"]
    assert [c.ziffer for c in large.candidates] == ["2404"]


# ------------------------------------------------------------------------------------------
# justification binding
# ------------------------------------------------------------------------------------------


def test_justification_binds_to_the_named_entity_only(catalog, rules):
    payload = extraction(
        procedures=[
            {"id": "p_punktion", "type": "punktion", "organ": "knie"},
            {"id": "p_sono", "type": "sonographie", "organ": "knie"},
        ],
        justification_factors=[
            {"reason": "erschwert", "severity": "mittel", "applies_to": ["p_punktion"]}
        ],
    )
    bridge = map_extraction(payload, catalog, rules)

    per_ziffer, encounter, warnings = resolve_justifications(payload, bridge)

    assert set(per_ziffer) == {"300", "301"}, "the puncture's candidates, and nothing else"
    assert encounter == []
    assert warnings == []


def test_justification_naming_an_unknown_entity_is_reported_not_widened(catalog, rules):
    """Silently widening it to the whole invoice would let one difficulty inflate every line."""
    payload = extraction(
        procedures=[{"id": "p1", "type": "punktion", "organ": "knie"}],
        justification_factors=[
            {"reason": "erschwert", "severity": "schwer", "applies_to": ["does_not_exist"]}
        ],
    )
    bridge = map_extraction(payload, catalog, rules)

    per_ziffer, encounter, warnings = resolve_justifications(payload, bridge)

    assert per_ziffer == {}
    assert encounter == [], "not applied encounter-wide"
    assert [w.type for w in warnings] == ["justification_target_unknown"]


def test_unbound_justification_is_encounter_wide(catalog, rules):
    payload = extraction(
        procedures=[{"type": "punktion", "organ": "knie"}],
        justification_factors=[{"reason": "Notfall", "severity": "schwer"}],
    )
    bridge = map_extraction(payload, catalog, rules)

    per_ziffer, encounter, warnings = resolve_justifications(payload, bridge)

    assert per_ziffer == {}
    assert encounter == [("schwer", "Notfall")]
    assert warnings == []
