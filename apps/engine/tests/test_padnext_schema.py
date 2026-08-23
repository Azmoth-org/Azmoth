"""PADnext framing validation: what is refused before a position is ever read, and what is not.

The design line this file defends is one sentence: **framing is fatal, positions are advisory.**

    framing     Is this an ADL payload at all? Wrong root, wrong namespace, no message type, a
                counter that is not a number, a treatment code outside the legal set, an
                Abrechnungsfall with no positions. The delivery is refused — `PadnextSchemaError`,
                HTTP 422 — because it cannot be audited, or cannot be priced.

    positions   A `goziffer` with no `@ziffer`, a `faktor` reading "zwei", an `auslagen` line this
                engine does not model. Found, reported per position, priced as far as possible.

The second half is the product, and it is why this file spends as much space asserting what is
still *accepted* as it does on the five rejections. An audit engine that refused every imperfect
invoice would refuse exactly the invoices worth auditing. `tests/test_padnext.py` owns the
tolerance assertions themselves; the ones here are the guard that validation did not quietly
promote a finding into a refusal.

The schema is `data/schemas/padnext/padx_adl_v2.12.subset.xsd` — ours, not the official PADneXt
XSD, which is not redistributable here. Its header comment documents every deliberate divergence.

Fixtures live in `tests/fixtures/invalid_padnext/`, deliberately not in `logic/tests/cases/`: that
directory is what CI's logic guard accepts as golden-snapshot evidence, and invalid XML sitting
there would let a catalog change be waved through by adding a broken file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import PadnextSchemaPolicy, Settings
from app.padnext import (
    PadnextError,
    PadnextSchemaError,
    read_delivery,
    read_file,
    validate_payload,
)
from app.padnext.schema import (
    MAX_REPORTED_VIOLATIONS,
    RULE_MISSING_POSITIONEN,
    SchemaUnavailable,
    load_schema,
)

FIXTURES = Path(__file__).parent / "fixtures" / "invalid_padnext"

#: Each fixture, the libxml2 (or our own) rule that must catch it, and a fragment of the source
#: line the violation must point at. The line is asserted by *finding* that fragment in the file
#: rather than by hard-coding a number, so editing a comment in a fixture cannot make a passing
#: test lie about where the error is.
CASES = {
    "missing_nachrichtentyp.xml": ("SCHEMAV_ELEMENT_CONTENT", "<rechnungsersteller>"),
    "missing_positionen.xml": (RULE_MISSING_POSITIONEN, "<abrechnungsfall>"),
    "wrong_type_posanzahl.xml": ("SCHEMAV_CVC_DATATYPE_VALID_1_2_1", 'posanzahl="viele"'),
    "invalid_enum_behandlungsart.xml": ("SCHEMAV_CVC_ENUMERATION_VALID", "<behandlungsart>9<"),
    "wrong_namespace.xml": ("SCHEMAV_CVC_ELT_1", "http://example.invalid/ns/pad"),
}


def fixture(name: str) -> bytes:
    path = FIXTURES / name
    assert path.is_file(), f"missing fixture {path}"
    return path.read_bytes()


def expected_line(name: str, needle: str) -> int:
    """The 1-based line of `needle` in the fixture markup — what the violation must point at.

    Lines inside the fixture's own `<!-- ... -->` header are skipped, because that header quotes
    the very violation it documents. Without the skip this helper finds the prose, the assertion
    compares a violation against a comment, and the test passes while proving nothing.
    """
    in_comment = False
    for number, text in enumerate(fixture(name).decode("utf-8").splitlines(), start=1):
        if "<!--" in text:
            in_comment = True
        if in_comment:
            if "-->" in text:
                in_comment = False
            continue
        if needle in text:
            return number
    raise AssertionError(f"{needle!r} is not in the markup of {name}")


# ==========================================================================================
# the five fixtures are refused, and say where
# ==========================================================================================


@pytest.mark.parametrize("name", sorted(CASES))
def test_every_invalid_fixture_is_refused(name):
    with pytest.raises(PadnextSchemaError):
        read_delivery(fixture(name), schema_policy=PadnextSchemaPolicy.STRICT)


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_refusal_is_still_a_padnext_error(name):
    """What keeps the API contract: `api/padnext.py` catches `PadnextError` and answers 422, so a
    schema refusal needs no new handler and no new status code."""
    with pytest.raises(PadnextError):
        read_delivery(fixture(name), schema_policy=PadnextSchemaPolicy.STRICT)


@pytest.mark.parametrize("name,rule,needle", [(n, r, l) for n, (r, l) in sorted(CASES.items())])
def test_a_violation_names_its_rule_and_its_line(name, rule, needle):
    """A structured violation, not a string: rule, line, column, readable path.

    The line is the whole point. "This delivery is invalid" sends someone grepping a 4000-line
    export; "line 20 at rechnungen/rechnung/abrechnungsfall/positionen" does not.
    """
    with pytest.raises(PadnextSchemaError) as exc:
        read_delivery(fixture(name), schema_policy=PadnextSchemaPolicy.STRICT)

    violations = exc.value.violations
    assert violations, "a refusal with no violations would be unexplainable"
    match = [v for v in violations if v.rule == rule]
    assert match, f"expected rule {rule}, got {[v.rule for v in violations]}"

    violation = match[0]
    assert violation.line == expected_line(name, needle), (
        f"{name}: violation points at line {violation.line}, "
        f"but {needle!r} is on line {expected_line(name, needle)}"
    )
    assert violation.message
    assert str(violation.line) in violation.location


def test_the_readable_path_is_element_names_not_libxml2_positions():
    """libxml2 reports `/*/*[2]/*/*[1]`. A path a human can read is resolved from it."""
    with pytest.raises(PadnextSchemaError) as exc:
        read_delivery(
            fixture("wrong_type_posanzahl.xml"), schema_policy=PadnextSchemaPolicy.STRICT
        )

    paths = [v.path for v in exc.value.violations]
    assert "rechnungen/rechnung/abrechnungsfall/positionen" in paths
    assert not any("*" in p or "{" in p for p in paths), f"unresolved paths: {paths}"


def test_the_error_message_carries_every_violation_not_just_the_first():
    """A file with two independent problems must report both, or the second one is discovered only
    after the first is fixed and the file is re-uploaded."""
    two_problems = fixture("wrong_type_posanzahl.xml").replace(
        b"<behandlungsart>0</behandlungsart>", b"<behandlungsart>9</behandlungsart>"
    )
    with pytest.raises(PadnextSchemaError) as exc:
        read_delivery(two_problems, schema_policy=PadnextSchemaPolicy.STRICT)

    rules = {v.rule for v in exc.value.violations}
    assert {"SCHEMAV_CVC_ENUMERATION_VALID", "SCHEMAV_CVC_DATATYPE_VALID_1_2_1"} <= rules
    assert "2 violation(s)" in str(exc.value)


def test_a_flood_of_violations_is_truncated_but_counted_honestly():
    """Truncating the message is fine; hiding how much was truncated is not."""
    positions = b"".join(
        b'<goziffer positionsnr="%d"><behandlungsart>9</behandlungsart></goziffer>' % i
        for i in range(MAX_REPORTED_VIOLATIONS + 5)
    )
    flooded = fixture("wrong_type_posanzahl.xml").replace(
        b'<positionen posanzahl="viele">', b'<positionen posanzahl="1">' + positions
    )
    with pytest.raises(PadnextSchemaError) as exc:
        read_delivery(flooded, schema_policy=PadnextSchemaPolicy.STRICT)

    assert len(exc.value.violations) > MAX_REPORTED_VIOLATIONS
    assert f"{len(exc.value.violations)} violation(s)" in str(exc.value)
    assert "further violation(s)" in str(exc.value)


# ==========================================================================================
# what must NOT be refused — the half of this feature that is a product decision
# ==========================================================================================


def test_the_bundled_example_validates():
    """The golden fixture ~60 other tests depend on. Its own header calls it "a hand-written subset
    ... not a schema-validated conforming document", so this is the assertion that the subset
    schema describes what the engine actually reads rather than an idealised document."""
    from app.config import PADNEXT_EXAMPLES_DIR

    payload = (PADNEXT_EXAMPLES_DIR / "00004711_20260726_ADL_000001_padx.xml").read_bytes()

    assert validate_payload(payload, policy=PadnextSchemaPolicy.STRICT) == []


PAYLOAD = """<?xml version="1.0" encoding="UTF-8"?>
<rechnungen anzahl="1" xmlns="http://padinfo.de/ns/pad">
  <nachrichtentyp version="02.12">ADL</nachrichtentyp>
  <rechnung id="x">
    <abrechnungsfall>
      {case}
      <positionen posanzahl="1">
        {position}
      </positionen>
    </abrechnungsfall>
  </rechnung>
