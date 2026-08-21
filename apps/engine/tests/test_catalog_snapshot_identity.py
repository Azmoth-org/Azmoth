"""The catalog snapshot's identity, which is what backs the "real official GOÄ data" claim.

If this file were quietly replaced by a hand-written subset, every other test would still pass —
the engine does not care where its data came from. These assertions are what make the provenance
claim falsifiable.
"""

from __future__ import annotations

import json

import pytest

from app.config import CATALOG_DIR, RAW_DIR

CATALOG = CATALOG_DIR / "goae.official.json"


@pytest.fixture(scope="module")
def data() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def test_catalog_exists():
    assert CATALOG.exists()


def test_catalog_has_provenance(data):
    assert data.get("catalog_version")
    assert data.get("source")
    assert data["source"].get("url")
    assert data["source"].get("retrieved_at")
    assert data["source"].get("sha256_raw")


def test_catalog_names_the_official_publisher(data):
    """A subset typed by hand would not carry this, and could not honestly claim to."""
    source = data["source"]

    assert "gesetze-im-internet.de" in source["url"]
    assert len(source["sha256_raw"]) == 64
    assert "§ 5 UrhG" in source.get("legal_status", ""), (
        "the redistribution basis for committing this data must be recorded"
    )


def test_catalog_has_expected_size(data):
    ziffern = data.get("ziffern", [])

    # Adjust this if you intentionally re-import a different official snapshot.
    assert len(ziffern) >= 2000, "Official GOÄ catalog should contain at least 2000 Ziffern"


def test_catalog_contains_core_ziffern(data):
    by_ziffer = {str(z["ziffer"]): z for z in data["ziffern"]}

    for ziffer in ["1", "3", "5", "7", "8", "250", "5030"]:
        assert ziffer in by_ziffer, f"Missing core GOÄ Ziffer {ziffer}"


@pytest.mark.parametrize(
    "ziffer,punkte,section",
    [
        ("1", 80, "B"),
        ("3", 150, "B"),
        ("5", 80, "B"),
        ("7", 160, "B"),
        ("8", 260, "B"),
        ("250", 40, "C"),      # Blutentnahme — not a biopsy
        ("301", 160, "C"),
        ("410", 200, "C"),
        ("651", 253, "F"),
        ("659", 400, "F"),
        ("3550", 60, "M"),
        ("4800", 217, "N"),
        ("5030", 360, "O"),
    ],
)
def test_core_ziffern_keep_their_official_values(data, ziffer, punkte, section):
    """Independently verifiable values. A silently swapped catalog would move these."""
    by_ziffer = {str(z["ziffer"]): z for z in data["ziffern"]}
    entry = by_ziffer[ziffer]

    assert entry["punkte"] == punkte, f"GOÄ {ziffer} Punktzahl changed"
    assert entry["section"] == section, f"GOÄ {ziffer} Abschnitt changed"


def test_every_position_claims_official_provenance(data):
    allowed = {"official", "manual_override"}
    rogue = sorted(
        {z["ziffer"] for z in data["ziffern"] if z.get("provenance") not in allowed}
    )

    assert rogue == [], f"positions with non-official provenance: {rogue[:10]}"


def test_statutory_parameters_are_unchanged(data):
    assert data["punktwert_cent"] == "5.82873", "§ 5 Abs. 1 Satz 3 GOÄ"
    assert data["minderung"]["stationaer"] == "0.25", "§ 6a Abs. 1 Satz 1 GOÄ"
    assert data["minderung"]["belegarzt"] == "0.15", "§ 6a Abs. 1 Satz 2 GOÄ"
    assert data["rounding"]["policy"] == "ROUND_HALF_UP", "§ 5 Abs. 1 Satz 4 GOÄ"


def test_factor_bands_match_paragraph_5(data):
    """The three § 5 bands, including the two the original brief had wrong."""
    bands = data["factor_bands"]

    for letter in ("A", "E", "O"):
        assert bands[letter]["max"] == "2.5", f"§ 5 Abs. 3 covers Abschnitt {letter}"
    assert bands["M"]["max"] == "1.3", "§ 5 Abs. 4 covers Abschnitt M"
    assert bands["N"]["max"] == "3.5", (
        "Abschnitt N is NOT named in § 5 Abs. 4; capping it would undercharge histology"
    )
    assert data["special_factor_ziffern"]["437"]["max"] == "1.3", (
        "§ 5 Abs. 4 names Nummer 437 individually"
    )


def test_coverage_is_declared_partial_not_full(data):
    """Overclaiming coverage is the failure mode that matters most here."""
    assert data["coverage"]["rule_coverage"] == "partial"
    assert data["coverage"]["ziffern_parsed"] >= 2000
    assert data["coverage"]["unparsed_rows"] >= 0
    assert data["coverage"]["rules_needing_review"] > 0, (
        "a fee schedule this complex must leave residue; zero would mean the importer stopped "
        "reporting what it could not model"
    )


def test_the_raw_snapshot_manifest_matches_the_catalog(data):
    """Catalog and manifest must describe the same download."""
    manifest_path = RAW_DIR / "manifest.json"
    if not manifest_path.exists():
        pytest.skip("raw snapshot manifest not present")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["sha256"] == data["source"]["sha256_raw"], (
        "the committed catalog was not built from the committed raw snapshot"
    )
    assert manifest["source_url"] == data["source"]["url"]


def test_unparsed_rows_are_retained_beside_the_catalog():
    """"Nothing is silently dropped" is only true if the residue file is actually there."""
    unparsed = CATALOG_DIR / "unparsed_rows.json"

    assert unparsed.exists()
    payload = json.loads(unparsed.read_text(encoding="utf-8"))
    assert payload["count"] == len(payload["rows"])
    assert all(row.get("reason") for row in payload["rows"])
