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
from app.config import PADNEXT_EXAMPLES_DIR, UnverifiedRulePolicy
from app.core.canonical import canonical
from app.padnext.audit import build_audit_input, derive_setting
from app.schemas.padnext import (
    PadnextCase,
    PadnextDelivery,
    PadnextInvoice,
    PadnextPosition,
)

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


# ------------------------------------------------------------------------------------------
# the three honest buckets
# ------------------------------------------------------------------------------------------


def test_the_three_buckets_account_for_every_claimed_euro(report):
    """The identity the whole split rests on. If it does not hold, some position's euros were
    counted twice or dropped, and every figure a practice would act on is wrong."""
    assert (
        report.confirmed_fine_eur + report.confirmed_wrong_eur + report.unconfirmed_eur
        == report.claimed_total_eur
    )
    assert report.bucket_summary() == {
        "confirmed_fine": 1,
        "confirmed_wrong": 5,
        "unconfirmed": 3,
    }
    assert sum(report.bucket_summary().values()) == len(report.positions)


def test_the_bundled_example_splits_into_the_three_buckets(report):
    """The concrete numbers, so a change in bucketing policy shows up as a diff here.

    Read against what the old `at_risk_eur` would have said about the same file: 251.54 claimed
    minus 51.06 defensible was 200.48 — 80 % of the invoice presented as disputed. Of that, only
    88.49 is actually demonstrable.
    """
    assert report.claimed_total_eur == Decimal("251.54")
    assert report.confirmed_fine_eur == Decimal("24.25")
    assert report.confirmed_wrong_eur == Decimal("88.49")
    assert report.unconfirmed_eur == Decimal("138.80")


def test_the_coverage_ratio_reports_the_audited_share_not_the_wrong_share(report):
    """`coverage_ratio` answers "how much of this invoice could we judge at all?" — so it counts
    confirmed_wrong as covered. An audit that proved a position wrong audited it."""
    judged = report.confirmed_fine_eur + report.confirmed_wrong_eur
    assert report.coverage_ratio == pytest.approx(float(judged / report.claimed_total_eur))
    assert 0.0 <= report.coverage_ratio <= 1.0
    # Under 50 % on a nine-line invoice, and that is the honest figure: it is what "837 of 869
    # exclusion rules are unverified" actually costs.
    assert report.coverage_ratio < 0.5


def test_every_position_carries_a_bucket_and_a_reason(report):
    for row in report.positions:
        assert row.bucket in {"confirmed_fine", "confirmed_wrong", "unconfirmed"}
        assert row.bucket_reason, f"position {row.positionsnr} bucketed without a reason"


def test_a_verified_zielleistung_violation_is_confirmed_wrong(report):
    """Position 3 charges a dressing beside the puncture it belongs to. `ziel_man_301_200` is
    manually verified, so this is provable, not advisory."""
    row = position(report, "3")
    assert row.bucket == "confirmed_wrong"
    assert "ziel_man_301_200" in row.verified_rule_ids


def test_a_position_validated_by_a_verified_rule_is_confirmed_fine(report):
    """Position 2 passed every check AND a verified rule actually bore on it — it is the
    Zielleistung that `ziel_man_301_200` names. That is what earns green."""
    row = position(report, "2")
    assert row.bucket == "confirmed_fine"
    assert row.verified_rule_ids == ["ziel_man_301_200"]
    assert row.advisory_rule_ids == []


def test_a_clean_position_with_no_verified_rule_is_unconfirmed_not_fine(report):
    """Position 6 recomputes to the cent and no rule touches GOÄ 410. It is still not `fine`:
    nothing verified checked it, so calling it safe would be an overclaim. This is the case that
    separates honest semantics from flattering ones."""
    row = position(report, "6")
    assert row.accepted_as_claimed is True
    assert row.verdict == "chargeable"
    assert row.verified_rule_ids == []
    assert row.bucket == "unconfirmed"


