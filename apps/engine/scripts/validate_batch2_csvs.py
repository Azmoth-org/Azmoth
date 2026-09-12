#!/usr/bin/env python3
"""Schema, citation and semantic validator for the four ADR-002 rule families.

    python scripts/validate_batch2_csvs.py                  # human-readable table
    python scripts/validate_batch2_csvs.py --json           # machine-readable findings
    python scripts/validate_batch2_csvs.py --rules-dir DIR  # validate a copy (mutation harness)

Exit status is 0 when no ERROR-severity finding was raised, 1 otherwise. WARN findings never
fail the run: they mark things a human should look at, not things that are wrong on their face.

This exists because `RuleStore._parse` is deliberately permissive — it coerces (`int(row.get(
"max_count") or "1")`, `(row.get("window") or "behandlungsfall")`) rather than rejecting, so that
one malformed row can never take the whole engine down at import time. That is the right posture
for a loader and the wrong posture for a release gate, so the strictness lives here instead.

The check that matters most is `citation_verbatim`. Every row in these files asserts a legal
basis, and the only thing standing between "cited" and "made up" is whether the quote is actually
in `data/catalogs/goae_current/goae.official.json`, byte for byte. A quote that has been tidied up
— even a typo silently corrected — is no longer the catalog's sentence, so the comparison is
whitespace-normalised (CSV cells cannot hold raw newlines) and nothing else.

`window_supported` is the second one. `app/solvers/souffle_facts.py` emits `quantity_limit` as a
3-tuple `(rule_id, ziffer, max_count)` — `window` is **not** in the fact, and `logic/datalog/
goae_rules.dl`'s LAYER 3.5 compares against `history_count`, which
`app.services.patient_history.quarter_counts` computes over a calendar quarter and nothing else.
So a row saying `window: sitzung` would not be skipped, and would not fail: it would be enforced
as if it said `behandlungsfall`, silently, at the wrong width. The report for this batch keeps
those rows out of the file by hand; this check is what makes that a gate rather than a habit.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _find_repo_root() -> Path:
    """The nearest ancestor holding both `logic/` and `data/` — the same search `app.config
    ._find_repo_root` does, kept independent rather than imported so this script stays stdlib-only
    (see the module docstring's Dockerfile note about `validate_padnext.py`/`anonymize_padnext.py`,
    the same design).

    Checkout:  …/TARGET_MONOREPO/apps/engine/scripts → …/TARGET_MONOREPO
    Container: /srv/scripts                          → /srv (`logic/` and `data/` are copied
    directly under `/srv`, not under a nested `apps/engine`, so a fixed `.parents[1]` walks past
    `/` and raises `IndexError` there — this is what broke before the search replaced it).
    """
    for candidate in (ENGINE_ROOT, *ENGINE_ROOT.parents):
        if (candidate / "logic").is_dir() and (candidate / "data").is_dir():
            return candidate
    return ENGINE_ROOT.parent.parent


REPO_ROOT = _find_repo_root()
sys.path.insert(0, str(ENGINE_ROOT))

DEFAULT_RULES_DIR = REPO_ROOT / "data" / "rules"
DEFAULT_CATALOG = REPO_ROOT / "data" / "catalogs" / "goae_current" / "goae.official.json"

#: The only `window` LAYER 3.5 can actually evaluate. See the module docstring.
SUPPORTED_WINDOWS = frozenset({"behandlungsfall"})

#: `relation` values `logic/datalog/goae_rules.dl` names literally. `min_hours_apart` is in the
#: vocabulary but is advisory-only — it never removes a position — so a row carrying it is legal
#: but is flagged, because shipping one would claim an enforcement that does not happen.
ENFORCED_RELATIONS = frozenset({"same_day_excludes"})
ADVISORY_RELATIONS = frozenset({"min_hours_apart"})

#: `app.schemas.common.Sex`.
ALLOWED_GENDERS = frozenset({"m", "w", "d"})

#: `app.schemas.case.Patient.age` is constrained `ge=0, le=130`; the Datalog sentinels for an
#: unbounded side (`NO_MIN_AGE = 0`, `NO_MAX_AGE = 999`) sit outside it on purpose.
AGE_MIN, AGE_MAX = 0, 130

#: A `source` that says nothing. Anything matching this is a placeholder, not a provenance.
PLACEHOLDER = re.compile(r"^\s*(tbd|todo|fixme|xxx+|n/?a|none|null|-+|\?+)\s*$", re.IGNORECASE)

#: Control characters that must never appear inside a CSV cell. Tab, CR and LF are included on
#: purpose: a quoted cell can carry all three through the CSV round-trip intact, but
#: `app/solvers/souffle_facts.py::_UNSAFE` (`[\t\r\n]+`) strips them on the way into a fact
#: file — so the value the engine evaluates would differ from the value a reviewer reads here.
CONTROL = re.compile(r"[\x00-\x1f\x7f]")

SEVERITIES = ("ERROR", "WARN", "INFO")


@dataclass(frozen=True)
class Finding:
    """One check, against one row (or one file, when `line` is None)."""

    file: str
    line: int | None
    rule_id: str
    check: str
    status: str  # PASS | FAIL
    severity: str  # ERROR | WARN | INFO
    message: str

    def as_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "rule_id": self.rule_id,
            "check": self.check,
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class FamilySpec:
    """What one rule family's CSV must look like, and which columns carry which meaning."""

    filename: str
    columns: tuple[str, ...]
    id_prefix: str
    ziffer_columns: tuple[str, ...]

    #: Columns that must be non-empty on every row.
    required: tuple[str, ...] = ()
    #: Columns whose value is quoted from the catalog and must appear there verbatim.
    quote_column: str = "quote"


