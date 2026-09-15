"""Every batch-3 rule's citation, checked against the official source it claims to quote.

`scripts/validate_batch2_csvs.py::citation_verbatim` does this for the four ADR-002 families, and
its reasoning is the reason this file exists at all:

> Every row in these files asserts a legal basis, and the only thing standing between "cited" and
> "made up" is whether the quote is actually in the catalog, byte for byte.

Batch 3 cannot reuse that check, because most of its quotes are **not in the catalog**. They are
section-level *Allgemeine Bestimmungen* — paragraphs printed under a chapter heading, before that
chapter's first Ziffer — and `scripts/import_goae.py` keeps only per-Ziffer rows, so all 50 of
them were dropped on import. `scripts/extract_allgemeine_bestimmungen.py` recovers them into
`data/catalogs/goae_current/allgemeine_bestimmungen.json`, and the checks below close the loop:

  1. that artefact is **re-derived from `data/raw/goae_source.xml` here**, in this process, and
     compared to the committed file — so it is the official download's text and not something a
     previous run could have edited;
  2. every batch-3 `quote` appears verbatim in either that artefact or the catalog entry for one
     of the row's own Ziffern;
  3. every batch-3 row's Ziffern resolve in the catalog, and its `legal_basis`, `verified_at` and
     `source` are filled in.

(1) is the half that matters. Without it, "the quote is in the JSON file" would only say that two
files in this repository agree with each other.
"""

from __future__ import annotations

import csv
import json
import unicodedata
from pathlib import Path

import pytest

from app.config import CATALOG_DIR, RULES_DATA_DIR
from tests.golden.oracle import REPO_ROOT

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from extract_allgemeine_bestimmungen import build as build_provisions  # noqa: E402

PROVISIONS_FILE = CATALOG_DIR / "allgemeine_bestimmungen.json"
CATALOG_FILE = CATALOG_DIR / "goae.official.json"

#: The infix `scripts/build_batch3_rules.py` stamps into every rule id it generates.
BATCH_INFIX = "_b3_"

EXPECTED_SOURCE = "manual_verification:coverage_sprint_batch3"


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text or "").split())


def _rows(filename: str) -> list[dict]:
    path = RULES_DATA_DIR / filename
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return [r for r in csv.DictReader(handle) if BATCH_INFIX in (r.get("rule_id") or "")]


@pytest.fixture(scope="module")
def exclusions() -> list[dict]:
    return _rows("exclusions.manual.csv")


@pytest.fixture(scope="module")
def factor_caps() -> list[dict]:
    return _rows("factor_caps.csv")


