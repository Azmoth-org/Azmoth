"""The `files_loaded` parity carve-out in `tests/test_golden_snapshot.py`, tested directly.

Batch 2 relaxed one path in the frozen-snapshot comparison so that shipping a new rule-file
format does not require re-freezing nine golden files. A relaxation in a parity test is exactly
the kind of change that quietly becomes a hole, so this file pins the shape of the hole:

* what the carve-out is allowed to permit — a new file, reordering, the snapshot's own list;
* what it must still reject — a file the snapshot loaded that no longer loads;
* and, most importantly, that it is **scoped**: every other leaf of the response, including the
  sibling fields inside `rule_summary`, is still compared value-by-value with no allow-list.

The helpers are imported from the snapshot module itself rather than re-implemented, so this
cannot pass against a copy of the logic that has drifted from the real one.
"""

from __future__ import annotations

import pytest

from tests.test_golden_snapshot import (
    RULE_SUMMARY_FILES_LOADED_PATH,
    _flatten,
    _get_path,
    _without_files_loaded,
)

PATH = RULE_SUMMARY_FILES_LOADED_PATH


def _response(files: list[str], **rule_summary_extra) -> dict:
    """The smallest tree with the same shape as the part of the response under test."""
    return {
        "audit_trail": {
            "rule_summary": {
                "files_loaded": files,
                "enforced_rule_count": 944,
                "total_constraint_rule_count": 980,
                **rule_summary_extra,
            }
        },
        "coding": {"billable": [{"ziffer": "1", "amount": "10.72"}]},
    }


def _dropped(frozen: dict, live: dict) -> list[str]:
    """The assertion `test_the_engine_still_reproduces_the_frozen_snapshot` actually makes."""
    return sorted(set(_get_path(frozen, PATH)) - set(_get_path(live, PATH)))


def _changed(frozen: dict, live: dict) -> dict:
    """The generic leaf comparison, with the carve-out applied — the second assertion."""
    frozen_leaves = _without_files_loaded(_flatten(frozen))
    live_leaves = _without_files_loaded(_flatten(live))
    return {
        path: (value, live_leaves.get(path))
        for path, value in frozen_leaves.items()
        if live_leaves.get(path) != value
    }


BASE = ["exclusions.csv", "exclusions.manual.csv", "factor_caps.csv"]


# ==============================================================================================
# What the carve-out permits
# ==============================================================================================


def test_identical_lists_in_the_same_order_pass():
    frozen, live = _response(list(BASE)), _response(list(BASE))
    assert _dropped(frozen, live) == []
    assert _changed(frozen, live) == {}


def test_identical_values_in_a_different_order_pass():
    """The whole point of the change: this is what an index-by-index comparison got wrong."""
    frozen, live = _response(list(BASE)), _response(list(reversed(BASE)))
    assert _dropped(frozen, live) == []
    assert _changed(frozen, live) == {}


@pytest.mark.parametrize("position", [0, 1, len(BASE)])
def test_a_new_file_inserted_anywhere_passes(position):
    """Insertion at the front is the case that shifted every later index. `age_restrictions
    .manual.csv` really does sort first among the four files Batch 2 added."""
    live_files = list(BASE)
    live_files.insert(position, "age_restrictions.manual.csv")
    frozen, live = _response(list(BASE)), _response(live_files)
    assert _dropped(frozen, live) == []
    assert _changed(frozen, live) == {}


def test_all_four_batch2_files_appearing_at_once_passes():
    live_files = sorted(
        BASE
        + [
            "age_restrictions.manual.csv",
            "gender_restrictions.manual.csv",
            "quantity_limits.manual.csv",
            "time_relations.manual.csv",
        ]
    )
    frozen, live = _response(list(BASE)), _response(live_files)
    assert _dropped(frozen, live) == []
    assert _changed(frozen, live) == {}


def test_an_empty_frozen_list_permits_anything():
    frozen, live = _response([]), _response(list(BASE))
    assert _dropped(frozen, live) == []


def test_a_duplicate_entry_does_not_fail_the_subset_check():
    """Set semantics make a repeated filename invisible. `RuleStore._rows` appends once per file
    per load, so a duplicate would mean the same file was loaded twice — which this comparison
    is not the thing that catches. Pinned so the limitation is stated, not discovered."""
    frozen, live = _response(list(BASE)), _response(BASE + [BASE[0]])
    assert _dropped(frozen, live) == []


# ==============================================================================================
# What the carve-out must still reject
# ==============================================================================================


def test_a_file_that_no_longer_loads_is_caught():
    """The regression the subset check exists to keep catching: a rule table silently stopped
    being loaded, so rules that used to be enforced are not."""
    frozen, live = _response(list(BASE)), _response(BASE[:-1])
    assert _dropped(frozen, live) == ["factor_caps.csv"]


def test_an_emptied_live_list_is_caught():
    frozen, live = _response(list(BASE)), _response([])
    assert _dropped(frozen, live) == sorted(BASE)


def test_a_renamed_file_is_caught_as_a_drop():
    """A rename is an add plus a drop; the add is fine and the drop is not."""
    frozen = _response(list(BASE))
    live = _response(["exclusions.csv", "exclusions.manual.csv", "factor_caps.v2.csv"])
    assert _dropped(frozen, live) == ["factor_caps.csv"]