def test_an_unknown_ziffer_is_unconfirmed_not_wrong(report):
    """Position 7 charges 99.99 € on a Ziffer our catalog does not have. That is a serious finding
    and an error-severity one, but our catalog's own coverage is `partial` — absence from it is a
    gap in our data, not proof the practice invented a service. It must not be counted as a
    refund."""
    row = position(report, "7")
    assert row.verdict == "unknown_ziffer"
    assert "padnext_unknown_ziffer" in finding_types(report, "7")
    assert row.bucket == "unconfirmed"
    assert Decimal("99.99") <= report.unconfirmed_eur


def test_another_fee_schedule_is_unconfirmed_and_borrows_no_goae_rules(report):
    """GOZ 2020 is not GOÄ 2020. Attributing GOÄ rules to a dental position by number would be a
    fabricated verdict, so out-of-scope positions get no rules at all."""
    row = position(report, "8")
    assert row.bucket == "unconfirmed"
    assert row.verified_rule_ids == []
    assert row.advisory_rule_ids == []


def test_the_old_at_risk_field_is_gone(report):
    """`at_risk_eur` was `claimed_total − defensible_total`, which reported unverified rule
    coverage as disputed revenue. It was removed rather than kept as an alias, so that no caller
    can keep rendering the misleading figure by accident — a missing field breaks a build, a
    quietly redefined one does not."""
    assert not hasattr(report, "at_risk_eur")
    assert "at_risk_eur" not in report.model_dump(mode="json")


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
    """Compared in canonical form, which is what makes the comparison mean anything.

    The report carries measured timings (`solve_time_ms`, `total_time_ms`), and two runs of a
    deterministic audit differ in them by design. `canonical()` strips exactly those — and nothing
    that decides money, which `test_golden_normalization.py` asserts in both directions — so a
    verdict, an amount or a receipt that moved between the two runs still fails here.
    """

    def run():
        delivery, findings = read_delivery(payload_bytes, source_name=PAYLOAD_NAME)
        report = audit_delivery(
            delivery,
            catalog=pipeline.catalog,
            rules=pipeline.rules,
            souffle_run=pipeline.souffle.run,
            read_findings=findings,
        )
        return canonical(report.model_dump(mode="python"))

    first, second = run(), run()

    assert first == second
    assert first["receipt_hash"], "a stripped-empty report would make this assert nothing"
    assert first["claimed_total_eur"]


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


# ------------------------------------------------------------------------------------------
# honest semantics, proved on a synthetic invoice with nothing else going on
# ------------------------------------------------------------------------------------------
#
# The bundled example is the realistic test, and it is a poor *proof*: every position in it has
# several things wrong at once, the amounts are whatever 5.82873 cent per point happens to produce,
# and the buckets it lands in depend on which of 869 real rules happen to touch which Ziffer. So the
# three cases below are built from nothing — a three-entry catalog, one rule, a stubbed solver — and
# priced so the money is legible: 100 €, 50 €, 200 €.
#
# Each position isolates exactly one reason for its bucket:
#
#   A  8100  100 €  a verified rule bears on it, every check passes   → confirmed_fine
#   B  8200   50 €  the same verified rule excludes it                → confirmed_wrong
#   C  8300  200 €  no rule in the store mentions this Ziffer at all  → unconfirmed
#
# C is the one that matters. It is a perfectly ordinary position: in the catalog, active, priced
# correctly to the cent, within its factor band, not excluded by anything. Under the old
# `at_risk_eur = claimed_total − defensible_total` it contributed nothing to the disputed figure only
# because the solver happened to confirm it; had the solver merely failed to return it, all 200 €
# would have been reported as revenue at risk. It is neither safe nor wrong. It is unchecked, and the
# report has to be able to say so.

SYNTHETIC_PUNKTWERT_CENT = "100"  # 1 point = 1.00 €, so the euros in the assertions are readable


