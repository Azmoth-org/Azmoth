"""Importer unit tests: the parsing decisions that determine whether the catalog is trustworthy.

These test the extraction logic directly, without re-downloading anything.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.config import (
    CATALOG_DIR,
    ENGINE_DIR,
    LICENSED_DIR,
    RAW_DIR,
    REPO_ROOT,
    RULES_DATA_DIR,
)


def _load_importer():
    spec = importlib.util.spec_from_file_location(
        "import_goae", ENGINE_DIR / "scripts" / "import_goae.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def importer():
    return _load_importer()


CATALOG_ZIFFERN = {"1", "3", "5", "6", "7", "8", "650", "651", "652", "653", "422", "423", "424"}


# ------------------------------------------------------------------------------------------
# Nummern list parsing — where the first version silently lost rules
# ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "blob,expected",
    [
        ("5", ["5"]),
        ("5, 6", ["5", "6"]),
        ("5, 6 und 7", ["5", "6", "7"]),
        ("5, 6 und/oder 8", ["5", "6", "8"]),
        ("448 oder 449", ["448", "449"]),
        ("1, 3, 4, 22 und 34", ["1", "3", "4", "22", "34"]),
    ],
)
def test_plain_nummern_lists_parse(importer, blob, expected):
    """'und/oder' is three separators back to back. A character class silently fails on it, which
    is how the Nr. 5-8 exclusions — the most important rules in the demo — went missing."""
    ziffern, expanded, unresolved = importer.parse_nummern(blob, set(expected))

    assert ziffern == expected
    assert expanded == []
    assert unresolved == []


def test_range_is_expanded_only_over_positions_the_catalog_contains(importer):
    """'6 bis 8' means the positions that exist between the bounds — enumeration, not invention."""
    ziffern, expanded, unresolved = importer.parse_nummern("6 bis 8", {"6", "7", "8"})

    assert ziffern == ["6", "7", "8"]
    assert expanded == ["6-8(3)"]
    assert unresolved == []


def test_range_skips_numbers_that_are_not_real_positions(importer):
    """The gap between two bounds is not assumed to be dense."""
    ziffern, expanded, _ = importer.parse_nummern("650 bis 653", {"650", "651", "653"})

    assert ziffern == ["650", "651", "653"], "652 does not exist in this catalog subset"
    assert expanded == ["650-653(3)"]


def test_range_with_bounds_outside_the_catalog_is_left_unresolved(importer):
    """Guessing membership from bounds we cannot even locate would be invention."""
    ziffern, expanded, unresolved = importer.parse_nummern("9000 bis 9100", {"1", "3"})

    assert ziffern == []
    assert expanded == []
    assert unresolved == ["9000-9100:bounds_not_in_catalog"]


def test_mixed_list_and_range(importer):
    known = {"1", "3", "5", "6", "7", "8"}
    ziffern, expanded, _ = importer.parse_nummern("1, 3 und 5 bis 7", known)

    assert ziffern == ["1", "3", "5", "6", "7"]
    assert expanded == ["5-7(3)"]


# ------------------------------------------------------------------------------------------
# rule-sentence recognition
# ------------------------------------------------------------------------------------------


def extract(importer, sentence: str, known=CATALOG_ZIFFERN):
    return importer.extract_rules([("", sentence)], set(known))


def test_recognises_neben_sind_form(importer):
    result = extract(
        importer,
        "Neben der Leistung nach Nummer 7 sind die Leistungen nach den Nummern 5 und 6 "
        "nicht berechnungsfähig.",
    )
    edges = {(r["from_ziffer"], r["to_ziffer"]) for r in result["exclusions"]}

    assert edges == {("7", "5"), ("7", "6")}


def test_recognises_ist_neben_form_and_reverses_the_direction(importer):
    """'Die Leistung nach Nummer 7 ist neben ... 5 ... nicht berechnungsfähig' means Nr. 5
    displaces Nr. 7, not the other way round."""
    result = extract(
        importer,
        "Die Leistung nach Nummer 7 ist neben den Leistungen nach den Nummern 5, 6 und/oder 8 "
        "nicht berechnungsfähig.",
    )
    edges = {(r["from_ziffer"], r["to_ziffer"]) for r in result["exclusions"]}

    assert edges == {("5", "7"), ("6", "7"), ("8", "7")}


def test_recognises_nicht_nebeneinander_as_mutual(importer):
    result = extract(
        importer,
        "Die Leistungen nach den Nummern 422 bis 424 sind nicht nebeneinander berechnungsfähig.",
    )

    assert result["exclusions"], "no rule extracted"
    assert all(r["direction"] == "mutual" for r in result["exclusions"])
    edges = {(r["from_ziffer"], r["to_ziffer"]) for r in result["exclusions"]}
    assert ("422", "423") in edges and ("423", "422") in edges


def test_recognises_darf_nicht_berechnet_werden_form(importer):
    result = extract(
        importer,
        "Neben den Leistungen nach Nummer 422 oder 423 darf die Leistung nach Nummer 424 "
        "nicht berechnet werden.",
    )
    edges = {(r["from_ziffer"], r["to_ziffer"]) for r in result["exclusions"]}

    assert edges == {("422", "424"), ("423", "424")}


def test_recognises_bestandteil_as_zielleistung(importer):
    result = extract(
        importer,
        "Die Leistung nach Nummer 5 ist Bestandteil der Leistung nach Nummer 7.",
    )

    assert [(r["parent_ziffer"], r["child_ziffer"]) for r in result["zielleistung"]] == [("7", "5")]
    assert "§ 4 Abs. 2a" in result["zielleistung"][0]["legal_basis"]


def test_recognises_einfacher_gebuehrensatz_as_a_factor_cap(importer):
    result = extract(
        importer,
        "Der Zuschlag nach Nummer 651 ist nur mit dem einfachen Gebührensatz berechnungsfähig.",
    )

    assert [(r["ziffer"], r["max_factor"]) for r in result["factor_caps"]] == [("651", "1.0")]


def test_every_extracted_rule_is_unverified_and_quotes_its_sentence(importer):
    sentence = (
        "Neben der Leistung nach Nummer 7 sind die Leistungen nach den Nummern 5 und 6 "
        "nicht berechnungsfähig."
    )
    result = extract(importer, sentence)

    for rule in result["exclusions"]:
        assert rule["verified"] == "false", "a machine-read rule may not claim verification"
        assert rule["quote"] == sentence
        assert rule["source"].startswith("auto_extracted")
        assert rule["legal_basis"]


def test_a_billing_restriction_it_cannot_parse_is_reported_not_dropped(importer):
    result = extract(
        importer,
        "Die Leistung nach Nummer 5 ist nur bei besonderer Indikation berechnungsfähig.",
    )

    assert result["exclusions"] == []
    assert result["skipped"], "an unparsed restriction must be reported"
    assert result["skipped"][0]["kind"] == "unrecognised_billing_restriction"


def test_quantity_restrictions_are_flagged_as_not_modelled(importer):
    result = extract(
        importer, "Die Leistung nach Nummer 5 ist je Sitzung nur einmal berechnungsfähig."
    )

    kinds = {s["kind"] for s in result["skipped"]}
    assert "quantity_or_time_restriction_not_modelled" in kinds


def test_self_exclusion_is_never_emitted(importer):
    result = extract(
        importer,
        "Neben der Leistung nach Nummer 5 sind die Leistungen nach den Nummern 5 und 6 "
        "nicht berechnungsfähig.",
    )

    assert all(r["from_ziffer"] != r["to_ziffer"] for r in result["exclusions"])


# ------------------------------------------------------------------------------------------
# Abschnitt resolution — the Roman-numeral collision
# ------------------------------------------------------------------------------------------


def test_abschnitt_sequence_disambiguates_roman_numerals(importer):
    """I, V, X, L, C, D and M are all both Abschnitt letters and Roman numerals. Accepting a
    marker only when it is the next expected letter is what keeps Nummer 1 in Abschnitt B
    instead of the 'I. Allgemeine Beratungen' subsection."""
    index = importer.SectionIndex()
    index.add("B", "Grundleistungen", 1, 109)
    index.add("I", "Augenheilkunde", 1200, 1386)

    assert index.lookup("1") == ("B", "Grundleistungen")
    assert index.lookup("1210") == ("I", "Augenheilkunde")


def test_factor_bands_match_paragraph_5_of_the_source(importer):
    """Read off the official § 5 in the snapshot, not from memory."""
    assert importer.FACTOR_BANDS["A"]["max"] == "2.5"
    assert importer.FACTOR_BANDS["E"]["max"] == "2.5"
    assert importer.FACTOR_BANDS["O"]["max"] == "2.5"
    assert importer.FACTOR_BANDS["M"]["max"] == "1.3"
    assert importer.FACTOR_BANDS["N"]["max"] == "3.5", (
        "Abschnitt N is NOT named in § 5 Abs. 4; capping it at 1.3 would undercharge histology"
    )
    assert importer.SPECIAL_FACTOR_ZIFFERN["437"]["max"] == "1.3", "§ 5 Abs. 4 names Nummer 437"


def test_punktwert_and_minderung_match_the_law(importer):
    assert importer.PUNKTWERT_CENT == "5.82873"
    assert importer.MINDERUNG["stationaer"] == "0.25"
    assert importer.MINDERUNG["belegarzt"] == "0.15"
    assert "§ 5 Abs. 1 Satz 4" in importer.ROUNDING_LEGAL_BASIS


def test_normalize_text_preserves_german_characters(importer):
    assert importer.normalize_text("  Röntgen­aufnahme   der  Wirbelsäule ") == (
        "Röntgenaufnahme der Wirbelsäule"
    )


def test_ziffer_normalisation(importer):
    assert importer.normalize_ziffer("K 1") == "K1"
    assert importer.normalize_ziffer("437") == "437"


# ------------------------------------------------------------------------------------------
# artefacts on disk
# ------------------------------------------------------------------------------------------


def test_raw_snapshot_manifest_records_provenance():
    manifest = json.loads((RAW_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert "gesetze-im-internet.de" in manifest["source_url"]
    assert len(manifest["sha256"]) == 64
    assert manifest["retrieved_at"]
    assert "§ 5 UrhG" in manifest["legal_status"]


def test_import_report_records_what_needs_review():
    report = json.loads((RULES_DATA_DIR / "import_report.json").read_text(encoding="utf-8"))

    assert report["coverage"]["ziffern_parsed"] > 2000
    assert report["coverage"]["rule_coverage"] == "partial"
    assert report["rules_needing_review"], "a fee schedule this complex must leave residue"
    for entry in report["rules_needing_review"][:20]:
        assert entry["kind"] and entry["reason"] and entry["quote"]


def test_licensed_directory_is_gitignored():
    """Licensed data must never be committed.

    Repository hygiene, so it only applies to a source checkout — the container image has no
    .gitignore, and skipping is more honest there than asserting on a file that cannot exist.
    """
    path = REPO_ROOT / ".gitignore"
    if not path.exists():
        pytest.skip("no .gitignore (running from a built image, not a source checkout)")

    assert "data/licensed" in path.read_text(encoding="utf-8")


def test_no_licensed_data_is_committed():
    licensed = LICENSED_DIR
    contents = [p.name for p in licensed.iterdir()] if licensed.exists() else []

    assert [c for c in contents if c not in {".gitkeep", "README.md"}] == []
