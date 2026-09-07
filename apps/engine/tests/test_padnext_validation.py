"""Batched validation: every problem with one delivery, in one answer.

Two properties are being defended here, and they pull in opposite directions.

**Completeness.** A delivery with three problems must report three problems. The failure this
prevents is not a wrong answer, it is a demoralising one: fix the missing `@echtdaten`, upload
again, get told the `posanzahl` is wrong, fix that, upload again. Three round trips for what was
one edit session, and the second one always looks as though the first fix achieved nothing.

**No new refusals.** It would be very easy for "more comprehensive validation" to start refusing
files the engine used to audit, which is the opposite of the point — `test_ok_agrees_with_the_
pipeline_it_reports_on` is the guard, and it is the most important test in this file. This
codebase's standing rule is *framing is fatal, positions are advisory*: an audit engine that
refused every imperfect invoice would refuse exactly the invoices worth auditing. Everything
`validation` adds beyond the reader is therefore a warning, and this file asserts that as hard as
it asserts the batching.

A third thing is asserted at the seams: **the HTTP contract does not move.**
`PadnextValidationFailed` adopts the primary problem's `error_code`, status, message and
`details`, so a client switching on
`ECHTDATEN_UNDECLARED` or reading `details.line` cannot tell this module was introduced.
`tests/test_error_handling.py` and `tests/test_padnext_schema.py` are the other half of that
assertion — they were written before batching existed and still pass unchanged, which is the
strongest available evidence.
"""

from __future__ import annotations

import io
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

from app.config import PADNEXT_EXAMPLES_DIR, REPO_ROOT, PadnextSchemaPolicy
from app.errors import ErrorCode
from app.padnext import (
    EchtdatenUndeclared,
    PadnextError,
    PadnextValidationFailed,
    audit_delivery,
    read_delivery,
    validate_bytes,
    validate_file,
)
from app.padnext.reader import MAX_XML_BYTES, MAX_ZIP_MEMBERS
from app.padnext.validation import (
    CATALOG,
    MAX_SUMMARY_CHARS,
    MAX_REPORTED_ISSUES,
    SUPPORTED_VERSION,
    ValidationResult,
    build_preview,
    one_line,
)

PAYLOAD_NAME = "00004711_20260726_ADL_000001_padx.xml"
ORDER_NAME = "00004711_20260726_ADL_000001.auf"
CONTAINER_NAME = "00004711_20260726_ADL_000001.padx"
FIXTURES = Path(__file__).parent / "fixtures" / "invalid_padnext"
CLI = REPO_ROOT / "scripts" / "validate_padnext.py"


@pytest.fixture(scope="module")
def payload() -> bytes:
    return (PADNEXT_EXAMPLES_DIR / PAYLOAD_NAME).read_bytes()


@pytest.fixture(scope="module")
def order() -> bytes:
    return (PADNEXT_EXAMPLES_DIR / ORDER_NAME).read_bytes()


