"""PADnext ingestion: reading a delivery, and auditing it against the rules.

The bundled example carries one deliberate defect per position, so most of these tests are
assertions that a specific defect is *found* — and, just as importantly, that a correct position is
not flagged. An auditor that reports everything is as useless as one that reports nothing.
"""

from __future__ import annotations

import io
import json
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest

from app.padnext import (
    PadnextError,
    RealDataRefused,
    audit_delivery,
    read_delivery,
    read_file,
)
from app.config import PADNEXT_EXAMPLES_DIR
from app.padnext.audit import build_audit_input, derive_setting
from app.schemas.padnext import PadnextCase, PadnextDelivery, PadnextInvoice

EXAMPLES = PADNEXT_EXAMPLES_DIR
ORDER_NAME = "00004711_20260726_ADL_000001.auf"
PAYLOAD_NAME = "00004711_20260726_ADL_000001_padx.xml"
CONTAINER_NAME = "00004711_20260726_ADL_000001.padx"


@pytest.fixture(scope="module")
def payload_bytes() -> bytes:
    return (EXAMPLES / PAYLOAD_NAME).read_bytes()


@pytest.fixture(scope="module")
def order_bytes() -> bytes:
    return (EXAMPLES / ORDER_NAME).read_bytes()


def make_container(order: bytes, payload: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(ORDER_NAME, order)
        archive.writestr(PAYLOAD_NAME, payload)
    return buf.getvalue()


@pytest.fixture
def report(pipeline, payload_bytes):
    delivery, findings = read_delivery(payload_bytes, source_name=PAYLOAD_NAME)
    return audit_delivery(
        delivery,
        catalog=pipeline.catalog,
        rules=pipeline.rules,
        souffle_run=pipeline.souffle.run,
        read_findings=findings,
    )


def position(report, positionsnr: str):
    match = next((p for p in report.positions if p.positionsnr == positionsnr), None)
    assert match is not None, f"position {positionsnr} missing from the report"
    return match


def finding_types(report, positionsnr: str | None = None) -> set[str]:
    return {f.type for f in report.findings if positionsnr is None or f.positionsnr == positionsnr}


# ------------------------------------------------------------------------------------------
# reading
# ------------------------------------------------------------------------------------------


def test_reads_the_bundled_payload(payload_bytes):
    delivery, findings = read_delivery(payload_bytes)

    assert delivery.nachrichtentyp == "ADL"
    assert delivery.version == "02.12"
    assert len(delivery.positions()) == 9
    assert [f.type for f in findings] == []


def test_reads_a_padx_container_and_learns_echtdaten(order_bytes, payload_bytes):
    """Without the order file there is no way to know whether the data is real."""
    bare, _ = read_delivery(payload_bytes)
    assert bare.echtdaten is None

    delivery, _ = read_delivery(make_container(order_bytes, payload_bytes))
    assert delivery.echtdaten is False
    assert set(delivery.container_members) == {ORDER_NAME, PAYLOAD_NAME}
    assert len(delivery.positions()) == 9


def test_the_committed_container_matches_the_committed_sources(order_bytes, payload_bytes):
    """`scripts/make_padnext_example.py` only zips the two XML files; if the container drifts from
    them, a demo shows something the reviewable sources do not say."""
    container = EXAMPLES / CONTAINER_NAME
    assert container.is_file(), "run scripts/make_padnext_example.py"

    with zipfile.ZipFile(container) as archive:
        assert archive.read(ORDER_NAME) == order_bytes
        assert archive.read(PAYLOAD_NAME) == payload_bytes


def test_attributes_and_children_are_read_off_a_position(payload_bytes):
    delivery, _ = read_delivery(payload_bytes)
    by_nr = {p.positionsnr: p for p in delivery.positions()}

    p301 = by_nr["2"]
    assert p301.ziffer == "301"
    assert p301.go == "GOÄ"
    assert p301.anzahl == 1
    assert p301.faktor == Decimal("2.6")
    assert p301.datum == "2026-07-20"
    assert p301.begruendung and "Punktion" in p301.begruendung
    assert p301.gesamtbetrag == Decimal("24.25")


def test_an_order_file_posted_as_the_payload_is_rejected_with_a_usable_message(order_bytes):
    with pytest.raises(PadnextError, match="Auftragsdatei"):
        read_delivery(order_bytes)


def test_a_doctype_is_refused():
    """ElementTree does not fetch external entities but does expand internal ones, which is enough
    for a billion-laughs expansion. Refusing the declaration removes the class."""
    with pytest.raises(PadnextError, match="DOCTYPE"):
        read_delivery(b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aa">]><rechnungen/>')


def test_non_xml_input_is_refused():
    with pytest.raises(PadnextError, match="not XML"):
        read_delivery(b"this is not a delivery")


def test_an_unsupported_payload_root_is_refused():
    with pytest.raises(PadnextError, match="unsupported PADnext payload root"):
        read_delivery(b'<?xml version="1.0"?><Quittung xmlns="http://padinfo.de/ns/pad"/>')


def test_a_container_member_escaping_the_archive_is_refused(payload_bytes):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("../evil_padx.xml", payload_bytes)
    with pytest.raises(PadnextError, match="escapes the archive root"):
        read_delivery(buf.getvalue())


def test_a_container_without_a_payload_is_refused(order_bytes):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(ORDER_NAME, order_bytes)
    with pytest.raises(PadnextError, match="no payload XML"):
        read_delivery(buf.getvalue())


def test_position_count_mismatch_is_reported(payload_bytes):
    """`@posanzahl` exists for consistency checks, so run one."""
    tampered = payload_bytes.replace(b'posanzahl="9"', b'posanzahl="7"')
    _, findings = read_delivery(tampered)
    assert "padnext_position_count_mismatch" in {f.type for f in findings}


def test_a_position_without_a_ziffer_is_reported_not_dropped():
    xml = """<?xml version="1.0"?>
    <rechnungen anzahl="1" xmlns="http://padinfo.de/ns/pad">
      <nachrichtentyp version="02.12">ADL</nachrichtentyp>
      <rechnung id="x"><abrechnungsfall><behandlungsart>0</behandlungsart>
        <positionen posanzahl="1"><goziffer positionsnr="1"><anzahl>1</anzahl></goziffer></positionen>
      </abrechnungsfall></rechnung>
    </rechnungen>"""
    delivery, findings = read_delivery(xml.encode("utf-8"))
    assert delivery.positions() == []
    assert "padnext_position_without_ziffer" in {f.type for f in findings}


def test_unmodelled_position_types_are_reported_not_dropped():
    """Auslagen, Entschädigungen and GOZ positions are real. Skipping them silently would
    understate an invoice without saying so."""
    xml = """<?xml version="1.0"?>
    <rechnungen anzahl="1" xmlns="http://padinfo.de/ns/pad">
      <nachrichtentyp version="02.12">ADL</nachrichtentyp>
      <rechnung id="x"><abrechnungsfall><behandlungsart>0</behandlungsart>
        <positionen posanzahl="2">
          <goziffer positionsnr="1" go="GOÄ" ziffer="1"><anzahl>1</anzahl><faktor>1.0</faktor></goziffer>
          <auslagen positionsnr="2"><betrag>3.00</betrag></auslagen>
        </positionen>
      </abrechnungsfall></rechnung>
    </rechnungen>"""
    _, findings = read_delivery(xml.encode("utf-8"))
    assert "padnext_position_type_not_modelled" in {f.type for f in findings}


def test_an_unparsable_number_is_reported_rather_than_silently_zero():
    xml = """<?xml version="1.0"?>
    <rechnungen anzahl="1" xmlns="http://padinfo.de/ns/pad">
      <nachrichtentyp version="02.12">ADL</nachrichtentyp>
      <rechnung id="x"><abrechnungsfall><behandlungsart>0</behandlungsart>
        <positionen posanzahl="1">
          <goziffer positionsnr="1" go="GOÄ" ziffer="1"><anzahl>1</anzahl><faktor>zwei</faktor></goziffer>
        </positionen>
      </abrechnungsfall></rechnung>
    </rechnungen>"""
    delivery, findings = read_delivery(xml.encode("utf-8"))
    assert "padnext_unparsable_number" in {f.type for f in findings}
    assert delivery.positions()[0].faktor is None


# ------------------------------------------------------------------------------------------
# privacy and the synthetic-data rule
# ------------------------------------------------------------------------------------------


def test_no_parsed_model_can_hold_patient_identity():
    """The reader must not be able to retain a name, address or date of birth — not "does not
    today", but has nowhere to put it. This is the assertion that keeps it that way.
    """
    identity = {
        "name",
        "vorname",
        "nachname",
        "geburtsdatum",
        "geburtstag",
        "strasse",
        "plz",
        "ort",
        "adresse",
        "versichertennr",
        "patient",
        "patientid",
        "email",
        "telefon",
    }
    from app.schemas.padnext import PadnextAuditedPosition, PadnextPosition

    for model in (PadnextPosition, PadnextCase, PadnextInvoice, PadnextDelivery,
                  PadnextAuditedPosition):
        leaked = {f for f in model.model_fields if f.lower().replace("_", "") in identity}
        assert not leaked, f"{model.__name__} exposes patient identity field(s): {leaked}"


def test_the_example_files_declare_themselves_synthetic(payload_bytes, order_bytes):
    for blob in (payload_bytes, order_bytes):
        text = blob.decode("utf-8")
        assert "SYNTHETIC" in text or "synthetisch" in text


def test_the_example_carries_no_patient_identity(payload_bytes):
    text = payload_bytes.decode("utf-8").lower()
    for tag in ("<geburtsdatum", "<versichertennr", "<strasse", "<plz"):
        assert tag not in text


def test_real_data_is_refused_by_default(pipeline, order_bytes, payload_bytes, monkeypatch):
    monkeypatch.delenv("PADNEXT_ALLOW_REAL_DATA", raising=False)
    real = order_bytes.replace(b'echtdaten="0"', b'echtdaten="1"')
    delivery, findings = read_delivery(make_container(real, payload_bytes))

    assert delivery.echtdaten is True
    with pytest.raises(RealDataRefused):
        audit_delivery(
            delivery,
            catalog=pipeline.catalog,
            rules=pipeline.rules,
            souffle_run=pipeline.souffle.run,
            read_findings=findings,
        )


def test_real_data_can_be_allowed_only_by_an_explicit_opt_in(
    pipeline, order_bytes, payload_bytes, monkeypatch
):
    monkeypatch.setenv("PADNEXT_ALLOW_REAL_DATA", "1")
    real = order_bytes.replace(b'echtdaten="0"', b'echtdaten="1"')
    delivery, findings = read_delivery(make_container(real, payload_bytes))

    report = audit_delivery(
        delivery,
        catalog=pipeline.catalog,
        rules=pipeline.rules,
        souffle_run=pipeline.souffle.run,
        read_findings=findings,
    )
    assert report.echtdaten is True


def test_a_delivery_of_unknown_provenance_says_so(report):
    """A bare payload has no order file, so we cannot know it is test data. Say that, do not
    assume it."""
    assert "padnext_echtdaten_unknown" in finding_types(report)


# ------------------------------------------------------------------------------------------
# the audit finds each planted defect
# ------------------------------------------------------------------------------------------


def test_every_position_gets_a_verdict(report, payload_bytes):
    delivery, _ = read_delivery(payload_bytes)
    assert len(report.positions) == len(delivery.positions())
    assert all(p.verdict for p in report.positions)


def test_every_rejected_position_carries_a_reason(report):
    for row in report.positions:
        if not row.accepted_as_claimed:
            has_reason = bool(row.reason) or bool(finding_types(report, row.positionsnr))
            assert has_reason, f"position {row.positionsnr} rejected without a reason"


def test_missing_justification_above_the_threshold_is_an_error(report):
    """Position 1 charges 3.5 — legal, but § 12 Abs. 3 requires a written reason and there is none."""
    row = position(report, "1")
    assert row.justification_required is True
    assert row.justification_present is False
    assert "padnext_justification_missing" in finding_types(report, "1")
    assert not row.accepted_as_claimed


def test_a_properly_justified_high_factor_is_accepted(report):
    """Position 2 is the control: same situation as position 1, but justified. It must pass."""
    row = position(report, "2")
    assert row.verdict == "chargeable"
    assert row.justification_required is True
    assert row.justification_present is True
    assert row.accepted_as_claimed is True
    assert finding_types(report, "2") == set()


def test_a_zielleistung_component_is_blocked_and_names_its_blocker(report):
    row = position(report, "3")
    assert row.verdict == "blocked"
    assert row.blocked_by == "301"
    assert "padnext_blocked_zielleistung" in finding_types(report, "3")


def test_mutually_exclusive_positions_are_both_reported(report):
    """The file charges GOÄ 5 and GOÄ 7, which cancel. Both must be flagged, each naming the other,
    because the engine cannot know which one the practice meant to keep."""
    for nr, other in (("4", "7"), ("5", "5")):
        row = position(report, nr)
        assert row.verdict == "blocked"
        assert "padnext_mutual_exclusion" in finding_types(report, nr)
    assert position(report, "4").blocked_by == "7"
    assert position(report, "5").blocked_by == "5"


def test_an_understated_amount_is_caught_to_the_cent(report):
    row = position(report, "5")
    assert row.claimed_amount_eur == Decimal("20.45")
    assert row.recomputed_amount_eur == Decimal("21.45")
    assert row.amount_delta_eur == Decimal("-1.00")
    assert "padnext_amount_mismatch" in finding_types(report, "5")


def test_a_wrong_control_field_warns_but_does_not_reject_correct_money(report):
    """Position 6 claims punktzahl 180 where the catalog says 200, but the euros are right. The
    spec carries these fields *für Kontrollzwecke*, so a mismatch is inconsistent metadata — worth
    reporting, not grounds for rejecting a line whose amount recomputes exactly."""
    row = position(report, "6")
    assert row.claimed_amount_eur == row.recomputed_amount_eur
    assert "padnext_punktzahl_mismatch" in finding_types(report, "6")
    assert row.accepted_as_claimed is True
    severities = {f.severity for f in report.findings if f.positionsnr == "6"}
    assert severities == {"warning"}


def test_an_unknown_ziffer_is_an_error_and_is_not_priced(report):
    row = position(report, "7")
    assert row.verdict == "unknown_ziffer"
    assert row.in_catalog is False
    assert row.recomputed_amount_eur is None
    assert "padnext_unknown_ziffer" in finding_types(report, "7")


def test_another_fee_schedule_is_reported_as_out_of_scope_not_silently_skipped(report):
    row = position(report, "8")
    assert row.go == "GOZ"
    assert row.verdict == "out_of_scope"
    assert "padnext_fee_schedule_out_of_scope" in finding_types(report, "8")


def test_a_factor_above_the_maximum_is_an_error(report):
    row = position(report, "9")
    assert row.factor_within_band is False
    assert "padnext_factor_above_maximum" in finding_types(report, "9")
    assert not row.accepted_as_claimed


def test_no_defect_is_reported_twice_under_two_names(report):
    """The rules engine reports some of these too, keyed only by Ziffer. Showing a reviewer the
    same defect under two type names is how an audit report loses credibility."""
    assert "unknown_ziffer" not in finding_types(report), "engine duplicate leaked through"
    assert "factor_above_hoechstsatz" not in finding_types(report)


# ------------------------------------------------------------------------------------------
# the money
# ------------------------------------------------------------------------------------------


def test_the_totals_are_internally_consistent(report):
    assert report.claimed_total_eur == sum(
        (p.claimed_amount_eur or Decimal("0") for p in report.positions), Decimal("0")
    )
    assert report.recomputed_total_eur == sum(
        (p.recomputed_amount_eur or Decimal("0") for p in report.positions), Decimal("0")
    )
    assert report.at_risk_eur == report.claimed_total_eur - report.defensible_total_eur


def test_the_defensible_total_counts_only_lines_that_survive_everything(report):
    expected = sum(
        (p.recomputed_amount_eur or Decimal("0") for p in report.positions if p.accepted_as_claimed),
        Decimal("0"),
    )
    assert report.defensible_total_eur == expected
    assert report.defensible_total_eur < report.claimed_total_eur


def test_unpriceable_euros_do_not_pollute_the_arithmetic_delta(report):
    """An unknown Ziffer claiming 99.99 € is a serious finding, but it is not an arithmetic error.
    Mixing the two produced a 110 € "delta" in an earlier version that meant nothing.
    """
    assert report.arithmetic_delta_eur == Decimal("-1.00")
    assert report.unpriceable_claimed_eur == Decimal("111.99")


def test_amounts_are_decimal_not_float(report):
    for row in report.positions:
        for value in (row.claimed_amount_eur, row.recomputed_amount_eur, row.amount_delta_eur):
            assert value is None or isinstance(value, Decimal)


def test_amounts_serialise_as_json_strings(report):
    """Same rule as the coding API: a client must not be able to re-introduce binary rounding by
    parsing a JSON number."""
    blob = json.loads(report.model_dump_json())
    assert isinstance(blob["claimed_total_eur"], str)
    assert isinstance(blob["positions"][0]["recomputed_amount_eur"], str)


def test_the_report_pins_the_catalog_that_priced_it(report, pipeline):
    assert report.catalog_version == pipeline.catalog.catalog_version
    assert report.catalog_sha256 == pipeline.catalog.sha256()


# ------------------------------------------------------------------------------------------
# § 6a: the setting, which is money
# ------------------------------------------------------------------------------------------


def test_behandlungsart_maps_to_the_setting(report):
    assert report.setting == "ambulant"
    assert "behandlungsart=0" in report.setting_source


@pytest.mark.parametrize(
    "art,expected", [("0", "ambulant"), ("1", "stationaer"), ("2", "stationaer")]
)
def test_each_mapped_behandlungsart(art, expected):
    delivery = PadnextDelivery(
        invoices=[PadnextInvoice(cases=[PadnextCase(behandlungsart=art)])]
    )
    findings: list = []
    setting, _ = derive_setting(delivery, findings)
    assert setting == expected


@pytest.mark.parametrize("art", ["3", "4", "5"])
def test_an_unmappable_behandlungsart_warns_instead_of_guessing(art):
    """Vor-/nachstationär and Konsiliarbehandlung do not map cleanly onto § 6a. Silently choosing
    one would misprice an entire invoice."""
    delivery = PadnextDelivery(
        invoices=[PadnextInvoice(cases=[PadnextCase(behandlungsart=art)])]
    )
    findings: list = []
    derive_setting(delivery, findings)
    assert "padnext_behandlungsart_not_mapped" in {f.type for f in findings}


def test_a_minderungssatz_contradicting_the_behandlungsart_is_reported():
    """behandlungsart=1 means the § 6a reduction is 25 %. A file claiming 0 % is either wrong or
    describes something the engine has not been told about — either way, say so."""
    delivery = PadnextDelivery(
        invoices=[
            PadnextInvoice(
                cases=[PadnextCase(behandlungsart="1", minderungssatz=Decimal("0"))]
            )
        ]
    )
    findings: list = []
    derive_setting(delivery, findings)
    assert "padnext_minderung_mismatch" in {f.type for f in findings}


def test_the_stationary_reduction_lowers_the_recomputed_amount(
    pipeline, payload_bytes
):
    """The same invoice as an inpatient case must recompute lower, by § 6a Abs. 1."""
    ambulant, f1 = read_delivery(payload_bytes)
    inpatient, f2 = read_delivery(
        payload_bytes.replace(b"<behandlungsart>0</behandlungsart>",
                              b"<behandlungsart>1</behandlungsart>")
    )

    def run(delivery, findings):
        return audit_delivery(
            delivery,
            catalog=pipeline.catalog,
            rules=pipeline.rules,
            souffle_run=pipeline.souffle.run,
            read_findings=findings,
        )

    a, b = run(ambulant, f1), run(inpatient, f2)
    assert b.setting == "stationaer"
    assert b.recomputed_total_eur < a.recomputed_total_eur


# ------------------------------------------------------------------------------------------
# the seam onto the existing engine
# ------------------------------------------------------------------------------------------


def test_claimed_positions_become_candidates_with_their_factors(payload_bytes):
    delivery, _ = read_delivery(payload_bytes)
    extraction, bridge, factors, _ = build_audit_input(delivery, "ambulant")

    goae = [p for p in delivery.positions() if p.is_goae]
    assert bridge.ziffern() == {p.ziffer for p in goae}
    assert factors["301"] == Decimal("2.6")
    # The GOZ position must not reach the GOÄ rules engine at all.
    assert "2020" not in bridge.ziffern()


def test_a_begruendung_becomes_a_justification_bound_to_its_own_position(payload_bytes):
    delivery, _ = read_delivery(payload_bytes)
    extraction, bridge, _, _ = build_audit_input(delivery, "ambulant")

    assert extraction.justification_factors, "no justification was carried over"
    for factor in extraction.justification_factors:
        assert factor.applies_to, "a justification with no target applies to the whole encounter"
        for target in factor.applies_to:
            assert bridge.ziffern_for_entity(target), f"{target} resolves to no Ziffer"


def test_the_synthetic_extraction_carries_no_clinical_claims(payload_bytes):
    """A PADnext file says nothing about what happened clinically, only what was billed. The
    extraction built from it must not pretend otherwise."""
    delivery, _ = read_delivery(payload_bytes)
    extraction, _, _, _ = build_audit_input(delivery, "ambulant")

    assert extraction.procedures == []
    assert extraction.examinations == []
    assert extraction.lab_tests == []
    assert extraction.consultation is None
    assert extraction.diagnoses == []


def test_reading_the_same_delivery_twice_gives_the_same_report(pipeline, payload_bytes):
    def run():
        delivery, findings = read_delivery(payload_bytes, source_name=PAYLOAD_NAME)
        report = audit_delivery(
            delivery,
            catalog=pipeline.catalog,
            rules=pipeline.rules,
            souffle_run=pipeline.souffle.run,
            read_findings=findings,
        )
        return report.model_dump_json()

    assert run() == run()


def test_read_file_accepts_both_bundled_forms():
    for name in (PAYLOAD_NAME, CONTAINER_NAME):
        delivery, _ = read_file(EXAMPLES / name)
        assert len(delivery.positions()) == 9
        assert delivery.source_name == name


# ------------------------------------------------------------------------------------------
# the finding vocabulary a client has to be able to render
# ------------------------------------------------------------------------------------------


def test_the_dynamic_blocked_finding_types_are_enumerable_from_the_schema():
    """`audit.py` builds this type with an f-string: `f"padnext_blocked_{blocked.reason}"`.

    A client cannot grep for a type that is assembled at runtime, so the set has to be derivable
    from the published schema instead — `BlockedCode.reason` is a closed `Literal`, and it is that
    closedness a UI depends on to label every possible finding. If someone widens it to `str`,
    every new value renders as a raw identifier, and this is where that shows up.

    The POC checked the same invariant against its bundled `manual.html`. That page is not part of
    this monorepo (see docs/migration/MIGRATION_PLAN.md §2), so the assertion moved to the contract
    itself: the generated TypeScript in `packages/contracts/typescript` carries the same union.
    """
    import typing

    from app.schemas import BlockedCode

    reasons = typing.get_args(BlockedCode.model_fields["reason"].annotation)

    assert reasons, "BlockedCode.reason is no longer a closed Literal; a client cannot enumerate it"
    assert set(reasons) >= {"exclusion", "zielleistung", "less_specific", "conflict_lost"}


def test_every_emitted_finding_type_is_a_stable_identifier(report):
    """Whatever this delivery produced must be a label key, not a sentence."""
    for finding in report.findings:
        assert finding.type == finding.type.lower()
        assert " " in finding.message, "the message is the prose; the type is the key"
        assert finding.type.replace("_", "").isalnum(), finding.type


def test_the_report_states_its_rule_coverage(report):
    """An audit that suppressed an unverified rule must say so, or "no finding" reads as "clean"."""
    assert report.rule_coverage_detail is not None
    assert report.enforced_rule_count > 0
    assert report.suppressed_unverified_rule_count > 0
    assert report.rule_coverage_detail.policy_for_unverified_rules == "warn"
    assert "advisory_rules_present" in {f.type for f in report.findings}


def test_the_report_carries_a_receipt_hash(report):
    assert len(report.receipt_hash) == 64
    assert report.logic_version


def test_the_receipt_hash_is_stable_across_identical_audits(pipeline, payload_bytes):
    """Same file, same catalog, same rules, same policy — same receipt. Twice."""

    def audit_once() -> str:
        delivery, findings = read_delivery(payload_bytes)
        return audit_delivery(
            delivery,
            catalog=pipeline.catalog,
            rules=pipeline.rules,
            souffle_run=pipeline.souffle.run,
            read_findings=findings,
            settings=pipeline.settings,
        ).receipt_hash

    assert audit_once() == audit_once()
