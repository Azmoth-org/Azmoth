"""What did the caller actually send us? Magic bytes, not filenames.

The commercial API takes exactly one input format — PADnext XML, bare or inside a `.padx`
container — and the first thing it does with a request body is work out whether that is what
arrived. The point is not validation, which the reader and the XSD already do far better; it is
being able to say *"that is a PDF"* to the integrator who posted a PDF, instead of letting them
read a schema violation at line 1 column 1 and conclude our XML parser is broken.

**Filenames are not evidence.** `upload.filename` is whatever the client's form said, a browser
will happily call a PDF `rechnung.xml`, and a PVS export script that got the wrong variable will be
consistently wrong. So nothing here looks at a name: `.padx` is recognised because it starts with
`PK\\x03\\x04`, JSON because its first non-whitespace byte is `{` or `[`. That also means the
detection cannot be defeated by renaming, which matters when the refusal is a documented part of
the contract.

**What is deliberately *not* detected.** There is no attempt to tell valid PADnext from other XML.
Anything that looks like XML is passed to `read_delivery`, which knows what an ADL document is and
reports precisely which part of it is missing. A second, shallower opinion here would only be able
to be wrong in a new way.
"""

from __future__ import annotations

from enum import StrEnum

#: The first four bytes of every ZIP — and therefore of every `.padx` container. Same constant as
#: `app.padnext.reader.ZIP_MAGIC`, spelled again rather than imported so this module stays free of
#: the reader (it is used to decide whether the reader should be called at all).
ZIP_MAGIC = b"PK\x03\x04"

#: `%PDF-`. The single most likely wrong thing to be posted to an invoice-audit API, by some
#: distance: a practice's own invoice archive is PDFs, and "audit this invoice" is a sentence that
#: makes as much sense holding one.
PDF_MAGIC = b"%PDF-"

#: What may precede the first real character of a document: XML's own definition of whitespace (S),
#: plus the UTF-8 byte-order mark, which a Windows-based PVS export routinely writes and which is
#: not whitespace by any definition but is nonetheless in front of the `<`.
_LEADING_NOISE = b" \t\r\n\xef\xbb\xbf"


class InputFormat(StrEnum):
    """What the first few bytes say the body is.

    A closed set, and the members are named for what a *caller* would call them rather than for
    what they are internally — the value ends up in `details.detected` on a `400`, where it is read
    by somebody deciding what their integration sent by mistake.
    """

    XML = "xml"
    ZIP = "zip"
    PDF = "pdf"
    JSON = "json"
    EMPTY = "empty"
    UNKNOWN = "unknown"


def detect_format(data: bytes) -> InputFormat:
    """Classify a request body by its leading bytes.

    Cheap by construction — it reads at most the first few hundred bytes and never parses — so it
    can sit in front of every upload without being a cost anybody has to think about.
    """
    if not data:
        return InputFormat.EMPTY
    if data.startswith(ZIP_MAGIC):
        return InputFormat.ZIP
    if data.startswith(PDF_MAGIC):
        return InputFormat.PDF

    head = data[:256].lstrip(_LEADING_NOISE)
    if not head:
        # Whitespace and nothing else. Not empty in the Content-Length sense, and not usable
        # either; `EMPTY` is what a caller needs to hear.
        return InputFormat.EMPTY
    if head[:1] in (b"{", b"["):
        return InputFormat.JSON
    if head[:1] == b"<":
        return InputFormat.XML
    return InputFormat.UNKNOWN


#: What to tell a caller who sent each thing. German first, English after, matching the rest of the
#: error catalog: the practice reads the first sentence and the integrator reads the second.
FORMAT_ADVICE: dict[InputFormat, str] = {
    InputFormat.PDF: (
        "Es wurde ein PDF gesendet. Diese Schnittstelle prüft PADnext-Abrechnungsdaten (XML), "
        "nicht das gedruckte Rechnungsdokument — exportieren Sie die Rechnung aus Ihrem PVS als "
        "PADnext-Lieferung. — A PDF was sent; this endpoint audits PADnext XML, not the printed "
        "invoice."
    ),
    InputFormat.JSON: (
        "Es wurde JSON gesendet. Der Body dieser Schnittstelle ist die PADnext-Datei selbst, kein "
        "JSON-Wrapper. Für strukturierte klinische Entitäten gibt es POST /api/v1/solve. — JSON "
        "was sent; the body of this endpoint is the PADnext file itself. For structured clinical "
        "entities use POST /api/v1/solve."
    ),
    InputFormat.EMPTY: (
        "Der Body ist leer. — The body is empty."
    ),
    InputFormat.UNKNOWN: (
        "Der Inhalt ist weder XML noch ein .padx-Container. Senden Sie die PADnext-Datei selbst — "
        "eine *_padx.xml oder ein .padx-Container. — The body is neither XML nor a .padx "
        "container."
    ),
    InputFormat.ZIP: (
        "Es wurde ein ZIP-Archiv gesendet. Ein .padx-Container ist hier erlaubt; ein Archiv mit "
        "mehreren Lieferungen gehört an POST /api/v1/audit/bulk. — A ZIP was sent. A .padx "
        "container is accepted here; an archive of many deliveries belongs on "
        "POST /api/v1/audit/bulk."
    ),
    InputFormat.XML: "",
}


__all__ = [
    "FORMAT_ADVICE",
    "PDF_MAGIC",
    "ZIP_MAGIC",
    "InputFormat",
    "detect_format",
]