def container(order: bytes, payload: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(ORDER_NAME, order)
        archive.writestr(PAYLOAD_NAME, payload)
    return buf.getvalue()


def undeclare(payload: bytes) -> bytes:
    """Strip `@echtdaten` from the `<rechnungen>` start tag only.

    Anchored at the start of a line, because the bundled fixture's comment header spells the
    attribute out too — a blanket byte replace edits the prose and produces a test that passes for
    the wrong reason. Borrowed from `tests/test_padnext.py::without_declaration` for that reason.
    """
    match = re.search(rb"^<rechnungen\b", payload, re.MULTILINE)
    assert match, "no <rechnungen> root element at the start of a line"
    end = payload.index(b">", match.start())
    tag = re.sub(rb'\s*echtdaten\s*=\s*"[^"]*"', b"", payload[match.start() : end])
    assert b"echtdaten" not in tag, tag
    return payload[: match.start()] + tag + payload[end:]


def codes(issues) -> list[str]:
    return [issue.code for issue in issues]


# ==========================================================================================
# the headline: everything at once
# ==========================================================================================


def test_three_problems_in_one_file_are_all_reported(payload):
    """The reason this module exists.

    One file, three independent mistakes of three different kinds — a datatype the schema refuses,
    a missing anonymisation declaration, and a version this engine does not know. Before batching,
    an upload answered with whichever one the reader hit first, and the other two were discovered
    on the second and third attempt.
    """
    broken = payload.replace(b'posanzahl="9"', b'posanzahl="viele"')
    broken = undeclare(broken)
    broken = broken.replace(b'version="02.12"', b'version="2.10"')

    result = validate_bytes(broken, source_name="drei_padx.xml")

    assert result.status == "validation_failed"
    assert "xsd_violation" in codes(result.errors)
    assert "echtdaten_undeclared" in codes(result.errors)
    assert "unsupported_version" in codes(result.warnings)
    assert len(result.errors) >= 2, (
        f"the point of the module is that both blocking problems arrive together: "
        f"{codes(result.errors)}"
    )


def test_a_file_with_nothing_wrong_reports_nothing_blocking(payload, order):
    """The other half. Without it, a validator refusing everything would pass every test above."""
    result = validate_bytes(container(order, payload), source_name=CONTAINER_NAME)

    assert result.ok and result.status == "valid", codes(result.errors)
    assert result.delivery is not None, "a valid delivery is handed back read, not re-read"
    # The bundled container declares its transfer number and its version, so it earns no notes.
    assert codes(result.warnings) == [], codes(result.warnings)


def test_every_error_carries_all_four_sections(payload):
    """What / where / why / how. A message missing one of them is an unfinished message.

    `message_en` is exempt where the issue came from the reader's own findings, which exist only in
    German — see `issue_from_finding`. Every issue this module raises itself has both.
    """
    result = validate_bytes(undeclare(payload), source_name="ohne_padx.xml")

    for issue in result.errors:
        assert issue.message_de.strip(), issue.code
        assert issue.message_en.strip(), issue.code
        assert issue.why_de.strip(), f"{issue.code} does not say why it matters"
        assert issue.fix.strip(), f"{issue.code} does not say how to fix it"
        assert issue.field or issue.path, f"{issue.code} does not say where it is"


@pytest.mark.parametrize("code", sorted(CATALOG))
def test_the_catalog_itself_is_complete(code):
    """Asserted over the catalog rather than over triggered issues, so a code added tomorrow with
    an empty `why` fails here instead of reaching a practice as a blank error."""
    spec = CATALOG[code]

    assert spec.summary_de.strip() and spec.summary_en.strip(), code
    assert spec.message_de.strip() and spec.message_en.strip(), code
    assert spec.why_de.strip() and spec.why_en.strip(), code
    assert spec.fix.strip() and spec.fix_en.strip(), code
    # The collapsed row is one line. A "summary" that needs two is the wall it exists to remove.
    assert len(spec.summary_de) <= MAX_SUMMARY_CHARS, (code, len(spec.summary_de))
    assert len(spec.summary_en) <= MAX_SUMMARY_CHARS, (code, len(spec.summary_en))
    assert "\n" not in spec.summary_de and "\n" not in spec.summary_en, code
    # No instruction and no reasoning in the summary — those live in `fix` and `why_de`, behind
    # the disclosure. A summary that already tells the reader what to do makes expanding pointless.
    for banned in ("Führen Sie", "Bitte ", "Lösung", "Warum"):
        assert banned not in spec.summary_de, (code, banned)
    assert spec.severity in {"info", "warning", "error"}
    assert spec.blocking is (spec.severity == "error") or not spec.blocking, (
        "a blocking issue must be an error; a non-blocking one may be any severity"
    )


# ==========================================================================================
# no new refusals
# ==========================================================================================

#: Every delivery this suite can lay hands on, valid and invalid, as (label, bytes-producer).
#: Parametrised over the *committed* fixtures rather than over hand-written strings so the set
#: cannot quietly shrink to the cases that happen to pass.
ALL_FIXTURES = sorted(p.name for p in FIXTURES.iterdir() if p.suffix == ".xml")


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_ok_agrees_with_the_pipeline_it_reports_on(pipeline, name):
    """**The most important test in this file.**

    `validate_bytes(...).ok` must be true for exactly the deliveries `read_delivery` reads and
    `audit_delivery` accepts. A validator that is stricter than the pipeline turns a working upload
    into a refusal; one that is more permissive promises an audit that then fails with a different
    error. Either is a silent contract change, so the two are compared directly rather than
    described.
    """
    data = (FIXTURES / name).read_bytes()
    result = validate_bytes(data, source_name=name)

    try:
        delivery, findings = read_delivery(data, source_name=name)
        audit_delivery(
            delivery,
            catalog=pipeline.catalog,
            rules=pipeline.rules,
            souffle_run=pipeline.souffle.run,
            read_findings=findings,
            settings=pipeline.settings,
        )
    except PadnextError:
        pipeline_accepts = False
    except Exception:  # noqa: BLE001 - anything else is a different failure, not a refusal
        pipeline_accepts = True
    else:
        pipeline_accepts = True

    assert result.ok is pipeline_accepts, (
        f"{name}: validator says ok={result.ok}, the pipeline says {pipeline_accepts}. "
        f"errors={codes(result.errors)}"
    )


def test_a_position_level_problem_is_a_warning_and_never_blocks(payload):
    """Framing is fatal, positions are advisory — the rule this module must not have moved.

    A `goziffer` with no `@ziffer` cannot be checked, and the reader says so at `severity="error"`.
    It is still not blocking, because refusing the delivery over it would refuse exactly the export
    a practice most needs read. The two fields say both things at once.
    """
    broken = payload.replace(b'ziffer="200"', b'ziffer=""')

    result = validate_bytes(broken, source_name="ohne_ziffer_padx.xml")

    assert result.ok, codes(result.errors)
    ziffer_issues = [w for w in result.warnings if w.code == "padnext_position_without_ziffer"]
    assert ziffer_issues, codes(result.warnings)
    assert ziffer_issues[0].severity == "error", "the finding's own severity is preserved"
    assert ziffer_issues[0].blocking is False, "and it still does not refuse the delivery"


def test_a_missing_transfer_number_is_never_a_refusal(payload, order):
    """It cannot be an error, and the reason is a supported input.

    A bare `*_padx.xml` has no `<auftrag>` to carry a transfer number, and that upload is taken by
    the API, used by the public demo, and read by half this suite. Refusing it would delete a
    working path to enforce a field that affects nothing in the audit — so: a warning when an order
    file is present and silent, an informational note when there is none.
    """
    silent_order = order.replace(b'transfernr="1"', b'transfernr=""')

    with_order = validate_bytes(container(silent_order, payload), source_name=CONTAINER_NAME)
    assert with_order.ok
    assert "transfernr_missing" in codes(with_order.warnings)

    bare = validate_bytes(payload, source_name=PAYLOAD_NAME)
    assert bare.ok
    assert "transfernr_unknown" in codes(bare.warnings)


@pytest.mark.parametrize("raw,expected", [("02.12", False), ("2.12", False), ("2.10", True)])
def test_the_version_note_fires_on_the_version_and_not_on_the_padding(payload, raw, expected):
    """`02.12` is the zero-padded spelling the bundled order file uses and the spec allows.

    Without normalisation the note would fire on every conforming delivery in existence — a warning
    that is wrong on the files it exists to stay quiet about is ignored within a day.
    """
    edited = payload.replace(b'version="02.12"', f'version="{raw}"'.encode())

    result = validate_bytes(edited, source_name=PAYLOAD_NAME)

    assert ("unsupported_version" in codes(result.warnings)) is expected
    if expected:
        note = next(w for w in result.warnings if w.code == "unsupported_version")
        assert raw in note.message_de and SUPPORTED_VERSION in note.message_de


# ==========================================================================================
# malformed XML
# ==========================================================================================


@pytest.mark.parametrize(
    "body,description",
    [
        (b"<rechnungen><rechnung></rechnungen>", "unclosed element"),
        (b"<rechnungen>\n  <rechnung>\n    <kaputt>\n", "truncated document"),
        (b"<a>&nosuchentity;</a>", "undefined entity"),
    ],
)
def test_malformed_xml_names_its_position_and_stays_a_400(body, description):
    result = validate_bytes(body, source_name="kaputt.xml")

    assert result.status == "parse_failed", description
    assert codes(result.errors) == ["xml_syntax_error"], description
    problem = result.errors[0]
    assert problem.line and problem.line >= 1, description
    assert problem.column is not None, description
    assert problem.legacy_code is ErrorCode.INVALID_XML
    assert problem.legacy_status == 400, "well-formedness is a malformed request, not bad content"
    # The German text must not stutter "Ungültiges XML: XML is not well formed: …".
    assert "XML is not well formed" not in problem.message_de


def test_a_truncated_export_still_shows_what_it_managed_to_write():
    """Partial parsing, and the reason it is worth the recovering parse.

    "Everything is broken" and "your first two invoices are fine and the file was cut off" call for
    different next actions, and only one of them is true. `recovered` marks the counts as a floor.
    """
    truncated = (
        b'<rechnungen anzahl="3" echtdaten="false" xmlns="http://padinfo.de/ns/pad">'
        b"<nachrichtentyp version=\"02.12\">ADL</nachrichtentyp>"
        b'<rechnung id="A"><abrechnungsfall><behandlungsart>0</behandlungsart>'
        b'<positionen posanzahl="2">'
        b'<goziffer positionsnr="1" ziffer="1"><datum>2026-09-01</datum></goziffer>'
        b'<goziffer positionsnr="2" ziffer="3"><datum>2026-09-15</datum></goziffer>'
        b"</positionen></abrechnungsfall></rechnung>"
        b'<rechnung id="B"><abrechnungsfall><positionen'
    )

    result = validate_bytes(truncated, source_name="abgebrochen.xml")

    assert result.status == "parse_failed"
    preview = result.preview
    assert preview.recovered is True, "the counts are a floor and must say so"
    assert preview.invoice_count == 2
    assert preview.position_count == 2
    assert preview.date_range == "01.09.2026 bis 15.09.2026"
    assert preview.first_invoice == {
        "invoice_id": "A",
        "behandlungsart": "0",
        "behandlungsart_label": "ambulante Behandlung",
        "position_count": 2,
    }


def test_a_preview_survives_a_typod_namespace():
    """The preview matches on local names.

    A file with `xmlns="http://padinfo.de/ns/pdd"` is refused by the schema — and a preview that
    reported zero invoices for it would be telling the reader the opposite of what is wrong.
    """
    preview = build_preview(
        b'<rechnungen xmlns="http://padinfo.de/ns/pdd"><rechnung id="X">'
        b"<abrechnungsfall><positionen><goziffer ziffer=\"1\"/></positionen>"
        b"</abrechnungsfall></rechnung></rechnungen>"
    )

    assert preview.invoice_count == 1
    assert preview.position_count == 1


def test_a_datum_that_is_not_iso_does_not_break_the_preview():
    """A PVS writing `20.07.2026` must not raise inside the one component whose whole job is to
    survive a malformed file. Non-ISO dates are skipped, not parsed and not guessed at."""
    preview = build_preview(
        b'<rechnungen xmlns="http://padinfo.de/ns/pad"><rechnung><abrechnungsfall>'
        b"<positionen><goziffer ziffer=\"1\"><datum>20.07.2026</datum></goziffer>"
        b"</positionen></abrechnungsfall></rechnung></rechnungen>"
    )

    assert preview.position_count == 1
    assert preview.first_service_date is None
    assert preview.date_range == ""


@pytest.mark.parametrize(
    "body,code",
    [
        (b"%PDF-1.7\n1 0 obj", "not_xml"),
        (b'<!DOCTYPE r [<!ENTITY a "aa">]><rechnungen/>', "xml_doctype_refused"),
        (b'<?xml version="1.0"?><Quittung xmlns="http://padinfo.de/ns/pad"/>', "unsupported_root"),
    ],
)
def test_the_refusals_that_are_not_about_content_keep_their_own_message(body, code):
    result = validate_bytes(body, source_name="x")

    assert codes(result.errors) == [code], codes(result.errors)


def test_an_order_file_on_its_own_is_named_as_such(order):
    """The most common wrong upload, and the one where a bare refusal is least helpful: the file is
    a perfectly good PADnext document, it is simply the other one."""
    result = validate_bytes(order, source_name=ORDER_NAME)

    assert codes(result.errors) == ["order_file_uploaded"]
    assert "_padx.xml" in result.errors[0].fix
    # Its own declarations are still previewed — this is the one upload that has them.
    assert result.preview.transfernr == "1"
    assert result.preview.echtdaten_declared == "0"


def test_a_broken_container_is_a_container_error_not_an_xml_error():
    corrupt = b"PK\x03\x04" + b"\x00" * 64

    result = validate_bytes(corrupt, source_name="kaputt.padx")

    assert codes(result.errors) == ["container_unreadable"]
    assert "unzip -t" in result.errors[0].command


def test_a_container_without_a_payload_says_what_member_it_wanted(order):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(ORDER_NAME, order)

    result = validate_bytes(buf.getvalue(), source_name="nur_auftrag.padx")

    assert codes(result.errors) == ["container_without_payload"]
    assert "_padx.xml" in result.errors[0].message_de


# ==========================================================================================
# the anonymisation gate
# ==========================================================================================


@pytest.mark.parametrize("spelling", ["ja", "yes", "nein", "2", ""])
def test_an_undeclared_or_unrecognised_echtdaten_is_still_blocking(payload, spelling, monkeypatch):
    monkeypatch.delenv("PADNEXT_ALLOW_REAL_DATA", raising=False)
    edited = re.sub(rb'echtdaten="[^"]*"', f'echtdaten="{spelling}"'.encode(), payload)

    result = validate_bytes(edited, source_name="ja_padx.xml")

    assert not result.ok
    problem = next(e for e in result.errors if e.field == "echtdaten")
    assert problem.legacy_code is ErrorCode.ECHTDATEN_UNDECLARED
    assert problem.legacy_status == 422
    if spelling:
        # The refusal quotes the value back: "es steht 'ja'" is a one-line fix in the export
        # profile, where "something is wrong with echtdaten" is a search through a 3 MB file.
        assert f"'{spelling}'" in problem.message_de
        assert problem.code == "echtdaten_unrecognised"
    else:
        assert problem.code == "echtdaten_undeclared"


def test_the_two_gates_say_the_same_thing(pipeline, payload, monkeypatch):
    """The validator refuses an undeclared delivery, and so does `audit_delivery` behind it.

    The audit's gate is the security control and does not depend on this module — that is the
    point of leaving it in place. What must not drift is the *message*, because it is the one the
    envelope carries and a shipped test reads substrings out of it. Asserted by comparing the two
    directly rather than by trusting a comment.
    """
    monkeypatch.delenv("PADNEXT_ALLOW_REAL_DATA", raising=False)
    undeclared = undeclare(payload)

    result = validate_bytes(undeclared, source_name=PAYLOAD_NAME)
    from_validator = result.primary.legacy_message

    delivery, findings = read_delivery(undeclared, source_name=PAYLOAD_NAME)
    with pytest.raises(EchtdatenUndeclared) as excinfo:
        audit_delivery(
            delivery,
            catalog=pipeline.catalog,
            rules=pipeline.rules,
            souffle_run=pipeline.souffle.run,
            read_findings=findings,
            settings=pipeline.settings,
        )

    assert from_validator == str(excinfo.value), (
        "the validator's refusal and the audit's must be the same sentence, or a client that "
        "reads the message sees one of two texts depending on which gate fired first"
    )
    assert "anonymize_padnext.py" in from_validator, "the message must name the way out"


def test_real_data_is_refused_with_its_own_code(payload, monkeypatch):
    monkeypatch.delenv("PADNEXT_ALLOW_REAL_DATA", raising=False)
    real = re.sub(rb'echtdaten="[^"]*"', b'echtdaten="1"', payload)

    result = validate_bytes(real, source_name="echt_padx.xml")

    problem = next(e for e in result.errors if e.field == "echtdaten")
    assert problem.code == "real_data_refused"
    assert problem.legacy_code is ErrorCode.REAL_DATA_REFUSED


def test_the_escape_hatch_opens_both_refusals_together(payload, monkeypatch):
    """`PADNEXT_ALLOW_REAL_DATA` is one switch for one decision, here as in the audit: an operator
    with a lawful basis for real deliveries has, a fortiori, accepted one that failed to declare."""
    monkeypatch.setenv("PADNEXT_ALLOW_REAL_DATA", "1")

    assert validate_bytes(undeclare(payload), source_name=PAYLOAD_NAME).ok
    assert validate_bytes(re.sub(rb'echtdaten="[^"]*"', b'echtdaten="1"', payload)).ok


def test_an_absent_attribute_still_gets_a_line_to_point_at(payload):
    """"Das Feld fehlt" without a position sends somebody scrolling. The root element's line is
    where the attribute would go, which is the actionable answer for a field that is not there."""
    result = validate_bytes(undeclare(payload), source_name=PAYLOAD_NAME)

    problem = next(e for e in result.errors if e.field == "echtdaten")
    assert problem.line and problem.line > 1
    assert "rechnungen/@echtdaten" in problem.path
    assert f"Zeile {problem.line}" in problem.location


def test_the_order_file_is_the_declaration_site_when_it_declared_something(payload, order):
    """The order file wins where both are present and disagree — `resolve_echtdaten`. When it is
    the site, no line is reported, because it is read with a parser that does not track them."""
    edited = order.replace(b'echtdaten="0"', b'echtdaten="ja"')

    result = validate_bytes(container(edited, payload), source_name=CONTAINER_NAME)

    problem = next(e for e in result.errors if e.field == "echtdaten")
    assert problem.path == "auftrag/@echtdaten"
    assert problem.line is None
    assert "'ja'" in problem.message_de


# ==========================================================================================
# the envelope, and which problem becomes it
# ==========================================================================================


def test_the_framing_failure_wins_over_the_declaration(payload):
    """Ordering is contract, because it decides the `error_code` a client sees.

    A file that is not an ADL document *and* fails to declare itself answers
    `PADNEXT_SCHEMA_VIOLATION` — the same code it answered before batching, because the schema gate
    ran before the audit's. Both problems are still in the list.
    """
    broken = undeclare(payload.replace(b'posanzahl="9"', b'posanzahl="viele"'))

    result = validate_bytes(broken, source_name="beides_padx.xml")

    assert result.primary.code == "xsd_violation"
    assert result.primary.legacy_code is ErrorCode.PADNEXT_SCHEMA_VIOLATION
    assert "echtdaten_undeclared" in codes(result.errors)


def test_the_exception_adopts_the_primary_problems_whole_identity():
    """`PadnextValidationFailed` must be indistinguishable from what shipped, plus new keys."""
    result = validate_file(FIXTURES / "wrong_namespace.xml")

    with pytest.raises(PadnextValidationFailed) as excinfo:
        result.raise_for_status()
    error = excinfo.value

    assert error.error_code is ErrorCode.PADNEXT_SCHEMA_VIOLATION
    assert error.http_status == 422
    assert "does not conform" in error.message, "the shipped message text is part of the contract"
    # The keys `tests/test_padnext_schema.py` and `tests/test_error_handling.py` already read.
    assert error.details["violation_count"] == len(result.schema_violations)
    assert all(
        {"message", "line", "column", "path", "location"} <= set(v)
        for v in error.details["violations"]
    )
    # And the ones that are new.
    assert error.details["error_count"] >= 1
    assert error.details["errors"][0]["code"] == "xsd_violation"
    assert "parsed_preview" in error.details


def test_a_valid_delivery_raises_nothing(payload):
    validate_bytes(payload, source_name=PAYLOAD_NAME).raise_for_status()


def test_a_flood_of_problems_is_capped_but_counted_honestly():
    """One systematic mistake produces one issue per position. A response carrying nine hundred of
    them helps nobody, and a response that quietly showed the first hundred as if they were all of
    them would be worse — so the counts are the totals and the lists say what did not fit."""
    positions = b"".join(
        f'<goziffer positionsnr="{n}" ziffer="{n}"><faktor>zwei</faktor></goziffer>'.encode()
        for n in range(1, MAX_REPORTED_ISSUES + 40)
    )
    flood = (
        b'<rechnungen anzahl="1" echtdaten="false" xmlns="http://padinfo.de/ns/pad">'
        b'<nachrichtentyp version="02.12">ADL</nachrichtentyp>'
        b'<rechnung id="F"><abrechnungsfall><behandlungsart>0</behandlungsart>'
        b"<positionen>" + positions + b"</positionen></abrechnungsfall></rechnung></rechnungen>"
    )

    result = validate_bytes(flood, source_name="flut_padx.xml")
    wire = result.as_dict()

    assert wire["warning_count"] > MAX_REPORTED_ISSUES
    assert len(wire["warnings"]) == MAX_REPORTED_ISSUES
    assert wire["warnings_omitted"] == wire["warning_count"] - MAX_REPORTED_ISSUES


def test_the_wire_shape_and_the_model_cannot_drift(payload):
    """`to_report` validates `as_dict` under `extra="forbid"`, so a field added to the dataclass
    without a home in the published model fails here instead of vanishing from the response."""
    result = validate_bytes(undeclare(payload), source_name=PAYLOAD_NAME)

    report = result.to_report()

    assert report.status == result.status
    assert report.error_count == len(result.errors)
    assert report.errors[0].code == result.errors[0].code
    assert report.parsed_preview.invoice_count == result.preview.invoice_count


# ==========================================================================================
# the schema policy
# ==========================================================================================


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_warn_moves_every_framing_violation_from_error_to_warning(name):
    result = validate_file(FIXTURES / name, schema_policy=PadnextSchemaPolicy.WARN)

    assert "xsd_violation" not in codes(result.errors)
    assert "xsd_violation" in codes(result.warnings)
    assert result.schema_policy == "warn"


def test_warn_still_puts_the_deviations_on_the_report_itself():
    """The inner read runs with the policy `off`, so the reader no longer produces the findings
    that become `PadnextAuditReport.schema_warnings` — the field that is the entire point of the
    `warn` policy. They are re-attached, and this is what says so."""
    result = validate_file(
        FIXTURES / "wrong_type_posanzahl.xml", schema_policy=PadnextSchemaPolicy.WARN
    )

    assert any(f.type == "padnext_schema_violation" for f in result.findings)


def test_warn_does_not_report_the_same_deviation_twice():
    """Once as an `xsd_violation`, once as a re-attached reader finding, would tell a user there
    are twice as many problems as there are."""
    result = validate_file(
        FIXTURES / "wrong_type_posanzahl.xml", schema_policy=PadnextSchemaPolicy.WARN
    )

    assert codes(result.warnings).count("xsd_violation") == 1
    assert "padnext_schema_violation" not in codes(result.warnings)


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_off_does_not_consult_the_schema_at_all(name):
    result = validate_file(FIXTURES / name, schema_policy=PadnextSchemaPolicy.OFF)

    assert "xsd_violation" not in codes(result.errors) + codes(result.warnings)


def test_the_delivery_records_the_policy_it_was_validated_under():
    """Not `off`, which is what the inner read was handed. A report naming a policy it did not run
    under is worse than one naming none."""
    result = validate_file(
        FIXTURES / "wrong_type_posanzahl.xml", schema_policy=PadnextSchemaPolicy.WARN
    )

    assert result.delivery is not None
    assert result.delivery.schema_policy == "warn"


# ==========================================================================================
# performance
# ==========================================================================================


def test_a_one_megabyte_delivery_validates_in_under_two_seconds():
    """The brief's budget, asserted rather than assumed.

    Validation runs three passes over the bytes — the schema, the reader, the preview — and a
    fourth would not be free. Generous by an order of magnitude on purpose: this must fail on a
    quadratic mistake, not on a loaded CI box.
    """
    positions = b"".join(
        (
            f'<goziffer positionsnr="{n}" go="GOÄ" ziffer="1">'
            f"<datum>2026-09-01</datum><anzahl>1</anzahl><faktor>2.3</faktor>"
            f"<punktzahl>80</punktzahl><gesamtbetrag>10.72</gesamtbetrag></goziffer>"
        ).encode()
        for n in range(6000)
    )
    big = (
        b'<rechnungen anzahl="1" echtdaten="false" xmlns="http://padinfo.de/ns/pad">'
        b'<nachrichtentyp version="02.12">ADL</nachrichtentyp>'
        b'<rechnung id="BIG"><abrechnungsfall><behandlungsart>0</behandlungsart>'
        b'<positionen posanzahl="6000">' + positions + b"</positionen>"
        b"</abrechnungsfall></rechnung></rechnungen>"
    )
    assert len(big) > 1_000_000, f"the fixture is only {len(big)} bytes"

    started = time.perf_counter()
    result = validate_bytes(big, source_name="gross_padx.xml")
    elapsed = time.perf_counter() - started

    assert result.ok, codes(result.errors)
    assert result.preview.position_count == 6000
    assert elapsed < 2.0, f"1 MB took {elapsed:.2f}s"


# ==========================================================================================
# the HTTP surface
# ==========================================================================================


def post(client, body: bytes, name: str = "case.xml", path: str = "validate"):
    return client.post(
        f"/api/v1/padnext/{path}",
        content=body,
        headers={"Content-Type": "application/xml", "x-padnext-filename": name},
    )


def test_validate_answers_200_even_for_a_delivery_it_would_refuse(client, payload):
    """The dry run's whole shape. `/audit` has to answer 422 for a refused delivery — the request
    genuinely failed. Here the request succeeded and the *file* is the subject, so a 422 would take
    away the distinction between "four problems were found" and "the check could not run"."""
    broken = undeclare(payload.replace(b'posanzahl="9"', b'posanzahl="viele"'))

    response = post(client, broken, "drei.xml")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "validation_failed"
    assert body["error_count"] >= 2
    assert {"code", "message_de", "message_en", "fix", "severity"} <= set(body["errors"][0])
    assert body["parsed_preview"]["invoice_count"] == 1


def test_validate_says_valid_for_the_bundled_delivery(client, payload):
    response = post(client, payload, PAYLOAD_NAME)

    assert response.status_code == 200, response.text
    assert response.json() == {
        **response.json(),
        "status": "valid",
        "error_count": 0,
        "errors": [],
    }


def test_validate_refuses_an_empty_body_and_says_what_to_send(client):
    response = post(client, b"")

    assert response.status_code == 400
    assert response.json()["error_code"] == "EMPTY_REQUEST_BODY"
    assert "padx" in response.json()["message"].lower()


def test_validate_starts_no_solve_and_consumes_no_quota(client, payload):
    """A practice iterating on a broken export profile must not pay per attempt, and the pilot's
    invoice counter must not drift away from the number of audits actually run."""
    before = post(client, payload, PAYLOAD_NAME)

    assert "x-quota-limit" not in {k.lower() for k in before.headers}
    assert "receipt_hash" not in before.json(), "nothing was audited, so nothing has a receipt"


def test_the_audit_endpoint_carries_the_whole_list_beside_the_legacy_details(client, payload):
    """The batching reaches an `/audit` caller too — under `details`, beside the shipped keys."""
    broken = undeclare(payload.replace(b'posanzahl="9"', b'posanzahl="viele"'))

    response = post(client, broken, "drei.xml", path="audit")

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error_code"] == "PADNEXT_SCHEMA_VIOLATION", "the shipped code, unchanged"
    details = body["details"]
    assert details["violations"], "and the shipped details, unchanged"
    assert details["error_count"] >= 2, "plus every problem, not only the one in the code"
    assert "echtdaten_undeclared" in [e["code"] for e in details["errors"]]
    assert details["parsed_preview"]["position_count"] == 9


def test_a_valid_delivery_still_audits_over_http(client, payload):
    """The regression that would matter most: nothing about a conforming delivery has changed."""
    response = post(client, payload, PAYLOAD_NAME, path="audit")

    assert response.status_code == 200, response.text
    assert response.json()["positions"], "the bundled example still audits, position by position"


# ==========================================================================================
# the CLI
# ==========================================================================================


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """The script under the interpreter running this test, so it finds the engine's dependencies."""
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )


