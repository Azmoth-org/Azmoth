"""A PDF writer, and the audit report rendered through it.

**Why there is no library here.** Every dependency in `requirements.txt` is pinned with a reason
written beside it, because the receipt hash records what produced an answer and an unpinned bump
would silently change what a receipt means. Adding ReportLab or WeasyPrint to render a table of
numbers would be the largest dependency in the file — WeasyPrint pulls a browser layout engine and
Cairo — to typeset text this service already holds as strings. So the subset of PDF that draws
Helvetica in a grid is implemented here, with no C extension, no fonts to ship and nothing to keep
up to date.

**What that subset is, and what it is not.** PDF 1.4, the fourteen standard fonts (so no font is
embedded), `WinAnsiEncoding`, single-column text, filled rectangles and straight rules — no images,
no curves, no charts. That is exactly enough for a Prüfbericht and is not enough for anything with
a real layout. If this ever needs a chart or a raster logo, that is the moment to take the
dependency — not before. The wordmark at the top of the report is set in type for the same reason.

**Text is measured, not estimated.** `app.services.pdf_metrics` holds the Helvetica advance widths,
so `wrap`, `fit` and every right-aligned amount ask how wide a string actually is. That is what lets
the Betrag column line up on its last digit and a 500-character GOÄ description break at the column
edge instead of over it.

**The output is deterministic: same input, same bytes.** No object id depends on a dict's iteration
order, and there is no hidden clock — the only wall-clock in the document is `generated_at`, which
is a *parameter*. Pass none and two renders are byte-identical, which is what `POST /demo/report.pdf`
does and what its test asserts. Pass one and it appears both in the header and in `/Info
/CreationDate`, and the same value renders the same bytes. So determinism is stated precisely:
identical inputs, including the stamp, produce an identical document.

**Encoding is cp1252, not UTF-8.** `WinAnsiEncoding` *is* cp1252, so the two agree byte for byte
over everything a German billing report contains, including `ä`, `ß` and `€` (which Latin-1, often
reached for instead, does not have). A character outside it becomes `?` rather than a broken glyph
or an exception — a report that fails to render because one practice's name has a Cyrillic letter
in it would be a worse failure than a substituted character.

**Nothing in the document depends on colour.** Emphasis is weight, rule thickness and grey level,
and the greys are chosen to stay distinct on a monochrome laser printer, because a Prüfbericht is
read on paper. There is no red bucket and no green bucket: the three buckets are told apart by
their labels, which is the only encoding that survives a fax.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, NamedTuple

from app.schemas.batch import BatchAggregateSummary, BatchAuditJob, BatchFileStatus
from app.schemas.padnext import PadnextAuditReport, PadnextFinding

from app.services.pdf_metrics import text_width

log = logging.getLogger(__name__)

# ==============================================================================================
# geometry
# ==============================================================================================

#: A4 in PostScript points (1/72 inch), which is the only unit PDF has. 595 × 842 pt is
#: 209.9 × 297.0 mm — A4 to within a tenth of a millimetre, and the integer both keeps the
#: arithmetic exact and matches what every reader reports for a nominal A4 page.
PAGE_WIDTH = 595
PAGE_HEIGHT = 842

#: 56 pt is 19.8 mm — the 20 mm margin a German business document is set with, to the nearest
#: point. Every offset in this module is relative to it, so changing it moves the whole block.
MARGIN = 56

#: The text column: 483 pt. Every table's columns must sum to this or narrower.
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

#: Where the running footer sits, and where content must therefore stop. The gap between `BOTTOM`
#: and `FOOTER_BASELINE` is what keeps a last line from colliding with the page number.
FOOTER_BASELINE = 34.0
BOTTOM = MARGIN + 12.0

#: Page one starts under the margin; every later page starts below a running header that repeats
#: the document's identity, so a page separated from its fellows still says what it belongs to.
TOP = PAGE_HEIGHT - MARGIN
CONTINUATION_HEADER_HEIGHT = 22.0

#: The fourteen standard fonts need no embedding, and these two are the only ones used.
FONT_REGULAR = "F1"
FONT_BOLD = "F2"

# The type scale. Stated once, used everywhere, so "make the report a point larger" is one edit.
#
# The brief asked for a 12 pt body. It is not set here and the reason is arithmetic rather than
# taste: the position table carries five columns across 483 pt, and its widest column — the GOÄ
# Leistungstext — needs about 40 characters to be worth printing. At 12 pt Helvetica that is
# roughly 250 pt for that column alone and about 700 pt for the row, which does not fit on A4 in
# portrait. So prose is set at 10 pt, which is the size a German Geschäftsbrief uses and is
# comfortably readable in print, and tabular matter at 9 pt. Headings carry the requested scale.
SIZE_TITLE = 18.0
SIZE_SECTION = 14.0
SIZE_SUBSECTION = 11.0
SIZE_BODY = 10.0
SIZE_TABLE = 9.0
SIZE_SMALL = 8.0
SIZE_FOOTER = 7.5

#: Grey levels, in PDF's `g` operator space where 0 is black and 1 is white. Chosen so each stays
#: distinguishable from its neighbours after a monochrome laser print — the medium a Prüfbericht is
#: actually read on.
GREY_TEXT = 0.0
GREY_MUTED = 0.38
GREY_RULE = 0.55
GREY_BAND = 0.90
GREY_ZEBRA = 0.965

Align = Literal["left", "right", "center"]


# ==============================================================================================
# the writer
# ==============================================================================================


def _escape(text: str) -> bytes:
    r"""One PDF literal string's payload: cp1252 bytes with `\`, `(` and `)` escaped.

    The escaping has to happen after the encode, not before, or a multi-byte sequence could be
    mistaken for a parenthesis. cp1252 is single-byte, so in practice the order does not bite —
    doing it in the safe order anyway costs nothing and survives somebody changing the encoding.
    """
    raw = text.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def wrap(text: str, *, size: float, width: float, bold: bool = False) -> list[str]:
    """Break a paragraph into lines no wider than `width` points.

    Measured against the real Helvetica advance widths rather than an average, so a line of capitals
    and a line of `i`s both stop at the column edge instead of one overflowing and the other
    stopping early. A single word longer than the column — a 40-character compound noun, or a hash
    — is broken mid-word rather than allowed to run into the neighbouring column, because in this
    document the neighbouring column is a euro amount.
    """
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if text_width(candidate, size=size, bold=bold) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        # A word that cannot fit a column of its own has to be cut, or it overprints the next one.
        while text_width(word, size=size, bold=bold) > width and len(word) > 1:
            cut = len(word)
            while cut > 1 and text_width(word[:cut], size=size, bold=bold) > width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines or [""]


def fit(text: str, *, size: float, width: float, bold: bool = False) -> str:
    """`text`, shortened with an ellipsis until it fits `width`. For single-line table cells.

    Used where a value must stay on one line — a Ziffer's official text in the position table, a
    filename in the delivery table. The ellipsis is the cp1252 `…`, one character, so the truncation
    is visible to a reader and to a text extractor rather than looking like the catalogue itself
    stops there.
    """
    if text_width(text, size=size, bold=bold) <= width:
        return text
    ellipsis = "…"
    budget = width - text_width(ellipsis, size=size, bold=bold)
    if budget <= 0:
        return ellipsis
    cut = len(text)
    while cut > 0 and text_width(text[:cut], size=size, bold=bold) > budget:
        cut -= 1
    return text[:cut].rstrip() + ellipsis


def _text_string(value: str) -> bytes:
    """A PDF *text string* — the type `/Info` entries and outlines use, which is not WinAnsi.

    This is a different type from the strings drawn on a page, and confusing the two is a bug that
    only shows up in a reader's properties dialogue. A literal string in `/Info` is interpreted as
    **PDFDocEncoding**, which agrees with Latin-1 over most of the upper range but not over
    0x80–0x9F: the em dash this report's title contains is 0x97 in cp1252 and a `Š` in
    PDFDocEncoding, so `GOÄ-Prüfbericht — Datei.xml` arrived in Acrobat as
    `GOÄ-Prüfbericht Š Datei.xml`. The `Ä` survived and the dash did not, which is exactly the kind
    of half-working that goes unnoticed.

    The fix the spec provides is a UTF-16BE string with a byte order mark, written here in hex form
    so there is nothing to escape. Pure ASCII is left as a literal, because it is unambiguous in
    both encodings and keeps the file readable to anyone inspecting it with `less`.
    """
    if value.isascii():
        return b"(" + _escape(value) + b")"
    return b"<" + (b"\xfe\xff" + value.encode("utf-16-be")).hex().encode("ascii") + b">"


class Cell(NamedTuple):
    """One table cell. A bare `(x, text)` pair is still valid, which is what most callers pass."""

    x: float
    text: str
    #: Only consulted for `right` and `center`; a left-aligned cell needs no column width.
    width: float = 0.0
    align: Align = "left"
    bold: bool | None = None
    grey: float | None = None


@dataclass(frozen=True)
class Column:
    """A column in a repeating table: where it starts, how wide it is, how its cells align."""

    label: str
    x: float
    width: float
    align: Align = "left"


@dataclass
class _Page:
    """One page's content stream, accumulated as PDF operators."""

    operators: list[bytes] = field(default_factory=list)