BASE_TAIL = ("legal_basis", "quote", "verified", "verified_at", "source")

FAMILIES: tuple[FamilySpec, ...] = (
    FamilySpec(
        filename="quantity_limits.manual.csv",
        columns=("rule_id", "ziffer", "max_count", "window") + BASE_TAIL,
        id_prefix="cnt_man_",
        ziffer_columns=("ziffer",),
        required=("rule_id", "ziffer", "max_count", "window") + BASE_TAIL,
    ),
    FamilySpec(
        filename="gender_restrictions.manual.csv",
        columns=("rule_id", "ziffer", "allowed_gender") + BASE_TAIL,
        id_prefix="gr_man_",
        ziffer_columns=("ziffer",),
        required=("rule_id", "ziffer", "allowed_gender") + BASE_TAIL,
    ),
    FamilySpec(
        filename="age_restrictions.manual.csv",
        columns=("rule_id", "ziffer", "min_age", "max_age") + BASE_TAIL,
        id_prefix="age_man_",
        ziffer_columns=("ziffer",),
        # min_age/max_age are deliberately absent from `required`: an unbounded side is empty.
        required=("rule_id", "ziffer") + BASE_TAIL,
    ),
    FamilySpec(
        filename="time_relations.manual.csv",
        columns=("rule_id", "ziffer_a", "ziffer_b", "relation", "min_hours") + BASE_TAIL,
        id_prefix="tr_man_",
        ziffer_columns=("ziffer_a", "ziffer_b"),
        required=("rule_id", "ziffer_a", "ziffer_b", "relation") + BASE_TAIL,
    ),
)


def _norm(text: str) -> str:
    """NFC + collapse whitespace. The only normalisation `citation_verbatim` allows."""
    return " ".join(unicodedata.normalize("NFC", text or "").split())