def test_the_cli_reports_a_valid_delivery_and_exits_zero():
    done = run_cli(str(PADNEXT_EXAMPLES_DIR / CONTAINER_NAME), "--no-color")

    assert done.returncode == 0, done.stderr
    assert "PADnext-Validierungsbericht" in done.stdout
    assert "gültig" in done.stdout
    assert "Rechnungen:            1" in done.stdout
    assert "GOÄ/GOZ-Positionen:    9" in done.stdout


def test_the_cli_lists_every_problem_with_its_fix(tmp_path, payload):
    broken = undeclare(payload.replace(b'posanzahl="9"', b'posanzahl="viele"'))
    path = tmp_path / "drei_padx.xml"
    path.write_bytes(broken)

    done = run_cli(str(path), "--no-color")

    assert done.returncode == 1, done.stdout
    assert "Prüfung fehlgeschlagen" in done.stdout
    assert "[xsd_violation]" in done.stdout
    assert "[echtdaten_undeclared]" in done.stdout
    assert "Warum:" in done.stdout and "Lösung:" in done.stdout
    assert "anonymize_padnext.py" in done.stdout, "the fix command has to be copyable"
    # Even a failing report shows what was read.
    assert "Gelesen (auch bei Fehlern)" in done.stdout


def test_the_cli_separates_unreadable_from_invalid(tmp_path):
    """Exit 3 and exit 1 are different next actions: a broken file, versus a field to change."""
    broken = tmp_path / "kaputt.xml"
    broken.write_bytes(b"<rechnungen><rechnung></rechnungen>")

    done = run_cli(str(broken), "--no-color")

    assert done.returncode == 3, done.stdout
    assert "nicht lesbar" in done.stdout
    assert "[xml_syntax_error]" in done.stdout