def _synthetic_catalog(tmp_path):
    """A three-Ziffer catalog priced so that punkte × faktor lands on a round euro amount."""
    from app.catalog.catalog_loader import Catalog

    raw = {
        "catalog_version": "synthetic-honest-buckets",
        "rules_version": "synthetic",
        "punktwert_cent": SYNTHETIC_PUNKTWERT_CENT,
        "coverage": {"rule_coverage": "partial"},
        # Threshold 2.3 with every position at 2.0: below the § 12 Abs. 3 line, so no position
        # needs a written justification and that check cannot muddy the buckets.
        "factor_bands": {"T": {"threshold": "2.3", "max": "3.5", "legal_basis": "§ 5 Abs. 1 GOÄ"}},
        "ziffern": [
            {"ziffer": "8100", "punkte": 50, "category": "T", "provenance": "illustrative",
             "official_text": "Synthetische Zielleistung"},
            {"ziffer": "8200", "punkte": 25, "category": "T", "provenance": "illustrative",
             "official_text": "Synthetische ausgeschlossene Leistung"},
            {"ziffer": "8300", "punkte": 100, "category": "T", "provenance": "illustrative",
             "official_text": "Synthetische Leistung ohne Regelabdeckung"},
            {"ziffer": "8400", "punkte": 75, "category": "T", "provenance": "illustrative",
             "official_text": "Synthetische Leistung, die der Solver nicht bestätigt"},
        ],
    }
    path = tmp_path / "synthetic_catalog.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    # A catalog with no overrides file: the third argument points at something that does not exist.
    return Catalog.load(path, tmp_path / "no_overrides.json")


def _synthetic_rules():
    """One rule, verified, excluding 8200 whenever 8100 is charged.

    Deliberately the only rule in the store. 8300 is therefore untouched by anything, which is what
    makes it a clean test of "no verified rule maps to this Ziffer" rather than of some accident of
    the real rule tables.
    """
    from app.rules.rule_store import ExclusionRule, RuleStore

    return RuleStore(
        policy=UnverifiedRulePolicy.WARN,
        exclusions=[
            ExclusionRule(
                rule_id="excl_synthetic_verified",
                from_ziffer="8100",
                to_ziffer="8200",
                direction="one_way",
                legal_basis="Synthetische Leistungslegende",
                verified=True,
                verified_at="2026-08-22",
                source="manual_verification",
            )
        ],
    )


def _synthetic_delivery():
    def goziffer(nr: str, ziffer: str, amount: str) -> PadnextPosition:
        # No punktzahl and no punktwert on purpose: those are control fields, and a mismatch on one
        # raises a finding that has nothing to do with the bucket under test.
        return PadnextPosition(
            positionsnr=nr,
            go="GOÄ",
            ziffer=ziffer,
            anzahl=1,
            faktor=Decimal("2.0"),
            gesamtbetrag=Decimal(amount),
            text=f"Synthetische Position {nr}",
        )

    return PadnextDelivery(
        nachrichtentyp="ADL",
        version="02.12",
        echtdaten=False,
        source_name="synthetic_honest_buckets_padx.xml",
        invoices=[
            PadnextInvoice(
                invoice_id="SYNTH-BUCKETS-1",
                cases=[
                    PadnextCase(
                        behandlungsart="0",  # ambulant → no § 6a Minderung to complicate the money
                        positions=[
                            goziffer("A", "8100", "100.00"),
                            goziffer("B", "8200", "50.00"),
                            goziffer("C", "8300", "200.00"),
                        ],
                    )
                ],
            )
        ],
    )


