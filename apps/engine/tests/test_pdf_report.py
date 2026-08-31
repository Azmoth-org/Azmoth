"""The Prüfbericht, checked as a document rather than as a byte string.

Every other test in this suite asks whether the engine reached the right verdict. These ask
whether the *deliverable* is sound — the file a Rechnungsprüfer prints, files, and forwards to a
payer. Three kinds of claim, and they need different machinery:

* **Geometry.** The content stream is parsed back and every drawn run of text is measured against
  the page box. That is the only way to catch a euro amount overprinting the column beside it or a
  line sliding under the footer, because nothing in a PDF *fails* when text runs off the page — it
  simply is not there when the paper comes out. `drawn_runs` is what makes this checkable at all.
* **Content.** The strings are extracted and asserted on, so the mandated disclaimer, the contact
  address and the three bucket labels cannot be quietly reworded.
* **Structure.** Cross-reference offsets, `/Info`, the page tree — the parts a reader rejects the
  whole file over.

The parser here is deliberately naive: it knows only the operators `app.services.pdf` emits, and it
would not survive a general PDF. That is the point — it is a check on *this* writer, and a change
to the writer that this parser cannot read is a change that should be looked at.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.schemas.batch import (
    BatchAggregateSummary,
    BatchAuditJob,
    BatchFileResult,
    BatchFileStatus,
    BatchJobStatus,
)
from app.schemas.padnext import (
    PadnextAuditedPosition,
    PadnextAuditReport,
    PadnextFinding,
)
from app.padnext.pilot_scope import TEMPORAL_SCOPE_WARNING
from app.services import pdf as pdf_module
from app.services.pdf import (
    BOTTOM,
    CONTENT_WIDTH,
    DISCLAIMER,
    MARGIN,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    Column,
    PdfCanvas,
    _euro,
    _escape,
    fit,
    render_batch_report,
    render_single_report,
    wrap,
)
from app.services.pdf_metrics import HELVETICA, HELVETICA_BOLD, text_width

# ==========================================================================================
# reading a document back
# ==========================================================================================

#: One `BT … Tj ET` run as `app.services.pdf` writes it. Anchored on that exact shape so a
#: refactor that starts emitting a different operator sequence fails loudly here rather than
#: silently reducing every geometry test below to "nothing was drawn, nothing overflowed".
_RUN = re.compile(
    rb"BT /(F\d) ([\d.]+) Tf 1 0 0 1 (-?[\d.]+) (-?[\d.]+) Tm \((.*?)\) Tj ET",
    re.DOTALL,
)

#: A page's **content** stream, and deliberately not every stream in the file.
#:
#: The document now also carries one image stream — the monogram in the masthead — and a bare
#: `stream…endstream` match returns it too. That made `pages()` report one page more than the
#: document has, with no text on it, and broke four assertions about page counts in a way whose
#: cause was not obvious from any of them.
#:
#: Anchored on `<< /Length N >>`, which is exactly how `PdfCanvas.render` writes a content stream and
#: is not how it writes the image (whose dictionary carries `/Type /XObject` and much else). So this
#: selects content streams by their shape rather than by excluding today's one exception, and a
#: second image added later would not need this line changed.
_STREAM = re.compile(rb"<< /Length \d+ >>\nstream\n(.*?)\nendstream", re.DOTALL)


class Run:
    """One run of text as it will be drawn: where it starts, how big, and how wide it ends up."""

    def __init__(self, font: bytes, size: float, x: float, y: float, raw: bytes) -> None:
        self.bold = font == b"F2"
        self.size = size
        self.x = x
        self.y = y
        # Undo the literal-string escaping `_escape` applied, then read it as what it is: cp1252.
        unescaped = (
            raw.replace(b"\\\\", b"\x00").replace(b"\\(", b"(").replace(b"\\)", b")")
        ).replace(b"\x00", b"\\")
        self.text = unescaped.decode("cp1252")

    @property
    def width(self) -> float:
        return text_width(self.text, size=self.size, bold=self.bold)

    @property
    def right(self) -> float:
        return self.x + self.width

    def __repr__(self) -> str:  # pragma: no cover - only ever read in a failure message
        return f"Run({self.text!r} at x={self.x:.1f} y={self.y:.1f} size={self.size})"


def pages(document: bytes) -> list[list[Run]]:
    """Every page's drawn text runs, in document order."""
    out: list[list[Run]] = []
    for stream in _STREAM.findall(document):
        out.append(
            [
                Run(font, float(size), float(x), float(y), raw)
                for font, size, x, y, raw in _RUN.findall(stream)
            ]
        )
    return out


def drawn_runs(document: bytes) -> list[Run]:
    return [run for page in pages(document) for run in page]


def drawn_text(document: bytes) -> str:
    """All the text, newline-joined. For asserting that a sentence is present, not where it is."""
    return "\n".join(run.text for run in drawn_runs(document))


# ==========================================================================================
# fixtures
# ==========================================================================================


@pytest.fixture
def demo_document(pipeline) -> bytes:
    from app.services.demo import demo_report

    return render_single_report(demo_report(pipeline), note="Testlauf")


def position(
    nr: str,
    ziffer: str,
    bucket: str,
    claimed: str,
    *,
    text: str = "Beispielleistung",
    reason: str = "",
    faktor: str = "2.3",
) -> PadnextAuditedPosition:
    return PadnextAuditedPosition(
        positionsnr=nr,
        ziffer=ziffer,
        go="GOÄ",
        in_catalog=True,
        official_text=text,
        bucket=bucket,  # type: ignore[arg-type]
        bucket_reason=reason,
        claimed_faktor=Decimal(faktor),
        claimed_amount_eur=Decimal(claimed),
        recomputed_amount_eur=Decimal(claimed),
    )


