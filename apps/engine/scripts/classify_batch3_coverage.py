#!/usr/bin/env python3
"""Classify what "covered" actually means, per Ziffer, for coverage-sprint batch 3.

    python scripts/classify_batch3_coverage.py            # rewrite the JSON artefact + summary
    python scripts/classify_batch3_coverage.py --check    # exit 1 if it would change

**The problem this solves.** "513 Ziffern under rule" is one number covering three quite different
situations, and the published figure cannot tell them apart:

  * a Ziffer whose every mechanical constraint in the fee schedule is encoded, and exercised by a
    test that would fail if the rule stopped firing;
  * one carrying a single factor cap, correct and dull, with nothing else in the GOÄ to say
    about it;
  * one where a rule was encoded *and another sentence about the same Ziffer was held out* — for
    an unsupported window, an invisible condition, an Abschnitt-wide scope. That Ziffer is under
    rule and under-checked at the same time, and it is the only one of the three where a reader
    who takes "covered" at face value is misled.

So each Ziffer batch 3 names gets one of three labels, computed rather than asserted:

  ``FULLY_VERIFIED``   every constraint sentence naming it is encoded, **and** a golden test in
                       `tests/test_coverage_sprint_batch3.py` claims it against the real engine.
  ``MECHANICAL_ONLY``  every constraint sentence naming it is encoded, but no golden test names
                       it: simple exclusion edges and factor caps, no complex logic, taken on the
                       strength of the citation and the regression suite alone.
  ``PARTIAL``          at least one constraint sentence naming it was held out. The label carries
                       the fragments, so "partial" is a list of specific missing sentences rather
                       than a hedge.

A Ziffer whose *only* constraint is one this engine cannot express at all never reaches this
script: nothing was encoded for it, so it is not in batch 3 and not in the coverage figure either.
That is the honest outcome and the reason `PARTIAL` is about *leftovers*, not about absence.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT / "scripts"))

from deterministic_rule_parser import expand_numbers, split_provisions  # noqa: E402


def _find_repo_root() -> Path:
    for candidate in (ENGINE_ROOT, *ENGINE_ROOT.parents):
        if (candidate / "logic").is_dir() and (candidate / "data").is_dir():
            return candidate
    return ENGINE_ROOT.parent.parent


REPO_ROOT = _find_repo_root()
RULES_DIR = REPO_ROOT / "data" / "rules"
CATALOG_DIR = REPO_ROOT / "data" / "catalogs" / "goae_current"
GOLDEN_TEST = ENGINE_ROOT / "tests" / "test_coverage_sprint_batch3.py"
OUT = REPO_ROOT / "docs" / "content" / "batch3-coverage-classification.json"

BATCH_INFIX = "_b3_"

#: A section heading run into the start of the provision beneath it. Bounded to the first 90
#: characters so it can only ever strip a prefix, never eat a sentence that mentions the phrase.
HEADING_RUN_IN = re.compile(r"^.{0,60}?Allgemeine\s+Bestimmung(?:en)?\s*")

#: A run of Ziffer references introduced by "Nummer(n)" or "Buchstabe(n)". `expand_numbers` reads
#: every integer in the fragment it is handed, which is right for the extractor (it cuts the text
#: first) and far too loose here: attributing a sentence to a Ziffer because the list marker "1."
#: or the "1" in "K 1" appears in it would make GOÄ 1 look under-covered for six provisions that
#: never mention it. So only the spans below are read, and only the tokens inside them.
REFERENCE_SPAN = re.compile(
    r"(?:Nummern?|Buchstaben?)\s+((?:K\s*[12]|[0-9A-J][0-9a-zA-Z]*)"
    r"(?:\s*(?:,|und/oder|und|oder|sowie|bis)\s*(?:K\s*[12]|[0-9A-J][0-9a-zA-Z]*))*)",
    re.IGNORECASE,
)
#: "K 1" / "K 2" are written with a space in the provisions and without one in the catalog.
LETTER_ZIFFER = re.compile(r"^(K)\s*([12])$")
#: How much of two sentences must agree before one counts as citing the other. The GOÄ prints
#: several provisions twice, once in a section's Allgemeine Bestimmungen and once as a Ziffer's
#: own Anmerkung, and the two copies are not always word for word — the Visite exclusion names
#: three more Ziffern in the Anmerkung than in the provision. A rule citing one of them has
#: encoded the other; 80 identical leading characters is not a coincidence in this corpus.
PREFIX_MATCH = 80

#: The same vocabulary the batch-3 inventory was built with. A sentence matching none of these is
#: not a constraint and is not held against any Ziffer.
CONSTRAINT = re.compile(
    r"nicht\s+(?:neben|nebeneinander|gesondert\s+)?berechnungsf|nicht\s+nebeneinander"
    r"|einfachen\s+Gebührensatz|nicht\s+gesondert\s+berechnet|(?:sind|ist)\s+Bestandteil"
    r"|nicht\s+zulässig|nur\s+einmal|nicht\s+mehrfach|nicht\s+berechnet\s+werden"
    r"|höchstens|je\s+Behandlungsfall",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text or "").split())


def sentences(text: str) -> list[str]:
    """One provision per element, using the splitter the extractor already uses.

    Not a hand-rolled full-stop regex. This corpus glues numbered list items straight onto the
    previous sentence ("...zu begründen.4.Die Leistungen nach den Nummern 1, 3, 22 ..."), runs a
    heading into the paragraph under it ("SkelettAllgemeine Bestimmung Neben den ..."), and
    abbreviates with "Nr." and "z.B." mid-sentence. `split_provisions` was written against exactly
    those defects for `scripts/deterministic_rule_parser.py`; splitting them a second, slightly
    different way here would make this classification disagree with the extractor about what a
    sentence even is — and every "PARTIAL" it produced would be a splitting artefact rather than a
    missing rule.
    """
    out: list[str] = []
    for piece in split_provisions(_norm(text)):
        #: The extractor's own splitter leaves a section heading glued to the paragraph beneath it
        #: ("SkelettAllgemeine Bestimmung Neben den Leistungen nach ..."), because the source has
        #: no separator there at all. Dropping the run-in is what lets a shipped `quote` — which
        #: begins at the actual sentence — be recognised as citing it.
        heading = HEADING_RUN_IN.search(piece[:90])
        piece = piece[heading.end():] if heading else piece
        piece = piece.strip()
        if piece:
            out.append(piece)
    return out


def named_ziffern(sentence: str) -> set[str]:
    """Every Ziffer a sentence *refers to*, as opposed to every integer printed in it."""
    out: set[str] = set()
    for span in REFERENCE_SPAN.finditer(sentence):
        numbers, _, _ = expand_numbers(span.group(1))
        for token in numbers:
            letter = LETTER_ZIFFER.match(token)
            out.add(f"{letter.group(1)}{letter.group(2)}" if letter else token)
        #: `expand_numbers` is digit-only, so the Zuschlag letters have to be read here. A bare
        #: "A bis D" inside a Buchstaben span is the four letters, not a range of numbers.
        for piece in re.split(r"\s*(?:,|und/oder|und|oder|sowie)\s*", span.group(1)):
            letter = LETTER_ZIFFER.match(piece.strip())
            if letter:
                out.add(f"{letter.group(1)}{letter.group(2)}")
                continue
            bounds = re.fullmatch(r"([A-J])\s*bis\s*([A-J])", piece.strip())
            if bounds:
                lo, hi = ord(bounds.group(1)), ord(bounds.group(2))
                out |= {chr(c) for c in range(lo, hi + 1)}
            elif re.fullmatch(r"[A-J]", piece.strip()):
                out.add(piece.strip())
    return out


def _cites(sentence: str, quote: str) -> bool:
    """Does `quote` cite `sentence`? See `PREFIX_MATCH` for why this is not plain equality."""
    sentence, quote = _norm(sentence), _norm(quote)
    if sentence in quote or quote in sentence:
        return True
    return (
        len(sentence) >= PREFIX_MATCH
        and len(quote) >= PREFIX_MATCH
        and sentence[:PREFIX_MATCH] == quote[:PREFIX_MATCH]
    )


def constraint_sentences() -> list[tuple[str, str, frozenset[str]]]:
    """Every constraint sentence in the official source: `(where, text, Ziffern it names)`."""
    catalog = json.loads((CATALOG_DIR / "goae.official.json").read_text(encoding="utf-8"))
    known = {entry["ziffer"] for entry in catalog["ziffern"]}
    provisions = json.loads(
        (CATALOG_DIR / "allgemeine_bestimmungen.json").read_text(encoding="utf-8")
    )

    out: list[tuple[str, str, frozenset[str]]] = []

    def add(where: str, text: str, always: frozenset[str] = frozenset()) -> None:
        for sentence in sentences(text):
            if not CONSTRAINT.search(sentence):
                continue
            named = {z for z in named_ziffern(sentence) if z in known} | always
            if named:
                out.append((where, sentence, frozenset(named)))

    for provision in provisions["provisions"]:
        add(provision["id"], provision["text"])
    for entry in catalog["ziffern"]:
        #: An Anmerkung printed under a Ziffer is about that Ziffer even when it names no number
        #: ("Die Leistung nach Nummer 61 ist neben anderen Leistungen nicht berechnungsfähig").
        own = frozenset({entry["ziffer"]})
        for annotation in entry.get("annotations") or []:
            add(f"ziffer:{entry['ziffer']}", annotation, own)
    return out


def shipped_rules() -> list[tuple[frozenset[str], str]]:
    """`(Ziffern the rule names, its quote)` for every enforced rule in every family."""
    families = (
        ("exclusions.csv", ("from_ziffer", "to_ziffer")),
        ("exclusions.manual.csv", ("from_ziffer", "to_ziffer")),
        ("zielleistung.csv", ("parent_ziffer", "child_ziffer")),
        ("zielleistung.manual.csv", ("parent_ziffer", "child_ziffer")),
        ("specificity.csv", ("specific_ziffer", "general_ziffer")),
        ("factor_caps.csv", ("ziffer",)),
        ("quantity_limits.manual.csv", ("ziffer",)),
        ("age_restrictions.manual.csv", ("ziffer",)),
        ("gender_restrictions.manual.csv", ("ziffer",)),
        ("time_relations.manual.csv", ("ziffer_a", "ziffer_b")),
    )
    out: list[tuple[frozenset[str], str]] = []
    for filename, columns in families:
        path = RULES_DIR / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("verified", "")).strip().lower() not in {"true", "1", "yes", "y"}:
                    continue
                out.append((frozenset(row[c] for c in columns if row[c]), _norm(row["quote"])))
    return out


def golden_tested_ziffern() -> frozenset[str]:
    """Ziffern named as a string literal anywhere in the batch-3 golden test module.

    Parsed rather than regex-matched so a number inside a docstring — and these docstrings quote
    the GOÄ heavily — cannot be mistaken for a Ziffer the suite actually claims on an invoice.
    """
    tree = ast.parse(GOLDEN_TEST.read_text(encoding="utf-8"))
    literals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # a docstring
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.add(node.value)
    return frozenset(literals)


def classify() -> dict:
    batch3: set[str] = set()
    with (RULES_DIR / "exclusions.manual.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if BATCH_INFIX in row["rule_id"]:
                batch3.update((row["from_ziffer"], row["to_ziffer"]))
    with (RULES_DIR / "factor_caps.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if BATCH_INFIX in row["rule_id"]:
                batch3.add(row["ziffer"])
    batch3.discard("")

    corpus = constraint_sentences()
    rules = shipped_rules()
    tested = golden_tested_ziffern()

    #: A sentence counts as encoded *for a Ziffer* when some shipped rule naming that Ziffer
    #: quotes it. Per Ziffer, not globally: the GOÄ 435 sentence is encoded for 435 and for the
    #: 181 positions it blocks, and would be "encoded" for nothing else even though it names
    #: Abschnitte that reach further.
    entries: dict[str, dict] = {}
    for ziffer in sorted(batch3):
        naming = [(where, text) for where, text, named in corpus if ziffer in named]
        quotes = [quote for ziffern, quote in rules if ziffer in ziffern]
        missing = [
            {"source": where, "sentence": text}
            for where, text in naming
            if not any(_cites(text, quote) for quote in quotes)
        ]
        if missing:
            label = "PARTIAL"
        elif ziffer in tested:
            label = "FULLY_VERIFIED"
        else:
            label = "MECHANICAL_ONLY"
        entries[ziffer] = {
            "classification": label,
            "constraint_sentences": len(naming),
            "encoded": len(naming) - len(missing),
            "golden_tested": ziffer in tested,
            "not_encoded": missing,
        }

    counts: dict[str, int] = {}
    for entry in entries.values():
        counts[entry["classification"]] = counts.get(entry["classification"], 0) + 1
    return {
        "note": (
            "Per-Ziffer classification of what coverage-sprint batch 3 actually encoded, computed "
            "by apps/engine/scripts/classify_batch3_coverage.py from data/rules/*.csv, the "
            "catalog and data/catalogs/goae_current/allgemeine_bestimmungen.json. See "
            "docs/content/coverage-sprint-report-batch3.md §5."
        ),
        "ziffern_classified": len(entries),
        "counts": counts,
        "ziffern": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    payload = classify()
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if OUT.exists() and OUT.read_text(encoding="utf-8") == text:
            print(f"{OUT.name}: up to date")
            return 0
        print(f"{OUT.name}: STALE — re-run without --check", file=sys.stderr)
        return 1

    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"  Ziffern classified : {payload['ziffern_classified']}")
    for label in ("FULLY_VERIFIED", "MECHANICAL_ONLY", "PARTIAL"):
        print(f"  {label:<18}: {payload['counts'].get(label, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
