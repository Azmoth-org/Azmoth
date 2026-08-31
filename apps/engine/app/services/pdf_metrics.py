"""Adobe Helvetica advance widths, so this renderer can measure text instead of guessing.

Everything laid out in `app.services.pdf` — where a line wraps, where a right-aligned euro amount
starts, whether a heading and its first row still fit above the footer — is a question about how
wide a string is. Before this table existed the answer was one constant, `AVERAGE_GLYPH_WIDTH =
0.5`, applied to every character alike. That is wrong by up to a factor of four in both directions:
`i` is 222 units and `%` is 889, so `WWW` measured narrower than it draws and `iii` measured more
than three times wider. In a report whose whole purpose is a column of amounts that line up, the
consequence is a Betrag column that visibly does not.

**Where these numbers come from.** They are the advance widths of the Adobe Helvetica and
Helvetica-Bold AFM metrics, indexed by `WinAnsiEncoding` code point — the same two fonts and the
same encoding the page resources declare, so what is measured here is exactly what a reader draws.
Units are 1/1000 em, the PDF glyph space convention: a character's width in points is
`width[code] * size / 1000`.

**Why a table and not a dependency.** This is 512 integers. Reading them from a font file at
startup would mean shipping an AFM and parsing it; taking a typesetting library to obtain them
would mean the dependency `app.services.pdf` exists specifically not to take. Frozen numbers from a
frozen specification — the fourteen standard fonts have not changed since 1985 — are the one case
where a literal table is the honest form. They were generated once and are checked rather than
trusted: `tests/test_pdf_report.py` asserts the invariants that make the layout work (the tables
are exactly 256 long, every printable cp1252 code point has a non-zero width, and all ten digits
are equal — Helvetica is tabular in the digits, which is what lets a column of amounts align).

**Code 0 means "no glyph at this code point".** WinAnsi leaves the C0 range and a handful of high
positions undefined. Those cannot appear in output — `_escape` maps anything outside cp1252 to `?`
first — so the width is never consulted, but it is 0 rather than a fallback so that a bug which did
reach one produces a visibly collapsed line rather than a subtly wrong one.
"""

from __future__ import annotations

from typing import Final

#: Widths are 1/1000 em, the unit PDF glyph space uses.
UNITS_PER_EM: Final = 1000

#: Helvetica advance widths by WinAnsi code point, in 1/1000 em.
HELVETICA: Final[tuple[int, ...]] = (
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556,
    556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722,
    722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667,
    944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222,
    222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260,
    334, 584, 350, 556, 350, 222, 556, 333, 1000, 556, 556, 333, 1000, 667, 333, 1000, 350, 611,
    350, 350, 222, 222, 333, 333, 350, 556, 1000, 333, 1000, 500, 333, 944, 350, 500, 667, 278,
    333, 556, 556, 556, 556, 260, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333,
    333, 556, 537, 278, 333, 333, 365, 556, 834, 834, 834, 611, 667, 667, 667, 667, 667, 667,
    1000, 722, 667, 667, 667, 667, 278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584,
    778, 722, 722, 722, 722, 667, 667, 611, 556, 556, 556, 556, 556, 556, 889, 500, 556, 556, 556,
    556, 278, 278, 278, 278, 556, 556, 556, 556, 556, 556, 556, 584, 611, 556, 556, 556, 556, 500,
    556, 500
)

#: Helvetica-Bold advance widths by WinAnsi code point, in 1/1000 em.
HELVETICA_BOLD: Final[tuple[int, ...]] = (
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556,
    556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722,
    667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944,
    667, 667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278,
    556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389,
    584, 350, 556, 350, 278, 556, 500, 1000, 556, 556, 333, 1000, 667, 333, 1000, 350, 611, 350,
    350, 278, 278, 500, 500, 350, 556, 1000, 333, 1000, 556, 333, 944, 350, 500, 667, 278, 333,
    556, 556, 556, 556, 280, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333,
    611, 556, 278, 333, 333, 365, 556, 834, 834, 834, 611, 722, 722, 722, 722, 722, 722, 1000,
    722, 667, 667, 667, 667, 278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722,
    722, 722, 722, 667, 667, 611, 556, 556, 556, 556, 556, 556, 889, 556, 556, 556, 556, 556, 278,
    278, 278, 278, 611, 611, 611, 611, 611, 611, 611, 584, 611, 611, 611, 611, 611, 556, 611, 556
)


def text_width(value: str, *, size: float, bold: bool = False) -> float:
    """How many points `value` occupies when drawn at `size`.

    Measured over the cp1252 bytes rather than the Python string, because those bytes are what
    reaches the content stream: `_escape` has already replaced anything unencodable with `?`, and
    measuring the original character would then disagree with what is drawn by exactly the
    difference between the two glyphs. Encoding here with the same `errors="replace"` keeps the
    measurement and the drawing looking at the same document.
    """
    table = HELVETICA_BOLD if bold else HELVETICA
    raw = value.encode("cp1252", errors="replace")
    return sum(table[byte] for byte in raw) * size / UNITS_PER_EM


__all__ = ["HELVETICA", "HELVETICA_BOLD", "UNITS_PER_EM", "text_width"]