def report_of(positions: list[PadnextAuditedPosition], **extra) -> PadnextAuditReport:
    """A report whose three buckets reconcile, because the model refuses to exist otherwise."""
    totals = {"confirmed_fine": Decimal("0.00"), "confirmed_wrong": Decimal("0.00"),
              "unconfirmed": Decimal("0.00")}
    for item in positions:
        totals[item.bucket] += item.claimed_amount_eur or Decimal("0.00")
    claimed = sum(totals.values(), Decimal("0.00"))
    judged = totals["confirmed_fine"] + totals["confirmed_wrong"]
    extra.setdefault("source_name", "probe_padx.xml")
    return PadnextAuditReport(
        nachrichtentyp="ADL",
        positions=positions,
        claimed_total_eur=claimed,
        confirmed_fine_eur=totals["confirmed_fine"],
        confirmed_wrong_eur=totals["confirmed_wrong"],
        unconfirmed_eur=totals["unconfirmed"],
        coverage_ratio=float(judged / claimed) if claimed else 0.0,
        catalog_version="goae_test",
        receipt_hash="a" * 64,
        **extra,
    )


def job_of(files: list[BatchFileResult], summary: BatchAggregateSummary | None) -> BatchAuditJob:
    return BatchAuditJob(
        batch_id="batch_test_0001",
        status=BatchJobStatus.COMPLETED,
        created_at=datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 7, 26, 8, 5, tzinfo=timezone.utc),
        file_count=len(files),
        processed_file_count=len(files),
        completed_file_count=sum(1 for f in files if f.report is not None),
        failed_file_count=sum(1 for f in files if f.report is None),
        aggregate_summary=summary,
        files=files,
    )


# ==========================================================================================
# 1. the font metrics, which everything else is measured with
# ==========================================================================================


def test_the_width_tables_cover_every_code_point_winansi_defines():
    """A missing entry would not raise — it would measure as zero and silently overprint."""
    assert len(HELVETICA) == len(HELVETICA_BOLD) == 256
    for code in range(0x20, 0x7F):
        assert HELVETICA[code] > 0, f"no width for ASCII {code:#04x}"
    # Everything a German billing report needs, by the byte cp1252 gives it.
    for character in "äöüÄÖÜß€§—»«…°":
        code = character.encode("cp1252")[0]
        assert HELVETICA[code] > 0, f"no width for {character!r}"
        assert HELVETICA_BOLD[code] > 0, f"no bold width for {character!r}"


def test_the_digits_are_all_the_same_width():
    """Why a column of euro amounts can be right-aligned and still read as a column.

    Helvetica is tabular in the digits — every one of them is 556 units. If that stopped being
    true, `1.111,11 €` and `8.888,88 €` would set to different widths and the decimal commas in the
    Betrag column would no longer line up, which is the one visual property a financial table has.
    """
    widths = {HELVETICA[ord(d)] for d in "0123456789"}
    assert widths == {556}
    assert {HELVETICA_BOLD[ord(d)] for d in "0123456789"} == {556}


def test_measured_widths_match_the_published_helvetica_metrics():
    """Spot values from the Adobe AFM. If the table were regenerated wrong, these move."""
    assert text_width("A", size=1000) == 667
    assert text_width("A", size=1000, bold=True) == 722
    assert text_width(" ", size=1000) == 278
    assert text_width("€", size=1000) == 556
    assert text_width("ß", size=1000) == 611
    # And it scales linearly, which is what makes `size / 1000` the whole of the arithmetic.
    assert text_width("Prüfbericht", size=20) == pytest.approx(
        text_width("Prüfbericht", size=10) * 2
    )


def test_a_character_outside_cp1252_is_measured_as_the_glyph_that_will_be_drawn():
    """`_escape` substitutes `?`, so measuring the original would disagree with the output."""
    assert text_width("Ω", size=10) == text_width("?", size=10)


# ==========================================================================================
# 2. wrapping and fitting
# ==========================================================================================


@pytest.mark.parametrize("size", [7.5, 9.0, 10.0])
def test_no_wrapped_line_is_wider_than_the_column(size):
    text = (
        "Vollständige körperliche Untersuchung mindestens eines der folgenden Organsysteme: "
        "Auge, Hals-Nasen-Ohren, Haut, Stütz- und Bewegungsorgane, urogenitale Organe. "
        "Zuschläge für außergewöhnliche Umstände bleiben unberührt (§ 5 Abs. 2 GOÄ)."
    )
    for line in wrap(text, size=size, width=240):
        assert text_width(line, size=size) <= 240, line


def test_a_word_too_long_for_the_column_is_broken_rather_than_allowed_to_overflow():
    """A 64-character receipt hash in a 60-point column would otherwise run into the next one."""
    lines = wrap("a" * 200, size=9, width=60)
    assert len(lines) > 1
    for line in lines:
        assert text_width(line, size=9) <= 60
    assert "".join(lines) == "a" * 200, "breaking a word must not lose any of it"


def test_wrapping_never_loses_or_reorders_a_word():
    text = "GOÄ 200 ist neben GOÄ 301 nicht berechnungsfähig (§ 4 Abs. 2a GOÄ)."
    assert " ".join(wrap(text, size=8, width=150)).split() == text.split()


@pytest.mark.parametrize("width", [20.0, 60.0, 240.0])
def test_fit_never_returns_something_wider_than_it_was_asked_for(width):
    long_text = "Verband - ausgenommen Schnell- und Sprühverbände, Augen-, Ohren- und Halsbinden"
    result = fit(long_text, size=9, width=width)
    assert text_width(result, size=9) <= width
    assert result.endswith("…"), "a shortened cell must show that it was shortened"


def test_fit_leaves_a_string_that_already_fits_completely_alone():
    assert fit("410", size=9, width=100) == "410"


# ==========================================================================================
# 3. geometry — the checks that catch a document nobody can print
# ==========================================================================================


def assert_inside_the_page(document: bytes) -> None:
    """No run of text may cross a margin, ride over the footer, or fall off the top.

    This is the assertion the old renderer could not have passed and had no way to fail: it
    estimated every character at half an em, so a row of capitals measured narrower than it drew
    and quietly overprinted the column to its right.
    """
    for number, page in enumerate(pages(document), start=1):
        for run in page:
            assert run.x >= MARGIN - 0.5, f"page {number}: {run} starts left of the margin"
            assert run.right <= PAGE_WIDTH - MARGIN + 0.5, (
                f"page {number}: {run} runs {run.right - (PAGE_WIDTH - MARGIN):.1f} pt "
                "past the right margin"
            )
            assert run.y >= 20, f"page {number}: {run} is below the footer"
            assert run.y <= PAGE_HEIGHT - MARGIN + 1, f"page {number}: {run} is above the top margin"


