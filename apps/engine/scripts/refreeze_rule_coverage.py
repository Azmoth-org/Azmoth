#!/usr/bin/env python3
"""Re-freeze the golden snapshots after a rule-verification pass — metadata only.

    python scripts/refreeze_rule_coverage.py            # report what would change
    python scripts/refreeze_rule_coverage.py --write    # apply it

Verifying a rule moves the rule-coverage counters that every solve response carries, so the nine
frozen snapshots stop matching. That is expected and says nothing about the engine. What is *not*
expected is a Ziffer, a factor, an amount, a proof or a verdict moving — that is what a falsely
verified rule looks like, and `test_the_engine_still_reproduces_the_frozen_snapshot` exists to
catch it.

`test_golden_snapshot.py` says a failure "must be investigated rather than papered over by
regenerating the snapshot", and this script is built to keep that true rather than to get around
it. It updates ONLY the keys in `ALLOWED` below. If the live engine differs from the snapshot
anywhere else, it refuses to write anything and prints the offending paths — so the one command
someone reaches for after a verification pass cannot quietly absorb a behavioural regression.

Run it after `auto_verify_rules.py`, read the summary, and commit the snapshot diff alongside the
rule diff so a reviewer sees both halves.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

# Before any `app.*` import, for the reason `tests/conftest.py` gives at its own top: `Settings`
# reads the environment once and `get_settings()` caches it. Without this the script solves against
# whatever `DATABASE_URL` points at — in practice the checked-in `test.db`, whose schema is older
# than the models — and dies on a missing column instead of re-freezing anything. The snapshots are
# a pure function of catalog + rules + logic, so an in-memory database is not a shortcut here; it is
# the correct isolation, and it matches what the suite this script serves actually runs against.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["DATABASE_AUTO_CREATE"] = "true"
os.environ["APP_ENV"] = "development"

from app.config import GOLDEN_DIR  # noqa: E402

#: Leaf paths a verification pass is allowed to move. Everything here is a count of rules or a
#: sentence quoting one; none of it is a billing decision.
ALLOWED = (
    "/audit_trail/rule_coverage_detail/advisory_rule_count",
    "/audit_trail/rule_coverage_detail/enforced_rule_count",
    "/audit_trail/rule_coverage_detail/suppressed_unverified_rule_count",
    "/audit_trail/rule_coverage_detail/unverified_rule_count",
    "/audit_trail/rule_coverage_detail/unverified_rules_not_enforced",
    "/audit_trail/rule_coverage_detail/verified_share",
    "/audit_trail/rule_coverage_detail/rules_hash",
    "/audit_trail/rules_hash",
    "/audit_trail/rule_summary/factor_caps_enforced",
    "/audit_trail/rule_summary/exclusions_enforced",
    "/audit_trail/rule_summary/exclusions_mutual",
    "/audit_trail/rule_summary/redundant_rules",
    "/audit_trail/rule_summary/unverified_constraint_rules",
    "/audit_trail/rule_summary/unverified_rules_not_enforced",
    "/audit_trail/rule_summary/verified_share",
)

#: Warning texts quote the counters, so they move for the same reason. Matched by shape rather than
#: by index, because the position of a warning in the list is not stable.
ALLOWED_WARNING_RE = re.compile(
    r"^/coding/warnings\[\d+\]/message$",
)
WARNING_FINGERPRINTS = ("Regelabdeckung ist unvollständig", "verifizierte Regeln von", "nur beratend")


def flatten(node, prefix="") -> dict[str, object]:
    out: dict[str, object] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            out.update(flatten(value, f"{prefix}/{key}"))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            out.update(flatten(value, f"{prefix}[{i}]"))
    else:
        out[prefix] = node
    return out


def is_allowed(path: str, old, new) -> bool:
    if path in ALLOWED:
        return True
    if ALLOWED_WARNING_RE.match(path):
        # Only a coverage sentence, not any warning that happens to sit at that index.
        return any(f in str(old) or f in str(new) for f in WARNING_FINGERPRINTS)
    return False


def set_at(doc, path: str, value) -> None:
    """Assign into the nested document at a `/a/b[0]/c` path."""
    parts = [p for p in path.split("/") if p]
    node = doc
    for part in parts[:-1]:
        node = _step(node, part)
    last = parts[-1]
    if "[" in last:
        name, index = last[:-1].split("[")
        node[name][int(index)] = value
    else:
        node[last] = value


def _step(node, part):
    if "[" in part:
        name, index = part[:-1].split("[")
        return node[name][int(index)]
    return node[part]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="apply the updates (default: report only)")
    args = parser.parse_args(argv)

    # Imported lazily: building the app pulls in the solvers, which --help has no business doing.
    from fastapi.testclient import TestClient

    from app.api import deps
    from app.api.tenancy import ORGANIZATION_ID_HEADER
    from app.core.canonical import canonical
    from app.main import app

    # `tests/conftest.py` builds its client exactly this way (see its `client` fixture). Replicated
    # rather than imported, because `manual_case` and `golden_case` there are pytest fixtures and
    # cannot be called outside a test run; `solve_payload` is a plain helper, so that one is reused.
    sys.path.insert(0, str(ENGINE_ROOT))
    from tests.conftest import CASES_DIR, TEST_ORGANIZATION_ID, solve_payload  # noqa: E402

    def manual_case(name: str) -> dict:
        return json.loads((CASES_DIR / name / "input.json").read_text(encoding="utf-8"))

    cases = sorted(p.name.split(".golden")[0] for p in GOLDEN_DIR.glob("*.golden.normalized.json"))
    print(f"golden cases: {len(cases)}\n")

    violations: dict[str, dict] = {}
    updates: dict[str, dict] = {}

    deps.reset()
    with TestClient(app, headers={ORGANIZATION_ID_HEADER: TEST_ORGANIZATION_ID}) as client:
        for name in cases:
            path = GOLDEN_DIR / f"{name}.golden.normalized.json"
            frozen = json.loads(path.read_text(encoding="utf-8"))
            live = canonical(solve_payload(client, manual_case(name)))

            frozen_leaves = flatten(canonical(frozen))
            live_leaves = flatten(live)

            changed = {
                p: (v, live_leaves[p])
                for p, v in frozen_leaves.items()
                if p in live_leaves and live_leaves[p] != v
            }
            ok = {p: nv for p, (ov, nv) in changed.items() if is_allowed(p, ov, nv)}
            bad = {p: pair for p, pair in changed.items() if p not in ok}

            if bad:
                violations[name] = bad
            if ok:
                updates[name] = ok

            status = "CLEAN" if not changed else ("METADATA ONLY" if not bad else "!! BEHAVIOUR MOVED")
            print(f"  {name:34} {status}  ({len(ok)} allowed, {len(bad)} not)")

    if violations:
        print("\n" + "=" * 90)
        print("REFUSING TO WRITE — these are not rule-coverage metadata:")
        print("=" * 90)
        for name, bad in violations.items():
            for p, (old, new) in bad.items():
                print(f"  {name}: {p}\n      frozen: {old!r}\n      live  : {new!r}")
        print("\nA falsely verified rule looks exactly like this. Identify the rule and revert it:")
        print("  python scripts/auto_verify_rules.py --revert-verdicts <rule_id,...>")
        return 1

    total = sum(len(v) for v in updates.values())
    if not total:
        print("\nNothing to do: every snapshot already matches.")
        return 0

    if not args.write:
        print(f"\n{total} metadata leaves would be updated across {len(updates)} snapshots.")
        print("Re-run with --write to apply.")
        return 0

    for name, ok in updates.items():
        path = GOLDEN_DIR / f"{name}.golden.normalized.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        for p, value in ok.items():
            set_at(doc, p, value)
        # No trailing newline: that is how the frozen snapshots are on disk, and adding one would
        # put a spurious last-line change in every diff this script produces.
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {total} metadata leaves across {len(updates)} snapshots.")
    deps.reset()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