</rechnungen>"""


def payload(*, case: str = "<behandlungsart>0</behandlungsart>", position: str = "") -> bytes:
    return PAYLOAD.format(case=case, position=position).encode("utf-8")


@pytest.mark.parametrize(
    "label,position",
    [
        ("no @ziffer", '<goziffer positionsnr="1"><anzahl>1</anzahl></goziffer>'),
        (
            "unreadable faktor",
            '<goziffer positionsnr="1" ziffer="1"><faktor>zwei</faktor></goziffer>',
        ),
        ("unmodelled type", '<auslagen positionsnr="1"><betrag>3.00</betrag></auslagen>'),
        (
            "unknown child element",
            '<goziffer positionsnr="1" ziffer="1"><hinweis>frei</hinweis></goziffer>',
        ),
        (
            "unknown attribute",
            '<goziffer positionsnr="1" ziffer="1" sonderfeld="x"><anzahl>1</anzahl></goziffer>',
        ),
    ],
)
def test_a_position_level_problem_is_never_a_refusal(label, position):
    """Each of these is a finding in `tests/test_padnext.py`. If the schema ever starts refusing
    one, the engine has stopped being able to audit the invoices that need auditing."""
    assert validate_payload(payload(position=position), policy=PadnextSchemaPolicy.STRICT) == []


@pytest.mark.parametrize("art", ["0", "1", "2", "3", "4", "5"])
def test_every_behandlungsart_the_specification_defines_is_accepted(art):
    """3, 4 and 5 do not map onto a § 6a reduction and are reported as unmapped — by
    `derive_setting`, after the delivery is read. They are legal values, so they are not framing
    violations, and only 6 and up are."""
    assert validate_payload(
        payload(case=f"<behandlungsart>{art}</behandlungsart>"),
        policy=PadnextSchemaPolicy.STRICT,
    ) == []


def test_an_abrechnungsfall_may_carry_elements_this_engine_never_parses():
    """A real delivery carries patient identity and diagnoses. The engine does not read them (see
    `test_no_parsed_model_can_hold_patient_identity`), and a schema that refused them would refuse
    every real file — which is why `abrechnungsfall` has open content."""
    assert validate_payload(
        payload(
            case="<patient><name>Muster</name></patient><behandlungsart>0</behandlungsart>",
            position='<goziffer positionsnr="1" ziffer="1"><anzahl>1</anzahl></goziffer>',
        ),
        policy=PadnextSchemaPolicy.STRICT,
    ) == []


def test_a_missing_behandlungsart_is_not_a_framing_violation():
    """Absence stays what it is today — `derive_setting` reports it. Only a value outside the
    defined set is fatal, because that is the case where a fallback would price the invoice on a
    basis nobody stated."""
    assert validate_payload(payload(case=""), policy=PadnextSchemaPolicy.STRICT) == []


# ==========================================================================================
# the existing rejections keep their own messages
# ==========================================================================================


def test_the_gate_runs_after_the_root_checks_so_their_messages_survive():
    """`<Quittung>` in the right namespace is a wrong-root error, not a schema violation. The
    reader's message names what to send instead; a schema violation cannot."""
    with pytest.raises(PadnextError, match="unsupported PADnext payload root"):
        read_delivery(b'<?xml version="1.0"?><Quittung xmlns="http://padinfo.de/ns/pad"/>')


