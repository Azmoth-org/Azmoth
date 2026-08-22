"""The golden snapshots: frozen, committed, and compared against the live engine.

`logic/tests/golden/case_001_knee.golden.normalized.json` was produced by the POC engine before
this migration and is committed **byte-for-byte unchanged**. That is the whole point: it is the
record of what the previous implementation billed, so it is what proves the migration did not move
a single number.

The comparison is a *subset* comparison, deliberately:

- every field the snapshot contains must still be present and identical — that is the migration
  check, and it is strict;
- the response may have gained fields (the production fixes added `missing_documentation`,
  `logic_version`, `rule_coverage_detail`, `solver_status`), and those are enumerated explicitly
  below rather than tolerated silently.

Regenerating the snapshot instead would make this file assert nothing.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from app.config import CASES_DIR, GOLDEN_DIR, REPO_ROOT
from app.core.canonical import canonical
from tests.conftest import solve_payload

CASES = sorted(p.name for p in CASES_DIR.iterdir() if (p / "input.json").exists())
GOLDEN = GOLDEN_DIR / "case_001_knee.golden.normalized.json"

#: Response fields added since the POC produced the frozen snapshots. Every entry is a deliberate
#: contract decision; anything else appearing is a change nobody declared, and
#: `test_no_undeclared_field_was_added` fails on it. A declared entry covers its whole subtree.
#:
#: Adding a line here is not a formality — it is the moment to ask whether the field belongs in the
#: contract at all. It must never be used to wave through a *changed* value: that is the other
#: test, and it has no allow-list.
FIELDS_ADDED_SINCE_POC = {
    # the migration's seven production fixes
    "/coding/missing_documentation",
    "/audit_trail/logic_version",
    "/audit_trail/rule_coverage_detail",
    "/audit_trail/solver_status",
    # contract polish, from frontend feedback: a blocked position now carries its own proof
    # instead of the client joining it out of audit_trail.per_code
    "/coding/blocked_codes/proof",
    # `rule_summary` is the rule store's own dict, passed through untyped; it gained the
    # policy-independent unverified count that backs RuleCoverage.unverified_rule_count
    "/audit_trail/rule_summary/unverified_constraint_rules",
}


def _in_git_repo() -> bool:
    """Ask git rather than look for a `.git` directory.

    The directory check breaks the moment the engine is a workspace inside a monorepo: `.git` sits
    two levels up. And the container image has no git binary at all, which raises rather than
    returning non-zero — that is exactly the "running from a built image" case, so it answers False.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
    except (FileNotFoundError, NotADirectoryError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def _flatten(node, prefix=""):
    """Every leaf path in a nested structure, as `/a/b[0]/c` → value."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            out.update(_flatten(value, f"{prefix}/{key}"))
        return out
    if isinstance(node, list):
        out = {}
        for index, value in enumerate(node):
            out.update(_flatten(value, f"{prefix}[{index}]"))
        return out or {prefix: []}
    return {prefix: node}


# ------------------------------------------------------------------------------------------
# the snapshot exists and is committed
# ------------------------------------------------------------------------------------------


def test_golden_snapshots_exist():
    """The failure this prevents: the snapshot is deleted or gitignored, every run prints
    "no golden snapshot found" as a *warning*, and the gate keeps passing against nothing."""
    missing = [name for name in CASES if not (GOLDEN_DIR / f"{name}.golden.normalized.json").exists()]

    assert missing == [], f"missing golden snapshots: {missing}"


def test_golden_snapshot_is_not_gitignored():
    """`git check-ignore` exits 0 when a path IS ignored."""
    if not _in_git_repo():
        pytest.skip("not a git checkout (running from a built image)")

    result = subprocess.run(
        ["git", "check-ignore", str(GOLDEN)], capture_output=True, text=True, cwd=REPO_ROOT
    )

    assert result.returncode != 0, f"{GOLDEN} must not be gitignored"


def test_golden_snapshot_is_valid_json_with_the_expected_shape():
    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))

    assert set(payload) == {"extraction", "coding", "audit_trail"}
    assert payload["coding"]["proposed_codes"], "a snapshot with no lines gates nothing"
    assert payload["coding"]["blocked_codes"], "case_001 must record its blocked codes"
    assert payload["coding"]["total"]["amount_eur"]


def test_golden_snapshot_has_the_volatile_fields_stripped():
    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))

    assert "timestamp" not in payload["audit_trail"]
    assert "stage_timings_ms" not in payload["audit_trail"]


def test_golden_snapshot_agrees_with_expected_json(expected_case):
    """Two files describe case_001's outcome. They must not drift apart."""
    expected = expected_case("case_001_knee")
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    golden_accepted = sorted(line["ziffer"] for line in golden["coding"]["proposed_codes"])
    assert golden_accepted == sorted(expected["accepted_ziffern"])

    assert golden["coding"]["total"]["amount_eur"] == expected["total_amount_eur"]
    assert golden["coding"]["total"]["punkte"] == expected["total_punkte"]
    assert golden["audit_trail"]["catalog_version"] == expected["catalog_version"]

    golden_blocked = {b["ziffer"] for b in golden["coding"]["blocked_codes"]}
    for entry in expected["blocked_ziffern"]:
        assert entry["ziffer"] in golden_blocked


# ------------------------------------------------------------------------------------------
# the migration check: the live engine still produces the frozen result
# ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", CASES)
def test_the_engine_still_reproduces_the_frozen_snapshot(client, manual_case, golden_case, name):
    """Every value the POC engine recorded, reproduced field for field by the migrated engine.

    A failure here is a migrated *behaviour* difference, not a path problem, and must be
    investigated rather than papered over by regenerating the snapshot.
    """
    live = canonical(solve_payload(client, manual_case(name)))
    frozen = canonical(golden_case(name))

    frozen_leaves = _flatten(frozen)
    live_leaves = _flatten(live)

    missing = sorted(p for p in frozen_leaves if p not in live_leaves)
    assert missing == [], f"{name}: fields the snapshot has and the engine no longer emits: {missing}"

    changed = {
        path: (value, live_leaves[path])
        for path, value in frozen_leaves.items()
        if live_leaves[path] != value
    }
    assert changed == {}, f"{name}: values changed since the POC: {changed}"


@pytest.mark.parametrize("name", CASES)
def test_no_undeclared_field_was_added(client, manual_case, golden_case, name):
    """The other half: the response may only have grown in the ways this migration declared."""
    live = canonical(solve_payload(client, manual_case(name)))
    frozen = canonical(golden_case(name))

    def keys(node, prefix=""):
        out = set()
        if isinstance(node, dict):
            for key, value in node.items():
                out.add(f"{prefix}/{key}")
                out |= keys(value, f"{prefix}/{key}")
        elif isinstance(node, list):
            for value in node:
                out |= keys(value, prefix)
        return out

    # A declared subtree covers everything inside it: declaring `/coding/missing_documentation`
    # is a decision about that field, not about each of its five members.
    added = {
        path
        for path in keys(live) - keys(frozen)
        if not any(path.startswith(f"{declared}/") for declared in FIELDS_ADDED_SINCE_POC)
    }

    assert added <= FIELDS_ADDED_SINCE_POC, (
        f"{name}: undeclared new response fields {sorted(added - FIELDS_ADDED_SINCE_POC)}. "
        "Add them to FIELDS_ADDED_SINCE_POC only after deciding they belong in the contract."
    )
