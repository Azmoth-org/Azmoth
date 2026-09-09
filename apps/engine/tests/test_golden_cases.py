"""The golden suite: five deliveries whose answers were worked out from the data, not the engine.

Each `tests/golden/<case>/` holds a PADnext delivery and an `expected.json`. The expectation was
computed by `tests/golden/oracle.py`, which imports nothing from `app`: `punkte` and `punktwert`
come out of `data/catalogs/goae_current/goae.official.json`, the amounts out of § 5 Abs. 1 GOÄ's
own arithmetic in `Decimal`, and the rule citations out of the `verified=true` rows of
`data/rules/*.csv`. An expectation produced by running the engine and writing down the answer
cannot fail when the engine is wrong — only when it changes — which is why none was.

`test_expectations_are_not_stale` is what keeps that claim true over time: it re-runs the oracle
and asserts the committed JSON still matches, so a catalog or rules bump cannot leave a golden file
describing a fee schedule that no longer exists.

The same five cases run against the live HTTP surface, with a real API key, in
`scripts/e2e_partner_api.py`. This module is the in-process half; that script is the paid-path
half, and both read these same files so the two can never disagree about what "expected" means.
"""

from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.golden import oracle

GOLDEN_DIR = Path(oracle.__file__).resolve().parent
REPO_ROOT = oracle.REPO_ROOT

#: The delivery case A was copied from. Committed twice on purpose — the golden tree has to be
#: readable on its own — and `test_case_a_fixture_is_the_committed_example` is what stops the two
#: drifting apart.
COMMITTED_EXAMPLE = REPO_ROOT / "padnext_example" / "00123456_20240315_ADL_000001_padx.xml"

def _delivery(case: str) -> bytes:
    return oracle.delivery_bytes(case)


def _expected(case: str) -> dict:
    return oracle.load_expected(case)


def _audit(client: TestClient, case: str):
    """POST one golden delivery to the partner endpoint under a real minted key."""
    minted = client.post("/api/v1/settings/api-keys", json={"name": f"golden-{case}"})
    assert minted.status_code == 201, minted.text
    return client.post(
        "/api/v1/audit/single",
        content=_delivery(case),
        headers={
            "X-API-Key": minted.json()["token"],
            "Content-Type": "application/xml",
            "x-padnext-filename": f"{case}_padx.xml",
        },
    )


def assert_report_matches(report: dict, expected: dict) -> None:
    """One comparator, shared with `scripts/e2e_partner_api.py` — see `oracle.compare_report`."""
    problems = oracle.compare_report(report, expected)
    assert not problems, "\n".join(problems)


# ==========================================================================================
# the expectations themselves
# ==========================================================================================


def test_expectations_are_not_stale():
    """Re-derive every `expected.json` from the catalog and the rule tables and compare.

    This is the test that makes "computed independently" a maintained property rather than a claim
    about one afternoon. A catalog bump that changes a `punkte` value, or a rule review that flips
    a `verified` column, fails here — with the instruction to regenerate — instead of silently
    leaving a golden file that describes a fee schedule nobody bills under any more.
    """
    stale = []
    for case in (*oracle.CASES, *oracle.BUG_CASES):
        committed = json.loads((GOLDEN_DIR / case / "expected.json").read_text(encoding="utf-8"))
        if committed != oracle.build(case):
            stale.append(case)
    assert not stale, (
        f"expectations no longer match data/: {stale}. "
        "Re-derive with `python apps/engine/tests/golden/oracle.py --write`, then read the diff — "
        "a changed euro figure is a changed fee schedule, not a formatting nit."
    )


def test_case_a_fixture_is_the_committed_example():
    """Byte-identical to `padnext_example/`, so the known-answer case cannot drift from the file
    the rest of the repository and the docs talk about."""
    assert COMMITTED_EXAMPLE.exists(), f"{COMMITTED_EXAMPLE} is missing"
    assert _delivery("case_a_known_answer") == COMMITTED_EXAMPLE.read_bytes()


