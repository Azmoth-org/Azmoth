"""A PDF writer, and the audit report rendered through it.

**Why there is no library here.** Every dependency in `requirements.txt` is pinned with a reason
written beside it, because the receipt hash records what produced an answer and an unpinned bump
would silently change what a receipt means. Adding ReportLab or WeasyPrint to render a table of
numbers would be the largest dependency in the file — WeasyPrint pulls a browser layout engine and
Cairo — to typeset text this service already holds as strings. So the subset of PDF that draws
left-aligned Helvetica in a grid is implemented here, in about two hundred lines, with no C
extension, no fonts to ship and nothing to keep up to date.

**What that subset is, and what it is not.** PDF 1.4, the fourteen standard fonts (so no font is
embedded), `WinAnsiEncoding`, single-column text, no images and no vector graphics beyond straight
rules. That is exactly enough for a Prüfbericht and is not enough for anything with a layout. If
this ever needs a chart or a logo, that is the moment to take the dependency — not before.

**The output is deterministic.** Same job, same bytes: no creation timestamp, no producer version,
no object ids that depend on a dict's iteration order. That is what lets a test assert on the whole
document, and it is also the honest property for a document that reports on money — two downloads
of the same completed batch produce the same file, the way `export_batch` already does for CSVs.

**Encoding is cp1252, not UTF-8.** `WinAnsiEncoding` *is* cp1252, so the two agree byte for byte
over everything a German billing report contains, including `ä`, `ß` and `€` (which Latin-1, often
reached for instead, does not have). A character outside it becomes `?` rather than a broken glyph
or an exception — a report that fails to render because one practice's name has a Cyrillic letter
in it would be a worse failure than a substituted character.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.schemas.batch import BatchAggregateSummary, BatchAuditJob, BatchFileStatus

log = logging.getLogger(__name__)

# A4 in PostScript points (1/72 inch), which is the only unit PDF has.
PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 48

#: The fourteen standard fonts need no embedding, and these two are the only ones used.
FONT_REGULAR = "F1"
FONT_BOLD = "F2"

#: Where the body starts and stops. Below `BOTTOM` a new page is begun.
TOP = PAGE_HEIGHT - MARGIN
BOTTOM = MARGIN + 24

#: Rough advance width of Helvetica at size 1, averaged over the characters a report contains.
#: Used only to decide where to wrap a paragraph — the renderer never needs a true text extent,
#: because nothing here is centred or right-aligned against a computed width.
AVERAGE_GLYPH_WIDTH = 0.5


def _escape(text: str) -> bytes:
    """One PDF literal string's payload: cp1252 bytes with `\\`, `(` and `)` escaped.

    The escaping has to happen after the encode, not before, or a multi-byte sequence could be
    mistaken for a parenthesis. cp1252 is single-byte, so in practice the order does not bite —
    doing it in the safe order anyway costs nothing and survives somebody changing the encoding.
    """
    raw = text.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def wrap(text: str, *, size: float, width: float) -> list[str]:
    """Break a paragraph into lines that fit `width` points. Whitespace-only splitting.

    Approximate by design — see `AVERAGE_GLYPH_WIDTH`. A line that runs a few points long in a
    report nobody sets in two columns is not worth carrying a font metrics table for.
    """
    limit = max(8, int(width / (size * AVERAGE_GLYPH_WIDTH)))
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines or [""]


@dataclass
class _Page:
    """One page's content stream, accumulated as PDF operators."""

    operators: list[bytes] = field(default_factory=list)