def _synthetic_souffle_run():
    """Stands in for Soufflé, so the test states the rule outcome instead of depending on a binary.

    It returns what the real engine returns for this input: 8100 and 8300 survive, 8200 is removed
    by the verified exclusion, and the block names the rule that did it — which is what
    `classify_position` looks up to decide whether the suppression rests on a verified basis.
    """
    from app.schemas.facts import BlockedCode, RulesResult

    def run(extraction, bridge, proposed_factors=None):
        return RulesResult(
            billable=["8100", "8300"],
            blocked=[
                BlockedCode(
                    ziffer="8200",
                    reason="exclusion",
                    blocked_by="8100",
                    rule_id="excl_synthetic_verified",
                    legal_basis="Synthetische Leistungslegende",
                    explanation="GOÄ 8200 ist neben GOÄ 8100 nicht berechnungsfähig.",
                )
            ],
        )

    return run


@pytest.fixture
def honest_report(tmp_path, settings):
    return audit_delivery(
        _synthetic_delivery(),
        catalog=_synthetic_catalog(tmp_path),
        rules=_synthetic_rules(),
        souffle_run=_synthetic_souffle_run(),
        settings=settings,
    )


def test_the_synthetic_invoice_splits_exactly_one_hundred_fifty_two_hundred(honest_report):
    """The headline assertion: 100 € fine, 50 € wrong, 200 € unconfirmed, and nothing anywhere else."""
    assert honest_report.claimed_total_eur == Decimal("350.00")
    assert honest_report.confirmed_fine_eur == Decimal("100.00")
    assert honest_report.confirmed_wrong_eur == Decimal("50.00")
    assert honest_report.unconfirmed_eur == Decimal("200.00")
    assert honest_report.bucket_summary() == {
        "confirmed_fine": 1,
        "confirmed_wrong": 1,
        "unconfirmed": 1,
    }


def test_position_a_is_confirmed_fine_because_a_verified_rule_checked_it(honest_report):
    row = position(honest_report, "A")
    assert row.claimed_amount_eur == Decimal("100.00")
    assert row.recomputed_amount_eur == Decimal("100.00")  # the money is not in dispute
    assert row.verdict == "chargeable"
    assert row.accepted_as_claimed is True
    assert row.bucket == "confirmed_fine"
    assert row.verified_rule_ids == ["excl_synthetic_verified"]
    assert row.advisory_rule_ids == []


def test_position_b_is_confirmed_wrong_because_the_rule_that_blocked_it_is_verified(honest_report):
    """A verified exclusion is the strongest thing this engine can say: not "unconfirmed", not
    "advisory" — a human checked the rule, and the invoice violates it."""
    row = position(honest_report, "B")
    assert row.claimed_amount_eur == Decimal("50.00")
    assert row.verdict == "blocked"
    assert row.blocked_by == "8100"
    assert row.bucket == "confirmed_wrong"
    assert "excl_synthetic_verified" in row.verified_rule_ids


def test_position_c_is_unconfirmed_because_no_verified_rule_maps_to_its_ziffer(honest_report):
    """The position at the centre of the refactor. Nothing is wrong with it — it survives the rules,
    it prices to the cent, its factor is inside the band. It is still not `confirmed_fine`, because
    no verified rule ever looked at GOÄ 8300. Reporting these 200 € as safe would be as dishonest as
    reporting them as at risk."""
    row = position(honest_report, "C")
    assert row.claimed_amount_eur == Decimal("200.00")
    assert row.recomputed_amount_eur == Decimal("200.00")
    assert row.verdict == "chargeable"
    assert row.accepted_as_claimed is True  # passed every check that exists
    assert row.verified_rule_ids == []  # but nothing verified checked it
    assert row.bucket == "unconfirmed"
    assert finding_types(honest_report, "C") == set()  # and it is not a finding against the practice


def test_the_synthetic_invoice_reports_its_own_coverage_honestly(honest_report):
    """150 € of 350 € could be judged. The remaining 200 € is our rule coverage, not their billing."""
    assert honest_report.coverage_ratio == pytest.approx(150 / 350)
    assert (
        honest_report.confirmed_fine_eur
        + honest_report.confirmed_wrong_eur
        + honest_report.unconfirmed_eur
        == honest_report.claimed_total_eur
    )


