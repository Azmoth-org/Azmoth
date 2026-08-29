#!/usr/bin/env python3
"""Mechanical re-derivation of the auto-extracted exclusion rules. No model, no network.

    python scripts/deterministic_rule_parser.py                 # report only
    python scripts/deterministic_rule_parser.py --write         # stamp the confirmed rules
    python scripts/deterministic_rule_parser.py --residue OUT   # where the quarantine CSV goes
    python scripts/deterministic_rule_parser.py --explain excl_auto_30_4

`import_goae.py` read 837 exclusion rules out of the Anmerkungen prose. This script reads the same
prose again, independently, and asks one question per rule: **does the quoted sentence, parsed from
scratch, produce exactly this directed edge?** A rule survives only if the answer is yes on every
check. Everything else is quarantined for judgement rather than guessed at.

Why this exists before any model is asked anything. The extractor's failure modes are grammatical,
not semantic — a reversed direction, a range member that is not in the range, a frequency rule read
as an exclusion — and grammar is checkable in code. Code that can be read, re-run and diffed is
worth more here than a model's opinion, and it costs nothing per rule. Whatever survives this is
already defensible; whatever does not is a much smaller pile to think hard about.

**The five sentence forms**, which are the whole of the grammar (`d` = the Ziffer that may not be
charged, `n` = the one whose presence forbids it; the stored edge is always `n -> d`):

    A  ist_neben          Die Leistung nach Nummer <d> ist neben den Leistungen nach den
                          Nummern <n...> nicht berechnungsfähig.
    B  neben_sind         Neben der Leistung nach Nummer <n> ist die Leistung nach Nummer <d>
                          nicht berechnungsfähig.
    C  nicht_nebeneinander  Die Leistungen nach den Nummern <x...> sind nicht nebeneinander
                          berechnungsfähig.                       (every pair, mutually)
    D  darf_neben         Die Leistung nach Nummer <d> darf anstelle oder neben einer Leistung
                          nach Nummer <n...> nicht berechnet werden.
    E  neben_darf         Neben den Leistungen nach Nummer <n...> darf die Leistung nach
                          Nummer <d> nicht berechnet werden.

A and D put the forbidden Ziffer first; B and E put it last. Getting that backwards is precisely
the mistake the extractor can make and a reader can miss, so the parser decides it structurally —
from where `neben` sits relative to the verb — rather than trusting the `source` column's label.

**Sentence splitting.** Many quotes are several provisions concatenated, because the importer did
not split numbered list items: `"...zu begründen.4.Die Leistungen nach den Nummern 1, 3, 22 ..."`.
A rule must be supported by ONE provision; a quote that carries three is split first, and the
provision that actually supports the rule is recorded so a reviewer can see which sentence decided
it. `--write-quotes` replaces the stored quote with that provision alone.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from app.config import CATALOG_PATH, RULES_DATA_DIR  # noqa: E402

EXCLUSIONS_CSV = RULES_DATA_DIR / "exclusions.csv"
DEFAULT_RESIDUE = RULES_DATA_DIR / "exclusions.residue.csv"
REPORT_JSON = RULES_DATA_DIR / "deterministic_parse_report.json"

PROVENANCE = "deterministic_parser"

#: Columns this script maintains, alongside the ones `auto_verify_rules.py` adds.
PARSER_COLUMNS = ("parser_verdict", "parser_reason", "parser_provision")

# ----------------------------------------------------------------------------------------------
# vocabulary
# ----------------------------------------------------------------------------------------------

#: A restriction on how OFTEN or WHEN, which the engine cannot evaluate: it sees one invoice as a
#: flat set of positions, with no calendar, no Behandlungsfall and no notion of a session. A
#: sentence whose operative restriction is one of these is not a Nebeneinanderberechnung rule, and
#: enforcing it as an unconditional block would be wrong even though the sentence is real law.
FREQUENCY_MARKERS = (
    "mehrmalige berechnung",
    "zweimalige berechnung",
    "mehr als zwei",
    "nur einmal",
    "hoechstens zweimal",
    "je behandlungstag",
    "im behandlungsfall",
    "kalenderjahr",
    "innerhalb von",
    "derselben sitzung",
    "je sitzung",
)

#: The operative phrase that makes a sentence an exclusion at all.
#:
#: A regex rather than a list of substrings, for two reasons that both came from testing the parser
#: against the 30 hand-verified rules in `exclusions.manual.csv` — where it initially scored 0/30.
#: First, `nicht nebeneinander berechnungsfähig` puts an adverb between the two words the other
#: forms put together, so a plain `nicht berechnungsfähig` test misses form C entirely. Second, the
#: manual file transliterates its umlauts (`berechnungsfaehig`), and the catalog does not, so any
#: marker written one way silently fails on text written the other.
#: `nebeneinander` is optional in every alternative rather than only the first, because the fee
#: schedule writes the mutual form both ways — "sind nicht nebeneinander berechnungsfähig" and
#: "dürfen nicht nebeneinander berechnet werden" — and an adverb sitting between the two words a
#: marker joins is exactly what makes a sound sentence parse as no sentence at all.
EXCLUSION_RE = re.compile(
    r"nicht\s+(?:nebeneinander\s+)?berechnungsf(?:ä|ae)hig"
    r"|nicht\s+(?:nebeneinander\s+)?berechnet\s+werden"
    r"|nicht\s+(?:nebeneinander\s+)?berechenbar",
    re.IGNORECASE,
)


def fold(text: str) -> str:
    """Lower-case and transliterate, so a marker matches whichever spelling the source used."""
    out = text.lower()
    for umlaut, ascii_ in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        out = out.replace(umlaut, ascii_)
    return out

#: Softeners that make a restriction conditional. An unconditional edge is not a sound reading of a
#: sentence that only bites under a condition the engine never sees.
CONDITIONAL_MARKERS = (
    "es sei denn",
    "in der regel",
    "auf verlangen",
    "sofern",
    "soweit",
    "nur bei",
    "wenn ",
    "falls ",
    "ausnahme",
)


# ----------------------------------------------------------------------------------------------
# splitting
# ----------------------------------------------------------------------------------------------

#: `.4.` between a lower-case/period end and a capital: an unsplit numbered list item.
_LIST_ITEM = re.compile(r"(?<=[a-zäöüß)])\.\s*\d{1,2}\.\s*(?=[A-ZÄÖÜ])")
#: A sentence boundary the importer also ran together: `begründen.Anstelle`.
_RUN_ON = re.compile(r"(?<=[a-zäöüß)])\.\s*(?=[A-ZÄÖÜ][a-zäöüß])")
#: `exclusions.manual.csv` joins the provisions of one Anmerkung with a slash instead.
_SLASH = re.compile(r"\s+/\s+")
#: Abbreviations that must never be treated as a sentence end.
_PROTECT = ((r"\bNr\.", "«NR»"), (r"\bv\.\s*H\.", "«VH»"), (r"\bZ\.\s*B\.", "«ZB»"), (r"\bz\.\s*B\.", "«zb»"))


def split_provisions(quote: str) -> list[str]:
    """One quote in, its separate legal provisions out.

    Splitting is why the whole pipeline can be trusted on the ~116 rules whose stored quote carries
    two or three unrelated provisions: a verifier reading the raw quote sees temporal language from
    a neighbouring sentence and either rejects a sound rule or accepts an unsound one for the wrong
    reason. Abbreviations are masked first so `Nr. 5` is not read as the end of a sentence.
    """
    text = quote.strip()
    for pattern, token in _PROTECT:
        text = re.sub(pattern, token, text)
    parts: list[str] = []
    for chunk in _LIST_ITEM.split(text):
        for piece in _SLASH.split(chunk):
            parts.extend(_RUN_ON.split(piece))
    out = []
    for part in parts:
        for pattern, token in _PROTECT:
            part = part.replace(token, pattern.replace(r"\b", "").replace(r"\s*", " "))
        part = part.strip()
        if part:
            out.append(part)
    return out


# ----------------------------------------------------------------------------------------------
# number sets
# ----------------------------------------------------------------------------------------------

_RANGE = re.compile(r"(\d{1,5})\s*(?:bis|-|–)\s*(\d{1,5})")
#: An optional letter suffix, because 22 catalog Ziffern are not purely numeric — `269a`, `250a`,
#: `1829a` and the Zuschlag letters. Without it `Nummer 269a` yields no Ziffer at all and a sound
#: sentence parses as "not an exclusion".
_NUMBER = re.compile(r"\b(\d{1,5}[a-zA-Z]?)\b")


def expand_numbers(segment: str) -> tuple[set[str], set[str], set[str]]:
    """Ziffern a fragment names. Returns (all, from_ranges, range_endpoints).

    Ranges are the riskiest construct in this data — 486 of the 837 rules come from one — so the
    endpoints are reported separately. They are what tells a misparse from a sparse chapter: the
    fee schedule numbers with gaps (only 9 real Ziffern exist between 5000 and 5031), so counting
    how many members are absent says nothing, while an endpoint that is not itself a Ziffer means
    the two numbers were never a range.
    """
    ranged: set[str] = set()
    endpoints: set[str] = set()
    for lo, hi in _RANGE.findall(segment):
        lo_i, hi_i = int(lo), int(hi)
        if 0 < hi_i - lo_i <= 400:
            ranged |= {str(n) for n in range(lo_i, hi_i + 1)}
            endpoints |= {lo, hi}
    rest = _RANGE.sub(" ", segment)
    singles = {m for m in _NUMBER.findall(rest)}
    return ranged | singles, ranged, endpoints


# ----------------------------------------------------------------------------------------------
# provisions
# ----------------------------------------------------------------------------------------------

#: Splits form A: subject ... `ist/sind neben` ... object.
_A_SPLIT = re.compile(r"\b(?:ist|sind)\s+(?:auch\s+)?neben\b", re.IGNORECASE)
#: Splits form D: subject ... `darf [anstelle oder] neben` ... object.
_D_SPLIT = re.compile(r"\bdarf\s+(?:anstelle\s+oder\s+)?neben\b", re.IGNORECASE)
#: Splits form B: `Neben` object `ist/sind die Leistung(en)` subject.
_B_SPLIT = re.compile(r"\b(?:ist|sind)\s+(?:die|der|eine)\s+Leistung", re.IGNORECASE)
#: Splits form E: `Neben` object `darf die Leistung` subject.
_E_SPLIT = re.compile(r"\bdarf\s+(?:die|der|eine)\s+Leistung", re.IGNORECASE)
#: Form C, in either of its spellings. Must agree with `EXCLUSION_RE` above or a mutual sentence
#: passes the gate and is then parsed as a directed edge with no `neben` to split on.
_NEBENEINANDER = re.compile(
    r"nicht\s+nebeneinander\s+(?:berechnungsf|berechnet|berechenbar)", re.IGNORECASE
)
_STARTS_NEBEN = re.compile(r"^\s*(?:Neben|Anstelle\s+oder\s+neben)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Provision:
    """One parsed sentence: who forbids whom."""

    text: str
    form: str
    #: Ziffern whose presence on the invoice forbids the others. Empty for a `mutual` set.
    blockers: frozenset[str] = frozenset()
    #: Ziffern that may then not be charged.
    blocked: frozenset[str] = frozenset()
    #: For form C: every member excludes every other.
    mutual_set: frozenset[str] = frozenset()
    ranged: frozenset[str] = frozenset()
    endpoints: frozenset[str] = frozenset()

    def supports(self, n: str, d: str) -> bool:
        """Does this sentence assert the directed edge `n -> d`?"""
        if self.mutual_set:
            return n in self.mutual_set and d in self.mutual_set and n != d
        return n in self.blockers and d in self.blocked


def _cut(text: str) -> str:
    """Drop the trailing `nicht berechnungsfähig` clause so it contributes no numbers."""
    match = EXCLUSION_RE.search(text)
    return text[: match.start()] if match else text


def parse_provision(text: str) -> Provision | None:
    """One sentence in, the edge it asserts out — or None when it is not an exclusion at all."""
    if not EXCLUSION_RE.search(text):
        return None

    if _NEBENEINANDER.search(text):
        members, ranged, ends = expand_numbers(_cut(text))
        if len(members) < 2:
            return None
        return Provision(
            text, "C", mutual_set=frozenset(members), ranged=frozenset(ranged),
            endpoints=frozenset(ends),
        )

    neben_first = bool(_STARTS_NEBEN.match(text))
    if neben_first:
        for form, splitter in (("B", _B_SPLIT), ("E", _E_SPLIT)):
            parts = splitter.split(text, maxsplit=1)
            if len(parts) == 2:
                blockers, r1, e1 = expand_numbers(parts[0])
                blocked, r2, e2 = expand_numbers(_cut(parts[1]))
                if blockers and blocked:
                    return Provision(
                        text, form, frozenset(blockers), frozenset(blocked), frozenset(),
                        frozenset(r1 | r2), frozenset(e1 | e2),
                    )
        return None

    for form, splitter in (("A", _A_SPLIT), ("D", _D_SPLIT)):
        parts = splitter.split(text, maxsplit=1)
        if len(parts) == 2:
            blocked, r1, e1 = expand_numbers(parts[0])
            blockers, r2, e2 = expand_numbers(_cut(parts[1]))
            if blockers and blocked:
                return Provision(
                    text, form, frozenset(blockers), frozenset(blocked), frozenset(),
                    frozenset(r1 | r2), frozenset(e1 | e2),
                )
    return None


def is_frequency_rule(text: str) -> bool:
    """True when the sentence's operative restriction is how often, not what beside what."""
    low = fold(text)
    return any(m in low for m in FREQUENCY_MARKERS)