#: How much clear space two cells on one baseline must leave between them. Two points at 9 pt is
#: about a third of a space — tight, but unambiguously *not* touching.
_MIN_GUTTER = 2.0


def assert_no_two_cells_collide(document: bytes) -> None:
    """Nothing drawn on a shared baseline may overlap anything else on it.

    The check the margin test cannot make. A right-aligned heading whose label is wider than the
    column it was given stays comfortably inside the page and still prints on top of its
    neighbour — which is exactly what `Nicht abrechenbar` (79 pt) did in a 63 pt column, running
    16 pt back into the Abgerechnet amounts beside it. On screen at 200 % it looks like tight
    spacing; on paper it is two numbers sharing the same ink.
    """
    for number, page in enumerate(pages(document), start=1):
        baselines: dict[float, list[Run]] = {}
        for run in page:
            baselines.setdefault(round(run.y, 1), []).append(run)
        for y, runs in baselines.items():
            ordered = sorted(runs, key=lambda run: run.x)
            for left, right in zip(ordered, ordered[1:]):
                assert left.right <= right.x - _MIN_GUTTER + 0.01, (
                    f"page {number}, baseline {y}: {left.text!r} ends at {left.right:.1f} and "
                    f"{right.text!r} starts at {right.x:.1f} — they overlap by "
                    f"{left.right - right.x:.1f} pt"
                )


def test_the_demo_report_stays_inside_its_page(demo_document):
    assert_inside_the_page(demo_document)


def test_no_two_cells_in_the_demo_report_print_on_top_of_each_other(demo_document):
    assert_no_two_cells_collide(demo_document)


def test_every_column_heading_fits_the_column_it_labels():
    """Caught directly rather than only through a rendered document, so the failure names the column.

    A heading is the widest thing most columns ever hold — `Nicht abrechenbar` is wider than every
    amount that will ever sit under it — so this is where a too-narrow column shows up first.
    """
    for table in (
        pdf_module._SUMMARY_COLUMNS,
        pdf_module._POSITION_COLUMNS,
        pdf_module._DELIVERY_COLUMNS,
    ):
        for column in table:
            measured = text_width(column.label, size=9, bold=True)
            assert measured <= column.width, (
                f"heading {column.label!r} is {measured:.1f} pt wide but its column is "
                f"{column.width:.1f} pt"
            )


def test_a_five_hundred_character_goae_description_does_not_break_the_layout():
    """The edge case a real catalog produces: some GOÄ Leistungstexte are a paragraph long."""
    document = render_single_report(
        report_of(
            [
                position(
                    "1",
                    "3306",
                    "confirmed_wrong",
                    "180.00",
                    text=(
                        "Untersuchung im Rahmen einer ausführlichen Diagnostik einschließlich "
                        "der Beurteilung sämtlicher erhobener Befunde sowie der Dokumentation "
                        "und der Erörterung mit dem Patienten " * 4
                    ),
                    reason="Verifizierte Prüfung fehlgeschlagen: " + "Begründungstext " * 40,
                )
            ]
        )
    )
    assert_inside_the_page(document)
    assert_no_two_cells_collide(document)


def test_a_hundred_positions_paginate_without_anything_sliding_off_a_page():
    positions = [
        position(str(index), str(400 + index), "unconfirmed", "26.81")
        for index in range(1, 101)
    ]
    document = render_single_report(report_of(positions))
    assert_inside_the_page(document)
    assert_no_two_cells_collide(document)
    assert len(pages(document)) > 2, "a hundred positions must not claim to fit on two pages"


def test_a_practice_name_full_of_special_characters_stays_in_its_column():
    document = render_single_report(
        report_of([position("1", "1", "confirmed_fine", "10.00")]),
        organization="Gemeinschaftspraxis Dres. Müller & Söhne — Ärzte für Groß- und "
                     "Kleintiere (Zweigstelle Köln/Düsseldorf) «Süd» 100 % €",
    )
    assert_inside_the_page(document)
    assert_no_two_cells_collide(document)


def test_a_string_with_no_spaces_at_all_cannot_escape_its_column():
    """The pathological input: a filename or hash with nothing to break on."""
    document = render_single_report(
        report_of([position("1", "1", "confirmed_wrong", "10.00", reason="x" * 400)])
    )
    assert_inside_the_page(document)
    assert_no_two_cells_collide(document)


def test_the_batch_report_stays_inside_its_page():
    files = [
        BatchFileResult(
            filename=f"lieferung_{index:03d}_sehr_langer_dateiname_padx.xml",
            status=BatchFileStatus.COMPLETED,
            report=report_of([position("1", "1", "confirmed_wrong", "88.49")]),
        )
        for index in range(40)
    ]
    files.append(
        BatchFileResult(
            filename="kaputt.xml",
            status=BatchFileStatus.FAILED,
            error_message="Die Datei ist kein gültiges PADnext-Dokument. " * 6,
        )
    )
    summary = BatchAggregateSummary(
        file_count=len(files),
        completed_file_count=40,
        failed_file_count=1,
        position_count=40,
        confirmed_wrong_positions=40,
        claimed_total_eur=Decimal("3539.60"),
        confirmed_wrong_eur=Decimal("3539.60"),
        coverage_ratio=1.0,
    )
    document = render_batch_report(job_of(files, summary), organization_id="org_test")
    assert_inside_the_page(document)
    assert_no_two_cells_collide(document)


# ==========================================================================================
# 4. the running furniture: page numbers and repeated table headings
# ==========================================================================================


def test_every_page_says_which_page_it_is_and_how_many_there_are(demo_document):
    """A stapled report that loses a page must make that detectable."""
    rendered = pages(demo_document)
    total = len(rendered)
    assert total >= 2, "the demo report is long enough that this test is worth running"
    for index, page in enumerate(rendered, start=1):
        assert any(
            run.text == f"Seite {index} von {total}" for run in page
        ), f"page {index} carries no page number"