def test_the_unconfirmed_position_is_not_counted_as_refund_exposure(honest_report):
    """Stated as the comparison that motivated the change. The old figure was
    `claimed_total − defensible_total`; every euro not positively confirmed landed in it."""
    old_at_risk = honest_report.claimed_total_eur - honest_report.defensible_total_eur
    assert old_at_risk == Decimal("50.00")

    # Here the old and new numbers agree, because the stub confirms C as billable. The point is that
    # they agree for the wrong reason: the old figure was a subtraction that happened to come out
    # right, and it had no way to distinguish C's 200 € from B's 50 €. The new one says which is
    # which, and only B is exposure.
    assert honest_report.confirmed_wrong_eur == Decimal("50.00")
    assert honest_report.unconfirmed_eur == Decimal("200.00")
    assert position(honest_report, "C").bucket == "unconfirmed"


def test_an_unverified_rule_downgrades_a_position_from_fine_to_unconfirmed(tmp_path, settings):
    """The other half of the honesty contract, and the reason `advisory_rule_ids` exists.

    Same invoice, but the store also holds an *unverified* rule excluding 8100 whenever 8300 is
    charged. Under the default `warn` policy that rule suppresses nothing, so the solver still
    returns 8100 as billable and every check still passes. It must nevertheless stop being green: a
    machine-extracted rule that would have removed the position is precisely the case where "no
    finding" must not be read as "the rules confirmed it".
    """
    from app.rules.rule_store import ExclusionRule

    rules = _synthetic_rules()
    advisory = ExclusionRule(
        rule_id="excl_synthetic_unverified",
        from_ziffer="8300",
        to_ziffer="8100",
        direction="one_way",
        legal_basis="Automatisch extrahiert, nicht geprüft",
        verified=False,
        source="auto_extracted:ist_neben",
    )
    # Where `warn` policy puts an unverified rule: loaded and counted, never enforced.
    rules.suppressed.append(advisory)

    report = audit_delivery(
        _synthetic_delivery(),
        catalog=_synthetic_catalog(tmp_path),
        rules=rules,
        souffle_run=_synthetic_souffle_run(),
        settings=settings,
    )

    row = position(report, "A")
    assert row.verdict == "chargeable"
    assert row.accepted_as_claimed is True
    assert row.advisory_rule_ids == ["excl_synthetic_unverified"]
    assert row.bucket == "unconfirmed"
    assert "nicht verifizierte Regel" in row.bucket_reason

    # A's 100 € moves from green to grey. No euro is created or destroyed, and nothing moves to red:
    # an unverified rule can never make a position wrong, only unconfirmed.
    assert report.confirmed_fine_eur == Decimal("0.00")
    assert report.confirmed_wrong_eur == Decimal("50.00")
    assert report.unconfirmed_eur == Decimal("300.00")
    assert report.claimed_total_eur == Decimal("350.00")


def test_a_second_case_reusing_position_numbers_does_not_inherit_the_first_case_verdict(
    tmp_path, settings
):
    """`positionsnr` is unique within an `abrechnungsfall`, not across a delivery.

    Two cases each numbering a position "B" is legal PADnext. Case one's "B" is removed by the
    verified exclusion; case two's "B" charges GOÄ 8400, which the solver simply does not confirm —
    so both carry the verdict `blocked`, and only the first has a rule behind it.

    That is the pair that makes the collision expensive. Keyed on `positionsnr`, case two's "B" would
    look up case one's verified exclusion, find `verified=True`, and be reported as provably wrong —
    75 € of refund exposure invented out of a numbering clash, on a position whose only defect is
    that our rules never confirmed it. Keyed on row identity, it stays `unconfirmed`.
    """
    delivery = _synthetic_delivery()
    delivery.invoices[0].cases.append(
        PadnextCase(
            behandlungsart="0",
            positions=[
                PadnextPosition(
                    positionsnr="B",  # the same number the excluded position carries in case one
                    go="GOÄ",
                    ziffer="8400",
                    anzahl=1,
                    faktor=Decimal("2.0"),
                    gesamtbetrag=Decimal("150.00"),
                    text="Zweiter Fall, gleiche Positionsnummer",
                )
            ],
        )
    )

    report = audit_delivery(
        delivery,
        catalog=_synthetic_catalog(tmp_path),
        rules=_synthetic_rules(),
        souffle_run=_synthetic_souffle_run(),
        settings=settings,
    )

    second = next(p for p in report.positions if p.ziffer == "8400")
    assert second.positionsnr == "B"  # the collision is real, not hypothetical
    assert second.verdict == "blocked"  # and both rows share the verdict
    assert second.verified_rule_ids == []  # but no verified rule bears on 8400
    assert second.bucket == "unconfirmed"

    # 50 € of exposure, exactly as with one case. The extra 150 € is unconfirmed, not wrong.
    assert report.claimed_total_eur == Decimal("500.00")
    assert report.confirmed_wrong_eur == Decimal("50.00")
    assert report.confirmed_fine_eur == Decimal("100.00")
    assert report.unconfirmed_eur == Decimal("350.00")