def conditional_marker(text: str) -> str:
    low = fold(text)
    return next((m.strip() for m in CONDITIONAL_MARKERS if m in low), "")


# ----------------------------------------------------------------------------------------------
# adjudication
# ----------------------------------------------------------------------------------------------

CONFIRMED = "CONFIRMED"
QUARANTINE = "QUARANTINE"


@dataclass
class Verdict:
    status: str
    reason: str
    provision: str = ""


@dataclass
class Tally:
    confirmed: int = 0
    quarantined: int = 0
    reasons: dict[str, int] = field(default_factory=lambda: defaultdict(int))


def adjudicate(row: dict, catalog: set[str], reciprocals: dict[str, set[str]]) -> Verdict:
    """Every check a rule must pass. The first failure wins and names itself."""
    n, d = row["from_ziffer"].strip(), row["to_ziffer"].strip()
    mutual = (row.get("direction") or "").strip() == "mutual"

    if n not in catalog or d not in catalog:
        missing = n if n not in catalog else d
        return Verdict(QUARANTINE, f"ziffer_not_in_catalog:{missing}")
    if n == d:
        return Verdict(QUARANTINE, "self_edge")

    provisions = [p for p in (parse_provision(s) for s in split_provisions(row["quote"])) if p]
    if not provisions:
        return Verdict(QUARANTINE, "no_parseable_exclusion_in_quote")

    supporting = [p for p in provisions if p.supports(n, d)]
    if not supporting:
        # The sharpest check in the script: the sentence exists, but read from scratch it does not
        # produce this edge. A reversed direction lands here.
        reversed_ = [p for p in provisions if p.supports(d, n)]
        if reversed_:
            return Verdict(QUARANTINE, "direction_reversed", reversed_[0].text)
        return Verdict(QUARANTINE, "quote_does_not_assert_this_edge", provisions[0].text)

    provision = supporting[0]

    if is_frequency_rule(provision.text):
        return Verdict(QUARANTINE, "frequency_or_time_restriction", provision.text)
    marker = conditional_marker(provision.text)
    if marker:
        return Verdict(QUARANTINE, f"conditional:{marker}", provision.text)

    # A range is checked at its ENDPOINTS, not by how many members exist. The fee schedule numbers
    # with large gaps — only 9 real Ziffern lie between 5000 and 5031 — so a sparse expansion is
    # normal and says nothing. An endpoint that is not itself a Ziffer is the real signal: it means
    # the two numbers flanking "bis" were never the bounds of a range of Ziffern.
    stray_ends = sorted(z for z in provision.endpoints if z not in catalog)
    if stray_ends:
        return Verdict(QUARANTINE, f"range_endpoint_not_a_ziffer:{stray_ends[0]}", provision.text)

    if mutual and not provision.mutual_set:
        # A one-directional sentence does not establish a mutual rule. It is mutual only if some
        # sentence also asserts the REVERSE edge `d -> n`.
        #
        # The direction here is the whole check and it is easy to get backwards — this asks whether
        # anything says `d` blocks `n`, not whether anything says `n` blocks `d`. The latter is true
        # by construction, because `provision` was selected for asserting exactly that, so testing
        # it would pass every mutual rule in the file without reading a second sentence.
        if n not in reciprocals.get(d, set()):
            return Verdict(QUARANTINE, "mutual_claim_without_reciprocal_text", provision.text)

    if not mutual and provision.mutual_set:
        return Verdict(QUARANTINE, "sentence_is_mutual_but_rule_is_one_way", provision.text)

    return Verdict(CONFIRMED, f"form_{provision.form}", provision.text)