def test_the_cli_emits_the_same_json_the_api_does(payload):
    import json

    done = run_cli(str(PADNEXT_EXAMPLES_DIR / PAYLOAD_NAME), "--json")

    assert done.returncode == 0, done.stderr
    document = json.loads(done.stdout)
    assert document["status"] == "valid"
    assert document["file"].endswith(PAYLOAD_NAME)
    assert document["parsed_preview"]["position_count"] == 9


def test_the_cli_reports_the_worst_outcome_across_several_files(tmp_path, payload):
    """`validate_padnext.py *.padx` in a hook fails on the batch, not on whichever file was last."""
    good = tmp_path / "gut_padx.xml"
    good.write_bytes(payload)
    bad = tmp_path / "schlecht_padx.xml"
    bad.write_bytes(undeclare(payload))

    assert run_cli(str(bad), str(good), "--no-color").returncode == 1
    assert run_cli(str(good), str(bad), "--no-color").returncode == 1
    assert run_cli(str(good), str(good), "--no-color").returncode == 0


def test_the_cli_says_what_to_do_when_asked_for_a_file_that_is_not_there():
    done = run_cli("/nonexistent/lieferung.padx", "--no-color")

    assert done.returncode == 2
    assert "Keine solche Datei" in done.stderr


def test_the_cli_prints_usage_rather_than_a_traceback_with_no_arguments():
    done = run_cli()

    assert done.returncode == 2
    assert "usage" in done.stdout.lower()
    assert "Traceback" not in done.stderr