def test_every_page_carries_the_report_identity_in_its_footer(demo_document):
    for number, page in enumerate(pages(demo_document), start=1):
        text = " ".join(run.text for run in page)
        assert "Azmoth" in text, f"page {number} does not say who produced it"
        assert "Bericht-ID" in text, f"page {number} cannot be tied back to its report"


def test_pages_after_the_first_repeat_the_document_title(demo_document):
    """A page that gets separated from the others still has to say what it belongs to."""
    for number, page in enumerate(pages(demo_document)[1:], start=2):
        text = " ".join(run.text for run in page)
        assert "GOÄ-Prüfbericht" in text, f"page {number} has no running header"


def test_a_table_that_spills_onto_a_page_repeats_its_column_headings():
    """The failure this prevents: page two of a long invoice is a column of unlabelled amounts."""
    positions = [
        position(str(index), str(400 + index), "unconfirmed", "26.81")
        for index in range(1, 121)
    ]
    document = render_single_report(report_of(positions))
    spilled = [
        page for page in pages(document) if any(run.text == "26,81 €" for run in page)
    ]
    assert len(spilled) >= 2, "the fixture must actually spill, or this asserts nothing"
    for page in spilled:
        labels = {run.text for run in page}
        assert "Ziffer" in labels and "Abgerechnet" in labels, (
            "a page of position rows must carry the column headings for those rows"
        )


def test_the_heading_of_a_table_is_never_the_last_thing_on_a_page():
    """`reserve` exists for this: a heading alone at the foot of a page is a heading nobody reads."""
    positions = [
        position(str(index), str(400 + index), "unconfirmed", "26.81")
        for index in range(1, 61)
    ]
    document = render_single_report(report_of(positions))
    for page in pages(document):
        body = [run for run in page if run.y > BOTTOM]
        if not body:
            continue
        lowest = min(body, key=lambda run: run.y)
        assert lowest.text not in {"Ziffer", "Bewertung", "Datei"}, (
            f"a table heading ({lowest.text!r}) was left stranded at the foot of a page"
        )


# ==========================================================================================
# 5. document metadata and structure
# ==========================================================================================


def test_the_document_carries_the_metadata_an_archive_indexes_on(demo_document):
    for key in (b"/Title", b"/Author", b"/Subject", b"/Creator", b"/Producer", b"/Keywords"):
        assert key in demo_document, f"{key.decode()} is missing from /Info"
    assert b"/Author (Azmoth)" in demo_document
    assert b"/Info 5 0 R" in demo_document, "the trailer must point at the info dictionary"
    assert b"/DisplayDocTitle true" in demo_document, (
        "a reader should show the report's title, not the filename it happens to be saved under"
    )
    assert b"/Lang (de-DE)" in demo_document


def test_a_title_with_an_em_dash_survives_into_the_metadata():
    """The bug this pins: `/Info` literals are PDFDocEncoded, not cp1252.

    An em dash is 0x97 in cp1252 and `Š` in PDFDocEncoding, so `GOÄ-Prüfbericht — Datei.xml` was
    reaching Acrobat's properties dialogue as `GOÄ-Prüfbericht Š Datei.xml`. Written as a UTF-16BE
    text string it round-trips, and this asserts the encoded form is actually there.
    """
    canvas = PdfCanvas(title="GOÄ-Prüfbericht — Datei.xml")
    document = canvas.render()
    encoded = ("﻿" + "GOÄ-Prüfbericht — Datei.xml").encode("utf-16-be").hex().encode("ascii")
    assert b"/Title <" + encoded + b">" in document


def test_an_ascii_title_stays_a_readable_literal():
    """No reason to make a file unreadable to `less` when the string is unambiguous either way."""
    assert b"/Title (Batch 0001)" in PdfCanvas(title="Batch 0001").render()


def test_the_cross_reference_table_points_at_the_objects_it_claims_to(demo_document):
    """The one part of a hand-written PDF that is easy to get subtly wrong, checked exactly."""
    start = demo_document.rindex(b"startxref\n")
    offset = int(demo_document[start + 10 :].split(b"\n", 1)[0])
    table = demo_document[offset:]
    assert table.startswith(b"xref\n")
    count = int(table.split(b"\n")[1].split()[1])
    entries = table.split(b"\n")[2 : 2 + count]
    for number, entry in enumerate(entries):
        if number == 0:
            assert entry.startswith(b"0000000000 65535 f")
            continue
        at = int(entry.split()[0])
        assert demo_document[at:].startswith(f"{number} 0 obj".encode()), (
            f"xref entry {number} points at {demo_document[at:at + 20]!r}"
        )


def test_the_page_tree_declares_as_many_pages_as_it_holds(demo_document):
    declared = int(re.search(rb"/Type /Pages /Count (\d+)", demo_document).group(1))
    assert declared == len(pages(demo_document))
    assert declared == demo_document.count(b"/Type /Page /Parent")


def test_every_page_is_a4(demo_document):
    boxes = re.findall(rb"/MediaBox \[0 0 (\d+) (\d+)\]", demo_document)
    assert boxes, "no page declared a size"
    assert all(box == (b"595", b"842") for box in boxes)


def test_the_text_is_real_text_and_not_a_picture_of_text(demo_document):
    """What makes Ctrl+F work in a reader, and what an archive's full-text index needs.

    This used to assert `/Subtype /Image not in` the document, which was a proxy: with no images at
    all, no page could be a scan. There is now exactly one image — the monogram in the masthead — so
    the property is asserted directly instead, and the proxy is replaced by a bound.

    **One image, and it is 128x128.** That is the check that would fail if somebody ever rendered a
    page as a picture: a page-sized raster is not 128 points square, and a document that grew a
    second image would have to come back through this test to say what it was for.
    """
    assert b"/Subtype /Type1" in demo_document
    assert b"/BaseFont /Helvetica" in demo_document
    assert b"/Encoding /WinAnsiEncoding" in demo_document
    assert len(drawn_runs(demo_document)) > 100

    images = re.findall(rb"/Subtype /Image[^>]*?/Width (\d+) /Height (\d+)", demo_document)
    assert images == [(b"128", b"128")], (
        "the only image this document may carry is the 128x128 monogram. A page rendered as a "
        "picture would show up here, and so would a second image nobody documented."
    )

    # And the brand is in the text as well as in the raster, which is what makes it survive a
    # monochrome fax, a screen reader and `pdftotext` — see `_masthead`.
    assert "A Z M O T H" in drawn_text(demo_document)


