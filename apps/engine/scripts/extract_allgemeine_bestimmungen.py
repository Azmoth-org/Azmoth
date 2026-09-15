#!/usr/bin/env python3
"""Extract the GOÄ *Allgemeine Bestimmungen* out of the raw official XML.

    python scripts/extract_allgemeine_bestimmungen.py            # rewrite the JSON artefact
    python scripts/extract_allgemeine_bestimmungen.py --check    # fail if it would change

**Why this file exists.** `scripts/import_goae.py` turns the Anlage's fee table into
`data/catalogs/goae_current/goae.official.json`: one entry per Ziffer, carrying its
`official_text` and the *Anmerkungen* printed underneath it. The section-level
*Allgemeine Bestimmungen* — the paragraphs printed under a chapter or subsection heading,
before that section's first Ziffer — belong to no single Ziffer, so the importer dropped
every one of them. All 50 of them.

That is not a cosmetic gap. The provisions hold some of the most frequently applied rules in
the whole fee schedule: that the Zuschläge A–D and E–J may only ever be billed at the single
rate, that the arthroscopy positions swallow the joint puncture beside them, that the
sonography positions 410–418 are mutually exclusive. Batch 1 of this coverage sprint scanned
only `goae.official.json` and concluded that 1,871 uncovered Ziffern "carry no annotation text
implying a mechanical rule". For a large slice of them the rule exists — it was simply never
imported.

So this script recovers the provisions, verbatim, into a committed artefact beside the catalog.
It does not touch `goae.official.json`: that file's identity is pinned
(`tests/test_catalog_snapshot_identity.py`) and its per-Ziffer shape is the wrong home for a
paragraph that governs 180 positions at once.

**Verbatim, and checkable.** The output is the source text with whitespace collapsed and nothing
else — the same single normalisation `scripts/validate_batch2_csvs.py::_norm` allows, and for the
same reason: a citation that has been tidied is no longer the source's sentence. OCR defects in
the official XML ("nd/oder", "ummern", "errechnungsfähig" in the Abschnitt M III 9 provision) are
preserved exactly. `tests/test_batch3_citations.py` re-derives this file from the raw XML and
asserts every batch-3 rule's `quote` appears in it byte for byte, which is what makes the phrase
"cited" mean something for a rule whose citation is not in the catalog.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _find_repo_root() -> Path:
    for candidate in (ENGINE_ROOT, *ENGINE_ROOT.parents):
        if (candidate / "logic").is_dir() and (candidate / "data").is_dir():
            return candidate
    return ENGINE_ROOT.parent.parent


REPO_ROOT = _find_repo_root()
RAW_XML = REPO_ROOT / "data" / "raw" / "goae_source.xml"
RAW_MANIFEST = REPO_ROOT / "data" / "raw" / "manifest.json"
OUT = REPO_ROOT / "data" / "catalogs" / "goae_current" / "allgemeine_bestimmungen.json"

#: The Anlage (Gebührenverzeichnis) is the last `<norm>` in the document and the only one that
#: carries the fee table. Located by `enbez` rather than by index so a reordered source fails
#: loudly instead of silently extracting the wrong norm.
ANLAGE_ENBEZ = "Anlage"

HEADING = re.compile(r"Allgemeine Bestimmung(?:en)?")

#: Where a provision stops and the section's first fee-table row begins. In the flattened text a
#: row reads as its number glued to its legend ("200Verband", "5480Quantitative", "K 2Zuschlag"),
#: which no German sentence produces, so this is a reliable terminator rather than a heuristic
#: about sentence content.
FIRST_ZIFFER = re.compile(r"\d{3,4}[a-z]?(?:\.[Hh]\d)?[A-ZÄÖÜ][a-zäöüß]|\b[A-JK]\s?\d?Zuschlag")

#: How much text before the heading to keep as `context`. Long enough to carry the section title
#: that precedes it ("VI.Sonographische Leistungen", "L. Chirurgie, Orthopädie"), short enough
#: that it cannot be mistaken for part of the provision.
CONTEXT_CHARS = 70


def _norm(text: str) -> str:
    """NFC + collapse whitespace. Identical to `validate_batch2_csvs._norm` on purpose."""
    return " ".join(unicodedata.normalize("NFC", text or "").split())


def anlage_text(xml_path: Path) -> str:
    #: `ET.fromstring` refuses the document's external DTD reference, and resolving it would mean
    #: a network fetch at import time. The declaration carries no entity definitions this file
    #: needs, so it is dropped rather than resolved.
    source = re.sub(r"<!DOCTYPE[^>]*>", "", xml_path.read_text(encoding="utf-8"), count=1)
    root = ET.fromstring(source)
    for norm in root.findall("norm"):
        metadata = norm.find("metadaten")
        if metadata is not None and metadata.findtext("enbez") == ANLAGE_ENBEZ:
            return _norm("".join(norm.itertext()))
    raise SystemExit(f"no <norm> with enbez={ANLAGE_ENBEZ!r} in {xml_path}")


def extract(text: str) -> list[dict]:
    out: list[dict] = []
    for index, match in enumerate(HEADING.finditer(text), start=1):
        rest = text[match.start() :]
        end = FIRST_ZIFFER.search(rest)
        body = rest[: end.start()] if end else rest
        out.append(
            {
                "id": f"ab_{index:02d}",
                "offset": match.start(),
                "context": text[max(0, match.start() - CONTEXT_CHARS) : match.start()].strip(),
                "text": body.strip(),
            }
        )
    return out


def build() -> dict:
    manifest = json.loads(RAW_MANIFEST.read_text(encoding="utf-8"))
    provisions = extract(anlage_text(RAW_XML))
    return {
        "note": (
            "Section-level Allgemeine Bestimmungen of the GOÄ Anlage (Gebührenverzeichnis), "
            "extracted verbatim from data/raw/goae_source.xml by "
            "apps/engine/scripts/extract_allgemeine_bestimmungen.py. These paragraphs govern a "
            "whole chapter or subsection and therefore belong to no single Ziffer, which is why "
            "scripts/import_goae.py does not carry them into goae.official.json. Whitespace is "
            "collapsed; nothing else is changed, OCR defects included."
        ),
        "source": {
            "url": manifest["source_url"],
            "retrieved_at": manifest["retrieved_at"],
            "sha256_raw": manifest["sha256"],
        },
        "count": len(provisions),
        "provisions": provisions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if the file would change")
    args = parser.parse_args(argv)

    payload = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current == payload:
            print(f"{OUT.name}: up to date ({json.loads(payload)['count']} provisions)")
            return 0
        print(f"{OUT.name}: STALE — re-run without --check", file=sys.stderr)
        return 1
    OUT.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    print(f"wrote {OUT} ({json.loads(payload)['count']} provisions, sha256:{digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