def test_the_oracle_imports_nothing_from_the_engine():
    """The independence claim, enforced. An oracle that imported `app` could only ever agree with
    the engine, which is the one thing a golden expectation must not be able to do."""
    source = (GOLDEN_DIR / "oracle.py").read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in source.splitlines()
        if line.startswith(("import app", "from app")) or " import app" in line
    ]
    assert not offenders, offenders

    # And in a subprocess with the engine unimportable, to catch a transitive import too.
    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(GOLDEN_DIR / "oracle.py")],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert done.returncode == 0, done.stderr
    assert "STALE" not in done.stdout, done.stdout


# ==========================================================================================
# the five cases, over the partner surface
# ==========================================================================================


@pytest.mark.parametrize(
    "case",
    [
        "case_a_known_answer",
        "case_b_verified_exclusion",
        "case_c_verified_factor_cap",
        "case_d_arithmetic_mismatch",
    ],
)
def test_a_golden_delivery_audits_to_its_expected_result(client, case):
    expected = _expected(case)
    response = _audit(client, case)
    assert response.status_code == expected["http_status"], response.text
    assert_report_matches(response.json(), expected["report"])


def test_case_a_every_position_is_chargeable_and_unconfirmed(client):
    """The sentence the amber bucket exists to be able to say: nothing is wrong with this invoice,
    and we still cannot call it correct. Asserted on the prose too, because that reason is what a
    Rechnungsprüfer reads and `docs/api/PARTNER_API.md` §7 is built on it."""
    report = _audit(client, "case_a_known_answer").json()
    for position in report["positions"]:
        assert position["verdict"] == "chargeable", position["positionsnr"]
        assert position["bucket"] == "unconfirmed", position["positionsnr"]
        assert position["accepted_as_claimed"] is True, position["positionsnr"]
        assert "Keine verifizierte Regel" in position["bucket_reason"], position["positionsnr"]
        assert position["verified_rule_ids"] == []


def test_case_a_receipt_is_stable_across_runs(client):
    """Two audits of the same bytes, and the hash the second returns is the first's.

    The prefix is a canary rather than the assertion: it pins the catalog, rule tables, logic,
    solver, policy and response shape that produced 78.81 €, and `app/services/receipt.py` is
    explicit that a change to any of them moves it. Equality of two runs is the property; the
    prefix is what tells a reader *which* engine the golden figures belong to.
    """
    expected = _expected("case_a_known_answer")
    first = _audit(client, "case_a_known_answer").json()["receipt_hash"]
    second = _audit(client, "case_a_known_answer").json()["receipt_hash"]

    assert first, "a completed audit carries a receipt"
    assert first == second, "the same delivery must hash to the same receipt"
    assert first.startswith(expected["receipt_hash_prefix"]), (
        f"receipt moved: {first[:16]} != {expected['receipt_hash_prefix']}. Something in the "
        "catalog, the rules, the logic, the solver, the policy or the response shape changed — "
        "see app/services/receipt.py before touching this expectation."
    )


def test_case_b_cites_the_verified_rule_and_leaves_the_other_line_alone(client):
    """The blocked line names `excl_auto_34_4`; the line that did the excluding is untouched."""
    report = _audit(client, "case_b_verified_exclusion").json()
    blocked = next(p for p in report["positions"] if p["ziffer"] == "4")
    winner = next(p for p in report["positions"] if p["ziffer"] == "34")

    assert blocked["verdict"] == "blocked"
    assert blocked["bucket"] == "confirmed_wrong"
    assert blocked["blocked_by"] == "34"
    assert winner["verdict"] == "chargeable"
    assert winner["bucket"] == "confirmed_fine"

    citations = [f for f in report["findings"] if f["rule_id"] == "excl_auto_34_4"]
    assert citations, f"no finding cites the rule; got {[f['type'] for f in report['findings']]}"
    assert all(f["positionsnr"] == "4" or f["ziffer"] == "4" for f in citations)


def test_case_c_the_cap_convicts_the_over_cap_line_only(client):
    """Above `max_factor` is provable; exactly at it is compliant. The boundary is the test."""
    report = _audit(client, "case_c_verified_factor_cap").json()
    over, at_cap = report["positions"]

    assert Decimal(over["claimed_faktor"]) == Decimal("2.3")
    assert over["bucket"] == "confirmed_wrong"
    assert Decimal(at_cap["claimed_faktor"]) == Decimal("1.0")
    assert at_cap["verdict"] == "chargeable", at_cap["bucket_reason"]
    assert at_cap["bucket"] == "confirmed_fine", at_cap["bucket_reason"]

    cap_finding = next(
        f for f in report["findings"] if f["type"] == "padnext_factor_above_maximum"
    )
    assert cap_finding["rule_id"] == "cap_auto_440"
    assert cap_finding["positionsnr"] == "1", "only the over-cap line is convicted"