def load_catalog(path: Path) -> dict[str, str]:
    """Ziffer → one normalised haystack of its official text and every annotation."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    haystacks: dict[str, str] = {}
    for entry in payload["ziffern"]:
        parts = [entry.get("official_text", "")]
        for annotation in entry.get("annotations", []):
            parts.append(
                annotation
                if isinstance(annotation, str)
                else json.dumps(annotation, ensure_ascii=False)
            )
        haystacks[entry["ziffer"]] = " ||| ".join(_norm(p) for p in parts)
    return haystacks


class Validator:
    def __init__(self, rules_dir: Path, catalog: dict[str, str]) -> None:
        self.rules_dir = rules_dir
        self.catalog = catalog
        self.findings: list[Finding] = []
        self.seen_ids: dict[str, str] = {}
        self.row_counts: dict[str, int] = {}

    # ── recording ─────────────────────────────────────────────────────────────────────────────
    def _record(
        self,
        spec_or_name: FamilySpec | str,
        line: int | None,
        rule_id: str,
        check: str,
        ok: bool,
        severity: str,
        message: str = "",
    ) -> bool:
        name = spec_or_name if isinstance(spec_or_name, str) else spec_or_name.filename
        self.findings.append(
            Finding(
                file=name,
                line=line,
                rule_id=rule_id,
                check=check,
                status="PASS" if ok else "FAIL",
                severity="INFO" if ok else severity,
                message="" if ok else message,
            )
        )
        return ok

    # ── file level ────────────────────────────────────────────────────────────────────────────
    def validate_file(self, spec: FamilySpec) -> list[dict]:
        path = self.rules_dir / spec.filename
        if not self._record(
            spec, None, "", "file_exists", path.exists(), "ERROR", f"{path} is missing"
        ):
            return []

        raw = path.read_bytes()
        self._record(
            spec, None, "", "no_bom", not raw.startswith(b"\xef\xbb\xbf"), "ERROR",
            "file starts with a UTF-8 BOM; `RuleStore._rows` opens with encoding='utf-8', so the "
            "BOM would become part of the first header name",
        )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            self._record(spec, None, "", "utf8_decodes", False, "ERROR", str(exc))
            return []
        self._record(spec, None, "", "utf8_decodes", True, "ERROR")
        # CRLF is not a defect here: `RuleStore._rows` opens with `newline=''` and hands the
        # handle to `csv.reader`, which treats \r\n as a terminator and never leaves a CR in a
        # cell (verified — no loaded value in any of the four families carries one). Several
        # older generated tables (`exclusions.csv`, `factor_bands.csv`) are CRLF too, so this is
        # the repository's existing convention. Reported only so a reviewer diffing these files
        # knows the line endings are mixed on purpose rather than by accident.
        self._record(
            spec, None, "", "line_endings_are_lf", "\r" not in text, "WARN",
            "file is CRLF; harmless (csv strips the terminator) but inconsistent with the "
            "LF-terminated manual tables such as exclusions.manual.csv",
        )
        self._record(
            spec, None, "", "trailing_newline", text.endswith("\n"), "WARN",
            "file does not end with a newline",
        )

        try:
            reader = csv.DictReader(text.splitlines(True))
            rows = list(reader)
        except csv.Error as exc:
            self._record(spec, None, "", "csv_parses", False, "ERROR", str(exc))
            return []
        self._record(spec, None, "", "csv_parses", True, "ERROR")

        header = tuple(reader.fieldnames or ())
        self._record(
            spec, None, "", "header_exact", header == spec.columns, "ERROR",
            f"header is {header!r}, expected {spec.columns!r} (schema drift: `RuleStore._parse` "
            f"indexes these names directly)",
        )

        # `RuleStore._rows` drops all-empty rows before the engine ever sees them; mirror that so
        # the counts here are the counts the engine loads, then flag them separately.
        data_rows = [r for r in rows if any((v or "").strip() for v in r.values())]
        blank = len(rows) - len(data_rows)
        self._record(
            spec, None, "", "no_blank_rows", blank == 0, "WARN",
            f"{blank} all-empty row(s) present; the loader silently drops them",
        )
        self.row_counts[spec.filename] = len(data_rows)
        return data_rows

    # ── row level ─────────────────────────────────────────────────────────────────────────────
    def validate_rows(self, spec: FamilySpec, rows: list[dict]) -> None:
        seen_semantic: dict[tuple, int] = {}

        for offset, row in enumerate(rows):
            line = offset + 2  # header is line 1
            rule_id = (row.get("rule_id") or "").strip()

            # -- required, clean, unique ---------------------------------------------------
            for column in spec.required:
                value = (row.get(column) or "").strip()
                self._record(
                    spec, line, rule_id, f"required:{column}", bool(value), "ERROR",
                    f"{column} is empty",
                )

            for column, value in row.items():
                if column is None or value is None:
                    continue
                self._record(
                    spec, line, rule_id, f"no_control_chars:{column}",
                    not CONTROL.search(value), "ERROR",
                    f"{column} contains a control character",
                )
                self._record(
                    spec, line, rule_id, f"no_edge_whitespace:{column}",
                    value == value.strip(), "WARN",
                    f"{column} has leading/trailing whitespace",
                )

            self._record(
                spec, line, rule_id, "rule_id_prefix", rule_id.startswith(spec.id_prefix), "ERROR",
                f"rule_id {rule_id!r} does not start with {spec.id_prefix!r}",
            )
            self._record(
                spec, line, rule_id, "rule_id_charset",
                bool(re.fullmatch(r"[A-Za-z0-9_]+", rule_id)), "ERROR",
                f"rule_id {rule_id!r} is not [A-Za-z0-9_]+; it is emitted as a bare Soufflé symbol",
            )
            first_seen = self.seen_ids.get(rule_id)
            self._record(
                spec, line, rule_id, "rule_id_unique", first_seen is None, "ERROR",
                f"rule_id {rule_id!r} already used in {first_seen}",
            )
            self.seen_ids.setdefault(rule_id, f"{spec.filename}:{line}")

            # -- Ziffern resolve against the shipped catalog -------------------------------
            ziffern = [(c, (row.get(c) or "").strip()) for c in spec.ziffer_columns]
            for column, ziffer in ziffern:
                self._record(
                    spec, line, rule_id, f"ziffer_syntax:{column}",
                    bool(re.fullmatch(r"[A-Za-z]?\d+[a-zA-Z]?", ziffer)), "ERROR",
                    f"{column}={ziffer!r} is not a GOÄ Ziffer token",
                )
                self._record(
                    spec, line, rule_id, f"ziffer_in_catalog:{column}",
                    ziffer in self.catalog, "ERROR",
                    f"{column}={ziffer!r} does not resolve in the shipped catalog",
                )
                self._record(
                    spec, line, rule_id, f"legal_basis_names_ziffer:{column}",
                    ziffer in (row.get("legal_basis") or ""), "WARN",
                    f"legal_basis does not name {ziffer!r}",
                )

            # -- provenance ----------------------------------------------------------------
            for column in ("quote", "legal_basis", "source"):
                value = (row.get(column) or "").strip()
                self._record(
                    spec, line, rule_id, f"not_placeholder:{column}",
                    not PLACEHOLDER.match(value), "ERROR",
                    f"{column}={value!r} is a placeholder, not a provenance",
                )

            verified = (row.get("verified") or "").strip().lower()
            self._record(
                spec, line, rule_id, "verified_vocabulary",
                verified in {"true", "false", "1", "0", "yes", "no"}, "ERROR",
                f"verified={verified!r} is not a boolean the loader's `_truthy` recognises",
            )
            verified_at = (row.get("verified_at") or "").strip()
            self._record(
                spec, line, rule_id, "verified_at_iso",
                bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", verified_at)), "ERROR",
                f"verified_at={verified_at!r} is not an ISO date",
            )

            # -- the citation is the whole point -------------------------------------------
            self._check_citation(spec, line, rule_id, row, ziffern)

            # -- family-specific -----------------------------------------------------------
            if spec.filename.startswith("quantity_limits"):
                self._check_quantity(spec, line, rule_id, row)
            elif spec.filename.startswith("gender_restrictions"):
                self._check_gender(spec, line, rule_id, row)
            elif spec.filename.startswith("age_restrictions"):
                self._check_age(spec, line, rule_id, row)
            elif spec.filename.startswith("time_relations"):
                self._check_time_relation(spec, line, rule_id, row)

            # -- no two rows may say the same thing about the same Ziffer ------------------
            key = tuple((row.get(c) or "").strip() for c in spec.ziffer_columns)
            if spec.filename.startswith("time_relations"):
                key = key + ((row.get("relation") or "").strip(),)
            prior = seen_semantic.get(key)
            self._record(
                spec, line, rule_id, "no_duplicate_subject", prior is None, "ERROR",
                f"a rule for {key!r} was already declared on line {prior}",
            )
            seen_semantic.setdefault(key, line)

    def _check_citation(
        self, spec: FamilySpec, line: int, rule_id: str, row: dict, ziffern: list
    ) -> None:
        """The quote must be in the catalog verbatim, under one of the row's own Ziffern.

        A row may cite more than one sentence, joined with ' | ' (the age rows do this to pair a
        Leistungslegende with its Anmerkung). Every part is checked independently: a row that
        cites one real sentence and one invented one must not pass on the strength of the first.
        """
        quote = (row.get(spec.quote_column) or "").strip()
        if not quote:
            return  # `required:quote` already failed; do not double-report.

        haystacks = [self.catalog.get(z, "") for _, z in ziffern if z in self.catalog]
        if not haystacks:
            return  # `ziffer_in_catalog` already failed.

        for part in quote.split(" | "):
            needle = _norm(part)
            found = any(needle in hay for hay in haystacks)
            self._record(
                spec, line, rule_id, "citation_verbatim", found, "ERROR",
                f"quoted text is not present verbatim in the catalog entry for "
                f"{[z for _, z in ziffern]}: {needle[:90]!r}",
            )

    def _check_quantity(self, spec: FamilySpec, line: int, rule_id: str, row: dict) -> None:
        raw = (row.get("max_count") or "").strip()
        try:
            max_count = int(raw)
        except ValueError:
            self._record(
                spec, line, rule_id, "max_count_int", False, "ERROR",
                f"max_count={raw!r} is not an integer; the loader would coerce it to 1 and "
                f"enforce a cap nobody wrote",
            )
            return
        self._record(spec, line, rule_id, "max_count_int", True, "ERROR")
        self._record(
            spec, line, rule_id, "max_count_positive", max_count >= 1, "ERROR",
            f"max_count={max_count} is not >= 1",
        )

        window = (row.get("window") or "").strip()
        self._record(
            spec, line, rule_id, "window_supported", window in SUPPORTED_WINDOWS, "ERROR",
            f"window={window!r} is not evaluable: `build_fact_rows` emits quantity_limit without "
            f"a window, so this row would be enforced as 'behandlungsfall' at the wrong width",
        )

    def _check_gender(self, spec: FamilySpec, line: int, rule_id: str, row: dict) -> None:
        gender = (row.get("allowed_gender") or "").strip()
        self._record(
            spec, line, rule_id, "gender_vocabulary", gender in ALLOWED_GENDERS, "ERROR",
            f"allowed_gender={gender!r} is not one of {sorted(ALLOWED_GENDERS)}",
        )

    def _check_age(self, spec: FamilySpec, line: int, rule_id: str, row: dict) -> None:
        bounds: dict[str, int | None] = {}
        for column in ("min_age", "max_age"):
            raw = (row.get(column) or "").strip()
            if raw == "":
                bounds[column] = None
                continue
            try:
                bounds[column] = int(raw)
            except ValueError:
                bounds[column] = None
                self._record(
                    spec, line, rule_id, f"{column}_int", False, "ERROR",
                    f"{column}={raw!r} is not an integer",
                )
                continue
            self._record(spec, line, rule_id, f"{column}_int", True, "ERROR")
            self._record(
                spec, line, rule_id, f"{column}_in_range",
                AGE_MIN <= bounds[column] <= AGE_MAX, "ERROR",
                f"{column}={bounds[column]} is outside Patient.age's {AGE_MIN}..{AGE_MAX}",
            )

        self._record(
            spec, line, rule_id, "age_has_a_bound",
            not (bounds.get("min_age") is None and bounds.get("max_age") is None), "ERROR",
            "neither min_age nor max_age is set; the row constrains nothing",
        )
        if bounds.get("min_age") is not None and bounds.get("max_age") is not None:
            self._record(
                spec, line, rule_id, "age_band_coherent",
                bounds["min_age"] <= bounds["max_age"], "ERROR",
                f"min_age={bounds['min_age']} > max_age={bounds['max_age']}",
            )

        self._check_vollendet(spec, line, rule_id, row, bounds)

    def _check_vollendet(
        self, spec: FamilySpec, line: int, rule_id: str, row: dict, bounds: dict
    ) -> None:
        """Cross-check the encoded band against the German the row quotes.

        "bis zum vollendeten N. Lebensjahr" is satisfied by a patient who has *not yet* completed
        their Nth year — i.e. `Patient.age <= N - 1`, because age is whole years. "ab dem
        vollendeten N. Lebensjahr" is the mirror: `age >= N`. Both readings are mechanical, so
        the encoding can be checked against the citation rather than trusted.

        The upper bound is an ERROR: "bis zum vollendeten N. Lebensjahr" is an eligibility ceiling
        in every GOÄ Leistungslegende that uses it, and `N - 1` is arithmetic, not judgement — so
        a mismatch is a defect rather than something to go and read. The lower bound stays a WARN,
        because "ab dem vollendeten N." demonstrably *can* scope something other than eligibility
        (see `min_age_is_eligibility_not_frequency`, and GOÄ 26 in the validation report).
        """
        quote = row.get("quote") or ""

        bis = re.search(r"bis\s+zum\s+vollendeten\s+(\d+)\.\s*Lebensjahr", quote)
        if bis:
            expected = int(bis.group(1)) - 1
            self._record(
                spec, line, rule_id, "vollendet_max_age",
                bounds.get("max_age") == expected, "ERROR",
                f"quote says 'bis zum vollendeten {bis.group(1)}. Lebensjahr' (age <= {expected}) "
                f"but max_age={bounds.get('max_age')}",
            )

        ab = re.search(r"ab\s+dem\s+vollendeten\s+(\d+)\.\s*Lebensjahr", quote)
        if ab:
            expected = int(ab.group(1))
            matches = bounds.get("min_age") == expected
            self._record(
                spec, line, rule_id, "vollendet_min_age", matches, "WARN",
                f"quote says 'ab dem vollendeten {ab.group(1)}. Lebensjahr' but "
                f"min_age={bounds.get('min_age')}",
            )
            # The trap this batch fell into: the phrase scopes a *frequency* clause, not
            # eligibility. Encoding it as min_age blocks the younger patients the sentence is
            # silent about — see the validation report for GOÄ 26.
            frequency = re.search(
                r"berechnungsfähig|Berechnung|je\s+Kalenderjahr|höchstens", quote
            )
            self._record(
                spec, line, rule_id, "min_age_is_eligibility_not_frequency",
                not (matches and frequency), "WARN",
                f"min_age={bounds.get('min_age')} is taken from a sentence that also limits "
                f"billing frequency ({frequency.group(0)!r} appears in the quote). Confirm the "
                f"age scopes who may be billed at all, not how often — otherwise this row blocks "
                f"younger patients the citation never excludes",
            )

    def _check_time_relation(self, spec: FamilySpec, line: int, rule_id: str, row: dict) -> None:
        relation = (row.get("relation") or "").strip()
        self._record(
            spec, line, rule_id, "relation_vocabulary",
            relation in (ENFORCED_RELATIONS | ADVISORY_RELATIONS), "ERROR",
            f"relation={relation!r} is not named in logic/datalog/goae_rules.dl",
        )
        self._record(
            spec, line, rule_id, "relation_is_enforced", relation not in ADVISORY_RELATIONS,
            "WARN",
            f"relation={relation!r} is advisory-only: LAYER 3.6 never removes a position for it, "
            f"so this row must not be counted as an enforced rule",
        )
        self._record(
            spec, line, rule_id, "distinct_ziffern",
            (row.get("ziffer_a") or "").strip() != (row.get("ziffer_b") or "").strip(), "ERROR",
            "ziffer_a equals ziffer_b; LAYER 3.6 requires A != B, so the row can never fire",
        )

        raw = (row.get("min_hours") or "").strip()
        if raw:
            try:
                hours = int(raw)
            except ValueError:
                self._record(
                    spec, line, rule_id, "min_hours_int", False, "ERROR",
                    f"min_hours={raw!r} is not an integer",
                )
                return
            self._record(spec, line, rule_id, "min_hours_int", True, "ERROR")
            self._record(
                spec, line, rule_id, "min_hours_not_enforced",
                not (hours > 0 and relation in ENFORCED_RELATIONS), "WARN",
                f"min_hours={hours} is set on an enforced relation, but `build_fact_rows` emits "
                f"time_relation without min_hours — the threshold would be silently ignored",
            )

    def run(self) -> int:
        for spec in FAMILIES:
            rows = self.validate_file(spec)
            self.validate_rows(spec, rows)
        return 1 if any(f.status == "FAIL" and f.severity == "ERROR" for f in self.findings) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rules-dir", type=Path, default=DEFAULT_RULES_DIR)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    parser.add_argument(
        "--all", action="store_true", help="list passing checks too, not only failures"
    )
    args = parser.parse_args(argv)

    validator = Validator(args.rules_dir, load_catalog(args.catalog))
    exit_code = validator.run()

    failures = [f for f in validator.findings if f.status == "FAIL"]
    shown = validator.findings if args.all else failures

    if args.json:
        print(
            json.dumps(
                {
                    "rules_dir": str(args.rules_dir),
                    "row_counts": validator.row_counts,
                    "total_checks": len(validator.findings),
                    "errors": sum(1 for f in failures if f.severity == "ERROR"),
                    "warnings": sum(1 for f in failures if f.severity == "WARN"),
                    "findings": [f.as_dict() for f in shown],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return exit_code

    print(f"rules dir : {args.rules_dir}")
    print(f"catalog   : {args.catalog}")
    for name, count in validator.row_counts.items():
        print(f"  {name:34s} {count:3d} data row(s)")
    print(f"\n{len(validator.findings)} checks run, {len(failures)} failing\n")

    if shown:
        print(f"{'SEVERITY':9s} {'FILE':34s} {'LINE':>4s} {'RULE':16s} CHECK / MESSAGE")
        print("-" * 110)
        for f in sorted(shown, key=lambda f: (SEVERITIES.index(f.severity), f.file, f.line or 0)):
            print(f"{f.severity:9s} {f.file:34s} {f.line or '':>4} {f.rule_id:16s} {f.check}")
            if f.message:
                print(f"{'':9s} {'':34s} {'':>4} {'':16s}   → {f.message}")

    errors = sum(1 for f in failures if f.severity == "ERROR")
    warnings = sum(1 for f in failures if f.severity == "WARN")
    print(f"\n{errors} error(s), {warnings} warning(s) — exit {exit_code}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
