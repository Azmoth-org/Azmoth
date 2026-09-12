#!/usr/bin/env python3
"""The CI logic guard, as a testable function — see `.github/workflows/ci.yml`'s
`contract-and-logic-gate` job for how it is invoked.

    git diff --name-only "origin/${BASE_REF}...HEAD" | python scripts/logic_guard.py

Changing the solver logic or the catalog changes what this product is willing to bill for. The
golden snapshots are the only evidence that the billing behaviour is still correct, so a change to
one without a look at the other is refused. This does not judge WHETHER the new behaviour is
right — a human does that. It refuses the case where nobody looked.

Two ways to satisfy it:

1. **The golden corpus itself moved** — the diff also touches `logic/tests/golden/` or
   `logic/tests/cases/`, so a human necessarily looked at what changed there.

2. **The ADR-002 family carve-out.** `data/rules/quantity_limits.manual.csv`,
   `gender_restrictions.manual.csv`, `age_restrictions.manual.csv` and `time_relations.manual.csv`
   are the four rule families added by ADR-002, and none of their Ziffern currently has an
   `entity_to_ziffer.csv` row — F2 in `docs/content/coverage-sprint-batch2-validation.md` records
   why. No `logic/tests/cases/*/input.json` can request one of those Ziffern, so no golden *case*
   can ever move because one of their rows changed, however real the edit is. Requiring golden
   evidence that structurally cannot exist would make the gate impossible to satisfy for this one
   family of files, which is worse than not gating them at all.

   This path only opens when EVERY legal artefact changed is one of those four CSVs — a single
   `.dl`, ASP or catalog edit alongside one still takes the golden-evidence path above, because
   *that* file's evidence can exist. It requires BOTH, together:

   - a touched family regression test (`apps/engine/tests/test_batch2_*.py` or
     `test_complex_constraints.py`) — the human evidence that someone actually exercised the
     family the edit is in, and
   - a committed `logic/tests/refreeze_report.json` (see `scripts/refreeze_rule_coverage.py
     --report`) whose `rules_hash` matches the rule tables on disk *right now* and whose
     `all_clean` is true — the mechanical proof that, for the exact rules just edited, all nine
     golden cases came back with zero leaves changed, not even an allowed one. A stale hash or a
     non-clean report is refused exactly like missing evidence, because neither proves anything
     about the code currently under review.

   **Sunset.** This path is scoped to families with no `entity_to_ziffer` wiring. The moment F2
   closes for a family — production supplies the fact the family's Ziffern need, and at least one
   of them gets an `entity_to_ziffer.csv` row — a real golden case must be added for it and this
   carve-out removed for that family's CSV. Tracked in
   `docs/content/coverage-sprint-batch2-validation.md` §13.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

#: The legal artefacts: the solver programs, and the versioned official data they run on. Mirrors
#: the original bash gate exactly — see its comment for why `data/catalogs/` is narrowed to
#: `goae_current/`.
LEGAL_RE = re.compile(r"^(logic/asp/|logic/datalog/|data/catalogs/goae_current/|data/rules/)")

#: The evidence that billing behaviour was re-examined by hand.
EVIDENCE_RE = re.compile(r"^logic/tests/(golden|cases)/")

#: The four ADR-002 rule families, none of which has an `entity_to_ziffer.csv` row for any of its
#: Ziffern (see the module docstring). Only a change confined to exactly these files may use the
#: carve-out.
FAMILY_CSVS = frozenset(
    {
        "data/rules/quantity_limits.manual.csv",
        "data/rules/gender_restrictions.manual.csv",
        "data/rules/age_restrictions.manual.csv",
        "data/rules/time_relations.manual.csv",
    }
)

#: A touched family regression test — the human half of the carve-out's evidence.
FAMILY_TEST_RE = re.compile(r"^apps/engine/tests/(test_batch2_[A-Za-z0-9_]+\.py|test_complex_constraints\.py)$")

#: Where `scripts/refreeze_rule_coverage.py --report` writes its summary, and where this guard
#: looks for it — both relative to the monorepo root.
REFREEZE_REPORT_PATH = "logic/tests/refreeze_report.json"

LOGIC_GUARD_FAILED_MESSAGE = (
    "🚨 LOGIC OR DATA CHANGED WITHOUT GOLDEN SNAPSHOT UPDATE. You modified the legal reasoning or "
    "catalog. You must review and update the golden snapshots in logic/tests/ to prove the billing "
    "behavior is still correct."
)


def verify_refreeze_report(report_path: Path) -> tuple[bool, str]:
    """The mechanical half of the carve-out's evidence. No souffle needed: `rules_hash` is a pure
    hash of the CSV bytes, so this can run in the fast, docker-less `contract-and-logic-gate` job.
    """
    if not report_path.exists():
        return False, (
            f"no refreeze report at {report_path} — run, from apps/engine: "
            f"python scripts/refreeze_rule_coverage.py --report ../../{report_path}"
        )

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"{report_path} is not valid JSON: {exc}"

    from app.config import RULES_DATA_DIR
    from app.services.rule_coverage import rules_hash

    live_hash = rules_hash(RULES_DATA_DIR)
    report_hash = report.get("rules_hash")
    if report_hash != live_hash:
        return False, (
            f"{report_path} is stale: it was generated for rules_hash {report_hash!r}, but the "
            f"rule tables on disk right now hash to {live_hash!r}. Re-run "
            f"`python scripts/refreeze_rule_coverage.py --report ../../{report_path}` (from "
            "apps/engine) against this exact change and commit the result."
        )

    if not report.get("all_clean"):
        dirty = sorted(
            name for name, case in report.get("cases", {}).items() if case.get("status") != "CLEAN"
        )
        return False, (
            f"{report_path} says the golden corpus is NOT clean for these exact rules "
            f"(non-clean cases: {dirty or 'unknown'}). That is real evidence a rule edit moved "
            "billing behaviour — this is not a false positive to route around, investigate it like "
            "any other golden-snapshot failure."
        )

    return True, (
        f"{report_path}: rules_hash {live_hash} matches the rule tables on disk, and all nine "
        "golden snapshots are CLEAN (zero leaves changed, not even an allowed one)."
    )


def evaluate(changed: list[str], *, repo_root: Path | None = None) -> tuple[bool, str]:
    """The whole decision. Returns `(satisfied, message)`; `message` is what the CI step prints."""
    repo_root = repo_root or Path.cwd()
    changed = sorted(set(changed))

    legal = sorted(p for p in changed if LEGAL_RE.match(p))
    if not legal:
        return True, (
            "No changes under logic/asp/, logic/datalog/, data/catalogs/goae_current/ or "
            "data/rules/.\nLogic guard: not applicable."
        )

    lines = ["Legal artefacts changed:"]
    lines += [f"  {p}" for p in legal]
    lines.append("")

    # `REFREEZE_REPORT_PATH` lives directly under `logic/tests/`, deliberately not inside
    # `golden/` or `cases/`: `test_batch2_parity_hardening.py` diffs `logic/tests/golden` and
    # asserts every added line is a rule-CSV filename, so a machine-generated report sitting in
    # that directory would trip it. It also is not golden-corpus evidence on its own — it is
    # machine-generated, and its presence in the diff proves nothing without `verify_refreeze_
    # report` actually checking it, which only the carve-out below does. The explicit exclusion
    # here is belt-and-braces: `EVIDENCE_RE` does not match this path today, but if the report ever
    # moved back under `golden/` or `cases/`, committing it would otherwise satisfy the ORIGINAL
    # evidence path for *any* legal change (a `.dl` edit included), skipping every carve-out check.
    evidence = sorted(p for p in changed if EVIDENCE_RE.match(p) and p != REFREEZE_REPORT_PATH)
    if evidence:
        lines.append("Golden snapshots / cases also changed:")
        lines += [f"  {p}" for p in evidence]
        lines.append("")
        lines.append(
            "::warning title=Legal artefacts changed::This pull request modifies the legal "
            "reasoning or the catalog. The golden snapshots were touched, so the billing behaviour "
            "was re-examined — the reviewer must confirm that every changed number is correct and "
            "intended. See logic/README.md."
        )
        lines.append("Logic guard: satisfied.")
        return True, "\n".join(lines)

    non_family = [p for p in legal if p not in FAMILY_CSVS]
    if not non_family:
        family_tests = sorted(p for p in changed if FAMILY_TEST_RE.match(p))
        if family_tests:
            ok, why = verify_refreeze_report(repo_root / REFREEZE_REPORT_PATH)
            lines.append("Family regression tests touched (ADR-002 carve-out):")
            lines += [f"  {p}" for p in family_tests]
            lines.append("")
            lines.append(why)
            if ok:
                lines.append("")
                lines.append(
                    "::warning title=Legal artefacts changed (family carve-out)::This pull request "
                    "modifies one or more ADR-002 rule-family CSVs. No golden case can exercise "
                    "these Ziffern yet (F2), so the carve-out's committed refreeze report is the "
                    "evidence a human looked. Sunset: once a family gets an entity_to_ziffer wiring, "
                    "a real golden case is required for it and this carve-out no longer applies."
                )
                lines.append("Logic guard: satisfied via the ADR-002 family carve-out.")
                return True, "\n".join(lines)
            lines.append("")
            lines.append(LOGIC_GUARD_FAILED_MESSAGE)
            lines.append(f"::error title=Logic guard failed::{LOGIC_GUARD_FAILED_MESSAGE}")
            return False, "\n".join(lines)

    lines.append(LOGIC_GUARD_FAILED_MESSAGE)
    lines.append(f"::error title=Logic guard failed::{LOGIC_GUARD_FAILED_MESSAGE}")
    return False, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    del argv  # the file list comes over stdin, one path per line — see the module docstring
    changed = [line.strip() for line in sys.stdin if line.strip()]
    satisfied, message = evaluate(changed)
    print(message)
    return 0 if satisfied else 1


if __name__ == "__main__":
    raise SystemExit(main())