def test_a_report_of_a_hundred_positions_is_a_file_somebody_can_email():
    positions = [
        position(str(index), str(400 + index), "unconfirmed", "26.81")
        for index in range(1, 101)
    ]
    document = render_single_report(report_of(positions))
    assert len(document) < 5 * 1024 * 1024, "a hundred positions must not produce a 5 MB PDF"
    # In practice it is two orders of magnitude under that; this pins the order of magnitude.
    assert len(document) < 300_000


# ==========================================================================================
# 6. determinism, and the one clock that is allowed
# ==========================================================================================


def test_the_same_report_renders_the_same_bytes(pipeline):
    """Two downloads of one finished audit must not be two different documents."""
    from app.services.demo import demo_report

    report = demo_report(pipeline)
    assert render_single_report(report) == render_single_report(report)


def test_a_supplied_timestamp_is_an_input_and_not_a_hidden_clock():
    """Determinism stated precisely: identical inputs *including the stamp* give identical bytes."""
    report = report_of([position("1", "1", "confirmed_fine", "10.00")])
    at = datetime(2026, 8, 31, 14, 5, tzinfo=timezone.utc)
    assert render_single_report(report, generated_at=at) == render_single_report(
        report, generated_at=at
    )
    later = render_single_report(report, generated_at=at + timedelta(minutes=1))
    assert later != render_single_report(report, generated_at=at), (
        "a different generation time must actually show on the document"
    )


def test_no_creation_date_is_written_when_no_time_was_supplied():
    """What keeps the public demo's two downloads byte-identical."""
    document = render_single_report(report_of([position("1", "1", "confirmed_fine", "10.00")]))
    assert b"/CreationDate" not in document


def test_a_supplied_time_reaches_both_the_page_and_the_metadata():
    at = datetime(2026, 8, 31, 14, 5, tzinfo=timezone.utc)
    document = render_single_report(
        report_of([position("1", "1", "confirmed_fine", "10.00")]), generated_at=at
    )
    assert b"/CreationDate (D:20260831140500Z)" in document
    assert "31.08.2026 14:05 UTC" in drawn_text(document), (
        "the date on the page is the one a reader checks; it must be the same one"
    )


def test_a_timestamp_in_a_local_zone_keeps_its_offset():
    """Berlin, not UTC-with-the-hours-moved. An archived report is read months later."""
    berlin = timezone(timedelta(hours=2))
    document = render_single_report(
        report_of([position("1", "1", "confirmed_fine", "10.00")]),
        generated_at=datetime(2026, 8, 31, 16, 5, tzinfo=berlin),
    )
    assert b"/CreationDate (D:20260831160500+02'00')" in document


def test_a_batch_report_dates_itself_by_when_the_run_finished():
    """Re-downloading a finished batch next week must still produce the same file."""
    job = job_of(
        [
            BatchFileResult(
                filename="a.xml",
                status=BatchFileStatus.COMPLETED,
                report=report_of([position("1", "1", "confirmed_fine", "10.00")]),
            )
        ],
        BatchAggregateSummary(
            file_count=1,
            completed_file_count=1,
            position_count=1,
            confirmed_fine_positions=1,
            claimed_total_eur=Decimal("10.00"),
            confirmed_fine_eur=Decimal("10.00"),
            coverage_ratio=1.0,
        ),
    )
    first = render_batch_report(job, organization_id="org_test")
    assert first == render_batch_report(job, organization_id="org_test")
    assert b"/CreationDate (D:20260726080500Z)" in first, "the job's own completion time"


# ==========================================================================================
# 7. what the document must say
# ==========================================================================================


def test_the_mandated_disclaimer_appears_verbatim(demo_document):
    """Reworded by accident is the failure mode; the constant and the page must agree exactly."""
    printed = " ".join(drawn_text(demo_document).split())
    assert " ".join(DISCLAIMER.split()) in printed


def test_the_report_names_its_data_protection_basis_and_a_contact(demo_document):
    printed = drawn_text(demo_document)
    assert "DSGVO" in printed
    assert "contact@azmoth.com" in printed
    assert "Azmoth" in printed


def test_the_report_names_the_catalog_edition_it_was_priced_against(demo_document):
    """Provenance without a consequence is theatre. The terms name the edition *and* say what
    auditing an older invoice against it costs, because the reader of a filed Prüfbericht is
    eighteen months downstream of the upload and was told none of this."""
    printed = " ".join(drawn_text(demo_document).split())

    assert "Geprüft gegen den GOÄ-Katalog in der Fassung von" in printed
    assert "Für historische Rechnungen" in printed
    assert "12 Monate" in printed


def test_a_pilot_warning_reaches_the_printed_terms(demo_document, pipeline):
    """The soft warning has to survive the trip into print. A caveat that exists only in JSON is a
    caveat the practice never sees, because what they file is the PDF."""
    from app.services.demo import demo_report

    report = demo_report(pipeline)
    report.pilot_warnings = [TEMPORAL_SCOPE_WARNING]
    printed = " ".join(drawn_text(render_single_report(report, note="Testlauf")).split())

    assert " ".join(TEMPORAL_SCOPE_WARNING.split()) in printed
    # And the clean report does not carry it, so its presence always means something.
    assert " ".join(TEMPORAL_SCOPE_WARNING.split()) not in " ".join(
        drawn_text(demo_document).split()
    )


def test_the_report_offers_somewhere_to_record_the_required_release(demo_document):
    """A document that demands a physician's Freigabe and offers no line for it invites a
    verbal one."""
    printed = drawn_text(demo_document)
    assert "Freigabe" in printed
    assert "Ort, Datum" in printed
    assert "Unterschrift" in printed