def test_case_d_names_the_position_whose_amount_does_not_recompute(client):
    """A wrong `gesamtbetrag` is arithmetic against a SHA-256-pinned catalog, so it is provable —
    and the report has to say which line, not merely that the invoice does not add up."""
    report = _audit(client, "case_d_arithmetic_mismatch").json()
    mismatch = next(f for f in report["findings"] if f["type"] == "padnext_amount_mismatch")

    assert mismatch["positionsnr"] == "1"
    assert mismatch["ziffer"] == "1"
    assert Decimal(report["arithmetic_delta_eur"]) == Decimal("10.00")

    # `unpriceable_claimed_eur` — the report's "nicht nachrechenbar" — stays 0.00, and that is
    # correct rather than a gap: GOÄ 1 *was* priced, its claimed figure simply disagrees with the
    # price. The two are different statements and the contract keeps them apart.
    assert Decimal(report["unpriceable_claimed_eur"]) == Decimal("0.00")
    assert Decimal(report["recomputed_total_eur"]) == Decimal("78.81")


# ==========================================================================================
# case E — the gate
# ==========================================================================================


def test_case_e_an_undeclared_delivery_is_refused_with_the_batched_list(client):
    """No `@echtdaten` is *unknown*, not "probably test data", and unknown is refused.

    Asserted on `error_code` because that is the field the contract says is stable, and on
    `details.errors` because a refusal that named one problem per round trip would cost a partner a
    deploy per mistake.
    """
    expected = _expected("case_e_echtdaten_gate")
    response = _audit(client, "case_e_echtdaten_gate")

    assert response.status_code == expected["http_status"], response.text
    body = response.json()
    assert body["error_code"] == expected["error_code"]

    details = body["details"]
    codes = [error["code"] for error in details["errors"]]
    for wanted in expected["batched_error_codes_include"]:
        assert wanted in codes, codes
    blocking = [error for error in details["errors"] if error["blocking"]]
    assert len(blocking) >= expected["batched_blocking_error_count_at_least"]
    # The fix is copyable, which is the whole point of carrying it in the envelope.
    undeclared = next(e for e in details["errors"] if e["code"] == "echtdaten_undeclared")
    assert "anonymize_padnext.py" in undeclared["command"]


def test_case_e_anonymised_audits_to_case_a(client, tmp_path):
    """Run the real `scripts/anonymize_padnext.py` on the refused delivery and re-submit.

    The script is the one a practice runs on its own machine, on data that has not been anonymised
    yet, so it is invoked as a subprocess exactly as a human would — not imported and monkeypatched.
    """
    raw = tmp_path / "case_e_padx.xml"
    raw.write_bytes(_delivery("case_e_echtdaten_gate"))
    out = tmp_path / "case_e.anonymised_padx.xml"

    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "anonymize_padnext.py"),
            str(raw),
            "-o",
            str(out),
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    assert out.exists(), done.stdout
    assert b'echtdaten="false"' in out.read_bytes(), "the script stamps the declaration"

    minted = client.post("/api/v1/settings/api-keys", json={"name": "golden-case-e"})
    response = client.post(
        "/api/v1/audit/single",
        content=out.read_bytes(),
        headers={
            "X-API-Key": minted.json()["token"],
            "Content-Type": "application/xml",
            "x-padnext-filename": out.name,
        },
    )

    expected = _expected("case_e_echtdaten_gate")["after_anonymisation"]
    assert response.status_code == expected["http_status"], response.text
    assert_report_matches(response.json(), expected["report"])


# ==========================================================================================
# a formerly known defect, now a regular golden case
# ==========================================================================================


