"""Synthetic `Proposal` objects for the database tests.

Built by hand rather than by solving a case, on purpose. The DB tests are about persistence,
transitions and the audit log — none of which involve Soufflé or Clingo — and a test that needs a
solver skips on a machine without one. A skipped durability test looks exactly like a passing one,
which is the failure mode `conftest._engines_required` exists to prevent elsewhere.

The proposals are shaped like real ones (a full `CodingResponse` with an extraction, a coding and an
audit trail) so the JSON round-trip being exercised is the real one, but nothing about the numbers
means anything clinically.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.schemas import (
    AuditTrail,
    ClinicalExtraction,
    Coding,
    CodingResponse,
    InvoiceLine,
    Proposal,
    ProposalStatus,
    RuleCoverage,
    Totals,
    Warning_,
)


def make_extraction(*, age: int = 50, setting: str = "ambulant") -> ClinicalExtraction:
    return ClinicalExtraction.model_validate(
        {
            "patient": {"age": age, "sex": "m", "setting": setting},
            "procedures": [{"id": "p1", "type": "punktion", "confidence": "0.9"}],
        }
    )


def make_coding_response(
    *, extraction: ClinicalExtraction | None = None, solver_status: str = "SATISFIABLE"
) -> CodingResponse:
    extraction = extraction or make_extraction()
    coding = Coding(
        proposed_codes=[
            InvoiceLine(
                ziffer="1",
                official_text="Beratung — auch mittels Fernsprecher",
                punkte=80,
                category="beratung",
                factor=Decimal("2.3"),
                factor_basis="schwellenwert",
                confidence=Decimal("0.9"),
                amount_eur=Decimal("10.72"),
            )
        ],
        total=Totals(amount_eur=Decimal("10.72"), punkte=80),
        warnings=[Warning_(type="synthetic", message="test fixture, not a real coding")],
    )
    audit_trail = AuditTrail(
        extraction_mode="manual",
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        solver_status=solver_status,
    )
    return CodingResponse(extraction=extraction, coding=coding, audit_trail=audit_trail)


def make_rule_coverage() -> RuleCoverage:
    return RuleCoverage(
        policy_for_unverified_rules="warn",
        enforced_rule_count=7,
        advisory_rule_count=11,
        unverified_rule_count=9,
        analog_candidate_count=2,
        suppressed_unverified_rule_count=9,
        rule_coverage="partial",
        rules_version="rules_test",
        verified_share="7/16",
    )


def make_proposal(
    *,
    case_id: str | None = "ENC-1",
    receipt_hash: str | None = None,
    status: ProposalStatus = ProposalStatus.DRAFT,
    solver_status: str = "SATISFIABLE",
    extraction: ClinicalExtraction | None = None,
    created_at: datetime | None = None,
    cached: bool = False,
) -> Proposal:
    """A DRAFT proposal with every field the API surfaces populated.

    `receipt_hash` defaults to a fresh random digest rather than a constant, so a test that stores
    two proposals cannot accidentally assert on a collision it created itself.
    """
    result = make_coding_response(extraction=extraction, solver_status=solver_status)
    coverage = make_rule_coverage()
    return Proposal(
        proposal_id=f"prop_{uuid.uuid4().hex[:16]}",
        case_id=case_id,
        status=status,
        created_at=created_at or datetime.now(timezone.utc),
        receipt_hash=receipt_hash or uuid.uuid4().hex * 2,
        catalog_version="goae_official_snapshot_2026-07-25",
        catalog_sha256="a" * 64,
        rules_version="rules_test",
        rules_hash="b" * 64,
        solver_version="5.8.0",
        rules_engine_version="2.5",
        logic_version="c" * 64,
        solver_result=result,
        warnings=list(result.coding.warnings),
        missing_documentation=list(result.coding.missing_documentation),
        solver_status=solver_status,
        solver_timed_out=solver_status == "TIMEOUT_PARTIAL",
        enforced_rule_count=coverage.enforced_rule_count,
        advisory_rule_count=coverage.advisory_rule_count,
        unverified_rule_count=coverage.unverified_rule_count,
        analog_candidate_count=coverage.analog_candidate_count,
        suppressed_unverified_rule_count=coverage.suppressed_unverified_rule_count,
        rule_coverage=coverage,
        cached=cached,
    )