def test_the_three_buckets_are_never_merged_into_one_risk_number(demo_document):
    printed = drawn_text(demo_document)
    assert "Belegbar korrekt" in printed
    assert "Belegbar nicht abrechenbar" in printed
    assert "Nicht beurteilbar" in printed
    assert "Risiko:" not in printed
    assert "Gesamtrisiko" not in printed


def test_the_provenance_block_carries_the_full_receipt_hash(pipeline):
    """A truncated hash identifies nothing; the point of printing it is that it can be compared."""
    from app.services.demo import demo_report

    report = demo_report(pipeline)
    assert report.receipt_hash in drawn_text(render_single_report(report))


def test_every_rejected_position_prints_its_legal_ground_and_its_rule_id(pipeline):
    """What separates a report a payer can act on from one they can only be annoyed by."""
    from app.services.demo import demo_report

    report = demo_report(pipeline)
    printed = drawn_text(render_single_report(report))
    assert "§ 12 Abs. 3 GOÄ" in printed
    assert "§ 4 Abs. 2a GOÄ" in printed
    assert "ziel_man_301_200" in printed, "the rule id is what makes a finding traceable"
    assert "excl_man_5_7" in printed


def test_each_position_prints_the_official_catalog_text_and_the_claimed_factor(pipeline):
    from app.services.demo import demo_report

    report = demo_report(pipeline)
    printed = drawn_text(render_single_report(report))
    assert "Symptombezogene Untersuchung" in printed, "the official GOÄ Leistungstext"
    assert "3,5" in printed, "the claimed Steigerungsfaktor, in German notation"


def test_the_invoice_the_report_is_about_is_named_on_it(pipeline):
    """A billing centre files one of these per invoice. It has to say which."""
    from app.services.demo import demo_report

    report = demo_report(pipeline)
    assert report.invoice_ids == ["SYNTH-2026-0001"]
    assert "SYNTH-2026-0001" in drawn_text(render_single_report(report))


def test_a_note_is_part_of_the_document_rather_than_a_watermark(pipeline):
    """A watermark is the first thing a photocopier loses."""
    from app.services.demo import demo_report

    printed = drawn_text(
        render_single_report(demo_report(pipeline), note="DEMONSTRATION — synthetische Testdaten")
    )
    assert "DEMONSTRATION" in printed


def test_positions_are_grouped_with_the_ones_that_need_action_first():
    document = render_single_report(
        report_of(
            [
                position("1", "1", "confirmed_fine", "10.00"),
                position("2", "2", "unconfirmed", "20.00"),
                position("3", "3", "confirmed_wrong", "30.00"),
            ]
        )
    )
    printed = drawn_text(document)
    wrong = printed.index("Belegbar nicht abrechenbar — 1 Position")
    unconfirmed = printed.index("Nicht beurteilbar — 1 Position")
    fine = printed.index("Belegbar korrekt — 1 Position")
    assert wrong < unconfirmed < fine, (
        "the first heading must answer 'what do I have to change?'"
    )


def test_a_batch_with_no_rollup_prints_the_absence_rather_than_zeros():
    """A page of €0,00 is a document somebody could reconcile against."""
    document = render_batch_report(job_of([], None), organization_id="org_test")
    printed = drawn_text(document)
    assert "Kein Ergebnis" in printed
    assert "0,00 €" not in printed
    # The terms still have to be on it — an empty result is still a document that leaves the building.
    assert "contact@azmoth.com" in printed


# ==========================================================================================
# 8. the money
# ==========================================================================================


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.00", "0,00 €"),
        ("12.50", "12,50 €"),
        ("1234.5", "1.234,50 €"),
        ("1234567.89", "1.234.567,89 €"),
        ("-40.10", "-40,10 €"),
    ],
)
def test_amounts_are_typeset_from_the_decimal_not_from_a_float(value, expected):
    """A cent that disappears into binary floating point is a cent a Rechnungsprüfer will find."""
    assert _euro(Decimal(value)) == expected


def test_the_printed_totals_are_the_report_s_own_totals_to_the_cent(pipeline):
    """The document and the JSON must not come to disagree about a total."""
    from app.services.demo import demo_report

    report = demo_report(pipeline)
    printed = drawn_text(render_single_report(report))
    for amount in (
        report.claimed_total_eur,
        report.confirmed_fine_eur,
        report.confirmed_wrong_eur,
        report.unconfirmed_eur,
    ):
        assert _euro(amount) in printed, f"{amount} does not appear on the report"


def test_the_bucket_shares_add_up_to_a_hundred_percent(pipeline):
    from app.services.demo import demo_report

    report = demo_report(pipeline)
    printed = drawn_text(render_single_report(report))
    shares = [
        Decimal(match.replace(".", "").replace(",", "."))
        for match in re.findall(r"(\d+,\d) %", printed)
    ]
    # The three bucket shares, the total's 100,0 and the coverage ratio are all on the page; the
    # three that must reconcile are the ones that reconcile in the model.
    for value in (
        report.confirmed_fine_eur,
        report.confirmed_wrong_eur,
        report.unconfirmed_eur,
    ):
        expected = (value / report.claimed_total_eur * 100).quantize(Decimal("0.1"))
        assert expected in shares, f"share {expected} for {value} is not printed"


