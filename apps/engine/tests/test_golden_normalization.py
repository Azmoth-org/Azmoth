"""The normalisation applied before two runs are compared.

In the POC this logic lived in `verify_case_001.py`, a script that drove a running API. The script
is not migrated (docs/migration/MIGRATION_PLAN.md §2); the normaliser is, as
`app.core.canonical`, because it is not test scaffolding — the content-addressed cache key and the
receipt hash are both computed over its output, so the whole engine now depends on it being right.

Two failure modes are being prevented:

- **False alarms.** Measured timings differ every run. If they were not stripped, the determinism
  check would fail on a system that is in fact deterministic, and the natural reaction would be to
  weaken or delete the check.
- **False confidence.** If normalisation stripped too much — or a real field were added to
  `VOLATILE_KEYS` by accident — the golden snapshot would stop noticing genuine changes, and so
  would the cache: two different results would hash to one key. That is worse, because it fails
  silently.

Both directions are asserted here.
"""

from __future__ import annotations

import copy
import json

import pytest

from app.config import GOLDEN_DIR
from app.core.canonical import VOLATILE_KEYS, canonical, sha256_of

GOLDEN = GOLDEN_DIR / "case_001_knee.golden.normalized.json"


def test_canonical_removes_stage_timings():
    a = {
        "coding": {"total": {"amount_eur": "130.39"}},
        "stage_timings_ms": {"bridge": 0.93, "souffle": 11.2},
        "timestamp": "2026-07-25T10:00:00Z",
    }
    b = {
        "coding": {"total": {"amount_eur": "130.39"}},
        "stage_timings_ms": {"bridge": 0.33, "souffle": 9.8},
        "timestamp": "2026-07-25T10:00:01Z",
    }

    assert canonical(a) == canonical(b)


def test_canonical_detects_real_difference():
    a = {"coding": {"total": {"amount_eur": "130.39"}}, "stage_timings_ms": {"bridge": 0.93}}
    b = {"coding": {"total": {"amount_eur": "130.40"}}, "stage_timings_ms": {"bridge": 0.33}}

    assert canonical(a) != canonical(b)


def test_volatile_keys_covers_the_fields_the_api_actually_emits():
    """Guards the names, not just the behaviour: renaming one of these in the API without updating
    this set would silently reintroduce the false-alarm failure."""
    assert "stage_timings_ms" in VOLATILE_KEYS
    assert "timestamp" in VOLATILE_KEYS
    assert "solve_ms" in VOLATILE_KEYS, "measured solver wall-clock is not part of the answer"
    assert "solve_time_ms" in VOLATILE_KEYS, "the published solve metric is a measurement"
    assert "total_time_ms" in VOLATILE_KEYS, "so is the published end-to-end metric"
    assert "ground_ms" in VOLATILE_KEYS and "build_ms" in VOLATILE_KEYS
    assert "proposal_id" in VOLATILE_KEYS, "a per-request id must not move the cache key"
    assert "created_at" in VOLATILE_KEYS


def test_volatile_keys_does_not_strip_anything_load_bearing():
    """A field that decides money, codes or provenance must never be normalised away."""
    load_bearing = {
        "amount_eur",
        "amount_cent_unrounded",
        "punkte",
        "factor",
        "ziffer",
        "proposed_codes",
        "blocked_codes",
        "total",
        "reason",
        "rule_id",
        "legal_basis",
        "proof",
        "catalog_version",
        "catalog_sha256",
        "rules_version",
        "rules_hash",
        "rule_coverage",
        "logic_version",
        "warnings",
        "minderung_rate",
        "justification",
        "missing_documentation",
        "receipt_hash",
        "status",
        "enforced_rule_count",
        "advisory_rule_count",
    }
    overlap = load_bearing & VOLATILE_KEYS

    assert overlap == set(), f"normalisation would hide real changes in: {sorted(overlap)}"


@pytest.mark.parametrize(
    "path,mutate",
    [
        ("total amount", lambda d: d["coding"]["total"].__setitem__("amount_eur", "999.99")),
        ("a line factor", lambda d: d["coding"]["proposed_codes"][0].__setitem__("factor", "3.5")),
        ("a line ziffer", lambda d: d["coding"]["proposed_codes"][0].__setitem__("ziffer", "9999")),
        ("a blocked reason", lambda d: d["coding"]["blocked_codes"][0].__setitem__("reason", "x")),
        ("catalog identity", lambda d: d["audit_trail"].__setitem__("catalog_sha256", "0" * 64)),
        ("rule coverage", lambda d: d["audit_trail"].__setitem__("rule_coverage", "full")),
        ("a proof step", lambda d: d["coding"]["proposed_codes"][0].__setitem__("proof", [])),
        ("dropping a line", lambda d: d["coding"]["proposed_codes"].pop()),
    ],
)
def test_canonical_notices_every_kind_of_meaningful_change(path, mutate):
    """Run against the committed snapshot, so this exercises the real response shape rather than a
    toy dict — the shape is what a future refactor would change."""
    original = json.loads(GOLDEN.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(original)
    mutate(mutated)

    assert canonical(original) != canonical(mutated), (
        f"normalisation hides a change to {path} — the golden snapshot would not catch it"
    )
    assert sha256_of(original) != sha256_of(mutated), (
        f"a change to {path} does not move the hash — the cache would serve a stale result"
    )


def test_canonical_is_order_insensitive_for_lists():
    """Lists are sorted so an incidental ordering change is not reported as a regression."""
    a = {"items": [{"z": "1"}, {"z": "2"}]}
    b = {"items": [{"z": "2"}, {"z": "1"}]}

    assert canonical(a) == canonical(b)


def test_canonical_is_idempotent():
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))

    assert canonical(data) == canonical(canonical(data))


def test_the_frozen_snapshot_is_already_canonical():
    """The snapshot was written in canonical form, so re-normalising it must be a no-op. If this
    fails, the snapshot was hand-edited and comparisons against it are unreliable."""
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))

    assert data == canonical(data), "the committed snapshot is not in canonical form"


def test_decimals_are_hashed_as_exact_strings_never_floats():
    """`float(Decimal("1.15"))` is not 1.15. A cache key that went through float would collide."""
    from decimal import Decimal

    assert canonical({"f": Decimal("1.15")}) == {"f": "1.15"}
    assert canonical({"f": Decimal("2.30")}) != canonical({"f": Decimal("2.3")}), (
        "2.30 and 2.3 are the same number but not the same recorded value"
    )
