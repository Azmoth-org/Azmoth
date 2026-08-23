#!/usr/bin/env python3
"""Build the synthetic temporal GOÄ catalogs under `data/catalogs/`.

Temporal routing — auditing a 2019 invoice against the fee schedule that was in force in 2019
rather than against today's — needs more than one catalog on disk. The official snapshot in
`data/catalogs/goae_current/` is the only *real* one we have, so the other eras are fixtures:
deliberately small, deliberately marked, and generated here rather than hand-written so that all
four stay structurally identical and only differ where an era is meant to differ.

    python scripts/make_temporal_fixtures.py            # write the four fixture catalogs
    python scripts/make_temporal_fixtures.py --check    # fail if the committed files differ

What each era is meant to prove, and the only differences between the files:

    goae_1996           Ziffer 20 does not exist yet.        Ziffer 5 = 100 Punkte
    goae_2012           Ziffer 20 exists.                    Ziffer 5 = 125 Punkte
    goae_2026_current   Ziffer 20 exists, plus Ziffer 99.    Ziffer 5 = 150 Punkte
    goae_neu_draft      identical to 2026, except that Ziffer 99 is renumbered 999

**"Base rate" is expressed in Punkte, because that is what a GOÄ catalog carries.** Money in this
engine is `Punkte × Punktwert × Steigerungsfaktor` (§ 5 Abs. 1 GOÄ) — there is no per-Ziffer euro
column to vary. The 10.0 / 12.5 / 15.0 progression the multi-catalog brief asks for is therefore
carried as 100 / 125 / 150 Punkte on Ziffer 5, which moves the recomputed line amount, the
catalog SHA-256 and the receipt hash exactly as a changed euro rate would. The Punktwert itself
stays at the statutory 5.82873 cent in every era, because it genuinely has not moved since 1996.

**These are fixtures and they say so.** Every position carries `provenance: "illustrative"`, the
file carries `"synthetic": true`, and `source.legal_status` names them as test data. The loader
logs a warning when one is loaded (`app/catalog/catalog_loader.py`), so a synthetic catalog cannot
quietly end up under a real invoice. Ziffer texts and Abschnitt letters are lifted from the real
snapshot so the fixtures read like a fee schedule; the Punktzahlen are not official in any era but
1996 and must never be quoted as such.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from app.config import CATALOGS_DIR, CATALOG_FILENAME, OVERRIDES_FILENAME  # noqa: E402

#: The real snapshot the fixtures borrow their texts and Abschnitt letters from.
REAL_CATALOG = CATALOGS_DIR / "goae_current" / CATALOG_FILENAME

#: One Ziffer per line of the fee schedule worth exercising: every § 5 band that the sample uses,
#: the Grundleistungen the PADnext examples charge, and Nummer 437 (named individually in
#: § 5 Abs. 4, so it exercises `special_factor_ziffern`).
BORROWED_ZIFFERN = (
    "1", "3", "5", "6", "7", "8", "20", "34", "50", "56", "60", "62", "70", "75", "80",
    "200", "204", "250", "252", "269", "298", "301",
    "410", "420", "435", "437", "470", "490", "491",
    "650", "651", "659", "675",
    "750", "800", "806",
    "1001", "3550", "4800", "5030", "5035",
)

#: Ziffer 5 is the one the multi-catalog tests read a "base rate" off, so its Punktzahl is pinned
#: here instead of being borrowed: 100 Punkte in 1996, scaled per era below to 125 and 150.
ANCHOR_ZIFFER = "5"
ANCHOR_PUNKTE_1996 = 100

#: A number the real GOÄ does not use, so a position that resolves can only have come from the
#: era that declares it. This is the whole point of the 99 / 999 pair.
NOVEL_2026 = {
    "ziffer": "99",
    "official_text": "Synthetische Testposition, nur im Fixture-Katalog 2026 vorhanden",
    "punkte": 300,
    "category": "B",
    "section": "B",
    "section_title": "Grundleistungen und allgemeine Leistungen",
}


class Era:
    """One catalog directory: its name, its declared version, and how it differs from 1996."""

    def __init__(
        self,
        directory: str,
        *,
        declared_version: str,
        punkte_scale: str,
        has_ziffer_20: bool,
        novel_ziffer: str | None,
        note: str,
    ) -> None:
        self.directory = directory
        self.declared_version = declared_version
        self.punkte_scale = Decimal(punkte_scale)
        self.has_ziffer_20 = has_ziffer_20
        self.novel_ziffer = novel_ziffer
        self.note = note


ERAS = (
    Era(
        "goae_1996",
        declared_version="goae_1996_synthetic_fixture_v1",
        punkte_scale="1.00",
        has_ziffer_20=False,
        novel_ziffer=None,
        note="Ziffer 20 ist in dieser Fassung nicht enthalten; Ziffer 5 steht bei 100 Punkten.",
    ),
    Era(
        "goae_2012",
        declared_version="goae_2012_synthetic_fixture_v1",
        punkte_scale="1.25",
        has_ziffer_20=True,
        novel_ziffer=None,
        note="Ziffer 20 ist enthalten; Ziffer 5 steht bei 125 Punkten.",
    ),
    Era(
        "goae_2026_current",
        declared_version="goae_2026_synthetic_fixture_v1",
        punkte_scale="1.50",
        has_ziffer_20=True,
        novel_ziffer="99",
        note="Ziffer 20 ist enthalten, Ziffer 5 steht bei 150 Punkten, Ziffer 99 nur hier.",
    ),
    Era(
        "goae_neu_draft",
        declared_version="goae_neu_draft_synthetic_fixture_v1",
        punkte_scale="1.50",
        has_ziffer_20=True,
        novel_ziffer="999",
        note="Wie 2026, aber die Testposition trägt die Nummer 999 statt 99.",
    ),
)


def _scale(punkte: int, factor: Decimal) -> int:
    """Punkte are integers in a fee schedule, so an era's scale rounds to one — half up, as § 5
    Abs. 1 Satz 4 rounds money, rather than Python's banker's rounding."""
    return int((Decimal(punkte) * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _position(entry: dict, punkte: int) -> dict:
    """A fixture position: the real legend and Abschnitt, a fabricated Punktzahl, and provenance
    that admits it. Field order matches the importer's output so a diff stays readable."""
    return {
        "ziffer": str(entry["ziffer"]),
        "official_text": entry["official_text"],
        "punkte": punkte,
        "category": entry.get("category"),
        "section": entry.get("section"),
        "section_title": entry.get("section_title"),
        "status": "active",
        # Never "official": only the Punktzahlen of the 1996 fixture happen to match the real
        # snapshot, and even there this file is not the official publication.
        "provenance": "illustrative",
        "rule_coverage": "partial",
        "text_quality": "ok",
        "minderung_exempt": bool(entry.get("minderung_exempt", False)),
        "annotations": [],
    }


