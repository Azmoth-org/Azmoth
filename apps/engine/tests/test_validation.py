"""Validation, exact money, § 6a Minderung, and blocked-reason reconciliation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.schemas import BlockedCode, FactorDecision, OptimizationResult, RulesResult
from app.validation.validator import (
    ValidationFailed,
    cent_to_eur,
    line_amount_cent,
)
from tests.conftest import make_bridge, make_extraction, one_act_per_ziffer


# ------------------------------------------------------------------------------------------
# money
# ------------------------------------------------------------------------------------------


def test_money_math_is_exact():
    """Gebühr = Punktzahl x Punktwert x Faktor (§ 5 Abs. 1 GOÄ), in Decimal, no float anywhere.

    160 x 2.3 x 5.82873 ct = 2144.97264 ct exactly. A float computation drifts in the last
    places, which is how invoices end up a cent apart from the practice's own arithmetic.
    """
    cents = line_amount_cent(160, Decimal("2.3"), Decimal("5.82873"))

    assert cents == Decimal("2144.97264")
    assert cent_to_eur(cents) == Decimal("21.45")


def test_amounts_are_decimal_not_float():
    cents = line_amount_cent(360, Decimal("1.8"), Decimal("5.82873"))

    assert isinstance(cents, Decimal)
    assert isinstance(cent_to_eur(cents), Decimal)


@pytest.mark.parametrize(
    "cents,eur",
    [
        ("1000.4", "10.00"),
        ("1000.5", "10.01"),  # § 5 Abs. 1 Satz 4: 0.5 and above rounds up
        ("1000.6", "10.01"),
        ("0.5", "0.01"),
        ("0.4", "0.00"),
    ],
)
def test_rounding_follows_paragraph_5_abs_1_satz_4(cents, eur):
    assert cent_to_eur(Decimal(cents)) == Decimal(eur)


def test_line_and_total_amounts_are_reported_rounded_and_unrounded(pipeline, manual_case):
    from app.schemas import ClinicalExtraction

    response = pipeline.run(
        ClinicalExtraction.model_validate(manual_case("case_001_knee"))
    )

    for line in response.coding.proposed_codes:
        assert line.amount_cent_unrounded > 0
        assert line.amount_eur == cent_to_eur(line.amount_cent_unrounded)
    assert response.coding.total.amount_cent_unrounded > 0


def test_total_equals_sum_of_lines(pipeline, manual_case):
    from app.schemas import ClinicalExtraction

    for name in ("case_001_knee", "case_002_cardiology", "case_003_dermatology"):
        response = pipeline.run(ClinicalExtraction.model_validate(manual_case(name)))
        line_sum = sum((line.amount_eur for line in response.coding.proposed_codes), Decimal(0))

        assert line_sum == response.coding.total.amount_eur, name


def test_points_total_counts_every_charged_line(pipeline, manual_case):
    from app.schemas import ClinicalExtraction

    response = pipeline.run(
        ClinicalExtraction.model_validate(manual_case("case_003_dermatology"))
    )
    expected = sum(line.punkte for line in response.coding.proposed_codes)

    assert response.coding.total.punkte == expected


# ------------------------------------------------------------------------------------------
# § 6a Minderung
# ------------------------------------------------------------------------------------------


def test_minderung_stationaer_25_percent(pipeline, manual_case):
    from app.schemas import ClinicalExtraction

    extraction = ClinicalExtraction.model_validate(manual_case("case_001_knee"))
    response = pipeline.run(extraction, setting="stationaer")
    total = response.coding.total

    assert total.minderung_rate == Decimal("0.25")
    assert total.minderung_applied is True
    for line in response.coding.proposed_codes:
        expected = cent_to_eur(
            line_amount_cent(line.punkte, line.factor, total.punktwert_cent) * Decimal("0.75")
        )
        assert line.amount_eur == expected, f"GOÄ {line.ziffer}"


def test_minderung_belegarzt_15_percent(pipeline, manual_case):
    from app.schemas import ClinicalExtraction

    extraction = ClinicalExtraction.model_validate(manual_case("case_001_knee"))
    response = pipeline.run(extraction, setting="belegarzt")
    total = response.coding.total

    assert total.minderung_rate == Decimal("0.15")
    for line in response.coding.proposed_codes:
        expected = cent_to_eur(
            line_amount_cent(line.punkte, line.factor, total.punktwert_cent) * Decimal("0.85")
        )
        assert line.amount_eur == expected, f"GOÄ {line.ziffer}"


def test_ambulant_has_no_minderung(pipeline, manual_case):
    from app.schemas import ClinicalExtraction

    response = pipeline.run(
        ClinicalExtraction.model_validate(manual_case("case_001_knee")), setting="ambulant"
    )

    assert response.coding.total.minderung_rate == Decimal("0")
    assert response.coding.total.minderung_applied is False
    assert response.coding.total.amount_eur == response.coding.total.amount_eur_before_minderung


def test_stationaer_is_cheaper_than_ambulant_for_the_same_input(pipeline, manual_case):
    from app.schemas import ClinicalExtraction

    payload = manual_case("case_001_knee")
    ambulant = pipeline.run(ClinicalExtraction.model_validate(payload), setting="ambulant")
    stationaer = pipeline.run(
        ClinicalExtraction.model_validate(payload), setting="stationaer"
    )

    assert stationaer.coding.total.amount_eur < ambulant.coding.total.amount_eur
    assert stationaer.coding.total.punkte == ambulant.coding.total.punkte


def test_minderung_is_reported_with_its_paragraph(pipeline, manual_case):
    from app.schemas import ClinicalExtraction

    response = pipeline.run(
        ClinicalExtraction.model_validate(manual_case("case_001_knee")), setting="stationaer"
    )
    notice = next(w for w in response.coding.warnings if w.type == "minderung_applied")

    assert "§ 6a" in notice.legal_basis


# ------------------------------------------------------------------------------------------
# hard failure when the layers disagree
# ------------------------------------------------------------------------------------------


def test_validation_fails_hard_when_the_solver_output_breaks_an_exclusion(validator):
    """Simulate a solver bug: two mutually exclusive positions on one invoice.

    The validator must refuse to produce an invoice, not return a plausible-looking one.
    """
    extraction = make_extraction()
    bridge = one_act_per_ziffer("5", "7")
    rules_result = RulesResult(proposed=list(bridge.candidates), billable=["5", "7"])
    optimization = OptimizationResult(
        billed=["5", "7"],
        factors=[
            FactorDecision(
                ziffer=z,
                factor=Decimal("2.3"),
                basis="schwellenwert",
                threshold=Decimal("2.3"),
                max_factor=Decimal("3.5"),
            )
            for z in ("5", "7")
        ],
    )

    with pytest.raises(ValidationFailed) as exc:
        validator.build(extraction, rules_result, optimization, bridge)

    codes = {v.code for v in exc.value.violations}
    assert "exclusion_violation" in codes


def test_validation_fails_hard_on_an_unlawful_factor(validator):
    extraction = make_extraction()
    bridge = one_act_per_ziffer("3550")
    rules_result = RulesResult(proposed=list(bridge.candidates), billable=["3550"])
    optimization = OptimizationResult(
        billed=["3550"],
        factors=[
            FactorDecision(
                ziffer="3550",
                factor=Decimal("2.3"),  # Abschnitt M caps at 1.3
                basis="hoechstsatz",
                threshold=Decimal("1.15"),
                max_factor=Decimal("1.3"),
            )
        ],
    )

    with pytest.raises(ValidationFailed) as exc:
        validator.build(extraction, rules_result, optimization, bridge)

    assert "factor_above_max" in {v.code for v in exc.value.violations}


def test_validation_fails_hard_when_a_factor_needs_a_reason_and_has_none(validator):
    extraction = make_extraction()
    bridge = one_act_per_ziffer("7")
    rules_result = RulesResult(proposed=list(bridge.candidates), billable=["7"])
    optimization = OptimizationResult(
        billed=["7"],
        factors=[
            FactorDecision(
                ziffer="7",
                factor=Decimal("3.0"),
                basis="ueber_schwellenwert",
                threshold=Decimal("2.3"),
                max_factor=Decimal("3.5"),
                justification_required=True,
                justification=None,
            )
        ],
    )

    with pytest.raises(ValidationFailed) as exc:
        validator.build(extraction, rules_result, optimization, bridge)

    violation = next(v for v in exc.value.violations if v.code == "missing_justification")
    assert "§ 12 Abs. 3" in violation.legal_basis


def test_validation_fails_hard_on_an_unknown_position(validator):
    extraction = make_extraction()
    bridge = one_act_per_ziffer("99999")
    rules_result = RulesResult(proposed=list(bridge.candidates), billable=["99999"])
    optimization = OptimizationResult(
        billed=["99999"],
        factors=[
            FactorDecision(
                ziffer="99999",
                factor=Decimal("1"),
                basis="einfachsatz",
                threshold=Decimal("2.3"),
                max_factor=Decimal("3.5"),
            )
        ],
    )

    with pytest.raises(ValidationFailed) as exc:
        validator.build(extraction, rules_result, optimization, bridge)

    assert "unknown_ziffer" in {v.code for v in exc.value.violations}


def test_validation_failure_lists_every_violation(validator):
    """A caller should see all the problems at once, not be told about them one per request."""
    extraction = make_extraction()
    bridge = one_act_per_ziffer("5", "7")
    rules_result = RulesResult(proposed=list(bridge.candidates), billable=["5", "7"])
    optimization = OptimizationResult(
        billed=["5", "7", "99999"],
        factors=[
            FactorDecision(
                ziffer=z,
                factor=Decimal("9"),
                basis="hoechstsatz",
                threshold=Decimal("2.3"),
                max_factor=Decimal("3.5"),
            )
            for z in ("5", "7", "99999")
        ],
    )

    with pytest.raises(ValidationFailed) as exc:
        validator.build(extraction, rules_result, optimization, bridge)

    codes = {v.code for v in exc.value.violations}
    assert {"exclusion_violation", "unknown_ziffer", "factor_above_max"} <= codes


# ------------------------------------------------------------------------------------------
# blocked-reason reconciliation
# ------------------------------------------------------------------------------------------


def test_blocked_reasons_are_reconciled_with_final_invoice(pipeline, manual_case):
    """GOÄ 5 is suppressed during rule evaluation and the winner is on the invoice, so the
    reported blocker must be a position the reviewer can actually find on the bill."""
    from app.schemas import ClinicalExtraction

    response = pipeline.run(
        ClinicalExtraction.model_validate(manual_case("case_001_knee"))
    )
    charged = {line.ziffer for line in response.coding.proposed_codes}

    for blocked in response.coding.blocked_codes:
        assert blocked.reconciled_with_final_invoice is True
        if blocked.blocked_by:
            assert blocked.blocked_by in charged, (
                f"GOÄ {blocked.ziffer} is reported as blocked by GOÄ {blocked.blocked_by}, "
                "which is not on the invoice"
            )


def test_a_suppression_whose_basis_disappeared_is_flagged(validator):
    """Defensive guard: if every blocker of a position drops off the invoice, the position may be
    chargeable after all. Reported rather than silently reinstated."""
    blocked = [
        BlockedCode(ziffer="5", reason="exclusion", blocked_by="7", explanation="x"),
        BlockedCode(ziffer="200", reason="zielleistung", blocked_by="301", explanation="y"),
    ]

    kept, issues = validator._reconcile_blocked(blocked, charged={"301"})

    assert {i.type for i in issues} == {"blocking_basis_removed"}
    assert issues[0].ziffer == "5"
    assert len(kept) == 2, "the reason is kept for transparency, not dropped"
    assert next(b for b in kept if b.ziffer == "5").reconciled_with_final_invoice is False
    assert next(b for b in kept if b.ziffer == "200").reconciled_with_final_invoice is True


def test_every_blocked_line_has_a_reason_and_explanation(pipeline, manual_case):
    from app.schemas import ClinicalExtraction

    for name in ("case_001_knee", "case_002_cardiology", "case_003_dermatology"):
        response = pipeline.run(ClinicalExtraction.model_validate(manual_case(name)))
        for blocked in response.coding.blocked_codes:
            assert blocked.reason, name
            assert blocked.explanation, f"{name}: GOÄ {blocked.ziffer} blocked without explanation"
            assert blocked.detail, name


def test_every_accepted_line_has_a_proof(pipeline, manual_case):
    from app.schemas import ClinicalExtraction

    for name in ("case_001_knee", "case_002_cardiology", "case_003_dermatology"):
        response = pipeline.run(ClinicalExtraction.model_validate(manual_case(name)))
        for line in response.coding.proposed_codes:
            assert line.proof, f"{name}: GOÄ {line.ziffer} has no proof"
            assert {"catalog_match"} <= {s.rule for s in line.proof}


# ------------------------------------------------------------------------------------------
# coverage honesty
# ------------------------------------------------------------------------------------------


def test_incomplete_rule_coverage_produces_a_warning(pipeline, manual_case):
    from app.schemas import ClinicalExtraction

    response = pipeline.run(
        ClinicalExtraction.model_validate(manual_case("case_001_knee"))
    )
    types = {w.type for w in response.coding.warnings}

    assert "rule_coverage_incomplete" in types


def test_unverified_rule_count_is_stated_in_the_warning(pipeline, manual_case):
    from app.schemas import ClinicalExtraction

    response = pipeline.run(
        ClinicalExtraction.model_validate(manual_case("case_001_knee"))
    )
    warning = next(
        w for w in response.coding.warnings if w.type == "rule_coverage_incomplete" and not w.ziffer
    )

    assert "nicht verifiziert" in warning.message.lower() or "NICHT verifiziert" in warning.message
    assert "ersetzt keine ärztliche Prüfung" in warning.message


def test_audit_trail_records_provenance_and_policies(pipeline, manual_case):
    from app.schemas import ClinicalExtraction

    response = pipeline.run(
        ClinicalExtraction.model_validate(manual_case("case_001_knee"))
    )
    audit = response.audit_trail

    assert audit.catalog_version.startswith("goae_official_snapshot_")
    assert len(audit.catalog_sha256) == 64
    assert audit.catalog_source
    assert audit.rule_coverage == "partial"
    assert audit.rules_version
    assert audit.rules_engine == "souffle" and audit.rules_engine_version.startswith("2.")
    assert audit.optimizer == "clingo" and audit.optimizer_version
    assert audit.extraction_mode == "manual"
    assert audit.llm_saw_goae_catalog is False
    assert audit.unverified_rule_policy == "warn"
    assert audit.base_factor_policy == "schwellenwert"
    assert audit.rule_summary["exclusions_enforced"] > 0
    assert audit.timestamp is not None


def test_stage_timings_cover_every_stage(pipeline, manual_case):
    from app.schemas import ClinicalExtraction

    response = pipeline.run(
        ClinicalExtraction.model_validate(manual_case("case_001_knee"))
    )

    assert {
        "bridge",
        "souffle",
        "clingo",
        "souffle_verification",
        "validation",
    } <= set(response.audit_trail.stage_timings_ms)