def test_a_doctype_is_still_refused_before_the_schema_is_consulted():
    with pytest.raises(PadnextError, match="DOCTYPE"):
        read_delivery(b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aa">]><rechnungen/>')


def test_a_malformed_document_is_a_parse_error_not_a_schema_error():
    """Two parsers see these bytes — the reader's `xml.etree` and the validator's lxml. One
    problem must not produce two different errors, so the validator stays silent about
    well-formedness and lets `parse_xml` own it."""
    with pytest.raises(PadnextError, match="not well formed"):
        read_delivery(b'<rechnungen xmlns="http://padinfo.de/ns/pad"><rechnung></rechnungen>')

    assert validate_payload(b"<rechnungen><unclosed>") == []


# ==========================================================================================
# policy
# ==========================================================================================


@pytest.mark.parametrize("name", sorted(CASES))
def test_warn_turns_a_refusal_into_a_finding(name):
    """The escape hatch: a real export that is 99 % conforming still gets audited, and every
    violation is on the report instead of in an exception."""
    delivery, findings = read_delivery(fixture(name), schema_policy=PadnextSchemaPolicy.WARN)

    schema_findings = [f for f in findings if f.type == "padnext_schema_violation"]
    assert schema_findings, f"{name} produced no schema finding under warn"
    assert all(f.severity == "error" for f in schema_findings)
    assert any("Zeile" in f.message or "line" in f.message for f in schema_findings)
    assert delivery is not None


@pytest.mark.parametrize("name", sorted(CASES))
def test_off_does_not_consult_the_schema_at_all(name):
    delivery, findings = read_delivery(fixture(name), schema_policy=PadnextSchemaPolicy.OFF)

    assert delivery is not None
    assert [f for f in findings if f.type == "padnext_schema_violation"] == []


def test_strict_is_the_default_and_the_setting_is_the_only_way_to_change_it():
    assert Settings.model_fields["padnext_schema_policy"].default == PadnextSchemaPolicy.STRICT
    assert str(PadnextSchemaPolicy.STRICT) == "strict"
    assert {str(p) for p in PadnextSchemaPolicy} == {"strict", "warn", "off"}


def test_read_file_honours_the_policy_too():
    """The CLI path reads files, not bytes, and must not be quietly more permissive."""
    with pytest.raises(PadnextSchemaError):
        read_file(FIXTURES / "wrong_namespace.xml", schema_policy=PadnextSchemaPolicy.STRICT)


# ==========================================================================================
# the HTTP contract
# ==========================================================================================


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_endpoint_answers_422_and_says_where(client, name):
    """End to end, because "it subclasses PadnextError" is an implementation detail and "the API
    returns 422 with the line number in it" is the contract a PVS integrator sees.

    The location used to be asserted by looking for the substring `"line "` in a prose `detail`.
    It is now a number in a named field, because the structured error envelope carries every
    violation with its own line, column and element path — a strictly stronger assertion, and one
    an integrator can act on without parsing German. See `docs/errors.md`.
    """
    response = client.post(
        "/api/v1/padnext/audit",
        content=fixture(name),
        headers={"Content-Type": "application/xml", "x-padnext-filename": name},
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error_code"] == "PADNEXT_SCHEMA_VIOLATION"
    assert "does not conform" in body["message"]

    violations = body["details"]["violations"]
    assert violations, "a 422 with no violation listed says nothing"
    assert body["details"]["violation_count"] == len(violations)
    assert all(v["message"] for v in violations)
    assert any(v["line"] > 0 for v in violations), (
        f"a 422 without a location is not actionable: {violations}"
    )


def test_a_valid_delivery_still_audits_over_http(client):
    """The other half: the gate must not have changed anything about a conforming delivery."""
    from app.config import PADNEXT_EXAMPLES_DIR

    payload = (PADNEXT_EXAMPLES_DIR / "00004711_20260726_ADL_000001_padx.xml").read_bytes()
    response = client.post(
        "/api/v1/padnext/audit",
        content=payload,
        headers={"Content-Type": "application/xml"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["positions"], "the bundled example still audits, position by position"


# ==========================================================================================
# the schema itself
# ==========================================================================================


def test_the_shipped_schema_is_the_subset_and_it_compiles():
    """A schema that does not compile is a deployment fault, and it must not look like a bad
    delivery — hence `SchemaUnavailable` rather than a violation."""
    from app.config import PADNEXT_XSD_PATH

    assert PADNEXT_XSD_PATH.is_file()
    assert load_schema(PADNEXT_XSD_PATH) is not None


def test_the_schema_says_out_loud_that_it_is_not_the_official_one():
    """Provenance, the same rule the catalog follows: data that could be mistaken for an official
    artefact has to say what it is. Someone will eventually diff this against padinfo.de's XSD."""
    from app.config import PADNEXT_XSD_PATH

    text = PADNEXT_XSD_PATH.read_text(encoding="utf-8")

    assert "NOT the official XSD" in text
    assert "§ 5 UrhG" in text, "the reason the GOÄ may be committed and this may not"
    assert "DELIBERATE DIVERGENCES" in text


def test_the_licensed_official_schema_is_preferred_when_an_operator_has_one(tmp_path):
    """An operator who holds the official schema gets it used without a code change — and the
    directory is git-ignored, so it cannot be committed by accident."""
    settings = Settings(data_dir=tmp_path)
    subset = tmp_path / "schemas" / "padnext" / "padx_adl_v2.12.subset.xsd"
    licensed = tmp_path / "licensed" / "padnext" / "padx_adl_v2.12.xsd"

    assert settings.padnext_xsd_path == subset

    licensed.parent.mkdir(parents=True)
    licensed.write_text("<xs:schema/>", encoding="utf-8")
    assert settings.padnext_xsd_path == licensed


def test_a_missing_schema_is_a_deployment_fault_not_an_invalid_delivery(tmp_path):
    with pytest.raises(SchemaUnavailable):
        load_schema(tmp_path / "absent.xsd")


def test_the_fixture_directory_holds_exactly_the_documented_cases():
    """A fixture added without a case here would be dead weight; one removed would silently stop
    being tested."""
    on_disk = {p.name for p in FIXTURES.glob("*.xml")}

    assert on_disk == set(CASES), f"fixtures and CASES disagree: {on_disk ^ set(CASES)}"


@pytest.mark.parametrize("name", sorted(CASES))
def test_every_fixture_declares_itself_synthetic_and_carries_no_identity(name):
    """The project's ground rule, and it applies to invalid fixtures too."""
    text = fixture(name).decode("utf-8")

    assert "SYNTHETIC" in text
    assert "VIOLATION:" in text, "a fixture must say what it violates, or it is just a broken file"
    for forbidden in ("versicherter", "geburtsdatum", "strasse", "<patient>"):
        assert forbidden not in text.lower()