def build_era(era: Era, real: dict) -> dict:
    by_ziffer = {str(z["ziffer"]): z for z in real["ziffern"]}
    missing = [z for z in BORROWED_ZIFFERN if z not in by_ziffer]
    if missing:
        raise SystemExit(
            f"{REAL_CATALOG} does not contain {missing} — adjust BORROWED_ZIFFERN or re-import "
            "the official snapshot."
        )

    ziffern: list[dict] = []
    for ziffer in BORROWED_ZIFFERN:
        if ziffer == "20" and not era.has_ziffer_20:
            continue  # the temporal difference the 1996 fixture exists to prove
        entry = by_ziffer[ziffer]
        base = ANCHOR_PUNKTE_1996 if ziffer == ANCHOR_ZIFFER else int(entry["punkte"])
        ziffern.append(_position(entry, _scale(base, era.punkte_scale)))

    if era.novel_ziffer:
        novel = dict(NOVEL_2026, ziffer=era.novel_ziffer)
        ziffern.append(_position(novel, novel["punkte"]))

    return {
        "catalog_version": era.declared_version,
        # Read by `Catalog.is_synthetic`, which is what the loader warns on.
        "synthetic": True,
        "source": {
            "name": f"Synthetischer Fixture-Katalog ({era.directory})",
            "publisher": "Govatax engine test fixtures — kein amtliches Werk",
            "url": "",
            "retrieved_at": "",
            "sha256_raw": "",
            "legal_status": (
                "SYNTHETIC TEST FIXTURE. Not the Gebührenordnung für Ärzte and not a historical "
                "edition of it. Generated by apps/engine/scripts/make_temporal_fixtures.py to "
                "exercise temporal catalog routing. Must never be used to bill or to audit a "
                "real invoice."
            ),
        },
        "rules_version": "synthetic_fixture_rules_v1",
        # Statutory and era-stable: § 5 Abs. 1 Satz 3 GOÄ has named 5.82873 cent since 1996.
        "punktwert_cent": real["punktwert_cent"],
        "punktwert_legal_basis": real["punktwert_legal_basis"],
        "rounding": real["rounding"],
        "minderung": real["minderung"],
        "minderung_legal_basis": real["minderung_legal_basis"],
        "minderung_exempt_ziffern": real["minderung_exempt_ziffern"],
        # § 5 bands are law, not data we invent per era.
        "factor_bands": real["factor_bands"],
        "special_factor_ziffern": real["special_factor_ziffern"],
        "coverage": {
            "ziffern_parsed": len(ziffern),
            "unparsed_rows": 0,
            "annotations_captured": 0,
            "exclusion_rules_auto": 0,
            "zielleistung_rules_auto": 0,
            "factor_cap_rules_auto": 0,
            "rules_needing_review": 1,
            "duplicates": 0,
            "validation_problems": 0,
            "rule_coverage": "partial",
            "note": (
                "Synthetic fixture for temporal routing tests. "
                f"{era.note} Rules are shared with the real catalog (data/rules/*.csv); only the "
                "positions differ per era."
            ),
        },
        "ziffern": ziffern,
    }


