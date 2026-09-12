"""`scripts/logic_guard.py`'s decision logic, unit-tested directly against synthetic diffs.

The three cases the ADR-002 family carve-out exists to tell apart, each pinned so a future edit to
the guard cannot loosen it by accident:

* a rule-family CSV change with a touched family test *and* a fresh, CLEAN refreeze report passes;
* any other legal artefact (a `.dl` edit, a non-family CSV) still needs the original golden-corpus
  evidence — the carve-out never applies to it, a family test and a CLEAN report notwithstanding;
* a rule-family CSV change with a stale or non-clean report still fails — the carve-out is not a
  blanket exemption for the four family files, it is conditioned on the report actually proving
  nothing moved for the rules on disk right now.
"""

from __future__ import annotations

import json

import scripts.logic_guard as logic_guard
from app.config import RULES_DATA_DIR
from app.services.rule_coverage import rules_hash

REPORT_REL_PATH = logic_guard.REFREEZE_REPORT_PATH


def _write_report(repo_root, *, rules_hash_value: str, all_clean: bool) -> None:
    path = repo_root / REPORT_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    status = "CLEAN" if all_clean else "!! BEHAVIOUR MOVED"
    path.write_text(
        json.dumps(
            {
                "generated_at": "2026-09-12T00:00:00+00:00",
                "rules_hash": rules_hash_value,
                "cases": {"case_001_knee": {"status": status, "allowed": 0, "not_allowed": 0 if all_clean else 1}},
                "all_clean": all_clean,
            }
        ),
        encoding="utf-8",
    )


def _live_rules_hash() -> str:
    return rules_hash(RULES_DATA_DIR)


# ==============================================================================================
# no legal artefact changed at all
# ==============================================================================================


def test_no_legal_artefact_changed_is_not_applicable():
    satisfied, message = logic_guard.evaluate(["apps/web/lib/review/format.ts", "docs/README.md"])

    assert satisfied is True
    assert "not applicable" in message


# ==============================================================================================
# the original path: golden evidence in the diff
# ==============================================================================================


def test_a_dl_edit_with_golden_evidence_is_satisfied():
    satisfied, _ = logic_guard.evaluate(
        ["logic/datalog/goae_rules.dl", "logic/tests/golden/case_001_knee.golden.normalized.json"]
    )

    assert satisfied is True


def test_a_dl_edit_with_no_golden_evidence_fails():
    satisfied, message = logic_guard.evaluate(["logic/datalog/goae_rules.dl"])

    assert satisfied is False
    assert "GOLDEN SNAPSHOT" in message


# ==============================================================================================
# the ADR-002 family carve-out — the three pinned scenarios
# ==============================================================================================


def test_family_csv_with_family_test_and_clean_report_passes(tmp_path):
    _write_report(tmp_path, rules_hash_value=_live_rules_hash(), all_clean=True)

    satisfied, message = logic_guard.evaluate(
        [
            "data/rules/age_restrictions.manual.csv",
            "apps/engine/tests/test_batch2_semantic_boundaries.py",
        ],
        repo_root=tmp_path,
    )

    assert satisfied is True
    assert "family carve-out" in message


def test_non_family_legal_artefact_is_not_covered_by_the_carve_out(tmp_path):
    """A family test plus a CLEAN report must not paper over a change to a file the carve-out was
    never scoped to — e.g. a second, non-family CSV changing alongside a family one, or a `.dl`
    edit. That file's evidence can exist in `logic/tests/`, so it must be there."""
    _write_report(tmp_path, rules_hash_value=_live_rules_hash(), all_clean=True)

    satisfied, message = logic_guard.evaluate(
        [
            "data/rules/age_restrictions.manual.csv",
            "data/rules/exclusions.manual.csv",  # not one of the four family CSVs
            "apps/engine/tests/test_batch2_semantic_boundaries.py",
        ],
        repo_root=tmp_path,
    )

    assert satisfied is False
    assert "GOLDEN SNAPSHOT" in message


def test_family_csv_change_with_a_stale_report_fails(tmp_path):
    """The report exists and says CLEAN, but for a different `rules_hash` than the rules on disk
    now — e.g. left over from a previous commit. Trusting it would let an unreviewed edit ride in
    on someone else's evidence."""
    _write_report(tmp_path, rules_hash_value="0" * 64, all_clean=True)

    satisfied, message = logic_guard.evaluate(
        [
            "data/rules/age_restrictions.manual.csv",
            "apps/engine/tests/test_batch2_semantic_boundaries.py",
        ],
        repo_root=tmp_path,
    )

    assert satisfied is False
    assert "GOLDEN SNAPSHOT" in message


def test_family_csv_change_with_no_report_at_all_fails(tmp_path):
    satisfied, message = logic_guard.evaluate(
        [
            "data/rules/age_restrictions.manual.csv",
            "apps/engine/tests/test_batch2_semantic_boundaries.py",
        ],
        repo_root=tmp_path,
    )

    assert satisfied is False
    assert "GOLDEN SNAPSHOT" in message


def test_family_csv_change_with_a_non_clean_report_fails(tmp_path):
    _write_report(tmp_path, rules_hash_value=_live_rules_hash(), all_clean=False)

    satisfied, message = logic_guard.evaluate(
        [
            "data/rules/age_restrictions.manual.csv",
            "apps/engine/tests/test_batch2_semantic_boundaries.py",
        ],
        repo_root=tmp_path,
    )

    assert satisfied is False
    assert "NOT clean" in message


def test_committing_the_report_alone_does_not_satisfy_a_non_family_change(tmp_path):
    """The guard excludes `REFREEZE_REPORT_PATH` from the ORIGINAL evidence match explicitly,
    belt-and-braces: if that path ever moved back under `logic/tests/golden/` or `logic/tests/
    cases/`, committing the report — even a stale or dirty one — would otherwise satisfy the guard
    for a `.dl` edit or any other legal artefact, skipping every check the carve-out exists to run.
    It must not, regardless of where the report happens to live."""
    _write_report(tmp_path, rules_hash_value=_live_rules_hash(), all_clean=True)

    satisfied, message = logic_guard.evaluate(
        ["logic/datalog/goae_rules.dl", REPORT_REL_PATH],
        repo_root=tmp_path,
    )

    assert satisfied is False
    assert "GOLDEN SNAPSHOT" in message


def test_family_csv_change_without_a_family_test_fails(tmp_path):
    """The carve-out needs both halves of the evidence. A CLEAN report with nobody having touched a
    family test is not enough — nothing shows a human exercised the family that changed."""
    _write_report(tmp_path, rules_hash_value=_live_rules_hash(), all_clean=True)

    satisfied, message = logic_guard.evaluate(
        ["data/rules/age_restrictions.manual.csv"],
        repo_root=tmp_path,
    )

    assert satisfied is False
    assert "GOLDEN SNAPSHOT" in message