# ------------------------------------------------------------------------------------------
# mutual exclusion: the finding lands on both sides, the money lands on the cheaper one
# ------------------------------------------------------------------------------------------
#
# A `Conflict` is the rules engine saying it cannot decide which of two positions the practice
# meant to keep. Reporting both is right — the practice must drop one. Charging *both* amounts to
# `confirmed_wrong` is not: GOÄ 5 (10.72 €) beside GOÄ 7 (21.45 €) overcharges by at most 10.72 €,
# and the engine used to report 32.17 €, treating an ambiguity as if the whole encounter were
# fictitious. These tests pin the lower bound and the fact that it stays a lower bound.


def _mutual_delivery(*positions: tuple[str, str, str]) -> PadnextDelivery:
    """A one-case delivery of `(positionsnr, ziffer, gesamtbetrag)` at the Schwellenwert."""
    return PadnextDelivery(
        nachrichtentyp="ADL",
        version="02.12",
        source_name="mutual_padx.xml",
        invoices=[
            PadnextInvoice(
                invoice_id="MUT-1",
                cases=[
                    PadnextCase(
                        behandlungsart="0",
                        positions=[
                            PadnextPosition(
                                positionsnr=nr,
                                ziffer=ziffer,
                                go="GOÄ",
                                anzahl=1,
                                faktor=Decimal("2.3"),
                                gesamtbetrag=Decimal(betrag),
                            )
                            for nr, ziffer, betrag in positions
                        ],
                    )
                ],
            )
        ],
    )


@pytest.fixture
def mutual_report(pipeline):
    """GOÄ 5 and GOÄ 7, both priced correctly, nothing else wrong with either line."""
    return audit_delivery(
        _mutual_delivery(("1", "5", "10.72"), ("2", "7", "21.45")),
        catalog=pipeline.catalog,
        rules=pipeline.rules,
        souffle_run=pipeline.souffle.run,
    )


def test_a_mutual_exclusion_still_reports_both_positions(mutual_report):
    """The regression guard on the fix: the money moved, the finding did not. A reviewer must
    still see that both lines are implicated, because only a human can say which one is real."""
    for nr in ("1", "2"):
        row = position(mutual_report, nr)
        assert row.verdict == "blocked"
        assert "padnext_mutual_exclusion" in finding_types(mutual_report, nr)


def test_only_the_cheaper_side_of_a_mutual_exclusion_is_confirmed_wrong(mutual_report):
    """10.72 €, not 32.17 €. The dearer position survives the cluster and is `unconfirmed` —
    not `confirmed_fine`, because nothing confirmed it either."""
    assert mutual_report.confirmed_wrong_eur == Decimal("10.72")
    assert mutual_report.unconfirmed_eur == Decimal("21.45")
    assert mutual_report.confirmed_fine_eur == Decimal("0.00")
    assert position(mutual_report, "1").bucket == "confirmed_wrong"
    assert position(mutual_report, "2").bucket == "unconfirmed"


