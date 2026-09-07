"""The unit of `<punktwert>`, and the false positive that not converting it produced.

**The finding.** PADnext writes `<punktwert>` in **euros**; § 5 Abs. 1 Satz 3 GOÄ states the legal
Punktwert in **cents**. `0.0582873 €` and `5.82873 ct` are the same value and are not the same
number, and the check compared them without converting — so every position of every conforming
delivery raised `padnext_punktwert_mismatch`, saying a value deviated from a value it was exactly
equal to. Five identical warnings on a five-position invoice; on an otherwise clean one they were
the *only* findings, so the whole report was noise.

**The evidence, and why it is a test rather than a comment.** The XSD cannot settle the question —
every numeric leaf in it is `xs:string` (divergence 2 in the subset schema's header), so the format
declares no unit anywhere this repository can read. What does settle it is the document's own
arithmetic: `punktzahl × faktor × punktwert = gesamtbetrag` holds to the cent for a file written in
euros and is off by exactly 100 for one written in cents, and `gesamtbetrag` is unambiguously euros
because it is the figure a practice puts on an invoice.
`test_the_spec_unit_is_the_one_the_files_own_arithmetic_uses` asserts that identity against the
committed examples, so the determination is re-derived on every run instead of being believed.

Two things are being defended here:

    conversion  a conforming punktwert produces NO finding, in either spelling
    dedup       a wrong one produces ONE finding naming the affected positions, not N copies

The second is not cosmetic. `punktwert` is a property of the fee schedule, so an export writes the
same figure on every line and a wrong one is wrong on every line — forty-seven copies of one
sentence is not forty-seven problems, it is one problem rendered in a way that buries every other
finding on the report.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.etree import ElementTree

import pytest

from app.config import PADNEXT_EXAMPLES_DIR, REPO_ROOT
from app.padnext import audit_delivery, read_delivery
from app.padnext.audit import (
    CENT_PER_EURO,
    VERIFIED_DEFECT_FINDINGS,
    describe_punktwert_mismatch,
    punktwert_in_cent,
    punktwert_matches,
)

PAYLOAD_NAME = "00004711_20260726_ADL_000001_padx.xml"

#: The legal figure, in cents, as the catalog carries it. Hard-coded rather than read from the
#: catalog so that a catalog regression cannot make these assertions vacuously true.
LEGAL_CENT = Decimal("5.82873")
LEGAL_EURO = Decimal("0.0582873")


@pytest.fixture(scope="module")
def payload() -> bytes:
    return (PADNEXT_EXAMPLES_DIR / PAYLOAD_NAME).read_bytes()


def audit(pipeline, data: bytes, name: str = PAYLOAD_NAME):
    delivery, findings = read_delivery(data, source_name=name)
    return audit_delivery(
        delivery,
        catalog=pipeline.catalog,
        rules=pipeline.rules,
        souffle_run=pipeline.souffle.run,
        read_findings=findings,
        settings=pipeline.settings,
    )


def punktwert_findings(report):
    return [f for f in report.findings if f.type == "padnext_punktwert_mismatch"]


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# ==========================================================================================
# the determination
# ==========================================================================================


def test_the_catalog_states_the_legal_figure_in_cents(catalog):
    """The other half of the mismatch, pinned: the catalog is right, and it is right in cents.

    The bug was never that this number was wrong. It is the figure § 5 Abs. 1 Satz 3 GOÄ quotes,
    carried with that citation, and `tests/test_import_goae.py` already guards it against the law.
    Restating the unit here is what makes the conversion below a conversion rather than a fudge.
    """
    assert catalog.punktwert_cent == LEGAL_CENT
    assert LEGAL_EURO * CENT_PER_EURO == LEGAL_CENT, "the two spellings must denote one value"


def test_the_spec_unit_is_the_one_the_files_own_arithmetic_uses():
    """**The evidence test.** For every position that carries all four fields, in every committed
    example, `punktzahl × faktor × punktwert` must equal `gesamtbetrag` when punktwert is read as
    EUROS — and must not when it is read as cents.

    This is what makes "PADnext writes euros" a finding rather than an opinion. The subset XSD
    types every numeric leaf as `xs:string` and declares no unit, so the format itself is silent;
    the document's own multiplication is not. Driven over the committed examples so that an
    example edited into the wrong unit fails here instead of shipping.
    """
    examples = sorted(PADNEXT_EXAMPLES_DIR.glob("*_padx.xml"))
    assert examples, "no example payloads found — this test would prove nothing"

    checked = 0
    for path in examples:
        root = ElementTree.fromstring(path.read_bytes())
        for position in root.iter():
            if local(position.tag) != "goziffer":
                continue

            def value(name: str, element=position) -> Decimal | None:
                for child in element:
                    if local(child.tag) == name and (child.text or "").strip():
                        return Decimal(child.text.strip())
                return None

            punktwert = value("punktwert")
            faktor, gesamt = value("faktor"), value("gesamtbetrag")
            if punktwert is None or faktor is None or gesamt is None:
                continue

            # The identity is asserted TO THE CENT, which is the strongest form it can take:
            # `gesamtbetrag` is a two-decimal amount, so the exact product is rounded before it
            # reaches the file and the implied point count carries that rounding (26.81 implies
            # 199.98 points, not 200). Recomputing forward from the whole point count and
            # comparing rounded amounts is the same claim without the artefact.
            #
            # The claimed punktzahl may itself be a deliberate fixture error — position 6 of the
            # bundled example claims 180 where the catalog says 200 — so the point count is taken
            # from the amount rather than from the element. The question here is the *unit*.
            per_point = punktwert * faktor
            punkte = Decimal(round(gesamt / per_point))
            as_euro = (punkte * per_point).quantize(Decimal("0.01"), ROUND_HALF_UP)
            as_cent = ((punkte * per_point) / CENT_PER_EURO).quantize(
                Decimal("0.01"), ROUND_HALF_UP
            )

            assert as_euro == gesamt, (
                f"{path.name} position {position.get('positionsnr')}: reading punktwert as euros, "
                f"{punkte} × {faktor} × {punktwert} = {as_euro} but gesamtbetrag says {gesamt} — "
                f"so euros is not the unit this file was written in"
            )
            assert as_cent != gesamt, (
                f"{path.name} position {position.get('positionsnr')}: the cent reading also "
                f"reproduces {gesamt}, so this position cannot settle the unit"
            )
            checked += 1

    assert checked, "no position carried punktwert, faktor and gesamtbetrag together"


def test_the_bundled_example_writes_the_spec_unit(payload):
    """The fixture used to write `5.82873`, which gave its position 6 a second, undocumented
    error — 180 × 2.3 × 5.82873 is 2413.09, not the 26.81 the same element claims. It is the
    reason the false positive was never noticed: on that file, and only that file, the unconverted
    comparison happened to succeed."""
    assert b"<punktwert>0.0582873</punktwert>" in payload
    assert b"<punktwert>5.82873</punktwert>" not in payload


# ==========================================================================================
# the conversion
# ==========================================================================================


def test_a_conforming_punktwert_converts_to_the_legal_figure_exactly():
    assert punktwert_in_cent(LEGAL_EURO) == LEGAL_CENT
    assert punktwert_matches(LEGAL_EURO, LEGAL_CENT)


@pytest.mark.parametrize("spelling", ["0.0582873", "0.05828730", "0.058287300000"])
def test_trailing_zeros_do_not_make_a_mismatch(spelling):
    """`Decimal` equality is numeric, not textual, and an exporter padding the field must not be
    told its fee schedule is wrong."""
    assert punktwert_matches(Decimal(spelling), LEGAL_CENT)


def test_the_cent_spelling_is_accepted_too():
    """A documented tolerance, not an oversight.

    `5.82873` denotes the identical legal value, it is the figure the GOÄ text quotes, and some
    exporters write it — this repository's own fixture did. Refusing to recognise it would
    reinstate the false positive for those senders, and it costs nothing real: this is a control
    field, the money is always recomputed from the versioned catalog, and a genuinely wrong amount
    is caught by `padnext_amount_mismatch` against that recomputation.
    """
    assert punktwert_matches(LEGAL_CENT, LEGAL_CENT)


@pytest.mark.parametrize("wrong", ["0.06", "0.05", "6", "0.582873", "0.00582873"])
def test_a_genuinely_wrong_punktwert_still_does_not_match(wrong):
    """The check must still be able to fail, or the fix removed the feature instead of the bug.

    `0.582873` and `0.00582873` are in here on purpose: they are the value off by one decimal
    place in each direction, which is the mistake a hand-edited export profile actually makes, and
    a tolerance built as a range rather than as two exact readings would swallow both.
    """
    assert not punktwert_matches(Decimal(wrong), LEGAL_CENT)


@pytest.mark.parametrize(
    "raw,exact",
    [("0.058", "5.8"), ("0.29", "29"), ("0.0007", "0.07"), ("0.0035", "0.35")],
)
def test_the_conversion_is_exact_where_binary_floating_point_is_not(raw, exact):
    """Scaling a decimal fraction by 100 is not reliably exact in floats, so a float
    implementation reinstates this bug for some punktwert values and not others.

    Asserted over values that actually break rather than over today's Punktwert, which happens to
    survive the float round trip — that is luck, and the Punktwert is a number the legislator can
    change. Each case asserts both halves: `Decimal` lands on the exact figure, and `float` does
    not, so the test would fail if someone "simplified" the helper.
    """
    assert punktwert_in_cent(Decimal(raw)) == Decimal(exact)
    assert float(raw) * 100 != float(exact), (
        f"{raw} no longer breaks in floats, so this case proves nothing — pick another"
    )


def test_the_conforming_delivery_reports_no_punktwert_finding(pipeline, payload):
    """The regression this whole change exists to prevent, end to end."""
    report = audit(pipeline, payload)

    assert punktwert_findings(report) == [], (
        "a conforming delivery must raise no punktwert finding: "
        f"{[f.message for f in punktwert_findings(report)]}"
    )


def test_the_cent_spelling_delivery_reports_no_finding_either(pipeline, payload):
    edited = payload.replace(b"<punktwert>0.0582873</punktwert>", b"<punktwert>5.82873</punktwert>")

    assert punktwert_findings(audit(pipeline, edited)) == []


# ==========================================================================================
# the deduplication
# ==========================================================================================


def many_positions(punktwerte: list[str]) -> bytes:
    """A delivery whose positions carry the given punktwert values, one each."""
    positions = "".join(
        f'<goziffer positionsnr="{n}" go="GOÄ" ziffer="1">'
        f"<datum>2026-07-20</datum><anzahl>1</anzahl><faktor>2.3</faktor>"
        f"<punktwert>{value}</punktwert><punktzahl>80</punktzahl>"
        f"<gesamtbetrag>10.72</gesamtbetrag></goziffer>"
        for n, value in enumerate(punktwerte, start=1)
    )
    return (
        '<rechnungen anzahl="1" echtdaten="false" xmlns="http://padinfo.de/ns/pad">'
        '<nachrichtentyp version="02.12">ADL</nachrichtentyp>'
        '<rechnung id="PW"><abrechnungsfall><behandlungsart>0</behandlungsart>'
        f'<positionen posanzahl="{len(punktwerte)}">{positions}</positionen>'
        "</abrechnungsfall></rechnung></rechnungen>"
    ).encode("utf-8")


def test_one_wrong_value_on_many_positions_is_one_finding(pipeline):
    report = audit(pipeline, many_positions(["0.06"] * 12), name="flut_padx.xml")

    found = punktwert_findings(report)
    assert len(found) == 1, f"expected one collapsed finding, got {len(found)}"
    assert "alle 12 Positionen" in found[0].message


def test_the_collapsed_finding_names_the_positions_when_only_some_are_affected(pipeline):
    report = audit(
        pipeline, many_positions(["0.06", "0.06", "0.0582873", "0.06"]), name="teil_padx.xml"
    )

    found = punktwert_findings(report)
    assert len(found) == 1
    assert "3 Position(en)" in found[0].message
    assert "1, 2, 4" in found[0].message, found[0].message


def test_two_distinct_wrong_values_stay_two_findings(pipeline):
    """Collapsing is per value, not per delivery. Two different wrong punktwerte in one export are
    two different facts about it, and merging them would hide one of the two numbers a sender has
    to go and change."""
    report = audit(pipeline, many_positions(["0.06", "0.06", "0.07"]), name="zwei_padx.xml")

    found = punktwert_findings(report)
    assert len(found) == 2
    assert {f.claimed for f in found} == {"0.06", "0.07"}


def test_a_long_position_list_is_truncated_but_counted_honestly(pipeline):
    report = audit(pipeline, many_positions(["0.06"] * 25 + ["0.0582873"]), name="lang_padx.xml")

    found = punktwert_findings(report)
    assert len(found) == 1
    assert "25 Position(en)" in found[0].message
    assert found[0].message.rstrip().endswith("…"), "truncation must be visible"


def test_the_collapsed_finding_claims_no_single_position(pipeline):
    """`positionsnr` names ONE position and this finding is about several. Naming the first would
    make the rest invisible to a reader filtering by position, which is worse than a finding that
    honestly belongs to the invoice."""
    report = audit(pipeline, many_positions(["0.06"] * 4), name="viele_padx.xml")

    assert punktwert_findings(report)[0].positionsnr is None


def test_punktzahl_mismatches_are_not_collapsed(pipeline, payload):
    """The deliberate asymmetry. `punktzahl` is per-Ziffer: each mismatch is a different claim
    about a different service, so those really are N findings and collapsing them would merge
    unrelated facts."""
    report = audit(pipeline, payload)

    punktzahl = [f for f in report.findings if f.type == "padnext_punktzahl_mismatch"]
    assert punktzahl, "the bundled example claims one wrong punktzahl on purpose"
    assert all(f.positionsnr for f in punktzahl), "each names its own position"


# ==========================================================================================
# the message
# ==========================================================================================


def test_the_message_states_the_expected_unit_and_both_figures():
    message = describe_punktwert_mismatch(Decimal("0.06"), LEGAL_CENT)

    assert "0.06" in message, "the value the file wrote"
    assert "0.0582873" in message, "the expected value, in the unit the file should use"
    assert "EURO" in message, "and which unit that is"
    assert "5.82873" in message and "Cent" in message, "with the legal figure beside it"
    assert "§ 5 Abs. 1 Satz 3 GOÄ" in message


def test_the_message_never_shows_an_exponent():
    """`Decimal("0.0582873") * 100` normalises to `5.828730`, and `str()` on some Decimals yields
    `5.82873E+1`. A practice must not be shown scientific notation for a fee."""
    for value in ("0.06", "6", "0.0000582873", "60000"):
        message = describe_punktwert_mismatch(Decimal(value), LEGAL_CENT)
        assert "E+" not in message and "E-" not in message, message


def test_the_finding_carries_both_sides_in_the_same_unit(pipeline):
    """`claimed` and `recomputed` are rendered side by side on the report and in the PDF. Handing
    them over in different units is how the original message became unreadable, so the pair is
    euros and euros."""
    report = audit(pipeline, many_positions(["0.06"] * 3), name="paar_padx.xml")
    finding = punktwert_findings(report)[0]

    assert finding.claimed == "0.06"
    assert finding.recomputed == "0.0582873"
    assert Decimal(finding.recomputed) * CENT_PER_EURO == LEGAL_CENT


def test_a_punktwert_mismatch_is_not_a_verified_defect():
    """It is metadata about the fee schedule, not a euro anyone may claim back. Putting it in
    `VERIFIED_DEFECT_FINDINGS` would move real money into `confirmed_wrong` over a control field
    whose value never entered a total."""
    assert "padnext_punktwert_mismatch" not in VERIFIED_DEFECT_FINDINGS


def test_a_wrong_punktwert_does_not_change_a_single_euro(pipeline):
    """The reason the tolerance above is safe: the money is recomputed from the catalog, never
    read from this field. Same delivery, absurd punktwert, identical totals."""
    clean = audit(pipeline, many_positions(["0.0582873"] * 3), name="a_padx.xml")
    wrong = audit(pipeline, many_positions(["99.99"] * 3), name="b_padx.xml")

    assert wrong.claimed_total_eur == clean.claimed_total_eur
    assert wrong.confirmed_fine_eur == clean.confirmed_fine_eur
    assert wrong.confirmed_wrong_eur == clean.confirmed_wrong_eur
    assert wrong.unconfirmed_eur == clean.unconfirmed_eur