def test_amounts_are_right_aligned_so_the_column_reads_as_a_column():
    """The reason the width table exists at all."""
    document = render_single_report(
        report_of(
            [
                position("1", "1", "confirmed_wrong", "9.00"),
                position("2", "2", "confirmed_wrong", "1234.56"),
            ]
        )
    )
    amounts = [run for run in drawn_runs(document) if run.text in {"9,00 €", "1.234,56 €"}]
    # Each position prints its amount twice — once claimed, once recomputed — so there are two
    # columns here and the claim is that each is internally flush, not that they coincide.
    columns: dict[int, list[float]] = {}
    for run in amounts:
        columns.setdefault(round(run.right), []).append(run.right)
    assert len(columns) == 2, f"expected a claimed and a recomputed column, got {columns.keys()}"
    for edge, members in columns.items():
        assert len(members) == 2, f"column at {edge} did not receive both amounts"
        # Within a hundredth of a point, which is the precision the writer emits: positions go
        # into the content stream as `%.2f`, so two right edges can differ by half of that and
        # still be the same edge. Half a hundredth of a point is 1.8 microns.
        assert max(members) - min(members) <= 0.01, (
            f"amounts in the column at {edge} do not share a right edge: {members}"
        )
    # A short amount and a long one in the same column must start at different x — which is the
    # whole difference between right-aligned and left-aligned.
    assert len({round(run.x) for run in amounts}) == 4


def test_german_characters_reach_the_content_stream_as_cp1252(demo_document):
    """`WinAnsiEncoding` is cp1252, so these are the bytes a reader will map back to glyphs."""
    assert "Prüfbericht".encode("cp1252") in demo_document
    assert "€".encode("cp1252") in demo_document
    assert "Gebührenordnung".encode("cp1252") in demo_document


def test_a_string_reaching_a_pdf_literal_cannot_break_out_of_it():
    """Parentheses and backslashes delimit and escape a PDF string. A filename carrying one — and
    a filename is client-supplied — would otherwise produce a document no reader can parse."""
    assert _escape("a(b)c\\d") == rb"a\(b\)c\\d"
    assert _escape("Zuschläge") == "Zuschläge".encode("cp1252")
    # Outside cp1252: substituted rather than raising, because a report that fails to render over
    # one character in a practice's name is a worse failure than a substituted one.
    assert _escape("Ω") == b"?"


def test_a_filename_full_of_delimiters_still_produces_a_document_that_parses():
    document = render_single_report(
        report_of([position("1", "1", "confirmed_fine", "10.00")], source_name="a(b)c\\d.xml")
    )
    assert document.startswith(b"%PDF-1.4")
    assert "a(b)c\\d.xml" in drawn_text(document)


# ==========================================================================================
# 9. the writer itself
# ==========================================================================================


def test_the_writer_produces_a_document_a_reader_can_open():
    canvas = PdfCanvas(title="test")
    canvas.text("Prüfbericht", bold=True)
    canvas.paragraph("Ein Absatz mit Umlauten: äöüß, und einem Betrag von 1.234,56 €.")
    document = canvas.render()

    assert document.startswith(b"%PDF-1.4")
    assert document.rstrip().endswith(b"%%EOF")
    assert b"/Type /Catalog" in document
    assert b"startxref" in document
    for number in (1, 2, 3, 4, 5):
        assert f"{number} 0 obj".encode() in document


def test_a_long_report_flows_onto_more_than_one_page():
    canvas = PdfCanvas(title="test")
    for index in range(300):
        canvas.text(f"Zeile {index}")
    document = canvas.render()
    assert len(pages(document)) > 1
    assert b"/Type /Pages" in document


def test_a_bare_x_text_pair_is_still_a_valid_table_cell():
    """The old two-tuple call shape, kept working so every call site did not have to move."""
    canvas = PdfCanvas(title="test")
    canvas.row([(0, "a"), (100, "b")])
    assert {run.text for run in drawn_runs(canvas.render())} >= {"a", "b"}


def test_a_repeating_table_header_stops_repeating_once_the_table_is_closed():
    """Otherwise the next section inherits the previous section's column headings."""
    canvas = PdfCanvas(title="test")
    table = canvas.table([Column("Ziffer", 0, 100)])
    table.head()
    table.close()
    for _ in range(200):
        canvas.text("füllung")
    document = canvas.render()
    assert sum(run.text == "Ziffer" for run in drawn_runs(document)) == 1


def test_reserve_moves_to_a_new_page_rather_than_splitting_a_block():
    canvas = PdfCanvas(title="test")
    while canvas.y - 400 >= BOTTOM:
        canvas.text("zeile")
    before = canvas.page_count
    canvas.reserve(400)
    assert canvas.page_count == before + 1


def test_reserve_does_nothing_when_the_block_already_fits():
    """The other half of the contract: `reserve` must not gratuitously start a page."""
    canvas = PdfCanvas(title="test")
    canvas.text("zeile")
    canvas.reserve(50)
    assert canvas.page_count == 1


def test_the_content_width_is_what_every_table_is_laid_out_against():
    """A guard on the geometry constants themselves: 20 mm margins on A4."""
    assert CONTENT_WIDTH == PAGE_WIDTH - 2 * MARGIN == 483
    assert 19.5 <= MARGIN / 72 * 25.4 <= 20.5, "the margin must be 20 mm to the nearest half"
    for table in (pdf_module._SUMMARY_COLUMNS, pdf_module._POSITION_COLUMNS,
                  pdf_module._DELIVERY_COLUMNS):
        last = table[-1]
        assert last.x + last.width <= CONTENT_WIDTH, (
            f"{[c.label for c in table]} is wider than the text column"
        )


# ==========================================================================================
# 10. the two endpoints that hand this document to a user
# ==========================================================================================


@pytest.fixture
def delivery_bytes() -> bytes:
    from app.services.demo import demo_delivery_path

    return demo_delivery_path().read_bytes()