def build_reciprocals(rows: list[dict]) -> dict[str, set[str]]:
    """Every edge any sentence in the corpus asserts, for checking a `mutual` claim.

    Built from the parsed sentences rather than from the CSV's own edges, so a mutual rule cannot
    be justified by the very row being checked.
    """
    edges: dict[str, set[str]] = defaultdict(set)
    for text in {q for r in rows for q in split_provisions(r["quote"])}:
        provision = parse_provision(text)
        if provision is None:
            continue
        if provision.mutual_set:
            for a in provision.mutual_set:
                edges[a] |= provision.mutual_set - {a}
        else:
            for a in provision.blockers:
                edges[a] |= set(provision.blocked)
    return edges


# ----------------------------------------------------------------------------------------------
# csv
# ----------------------------------------------------------------------------------------------


def load(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader if any((v or "").strip() for v in r.values())]
    for column in PARSER_COLUMNS:
        if column not in fields:
            fields.append(column)
    for row in rows:
        row.pop(None, None)
        for column in PARSER_COLUMNS:
            row.setdefault(column, "")
    return fields, rows


def save(path: Path, fields: list[str], rows: list[dict]) -> None:
    """Atomic, CRLF-preserving — `rules_hash` is a SHA-256 over these bytes."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\r\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="stamp confirmed rules as verified")
    parser.add_argument(
        "--write-quotes",
        action="store_true",
        help="also replace a concatenated quote with the single provision that decided the rule",
    )
    parser.add_argument("--residue", type=Path, default=DEFAULT_RESIDUE)
    parser.add_argument("--explain", metavar="RULE_ID", help="show the full parse for one rule")
    args = parser.parse_args(argv)

    catalog = {
        str(z["ziffer"]) for z in json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["ziffern"]
    }
    fields, rows = load(EXCLUSIONS_CSV)
    reciprocals = build_reciprocals(rows)

    if args.explain:
        row = next((r for r in rows if r["rule_id"] == args.explain), None)
        if row is None:
            print(f"no such rule: {args.explain}")
            return 1
        print(f"rule      : {row['rule_id']}  {row['from_ziffer']} -> {row['to_ziffer']} ({row['direction']})")
        print(f"raw quote : {row['quote']}\n")
        for i, text in enumerate(split_provisions(row["quote"]), 1):
            p = parse_provision(text)
            print(f"  provision {i}: {text}")
            if p is None:
                print("    -> not an exclusion statement")
            else:
                print(f"    -> form {p.form}  blockers={sorted(p.blockers)[:12]} blocked={sorted(p.blocked)[:12]}"
                      f" mutual={sorted(p.mutual_set)[:12]}")
        verdict = adjudicate(row, catalog, reciprocals)
        print(f"\nverdict   : {verdict.status}  ({verdict.reason})")
        return 0

    tally = Tally()
    residue: list[dict] = []
    today = date.today().isoformat()

    for row in rows:
        already_verified = (row.get("verified") or "").strip().lower() in {"true", "1", "yes", "y"}
        verdict = adjudicate(row, catalog, reciprocals)
        row["parser_verdict"] = verdict.status
        row["parser_reason"] = verdict.reason
        row["parser_provision"] = " ".join(verdict.provision.split())

        if verdict.status == CONFIRMED:
            tally.confirmed += 1
            tally.reasons[verdict.reason] += 1
            if args.write and not already_verified:
                row["verified"] = "true"
                row["verified_at"] = today
                source = (row.get("source") or "").strip()
                if not source.startswith(PROVENANCE):
                    row["source"] = f"{PROVENANCE}:{source}"
            if args.write_quotes and verdict.provision:
                row["quote"] = verdict.provision
        else:
            tally.quarantined += 1
            tally.reasons[verdict.reason.split(":")[0]] += 1
            residue.append(row)

    print("=" * 92)
    print("DETERMINISTIC EXCLUSION PARSE — no model, no network")
    print("=" * 92)
    print(f"  rules examined      : {len(rows)}")
    print(f"  CONFIRMED           : {tally.confirmed}  ({tally.confirmed / len(rows):.1%})")
    print(f"  QUARANTINED         : {tally.quarantined}  ({tally.quarantined / len(rows):.1%})")
    print()
    print("  confirmed by sentence form:")
    for reason, count in sorted(tally.reasons.items()):
        if reason.startswith("form_"):
            print(f"    {reason:44} {count:5}")
    print()
    print("  quarantined, by why:")
    for reason, count in sorted(tally.reasons.items(), key=lambda kv: -kv[1]):
        if not reason.startswith("form_"):
            print(f"    {reason:44} {count:5}")
    print()

    residue_fields = [f for f in fields if f in residue[0]] if residue else fields
    if residue:
        save(args.residue, residue_fields, residue)
        print(f"  residue written     : {args.residue}  ({len(residue)} rules)")
    REPORT_JSON.write_text(
        json.dumps(
            {
                "examined": len(rows),
                "confirmed": tally.confirmed,
                "quarantined": tally.quarantined,
                "by_reason": dict(sorted(tally.reasons.items())),
                "generated_at": today,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"  report written      : {REPORT_JSON}")

    if args.write or args.write_quotes:
        save(EXCLUSIONS_CSV, fields, rows)
        print(f"  exclusions.csv      : updated"
              f"{' (verdicts + verified)' if args.write else ' (quotes only)'}")
    else:
        print("  exclusions.csv      : NOT modified (report only; pass --write to stamp)")
    print("=" * 92)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