def test_the_surviving_side_says_why_it_survived(mutual_report):
    """`unconfirmed` here is a different statement from "no rule covers this Ziffer", and the
    reason has to distinguish them or a reader will read a rule gap where there is none."""
    reason = position(mutual_report, "2").bucket_reason
    assert "Wechselseitiger Ausschluss" in reason
    assert "GOÄ 5" in reason


def test_the_buckets_still_account_for_every_euro_of_a_mutual_exclusion(mutual_report):
    total = (
        mutual_report.confirmed_fine_eur
        + mutual_report.confirmed_wrong_eur
        + mutual_report.unconfirmed_eur
    )
    assert total == mutual_report.claimed_total_eur == Decimal("32.17")


def test_a_four_way_exclusion_cluster_keeps_exactly_one_survivor(pipeline):
    """GOÄ 5/6/7/8 arrive as several overlapping pairs. Choosing a survivor per *pair* would leave
    every member surviving something and charge nothing to `confirmed_wrong`; the pairs are unioned
    into one cluster first, so three of the four are the overcharge."""
    report = audit_delivery(
        _mutual_delivery(
            ("1", "5", "10.72"),
            ("2", "6", "13.41"),
            ("3", "7", "21.45"),
            ("4", "8", "34.86"),
        ),
        catalog=pipeline.catalog,
        rules=pipeline.rules,
        souffle_run=pipeline.souffle.run,
    )
    buckets = {p.positionsnr: p.bucket for p in report.positions}
    assert sum(1 for b in buckets.values() if b == "unconfirmed") == 1
    assert buckets["4"] == "unconfirmed", "the dearest member is the one kept"
    assert report.confirmed_wrong_eur == Decimal("45.58")  # 10.72 + 13.41 + 21.45
    assert (
        report.confirmed_fine_eur + report.confirmed_wrong_eur + report.unconfirmed_eur
        == report.claimed_total_eur
    )


def test_surviving_a_cluster_does_not_excuse_a_defect_of_the_lines_own(pipeline):
    """Position 5 of the bundled example is the dearer half of the 5/7 cluster *and* understates
    its own total by 1 €. Surviving the cluster must not launder that: an independent verified
    defect is checked first and still puts the line in `confirmed_wrong`."""
    report = audit_delivery(
        _mutual_delivery(("1", "5", "10.72"), ("2", "7", "20.45")),  # 20.45 recomputes to 21.45
        catalog=pipeline.catalog,
        rules=pipeline.rules,
        souffle_run=pipeline.souffle.run,
    )
    row = position(report, "2")
    assert "padnext_amount_mismatch" in finding_types(report, "2")
    assert row.bucket == "confirmed_wrong"
    assert report.confirmed_wrong_eur == Decimal("31.17")


# ------------------------------------------------------------------------------------------
# § 12 Abs. 3 attaches above the Schwellenwert, including above the Höchstsatz
# ------------------------------------------------------------------------------------------


def test_a_factor_above_the_hoechstsatz_still_requires_a_justification(report):
    """Position 9 charges 4.0 against a maximum of 3.5. It used to report
    `justification_required: false`, because the cap branch short-circuited the § 12 Abs. 3 flag —
    a factor so high it is illegal was reported as needing no written reason at all."""
    row = position(report, "9")
    assert row.factor_within_band is False
    assert row.justification_required is True
    assert row.justification_present is True  # the position does carry a begruendung
    assert "padnext_factor_above_maximum" in finding_types(report, "9")


def test_an_illegal_factor_reports_one_error_not_two(report):
    """The flag moved out of the branch; the *finding* stayed in it. A reviewer sees the error that
    decides what happens next — the factor is above the legal maximum — not that plus a second
    error about the paperwork for a factor that may not be charged at all."""
    assert "padnext_justification_missing" not in finding_types(report, "9")
