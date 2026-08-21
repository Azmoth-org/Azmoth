#!/usr/bin/env python3
"""Parse an official GOÄ snapshot into the canonical catalog and rule files.

    python scripts/import_goae.py                       # from data/raw (see fetch_goae.py)
    python scripts/import_goae.py --input FILE
    python scripts/import_goae.py --illustrative        # bundled demo catalog instead

Outputs
-------
    data/catalog/goae.official.json     canonical catalog, versioned + sha256 of the source
    data/catalog/unparsed_rows.json     every row that was NOT understood, with the reason
    data/rules/exclusions.csv           auto-extracted, each with its legal quote
    data/rules/zielleistung.csv
    data/rules/factor_bands.csv
    data/rules/import_report.json

Nothing is silently dropped: a table row either becomes a Ziffer, becomes an annotation
attached to a Ziffer, or is written to ``unparsed_rows.json`` with a reason.

What is *derived* rather than read verbatim, and must be reviewed:
  * The Abschnitt (A..P) of each Ziffer, from the official Übersicht number ranges.
  * The § 5 factor band per Abschnitt (§ 5 Abs. 2/3/4 GOÄ) — a small hand-written table with
    the paragraph as legal basis, applied to Abschnitte read from the source.
  * Exclusion and Zielleistung rules parsed out of the Anmerkungen prose. These are emitted
    with ``verified=false`` and the exact sentence they came from, and under the default
    UNVERIFIED_RULE_POLICY=warn they warn instead of blocking. A human must confirm them.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE_ROOT))

from app.config import CATALOG_DIR, DATA_DIR, RAW_DIR, RULES_DATA_DIR  # noqa: E402

#: Data lives in the monorepo's data/ directory, not inside this app. Resolved through
#: app.config so LOGIC_DIR / DATA_DIR overrides apply here exactly as they do to the service.
RULES_DIR = RULES_DATA_DIR

CATALOG_PATH = CATALOG_DIR / "goae.official.json"
UNPARSED_PATH = CATALOG_DIR / "unparsed_rows.json"
OVERRIDES_PATH = CATALOG_DIR / "overrides.json"
REPORT_PATH = RULES_DIR / "import_report.json"

# ==========================================================================================
# § 5 GOÄ factor bands, keyed by Abschnitt.
# ==========================================================================================
# This is the one piece of legal knowledge that is hand-encoded rather than parsed, because it
# lives in the paragraph text rather than in the fee table. The values below were read off the
# official § 5 in the very snapshot being imported — not from memory — and each carries the
# Absatz it comes from. `scripts/verify_factor_bands.py` re-checks them against the source.
#
#   § 5 Abs. 1/2  1.0–3.5, Schwellenwert 2.3   (the general case)
#   § 5 Abs. 3    1.0–2.5, Schwellenwert 1.8   Abschnitte A, E and O
#   § 5 Abs. 4    1.0–1.3, Schwellenwert 1.15  Abschnitt M *and Nummer 437*
#
# Note that Abschnitt N (Histologie/Zytologie) is NOT in Abs. 4 and therefore takes the
# general band. Getting that wrong would cap every histology line at 1.3 and undercharge it.
GENERAL_BAND = {"threshold": "2.3", "max": "3.5", "legal_basis": "§ 5 Abs. 1, 2 GOÄ"}
REDUCED_BAND = {"threshold": "1.8", "max": "2.5", "legal_basis": "§ 5 Abs. 3 GOÄ"}
LAB_BAND = {"threshold": "1.15", "max": "1.3", "legal_basis": "§ 5 Abs. 4 GOÄ"}

FACTOR_BANDS: dict[str, dict[str, str]] = {
    "A": REDUCED_BAND,
    "E": REDUCED_BAND,
    "O": REDUCED_BAND,
    "M": LAB_BAND,
    **{letter: GENERAL_BAND for letter in "BCDFGHIJKLNP"},
}

#: § 5 Abs. 4 names one individual Ziffer alongside Abschnitt M.
SPECIAL_FACTOR_ZIFFERN: dict[str, dict[str, str]] = {"437": LAB_BAND}

#: § 5 Abs. 1 Satz 3 GOÄ. A Decimal string, never a float.
PUNKTWERT_CENT = "5.82873"

#: § 5 Abs. 1 Satz 4 GOÄ prescribes the rounding: fractions below 0.5 down, 0.5 and above up.
#: That is ROUND_HALF_UP at cent granularity, and it is law rather than a house convention.
ROUNDING_LEGAL_BASIS = "§ 5 Abs. 1 Satz 4 GOÄ (ROUND_HALF_UP auf Cent)"

MINDERUNG = {
    "ambulant": "0",
    "stationaer": "0.25",  # § 6a Abs. 1 Satz 1 GOÄ
    "belegarzt": "0.15",  # § 6a Abs. 1 Satz 2 GOÄ
}

#: § 6a Abs. 1 Satz 3 GOÄ exempts the Zuschlag nach Buchstabe J in Abschnitt B V from the
#: Minderung. Tracked per Ziffer so the money layer can honour it.
MINDERUNG_EXEMPT_ZIFFERN = {"J"}

# ==========================================================================================
# parsing helpers
# ==========================================================================================

#: A Ziffer in the Gebührenverzeichnis: digits, optionally with a trailing letter ("437a"),
#: or a Zuschlag letter ("A", "K 1", "C 2").
ZIFFER_RE = re.compile(r"^(?:\d{1,4}[a-z]?|[A-Z](?:\s?\d)?)$")
PUNKTE_RE = re.compile(r"^\d{1,5}$")
#: "1 bis 15", "A bis K 2" — Übersicht ranges, not Ziffern.
RANGE_RE = re.compile(r"\bbis\b")


def normalize_text(value: str) -> str:
    """Collapse whitespace and normalise unicode without destroying German characters."""
    value = unicodedata.normalize("NFC", value)
    value = value.replace("­", "")  # soft hyphen
    value = value.replace("–", "-").replace("—", "-")
    return " ".join(value.split()).strip()


def cell_text(element: ET.Element) -> str:
    return normalize_text("".join(element.itertext()))


def normalize_ziffer(raw: str) -> str:
    """'K 1' -> 'K1'. Keeps Ziffern usable as identifiers in Datalog and ASP."""
    return re.sub(r"\s+", "", raw)


#: The Abschnitte of the Gebührenverzeichnis, in the order the law prints them.
ABSCHNITT_SEQUENCE = "ABCDEFGHIJKLMNOP"


class SectionIndex:
    """Maps a Ziffer to its Abschnitt, using the ranges in the official Übersicht."""

    def __init__(self) -> None:
        self.ranges: list[tuple[str, str, int, int]] = []  # (letter, title, lo, hi)

    def add(self, letter: str, title: str, lo: int, hi: int) -> None:
        self.ranges.append((letter, title, lo, hi))

    def lookup(self, ziffer: str) -> tuple[str | None, str | None]:
        """Numeric Ziffern resolve by range. Letter Ziffern (Zuschläge) cannot — the caller
        falls back to the Abschnitt the Zuschlag is printed under."""
        match = re.match(r"^(\d+)", ziffer)
        if not match:
            return None, None
        number = int(match.group(1))
        for letter, title, lo, hi in self.ranges:
            if lo <= number <= hi:
                return letter, title
        return None, None


def parse_section_index(root: ET.Element) -> SectionIndex:
    """Read Abschnitt letters and their number ranges out of the official Übersicht.

    The hard part is that the Übersicht interleaves Abschnitt letters (A., B., C., ...) with
    Roman-numeral subsections (I., II., ..., V., ..., X.), and the two alphabets overlap: I, V,
    X, L, C, D and M are all both valid Abschnitt letters and valid Roman numerals. Matching on
    shape alone assigns Nummer 1 to "Abschnitt I" (the subsection "I. Allgemeine Beratungen")
    instead of Abschnitt B, which then gives it the wrong § 5 factor band.

    The disambiguator is order: Abschnitte appear exactly once each, in alphabetical sequence.
    A marker is only accepted as an Abschnitt when it is the next letter still expected, so the
    repeated "I." subsection headers are rejected while Abschnitt I (Augenheilkunde) is not.
    """
    index = SectionIndex()
    expected = 0  # position in ABSCHNITT_SEQUENCE

    for table in root.findall(".//table"):
        rows = table.findall(".//row")
        header = [cell_text(c) for c in rows[0].findall("entry")] if rows else []
        if "Übersicht" not in " ".join(header):
            continue
        for row in rows:
            if expected >= len(ABSCHNITT_SEQUENCE):
                break
            cells = [cell_text(c) for c in row.findall("entry")]
            wanted = ABSCHNITT_SEQUENCE[expected]
            markers = [c.rstrip(".") for c in cells if c.endswith(".") and len(c.rstrip(".")) == 1]
            if wanted not in markers:
                continue

            bounds = None
            for candidate in (c for c in cells if RANGE_RE.search(c)):
                found = re.findall(r"\d+", candidate)
                if len(found) >= 2:
                    bounds = (int(found[0]), int(found[-1]))
                    break
            title = next(
                (c for c in cells if len(c) > 4 and not c[0].isdigit() and c.rstrip(".") != wanted),
                "",
            )
            if bounds:
                index.add(wanted, title, bounds[0], bounds[1])
            else:
                # Abschnitt A (Gebühren in besonderen Fällen) carries no Nummernbereich.
                index.add(wanted, title, -1, -1)
            expected += 1
    return index


def looks_like_fee_table(rows: list[ET.Element]) -> bool:
    """A fee table has at least one row shaped like <Ziffer, prose, Punktzahl, ...>."""
    for row in rows[:12]:
        cells = [cell_text(c) for c in row.findall("entry")]
        cells = [c for c in cells if c]
        if len(cells) < 3:
            continue
        if ZIFFER_RE.match(cells[0]) and not RANGE_RE.search(cells[0]):
            if any(PUNKTE_RE.match(c) for c in cells[1:]):
                return True
    return False


# ==========================================================================================
# rule extraction from the Anmerkungen
# ==========================================================================================

# A list of Nummern as the GOÄ writes them: "5, 6 und/oder 8", "448 oder 449",
# "5300 bis 5313", "538, 560, 561 und 562". Written as an explicit alternation of numbers and
# separators rather than a loose character class — a character class silently fails on
# "und/oder" (no '/', no 'o', 'e', 'r'), which is exactly how the Nr. 5-8 exclusions, the
# single most important rules in the demo, went missing in the first version.
_NUM = r"\d{1,4}[a-z]?"
_SEP = r"(?:\s*(?:,|/|;|\bund\b|\boder\b|\bsowie\b|\bbis\b)\s*)"
#: One *or more* separators between numbers. "und/oder" is three separators back to back
#: ("und", "/", "oder"); allowing only one silently dropped every rule phrased that way,
#: which is how the Nr. 5-8 exclusions disappeared.
NUM_LIST = rf"{_NUM}(?:{_SEP}+{_NUM})*"

_LEISTUNG = r"(?:Leistung(?:en)?|Zuschlag|Zuschläge|Pauschalgebühr|Ergänzungsleistungen)"
_NUMMER = r"(?:Nummer|Nummern|den\s+Nummern|der\s+Nummer)"

#: "Neben der/einer Leistung nach Nummer X sind die Leistungen nach den Nummern Y nicht
#: berechnungsfähig."
EXCLUSION_RE = re.compile(
    rf"Neben\s+(?:der|den|einer|einem)\s+{_LEISTUNG}\s+nach\s+{_NUMMER}\s+"
    rf"(?P<anchors>{NUM_LIST})\s+"
    rf"(?:ist|sind)\s+(?:die\s+|der\s+)?{_LEISTUNG}\s+nach\s+{_NUMMER}\s+"
    rf"(?P<targets>{NUM_LIST})\s+nicht\s+berechnungsf[äa]hig",
    re.IGNORECASE,
)

#: "Die Leistung nach Nummer X ist neben den Leistungen nach den Nummern Y nicht
#: berechnungsfähig." — the same rule with the roles swapped.
EXCLUSION_REVERSED_RE = re.compile(
    rf"(?:Die|Der)\s+{_LEISTUNG}\s+nach\s+{_NUMMER}\s+(?P<targets>{NUM_LIST})\s+"
    rf"(?:ist|sind)\s+neben\s+(?:der|den|einer|einem)\s+{_LEISTUNG}\s+nach\s+{_NUMMER}\s+"
    rf"(?P<anchors>{NUM_LIST})\s+nicht\s+berechnungsf[äa]hig",
    re.IGNORECASE,
)

#: "Neben den Leistungen nach Nummer X darf die Leistung nach Nummer Y nicht berechnet werden."
EXCLUSION_DARF_RE = re.compile(
    rf"Neben\s+(?:der|den|einer|einem)\s+{_LEISTUNG}\s+nach\s+{_NUMMER}\s+"
    rf"(?P<anchors>{NUM_LIST})\s+darf\s+(?:die|der)\s+{_LEISTUNG}\s+nach\s+{_NUMMER}\s+"
    rf"(?P<targets>{NUM_LIST})\s+nicht\s+berechnet\s+werden",
    re.IGNORECASE,
)

#: "Die Leistung nach Nummer X darf anstelle oder neben einer Leistung nach Nummer Y nicht
#: berechnet werden."
EXCLUSION_DARF_REVERSED_RE = re.compile(
    rf"(?:Die|Der)\s+{_LEISTUNG}\s+nach\s+{_NUMMER}\s+(?P<targets>{NUM_LIST})\s+darf\s+"
    rf"(?:anstelle\s+(?:oder|und)\s+)?neben\s+(?:der|den|einer|einem)\s+{_LEISTUNG}\s+nach\s+"
    rf"{_NUMMER}\s+(?P<anchors>{NUM_LIST})\s+nicht\s+berechnet\s+werden",
    re.IGNORECASE,
)

#: "Die Leistungen nach den Nummern X, Y und Z sind nicht nebeneinander berechnungsfähig."
#: Every pair in the list excludes every other — a genuinely MUTUAL rule, which the engine
#: must route to the solver rather than resolve by negation.
MUTUAL_RE = re.compile(
    rf"(?:Die|Der)\s+{_LEISTUNG}\s+nach\s+{_NUMMER}\s+(?P<members>{NUM_LIST})\s+"
    rf"(?:sind|ist|dürfen|darf)\s+nicht\s+nebeneinander\s+"
    rf"(?:berechnungsf[äa]hig|berechnet\s+werden)",
    re.IGNORECASE,
)

#: "Die Leistung nach Nummer X ist Bestandteil der Leistung nach Nummer Y." (§ 4 Abs. 2a)
ZIELLEISTUNG_RE = re.compile(
    rf"(?:Die|Der)\s+{_LEISTUNG}\s+nach\s+{_NUMMER}\s+(?P<children>{NUM_LIST})\s+"
    rf"(?:ist|sind)\s+Bestandteil\s+(?:der|des)\s+{_LEISTUNG}\s+nach\s+{_NUMMER}\s+"
    rf"(?P<parents>{NUM_LIST})",
    re.IGNORECASE,
)

#: "Der Zuschlag nach Nummer X ist nur mit dem einfachen Gebührensatz berechnungsfähig."
#: A hard factor cap of 1.0 on individual Ziffern, independent of the § 5 band.
FACTOR_CAP_RE = re.compile(
    rf"(?:Die|Der)\s+{_LEISTUNG}\s+nach\s+{_NUMMER}\s+(?P<members>{NUM_LIST})\s+"
    rf"(?:ist|sind|kann|können)\s+nur\s+mit\s+dem\s+einfachen\s+Gebührensatz\s+"
    rf"berechnungsf[äa]hig",
    re.IGNORECASE,
)

#: Restrictions the engine does not model (quantities, per-session, per-day limits). Detected
#: so they can be reported as known gaps instead of looking like full coverage.
QUANTITY_HINT_RE = re.compile(
    r"(?:nur\s+einmal|je\s+Sitzung|je\s+Tag|zweimal|mehrfach|nicht\s+mehrfach|"
    r"je\s+Behandlungsfall|innerhalb\s+eines\s+Zeitraums)",
    re.IGNORECASE,
)


#: Splits a Nummern blob into numbers and the separators between them, so that "6 bis 8" can be
#: told apart from "6 und 8".
_BLOB_TOKEN_RE = re.compile(rf"(?P<num>{_NUM})|(?P<sep>,|/|;|\bund\b|\boder\b|\bsowie\b|\bbis\b)")


def parse_nummern(blob: str, known: set[str]) -> tuple[list[str], list[str], list[str]]:
    """Turn a Nummern blob into concrete Ziffern.

    Returns ``(ziffern, expanded_ranges, unresolved_ranges)``.

    "6 bis 8" is expanded by *enumerating the Ziffern the catalog actually contains* between the
    two bounds — never by generating numbers. That distinction matters: enumerating catalog
    members inside stated bounds is reading the law, whereas emitting 5301..5312 because the law
    said "5300 bis 5313" would be inventing codes. A range whose bounds are not themselves in
    the catalog is left unresolved and reported, because then the intended membership is a
    guess.
    """
    tokens: list[tuple[str, str]] = [
        ("num", m.group("num")) if m.group("num") else ("sep", m.group("sep").lower())
        for m in _BLOB_TOKEN_RE.finditer(blob)
    ]

    numeric_known = sorted(
        (int(z) for z in known if z.isdigit()),
    )

    ziffern: list[str] = []
    expanded: list[str] = []
    unresolved: list[str] = []

    index = 0
    while index < len(tokens):
        kind, value = tokens[index]
        if kind != "num":
            index += 1
            continue

        # Look ahead for "<num> bis <num>".
        lookahead = index + 1
        saw_bis = False
        while lookahead < len(tokens) and tokens[lookahead][0] == "sep":
            if tokens[lookahead][1] == "bis":
                saw_bis = True
            lookahead += 1

        if saw_bis and lookahead < len(tokens) and tokens[lookahead][0] == "num":
            low_raw, high_raw = value, tokens[lookahead][1]
            if low_raw.isdigit() and high_raw.isdigit() and low_raw in known and high_raw in known:
                low, high = int(low_raw), int(high_raw)
                if low <= high:
                    members = [str(n) for n in numeric_known if low <= n <= high]
                    ziffern.extend(members)
                    expanded.append(f"{low_raw}-{high_raw}({len(members)})")
                else:
                    unresolved.append(f"{low_raw}-{high_raw}:inverted")
            else:
                unresolved.append(f"{low_raw}-{high_raw}:bounds_not_in_catalog")
            index = lookahead + 1
            continue

        ziffern.append(value)
        index += 1

    # Preserve order, drop duplicates.
    seen: set[str] = set()
    deduped = [z for z in ziffern if not (z in seen or seen.add(z))]
    return deduped, expanded, unresolved


def split_sentences(text: str) -> list[str]:
    """Split on sentence ends, but not on the '.' inside 'Nummer 5.' style references."""
    parts = re.split(r"(?<=[.;])\s+(?=[A-ZÄÖÜ])", text)
    return [p.strip() for p in parts if p.strip()]


def extract_rules(
    sentences: list[tuple[str, str]], known: set[str]
) -> dict[str, list[dict]]:
    """Pull billing rules out of GOÄ prose.

    ``sentences`` is a list of ``(owner, sentence)``; owner is the Ziffer the sentence was
    printed under, or "" for Allgemeine Bestimmungen that stand on their own. Every rule keeps
    the sentence it came from so a reviewer can check it against the law without re-reading the
    source, and every rule is marked unverified.
    """
    exclusions: list[dict] = []
    zielleistung: list[dict] = []
    factor_caps: list[dict] = []
    skipped: list[dict] = []
    today = datetime.now(timezone.utc).date().isoformat()

    def basis(owner: str, prefix: str = "") -> str:
        where = f"Anmerkung zu Nummer {owner}" if owner else "Allgemeine Bestimmung"
        return f"{prefix}GOÄ {where}".strip()

    def note_skip(owner: str, kind: str, reason: str, sentence: str) -> None:
        skipped.append(
            {"owner_ziffer": owner, "kind": kind, "reason": reason, "quote": sentence}
        )

    def add_exclusions(owner: str, sentence: str, anchors_raw: str, targets_raw: str, pattern: str) -> None:
        anchors, a_expanded, a_unresolved = parse_nummern(anchors_raw, known)
        targets, t_expanded, t_unresolved = parse_nummern(targets_raw, known)
        if a_unresolved or t_unresolved:
            note_skip(
                owner,
                "exclusion_range_unresolved",
                "names a Nummern range whose bounds are not both in the catalog: "
                + ", ".join(a_unresolved + t_unresolved),
                sentence,
            )
        if not anchors or not targets:
            return
        expanded_note = ";".join(a_expanded + t_expanded)
        for anchor in anchors:
            for target in targets:
                if anchor == target:
                    continue
                exclusions.append(
                    {
                        "rule_id": f"excl_auto_{anchor}_{target}",
                        "from_ziffer": anchor,
                        "to_ziffer": target,
                        "direction": "one_way",
                        "legal_basis": basis(owner),
                        "quote": sentence,
                        "verified": "false",
                        "verified_at": "",
                        "source": f"auto_extracted:{pattern}"
                        + (f":range[{expanded_note}]" if expanded_note else ""),
                        "extracted_at": today,
                    }
                )

    for owner, sentence in sentences:
        matched = False

        for pattern_name, pattern in (
            ("neben_sind", EXCLUSION_RE),
            ("ist_neben", EXCLUSION_REVERSED_RE),
            ("neben_darf", EXCLUSION_DARF_RE),
            ("darf_neben", EXCLUSION_DARF_REVERSED_RE),
        ):
            for match in pattern.finditer(sentence):
                matched = True
                add_exclusions(
                    owner, sentence, match.group("anchors"), match.group("targets"), pattern_name
                )

        # "… sind nicht nebeneinander berechnungsfähig" — every listed pair, both directions.
        for match in MUTUAL_RE.finditer(sentence):
            matched = True
            members, expanded, unresolved = parse_nummern(match.group("members"), known)
            if unresolved:
                note_skip(
                    owner, "mutual_range_unresolved",
                    "range bounds not both in catalog: " + ", ".join(unresolved), sentence,
                )
            if len(members) < 2:
                continue
            for a in members:
                for b in members:
                    if a == b:
                        continue
                    exclusions.append(
                        {
                            "rule_id": f"excl_auto_{a}_{b}",
                            "from_ziffer": a,
                            "to_ziffer": b,
                            "direction": "mutual",
                            "legal_basis": basis(owner),
                            "quote": sentence,
                            "verified": "false",
                            "verified_at": "",
                            "source": "auto_extracted:nicht_nebeneinander"
                            + (f":range[{';'.join(expanded)}]" if expanded else ""),
                            "extracted_at": today,
                        }
                    )

        for match in ZIELLEISTUNG_RE.finditer(sentence):
            matched = True
            children, _c_exp, c_unresolved = parse_nummern(match.group("children"), known)
            parents, _p_exp, p_unresolved = parse_nummern(match.group("parents"), known)
            if c_unresolved or p_unresolved:
                note_skip(
                    owner, "zielleistung_range_unresolved",
                    "range bounds not both in catalog: " + ", ".join(c_unresolved + p_unresolved),
                    sentence,
                )
            if not children or not parents:
                continue
            for parent in parents:
                for child in children:
                    if parent == child:
                        continue
                    zielleistung.append(
                        {
                            "rule_id": f"ziel_auto_{parent}_{child}",
                            "parent_ziffer": parent,
                            "child_ziffer": child,
                            "legal_basis": basis(owner, "§ 4 Abs. 2a GOÄ i.V.m. "),
                            "quote": sentence,
                            "verified": "false",
                            "verified_at": "",
                            "source": "auto_extracted:bestandteil",
                            "extracted_at": today,
                        }
                    )

        for match in FACTOR_CAP_RE.finditer(sentence):
            matched = True
            members, _exp, unresolved = parse_nummern(match.group("members"), known)
            if unresolved:
                note_skip(
                    owner, "factor_cap_range_unresolved",
                    "range bounds not both in catalog: " + ", ".join(unresolved), sentence,
                )
            if not members:
                continue
            for ziffer in members:
                factor_caps.append(
                    {
                        "rule_id": f"cap_auto_{ziffer}",
                        "ziffer": ziffer,
                        "max_factor": "1.0",
                        "legal_basis": basis(owner),
                        "quote": sentence,
                        "verified": "false",
                        "verified_at": "",
                        "source": "auto_extracted:einfacher_gebuehrensatz",
                        "extracted_at": today,
                    }
                )

        if not matched:
            lowered = sentence.lower()
            if QUANTITY_HINT_RE.search(sentence) and (
                "berechnungsf" in lowered or "berechnet" in lowered
            ):
                note_skip(
                    owner,
                    "quantity_or_time_restriction_not_modelled",
                    "restricts how often a service may be charged; the engine models no "
                    "quantity or time dimension yet",
                    sentence,
                )
            elif "berechnungsf" in lowered or "nicht berechnet werden" in lowered:
                note_skip(
                    owner,
                    "unrecognised_billing_restriction",
                    "sentence constrains billing but matched no known pattern",
                    sentence,
                )

    return {
        "exclusions": exclusions,
        "zielleistung": zielleistung,
        "factor_caps": factor_caps,
        "skipped": skipped,
    }


def dedupe(rows: list[dict], key: tuple[str, ...]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for row in rows:
        identity = tuple(row[k] for k in key)
        if identity in seen:
            continue
        seen.add(identity)
        out.append(row)
    return out


# ==========================================================================================
# the import
# ==========================================================================================


def import_official(xml_path: Path, source_meta: dict) -> dict:
    root = ET.parse(xml_path).getroot()
    sections = parse_section_index(root)

    ziffern: dict[str, dict] = {}
    annotations: list[tuple[str, str]] = []
    unparsed: list[dict] = []
    duplicates: list[dict] = []
    #: The Abschnitt most recently resolved from a numeric Ziffer, used to place Zuschläge.
    last_section: tuple[str | None, str | None] = (None, None)

    for table_index, table in enumerate(root.findall(".//table")):
        rows = table.findall(".//row")
        if not rows or not looks_like_fee_table(rows):
            continue

        current: str | None = None
        for row_index, row in enumerate(rows):  # noqa: B007
            raw_cells = [cell_text(c) for c in row.findall("entry")]
            cells = [c for c in raw_cells if c]
            if not cells:
                continue  # a purely decorative spacer row

            head = cells[0]

            # -- a Ziffer row -----------------------------------------------------------
            if ZIFFER_RE.match(head) and not RANGE_RE.search(head):
                punkte = next((c for c in cells[1:] if PUNKTE_RE.match(c)), None)
                text_cells = [
                    c for c in cells[1:] if not PUNKTE_RE.match(c) and not re.match(r"^[\d.,]+$", c)
                ]
                official_text = max(text_cells, key=len) if text_cells else ""

                if punkte is None or not official_text:
                    unparsed.append(
                        {
                            "table": table_index,
                            "row": row_index,
                            "cells": raw_cells,
                            "reason": "row starts with a Ziffer but has no Punktzahl"
                            if punkte is None
                            else "row starts with a Ziffer but has no service text",
                        }
                    )
                    continue

                ziffer = normalize_ziffer(head)
                letter, section_title = sections.lookup(ziffer)
                if letter is None:
                    # A Zuschlag ("A", "K1", ...) has no number to range-match on. It belongs to
                    # the Abschnitt it is printed under, which is the last one we resolved.
                    letter, section_title = last_section
                category = letter if letter in FACTOR_BANDS else None
                if ziffer in SPECIAL_FACTOR_ZIFFERN:
                    # § 5 Abs. 4 names Nummer 437 individually, regardless of its Abschnitt.
                    category = "M"

                if ziffer in ziffern:
                    duplicates.append(
                        {"ziffer": ziffer, "existing": ziffern[ziffer]["official_text"][:80],
                         "duplicate": official_text[:80], "table": table_index, "row": row_index}
                    )
                    current = ziffer
                    continue

                # A legend split across table rows leaves a fragment behind ("jeweils in zwei
                # Ebenen"). Flagged rather than shipped as if it were the full legend.
                truncated = official_text[:1].islower() or len(official_text) < 12

                ziffern[ziffer] = {
                    "ziffer": ziffer,
                    "official_text": official_text,
                    "punkte": int(punkte),
                    "category": category,
                    "section": letter,
                    "section_title": section_title,
                    "status": "active",
                    "provenance": "official",
                    "rule_coverage": "partial",
                    "text_quality": "possibly_truncated" if truncated else "ok",
                    "minderung_exempt": ziffer in MINDERUNG_EXEMPT_ZIFFERN,
                    "annotations": [],
                }
                if re.match(r"^\d", ziffer) and letter:
                    last_section = (letter, section_title)
                current = ziffer
                continue

            # -- an annotation row belonging to the Ziffer above it ----------------------
            prose = max(cells, key=len)
            if current and len(prose) > 20:
                ziffern[current]["annotations"].append(prose)
                annotations.append((current, prose))
            else:
                unparsed.append(
                    {
                        "table": table_index,
                        "row": row_index,
                        "cells": raw_cells,
                        "reason": "annotation text with no preceding Ziffer"
                        if not current
                        else "row too short to classify",
                    }
                )

    # -- validation --------------------------------------------------------------------
    problems: list[dict] = []
    for ziffer, entry in list(ziffern.items()):
        if entry["punkte"] <= 0:
            problems.append({"ziffer": ziffer, "problem": "punkte is not positive"})
            entry["status"] = "invalid"
        if not entry["official_text"]:
            problems.append({"ziffer": ziffer, "problem": "official_text is empty"})
            entry["status"] = "invalid"
        if entry["category"] is None:
            problems.append(
                {"ziffer": ziffer, "problem": "no Abschnitt could be resolved; no factor band"}
            )

    # Rules do not live only in per-Ziffer annotations. "Allgemeine Bestimmungen" sit in <P>
    # paragraphs outside any table, and that is where several of the most important exclusions
    # are stated. Every sentence in the document is offered to the extractor; each rule sentence
    # names its own Nummern, so attribution to an owner Ziffer is a convenience, not a
    # requirement.
    sentences: list[tuple[str, str]] = []
    seen_sentences: set[str] = set()

    def offer(owner: str, text: str) -> None:
        for sentence in split_sentences(text):
            if sentence not in seen_sentences:
                seen_sentences.add(sentence)
                sentences.append((owner, sentence))

    for owner, text in annotations:
        offer(owner, text)

    # Every table cell that holds prose. Cell-level text is clean; the <P> that wraps a table
    # flattens the whole section into one string ("...Fernsprecher -809,122Ausstellung..."),
    # running Punktzahlen into Nummern, which would manufacture rules out of typography.
    for entry in root.findall(".//entry"):
        text = normalize_text("".join(entry.itertext()))
        if len(text) > 25 and re.search(r"[A-Za-zÄÖÜäöüß]{4}", text):
            offer("", text)

    # Allgemeine Bestimmungen that genuinely stand outside a table.
    for tag in ("P", "LA", "DD"):
        for element in root.findall(f".//{tag}"):
            if element.find(".//table") is not None:
                continue  # a wrapper around a table, not prose of its own
            offer("", normalize_text("".join(element.itertext())))

    extracted = extract_rules(sentences, set(ziffern))
    exclusions = extracted["exclusions"]
    zielleistung = extracted["zielleistung"]
    factor_caps = extracted["factor_caps"]
    skipped_rules = extracted["skipped"]

    # Rules may only reference Ziffern that actually exist in the catalog.
    def known(z: str) -> bool:
        return z in ziffern

    dangling = [r for r in exclusions if not known(r["from_ziffer"]) or not known(r["to_ziffer"])]
    exclusions = [r for r in exclusions if known(r["from_ziffer"]) and known(r["to_ziffer"])]
    dangling += [
        r for r in zielleistung if not known(r["parent_ziffer"]) or not known(r["child_ziffer"])
    ]
    zielleistung = [
        r for r in zielleistung if known(r["parent_ziffer"]) and known(r["child_ziffer"])
    ]
    dangling += [r for r in factor_caps if not known(r["ziffer"])]
    factor_caps = [r for r in factor_caps if known(r["ziffer"])]
    for rule in dangling:
        skipped_rules.append(
            {
                "owner_ziffer": rule.get("legal_basis", ""),
                "kind": "dangling_reference",
                "reason": "rule references a Ziffer that is not in the parsed catalog",
                "quote": rule.get("quote", ""),
            }
        )

    exclusions = dedupe(exclusions, ("from_ziffer", "to_ziffer"))
    zielleistung = dedupe(zielleistung, ("parent_ziffer", "child_ziffer"))
    factor_caps = dedupe(factor_caps, ("ziffer",))

    # An exclusion is mutual whenever the reverse edge also exists, whether because the law
    # said "nicht nebeneinander" or because two separate annotations each name the other. The
    # engine treats mutual pairs completely differently from one-way ones, so the distinction is
    # resolved here, in the data, rather than being rediscovered at query time.
    edges = {(r["from_ziffer"], r["to_ziffer"]) for r in exclusions}
    for rule in exclusions:
        if (rule["to_ziffer"], rule["from_ziffer"]) in edges:
            rule["direction"] = "mutual"

    retrieved = source_meta.get("retrieved_at", datetime.now(timezone.utc).isoformat())
    snapshot_date = retrieved[:10]

    catalog = {
        "catalog_version": f"goae_official_snapshot_{snapshot_date}",
        "source": {
            "name": source_meta.get("source_name", "Official GOÄ fee schedule"),
            "publisher": source_meta.get("publisher", ""),
            "url": source_meta.get("source_url", ""),
            "retrieved_at": retrieved,
            "sha256_raw": source_meta.get("sha256", ""),
            "legal_status": source_meta.get("legal_status", ""),
        },
        "rules_version": f"auto_extracted_{snapshot_date}",
        "punktwert_cent": PUNKTWERT_CENT,
        "punktwert_legal_basis": "§ 5 Abs. 1 Satz 3 GOÄ",
        "rounding": {"policy": "ROUND_HALF_UP", "unit": "cent", "legal_basis": ROUNDING_LEGAL_BASIS},
        "minderung": MINDERUNG,
        "minderung_legal_basis": "§ 6a Abs. 1 GOÄ",
        "minderung_exempt_ziffern": sorted(MINDERUNG_EXEMPT_ZIFFERN),
        "factor_bands": {
            letter: {"threshold": band["threshold"], "max": band["max"],
                     "legal_basis": band["legal_basis"]}
            for letter, band in sorted(FACTOR_BANDS.items())
        },
        "special_factor_ziffern": {
            ziffer: {"threshold": band["threshold"], "max": band["max"],
                     "legal_basis": band["legal_basis"]}
            for ziffer, band in SPECIAL_FACTOR_ZIFFERN.items()
        },
        "coverage": {
            "ziffern_parsed": len(ziffern),
            "unparsed_rows": len(unparsed),
            "annotations_captured": len(annotations),
            "exclusion_rules_auto": len(exclusions),
            "exclusion_rules_mutual": sum(1 for r in exclusions if r["direction"] == "mutual"),
            "zielleistung_rules_auto": len(zielleistung),
            "factor_cap_rules_auto": len(factor_caps),
            "rules_needing_review": len(skipped_rules),
            "duplicates": len(duplicates),
            "validation_problems": len(problems),
            "rule_coverage": "partial",
            "note": (
                "Ziffern and Punktzahlen come verbatim from the official source. Exclusion and "
                "Zielleistung rules were extracted from the Anmerkungen prose automatically and "
                "are unverified; they warn rather than block by default."
            ),
        },
        "ziffern": [ziffern[z] for z in sorted(ziffern, key=_ziffer_sort_key)],
    }

    return {
        "catalog": catalog,
        "unparsed": unparsed,
        "exclusions": exclusions,
        "zielleistung": zielleistung,
        "factor_caps": factor_caps,
        "skipped_rules": skipped_rules,
        "duplicates": duplicates,
        "problems": problems,
    }


def _ziffer_sort_key(ziffer: str) -> tuple:
    match = re.match(r"^(\d+)([a-z]?)$", ziffer)
    if match:
        return (0, int(match.group(1)), match.group(2))
    return (1, 0, ziffer)


# ==========================================================================================
# writers
# ==========================================================================================


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_outputs(result: dict) -> None:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    RULES_DIR.mkdir(parents=True, exist_ok=True)

    CATALOG_PATH.write_text(
        json.dumps(result["catalog"], indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    UNPARSED_PATH.write_text(
        json.dumps(
            {
                "note": (
                    "Rows from the official source that the importer did not turn into a Ziffer "
                    "or an annotation. Nothing here was silently dropped — each entry says why."
                ),
                "count": len(result["unparsed"]),
                "rows": result["unparsed"],
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    write_csv(
        RULES_DIR / "exclusions.csv",
        result["exclusions"],
        ["rule_id", "from_ziffer", "to_ziffer", "direction", "legal_basis", "quote",
         "verified", "verified_at", "source"],
    )
    write_csv(
        RULES_DIR / "zielleistung.csv",
        result["zielleistung"],
        ["rule_id", "parent_ziffer", "child_ziffer", "legal_basis", "quote",
         "verified", "verified_at", "source"],
    )
    write_csv(
        RULES_DIR / "factor_caps.csv",
        result["factor_caps"],
        ["rule_id", "ziffer", "max_factor", "legal_basis", "quote", "verified", "verified_at", "source"],
    )
    write_csv(
        RULES_DIR / "factor_bands.csv",
        [
            {
                "category": letter,
                "threshold": band["threshold"],
                "max": band["max"],
                "legal_basis": band["legal_basis"],
                "verified": "true",
                "verified_at": datetime.now(timezone.utc).date().isoformat(),
            }
            for letter, band in sorted(FACTOR_BANDS.items())
        ],
        ["category", "threshold", "max", "legal_basis", "verified", "verified_at"],
    )

    REPORT_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "catalog_version": result["catalog"]["catalog_version"],
                "coverage": result["catalog"]["coverage"],
                "duplicates": result["duplicates"],
                "validation_problems": result["problems"][:200],
                "validation_problem_count": len(result["problems"]),
                "rules_needing_review": result["skipped_rules"],
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    if not OVERRIDES_PATH.exists():
        OVERRIDES_PATH.write_text(
            json.dumps(
                {
                    "note": (
                        "Manual corrections applied on top of the imported catalog. Every entry "
                        "needs a reason, a source and a verification date. Overrides are applied "
                        "by app/catalog.py after loading the canonical catalog."
                    ),
                    "overrides": [],
                },
                indent=1,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", help="XML snapshot to parse (default: from data/raw/manifest.json)")
    parser.add_argument(
        "--illustrative",
        action="store_true",
        help="skip the official import and keep the bundled illustrative catalog",
    )
    args = parser.parse_args()

    if args.illustrative:
        print("illustrative mode: the official import was skipped.")
        print("The catalog remains marked provenance='illustrative', rule_coverage='partial'.")
        return 0

    source_meta: dict = {}
    if args.input:
        xml_path = Path(args.input)
    else:
        manifest = RAW_DIR / "manifest.json"
        if not manifest.exists():
            print(
                "error: no snapshot found. Run scripts/fetch_goae.py first, or pass --input.",
                file=sys.stderr,
            )
            return 2
        source_meta = json.loads(manifest.read_text(encoding="utf-8"))
        xml_path = RAW_DIR / source_meta["raw_file"]

    if not xml_path.exists():
        print(f"error: {xml_path} does not exist", file=sys.stderr)
        return 2

    print(f"parsing {xml_path}")
    result = import_official(xml_path, source_meta)
    write_outputs(result)

    coverage = result["catalog"]["coverage"]
    print(f"\ncatalog_version : {result['catalog']['catalog_version']}")
    print(f"ziffern parsed  : {coverage['ziffern_parsed']}")
    print(f"annotations     : {coverage['annotations_captured']}")
    print(f"exclusions      : {coverage['exclusion_rules_auto']} "
          f"({coverage['exclusion_rules_mutual']} mutual) (unverified, warn-only)")
    print(f"zielleistung    : {coverage['zielleistung_rules_auto']} (unverified, warn-only)")
    print(f"factor caps     : {coverage['factor_cap_rules_auto']} (§ einfacher Gebührensatz)")
    print(f"unparsed rows   : {coverage['unparsed_rows']} -> {UNPARSED_PATH.name}")
    print(f"needs review    : {coverage['rules_needing_review']} -> {REPORT_PATH.name}")
    print(f"duplicates      : {coverage['duplicates']}")
    print(f"validation probs: {coverage['validation_problems']}")

    if coverage["ziffern_parsed"] < 100:
        print("\nerror: implausibly few Ziffern parsed; refusing to claim a usable catalog.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