# ==============================================================================================
# The carve-out is scoped to exactly one path
# ==============================================================================================


def test_a_sibling_field_in_the_same_rule_summary_is_still_compared():
    """`enforced_rule_count` lives next to `files_loaded`. Excluding one must not excuse the
    other — this is the check that would fail if the carve-out were written too broadly."""
    frozen = _response(list(BASE))
    live = _response(list(BASE))
    live["audit_trail"]["rule_summary"]["enforced_rule_count"] = 1
    changed = _changed(frozen, live)
    assert "/audit_trail/rule_summary/enforced_rule_count" in changed
    assert changed["/audit_trail/rule_summary/enforced_rule_count"] == (944, 1)


def test_a_billing_value_elsewhere_in_the_response_is_still_compared():
    frozen = _response(list(BASE))
    live = _response(list(BASE))
    live["coding"]["billable"][0]["amount"] = "99.99"
    assert "/coding/billable[0]/amount" in _changed(frozen, live)


def test_the_carve_out_removes_only_files_loaded_leaves():
    """Every excluded leaf path must be under `files_loaded` and nothing else."""
    leaves = _flatten(_response(list(BASE)))
    kept = _without_files_loaded(leaves)
    removed = set(leaves) - set(kept)
    assert removed == {f"{PATH}[{i}]" for i in range(len(BASE))}
    assert all(p.startswith(PATH) for p in removed)


def test_the_carve_out_does_not_match_a_path_that_merely_starts_the_same():
    """A future `files_loaded_count` sibling must not be swallowed by the prefix test."""
    frozen = _response(list(BASE), files_loaded_count=3)
    live = _response(list(BASE), files_loaded_count=11)
    changed = _changed(frozen, live)
    assert "/audit_trail/rule_summary/files_loaded_count" in changed


# ==============================================================================================
# Against the real snapshot data
# ==============================================================================================


def test_every_batch2_file_is_actually_in_the_live_files_loaded(rules):
    """The carve-out permits new files; this asserts the four really did arrive."""
    for name in (
        "age_restrictions.manual.csv",
        "gender_restrictions.manual.csv",
        "quantity_limits.manual.csv",
        "time_relations.manual.csv",
    ):
        assert name in rules.files_loaded


def test_files_loaded_has_no_duplicates_in_the_real_store(rules):
    """Set semantics hide a double-load, so assert the property directly on the real store."""
    assert len(rules.files_loaded) == len(set(rules.files_loaded))


def test_no_behavioural_value_moved_in_any_frozen_snapshot_on_this_branch():
    """The relaxation's real justification, stated as the property that actually holds.

    The batch 2 report (§1) says the four files were materialised "without touching any of the
    nine frozen golden files". That is true of the data commit itself, but not of the branch: the
    follow-up commit that taught `refreeze_rule_coverage.py` the same `files_loaded` lesson did
    re-freeze all nine. What matters is that the re-freeze was **purely additive** — the only
    edit in any of them is new filenames appearing in `files_loaded`. No line was removed, and no
    value changed.

    That is the claim worth defending, so it is the one asserted here: across every golden file
    on this branch, every added line is a `files_loaded` filename entry and nothing was deleted.
    """
    import re
    import subprocess

    from app.config import REPO_ROOT as repo_root

    # Scope the window to batch 2 itself — the commit that introduced the four rule files, and
    # everything after it. Deliberately *not* the merge base against main: that range also spans
    # coverage-sprint batch 1, which added 25 Ziffern and legitimately moved rule counts in every
    # snapshot. Widening this window would make the test fail for a reason batch 2 did not cause.
    # `git` itself is absent from the container image (see `test_golden_snapshot.py::_in_git_repo`,
    # which guards the same way) — that raises `FileNotFoundError` before `subprocess.run` produces
    # a returncode to check, so it needs its own catch rather than folding into the checks below.
    try:
        intro = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%H", "--", "data/rules/quantity_limits.manual.csv"],
            capture_output=True, text=True, cwd=repo_root,
        )
    except (FileNotFoundError, NotADirectoryError):
        pytest.skip("git is not available (running from a built image)")
    if intro.returncode != 0 or not intro.stdout.strip():
        pytest.skip("not in a git checkout that carries the batch 2 history")
    first_commit = intro.stdout.split()[-1]

    diff = subprocess.run(
        ["git", "diff", "-U0", f"{first_commit}^", "HEAD", "--", "logic/tests/golden"],
        capture_output=True, text=True, cwd=repo_root,
    )
    assert diff.returncode == 0

    added, removed = [], []
    for line in diff.stdout.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added.append(line[1:].strip())
        elif line.startswith("-"):
            removed.append(line[1:].strip())

    assert removed == [], f"a frozen snapshot lost a line on this branch: {sorted(set(removed))}"

    csv_entry = re.compile(r'^"[A-Za-z0-9_.]+\.csv",?$')
    unexpected = sorted({a for a in added if not csv_entry.match(a)})
    assert unexpected == [], (
        f"a frozen snapshot gained something other than a rule filename: {unexpected}"
    )