class PdfCanvas:
    """Draw text and rules onto pages, then serialise the whole document.

    Stateful and single-use: `y` walks down the page and a write that would cross `BOTTOM` starts a
    new one. That is the entire layout model, and it is enough because every element in this report
    is a full-width row placed under the previous one.
    """

    def __init__(self, *, title: str) -> None:
        self.title = title
        self._pages: list[_Page] = []
        self._page: _Page | None = None
        self.y = 0.0
        self.new_page()

    # -- page management -------------------------------------------------------------------

    def new_page(self) -> None:
        self._page = _Page()
        self._pages.append(self._page)
        self.y = TOP

    def _ensure(self, needed: float) -> None:
        if self.y - needed < BOTTOM:
            self.new_page()

    # -- drawing ---------------------------------------------------------------------------

    def text(
        self,
        value: str,
        *,
        x: float = MARGIN,
        size: float = 9.5,
        bold: bool = False,
        leading: float | None = None,
    ) -> None:
        """One line, at the current vertical position. Advances past it."""
        step = leading if leading is not None else size + 3.5
        self._ensure(step)
        assert self._page is not None
        font = FONT_BOLD if bold else FONT_REGULAR
        self._page.operators.append(
            b"BT /" + font.encode() + f" {size:g} Tf 1 0 0 1 {x:g} {self.y:g} Tm (".encode()
            + _escape(value)
            + b") Tj ET"
        )
        self.y -= step

    def paragraph(self, value: str, *, size: float = 8.5, indent: float = 0.0) -> None:
        """A wrapped block of prose. The caveats in this report are paragraphs, not table cells."""
        for line in wrap(value, size=size, width=PAGE_WIDTH - 2 * MARGIN - indent):
            self.text(line, x=MARGIN + indent, size=size)

    def row(self, cells: list[tuple[float, str]], *, size: float = 8.5, bold: bool = False) -> None:
        """One table row: `(x offset, text)` pairs, all on the same baseline.

        Columns are absolute offsets rather than a computed grid, because the tables here have
        fixed shapes decided at authoring time and a column solver would be a layout engine — the
        thing this module exists not to be.
        """
        step = size + 4
        self._ensure(step)
        assert self._page is not None
        font = FONT_BOLD if bold else FONT_REGULAR
        for offset, value in cells:
            self._page.operators.append(
                b"BT /" + font.encode()
                + f" {size:g} Tf 1 0 0 1 {MARGIN + offset:g} {self.y:g} Tm (".encode()
                + _escape(value)
                + b") Tj ET"
            )
        self.y -= step

    def rule(self, *, thickness: float = 0.5) -> None:
        """A horizontal line across the text column."""
        self._ensure(6)
        assert self._page is not None
        self._page.operators.append(
            f"{thickness:g} w {MARGIN} {self.y + 3:g} m {PAGE_WIDTH - MARGIN} "
            f"{self.y + 3:g} l S".encode()
        )
        self.y -= 6

    def space(self, points: float = 8) -> None:
        self._ensure(points)
        self.y -= points

    # -- serialisation ---------------------------------------------------------------------

    def render(self) -> bytes:
        """The complete PDF.

        Object numbering is fixed rather than allocated: 1 catalogue, 2 page tree, 3 and 4 the two
        fonts, then a page and a content stream per page. Fixed because it makes the cross-reference
        table computable in one pass and the output byte-identical for identical input — an
        allocator keyed on insertion order would be the one place non-determinism could creep in.
        """
        objects: dict[int, bytes] = {}
        page_ids = [5 + 2 * index for index in range(len(self._pages))]

        objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
        kids = b" ".join(f"{page_id} 0 R".encode() for page_id in page_ids)
        objects[2] = (
            b"<< /Type /Pages /Count " + str(len(page_ids)).encode() + b" /Kids [" + kids + b"] >>"
        )
        objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
        objects[4] = (
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
            b"/Encoding /WinAnsiEncoding >>"
        )

        for index, page in enumerate(self._pages):
            page_id = page_ids[index]
            stream_id = page_id + 1
            objects[page_id] = (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
                + f"{PAGE_WIDTH} {PAGE_HEIGHT}".encode()
                + b"] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents "
                + f"{stream_id} 0 R".encode()
                + b" >>"
            )
            body = b"\n".join(page.operators)
            objects[stream_id] = (
                b"<< /Length " + str(len(body)).encode() + b" >>\nstream\n" + body + b"\nendstream"
            )

        out = bytearray(b"%PDF-1.4\n")
        # A comment of high bytes, as the spec recommends, so a tool transferring the file in text
        # mode is detectable rather than silently corrupting it.
        out += b"%\xe2\xe3\xcf\xd3\n"

        offsets: dict[int, int] = {}
        for number in sorted(objects):
            offsets[number] = len(out)
            out += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"

        xref_at = len(out)
        count = max(objects) + 1
        out += f"xref\n0 {count}\n".encode()
        out += b"0000000000 65535 f \n"
        for number in range(1, count):
            out += f"{offsets[number]:010d} 00000 n \n".encode()
        out += (
            b"trailer\n<< /Size " + str(count).encode() + b" /Root 1 0 R >>\nstartxref\n"
            + str(xref_at).encode()
            + b"\n%%EOF\n"
        )
        return bytes(out)