def _overrides_stub(era: Era) -> dict:
    return {
        "note": (
            "No overrides. The file exists because the loader looks for it beside every catalog; "
            f"a fixture ({era.directory}) has nothing to correct — regenerate it instead."
        ),
        "overrides": [],
    }


def _dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def build(check: bool = False) -> int:
    if not REAL_CATALOG.is_file():
        raise SystemExit(
            f"{REAL_CATALOG} is missing. Build it first:\n"
            "    python scripts/fetch_goae.py && python scripts/import_goae.py"
        )
    real = json.loads(REAL_CATALOG.read_text(encoding="utf-8"))

    stale: list[str] = []
    for era in ERAS:
        directory = CATALOGS_DIR / era.directory
        files = {
            directory / CATALOG_FILENAME: _dump(build_era(era, real)),
            directory / OVERRIDES_FILENAME: _dump(_overrides_stub(era)),
        }
        for path, text in files.items():
            if check:
                current = path.read_text(encoding="utf-8") if path.is_file() else ""
                if current != text:
                    stale.append(str(path.relative_to(CATALOGS_DIR.parent.parent)))
                continue
            directory.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        if not check:
            written = json.loads((directory / CATALOG_FILENAME).read_text(encoding="utf-8"))
            print(
                f"{era.directory:<18} {len(written['ziffern']):>3} Ziffern  "
                f"{written['catalog_version']}"
            )

    if check and stale:
        print("out of date, re-run without --check:", file=sys.stderr)
        for name in stale:
            print(f"  {name}", file=sys.stderr)
        return 1
    if check:
        print(f"{len(ERAS)} fixture catalogs are up to date")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed fixtures match this script instead of rewriting them",
    )
    sys.exit(build(check=parser.parse_args().check))
