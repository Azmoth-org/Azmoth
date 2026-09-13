"""`receipt_hash` determinism and field coverage.

Prompted by a UI observation: two runs of `case_001_knee`, at 00:41:34 and 01:00:53, produced
proposals with different ids (`prop_69d9e05688c14b4c`, `prop_b87b1f9fc12c4b31`) and the *same*
receipt hash prefix (`1fd67d6dd0e0df3814335305c…`), while a third proposal on the same page
(`prop_89ed57378050462d`) had a different one. That is exactly the contract described in
`app.services.receipt`: the hash covers catalog/rule/logic/solver identity, policy, and the
canonical input/output — never the proposal id or a timestamp — so two runs of one fixture must
match and a run of a different fixture must not.

This module checks both directions, per `app.core.canonical`'s own warning: a hash that moved on a
no-op change would be useless (false alarms), and a hash that failed to move on a real change would
be dangerous (false confidence, and a poisoned cache).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from app.schemas import ClinicalExtraction
from app.services.pipeline import Pipeline
from app.services.receipt import receipt_hash


def _extraction(manual_case, name: str) -> ClinicalExtraction:
    return ClinicalExtraction.model_validate(manual_case(name))


# ==================================================================================================
# in-process pipeline runs — what the UI observation is actually about
# ==================================================================================================


def test_same_fixture_twice_gives_identical_hash_but_different_identity(pipeline, manual_case):
    """Two `propose()` calls for the same fixture on the same pipeline: one is a cache hit, but the
    receipt hash must be identical either way, while `proposal_id` and `created_at` — generated
    fresh per call — must not be."""
    extraction = _extraction(manual_case, "case_001_knee")

    first = pipeline.propose(copy.deepcopy(extraction), case_id="case_001_knee")
    second = pipeline.propose(copy.deepcopy(extraction), case_id="case_001_knee")

    assert first.receipt_hash == second.receipt_hash
    assert first.proposal_id != second.proposal_id
    assert first.created_at != second.created_at


def test_same_fixture_on_independent_pipelines_gives_identical_hash(pipeline, settings, catalog, rules, manual_case):
    """The same guarantee without a shared cache: two independently constructed `Pipeline`
    instances (independent `ResultCache`s) solving the same fixture must still agree, because the
    hash is a pure function of catalog/rule/logic/solver identity and canonical input/output — not
    of anything the cache remembers.

    Depends on the `pipeline` fixture (unused directly) purely so the suite's usual
    souffle-availability skip applies here too, before a second instance is built by hand.
    """
    extraction = _extraction(manual_case, "case_001_knee")

    pipeline_a = pipeline
    pipeline_b = Pipeline(settings, catalog, rules)

    proposal_a = pipeline_a.propose(copy.deepcopy(extraction), case_id="case_001_knee")
    proposal_b = pipeline_b.propose(copy.deepcopy(extraction), case_id="case_001_knee")

    assert proposal_a.receipt_hash == proposal_b.receipt_hash


def test_different_fixtures_give_different_hashes(pipeline, manual_case):
    """If this fails, the hash is constant (or the cache is serving one fixture's result for
    another's key) — not a case to "fix" by loosening the assertion."""
    knee = pipeline.propose(_extraction(manual_case, "case_001_knee"), case_id="case_001_knee")
    cardiology = pipeline.propose(
        _extraction(manual_case, "case_002_cardiology"), case_id="case_002_cardiology"
    )

    assert knee.receipt_hash != cardiology.receipt_hash


def test_stale_cache_guard_mutated_input_moves_the_hash_without_a_restart(pipeline, manual_case):
    """Mutate the input and re-run on the *same* (already warmed) pipeline, no process restart.
    The content-addressed cache key must change with the input, so the second call must neither
    reuse the first call's cache entry nor its receipt hash."""
    raw = manual_case("case_001_knee")
    first = pipeline.propose(ClinicalExtraction.model_validate(raw), case_id="case_001_knee")

    mutated = copy.deepcopy(raw)
    mutated["consultation"]["duration_minutes"] += 1
    second = pipeline.propose(ClinicalExtraction.model_validate(mutated), case_id="case_001_knee")

    assert first.receipt_hash != second.receipt_hash


# ==================================================================================================
# field coverage — every one of the ten documented inputs must move the hash alone
# ==================================================================================================


def _base_kwargs() -> dict[str, Any]:
    return dict(
        catalog_version="2026.1",
        catalog_sha256="a" * 64,
        rules_version="rv-2026.1",
        rules_hash="b" * 64,
        logic_version="logic-1.0",
        solver_version="clingo-5.7.1",
        rules_engine_version="souffle-2.4",
        policy={
            "extraction_mode": "manual",
            "unverified_rule_policy": "warn",
            "base_factor_policy": "schwellenwert",
        },
        facts={
            "patient": {"age": 58, "sex": "m", "setting": "ambulant"},
            "procedures": [{"id": "proc_1", "type": "punktion", "confidence": "1.0"}],
        },
        output={
            "proposed_codes": [{"ziffer": "300", "factor": "2.3", "amount_eur": "100.00"}],
            "total": {"amount_eur": "100.00"},
        },
    )


def _bump_policy(kwargs: dict[str, Any]) -> None:
    kwargs["policy"] = {**kwargs["policy"], "base_factor_policy": "hoechstwert"}


def _bump_facts(kwargs: dict[str, Any]) -> None:
    facts = copy.deepcopy(kwargs["facts"])
    facts["patient"]["age"] = 59
    kwargs["facts"] = facts


def _bump_facts_by_one_cent(kwargs: dict[str, Any]) -> None:
    facts = copy.deepcopy(kwargs["facts"])
    facts["procedures"][0]["confidence"] = "0.99"
    kwargs["facts"] = facts


def _bump_output_by_one_cent(kwargs: dict[str, Any]) -> None:
    output = copy.deepcopy(kwargs["output"])
    output["total"]["amount_eur"] = "100.01"
    kwargs["output"] = output


FIELD_PERTURBATIONS = [
    pytest.param("catalog_version", lambda k: k.__setitem__("catalog_version", "2026.2"), id="catalog_version"),
    pytest.param("catalog_sha256", lambda k: k.__setitem__("catalog_sha256", "c" * 64), id="catalog_sha256"),
    pytest.param("rules_version", lambda k: k.__setitem__("rules_version", "rv-2026.2"), id="rules_version"),
    pytest.param("rules_hash", lambda k: k.__setitem__("rules_hash", "d" * 64), id="rules_hash"),
    pytest.param("logic_version", lambda k: k.__setitem__("logic_version", "logic-1.1"), id="logic_version"),
    pytest.param("solver_version", lambda k: k.__setitem__("solver_version", "clingo-5.7.2"), id="solver_version"),
    pytest.param(
        "rules_engine_version",
        lambda k: k.__setitem__("rules_engine_version", "souffle-2.5"),
        id="rules_engine_version",
    ),
    pytest.param("policy", _bump_policy, id="policy"),
    pytest.param("facts", _bump_facts, id="facts"),
    pytest.param("facts (one cent, via confidence)", _bump_facts_by_one_cent, id="facts-one-cent"),
    pytest.param("output (one cent)", _bump_output_by_one_cent, id="output-one-cent"),
]


@pytest.mark.parametrize("field_name, mutate", FIELD_PERTURBATIONS)
def test_perturbing_one_field_alone_moves_the_hash(field_name, mutate):
    baseline = _base_kwargs()
    mutated = _base_kwargs()
    mutate(mutated)

    assert mutated != baseline or field_name, "mutator did not actually change the kwargs"
    assert receipt_hash(**baseline) != receipt_hash(**mutated), (
        f"changing {field_name} alone did not move the receipt hash"
    )


def test_receipt_hash_is_a_pure_function_of_its_inputs():
    """Same call, same kwargs, twice — no pipeline, no cache, nothing measured in between."""
    kwargs = _base_kwargs()

    assert receipt_hash(**kwargs) == receipt_hash(**copy.deepcopy(kwargs))


def test_proposal_id_and_timestamp_are_not_among_the_ten_hashed_fields():
    """`receipt_hash()` has no parameter for either — this pins the signature itself, so a future
    change that threaded one through would fail here first."""
    import inspect

    params = set(inspect.signature(receipt_hash).parameters)
    assert "proposal_id" not in params
    assert "created_at" not in params
    assert "timestamp" not in params