# ==============================================================================================
# the report
# ==============================================================================================


def _euro(value: Decimal | None) -> str:
    """`1.234,56 €`, German conventions. `Decimal` in, string out, never a float.

    The report is the one place these numbers are typeset for a human, and the formatting is done
    from the `Decimal` the API carries rather than from a parsed float for the same reason the API
    ships them as strings: a cent that disappears into binary floating point is a cent a
    Rechnungsprüfer will find.
    """
    if value is None:
        return "—"
    quantised = Decimal(value).quantize(Decimal("0.01"))
    whole, _, fraction = f"{abs(quantised):.2f}".partition(".")
    grouped = f"{int(whole):,}".replace(",", ".")
    sign = "-" if quantised < 0 else ""
    return f"{sign}{grouped},{fraction} €"


def _stamp(moment: datetime | None) -> str:
    return moment.strftime("%d.%m.%Y %H:%M UTC") if moment else "—"


def _coverage_sentence(job: BatchAuditJob, summary: BatchAggregateSummary) -> str:
    """Why this report could not judge everything — **counted, never asserted**.

    This paragraph is the most consequential prose the product emits. It is printed on a document a
    billing centre may hand to a payer, and it is the sentence that decides whether »nicht
    beurteilbar« is read as "we could not check this" or as "we suspect this". Getting it wrong in
    the second direction manufactures an accusation out of our own gap.

    It used to be a fixed string claiming that most machine-extracted exclusion rules were still
    unconfirmed and therefore not applied. That was true when it was written and is now false —
    verification has since promoted almost all of them — so every PDF produced after that work
    understated the engine on its own front page. A hardcoded number in a rendered artefact is a
    claim with no mechanism to stay true, and this one had already stopped being true without
    anything failing.

    So the numbers come from the report being rendered. Two facts, and they are deliberately
    different in kind:

    * **How much of the rule set is enforced** — a property of the engine, the same on every
      report, read from `rule_coverage_detail`.
    * **How many of *these* positions no verified rule reached** — a property of this invoice,
      which is what actually produced the amber bucket in front of the reader.

    The second is the honest explanation and the first is the context for it. Stating only the
    first would invite the reader to conclude that a high enforcement figure means a thorough
    audit; they measure different things, and the gap between them is catalog reach.
    """
    detail = next(
        (entry.report.rule_coverage_detail for entry in job.files if entry.report is not None),
        None,
    )
    first = next((entry.report for entry in job.files if entry.report is not None), None)

    parts: list[str] = []
    if detail is not None and detail.total_constraint_rule_count:
        parts.append(
            f"Von {detail.total_constraint_rule_count} hinterlegten Regeln waren bei dieser "
            f"Prüfung {detail.enforced_rule_count} durchgesetzt"
        )
        if detail.suppressed_unverified_rule_count:
            parts.append(
                f", {detail.suppressed_unverified_rule_count} weitere sind noch nicht von einer "
                "Abrechnungsfachkraft bestätigt und werden deshalb nicht angewendet"
            )
        parts.append(". ")
    elif first is not None:
        parts.append(
            f"Bei dieser Prüfung waren {first.enforced_rule_count} Regeln durchgesetzt und "
            f"{first.advisory_rule_count} nur beratend. "
        )

    if summary.position_count and summary.unconfirmed_positions:
        parts.append(
            f"Für {summary.unconfirmed_positions} der {summary.position_count} abgerechneten "
            "Positionen greift keine verifizierte Regel: der hinterlegte Regelsatz deckt diese "
            "Ziffern noch nicht ab. Was hier fehlt, ist also die Reichweite der Regeln über den "
            "Gebührenkatalog, nicht das Vertrauen in die Regeln selbst."
        )
    elif summary.position_count:
        parts.append(
            f"Für alle {summary.position_count} abgerechneten Positionen konnte eine verifizierte "
            "Regel herangezogen werden."
        )

    return "".join(parts).strip()


