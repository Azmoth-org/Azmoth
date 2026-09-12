"""Reproducibility of the Batch 2 layers and of the hashes their data feeds.

A rule that blocks a claim is a legal assertion about somebody's invoice, so "it decided this"
is only half the product — the other half is "it decides the same thing every time, and here is
the trail". This file pins both halves for the three families Batch 2 shipped.

Nothing here is a timing test. Determinism is asserted by running the same input repeatedly in
one process and comparing the *whole* normalised result — verdict, every blocked entry with its
rule id and detail string, and the proof steps — rather than by comparing a wall-clock number or
a single field that could be stable while the rest drifts.
"""

from __future__ import annotations

import json

import pytest

from app.rules.rule_store import RULES_DATA_DIR, RuleStore
from app.schemas import ClinicalExtraction
from app.services.rule_coverage import rules_hash
from tests.conftest import make_bridge

RUNS = 5


def _extraction(*, age: int | None = None, sex: str | None = None):
    return ClinicalExtraction.model_validate(
        {"patient": {"age": age, "sex": sex, "setting": "ambulant"}, "justification_factors": []}
    )


def _normalise(result) -> str:
    """Everything a reviewer would read off the result, in a stable order."""
    return json.dumps(
        {
            "billable": list(result.billable),
            "blocked": sorted(
                [b.ziffer, b.reason, b.rule_id, b.detail, b.legal_basis] for b in result.blocked
            ),
            "proof": sorted([p.ziffer, p.rule] for p in result.proof),
        },
        sort_keys=True,
        ensure_ascii=False,
    )


# ==============================================================================================
# The engine gives the same answer every time
# ==============================================================================================


def test_all_three_layers_firing_at_once_is_deterministic(souffle):
    """One case that trips Mengenbegrenzung, Geschlecht and Alter simultaneously, five times."""
    seen = {
        _normalise(
            souffle.run(
                _extraction(age=42, sex="m"),
                make_bridge(
                    ("a1", "26", 100, "1.0"),
                    ("a2", "27", 100, "1.0"),
                    ("a3", "4601", 100, "1.0"),
                ),
                history_counts={"4601": 3},
            )
        )
        for _ in range(RUNS)
    }
    assert len(seen) == 1, f"{len(seen)} distinct results across {RUNS} identical runs"


@pytest.mark.parametrize(
    ("ziffer", "kwargs", "history"),
    [
        ("4601", {}, {"4601": 3}),
        ("27", {"sex": "m"}, None),
        ("26", {"age": 42}, None),
        ("250a", {"age": 8}, None),
    ],
)
def test_each_layer_is_deterministic_on_its_own(souffle, ziffer, kwargs, history):
    seen = {
        _normalise(
            souffle.run(
                _extraction(**kwargs), make_bridge(("a1", ziffer, 100, "1.0")), history_counts=history
            )
        )
        for _ in range(RUNS)
    }
    assert len(seen) == 1


def test_the_order_positions_arrive_in_does_not_change_the_verdict(souffle):
    """Two claims, both orderings — the same set of decisions, differing only in list order."""
    forward = souffle.run(
        _extraction(age=42, sex="m"),
        make_bridge(("a1", "26", 100, "1.0"), ("a2", "27", 100, "1.0")),
    )
    reverse = souffle.run(
        _extraction(age=42, sex="m"),
        make_bridge(("a1", "27", 100, "1.0"), ("a2", "26", 100, "1.0")),
    )
    assert sorted(forward.billable) == sorted(reverse.billable)
    assert sorted((b.ziffer, b.reason, b.rule_id) for b in forward.blocked) == sorted(
        (b.ziffer, b.reason, b.rule_id) for b in reverse.blocked
    )


# ==============================================================================================
# Every decision carries its trail
# ==============================================================================================