class PdfCanvas:
    """Draw text, rules and bands onto pages, then serialise the whole document.

    Stateful and single-use: `y` walks down the page and a write that would cross `BOTTOM` starts a
    new one. That is the entire layout model, and it is enough because every element in this report
    is a full-width row placed under the previous one.

    Three things sit on top of that model and exist because a printed financial document needs
    them:

    * **`reserve`** — refuse to leave a heading, or the first row of a table, stranded alone at the
      foot of a page. The caller measures the block it is about to draw and asks for that much room.
    * **`on_new_page`** — a hook a `Table` installs so its header row is redrawn after a break. A
      column of numbers whose headings are three pages back is a column nobody can read.
    * **the deferred footer** — page numbers cannot be written while drawing, because "von wie
      viel" is not known until the last page exists. So the footer is composed in `render`, when
      the count is final.
    """

    def __init__(
        self,
        *,
        title: str,
        subject: str = "GOÄ-Prüfbericht",
        report_id: str = "",
        generated_at: datetime | None = None,
        footer_note: str = "",
        keywords: str = "",
    ) -> None:
        self.title = title
        self.subject = subject
        self.report_id = report_id
        self.generated_at = generated_at
        self.footer_note = footer_note
        self.keywords = keywords
        self._pages: list[_Page] = []
        self._page: _Page | None = None
        self.y = 0.0
        self._on_new_page: Callable[[], None] | None = None
        self._repeating = False
        self.new_page()

    # -- page management -------------------------------------------------------------------

    def new_page(self) -> None:
        first = not self._pages
        self._page = _Page()
        self._pages.append(self._page)
        self.y = TOP if first else TOP - CONTINUATION_HEADER_HEIGHT
        if not first and self._on_new_page and not self._repeating:
            # Guarded because the hook draws rows, and a row that did not fit would otherwise
            # recurse straight back into here.
            self._repeating = True
            try:
                self._on_new_page()
            finally:
                self._repeating = False

    def on_new_page(self, hook: Callable[[], None] | None) -> None:
        """Install (or clear) what should be redrawn at the top of every continuation page."""
        self._on_new_page = hook

    def _ensure(self, needed: float) -> None:
        if self.y - needed < BOTTOM:
            self.new_page()

    def reserve(self, needed: float) -> None:
        """Break to a new page now if `needed` points do not remain. Keeps a block together."""
        if self.y - needed < BOTTOM:
            self.new_page()

    @property
    def page_count(self) -> int:
        return len(self._pages)

    def _emit(self, operator: bytes) -> None:
        assert self._page is not None
        self._page.operators.append(operator)

    # -- drawing ---------------------------------------------------------------------------

    @staticmethod
    def _place(text: str, *, x: float, width: float, align: Align, size: float, bold: bool) -> float:
        """The x at which to start drawing so that `text` sits `align`-ed in its column."""
        if align == "left" or width <= 0:
            return MARGIN + x
        measured = text_width(text, size=size, bold=bold)
        if align == "right":
            return MARGIN + x + width - measured
        return MARGIN + x + (width - measured) / 2

    def _show(
        self,
        value: str,
        *,
        x: float,
        y: float,
        size: float,
        bold: bool,
        align: Align = "left",
        width: float = 0.0,
        grey: float = GREY_TEXT,
    ) -> None:
        """One run of text at an absolute position. The only operator that draws glyphs."""
        font = FONT_BOLD if bold else FONT_REGULAR
        left = self._place(value, x=x, width=width, align=align, size=size, bold=bold)
        prefix = b"" if grey == GREY_TEXT else f"{grey:g} g ".encode()
        suffix = b"" if grey == GREY_TEXT else b" 0 g"
        self._emit(
            prefix
            + b"BT /"
            + font.encode()
            + f" {size:g} Tf 1 0 0 1 {left:.2f} {y:.2f} Tm (".encode()
            + _escape(value)
            + b") Tj ET"
            + suffix
        )

    def text(
        self,
        value: str,
        *,
        x: float = 0.0,
        size: float = SIZE_BODY,
        bold: bool = False,
        leading: float | None = None,
        align: Align = "left",
        width: float = 0.0,
        grey: float = GREY_TEXT,
    ) -> None:
        """One line, at the current vertical position. Advances past it."""
        step = leading if leading is not None else size + 3.5
        self._ensure(step)
        self._show(value, x=x, y=self.y, size=size, bold=bold, align=align, width=width, grey=grey)
        self.y -= step

    def paragraph(
        self,
        value: str,
        *,
        size: float = SIZE_SMALL,
        indent: float = 0.0,
        width: float | None = None,
        bold: bool = False,
        grey: float = GREY_TEXT,
        leading: float | None = None,
    ) -> None:
        """A wrapped block of prose. The caveats in this report are paragraphs, not table cells."""
        column = CONTENT_WIDTH - indent if width is None else width
        for line in wrap(value, size=size, width=column, bold=bold):
            self.text(line, x=indent, size=size, bold=bold, grey=grey, leading=leading)

    def measure_paragraph(
        self, value: str, *, size: float = SIZE_SMALL, indent: float = 0.0,
        width: float | None = None, leading: float | None = None, bold: bool = False,
    ) -> float:
        """How tall `paragraph` would draw `value`. For `reserve`, so a block is not split."""
        column = CONTENT_WIDTH - indent if width is None else width
        step = leading if leading is not None else size + 3.5
        return len(wrap(value, size=size, width=column, bold=bold)) * step

    def row(
        self,
        cells: Sequence[Cell | tuple[float, str]],
        *,
        size: float = SIZE_TABLE,
        bold: bool = False,
        grey: float = GREY_TEXT,
        band: float | None = None,
        leading: float | None = None,
    ) -> None:
        """One table row: cells on a shared baseline, optionally over a filled band.

        Columns are absolute offsets rather than a computed grid, because the tables here have
        fixed shapes decided at authoring time and a column solver would be a layout engine — the
        thing this module exists not to be. What *is* computed is alignment within a column, which
        needs only the width the caller already knows.
        """
        step = leading if leading is not None else size + 5.0
        self._ensure(step)
        if band is not None:
            # Drawn before the text so the glyphs land on top of the fill.
            self._emit(
                f"{band:g} g {MARGIN:g} {self.y - 3.5:.2f} {CONTENT_WIDTH:g} "
                f"{step:.2f} re f 0 g".encode()
            )
        for cell in cells:
            item = cell if isinstance(cell, Cell) else Cell(cell[0], cell[1])
            self._show(
                item.text,
                x=item.x,
                y=self.y,
                size=size,
                bold=bold if item.bold is None else item.bold,
                align=item.align,
                width=item.width,
                grey=grey if item.grey is None else item.grey,
            )
        self.y -= step

    def rule(self, *, thickness: float = 0.5, grey: float = GREY_RULE, x: float = 0.0,
             width: float | None = None) -> None:
        """A horizontal line across the text column."""
        self._ensure(6)
        span = CONTENT_WIDTH - x if width is None else width
        self._emit(
            f"{grey:g} G {thickness:g} w {MARGIN + x:g} {self.y + 3:.2f} m "
            f"{MARGIN + x + span:g} {self.y + 3:.2f} l S 0 G".encode()
        )
        self.y -= 6

    def space(self, points: float = 8) -> None:
        self._ensure(points)
        self.y -= points

    def table(self, columns: Sequence[Column], *, size: float = SIZE_TABLE) -> Table:
        return Table(self, columns, size=size)

    # -- serialisation ---------------------------------------------------------------------

    def _footer_operators(self, index: int) -> list[bytes]:
        """The running footer for page `index`, composed once the page count is known.

        Every page carries the same three facts: who produced the document, which report it is, and
        where this page sits in the whole. The third is why this cannot be drawn while laying out —
        "Seite 3 von 7" is unknowable until page 7 exists — and the first two are here rather than
        in a block at the end because a page that gets separated from the rest is exactly the page
        that needs to say what it belongs to.
        """
        left = self.footer_note or "Erstellt von Azmoth — deterministische GOÄ-Prüfengine"
        if self.report_id:
            left = f"{left} · Bericht-ID {self.report_id[:16]}"
        right = f"Seite {index + 1} von {len(self._pages)}"

        operators = [
            f"{GREY_RULE:g} G 0.5 w {MARGIN:g} {FOOTER_BASELINE + 11:g} m "
            f"{PAGE_WIDTH - MARGIN:g} {FOOTER_BASELINE + 11:g} l S 0 G".encode()
        ]
        for value, align in ((left, "left"), (right, "right")):
            start = self._place(
                value,
                x=0.0,
                width=CONTENT_WIDTH,
                align=align,  # type: ignore[arg-type]
                size=SIZE_FOOTER,
                bold=False,
            )
            operators.append(
                f"{GREY_MUTED:g} g BT /{FONT_REGULAR} {SIZE_FOOTER:g} Tf 1 0 0 1 "
                f"{start:.2f} {FOOTER_BASELINE:g} Tm (".encode()
                + _escape(value)
                + b") Tj ET 0 g"
            )
        return operators

    def _continuation_header_operators(self) -> list[bytes]:
        """The strip at the top of every page after the first: title left, subject right."""
        baseline = TOP - 4
        operators: list[bytes] = []
        for value, align, bold in ((self.title, "left", True), (self.subject, "right", False)):
            if not value:
                continue
            start = self._place(
                value,
                x=0.0,
                width=CONTENT_WIDTH,
                align=align,  # type: ignore[arg-type]
                size=SIZE_FOOTER,
                bold=bold,
            )
            font = FONT_BOLD if bold else FONT_REGULAR
            operators.append(
                f"{GREY_MUTED:g} g BT /{font} {SIZE_FOOTER:g} Tf 1 0 0 1 "
                f"{start:.2f} {baseline:.2f} Tm (".encode()
                + _escape(value)
                + b") Tj ET 0 g"
            )
        operators.append(
            f"{GREY_RULE:g} G 0.5 w {MARGIN:g} {baseline - 5:.2f} m "
            f"{PAGE_WIDTH - MARGIN:g} {baseline - 5:.2f} l S 0 G".encode()
        )
        return operators

    def _info_object(self) -> bytes:
        """`/Info`: what a reader shows in its title bar and what an archive indexes on.

        Filled in because a Prüfbericht gets filed. A document whose properties dialogue is blank
        is one a Dokumentenmanagementsystem can only index by filename, and the filename is the
        first thing that changes when somebody moves it into a client folder.

        `/CreationDate` is written only when the caller supplied `generated_at`, which is the whole
        of this module's clock. Omitting it is what keeps two renders of the same demo delivery
        byte-identical.
        """
        entries: list[tuple[str, str]] = [
            ("Title", self.title),
            ("Author", "Azmoth"),
            ("Subject", self.subject),
            ("Creator", "Azmoth GOÄ-Prüfengine"),
            ("Producer", "Azmoth PDF-Writer"),
        ]
        if self.keywords:
            entries.append(("Keywords", self.keywords))
        out = bytearray(b"<<")
        for key, value in entries:
            out += b" /" + key.encode() + b" " + _text_string(value)
        if self.generated_at is not None:
            # Dates stay ASCII literals: `/CreationDate` is parsed as a date, not displayed as
            # text, and a reader that meets a UTF-16 one may decline to parse it at all.
            stamp = _pdf_date(self.generated_at).encode("ascii")
            out += b" /CreationDate (" + stamp + b")"
            out += b" /ModDate (" + stamp + b")"
        out += b" >>"
        return bytes(out)

    def render(self) -> bytes:
        """The complete PDF.

        Object numbering is fixed rather than allocated: 1 catalogue, 2 page tree, 3 and 4 the two
        fonts, 5 the document information dictionary, then a page and a content stream per page.
        Fixed because it makes the cross-reference table computable in one pass and the output
        byte-identical for identical input — an allocator keyed on insertion order would be the one
        place non-determinism could creep in.
        """
        objects: dict[int, bytes] = {}
        page_ids = [6 + 2 * index for index in range(len(self._pages))]

        objects[1] = (
            b"<< /Type /Catalog /Pages 2 0 R /Lang (de-DE) "
            # So a reader's window title says "GOÄ-Prüfbericht …" rather than the filename, which
            # is the one piece of provenance that survives being emailed on.
            b"/ViewerPreferences << /DisplayDocTitle true >> >>"
        )
        kids = b" ".join(f"{page_id} 0 R".encode() for page_id in page_ids)
        objects[2] = (
            b"<< /Type /Pages /Count " + str(len(page_ids)).encode() + b" /Kids [" + kids + b"] >>"
        )
        objects[3] = (
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
        )
        objects[4] = (
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
            b"/Encoding /WinAnsiEncoding >>"
        )
        objects[5] = self._info_object()

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
            operators = list(page.operators)
            if index:
                operators = self._continuation_header_operators() + operators
            operators += self._footer_operators(index)
            body = b"\n".join(operators)
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
            b"trailer\n<< /Size " + str(count).encode() + b" /Root 1 0 R /Info 5 0 R >>\nstartxref\n"
            + str(xref_at).encode()
            + b"\n%%EOF\n"
        )
        return bytes(out)


