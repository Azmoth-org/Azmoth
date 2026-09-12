#!/usr/bin/env python3
"""Mutation harness for the Batch 2 rule corpus and its validator.

    python scripts/mutate_batch2.py                # run every mutation, print the table
    python scripts/mutate_batch2.py --json
    python scripts/mutate_batch2.py --keep         # leave the temp dirs for inspection

A check that no mutation has ever been shown to fail is not evidence of anything. This applies a
list of deliberate, targeted corruptions to a **copy** of `data/rules/` and records, for each
one, whether `validate_batch2_csvs.py` catches it.

Isolation is by file copy into a fresh temporary directory, one per mutation, removed afterwards.
Nothing here writes to `data/rules/`, and nothing here uses git — no worktrees, no stashing, no
checkout switching. `verify_working_tree_is_clean()` re-reads the four real files at the end and
compares them against the digests taken before the run, so "the working tree was not touched" is
asserted rather than assumed.

A mutation that is **not** detected is a survivor. Survivors are printed separately and are not
silently repaired: each one is a real statement about what this validator cannot see, and the
right response is a decision, not a patch applied in the dark.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _find_repo_root() -> Path:
    """The nearest ancestor holding both `logic/` and `data/` — see `validate_batch2_csvs.py`'s
    copy of this helper for why it is independent rather than imported from `app.config`: this
    script is stdlib-only by design (like it, and like the padnext validator/anonymiser), and a
    fixed `.parents[1]` breaks in the container image, where `logic/` and `data/` sit directly
    under `/srv` rather than under a nested `apps/engine`."""
    for candidate in (ENGINE_ROOT, *ENGINE_ROOT.parents):
        if (candidate / "logic").is_dir() and (candidate / "data").is_dir():
            return candidate
    return ENGINE_ROOT.parent.parent


REPO_ROOT = _find_repo_root()
sys.path.insert(0, str(ENGINE_ROOT))

RULES_DIR = REPO_ROOT / "data" / "rules"
CATALOG = REPO_ROOT / "data" / "catalogs" / "goae_current" / "goae.official.json"
VALIDATOR = ENGINE_ROOT / "scripts" / "validate_batch2_csvs.py"

FILES = (
    "quantity_limits.manual.csv",
    "gender_restrictions.manual.csv",
    "age_restrictions.manual.csv",
    "time_relations.manual.csv",
)

_spec = importlib.util.spec_from_file_location("validate_batch2_csvs", VALIDATOR)
_validator = importlib.util.module_from_spec(_spec)
sys.modules["validate_batch2_csvs"] = _validator
_spec.loader.exec_module(_validator)


@dataclass
class Mutation:
    id: str
    file: str
    description: str
    #: What a reviewer should expect. "detected" means the validator must fail; "survives" means
    #: it is known and accepted that this validator cannot see it, and why is in `note`.
    expected: str
    apply: object
    note: str = ""


# ── mutation operators ────────────────────────────────────────────────────────────────────────


def _edit(path: Path, mutate) -> None:
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(text.splitlines(True))
    fieldnames = list(reader.fieldnames or [])
    rows = [dict(r) for r in reader]
    mutate(rows)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _row(rows: list[dict], ziffer: str) -> dict:
    return next(r for r in rows if r.get("ziffer") == ziffer)


def _set(ziffer: str, column: str, value: str):
    return lambda rows: _row(rows, ziffer).update({column: value})


def _delete_row(ziffer: str):
    def op(rows):
        rows.remove(_row(rows, ziffer))

    return op


MUTATIONS: tuple[Mutation, ...] = (
    # ── boundary shifts: the off-by-one class ────────────────────────────────────────────────
    Mutation(
        "M01", "age_restrictions.manual.csv",
        "shift GOÄ 250a max_age 7 → 8 (one year past 'bis zum vollendeten 8. Lebensjahr')",
        "detected", _set("250a", "max_age", "8"),
    ),
    Mutation(
        "M02", "age_restrictions.manual.csv",
        "shift GOÄ 5041 max_age 13 → 12 (one year short of the cited band)",
        "detected", _set("5041", "max_age", "12"),
    ),
    Mutation(
        "M03", "age_restrictions.manual.csv",
        "invert GOÄ 26's band: min_age 2 → 14, max_age 13 → 2",
        "detected", lambda rows: _row(rows, "26").update({"min_age": "14", "max_age": "2"}),
    ),
    Mutation(
        "M04", "age_restrictions.manual.csv",
        "widen GOÄ 412 max_age 1 → 130 (rule made vacuous)",
        "detected", _set("412", "max_age", "130"),
    ),
    Mutation(
        "M05", "quantity_limits.manual.csv",
        "loosen GOÄ 4601 max_count 3 → 4 (the '<' vs '<=' equivalent for a cap)",
        "survives", _set("4601", "max_count", "4"),
        note="max_count is a free integer; nothing in the citation is machine-comparable to it. "
             "Covered instead by tests/test_batch2_semantic_boundaries.py, which asserts the cap "
             "value per Ziffer.",
    ),
    Mutation(
        "M06", "quantity_limits.manual.csv",
        "set GOÄ 4 max_count 1 → 0 (blocks every claim)",
        "detected", _set("4", "max_count", "0"),
    ),
    Mutation(
        "M07", "quantity_limits.manual.csv",
        "set GOÄ 860 max_count to a non-integer ('einmal')",
        "detected", _set("860", "max_count", "einmal"),
    ),
    # ── the unsupported-window gate ──────────────────────────────────────────────────────────
    Mutation(
        "M08", "quantity_limits.manual.csv",
        "change GOÄ 4 window behandlungsfall → sitzung (a window the engine cannot evaluate)",
        "detected", _set("4", "window", "sitzung"),
    ),
    Mutation(
        "M09", "quantity_limits.manual.csv",
        "change GOÄ 807 window → kalenderjahr",
        "detected", _set("807", "window", "kalenderjahr"),
    ),
    Mutation(
        "M10", "quantity_limits.manual.csv",
        "blank GOÄ 842's window entirely (loader would default it to behandlungsfall)",
        "detected", _set("842", "window", ""),
    ),
    # ── gender comparisons ───────────────────────────────────────────────────────────────────
    Mutation(
        "M11", "gender_restrictions.manual.csv",
        "reverse GOÄ 27 allowed_gender w → m (contradicts 'Untersuchung einer Frau')",
        "survives", _set("27", "allowed_gender", "m"),
        note="'m' is in the vocabulary and the citation stays verbatim; the contradiction is "
             "between German prose and a one-letter code, which this validator does not parse. "
             "Covered by the GENDER_ROWS parametrisation in the boundary suite.",
    ),
    Mutation(
        "M12", "gender_restrictions.manual.csv",
        "set GOÄ 1700 allowed_gender to 'male' (out of the Sex vocabulary)",
        "detected", _set("1700", "allowed_gender", "male"),
    ),
    Mutation(
        "M13", "gender_restrictions.manual.csv",
        "uppercase GOÄ 1730 allowed_gender w → W",
        "detected", _set("1730", "allowed_gender", "W"),
    ),
    # ── provenance: the legal-traceability class ─────────────────────────────────────────────
    Mutation(
        "M14", "gender_restrictions.manual.csv",
        "remove GOÄ 1709's citation entirely",
        "detected", _set("1709", "quote", ""),
    ),
    Mutation(
        "M15", "quantity_limits.manual.csv",
        "replace GOÄ 380's citation with a plausible invention",
        "detected",
        _set("380", "quote", "Die Leistung nach Nummer 380 ist je Behandlungsfall 30-mal berechnungsfähig."),
    ),
    Mutation(
        "M16", "quantity_limits.manual.csv",
        "silently correct the catalog's 'je Text' typo on GOÄ 382 to 'je Test'",
        "detected",
        lambda rows: _row(rows, "382").update(
            {"quote": _row(rows, "382")["quote"].replace("je Text", "je Test")}
        ),
    ),
    Mutation(
        "M17", "age_restrictions.manual.csv",
        "swap GOÄ 273's citation for GOÄ 412's (a real sentence, wrong Ziffer)",
        "detected",
        lambda rows: _row(rows, "273").update({"quote": _row(rows, "412")["quote"]}),
    ),
    Mutation(
        "M18", "age_restrictions.manual.csv",
        "replace GOÄ 1063's source with a placeholder ('TBD')",
        "detected", _set("1063", "source", "TBD"),
    ),
    Mutation(
        "M19", "gender_restrictions.manual.csv",
        "blank GOÄ 1782's legal_basis",
        "detected", _set("1782", "legal_basis", ""),
    ),
    Mutation(
        "M20", "quantity_limits.manual.csv",
        "flip GOÄ 388 verified true → false (claims verification it does not have)",
        "survives", _set("388", "verified", "false"),
        note="'false' is a legal value — an unverified rule is a supported state, handled by "
             "UnverifiedRulePolicy at load time, not a malformed row. Its effect is a rule that "
             "stops being enforced, which the engine-level count would show.",
    ),
    # ── structural ───────────────────────────────────────────────────────────────────────────
    Mutation(
        "M21", "quantity_limits.manual.csv",
        "delete the GOÄ 4601 row outright",
        "survives", _delete_row("4601"),
        note="A validator cannot know which rows *should* exist. Detected instead by "
             "tests/test_coverage_sprint_batch2.py (asserts cnt_man_4601 fires) and by the row "
             "counts pinned in tests/test_validate_batch2_csvs.py.",
    ),
    Mutation(
        "M22", "gender_restrictions.manual.csv",
        "duplicate GOÄ 1700's rule_id onto the GOÄ 1701 row",
        "detected", _set("1701", "rule_id", "gr_man_1700"),
    ),
    Mutation(
        "M23", "age_restrictions.manual.csv",
        "point GOÄ 413's row at a Ziffer that is not in the catalog (99999)",
        "detected", _set("413", "ziffer", "99999"),
    ),
    Mutation(
        "M24", "age_restrictions.manual.csv",
        "blank both age bounds on GOÄ K1 (row constrains nothing)",
        "detected", lambda rows: _row(rows, "K1").update({"min_age": "", "max_age": ""}),
    ),
    Mutation(
        "M25", "quantity_limits.manual.csv",
        "rename the max_count column in the header",
        "detected", None,
        note="applied as a raw text edit, not a row edit",
    ),
    Mutation(
        "M26", "age_restrictions.manual.csv",
        "prepend a UTF-8 BOM",
        "detected", None,
        note="applied as a raw byte edit",
    ),
    Mutation(
        "M27", "gender_restrictions.manual.csv",
        "embed a tab inside GOÄ 1711's legal_basis",
        "detected", _set("1711", "legal_basis", "GOÄ\tLeistungslegende Nr. 1711"),
    ),
    Mutation(
        "M28", "time_relations.manual.csv",
        "add a time-relation row with an unknown relation kind",
        "detected", None,
        note="applied by writing a row into the empty family",
    ),
    Mutation(
        "M29", "time_relations.manual.csv",
        "add a self-referential time-relation row (ziffer_a == ziffer_b)",
        "detected", None,
        note="applied by writing a row into the empty family",
    ),
)


def _raw_mutation(mutation_id: str, path: Path) -> None:
    """The mutations that cannot be expressed as a row edit."""
    if mutation_id == "M25":
        path.write_text(
            path.read_text(encoding="utf-8").replace("max_count", "maximum_count", 1),
            encoding="utf-8",
        )
    elif mutation_id == "M26":
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    elif mutation_id in {"M28", "M29"}:
        spec = next(f for f in _validator.FAMILIES if f.filename.startswith("time_relations"))
        row = {
            "rule_id": "tr_man_4_5",
            "ziffer_a": "4",
            "ziffer_b": "4" if mutation_id == "M29" else "5",
            "relation": "within_14_days" if mutation_id == "M28" else "same_day_excludes",
            "min_hours": "",
            "legal_basis": "GOÄ Anmerkung zu Nummer 4",
            "quote": "Die Leistung nach Nummer 4 ist im Behandlungsfall nur einmal berechnungsfähig.",
            "verified": "true",
            "verified_at": "2026-09-12",
            "source": "mutation_harness",
        }
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(spec.columns))
            writer.writeheader()
            writer.writerow(row)


def _digests() -> dict[str, str]:
    return {
        name: hashlib.sha256((RULES_DIR / name).read_bytes()).hexdigest() for name in FILES
    }


def run_mutation(mutation: Mutation, keep: bool) -> dict:
    workdir = Path(tempfile.mkdtemp(prefix=f"azmoth-mutation-{mutation.id}-"))
    try:
        rules_copy = workdir / "rules"
        rules_copy.mkdir()
        for name in FILES:
            shutil.copy2(RULES_DIR / name, rules_copy / name)

        target = rules_copy / mutation.file
        if mutation.apply is None:
            _raw_mutation(mutation.id, target)
        else:
            _edit(target, mutation.apply)

        proc = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--rules-dir", str(rules_copy),
                "--catalog", str(CATALOG),
                "--json",
            ],
            capture_output=True, text=True,
        )
        detected = proc.returncode != 0
        checks: list[str] = []
        if proc.stdout:
            try:
                payload = json.loads(proc.stdout)
                checks = sorted(
                    {f["check"] for f in payload["findings"] if f["severity"] == "ERROR"}
                )
            except json.JSONDecodeError:
                pass

        expected_detected = mutation.expected == "detected"
        return {
            "id": mutation.id,
            "file": mutation.file,
            "description": mutation.description,
            "expected": mutation.expected,
            "detected": detected,
            "exit_code": proc.returncode,
            "caught_by": checks,
            "result": "OK" if detected == expected_detected else "UNEXPECTED",
            "survivor": not detected,
            "note": mutation.note,
            "command": (
                f"python scripts/validate_batch2_csvs.py --rules-dir <copy> --catalog <catalog>"
            ),
        }
    finally:
        if not keep:
            shutil.rmtree(workdir, ignore_errors=True)


def verify_working_tree_is_clean(before: dict[str, str]) -> bool:
    return _digests() == before


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--keep", action="store_true", help="do not delete the temp directories")
    args = parser.parse_args(argv)

    before = _digests()
    results = [run_mutation(m, args.keep) for m in MUTATIONS]
    tree_clean = verify_working_tree_is_clean(before)

    detected = [r for r in results if r["detected"]]
    survivors = [r for r in results if r["survivor"]]
    unexpected = [r for r in results if r["result"] == "UNEXPECTED"]

    if args.json:
        print(
            json.dumps(
                {
                    "total": len(results),
                    "detected": len(detected),
                    "survivors": len(survivors),
                    "unexpected": len(unexpected),
                    "working_tree_unchanged": tree_clean,
                    "results": results,
                },
                indent=2, ensure_ascii=False,
            )
        )
    else:
        print(f"{'ID':5s} {'FILE':32s} {'EXPECT':9s} {'ACTUAL':9s} RESULT  CAUGHT BY")
        print("-" * 118)
        for r in results:
            actual = "detected" if r["detected"] else "survived"
            caught = ", ".join(r["caught_by"][:3]) if r["caught_by"] else "—"
            print(
                f"{r['id']:5s} {r['file']:32s} {r['expected']:9s} {actual:9s} "
                f"{r['result']:7s} {caught}"
            )
            print(f"      {r['description']}")
            if r["note"]:
                print(f"      note: {r['note']}")
        print()
        print(f"{len(results)} mutation(s): {len(detected)} detected, {len(survivors)} survived")
        print(f"unexpected outcomes           : {len(unexpected)}")
        print(f"working tree unchanged        : {tree_clean}")

    # A survivor that was predicted is information, not a failure. An outcome that contradicts
    # the prediction is the thing that must stop a release gate.
    return 0 if (not unexpected and tree_clean) else 1


if __name__ == "__main__":
    raise SystemExit(main())