def test_validate_file_refuses_a_path_that_is_not_there():
    with pytest.raises(PadnextError, match="no such PADnext file"):
        validate_file("/nonexistent/lieferung.padx")


def test_a_result_with_no_errors_has_no_primary():
    assert ValidationResult(status="valid").primary is None


def test_the_partner_api_carries_the_batched_list_too(client, payload):
    """A partner integrating against `/audit/single` hits three export mistakes on their first real
    file. One code per round trip is three deploys, so that path batches as well — and its
    documented codes (`docs/api/PARTNER_API.md`) are the ones this asserts have not moved."""
    broken = undeclare(payload.replace(b'posanzahl="9"', b'posanzahl="viele"'))
    # Minted through the real endpoint, as `tests/test_partner_api.py` does, so the token is one
    # the code a customer's key comes from actually produced.
    minted = client.post("/api/v1/settings/api-keys", json={"name": "Validation-Test"})
    assert minted.status_code == 201, minted.text
    token = minted.json()["token"]

    response = client.post(
        "/api/v1/audit/single",
        content=broken,
        headers={
            "X-API-Key": token,
            "Content-Type": "application/xml",
            "x-padnext-filename": "drei.xml",
        },
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error_code"] == "PADNEXT_SCHEMA_VIOLATION"
    assert body["details"]["violations"]
    assert body["details"]["error_count"] >= 2
    assert "echtdaten_undeclared" in [e["code"] for e in body["details"]["errors"]]


def test_the_cli_keeps_the_engines_operator_log_out_of_the_report(tmp_path, payload):
    """`app.padnext.reader` writes one structured line per schema violation — for a running
    service, where it is the only durable record of a non-conforming delivery let through under
    `warn`. Nobody is watching a log stream in a terminal, and the same violation arriving twice,
    once unformatted and interleaved with the header, makes the report look broken."""
    path = tmp_path / "schema_padx.xml"
    path.write_bytes(payload.replace(b'posanzahl="9"', b'posanzahl="viele"'))

    done = run_cli(str(path), "--no-color", "--quiet")

    assert "PADnext framing violated" not in done.stdout + done.stderr
    assert "[xsd_violation]" in done.stdout, "the violation itself is still reported, once"

    with_debug = run_cli(str(path), "--no-color", "--quiet", "--debug")
    assert "PADnext framing violated" in with_debug.stderr, "--debug puts it back"


def test_the_cli_quiet_prints_the_message_without_the_essay(tmp_path, payload):
    path = tmp_path / "ohne_padx.xml"
    path.write_bytes(undeclare(payload))

    quiet = run_cli(str(path), "--no-color", "--quiet")
    loud = run_cli(str(path), "--no-color")

    assert "[echtdaten_undeclared]" in quiet.stdout, "the problem is still named"
    assert "Warum:" not in quiet.stdout
    assert "Warum:" in loud.stdout
    # The copyable command survives --quiet: it is the shortest possible fix, not commentary.
    assert "anonymize_padnext.py" in quiet.stdout


# ==========================================================================================
# the container is unpacked twice, and must not be reported twice
# ==========================================================================================


def with_extra_member(order: bytes, payload: bytes, extra: bytes = b"Liesmich") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(ORDER_NAME, order)
        if payload:
            archive.writestr(PAYLOAD_NAME, payload)
        archive.writestr("liesmich.txt", extra)
    return buf.getvalue()


def test_a_container_finding_is_reported_once_not_twice(payload, order):
    """`validate_bytes` unpacks the container to build the preview, and `read_delivery` unpacks it
    again to read it. Both produce the same findings, so mapping both would tell a user there are
    two ignored members where there is one — under the same code, at the same time."""
    result = validate_bytes(with_extra_member(order, payload), source_name=CONTAINER_NAME)

    assert codes(result.warnings).count("padnext_container_member_ignored") == 1


def test_an_encryption_notice_is_reported_once(payload, order):
    encrypted = order.replace(b'verfahren="0"', b'verfahren="1"')

    result = validate_bytes(with_extra_member(encrypted, payload), source_name=CONTAINER_NAME)

    assert codes(result.warnings).count("padnext_encrypted_payload") == 1


def test_a_container_finding_survives_a_reading_that_failed(order):
    """The other side of the deduplication. When `read_delivery` raises, its findings go with it —
    so the container-level ones collected before it are all that is left, and dropping them would
    lose the only note about the file's own structure on exactly the upload that needs it."""
    empty_payload = (
        b'<rechnungen anzahl="0" echtdaten="false" xmlns="http://padinfo.de/ns/pad">'
        b'<nachrichtentyp version="02.12">ADL</nachrichtentyp></rechnungen>'
    )

    result = validate_bytes(with_extra_member(order, empty_payload), source_name=CONTAINER_NAME)

    assert codes(result.errors) == ["no_invoices"]
    assert codes(result.warnings) == ["padnext_container_member_ignored"]


# ==========================================================================================
# the reader's blanket refusals
# ==========================================================================================
#
# `reader.PadnextError` is one type covering six different problems, so this module classifies
# them by a fragment of the message each raises. That is not a nice way to catch an exception, and
# the tests below are what make it acceptable: each triggers a refusal *through the reader* and
# asserts the code it lands on, so rewording one of those messages fails here rather than quietly
# degrading a specific error into the generic one.


def test_every_reader_refusal_is_classified(payload, order):
    """Driven through `read_delivery` itself rather than against hand-written strings, so the
    fragment being matched is the one the reader really emits."""
    over_limit = b"<rechnungen>" + b"x" * (MAX_XML_BYTES + 1)
    many_members = io.BytesIO()
    with zipfile.ZipFile(many_members, "w") as archive:
        for n in range(MAX_ZIP_MEMBERS + 2):
            archive.writestr(f"m{n}.xml", b"<x/>")

    cases = {
        "xml_too_large": over_limit,
        "container_too_large": many_members.getvalue(),
        "container_unreadable": b"PK\x03\x04" + b"\x00" * 32,
        "xml_doctype_refused": b'<!DOCTYPE r [<!ENTITY a "aa">]><rechnungen/>',
        "not_xml": b"%PDF-1.7 not xml at all",
    }

    for expected, body in cases.items():
        # The reader refuses it…
        with pytest.raises(PadnextError):
            read_delivery(body, source_name="x")
        # …and the validator names which refusal it was.
        result = validate_bytes(body, source_name="x")
        assert codes(result.errors) == [expected], (expected, codes(result.errors))


def test_a_member_that_escapes_the_archive_root_is_named_as_such():
    """Never legitimate in a delivery, and worth its own message: the next action is "do not
    unpack this", not "re-export"."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("../../etc/passwd.xml", b"<x/>")

    result = validate_bytes(buf.getvalue(), source_name="boese.padx")

    assert codes(result.errors) == ["container_member_escapes"]


def test_a_big_container_holding_a_small_payload_is_not_refused(payload, order):
    """The regression this file exists to prevent, in its narrowest form.

    `MAX_XML_BYTES` bounds the *payload*, and applying it to the container instead would refuse a
    40 MB `.padx` whose extracted payload is 1 MB — a delivery `read_delivery` reads without
    complaint. The size check therefore stays inside `parse_xml`, where the reader put it.
    """
    padding = b"<!--" + b"x" * (MAX_XML_BYTES + 1024) + b"-->"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(ORDER_NAME, order)
        archive.writestr(PAYLOAD_NAME, payload)
        archive.writestr("beilage.bin", padding)
    big = buf.getvalue()

    # The reader accepts it, ignoring the extra member with a finding…
    delivery, _ = read_delivery(big, source_name=CONTAINER_NAME)
    assert delivery.invoices

    # …and so must the validator.
    result = validate_bytes(big, source_name=CONTAINER_NAME)
    assert result.ok, codes(result.errors)


def test_the_cli_does_not_show_an_empty_preview(tmp_path):
    """A block headed "was gelesen wurde" listing three zeros reads as a second failure rather
    than as reassurance — and its "beschädigtes Dokument" line is simply wrong about a file that
    was never XML. `ParsedPreview` in the web UI suppresses itself on the same condition."""
    path = tmp_path / "rechnung.pdf"
    path.write_bytes(b"%PDF-1.7 not xml at all")

    done = run_cli(str(path), "--no-color")

    assert done.returncode == 3
    assert "[not_xml]" in done.stdout
    assert "Gelesen" not in done.stdout
    assert "Notfall-Lesung" not in done.stdout


def test_the_cli_still_shows_the_preview_when_there_is_something_to_show(tmp_path, payload):
    """The other half — the suppression must not have removed the feature it guards."""
    path = tmp_path / "ohne_padx.xml"
    path.write_bytes(undeclare(payload))

    done = run_cli(str(path), "--no-color", "--quiet")

    assert done.returncode == 1
    assert "Gelesen (auch bei Fehlern)" in done.stdout
    assert "GOÄ/GOZ-Positionen:    9" in done.stdout


# ==========================================================================================
# the collapsed summary
# ==========================================================================================


def test_every_issue_carries_a_one_line_summary(payload):
    """The collapsed row renders `summary_de`, not `message_de`. An empty one is a row with a
    badge and no sentence, so every issue must have one — including those lifted from the
    reader's findings, which have only a long form and get theirs derived."""
    result = validate_bytes(
        undeclare(payload.replace(b'posanzahl="9"', b'posanzahl="viele"')),
        source_name="drei_padx.xml",
    )

    for issue in result.errors + result.warnings:
        assert issue.summary_de.strip(), issue.code
        assert len(issue.summary_de) <= MAX_SUMMARY_CHARS, (issue.code, issue.summary_de)
        assert "\n" not in issue.summary_de, issue.code


def test_the_summary_does_not_repeat_the_location(payload):
    """The line number is rendered beside the summary as its own chip, so spending the line's
    width saying it twice is what makes a row wrap to three lines at 390 px."""
    result = validate_bytes(undeclare(payload), source_name=PAYLOAD_NAME)

    issue = next(e for e in result.errors if e.field == "echtdaten")
    assert issue.summary_de == "echtdaten fehlt in den Nutzdaten."
    assert "Zeile" not in issue.summary_de
    assert issue.location.startswith("Zeile "), "and it is still available, separately"


def test_the_summary_is_shorter_than_the_message_it_summarises(payload):
    """Otherwise the disclosure buys the reader nothing and the collapsed state is a lie."""
    result = validate_bytes(undeclare(payload), source_name=PAYLOAD_NAME)

    issue = next(e for e in result.errors if e.field == "echtdaten")
    assert len(issue.summary_de) < len(issue.message_de)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Kurz und gut.", "Kurz und gut."),
        ("Erster Satz. Zweiter Satz.", "Erster Satz."),
        ("", ""),
        ("  doppelte   Leerzeichen  ", "doppelte Leerzeichen"),
    ],
)
def test_one_line_cuts_at_a_sentence_when_it_can(text, expected):
    assert one_line(text) == expected


def test_one_line_never_cuts_mid_word():
    """A summary reading "Feld 'posanzahl' enthält keine lesb…" costs the reader the one piece of
    information the line had."""
    long = "Wort " * 60

    cut = one_line(long)

    assert len(cut) <= MAX_SUMMARY_CHARS + 2
    assert cut.endswith(" …")
    assert "Wor …" not in cut, "cut at a word boundary, not mid-word"


def test_the_summary_reaches_the_wire_model(payload):
    result = validate_bytes(undeclare(payload), source_name=PAYLOAD_NAME)

    report = result.to_report()

    assert report.errors[0].summary_de == result.errors[0].summary_de
    assert report.errors[0].summary_en