class Table:
    """A table whose header row comes back at the top of every page it spills onto.

    The failure this prevents is specific and was reachable in the old renderer: a batch of two
    hundred deliveries, or an invoice of a hundred positions, produced pages two onward that were
    columns of unlabelled euro amounts. On screen that is recoverable by scrolling up. On paper —
    which is where this document is read — it is not.

    Use it as a context manager; leaving the block clears the hook so the *next* section does not
    inherit this table's heading.
    """

    def __init__(self, canvas: PdfCanvas, columns: Sequence[Column], *, size: float = SIZE_TABLE):
        self.canvas = canvas
        self.columns = list(columns)
        self.size = size

    def __enter__(self) -> Table:
        self.head()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def head(self) -> None:
        """Draw the header row, and arrange for it to be drawn again after every page break."""
        self._draw_head()
        self.canvas.on_new_page(self._draw_head)

    def _draw_head(self) -> None:
        self.canvas.row(
            [
                Cell(column.x, column.label, column.width, column.align)
                for column in self.columns
            ],
            size=self.size,
            bold=True,
            band=GREY_BAND,
        )

    def row(
        self,
        values: Sequence[str] | Mapping[str, str],
        *,
        bold: bool = False,
        grey: float = GREY_TEXT,
        band: float | None = None,
    ) -> None:
        texts = (
            [values[column.label] for column in self.columns]
            if isinstance(values, Mapping)
            else list(values)
        )
        self.canvas.row(
            [
                Cell(column.x, text, column.width, column.align)
                for column, text in zip(self.columns, texts, strict=False)
            ],
            size=self.size,
            bold=bold,
            grey=grey,
            band=band,
        )

    def close(self) -> None:
        self.canvas.on_new_page(None)