def test_the_single_audit_endpoint_answers_with_a_pdf(client, delivery_bytes):
    response = client.post(
        "/api/v1/padnext/audit.pdf",
        content=delivery_bytes,
        headers={
            "Content-Type": "application/xml",
            "X-Padnext-Filename": "00004711_20260726_ADL_000001_padx.xml",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="pruefbericht_00004711_20260726_ADL_000001_padx.pdf"'
    )
    # A Prüfbericht carries a timestamp and a practice's billing detail; it must not be cached
    # anywhere between the engine and the browser.
    assert response.headers["cache-control"] == "no-store"
    assert_inside_the_page(response.content)
    assert_no_two_cells_collide(response.content)


def test_the_pdf_and_the_json_are_the_same_audit(client, delivery_bytes):
    """Two renderings of one verdict. The receipt hash on the document is what proves it."""
    headers = {"Content-Type": "application/xml", "X-Padnext-Filename": "probe_padx.xml"}
    report = client.post("/api/v1/padnext/audit", content=delivery_bytes, headers=headers).json()
    document = client.post(
        "/api/v1/padnext/audit.pdf", content=delivery_bytes, headers=headers
    ).content

    printed = drawn_text(document)
    assert report["receipt_hash"] in printed
    assert _euro(Decimal(report["claimed_total_eur"])) in printed
    assert _euro(Decimal(report["confirmed_wrong_eur"])) in printed


def test_the_single_pdf_refuses_exactly_what_the_json_refuses(client):
    """Same endpoint underneath, so a refusal must not differ between the two — including the
    `error_code` a caller branches on."""
    for content, expected in ((b"", 400), (b"<nope/>", 422)):
        json_status = client.post(
            "/api/v1/padnext/audit", content=content, headers={"Content-Type": "application/xml"}
        ).status_code
        pdf = client.post(
            "/api/v1/padnext/audit.pdf",
            content=content,
            headers={"Content-Type": "application/xml"},
        )
        assert pdf.status_code == json_status == expected
        assert pdf.headers["content-type"].startswith("application/json"), (
            "a refusal is a JSON error body, not a PDF of an error"
        )


def test_a_filename_with_a_space_or_a_slash_cannot_break_the_download_header(client, delivery_bytes):
    """The filename arrives in a request header and leaves in a response header. Sanitised, not
    trusted — `attachment_headers` would otherwise refuse the whole response over one space."""
    response = client.post(
        "/api/v1/padnext/audit.pdf",
        content=delivery_bytes,
        headers={
            "Content-Type": "application/xml",
            "X-Padnext-Filename": "../etc/Rechnung Mai 2026.xml",
        },
    )
    assert response.status_code == 200
    # The directory part is dropped outright rather than escaped, so a traversal attempt cannot
    # even reach the character filter — what is left is the basename it was hiding behind.
    assert response.headers["content-disposition"] == (
        'attachment; filename="pruefbericht_Rechnung_Mai_2026.pdf"'
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("00004711_20260726_ADL_000001_padx.xml", "pruefbericht_00004711_20260726_ADL_000001_padx.pdf"),
        ("lieferung.padx", "pruefbericht_lieferung.pdf"),
        ("Rechnung Mai.xml", "pruefbericht_Rechnung_Mai.pdf"),
        ("", "pruefbericht.pdf"),
        ("...", "pruefbericht.pdf"),
        ("/nur/pfad/", "pruefbericht.pdf"),
        ("../../etc/passwd", "pruefbericht_passwd.pdf"),
    ],
)
def test_the_download_filename_is_derived_and_always_safe(source, expected):
    from app.api.padnext import pruefbericht_filename
    from app.services.export import SAFE_FILENAME

    result = pruefbericht_filename(source)
    assert result == expected
    assert SAFE_FILENAME.match(result), "every derived name must pass the header guard"


async def test_the_batch_pdf_is_refused_while_the_batch_is_unfinished(client):
    """A partial roll-up printed onto paper is a number somebody reconciles against three weeks
    later, with no way to tell which moment it was a snapshot of.

    The job is written directly rather than uploaded, because a batch that goes through the endpoint
    is already `COMPLETED` by the time the `202` returns — `TestClient` runs the drain inside the
    request cycle. This is the only way to observe a non-terminal one.
    """
    from app.api import deps
    from app.services.batch_audit import new_batch_id
    from tests.conftest import TEST_ORGANIZATION_ID

    batch_id = new_batch_id()
    await deps.batches().create_bulk_job(
        [],
        upload_path="/nonexistent/upload.zip",
        organization_id=TEST_ORGANIZATION_ID,
        batch_id=batch_id,
    )

    refused = client.post(f"/api/v1/padnext/batch/{batch_id}/report.pdf")
    assert refused.status_code == 409, refused.text
    assert refused.json()["details"]["current_status"] == "PENDING"


def test_an_unknown_batch_is_a_404_rather_than_an_empty_report(client):
    response = client.post("/api/v1/padnext/batch/batch_does_not_exist/report.pdf")
    assert response.status_code == 404


def test_a_completed_batch_renders_and_re_renders_the_same_document(client, delivery_bytes):
    """Downloading a finished batch twice must give one document, not two."""
    accepted = client.post(
        "/api/v1/padnext/batch",
        files=[
            ("files", ("erste_padx.xml", delivery_bytes, "application/xml")),
            ("files", ("zweite_padx.xml", delivery_bytes, "application/xml")),
        ],
    )
    batch_id = accepted.json()["batch_id"]
    assert client.get(f"/api/v1/padnext/batch/{batch_id}").json()["status"] == "COMPLETED"

    first = client.post(f"/api/v1/padnext/batch/{batch_id}/report.pdf")
    assert first.status_code == 200
    assert first.headers["content-type"] == "application/pdf"
    assert first.headers["content-disposition"] == (
        f'attachment; filename="{batch_id}_pruefbericht.pdf"'
    )
    assert first.content == client.post(f"/api/v1/padnext/batch/{batch_id}/report.pdf").content

    assert_inside_the_page(first.content)
    assert_no_two_cells_collide(first.content)
    printed = drawn_text(first.content)
    assert "erste_padx.xml" in printed and "zweite_padx.xml" in printed
    assert batch_id in printed


def test_a_batch_belonging_to_another_practice_has_no_report_here(client, delivery_bytes):
    """Same refusal the rest of the batch endpoints make: a 404, not a 403 — see `app.api.tenancy`."""
    accepted = client.post(
        "/api/v1/padnext/batch",
        files=[("files", ("a_padx.xml", delivery_bytes, "application/xml"))],
    )
    batch_id = accepted.json()["batch_id"]
    assert client.post(f"/api/v1/padnext/batch/{batch_id}/report.pdf").status_code == 200

    other = client.post(
        f"/api/v1/padnext/batch/{batch_id}/report.pdf",
        headers={"X-Organization-ID": "org_someone_else"},
    )
    assert other.status_code == 404