@pytest.mark.parametrize(
    ("ziffer", "kwargs", "history", "reason", "rule_id", "proof_rule"),
    [
        ("4601", {}, {"4601": 3}, "quantity_exceeded", "cnt_man_4601", "blocked_quantity"),
        ("27", {"sex": "m"}, None, "gender_restricted", "gr_man_27", "blocked_gender"),
        ("26", {"age": 42}, None, "age_restricted", "age_man_26", "blocked_age"),
    ],
)
def test_a_block_is_traceable_to_a_rule_a_citation_and_a_proof_step(
    souffle, rules, ziffer, kwargs, history, reason, rule_id, proof_rule
):
    """The auditability claim, per family: the block names a rule, the rule resolves in the
    store, its `legal_basis` is non-empty and matches the CSV, and the Datalog proof names the
    layer that produced it. A verdict that cannot be walked back to a cited sentence is not
    something this product may emit."""
    result = souffle.run(
        _extraction(**kwargs), make_bridge(("a1", ziffer, 100, "1.0")), history_counts=history
    )

    blocked = next(b for b in result.blocked if b.ziffer == ziffer)
    assert blocked.reason == reason
    assert blocked.rule_id == rule_id
    assert blocked.detail, "a block must say what the comparison actually was"

    rule = rules.rule_by_id(rule_id)
    assert rule is not None, f"{rule_id} does not resolve in the rule store"
    assert rule.legal_basis == blocked.legal_basis
    assert rule.legal_basis.strip(), "the cited legal basis is empty"
    assert rule.quote.strip(), "the rule carries no quoted source text"

    proof_rules = {p.rule for p in result.proof if p.ziffer == ziffer}
    assert proof_rule in proof_rules, f"no {proof_rule} proof step for {ziffer}: {proof_rules}"


def test_an_admitted_ziffer_produces_no_batch2_block_in_the_trail(souffle):
    """The negative half: a patient who satisfies every band leaves no trace of these layers."""
    result = souffle.run(
        _extraction(age=8, sex="w"),
        make_bridge(("a1", "26", 100, "1.0"), ("a2", "27", 100, "1.0")),
    )
    assert sorted(result.billable) == ["26", "27"]
    assert result.blocked == []


# ==============================================================================================
# Hashes
# ==============================================================================================


def test_rules_hash_is_stable_across_repeated_computation():
    """`rules_hash` is inside `receipt_hash`. If it moved between two calls on an unchanged tree,
    every receipt this engine has ever issued would be unverifiable."""
    assert len({rules_hash(RULES_DATA_DIR) for _ in range(RUNS)}) == 1


def test_rules_hash_covers_the_batch2_files(tmp_path):
    """The four new CSVs must be inside the hash — otherwise a rule change could ship without
    the receipt moving, which is the failure `receipt_hash` exists to prevent."""
    import shutil

    baseline = rules_hash(RULES_DATA_DIR)
    for name in (
        "quantity_limits.manual.csv",
        "gender_restrictions.manual.csv",
        "age_restrictions.manual.csv",
        "time_relations.manual.csv",
    ):
        copy = tmp_path / name.replace(".csv", "")
        copy.mkdir()
        for f in RULES_DATA_DIR.glob("*"):
            if f.is_file():
                shutil.copy2(f, copy / f.name)
        target = copy / name
        target.write_bytes(target.read_bytes() + b"# touched\n")
        assert rules_hash(copy) != baseline, f"{name} is not covered by rules_hash"


def test_loading_the_store_twice_yields_the_same_corpus():
    """`RuleStore.load` reads a directory; two loads must agree on every Batch 2 row, in order."""
    first, second = RuleStore.load(RULES_DATA_DIR), RuleStore.load(RULES_DATA_DIR)
    for family in ("quantity_limits", "gender_restrictions", "age_restrictions", "time_relations"):
        assert [r.rule_id for r in getattr(first, family)] == [
            r.rule_id for r in getattr(second, family)
        ]
    assert sorted(first.files_loaded) == sorted(second.files_loaded)


def test_no_timestamp_or_random_id_leaks_into_a_batch2_block(souffle):
    """A receipt has to be comparable across runs, so nothing a Batch 2 layer emits may carry a
    clock reading or a fresh uuid. Asserted by re-running and comparing the fields verbatim."""
    import re

    result = souffle.run(
        _extraction(age=42), make_bridge(("a1", "26", 100, "1.0"))
    )
    blocked = next(b for b in result.blocked if b.ziffer == "26")
    blob = f"{blocked.rule_id}|{blocked.detail}|{blocked.legal_basis}|{blocked.explanation}"

    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:", blob), f"a timestamp leaked: {blob}"
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", blob), f"a uuid leaked: {blob}"

    again = souffle.run(_extraction(age=42), make_bridge(("a1", "26", 100, "1.0")))
    repeat = next(b for b in again.blocked if b.ziffer == "26")
    assert blob == f"{repeat.rule_id}|{repeat.detail}|{repeat.legal_basis}|{repeat.explanation}"
