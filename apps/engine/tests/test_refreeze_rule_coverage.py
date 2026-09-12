"""`scripts/refreeze_rule_coverage.py`'s own diffing logic, unit-tested directly.

The tool exists to keep one promise: it moves rule-coverage metadata and refuses to move anything
else. `rule_summary.files_loaded` is the one leaf that promise needed a second rule for — see the
module docstring — and the blind spot this covers was real: before this fix, the script read a
coverage-sprint batch that only added new rule-file formats (no enforced-rule-count change at all)
as "!! BEHAVIOUR MOVED" on 6 of 9 cases, because every later filename in the sorted list shifted
index. This file is the regression test for that fix, so it cannot come back silently: a files_loaded
reorder/growth must classify as allowed, and — the other half, which must never regress — a real
changed value must still be refused.
"""

from __future__ import annotations

import scripts.refreeze_rule_coverage as refreeze


# ==========================================================================================
# files_loaded — the fixed blind spot
# ==========================================================================================


def test_a_files_loaded_reorder_is_allowed():
    """The exact shape a new rule-file format produces: every existing name is still present,
    just at different indices because a new, alphabetically-earlier filename was inserted."""
    old = ["analog_candidates.csv", "exclusions.csv", "factor_caps.csv"]
    new = ["age_restrictions.manual.csv", "analog_candidates.csv", "exclusions.csv", "factor_caps.csv"]

    assert refreeze.is_allowed(refreeze.FILES_LOADED_PATH, old, new) is True


def test_a_files_loaded_pure_growth_with_no_reorder_is_allowed():
    old = ["exclusions.csv", "factor_caps.csv"]
    new = ["exclusions.csv", "factor_caps.csv", "quantity_limits.manual.csv"]

    assert refreeze.is_allowed(refreeze.FILES_LOADED_PATH, old, new) is True


def test_a_files_loaded_drop_is_not_allowed():
    """The regression this tool exists to catch: a file the frozen snapshot loaded that no longer
    loads is not a harmless reorder, whatever else is true about the new list."""
    old = ["exclusions.csv", "exclusions.manual.csv", "factor_caps.csv"]
    new = ["exclusions.csv", "factor_caps.csv"]  # exclusions.manual.csv vanished

    assert refreeze.is_allowed(refreeze.FILES_LOADED_PATH, old, new) is False


def test_flatten_keeps_files_loaded_as_one_leaf_not_per_index():
    """The mechanism the reorder-tolerance depends on: `files_loaded` must never be exploded into
    `[0]`, `[1]`, … the way every other list in the response still is."""
    doc = {
        "audit_trail": {
            "rule_summary": {"files_loaded": ["a.csv", "b.csv", "c.csv"]},
        },
        "coding": {"proposed_codes": [{"ziffer": "1"}, {"ziffer": "2"}]},
    }

    leaves = refreeze.flatten(doc)

    assert leaves["/audit_trail/rule_summary/files_loaded"] == ["a.csv", "b.csv", "c.csv"]
    assert "/audit_trail/rule_summary/files_loaded[0]" not in leaves
    # A list elsewhere in the same document is still exploded index by index, unaffected — the
    # special case is scoped to exactly this one path, not to "any list of strings".
    assert leaves["/coding/proposed_codes[0]/ziffer"] == "1"
    assert leaves["/coding/proposed_codes[1]/ziffer"] == "2"


# ==========================================================================================
# everything else — must still be refused, exactly as before this fix
# ==========================================================================================


def test_a_known_metadata_leaf_is_still_allowed():
    assert refreeze.is_allowed("/audit_trail/rule_summary/verified_share", "30/30", "35/40") is True


def test_a_changed_verdict_is_not_allowed():
    """The property the whole tool exists for: a Ziffer, factor, amount or verdict moving must
    never be waved through, files_loaded's new leniency included."""
    assert refreeze.is_allowed("/coding/proposed_codes[0]/ziffer", "301", "300") is False


def test_a_changed_amount_is_not_allowed():
    assert refreeze.is_allowed("/coding/total/amount_eur", "78.81", "69.71") is False


def test_an_unlisted_path_that_happens_to_share_a_value_shape_is_not_allowed():
    """Being a fraction-like string is not what makes `verified_share` safe to move — being that
    specific, named leaf is. A lookalike path outside `ALLOWED` gets no benefit of the doubt."""
    assert refreeze.is_allowed("/coding/some_other_ratio", "30/30", "35/40") is False


def test_a_warning_message_quoting_the_counters_is_allowed():
    old = "12 verifizierte Regeln von 30 werden durchgesetzt; 4 Regeln sind nur beratend."
    new = "16 verifizierte Regeln von 30 werden durchgesetzt; 4 Regeln sind nur beratend."

    assert refreeze.is_allowed("/coding/warnings[0]/message", old, new) is True


def test_an_unrelated_warning_at_the_same_index_is_not_allowed():
    assert refreeze.is_allowed("/coding/warnings[0]/message", "old warning text", "new warning text") is False
