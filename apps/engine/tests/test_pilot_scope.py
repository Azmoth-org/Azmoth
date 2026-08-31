"""The pilot's temporal scope warning: it fires, it is accurate, and it never blocks.

The feature under test is a *caveat*, and the whole value of a caveat is that it costs the user
nothing. So the assertions here fall into two halves and the second half is the important one:

    it fires    an invoice older than `PILOT_MAX_INVOICE_AGE_DAYS` comes back with a warning
                naming the reason, and a recent one does not.

    it is inert every status code, every verdict, every bucket and every euro is byte-for-byte
                what the same delivery produced before this feature existed — including the
                receipt hash, which must not become a function of what day the audit ran.

`app/padnext/pilot_scope.py` states the reasoning; this file is what stops it from quietly
becoming a gate the next time somebody "tightens" it.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

from app.config import PADNEXT_EXAMPLES_DIR, Settings
from app.padnext import audit_delivery, read_delivery
from app.padnext.pilot_scope import (
    TEMPORAL_SCOPE_WARNING,
    latest_service_date,
    parse_service_date,
    temporal_scope_warnings,
)
from app.schemas.padnext import PadnextPosition

PAYLOAD_NAME = "00004711_20260726_ADL_000001_padx.xml"

#: A fixed "today", so these tests assert on an age rather than on the wall clock. The bundled
#: fixture is dated 2026-07-20 and gets one day older every day nobody touches this repo; a test
#: that read `date.today()` would start passing or failing for reasons unrelated to the code.
TODAY = date(2026, 8, 31)


def position(datum: str | None) -> PadnextPosition:
    return PadnextPosition(positionsnr="1", ziffer="1", datum=datum)


def settings_with(days: int) -> Settings:
    return Settings(pilot_max_invoice_age_days=days)


# ==========================================================================================
# 1. reading a date
# ==========================================================================================


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2020-03-01", date(2020, 3, 1)),  # xs:date — what the ADL schema mandates
        ("01.03.2020", date(2020, 3, 1)),  # a real PVS export under PADNEXT_SCHEMA_POLICY=warn
        ("20200301", date(2020, 3, 1)),  # the same, without separators
        ("  2020-03-01  ", date(2020, 3, 1)),
    ],
)
def test_the_date_formats_a_real_export_actually_carries_are_read(raw, expected):
    assert parse_service_date(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "letzten Monat", "2020-13-45", "2020"])
def test_an_unreadable_date_is_not_a_date_rather_than_an_error(raw):
    """The safe direction. A `<datum>` we cannot parse must produce no warning at all — reporting
    an unreadable field as "this invoice is old" would be a false statement about the invoice, and
    the malformed field is already reported by the reader and the schema check."""
    assert parse_service_date(raw) is None


def test_the_delivery_is_as_old_as_its_newest_treatment():
    """A maximum, not a minimum, and this is the case that decides it: an otherwise current
    invoice carrying one carried-over line from years ago must not be flagged as historical. A
    warning that fires on normal invoices is a warning nobody reads."""
    positions = [position("2019-01-01"), position("2026-08-01"), position("2024-06-30")]

    assert latest_service_date(positions) == date(2026, 8, 1)


def test_a_delivery_with_no_readable_date_anywhere_yields_none():
    assert latest_service_date([position(None), position("irgendwann")]) is None


# ==========================================================================================
# 2. when the warning fires
# ==========================================================================================


def test_an_invoice_from_2020_is_flagged():
    warnings, checked, latest = temporal_scope_warnings(
        [position("2020-03-01")], settings=settings_with(365), today=TODAY
    )

    assert warnings == [TEMPORAL_SCOPE_WARNING]
    assert checked is True
    assert latest == "2020-03-01"


def test_an_invoice_from_last_month_is_not_flagged():
    warnings, checked, latest = temporal_scope_warnings(
        [position("2026-08-01")], settings=settings_with(365), today=TODAY
    )

    assert warnings == []
    assert checked is True, "checked and clean is not the same as never asked"
    assert latest == "2026-08-01"


def test_the_boundary_is_older_than_the_limit_rather_than_at_it():
    """Exactly 365 days old is inside the window the pilot asks for, so it does not warn. One day
    past it does. Asserted at both sides because an off-by-one here is invisible in production and
    shows up as a partner asking why last September's invoice is 'historical'."""
    at_limit = TODAY - timedelta(days=365)
    past_limit = TODAY - timedelta(days=366)

    assert temporal_scope_warnings(
        [position(at_limit.isoformat())], settings=settings_with(365), today=TODAY
    )[0] == []
    assert temporal_scope_warnings(
        [position(past_limit.isoformat())], settings=settings_with(365), today=TODAY
    )[0] == [TEMPORAL_SCOPE_WARNING]


def test_a_future_date_is_not_reported_as_historical():
    """A Leistungsdatum in the future is a different defect and not this module's. Comparing on the
    signed difference means it simply does not fire, rather than firing on a negative age."""
    warnings, _, _ = temporal_scope_warnings(
        [position("2027-01-01")], settings=settings_with(365), today=TODAY
    )

    assert warnings == []


def test_no_readable_date_means_not_checked_rather_than_checked_and_fine():
    """The distinction `schema_policy` draws for `schema_warnings`, drawn again here: an empty
    `pilot_warnings` must not be readable as "this invoice is recent" when no date was found."""
    warnings, checked, latest = temporal_scope_warnings(
        [position(None)], settings=settings_with(365), today=TODAY
    )

    assert warnings == []
    assert checked is False
    assert latest == ""