@pytest.fixture(scope="module")
def haystack() -> str:
    """Every provision and every Ziffer's own text, normalised, as one searchable blob.

    One blob rather than a per-Ziffer lookup on purpose: a batch-3 quote is a *section* provision
    naming up to 182 Ziffern, and demanding that it sit in the catalog entry for each of them —
    what the batch-2 checker demands — would fail every row in the batch for a reason that is
    about the catalog's shape, not the citation's truth. The per-Ziffer version of the question
    ("does this Ziffer exist at all?") is asked separately, below.
    """
    provisions = json.loads(PROVISIONS_FILE.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    parts = [p["text"] for p in provisions["provisions"]]
    for entry in catalog["ziffern"]:
        parts.append(entry.get("official_text", ""))
        parts.extend(entry.get("annotations") or [])
    return " ||| ".join(_norm(part) for part in parts)


@pytest.fixture(scope="module")
def catalog_ziffern() -> set[str]:
    return {e["ziffer"] for e in json.loads(CATALOG_FILE.read_text(encoding="utf-8"))["ziffern"]}


def test_the_batch_actually_shipped_rows(exclusions, factor_caps):
    """A citation sweep that silently matched zero rows would pass every assertion below."""
    assert len(exclusions) > 400, f"only {len(exclusions)} batch-3 exclusion rows found"
    assert len(factor_caps) > 10, f"only {len(factor_caps)} batch-3 factor-cap rows found"


def test_the_provisions_artefact_is_what_the_raw_xml_says_it_is():
    """Re-derived from `data/raw/goae_source.xml` right here, and identical.

    This is the assertion that makes every quote check below mean something. The committed
    artefact is a *convenience*; the official download is the authority, and the two must agree
    on every byte — the extractor collapses whitespace and changes nothing else, OCR defects in
    the source included.
    """
    committed = json.loads(PROVISIONS_FILE.read_text(encoding="utf-8"))
    rebuilt = build_provisions()

    assert rebuilt["source"]["sha256_raw"] == committed["source"]["sha256_raw"]
    assert rebuilt["count"] == committed["count"]
    assert rebuilt["provisions"] == committed["provisions"], (
        "data/catalogs/goae_current/allgemeine_bestimmungen.json no longer matches what "
        "scripts/extract_allgemeine_bestimmungen.py derives from data/raw/goae_source.xml — "
        "re-run the script, and find out which of the two moved before committing the result."
    )


def test_the_raw_snapshot_still_hashes_to_its_manifest():
    """The provisions are only the official text if the file they came out of is."""
    import hashlib

    manifest = json.loads((REPO_ROOT / "data" / "raw" / "manifest.json").read_text(encoding="utf-8"))
    raw = (REPO_ROOT / "data" / "raw" / manifest["raw_file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["sha256"]


@pytest.mark.parametrize("family", ["exclusions", "factor_caps"])
def test_every_batch3_quote_is_verbatim_in_the_official_source(
    family, exclusions, factor_caps, haystack
):
    rows = exclusions if family == "exclusions" else factor_caps
    missing = [
        row["rule_id"] for row in rows if _norm(row["quote"]) not in haystack
    ]
    assert missing == [], (
        f"{len(missing)} batch-3 {family} rows quote text that is in neither "
        f"allgemeine_bestimmungen.json nor goae.official.json: {missing[:5]}"
    )


@pytest.mark.parametrize("family", ["exclusions", "factor_caps"])
def test_every_batch3_row_names_ziffern_the_catalog_has(
    family, exclusions, factor_caps, catalog_ziffern
):
    """A dangling Ziffer is a rule that can never fire and can never be reviewed."""
    rows = exclusions if family == "exclusions" else factor_caps
    columns = ("from_ziffer", "to_ziffer") if family == "exclusions" else ("ziffer",)
    dangling = sorted(
        {row[column] for row in rows for column in columns if row[column] not in catalog_ziffern}
    )
    assert dangling == [], f"batch-3 {family} reference Ziffern not in the catalog: {dangling}"


@pytest.mark.parametrize("family", ["exclusions", "factor_caps"])
def test_every_batch3_row_carries_its_provenance(family, exclusions, factor_caps):
    rows = exclusions if family == "exclusions" else factor_caps
    for row in rows:
        assert row["legal_basis"].strip(), f"{row['rule_id']} has no legal_basis"
        assert row["quote"].strip(), f"{row['rule_id']} has no quote"
        assert row["verified"] == "true", f"{row['rule_id']} is not verified"
        assert row["verified_at"].strip(), f"{row['rule_id']} has no verified_at"
        assert row["source"] == EXPECTED_SOURCE, f"{row['rule_id']} has source {row['source']!r}"


def test_the_generated_rows_are_exactly_what_the_generator_produces():
    """`build_batch3_rules.py --check`, as a test.

    Batch 3's rows are generated, not typed, and the value of that is lost the moment the CSV can
    drift from the generator: a hand-edit to row 400 would then be invisible. This asserts the two
    still agree, which also re-runs the generator's own verbatim-quote gate on every provision.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import build_batch3_rules as generator

    assert generator.main(["--check"]) == 0, (
        "data/rules/*.csv no longer matches scripts/build_batch3_rules.py — re-run it"
    )


# ==========================================================================================
# The per-Ziffer coverage classification — report §5
# ==========================================================================================


def test_the_coverage_classification_is_current():
    """`classify_batch3_coverage.py --check`, as a test.

    The classification is what turns "516 Ziffern under rule" back into three honest numbers, and
    it is derived from the rule CSVs, the catalog, the provisions artefact *and* the golden test
    module. Every one of those moves in a normal batch, so a committed classification that nobody
    regenerates is a stale honesty metric — the worst kind.
    """
    import classify_batch3_coverage

    assert classify_batch3_coverage.main(["--check"]) == 0, (
        "docs/content/batch3-coverage-classification.json is stale — re-run "
        "apps/engine/scripts/classify_batch3_coverage.py"
    )


def test_no_ziffer_is_classified_fully_verified_without_a_golden_test():
    """The label means "encoded *and* tested". Nothing else may carry it."""
    payload = json.loads(
        (REPO_ROOT / "docs" / "content" / "batch3-coverage-classification.json").read_text(
            encoding="utf-8"
        )
    )
    wrong = [
        ziffer
        for ziffer, entry in payload["ziffern"].items()
        if entry["classification"] == "FULLY_VERIFIED"
        and not (entry["golden_tested"] and not entry["not_encoded"])
    ]
    assert wrong == [], f"FULLY_VERIFIED without a golden test or with leftovers: {wrong}"


def test_every_partial_ziffer_names_the_sentence_it_is_missing():
    """"Partial" has to be a list of specific sentences, or it is a hedge."""
    payload = json.loads(
        (REPO_ROOT / "docs" / "content" / "batch3-coverage-classification.json").read_text(
            encoding="utf-8"
        )
    )
    silent = [
        ziffer
        for ziffer, entry in payload["ziffern"].items()
        if entry["classification"] == "PARTIAL"
        and not all(m.get("sentence") and m.get("source") for m in entry["not_encoded"])
    ]
    assert silent == [], f"PARTIAL Ziffern with no cited leftover: {silent}"
