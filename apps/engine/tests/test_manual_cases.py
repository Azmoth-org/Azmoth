"""Run every bundled synthetic case through the API and check its expected.json.

These are the end-to-end acceptance tests: structured clinical entities in, an auditable invoice
draft out, no model anywhere. The cases live in `logic/tests/cases/`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import CASES_DIR
from app.core.canonical import canonical
from tests.conftest import solve_payload

CASES = sorted(p.name for p in CASES_DIR.iterdir() if (p / "input.json").exists())


def test_there_are_synthetic_cases():
    assert CASES == ["case_001_knee", "case_002_cardiology", "case_003_dermatology"]


@pytest.mark.parametrize("name", CASES)
def test_case_accepts_the_expected_ziffern(client, manual_case, expected_case, name):
    result = solve_payload(client, manual_case(name))
    expected = expected_case(name)

    accepted = sorted(line["ziffer"] for line in result["coding"]["proposed_codes"])
    assert accepted == sorted(expected["accepted_ziffern"]), name


@pytest.mark.parametrize("name", CASES)
def test_case_blocks_the_expected_ziffern(client, manual_case, expected_case, name):
    result = solve_payload(client, manual_case(name))
    expected = expected_case(name)

    blocked = {b["ziffer"]: b for b in result["coding"]["blocked_codes"]}
    for entry in expected["blocked_ziffern"]:
        ziffer = entry["ziffer"]
        assert ziffer in blocked, f"{name}: expected GOÄ {ziffer} to be blocked"
        actual = blocked[ziffer]
        assert entry["reason_contains"] in actual["reason"], f"{name}: GOÄ {ziffer}"
        if "blocked_by" in entry:
            assert actual["blocked_by"] == entry["blocked_by"], f"{name}: GOÄ {ziffer}"
        assert actual["explanation"], f"{name}: GOÄ {ziffer} blocked without explanation"


@pytest.mark.parametrize("name", CASES)
def test_case_matches_expected_factors(client, manual_case, expected_case, name):
    result = solve_payload(client, manual_case(name))
    expected = expected_case(name)

    lines = {line["ziffer"]: line for line in result["coding"]["proposed_codes"]}
    for entry in expected.get("factor_expectations", []):
        ziffer = entry["ziffer"]
        assert ziffer in lines, f"{name}: GOÄ {ziffer} is not on the invoice"
        line = lines[ziffer]
        factor = Decimal(line["factor"])

        if "factor" in entry:
            assert factor == Decimal(entry["factor"]), f"{name}: GOÄ {ziffer}"
        if "min_factor" in entry:
            assert factor >= Decimal(entry["min_factor"]), f"{name}: GOÄ {ziffer}"
        if "max_factor" in entry:
            assert factor <= Decimal(entry["max_factor"]), f"{name}: GOÄ {ziffer}"
        if "requires_justification" in entry:
            assert line["justification_required"] is entry["requires_justification"], (
                f"{name}: GOÄ {ziffer}"
            )
            if entry["requires_justification"]:
                assert line["justification_present"] is True, f"{name}: GOÄ {ziffer}"


@pytest.mark.parametrize("name", CASES)
def test_case_matches_expected_total(client, manual_case, expected_case, name):
    result = solve_payload(client, manual_case(name))
    expected = expected_case(name)
    total = result["coding"]["total"]

    assert Decimal(total["amount_eur"]) == Decimal(expected["total_amount_eur"]), name
    assert total["punkte"] == expected["total_punkte"], name
    assert total["minderung_applied"] is expected["minderung_applied"], name


@pytest.mark.parametrize("name", CASES)
def test_case_emits_the_expected_warning_types(client, manual_case, expected_case, name):
    result = solve_payload(client, manual_case(name))
    expected = expected_case(name)

    types = {w["type"] for w in result["coding"]["warnings"]}
    for required in expected.get("warnings_contain", []):
        assert required in types, f"{name}: expected a '{required}' warning, got {sorted(types)}"


@pytest.mark.parametrize("name", CASES)
def test_case_matches_the_pinned_catalog_snapshot(client, manual_case, expected_case, name):
    """Totals depend on the catalog, so the expectation pins which snapshot it was written for."""
    result = solve_payload(client, manual_case(name))

    assert result["audit_trail"]["catalog_version"] == expected_case(name)["catalog_version"], (
        f"{name}: the catalog snapshot changed; re-verify the expected totals before updating"
    )


@pytest.mark.parametrize("name", CASES)
def test_case_analog_expectations(client, manual_case, expected_case, name):
    result = solve_payload(client, manual_case(name))
    expected = expected_case(name)

    analogs = {a["entity_type"]: a for a in result["coding"]["analog_codes"]}
    for entry in expected.get("analog_expectations", []):
        entity = entry["entity_type"]
        assert entity in analogs, f"{name}: expected an analog decision for {entity}"
        assert analogs[entity]["ziffer"] == entry["ziffer"], f"{name}: {entity}"
        assert analogs[entity]["requires_human_review"] is entry["requires_human_review"]

    if not expected.get("analog_expectations"):
        assert analogs == {}, f"{name}: unexpected analog decisions {sorted(analogs)}"


@pytest.mark.parametrize("name", CASES)
def test_case_is_deterministic(client, manual_case, name):
    """Same input + same catalog + same rules = same output, field for field.

    Volatile fields — the wall-clock timestamp, the measured stage timings, the per-request
    proposal id — are stripped by `canonical()`; nothing that decides money, codes or provenance
    is. tests/test_golden_normalization.py asserts exactly that, in both directions.
    """
    first = solve_payload(client, manual_case(name))
    second = solve_payload(client, manual_case(name))

    assert canonical(first) == canonical(second), name


@pytest.mark.parametrize("name", CASES)
def test_case_receipt_hash_is_stable(client, manual_case, name):
    """The stronger determinism claim: the same run is identified by the same 64-hex receipt."""
    first = client.post("/api/v1/solve", json={"extraction": manual_case(name)}).json()
    second = client.post("/api/v1/solve", json={"extraction": manual_case(name)}).json()

    assert len(first["receipt_hash"]) == 64
    assert first["receipt_hash"] == second["receipt_hash"], name


@pytest.mark.parametrize("name", CASES)
def test_case_never_violates_a_rule_it_enforces(client, manual_case, rules, name):
    result = solve_payload(client, manual_case(name))
    charged = {line["ziffer"] for line in result["coding"]["proposed_codes"]}

    for rule in rules.exclusions:
        assert not (rule.from_ziffer in charged and rule.to_ziffer in charged), (
            f"{name}: {rule.rule_id} violated"
        )
    for zrule in rules.zielleistung:
        assert not (zrule.parent_ziffer in charged and zrule.child_ziffer in charged), (
            f"{name}: {zrule.rule_id} violated"
        )


@pytest.mark.parametrize("name", CASES)
def test_case_factors_stay_inside_their_legal_band(client, manual_case, catalog, rules, name):
    result = solve_payload(client, manual_case(name))

    for line in result["coding"]["proposed_codes"]:
        band = catalog.factor_band(line["ziffer"])
        cap = rules.factor_cap(line["ziffer"])
        ceiling = min(band.max, cap.max_factor) if cap else band.max
        factor = Decimal(line["factor"])

        assert Decimal(1) <= factor <= ceiling, f"{name}: GOÄ {line['ziffer']} at {factor}"
        if factor > band.threshold:
            assert line["justification_present"], (
                f"{name}: GOÄ {line['ziffer']} exceeds the Schwellenwert without a reason"
            )


@pytest.mark.parametrize("name", CASES)
def test_case_uses_only_synthetic_data(manual_case, name):
    """A guard against a real record ever being committed as a fixture."""
    payload = manual_case(name)

    assert "synthetic" in payload.get("notes", "").lower(), (
        f"{name}: every bundled case must state that it is synthetic"
    )
    blob = str(payload).lower()
    for marker in ("geb.", "geboren", "versicherungsnummer", "@", "straße", "strasse"):
        assert marker not in blob, f"{name}: looks like it contains identifying data ({marker})"


# ------------------------------------------------------------------------------------------
# the operations CLI
# ------------------------------------------------------------------------------------------


def _cli():
    """Loaded by path: `scripts/` is tooling, not an importable package."""
    import importlib.util

    from app.config import ENGINE_DIR

    spec = importlib.util.spec_from_file_location(
        "engine_cli", ENGINE_DIR / "scripts" / "engine_cli.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_runs_a_case():
    assert _cli().main(["solve", str(CASES_DIR / "case_001_knee" / "input.json")]) == 0


def test_cli_rejects_a_schema_violation(tmp_path):
    import json

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"procedures": [{"typ": "punktion"}]}), encoding="utf-8")

    assert _cli().main(["solve", str(bad)]) == 2


def test_cli_check_passes():
    assert _cli().main(["check"]) == 0


def test_cli_check_souffle_passes():
    assert _cli().main(["check-souffle"]) == 0