def render_batch_report(job: BatchAuditJob, *, organization_id: str) -> bytes:
    """A completed job as a Prüfbericht, ready to hand a Rechnungsprüfer.

    The document says three things, in this order, and the order is the argument:

    1. **What was checked** — how many deliveries, when, under which catalog and rule set. A report
       that cannot state the engine state it was produced under is not evidence of anything, which
       is why the identity block is on the first page rather than in a footnote.
    2. **The three buckets, never merged.** The same refusal `BatchAggregateSummary` makes, carried
       into print, where it matters more: a PDF outlives the screen it came from and will be read
       by somebody who was not told what `unconfirmed` means. So it is spelled out in a paragraph
       beside the number rather than in a legend.
    3. **The per-delivery table**, riskiest first — which is the order `load_batch` already sorted
       `files` into, so this renders the engine's ordering rather than inventing a second one.

    Takes the `BatchAuditJob` the API returns rather than the ORM rows, deliberately: the printed
    document and the JSON a client parses are then two renderings of one object, and they cannot
    come to disagree about a total.
    """
    summary = job.aggregate_summary
    canvas = PdfCanvas(title=f"Prüfbericht {job.batch_id}")

    canvas.text("Azmoth — GOÄ-Prüfbericht", size=17, bold=True, leading=24)
    canvas.text(
        "Systematische Prüfung einer PADnext-Lieferung gegen die GOÄ", size=10, leading=18
    )
    canvas.rule(thickness=1)
    canvas.space(4)

    canvas.row([(0, "Auftrag"), (110, job.batch_id)], bold=False)
    canvas.row([(0, "Organisation"), (110, organization_id)])
    canvas.row([(0, "Eingegangen"), (110, _stamp(job.created_at))])
    canvas.row([(0, "Abgeschlossen"), (110, _stamp(job.completed_at))])
    canvas.row(
        [
            (0, "Lieferungen"),
            (
                110,
                f"{job.file_count} gesamt · {job.completed_file_count} geprüft · "
                f"{job.failed_file_count} nicht lesbar",
            ),
        ]
    )
    canvas.space(10)

    if summary is None:
        # A job with no roll-up should not reach here — the endpoint refuses anything that is not
        # COMPLETED — so this is the belt-and-braces branch. It prints the absence rather than
        # zeros, because a page of €0,00 is a document somebody could reconcile against.
        canvas.text("Kein Ergebnis", size=12, bold=True)
        canvas.paragraph(
            "Für diesen Auftrag liegt keine Auswertung vor. Es werden bewusst keine Zahlen "
            "gedruckt: eine Aufstellung mit Nullwerten wäre von einem geprüften Nullbetrag nicht "
            "zu unterscheiden."
        )
        return canvas.render()

    canvas.text("Ergebnis nach Belegbarkeit", size=12, bold=True, leading=18)
    canvas.row(
        [(0, "Bewertung"), (250, "Positionen"), (330, "Betrag"), (450, "Anteil")], bold=True
    )
    canvas.rule()

    claimed = summary.claimed_total_eur or Decimal("0.00")

    def share(value: Decimal) -> str:
        if not claimed:
            return "—"
        return f"{(Decimal(value) / claimed * 100):.1f} %".replace(".", ",")

    canvas.row(
        [
            (0, "Belegbar korrekt"),
            (250, str(summary.confirmed_fine_positions)),
            (330, _euro(summary.confirmed_fine_eur)),
            (450, share(summary.confirmed_fine_eur)),
        ]
    )
    canvas.row(
        [
            (0, "Belegbar nicht abrechenbar"),
            (250, str(summary.confirmed_wrong_positions)),
            (330, _euro(summary.confirmed_wrong_eur)),
            (450, share(summary.confirmed_wrong_eur)),
        ]
    )
    canvas.row(
        [
            (0, "Nicht beurteilbar"),
            (250, str(summary.unconfirmed_positions)),
            (330, _euro(summary.unconfirmed_eur)),
            (450, share(summary.unconfirmed_eur)),
        ]
    )
    canvas.rule()
    canvas.row(
        [
            (0, "Abgerechnet gesamt"),
            (250, str(summary.position_count)),
            (330, _euro(summary.claimed_total_eur)),
            (450, "100,0 %"),
        ],
        bold=True,
    )
    canvas.space(6)
    canvas.text(
        f"Prüfabdeckung: {summary.coverage_ratio * 100:.1f} % der abgerechneten Summe".replace(
            ".", ","
        ),
        size=9,
        bold=True,
    )
    canvas.space(8)

    canvas.paragraph(
        "Zur Lesart. »Belegbar nicht abrechenbar« ist der einzige Betrag, der als Rückforderung "
        "gelesen werden darf: hier hat eine verifizierte Regel die Position beanstandet. "
        "»Nicht beurteilbar« ist ausdrücklich KEIN Befund gegen die Praxis — es ist die Grenze der "
        "Regelabdeckung dieser Engine. " + _coverage_sentence(job, summary) + " Die drei Beträge "
        "werden nie zu einer Summe »Risiko« zusammengefasst, weil genau diese Zusammenfassung aus "
        "einer Abdeckungslücke eine Anschuldigung machen würde."
    )
    canvas.space(4)
    canvas.paragraph(
        "Auch »belegbar nicht abrechenbar« ist kein festgestellter Rückforderungsbetrag: bei zwei "
        "sich gegenseitig ausschliessenden Positionen zählen beide hinein, weil die Engine nicht "
        "errät, welche die Praxis behalten wollte. Die Rechnung ist in beiden Fällen zu "
        "korrigieren, der tatsächlich strittige Betrag ist jedoch geringer."
    )
    canvas.space(10)

    canvas.text("Lieferungen im Einzelnen", size=12, bold=True, leading=16)
    canvas.paragraph(
        "Sortiert nach belegbar nicht abrechenbarem Betrag, absteigend.", size=8
    )
    canvas.space(2)
    canvas.row(
        [(0, "Datei"), (250, "Status"), (310, "Abgerechnet"), (400, "Nicht abrechenbar")],
        bold=True,
    )
    canvas.rule()

    for entry in job.files:
        report = entry.report
        name = entry.filename if len(entry.filename) <= 46 else entry.filename[:43] + "..."
        if report is None:
            canvas.row(
                [
                    (0, name),
                    (250, "fehlgeschlagen" if entry.status == BatchFileStatus.FAILED else "offen"),
                    (310, "—"),
                    (400, "—"),
                ]
            )
            if entry.error_message:
                canvas.paragraph(entry.error_message, size=7.5, indent=10)
            continue
        canvas.row(
            [
                (0, name),
                (250, "geprüft"),
                (310, _euro(report.claimed_total_eur)),
                (400, _euro(report.confirmed_wrong_eur)),
            ]
        )

    canvas.space(12)
    canvas.rule()
    canvas.text("Prüfgrundlage", size=10, bold=True, leading=14)

    first = next((entry.report for entry in job.files if entry.report is not None), None)
    if first is not None:
        canvas.row([(0, "Katalog"), (110, first.catalog_version)], size=8)
        canvas.row([(0, "Katalog-SHA-256"), (110, first.catalog_sha256[:32] + "…")], size=8)
        canvas.row([(0, "Regelstand"), (110, first.rules_version[:32] + "…")], size=8)
        canvas.row([(0, "Logikstand"), (110, first.logic_version[:32] + "…")], size=8)
        canvas.row(
            [
                (0, "Regelabdeckung"),
                (
                    110,
                    f"{first.enforced_rule_count} durchgesetzt · "
                    f"{first.advisory_rule_count} hinweisend · "
                    f"{first.suppressed_unverified_rule_count} unbestätigt und unterdrückt",
                ),
            ],
            size=8,
        )
    canvas.space(6)
    canvas.paragraph(
        "Dieser Bericht ist eine maschinelle Prüfung und ersetzt keine ärztliche oder "
        "abrechnungsfachliche Entscheidung. Die Verantwortung für die Rechnung bleibt beim "
        "Rechnungssteller.",
        size=7.5,
    )

    return canvas.render()


__all__ = [
    "PAGE_HEIGHT",
    "PAGE_WIDTH",
    "PdfCanvas",
    "render_batch_report",
    "wrap",
]