def test_zero_switches_the_check_off():
    """For a deployment carrying real historical catalog editions, where the caveat would be a
    false statement rather than an honest one."""
    warnings, checked, _ = temporal_scope_warnings(
        [position("2005-01-01")], settings=settings_with(0), today=TODAY
    )

    assert warnings == []
    assert checked is False


def test_the_wording_names_the_reason_and_not_only_the_symptom():
    """The sentence has to survive being read alone, in a PDF, by somebody who was told nothing
    else — so it must say *why* an old invoice matters here, not just that it is old."""
    assert "12 Monate" in TEMPORAL_SCOPE_WARNING
    assert "GOÄ-Katalog" in TEMPORAL_SCOPE_WARNING
    assert "aktuellen" in TEMPORAL_SCOPE_WARNING


# ==========================================================================================
# 3. the guarantee: it is a warning, not a gate
# ==========================================================================================


def aged_payload(years_back: int) -> bytes:
    """The bundled synthetic delivery with every `<datum>` moved back by whole years.

    Whole years so the day and month — and therefore the weekday-independent shape of the file —
    are untouched, and the only thing that differs from the fixture the rest of the suite audits
    is the year. Anything this delivery does differently is therefore attributable to its age.
    """
    payload = (PADNEXT_EXAMPLES_DIR / PAYLOAD_NAME).read_bytes().decode("utf-8")
    return re.sub(
        r"<datum>(\d{4})(-\d{2}-\d{2})</datum>",
        lambda m: f"<datum>{int(m.group(1)) - years_back}{m.group(2)}</datum>",
        payload,
    ).encode("utf-8")


@pytest.fixture
def recent_report(client) -> dict:
    response = client.post(
        "/api/v1/padnext/audit",
        content=(PADNEXT_EXAMPLES_DIR / PAYLOAD_NAME).read_bytes(),
        headers={"Content-Type": "application/xml"},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def historical_report(client) -> dict:
    response = client.post(
        "/api/v1/padnext/audit",
        content=aged_payload(6),  # 2026 → 2020
        headers={"Content-Type": "application/xml"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_a_2020_delivery_is_audited_rather_than_refused(historical_report):
    """The constraint the whole feature is under: 200, with a real report. If this ever becomes a
    422 the pilot has been broken by its own safety rail."""
    assert historical_report["positions"], "an old delivery must still be audited, not refused"
    assert historical_report["pilot_warnings"] == [TEMPORAL_SCOPE_WARNING]
    assert historical_report["pilot_scope_checked"] is True
    assert historical_report["latest_service_date"].startswith("2020-")


def test_a_current_delivery_carries_no_pilot_warning(recent_report):
    """The negative, so a non-empty `pilot_warnings` always means something rather than being an
    artefact of the check being on."""
    assert recent_report["pilot_warnings"] == []
    assert recent_report["pilot_scope_checked"] is True


def test_the_warning_is_kept_out_of_findings_and_out_of_schema_warnings(historical_report):
    """`findings` is what is wrong with the *invoice*; this is what is missing from the *engine*.
    A reviewer reading "n Befunde" must not be counting our own coverage gap among them — and
    `schema_warnings` means one thing only, that the file did not match the ADL schema."""
    assert historical_report["schema_warnings"] == []
    assert all(
        TEMPORAL_SCOPE_WARNING not in finding["message"]
        for finding in historical_report["findings"]
    )


def test_age_changes_no_verdict_no_bucket_and_no_euro(recent_report, historical_report):
    """The inertness guarantee, asserted against the same delivery audited twice. Every number the
    practice acts on has to be identical; the only difference between these two reports is the
    year in the dates and the warning that observes it."""
    money = [
        "claimed_total_eur",
        "recomputed_total_eur",
        "comparable_claimed_eur",
        "arithmetic_delta_eur",
        "defensible_total_eur",
        "confirmed_fine_eur",
        "confirmed_wrong_eur",
        "unconfirmed_eur",
    ]
    for field in money:
        assert historical_report[field] == recent_report[field], field

    assert historical_report["coverage_ratio"] == recent_report["coverage_ratio"]
    assert [p["verdict"] for p in historical_report["positions"]] == [
        p["verdict"] for p in recent_report["positions"]
    ]
    assert [p["bucket"] for p in historical_report["positions"]] == [
        p["bucket"] for p in recent_report["positions"]
    ]
    assert len(historical_report["findings"]) == len(recent_report["findings"])


def test_the_receipt_is_a_fingerprint_and_not_a_clock(pipeline):
    """`pilot_warnings` is deliberately outside the receipt.

    Were it inside, the same delivery audited identically would hash differently the morning its
    invoice crossed the twelve-month line — and every receipt stored before that morning would
    stop verifying, through the passage of time alone. Asserted by auditing one delivery under
    both settings: the warning appears in one report and not the other, and the hash does not move.
    """
    delivery, findings = read_delivery(aged_payload(6), source_name=PAYLOAD_NAME)

    def audit(max_age_days: int):
        return audit_delivery(
            delivery,
            catalog=pipeline.catalog,
            rules=pipeline.rules,
            souffle_run=pipeline.souffle.run,
            read_findings=findings,
            settings=Settings(pilot_max_invoice_age_days=max_age_days),
        )

    warned = audit(365)
    unchecked = audit(0)

    assert warned.pilot_warnings == [TEMPORAL_SCOPE_WARNING]
    assert unchecked.pilot_warnings == []
    assert warned.receipt_hash == unchecked.receipt_hash


def test_the_report_still_names_the_catalog_it_was_priced_against(historical_report):
    """The warning is only actionable beside the edition that caused it."""
    assert historical_report["catalog_version"]