# ==============================================================================================
# formatting
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


def _percent(value: float | Decimal) -> str:
    """`44,8 %` — one decimal, German comma, the non-breaking-space-free form a printer handles."""
    return f"{float(value):.1f} %".replace(".", ",")


def _factor(value: Decimal | None) -> str:
    """A GOÄ Steigerungsfaktor: `2,3`. Two decimals only when the second one carries information."""
    if value is None:
        return "—"
    quantised = Decimal(value).normalize()
    text = f"{quantised:f}"
    if "." not in text:
        text += ".0"
    return text.replace(".", ",")


def _stamp(moment: datetime | None) -> str:
    """`31.08.2026 14:05 UTC` — the German order, with the zone named rather than assumed.

    The zone is printed because this is an archival document read months later, possibly in another
    country, and `14:05` with no zone is a timestamp that cannot be reconciled against a server log.
    A naive datetime is labelled UTC, which is what the engine stores.
    """
    if moment is None:
        return "—"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    name = moment.tzname() or "UTC"
    return f"{moment.strftime('%d.%m.%Y %H:%M')} {name}"


def _pdf_date(moment: datetime) -> str:
    """A `/CreationDate` in PDF's own `D:YYYYMMDDHHmmSSOHH'mm'` form."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    stamp = moment.strftime("D:%Y%m%d%H%M%S")
    offset = moment.utcoffset()
    if offset is None or offset.total_seconds() == 0:
        return stamp + "Z"
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{stamp}{sign}{total // 3600:02d}'{(total % 3600) // 60:02d}'"


# ==============================================================================================
# shared blocks — every report is built from these, so the two cannot drift apart
# ==============================================================================================

#: The mandated wording. A constant rather than a literal at each call site, because it is the
#: sentence that decides what this document is in law, and two copies of it would eventually be
#: one copy and one paraphrase.
DISCLAIMER = (
    "Dieser Bericht ist ein Abrechnungsvorschlag (Entwurf) gemäß GOÄ und keine Rechnung. Die "
    "ärztliche Prüfung und Freigabe ist zwingend erforderlich. Azmoth übernimmt keine Haftung "
    "für abweichende fachliche Entscheidungen."
)

DATA_PROTECTION = (
    "Verarbeitet nach DSGVO-konformen Richtlinien. Der Bericht enthält keine Patientendaten: "
    "Name, Anschrift und Geburtsdatum werden von dieser Engine nicht eingelesen und können daher "
    "hier nicht erscheinen."
)

CONTACT = "kontakt@azmoth.com"

#: The three buckets, in the order a reader must meet them, with the label each is printed under.
#: One mapping, used by both reports, so a bucket cannot be called one thing in a single report and
#: another in a batch.
_BUCKET_ORDER = {"confirmed_wrong": 0, "unconfirmed": 1, "confirmed_fine": 2}

_BUCKET_LABEL = {
    "confirmed_wrong": "Belegbar nicht abrechenbar",
    "unconfirmed": "Nicht beurteilbar",
    "confirmed_fine": "Belegbar korrekt",
}

_SEVERITY_LABEL = {"error": "Fehler", "warning": "Hinweis", "info": "Information"}


def _masthead(canvas: PdfCanvas, *, note: str | None = None) -> None:
    """The block at the top of page one: wordmark, title, one line of what this document is.

    The wordmark is set in type rather than placed as an image, and that is a limitation stated
    plainly rather than worked around: this writer draws no rasters, so a logo would mean either a
    dependency or a hand-rolled image codec. Letter-spaced capitals read as a wordmark on paper and
    cost neither.
    """
    canvas.text("A Z M O T H", size=SIZE_SMALL, bold=True, leading=15, grey=GREY_MUTED)
    canvas.text("GOÄ-Prüfbericht", size=SIZE_TITLE, bold=True, leading=25)
    canvas.text(
        "Systematische Prüfung einer PADnext-Lieferung gegen die Gebührenordnung für Ärzte",
        size=SIZE_BODY,
        leading=16,
        grey=GREY_MUTED,
    )
    if note:
        canvas.space(2)
        canvas.paragraph(note, size=SIZE_SMALL, bold=True)
    canvas.rule(thickness=1.2, grey=GREY_TEXT)
    canvas.space(6)


#: How much of the identity block a label may take before its value starts.
_IDENTITY_LABEL_WIDTH = 96.0


def _identity_block(canvas: PdfCanvas, rows: Sequence[tuple[str, str]]) -> None:
    """The label/value grid under the masthead: what was checked, when, under whose account.

    Two pairs to a line rather than one, because the list is long enough that a single column would
    push the summary table off page one — and the summary table belongs on page one.

    **A value that does not fit its half gets the whole line instead of an ellipsis.** These are the
    fields somebody uses to find this document again: a filename, an invoice number, a report id.
    Truncating `00004711_20260726_ADL_000001_padx.xml` to `00004711_20260726_ADL_000…` produces a
    header that identifies nothing, and it is precisely the long ones — a 64-character receipt hash,
    a PADnext filename — that carry the identity. So the block measures first and lays out second,
    and only a value too long even for the full width is shortened.
    """
    half = CONTENT_WIDTH / 2
    narrow = half - _IDENTITY_LABEL_WIDTH - 8
    full = CONTENT_WIDTH - _IDENTITY_LABEL_WIDTH

    def fits(value: str) -> bool:
        return text_width(value, size=SIZE_TABLE) <= narrow

    def draw(pairs: Sequence[tuple[str, str]], *, width: float) -> None:
        cells: list[Cell] = []
        for offset, (label, value) in enumerate(pairs):
            x = offset * half
            cells.append(Cell(x, label, _IDENTITY_LABEL_WIDTH, "left", False, GREY_MUTED))
            cells.append(
                Cell(
                    x + _IDENTITY_LABEL_WIDTH,
                    fit(value, size=SIZE_TABLE, width=width),
                    width,
                    "left",
                )
            )
        canvas.row(cells, size=SIZE_TABLE, leading=13)

    pending: list[tuple[str, str]] = []
    for label, value in rows:
        if fits(value):
            pending.append((label, value))
            if len(pending) == 2:
                draw(pending, width=narrow)
                pending = []
            continue
        # Too wide to share a line. Flush whatever was waiting, then take the full width.
        if pending:
            draw(pending, width=narrow)
            pending = []
        draw([(label, value)], width=full)
    if pending:
        draw(pending, width=narrow)


def _section(canvas: PdfCanvas, number: int, title: str, *, needs: float = 60.0) -> None:
    """A numbered section heading that will not be left stranded at the foot of a page.

    The space is *before* the heading and larger than the space after it, which is the one typographic
    rule that makes a document of stacked sections readable: a heading has to belong visibly to what
    follows it rather than float between two blocks. `needs` is what `reserve` guarantees — the
    heading plus enough of its first rows to be worth turning the page for.
    """
    canvas.reserve(needs)
    canvas.space(14)
    canvas.text(f"{number}. {title}", size=SIZE_SECTION, bold=True, leading=20)


#: The summary table's shape, shared by both reports so their front pages are the same document.
_SUMMARY_COLUMNS = (
    Column("Bewertung", 0, 210),
    Column("Positionen", 210, 70, "right"),
    Column("Betrag", 285, 105, "right"),
    Column("Anteil", 395, 88, "right"),
)


def _summary_table(
    canvas: PdfCanvas,
    *,
    claimed: Decimal,
    rows: Sequence[tuple[str, int, Decimal]],
    total_positions: int,
    coverage_ratio: float,
) -> None:
    """The three buckets and their total. Never four rows, never a merged »Risiko«."""
    canvas.reserve(110)

    def share(value: Decimal) -> str:
        if not claimed:
            return "—"
        return _percent(Decimal(value) / claimed * 100)

    with canvas.table(_SUMMARY_COLUMNS) as table:
        for index, (label, count, amount) in enumerate(rows):
            table.row(
                [label, str(count), _euro(amount), share(amount)],
                band=GREY_ZEBRA if index % 2 else None,
            )
        canvas.rule(thickness=0.8, grey=GREY_TEXT)
        table.row(
            [
                "Abgerechnet gesamt",
                str(total_positions),
                _euro(claimed),
                "100,0 %" if claimed else "—",
            ],
            bold=True,
        )
    canvas.space(4)
    canvas.text(
        f"Prüfabdeckung: {_percent(coverage_ratio * 100)} der abgerechneten Summe",
        size=SIZE_SUBSECTION,
        bold=True,
        leading=16,
    )


def _reading_note(canvas: PdfCanvas, coverage_sentence: str) -> None:
    """The paragraph beside the numbers. The most consequential prose the product emits."""
    canvas.paragraph(
        "Zur Lesart. »Belegbar nicht abrechenbar« ist der einzige Betrag, der als Rückforderung "
        "gelesen werden darf: hier hat eine verifizierte Regel die Position beanstandet. "
        "»Nicht beurteilbar« ist ausdrücklich KEIN Befund gegen die Praxis — es ist die Grenze der "
        "Regelabdeckung dieser Engine. " + coverage_sentence + " Die drei Beträge werden nie zu "
        "einer Summe »Risiko« zusammengefasst, weil genau diese Zusammenfassung aus einer "
        "Abdeckungslücke eine Anschuldigung machen würde.",
        size=SIZE_SMALL,
    )
    canvas.space(3)
    canvas.paragraph(
        "Auch »belegbar nicht abrechenbar« ist kein festgestellter Rückforderungsbetrag: bei zwei "
        "sich gegenseitig ausschliessenden Positionen zählen beide hinein, weil die Engine nicht "
        "errät, welche die Praxis behalten wollte. Die Rechnung ist in beiden Fällen zu "
        "korrigieren, der tatsächlich strittige Betrag ist jedoch geringer.",
        size=SIZE_SMALL,
    )


def _legal_block(canvas: PdfCanvas, number: int) -> None:
    """The disclaimer, the data-protection note, the contact — and the line somebody signs.

    Last, and deliberately not in the running footer. A footer is where a reader's eye stops
    going after page one; the statement that this document is a draft requiring a physician's
    release has to be a block they read, in the place a document's terms belong.
    """
    canvas.reserve(170)
    _section(canvas, number, "Rechtliche Hinweise")
    canvas.paragraph(DISCLAIMER, size=SIZE_SMALL)
    canvas.space(4)
    canvas.paragraph(DATA_PROTECTION, size=SIZE_SMALL, grey=GREY_MUTED)
    canvas.space(4)
    canvas.paragraph(
        f"Erstellt von Azmoth — deterministische GOÄ-Prüfengine. Rückfragen: {CONTACT}",
        size=SIZE_SMALL,
        grey=GREY_MUTED,
    )
    canvas.space(16)

    # The Freigabe line. Ruled and labelled, because a report that demands a physician's release
    # and then offers nowhere to record it invites the release to be given verbally.
    canvas.reserve(48)
    canvas.text("Freigabe", size=SIZE_SUBSECTION, bold=True, leading=22)
    half = CONTENT_WIDTH / 2
    canvas.rule(thickness=0.5, grey=GREY_TEXT, x=0, width=half - 20)
    canvas.y += 6  # the second rule sits on the same baseline as the first
    canvas.rule(thickness=0.5, grey=GREY_TEXT, x=half, width=half)
    canvas.row(
        [
            Cell(0, "Ort, Datum", half - 20, "left", False, GREY_MUTED),
            Cell(half, "Unterschrift / Stempel — ärztliche Prüfung und Freigabe",
                 half, "left", False, GREY_MUTED),
        ],
        size=SIZE_FOOTER,
    )


def _provenance_block(
    canvas: PdfCanvas, number: int, rows: Sequence[tuple[str, str]], *, title: str = "Prüfgrundlage"
) -> None:
    """Catalog, rules, logic, receipt — the identity a verdict is only meaningful against."""
    canvas.reserve(40 + 13 * len(rows))
    _section(canvas, number, title)
    canvas.paragraph(
        "Ein Prüfergebnis ist nur gegenüber dem Datenstand aussagekräftig, gegen den es erzeugt "
        "wurde. Diese Angaben identifizieren ihn vollständig; der Receipt-Hash bindet Katalog, "
        "Regelstand, Logikprogramme und Eingabe an genau dieses Ergebnis.",
        size=SIZE_SMALL,
        grey=GREY_MUTED,
    )
    canvas.space(4)
    for label, value in rows:
        canvas.row(
            [
                Cell(0, label, 130, "left", False, GREY_MUTED),
                Cell(130, fit(value, size=SIZE_TABLE, width=CONTENT_WIDTH - 130), 0, "left"),
            ],
            size=SIZE_TABLE,
            leading=13,
        )


# ==============================================================================================
# the batch report
# ==============================================================================================


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


#: The delivery table's shape. Widths are set from the *headings*, not from the values: `Nicht
#: abrechenbar` is 79 pt at 9 pt bold and is wider than any euro amount that will ever sit under
#: it, so a column sized for `1.234,56 €` puts its own heading through the column beside it.
#: `tests/test_pdf_report.py::test_every_column_heading_fits_the_column_it_labels` holds this.
_DELIVERY_COLUMNS = (
    Column("Datei", 0, 196),
    Column("Status", 196, 72),
    Column("Positionen", 268, 48, "right"),
    Column("Abgerechnet", 316, 78, "right"),
    Column("Nicht abrechenbar", 394, 89, "right"),
)


def render_batch_report(
    job: BatchAuditJob,
    *,
    organization_id: str,
    generated_at: datetime | None = None,
) -> bytes:
    """A completed job as a Prüfbericht, ready to hand a Rechnungsprüfer.

    The document says these things, in this order, and the order is the argument:

    1. **What was checked** — how many deliveries, when, for whom, under which catalog and rule
       set. A report that cannot state the engine state it was produced under is not evidence of
       anything, which is why the identity block is on the first page rather than in a footnote.
    2. **The three buckets, never merged.** The same refusal `BatchAggregateSummary` makes, carried
       into print, where it matters more: a PDF outlives the screen it came from and will be read
       by somebody who was not told what `unconfirmed` means. So it is spelled out in a paragraph
       beside the number rather than in a legend.
    3. **The per-delivery table**, riskiest first — which is the order `load_batch` already sorted
       `files` into, so this renders the engine's ordering rather than inventing a second one.
    4. **The basis and the terms** — provenance, then the disclaimer and the Freigabe line.

    Takes the `BatchAuditJob` the API returns rather than the ORM rows, deliberately: the printed
    document and the JSON a client parses are then two renderings of one object, and they cannot
    come to disagree about a total.

    `generated_at` defaults to the job's own completion time rather than to `now`, so re-downloading
    a finished batch a week later still produces the same bytes — the document is about a run that
    already happened, and its date is that run's date.
    """
    summary = job.aggregate_summary
    first = next((entry.report for entry in job.files if entry.report is not None), None)
    stamped = generated_at if generated_at is not None else job.completed_at

    canvas = PdfCanvas(
        title=f"GOÄ-Prüfbericht — Stapel {job.batch_id}",
        subject="GOÄ-Prüfbericht (Stapelprüfung)",
        report_id=job.batch_id,
        generated_at=stamped,
        keywords="GOÄ, Prüfbericht, PADnext, Abrechnungsprüfung, Azmoth",
    )

    _masthead(canvas)
    _identity_block(
        canvas,
        [
            ("Auftrag", job.batch_id),
            ("Erstellt am", _stamp(stamped)),
            ("Organisation", organization_id),
            ("Eingegangen", _stamp(job.created_at)),
            ("Lieferungen", f"{job.file_count} gesamt · {job.completed_file_count} geprüft · "
                            f"{job.failed_file_count} nicht lesbar"),
            ("Abgeschlossen", _stamp(job.completed_at)),
            ("Katalog", first.catalog_version if first else "—"),
            ("Regelstand", first.rules_version if first else "—"),
        ],
    )
    canvas.space(6)

    if summary is None:
        # A job with no roll-up should not reach here — the endpoint refuses anything that is not
        # COMPLETED — so this is the belt-and-braces branch. It prints the absence rather than
        # zeros, because a page of €0,00 is a document somebody could reconcile against.
        _section(canvas, 1, "Kein Ergebnis")
        canvas.paragraph(
            "Für diesen Auftrag liegt keine Auswertung vor. Es werden bewusst keine Zahlen "
            "gedruckt: eine Aufstellung mit Nullwerten wäre von einem geprüften Nullbetrag nicht "
            "zu unterscheiden.",
            size=SIZE_SMALL,
        )
        _legal_block(canvas, 2)
        return canvas.render()

    _section(canvas, 1, "Ergebnis nach Belegbarkeit", needs=150)
    _summary_table(
        canvas,
        claimed=summary.claimed_total_eur or Decimal("0.00"),
        rows=[
            ("Belegbar korrekt", summary.confirmed_fine_positions, summary.confirmed_fine_eur),
            ("Belegbar nicht abrechenbar", summary.confirmed_wrong_positions,
             summary.confirmed_wrong_eur),
            ("Nicht beurteilbar", summary.unconfirmed_positions, summary.unconfirmed_eur),
        ],
        total_positions=summary.position_count,
        coverage_ratio=summary.coverage_ratio,
    )
    canvas.space(6)
    _reading_note(canvas, _coverage_sentence(job, summary))
    canvas.space(8)

    _section(canvas, 2, "Lieferungen im Einzelnen", needs=90)
    canvas.paragraph(
        "Sortiert nach belegbar nicht abrechenbarem Betrag, absteigend — die Reihenfolge, in der "
        "eine Praxis die Rechnungen durchgehen sollte.",
        size=SIZE_SMALL,
        grey=GREY_MUTED,
    )
    canvas.space(3)

    with canvas.table(_DELIVERY_COLUMNS) as table:
        for index, entry in enumerate(job.files):
            report = entry.report
            name = fit(entry.filename, size=SIZE_TABLE, width=_DELIVERY_COLUMNS[0].width - 4)
            zebra = GREY_ZEBRA if index % 2 else None
            if report is None:
                table.row(
                    [
                        name,
                        "fehlgeschlagen" if entry.status == BatchFileStatus.FAILED else "offen",
                        "—",
                        "—",
                        "—",
                    ],
                    band=zebra,
                )
                if entry.error_message:
                    canvas.paragraph(
                        entry.error_message, size=SIZE_FOOTER, indent=10, grey=GREY_MUTED
                    )
                continue
            table.row(
                [
                    name,
                    "geprüft",
                    str(len(report.positions)),
                    _euro(report.claimed_total_eur),
                    _euro(report.confirmed_wrong_eur),
                ],
                band=zebra,
            )

    canvas.space(8)

    rows: list[tuple[str, str]] = []
    if first is not None:
        rows = [
            ("Katalog", first.catalog_version),
            ("Katalog-SHA-256", first.catalog_sha256),
            ("Regelstand", first.rules_version),
            ("Logikstand", first.logic_version),
            (
                "Regelabdeckung",
                f"{first.enforced_rule_count} durchgesetzt · "
                f"{first.advisory_rule_count} hinweisend · "
                f"{first.suppressed_unverified_rule_count} unbestätigt und unterdrückt",
            ),
        ]
    _provenance_block(canvas, 3, rows)
    _legal_block(canvas, 4)

    return canvas.render()


# ==============================================================================================
# the single-delivery report
# ==============================================================================================


def _single_coverage_sentence(report: PadnextAuditReport) -> str:
    """Why this one delivery could not be judged in full — counted from the report, never asserted.

    The single-delivery twin of `_coverage_sentence`, and it exists for the identical reason: the
    paragraph beside the amber number decides whether a reader takes »nicht beurteilbar« for "we
    could not check this" or for "we suspect this", and a hardcoded claim about rule coverage is a
    sentence with no mechanism to stay true. Every figure below comes off the report being printed.
    """
    parts: list[str] = []
    detail = report.rule_coverage_detail

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
    else:
        parts.append(
            f"Bei dieser Prüfung waren {report.enforced_rule_count} Regeln durchgesetzt und "
            f"{report.advisory_rule_count} nur beratend. "
        )

    unconfirmed = sum(1 for p in report.positions if p.bucket == "unconfirmed")
    total = len(report.positions)
    if total and unconfirmed:
        parts.append(
            f"Für {unconfirmed} der {total} abgerechneten Positionen greift keine verifizierte "
            "Regel: der hinterlegte Regelsatz deckt diese Ziffern noch nicht ab. Was hier fehlt, "
            "ist also die Reichweite der Regeln über den Gebührenkatalog, nicht das Vertrauen "
            "in die Regeln selbst."
        )
    elif total:
        parts.append(
            f"Für alle {total} abgerechneten Positionen konnte eine verifizierte Regel "
            "herangezogen werden."
        )

    return "".join(parts).strip()


#: The position table's shape. Five columns across 483 pt, with the three numeric ones right
#: aligned so their last digits form a line a reader can add up down the page.
_POSITION_COLUMNS = (
    Column("Ziffer", 0, 46),
    Column("Leistung nach GOÄ", 46, 244),
    Column("Faktor", 290, 40, "right"),
    Column("Abgerechnet", 330, 76, "right"),
    Column("Nachgerechnet", 406, 77, "right"),
)

#: Where a position's explanatory lines are indented to: under the Leistung column, so the block
#: reads as belonging to the Ziffer on its left rather than as a new row.
_POSITION_INDENT = 46.0


def _legal_bases_for(
    position_findings: Sequence[PadnextFinding],
) -> str:
    """The exact legal ground and rule id behind a position, joined for one line of print.

    Read off the *findings*, not off `PadnextAuditedPosition.legal_basis`. That field carries the
    fee schedule's valuation basis — § 5 Abs. 1, 2 GOÄ — which is the same for nearly every
    position and is not why any particular one was rejected. The paragraph a Rechnungsprüfer needs
    to see beside a rejected line is the one the *finding* cites: § 4 Abs. 2a for a Zielleistung,
    § 12 Abs. 3 for a missing justification. Printing the generic basis in that place would look
    like an answer and be a non-answer.
    """
    seen: list[str] = []
    for finding in position_findings:
        for part in (finding.legal_basis, finding.rule_id):
            if part and part not in seen:
                seen.append(part)
    return " · ".join(seen)


def _findings_by_position(report: PadnextAuditReport) -> dict[str, list[PadnextFinding]]:
    """Index the findings by the position they were raised against, keeping their order."""
    index: dict[str, list[PadnextFinding]] = {}
    for finding in report.findings:
        if finding.positionsnr:
            index.setdefault(finding.positionsnr, []).append(finding)
    return index


def render_single_report(
    report: PadnextAuditReport,
    *,
    note: str | None = None,
    organization: str | None = None,
    generated_at: datetime | None = None,
) -> bytes:
    """One audited delivery as a Prüfbericht, ready to hand a Rechnungsprüfer.

    The single-delivery counterpart to `render_batch_report`, and deliberately the same document in
    the same order: what was checked, the three buckets with the caveat spelled out beside them,
    the positions riskiest first, then the basis and the terms. A reader who has seen a batch report
    can read this one without being told anything, which is the whole reason it is not laid out to
    suit itself.

    **Positions are grouped by bucket rather than merely sorted into it.** Each group carries its
    own heading, count and subtotal, so the question a practice actually opens this document with —
    "what do I have to change?" — is answered by the first heading rather than by reading a
    Bewertung column down forty rows. Within a group the order is the invoice's own.

    **Each position prints its ground.** The official GOÄ Leistungstext from the versioned catalog,
    the claimed factor, what was billed, what we recompute, the reason in prose, and then the
    paragraph and rule id behind it. That last pair is the difference between a report a payer can
    act on and one they can only be annoyed by: `§ 4 Abs. 2a GOÄ · ziel_man_301_200` is checkable,
    "nicht berechnungsfähig" is not.

    `note` is stamped under the title, in the one register a PDF has for saying what it is: the
    public demo passes the sentence that says this is synthetic. It is deliberately part of the
    document rather than a watermark, because a watermark is the first thing a photocopier loses.

    `generated_at` is the document's only clock and it is a parameter. The demo passes none and its
    two downloads are byte-identical; an authenticated export passes the request time, and prints
    it, because a report going into a client file needs to say when it was drawn.
    """
    findings_by_position = _findings_by_position(report)

    canvas = PdfCanvas(
        title=f"GOÄ-Prüfbericht — {report.source_name or 'PADnext-Lieferung'}",
        subject="GOÄ-Prüfbericht (Einzelprüfung)",
        report_id=report.receipt_hash,
        generated_at=generated_at,
        keywords="GOÄ, Prüfbericht, PADnext, Abrechnungsprüfung, Azmoth",
    )

    _masthead(canvas, note=note)

    invoice_ids = ", ".join(report.invoice_ids) if report.invoice_ids else "—"
    _identity_block(
        canvas,
        # Ordered so the long values — which `_identity_block` promotes to a full line — come
        # first and the short ones pair off after, rather than leaving a half-line stranded
        # between two wide ones.
        [
            ("Datei", report.source_name or "—"),
            ("Bericht-ID", report.receipt_hash or "—"),
            ("Setting (§ 6a)", f"{report.setting} ({report.setting_source or '—'})"),
            ("Erstellt am", _stamp(generated_at)),
            ("Nachrichtentyp", report.nachrichtentyp or "—"),
            ("Rechnung", invoice_ids),
            ("Positionen", str(len(report.positions))),
            ("Praxis / Konto", organization or "—"),
        ],
    )
    canvas.space(6)

    # ---- 1. the three buckets ---------------------------------------------------------------
    _section(canvas, 1, "Ergebnis nach Belegbarkeit", needs=150)

    def count(bucket: str) -> int:
        return sum(1 for p in report.positions if p.bucket == bucket)

    _summary_table(
        canvas,
        claimed=report.claimed_total_eur or Decimal("0.00"),
        rows=[
            ("Belegbar korrekt", count("confirmed_fine"), report.confirmed_fine_eur),
            ("Belegbar nicht abrechenbar", count("confirmed_wrong"), report.confirmed_wrong_eur),
            ("Nicht beurteilbar", count("unconfirmed"), report.unconfirmed_eur),
        ],
        total_positions=len(report.positions),
        coverage_ratio=report.coverage_ratio,
    )
    canvas.space(6)
    _reading_note(canvas, _single_coverage_sentence(report))
    canvas.space(8)

    # ---- 2. the positions, grouped by bucket, riskiest group first ---------------------------
    _section(canvas, 2, "Positionen im Einzelnen", needs=100)
    canvas.paragraph(
        "Nach Belegbarkeit gruppiert, innerhalb einer Gruppe in der Reihenfolge der Rechnung. "
        "»Nachgerechnet« ist der Betrag aus dem versionierten Katalog — die Datei wird nicht als "
        "Preisauskunft geglaubt. Unter jeder beanstandeten Position steht die Begründung und, wo "
        "eine Regel gegriffen hat, die Rechtsgrundlage und die Regel-ID zur Nachprüfung.",
        size=SIZE_SMALL,
        grey=GREY_MUTED,
    )
    canvas.space(4)

    for bucket in sorted(_BUCKET_ORDER, key=lambda b: _BUCKET_ORDER[b]):
        group = [p for p in report.positions if p.bucket == bucket]
        if not group:
            continue
        subtotal = sum(
            (p.claimed_amount_eur or Decimal("0.00") for p in group), Decimal("0.00")
        )
        canvas.reserve(64)
        canvas.space(4)
        canvas.row(
            [
                Cell(0, f"{_BUCKET_LABEL[bucket]} — {len(group)} Position"
                        f"{'en' if len(group) != 1 else ''}", 300, "left", True),
                Cell(300, _euro(subtotal), 183, "right", True),
            ],
            size=SIZE_SUBSECTION,
            leading=17,
        )

        with canvas.table(_POSITION_COLUMNS) as table:
            for position in group:
                position_findings = findings_by_position.get(position.positionsnr, [])
                reason = position.bucket_reason or position.reason
                basis = _legal_bases_for(position_findings)

                # Measure the whole block — headline row, reason, legal ground — and take a page
                # break before it rather than through it. A position whose reason is orphaned on
                # the next page reads as belonging to the position printed above it there.
                needed = SIZE_TABLE + 5.0
                if reason:
                    needed += canvas.measure_paragraph(
                        reason, size=SIZE_FOOTER, indent=_POSITION_INDENT
                    )
                if basis:
                    needed += canvas.measure_paragraph(
                        basis, size=SIZE_FOOTER, indent=_POSITION_INDENT
                    )
                canvas.reserve(needed + 4)

                label = position.ziffer or "—"
                if position.go and position.go.upper() not in {"GOÄ", "GOAE", "GOAE_1982"}:
                    label = f"{position.go} {label}"
                official = position.official_text or (
                    "Nicht im geprüften Katalog enthalten"
                    if not position.in_catalog
                    else "—"
                )
                table.row(
                    [
                        label,
                        fit(official, size=SIZE_TABLE, width=240),
                        _factor(position.claimed_faktor),
                        _euro(position.claimed_amount_eur),
                        _euro(position.recomputed_amount_eur),
                    ],
                    bold=bucket == "confirmed_wrong",
                )
                if reason:
                    canvas.paragraph(reason, size=SIZE_FOOTER, indent=_POSITION_INDENT)
                if basis:
                    canvas.paragraph(
                        basis, size=SIZE_FOOTER, indent=_POSITION_INDENT, grey=GREY_MUTED
                    )
                canvas.space(2)

    canvas.space(8)

    # ---- 3. findings -------------------------------------------------------------------------
    section = 3
    if report.findings:
        _section(canvas, section, f"Befunde ({len(report.findings)})", needs=80)
        canvas.paragraph(
            "Jede Beanstandung einzeln, mit der Rechtsgrundlage und — wo eine hinterlegte Regel "
            "gegriffen hat — ihrer Regel-ID.",
            size=SIZE_SMALL,
            grey=GREY_MUTED,
        )
        canvas.space(4)
        for finding in report.findings:
            basis = _legal_bases_for([finding])
            needed = 14.0 + canvas.measure_paragraph(
                finding.message, size=SIZE_FOOTER, indent=_POSITION_INDENT
            )
            if basis:
                needed += canvas.measure_paragraph(
                    basis, size=SIZE_FOOTER, indent=_POSITION_INDENT
                )
            canvas.reserve(needed + 6)

            # A finding that names no position carries its `type` instead — and a type like
            # `advisory_rules_present` is far wider than a Ziffer column. So the label takes
            # whatever room it needs and the severity is right-aligned against the far margin,
            # which keeps both readable whether the label is `410` or a thirty-character slug.
            label = finding.ziffer or finding.positionsnr or finding.type
            severity = _SEVERITY_LABEL.get(finding.severity, finding.severity)
            canvas.row(
                [
                    Cell(0, fit(str(label), size=SIZE_TABLE, width=380, bold=True), 380,
                         "left", True),
                    Cell(380, severity, CONTENT_WIDTH - 380, "right", True, GREY_MUTED),
                ],
                size=SIZE_TABLE,
                leading=13,
            )
            canvas.paragraph(finding.message, size=SIZE_FOOTER, indent=_POSITION_INDENT)
            if basis:
                canvas.paragraph(
                    basis, size=SIZE_FOOTER, indent=_POSITION_INDENT, grey=GREY_MUTED
                )
            canvas.space(3)
        canvas.space(6)
        section += 1

    # ---- 4. provenance -----------------------------------------------------------------------
    _provenance_block(
        canvas,
        section,
        [
            ("Katalog", report.catalog_version or "—"),
            ("Katalog-SHA-256", report.catalog_sha256 or "—"),
            ("Regelstand", report.rules_version or "—"),
            ("Logikstand", report.logic_version or "—"),
            ("Receipt-Hash", report.receipt_hash or "—"),
            ("Schema-Prüfung", report.schema_policy),
            (
                "Regelabdeckung",
                f"{report.enforced_rule_count} durchgesetzt · "
                f"{report.advisory_rule_count} hinweisend · "
                f"{report.suppressed_unverified_rule_count} unbestätigt und unterdrückt",
            ),
        ],
    )
    _legal_block(canvas, section + 1)

    return canvas.render()


__all__ = [
    "BOTTOM",
    "CONTENT_WIDTH",
    "DISCLAIMER",
    "MARGIN",
    "PAGE_HEIGHT",
    "PAGE_WIDTH",
    "Cell",
    "Column",
    "PdfCanvas",
    "Table",
    "fit",
    "render_batch_report",
    "render_single_report",
    "wrap",
]