def test_findings_are_attributed_per_delivery_and_not_per_positionsnr(client):
    """positionsnr collision, fixed: `app/padnext/audit.py` used to attribute findings to
    positions by `positionsnr` alone, which PADnext scopes to an `<abrechnungsfall>` and not to a
    delivery. Two invoices each numbering their line "1" shared one attribution slot, so a cap
    breach on one convicted the compliant line on the other and moved its euros into
    confirmed_wrong. The audit now keys its per-position aggregation by `id(row)` instead — see
    `errors_per_row` / `verified_defects_per_row` in `audit_delivery`. See docs/api/E2E_GOLDEN.md.
    """
    case = "bug_positionsnr_collision"
    expected = _expected(case)
    response = _audit(client, case)
    assert response.status_code == expected["http_status"], response.text
    assert_report_matches(response.json(), expected["report"])


# ==========================================================================================
# case F and case G — the cross-invoice / cross-date boundary fix
# ==========================================================================================
#
# Both are hand-computed, like `bug_positionsnr_collision` above, rather than derived through
# `oracle.build()`: the oracle's generic per-delivery walker credits and blocks rules over the
# delivery's *whole* claimed-Ziffer set, which is exactly the flat-fact-base bug these two cases
# exist to catch — teaching the oracle to group by `<abrechnungsfall>` and to reason about `datum`
# would just be a second copy of `app/padnext/audit.py`'s own fix, and an oracle that agreed with
# the engine by construction could never catch a regression in it. `expected.json` here was instead
# checked by hand against `data/rules/exclusions.csv` and `logic/datalog/goae_rules.dl`, and against
# a live run of the fixed engine — see docs/api/E2E_GOLDEN.md §5b for the reasoning, in particular
# for why case F's two positions land in `unconfirmed` rather than `confirmed_fine`.


def test_case_f_an_exclusion_does_not_cross_a_patient_boundary(client):
    """GOÄ 34 on one invoice, GOÄ 4 on a different invoice's `<abrechnungsfall>` — two patients.

    Before the fix, `audit_delivery` ground every invoice's positions in one Ziffer-keyed Soufflé
    run, so `excl_auto_34_4` fired the moment both Ziffern appeared anywhere in the delivery and
    convicted invoice 2's GOÄ 4 as `confirmed_wrong`, on the strength of a service invoice 2 never
    claimed. Soufflé now runs once per `<abrechnungsfall>`, so the two invoices' fact bases never
    mix and the exclusion cannot fire on either side.
    """
    case = "case_f_cross_patient_boundary"
    expected = _expected(case)
    response = _audit(client, case)
    assert response.status_code == expected["http_status"], response.text
    report = response.json()
    assert_report_matches(report, expected["report"])

    for position in report["positions"]:
        assert position["verdict"] == "chargeable", position["positionsnr"]
        assert position["bucket"] != "confirmed_wrong", position["positionsnr"]
    assert Decimal(report["confirmed_wrong_eur"]) == Decimal("0.00")


def test_case_g_an_exclusion_across_two_service_dates_is_advisory_not_confirmed_wrong(client):
    """Same patient, same `<abrechnungsfall>`, GOÄ 34 and GOÄ 4 claimed 5.5 months apart.

    Grouping (case F) does not touch this one — both positions are already in one billing case.
    `logic/datalog/goae_rules.dl` LAYER 3 now carries `datum` and derives
    `blocked_exclusion_cross_date` instead of `blocked_exclusion` once it can see the two dates
    differ, and `app/padnext/audit.py` reads that off `BlockedCode.cross_date` to route GOÄ 4 to
    `unconfirmed` rather than `confirmed_wrong` — "neben" (alongside) is a clinical term, and
    services five months apart were not rendered alongside each other.
    """
    case = "case_g_cross_date_same_patient"
    expected = _expected(case)
    response = _audit(client, case)
    assert response.status_code == expected["http_status"], response.text
    report = response.json()
    assert_report_matches(report, expected["report"])

    blocked = next(p for p in report["positions"] if p["ziffer"] == "4")
    winner = next(p for p in report["positions"] if p["ziffer"] == "34")
    assert blocked["verdict"] == "blocked"
    assert blocked["blocked_by"] == "34"
    assert blocked["bucket"] == "unconfirmed"
    assert winner["bucket"] == "confirmed_fine"
    assert Decimal(report["confirmed_wrong_eur"]) == Decimal("0.00")
