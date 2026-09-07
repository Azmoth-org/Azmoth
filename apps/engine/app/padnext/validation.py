"""Every reason one PADnext delivery cannot be audited, collected in a single pass.

`reader.read_delivery` answers one question — *can this be read?* — and answers it by raising on
the first thing that stops it. That is the right shape for the audit pipeline, which has nothing
useful to do with a half-read delivery, and it is the wrong shape for the person holding the file.
An export with a missing `@echtdaten`, a `posanzahl` that disagrees with reality and a version this
engine does not know is three edits in the PVS export profile; discovering them one upload at a
time is three round trips, and the second one is always the demoralising one because it looks like
the first fix achieved nothing.

So this module runs the same checks in the same order and *collects* instead of raising:

    validate_bytes(data) -> ValidationResult
        .errors     blocking. Every one of these refuses the delivery today, and the set is
                    deliberately identical to what `read_delivery` + `audit_delivery` refuse —
                    see "No new refusals" below.
        .warnings   non-blocking. The reader's findings, plus the advisory checks this module
                    adds. A delivery with warnings and no errors is audited.
        .preview    what could be read out of the document regardless — invoice count, position
                    count, date range. Present even when the XML does not parse.

**No new refusals, and that is the load-bearing property.** It would be very easy for a "more
comprehensive validation" to start refusing files the engine used to audit, which is the opposite
of the point: this codebase's standing rule is *framing is fatal, positions are advisory*, because
an audit engine that refused every imperfect invoice would refuse exactly the invoices worth
auditing (`app.padnext.schema`, and the header of the subset XSD). `validate_bytes(...).ok` is
true for precisely the deliveries `read_delivery` reads and `audit_delivery` accepts, and
`tests/test_padnext_validation.py::test_ok_agrees_with_the_pipeline_it_reports_on` is the guard.
Everything this module adds beyond the reader is a **warning**.

**The two-tier code namespace is deliberate.** `ValidationError.code` is fine-grained
(`xml_syntax_error`, `echtdaten_undeclared`, `unsupported_version`) and new. The HTTP envelope's
`error_code` is unchanged and still comes from `app.errors.ErrorCode` — a client switching on
`ECHTDATEN_UNDECLARED` or `PADNEXT_SCHEMA_VIOLATION` sees exactly what it saw before, because
`PadnextValidationFailed` adopts the legacy code, status, message and `details` of whichever error
came first. The batched list arrives *beside* that, under `details.errors`. Adding detail without
moving anything a client already reads is the whole reason this is not a new error code.

**Why each message carries `why` as well as `fix`.** A message that says what to do without saying
why is followed until it is inconvenient, and then it is worked around. `echtdaten="1"` is one
character away from `echtdaten="0"` and the fix instruction alone does not distinguish "declare
what your file is" from "make the error go away", so the reason the field exists — Art. 9 GDPR
processing of health data, § 203 StGB for the practice — is part of the payload rather than a
sentence in a document nobody opens at the moment of the error.

German first, English second, in every message. The reader of an error here is a German medical
practice or their PVS vendor; the English half is for the integrator reading a log.
"""

from __future__ import annotations

# `field` is aliased because `ValidationError.field` — the XML field a problem is about — is
# part of the shape the brief asks for, and it shadows `dataclasses.field` inside the class body.
from dataclasses import dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any, Literal

from lxml import etree

from app.config import PadnextSchemaPolicy, Settings, get_settings
from app.errors import ErrorCode
from app.padnext.audit import real_data_allowed
from app.padnext.reader import (
    MAX_XML_BYTES,
    ZIP_MAGIC,
    InvalidXmlError,
    PadnextError,
    PadnextSchemaError,
    _local,
    _log_violations,
    parse_xml,
    read_delivery,
    read_order_files,
    resolve_echtdaten,
    unpack_container,
)
from app.padnext.schema import (
    MAX_REPORTED_VIOLATIONS,
    SchemaViolation,
    describe_violations,
    validate_payload,
)
from app.schemas import Warning_
from app.schemas.padnext import (
    BEHANDLUNGSART_LABEL,
    PadnextDelivery,
    PadnextValidationReport,
)

Severity = Literal["error", "warning", "info"]

#: The version of PADnext this engine's subset schema and audit rules were written against.
SUPPORTED_VERSION = "2.12"

#: How many issues travel in one bucket. A systematic export mistake produces one issue per
#: position, and a response carrying nine hundred of them helps nobody. The counts on
#: `ValidationResult` stay honest, so nothing is hidden by the truncation — the same rule
#: `MAX_REPORTED_VIOLATIONS` follows for schema violations.
MAX_REPORTED_ISSUES = 100

#: How many invoice ids and container members the preview names before it stops.
MAX_PREVIEW_IDS = 20


# ==============================================================================================
# one issue
# ==============================================================================================


@dataclass(frozen=True)
class ValidationError:
    """One thing wrong with a delivery, where it is, why it matters and how to fix it.

    Not `pydantic.ValidationError` and not `app.errors.ErrorCode.VALIDATION_ERROR`. The name is
    the one the brief asks for; nothing in this package imports pydantic's, so there is no
    shadowing, and `app.schemas.padnext.PadnextValidationIssue` is the wire form.

    `blocking` and `severity` are separate on purpose, and the gap between them is this codebase's
    central rule made visible. `padnext_position_without_ziffer` is `severity="error"` — a claimed
    line that cannot be checked is a serious finding — and `blocking=False`, because refusing the
    delivery over it would refuse exactly the export most worth auditing. A UI that collapsed the
    two would either understate the finding or turn it into a wall.
    """

    code: str
    field: str = ""
    path: str = ""
    line: int | None = None
    column: int | None = None
    severity: Severity = "error"
    blocking: bool = True
    #: The one-line form, for the collapsed row. Never empty for a catalogued issue; falls back to
    #: `message_de` for one lifted from a reader finding, which has only the long form.
    summary_de: str = ""
    summary_en: str = ""
    message_de: str = ""
    message_en: str = ""
    why_de: str = ""
    why_en: str = ""
    fix: str = ""
    fix_en: str = ""
    #: The exact shell command that fixes this, when one exists. Rendered as a copyable block.
    command: str = ""

    # -- the legacy envelope, for the one issue that becomes the HTTP error --------------------
    #: The catalog code, status, message and `details` this issue would have produced on its own,
    #: before batching existed. `PadnextValidationFailed` adopts them from the primary error so
    #: that no client sees a contract change. Excluded from `as_dict`.
    legacy_code: ErrorCode = ErrorCode.PADNEXT_UNREADABLE
    legacy_status: int = 422
    legacy_message: str = ""
    legacy_details: dict[str, Any] = dc_field(default_factory=dict)

    @property
    def location(self) -> str:
        """`Zeile 12, Spalte 8 (/rechnungen/rechnung)` — empty when the position is unknown."""
        parts = []
        if self.line:
            parts.append(f"Zeile {self.line}")
        if self.column:
            parts.append(f"Spalte {self.column}")
        where = ", ".join(parts)
        if self.path:
            return f"{where} ({self.path})" if where else f"({self.path})"
        return where

    def as_dict(self) -> dict[str, Any]:
        """The wire shape. `legacy_*` is deliberately absent — it is envelope plumbing."""
        return {
            "code": self.code,
            "field": self.field,
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "blocking": self.blocking,
            "summary_de": self.summary_de,
            "summary_en": self.summary_en,
            "message_de": self.message_de,
            "message_en": self.message_en,
            "why_de": self.why_de,
            "why_en": self.why_en,
            "fix": self.fix,
            "fix_en": self.fix_en,
            "command": self.command,
            "location": self.location,
        }

    def render_de(self) -> str:
        """The long form, for a terminal. What / where / why / how, in that order."""
        head = self.message_de
        if self.location:
            head = f"{head}\n{self.location}"
        blocks = [head]
        if self.why_de:
            blocks.append(f"Warum das wichtig ist:\n{self.why_de}")
        if self.fix:
            blocks.append(f"Lösung:\n{self.fix}")
        if self.command:
            blocks.append(f"Befehl:\n  $ {self.command}")
        return "\n\n".join(blocks)


# ==============================================================================================
# the message catalog
# ==============================================================================================


@dataclass(frozen=True)
class _Spec:
    """A template for one issue code. Filled by `_issue`, which substitutes `{...}` placeholders.

    Kept as data rather than as f-strings at the raise site for one reason: these texts are the
    product. They get rewritten by whoever answers the support mail, and a text that lives beside
    its twelve siblings gets reviewed for consistency of tone and completeness of the four
    sections; the same text inline in a 700-line reader does not.
    """

    field: str
    severity: Severity
    blocking: bool
    #: The collapsed line: ONE clause, ~120 characters, no reasoning and no instruction. It is
    #: what a reader scans to decide which of four problems to open first, so it has to fit on one
    #: line at 390 px — `message_de` routinely does not, and stacking five of those was the wall
    #: this field exists to remove.
    summary_de: str
    summary_en: str
    message_de: str
    message_en: str
    why_de: str = ""
    why_en: str = ""
    fix: str = ""
    fix_en: str = ""
    command: str = ""
    legacy_code: ErrorCode = ErrorCode.PADNEXT_UNREADABLE
    legacy_status: int = 422


_ANONYMISE = "python3 scripts/anonymize_padnext.py {source} -o anonymisiert.padx"

CATALOG: dict[str, _Spec] = {
    # -- the bytes are not a document ----------------------------------------------------------
    "not_xml": _Spec(
        field="",
        severity="error",
        blocking=True,
        summary_de="Kein XML und kein .padx-Container.",
        summary_en="Neither XML nor a .padx container.",
        message_de="Die Datei ist kein XML und kein .padx-Container.",
        message_en="The upload is neither XML nor a .padx container.",
        why_de=(
            "Azmoth liest genau zwei Formate: einen .padx-Container (eine ZIP-Datei mit "
            "Auftragsdatei und Nutzdaten) oder die Nutzdaten-XML allein. Ein PDF, eine "
            "Excel-Tabelle oder ein CSV-Export enthält die kodierten Positionen nicht in einer "
            "Form, die nachgerechnet werden kann."
        ),
        why_en=(
            "The reader accepts a .padx container or a bare payload XML. Nothing else carries "
            "coded positions in a checkable form."
        ),
        fix=(
            "Exportieren Sie in Ihrem PVS erneut und wählen Sie das PADnext-Format (ADL). Die "
            "Ausgabe heißt üblicherweise <Kundennr>_<Datum>_ADL_<Nr>.padx."
        ),
        fix_en="Re-export from your PVS choosing the PADnext (ADL) format.",
    ),
    "xml_too_large": _Spec(
        field="",
        severity="error",
        blocking=True,
        summary_de="Datei zu groß: {size} Bytes (Grenze {limit}).",
        summary_en="File too large: {size} bytes (limit {limit}).",
        message_de=(
            "Die Datei ist {size} Bytes groß. Die Obergrenze für eine einzelne Lieferung liegt "
            "bei {limit} Bytes."
        ),
        message_en="The payload is {size} bytes, above the {limit}-byte limit for one delivery.",
        why_de=(
            "Die Grenze schützt den Dienst vor einer Datei, die den Speicher eines Prozesses "
            "füllt, bevor irgendetwas geprüft werden konnte."
        ),
        why_en=(
            "The limit protects the process from a file that exhausts memory before any check "
            "could run."
        ),
        fix=(
            "Teilen Sie den Export in mehrere Lieferungen auf — oder nutzen Sie die "
            "Stapelprüfung, die viele kleinere Dateien in einem Durchgang prüft."
        ),
        fix_en="Split the export into several deliveries, or use the batch endpoint.",
    ),
    "xml_doctype_refused": _Spec(
        field="",
        severity="error",
        blocking=True,
        summary_de="DOCTYPE-Deklaration wird abgelehnt.",
        summary_en="DOCTYPE declaration refused.",
        message_de=(
            "Das Dokument deklariert eine DOCTYPE-Definition. Diese wird abgelehnt, ohne den "
            "Inhalt zu lesen."
        ),
        message_en="The document declares a DOCTYPE, which this reader refuses outright.",
        why_de=(
            "Eine DOCTYPE-Deklaration darf interne Entities definieren, und die lassen sich so "
            "verschachteln, dass ein kleines Dokument beim Einlesen auf Gigabytes anwächst "
            "(„billion laughs“). Die Deklaration ganz zu verweigern entfernt diese Klasse von "
            "Angriffen vollständig; sie zu begrenzen würde sie nur verschieben. "
            "PADnext-Nutzdaten "
            "brauchen keine DOCTYPE-Deklaration."
        ),
        why_en=(
            "A DOCTYPE may define internal entities that expand exponentially. Refusing the "
            "declaration removes the class; bounding it would not. PADnext payloads need none."
        ),
        fix=(
            "Entfernen Sie die Zeile <!DOCTYPE ...> aus der Datei. Ein konformer PADnext-Export "
            "erzeugt sie nicht — wenn sie da ist, hat ein Zwischenschritt sie eingefügt."
        ),
        fix_en="Remove the <!DOCTYPE ...> declaration; a conforming PADnext export emits none.",
    ),
    "xml_syntax_error": _Spec(
        field="",
        severity="error",
        blocking=True,
        summary_de="XML nicht wohlgeformt.",
        summary_en="XML is not well formed.",
        message_de="Ungültiges XML: {detail}",
        message_en="Invalid XML: {detail}",
        why_de=(
            "Ein Dokument, das nicht wohlgeformt ist, kann nicht geprüft werden — es ist noch "
            "nicht entschieden, was darin überhaupt steht. Die genannte Stelle ist die, an der "
            "der Parser aufgegeben hat; die Ursache liegt oft eine Zeile davor."
        ),
        why_en=(
            "A document that is not well formed cannot be validated at all. The position given is "
            "where the parser gave up; the cause is often one line earlier."
        ),
        fix=(
            "Häufige Ursachen, in dieser Reihenfolge:\n"
            "  1. Umlaute oder Sonderzeichen in einer anderen Kodierung als der deklarierten — "
            "PADnext verlangt UTF-8.\n"
            "  2. Ein kaufmännisches Und (&) in einem Freitextfeld, das nicht als &amp; "
            "geschrieben ist. Dasselbe gilt für < und >.\n"
            "  3. Ein nicht geschlossenes Element, meist weil der Export abgebrochen wurde. "
            "Prüfen Sie, ob die Datei vollständig ist.\n"
            "  4. Ein Zeichen aus einer Zwischenverarbeitung (Suchen-und-Ersetzen in einem "
            "Editor, Zeilenumbrüche einer Übertragung)."
        ),
        fix_en=(
            "Common causes: wrong encoding (PADnext requires UTF-8), an unescaped & < or > in a "
            "free-text field, a truncated export, or an editing step in between."
        ),
        legacy_code=ErrorCode.INVALID_XML,
        legacy_status=400,
    ),
    "container_unreadable": _Spec(
        field="",
        severity="error",
        blocking=True,
        summary_de="ZIP-Container lässt sich nicht öffnen.",
        summary_en="The ZIP container cannot be opened.",
        message_de=(
            "Die Datei beginnt wie ein ZIP-Container, lässt sich aber nicht öffnen: {detail}"
        ),
        message_en="The file starts like a ZIP container but cannot be opened: {detail}",
        why_de=(
            "Ein .padx ist eine ZIP-Datei. Die Signatur stimmt, das Verzeichnis darin nicht — "
            "meist ein abgebrochener Download oder eine Übertragung im Textmodus."
        ),
        why_en=(
            "A .padx is a ZIP. The magic bytes match and the directory does not: usually a "
            "truncated download or a transfer in text mode."
        ),
        fix=(
            "Übertragen Sie die Datei erneut (binär, nicht als Text) oder exportieren Sie sie im "
            "PVS neu. Ob der Container heil ist, sagt Ihnen auch: unzip -t datei.padx"
        ),
        fix_en=(
            "Re-transfer the file in binary mode or re-export it. `unzip -t file.padx` checks it."
        ),
        command="unzip -t {source}",
    ),
    "container_without_payload": _Spec(
        field="",
        severity="error",
        blocking=True,
        summary_de="Container enthält keine Nutzdaten-XML.",
        summary_en="Container holds no payload XML.",
        message_de=(
            "Der Container enthält keine Nutzdaten-XML. Erwartet wird ein Mitglied namens "
            "<Kundennr>_<Datum>_<Typ>_<Nr>_padx.xml."
        ),
        message_en=(
            "The container holds no payload XML. Expected a member named "
            "<kundennr>_<datum>_<typ>_<nr>_padx.xml."
        ),
        why_de=(
            "Ein PADnext-Container trägt zwei Dokumente: die Auftragsdatei (.auf), die die "
            "Lieferung beschreibt, und die Nutzdaten (_padx.xml), die die Rechnungen enthalten. "
            "Ohne die zweite gibt es nichts zu prüfen."
        ),
        why_en=(
            "A PADnext container carries the order file (.auf) and the payload (_padx.xml). "
            "Without the payload there is nothing to audit."
        ),
        fix=(
            "Prüfen Sie den Inhalt des Containers mit `unzip -l datei.padx`. Fehlt die "
            "_padx.xml, ist der Export unvollständig — bitte im PVS erneut erzeugen."
        ),
        fix_en="List the container with `unzip -l file.padx`; if the payload is absent, re-export.",
        command="unzip -l {source}",
    ),
    "container_too_large": _Spec(
        field="",
        severity="error",
        blocking=True,
        summary_de="Container überschreitet eine Sicherheitsgrenze.",
        summary_en="Container exceeds a safety limit.",
        message_de="Der Container überschreitet eine Sicherheitsgrenze: {detail}",
        message_en="The container exceeds a safety limit: {detail}",
        why_de=(
            "Ein Archiv kann sich beim Entpacken um ein Vielfaches seiner Größe ausdehnen, und "
            "eine Datei, die den Speicher des Dienstes füllt, bevor überhaupt etwas geprüft "
            "wurde, wird nicht entpackt. Geprüft werden die Anzahl der Mitglieder und die "
            "entpackte Gesamtgröße."
        ),
        why_en=(
            "An archive can expand to many times its size, and a file that exhausts the service's "
            "memory before any check runs is not unpacked. The member count and the total "
            "uncompressed size are both bounded."
        ),
        fix=(
            "Ein PADnext-Container trägt eine Auftragsdatei und eine Nutzdatendatei. Wenn Ihrer "
            "sehr viel mehr enthält, ist es vermutlich ein Sammelarchiv — nutzen Sie dann die "
            "Stapelprüfung, die viele Lieferungen einzeln annimmt."
        ),
        fix_en=(
            "A PADnext container holds an order file and a payload. For an archive of many "
            "deliveries, use the batch endpoint instead."
        ),
    ),
    "container_member_escapes": _Spec(
        field="",
        severity="error",
        blocking=True,
        summary_de="Ein Container-Mitglied verweist aus dem Archiv heraus.",
        summary_en="A container member escapes the archive root.",
        message_de="Ein Mitglied des Containers verweist aus dem Archiv heraus: {value!r}",
        message_en="A container member escapes the archive root: {value!r}",
        why_de=(
            "Ein Dateiname mit „..“ oder einem absoluten Pfad kann beim Entpacken Dateien "
            "außerhalb des Zielverzeichnisses überschreiben. In einer PADnext-Lieferung gibt es "
            "keinen legitimen Grund dafür."
        ),
        why_en=(
            "A member name containing '..' or an absolute path can overwrite files outside the "
            "target directory when unpacked. No legitimate delivery does this."
        ),
        fix=(
            "Diese Datei nicht entpacken. Erzeugen Sie den Export im PVS neu; entsteht der Name "
            "wieder, melden Sie es dem Hersteller Ihres PVS."
        ),
        fix_en="Do not unpack this file. Re-export, and report it to your PVS vendor if it recurs.",
    ),
    # -- the document is the wrong document ----------------------------------------------------
    "order_file_uploaded": _Spec(
        field="auftrag",
        severity="error",
        blocking=True,
        summary_de="Auftragsdatei hochgeladen, nicht die Nutzdaten.",
        summary_en="Order file uploaded, not the payload.",
        message_de=(
            "Das ist die PADnext-Auftragsdatei (auftrag), nicht die Nutzdaten. Sie beschreibt die "
            "Lieferung, enthält aber keine Rechnungspositionen."
        ),
        message_en=(
            "This is a PADnext Auftragsdatei (order file), not the payload. It describes the "
            "delivery and carries no billing positions."
        ),
        why_de=(
            "Geprüft werden die Positionen, und die stehen ausschließlich in der Nutzdatendatei."
        ),
        why_en="The audit reads positions, and only the payload document carries them.",
        fix=(
            "Laden Sie die *_padx.xml hoch — oder besser den ganzen .padx-Container, der beide "
            "Dokumente enthält. Nur mit dem Container kann Azmoth auch die Angaben der "
            "Auftragsdatei (echtdaten, Transfernummer, Verschlüsselung) auswerten."
        ),
        fix_en=(
            "Upload the *_padx.xml, or better the whole .padx container so the order file's "
            "declarations are read too."
        ),
    ),
    "unsupported_root": _Spec(
        field="",
        severity="error",
        blocking=True,
        summary_de="Unbekanntes Wurzelelement <{value}>.",
        summary_en="Unsupported root element <{value}>.",
        message_de=(
            "Unbekanntes Wurzelelement <{value}>. Dieser Leser verarbeitet <rechnungen> "
            "(Nachrichtentyp ADL)."
        ),
        message_en=(
            "Unsupported PADnext payload root <{value}>. This reader handles <rechnungen> "
            "(message type ADL)."
        ),
        why_de=(
            "PADnext kennt mehrere Nachrichtentypen — Quittungen, Statusmeldungen, "
            "Abrechnungslieferungen. Nur die Abrechnungslieferung (ADL) enthält Positionen, die "
            "gegen die GOÄ nachgerechnet werden können."
        ),
        why_en=(
            "PADnext defines several message types; only the ADL delivery carries positions that "
            "can be recomputed against the GOÄ."
        ),
        fix=(
            "Wählen Sie im PVS-Export den Nachrichtentyp ADL (Abrechnungsdatenlieferung). Eine "
            "Quittung oder Statusmeldung des Rechenzentrums ist hier nicht auswertbar."
        ),
        fix_en="Export message type ADL. A receipt or status message cannot be audited here.",
    ),
    "xsd_violation": _Spec(
        field="",
        severity="error",
        blocking=True,
        summary_de="Schema-Verletzung im Element '{field}'.",
        summary_en="Schema violation in element '{field}'.",
        message_de="Schema-Verletzung: {detail}",
        message_en="Schema violation: {detail}",
        why_de=(
            "Diese Prüfung beantwortet genau eine Frage: Ist das überhaupt eine "
            "ADL-Abrechnungslieferung? Falsches Wurzelelement, falscher Namensraum, fehlender "
            "Nachrichtentyp, ein Zähler, der keine Zahl ist, eine Behandlungsart außerhalb der "
            "definierten Werte. Was diese Prüfung nicht bestanden hat, kann nicht geprüft oder "
            "nicht bewertet werden — deshalb wird die Lieferung abgewiesen und nicht mit einem "
            "Hinweis versehen."
        ),
        why_en=(
            "This check answers one question: is this an ADL delivery at all? What fails it "
            "cannot be audited or cannot be priced, which is why it is a refusal and not a note."
        ),
        fix=(
            "Die Stelle steht oben. Melden Sie die Meldung samt Zeilennummer dem Hersteller Ihres "
            "PVS — es ist ein Fehler im Export, nicht in Ihren Daten.\n"
            "Wenn Ihr Export ansonsten korrekt ist und Sie den Bericht trotzdem brauchen: mit "
            "PADNEXT_SCHEMA_POLICY=warn wird die Abweichung zu einem Hinweis auf dem "
            "Prüfbericht, und die Prüfung läuft durch."
        ),
        fix_en=(
            "Report the message and line to your PVS vendor. PADNEXT_SCHEMA_POLICY=warn turns "
            "the deviation into a note on the report and audits anyway."
        ),
        legacy_code=ErrorCode.PADNEXT_SCHEMA_VIOLATION,
    ),
    "no_invoices": _Spec(
        field="rechnung",
        severity="error",
        blocking=True,
        summary_de="Keine Rechnung mit Abrechnungsfall enthalten.",
        summary_en="No invoice with an Abrechnungsfall.",
        message_de=(
            "Die Nutzdaten enthalten keine <rechnung> mit einem <abrechnungsfall>. Es gibt "
            "nichts zu prüfen."
        ),
        message_en="The payload contains no <rechnung> with an <abrechnungsfall>.",
        why_de=(
            "Ein leerer Prüfbericht wäre von einem Bericht ohne Befunde nicht zu "
            "unterscheiden — „alles in Ordnung“ und „es war nichts drin“ sind zwei sehr "
            "verschiedene Aussagen."
        ),
        why_en=(
            "An empty report is indistinguishable from a clean one. 'Nothing wrong' and 'nothing "
            "there' are different statements."
        ),
        fix=(
            "Prüfen Sie im PVS den Zeitraum und den Filter des Exports. Häufig ist der Zeitraum "
            "gewählt, in dem noch nicht abgerechnet wurde."
        ),
        fix_en="Check the export's date range and filter; often the period simply has no invoices.",
    ),
    "delivery_unreadable": _Spec(
        field="",
        severity="error",
        blocking=True,
        summary_de="Lieferung nicht lesbar.",
        summary_en="The delivery cannot be read.",
        message_de="Die Lieferung kann nicht gelesen werden: {detail}",
        message_en="The delivery cannot be read: {detail}",
        why_de=(
            "Der Leser hat die Lieferung abgewiesen, ohne dass diese Prüfung den Grund einer "
            "der bekannten Kategorien zuordnen konnte. Die Meldung oben ist die des Lesers "
            "selbst und ist die maßgebliche Aussage."
        ),
        why_en=(
            "The reader refused the delivery for a reason this validation could not place in one "
            "of its known categories. The message above is the reader's own and is authoritative."
        ),
        fix=(
            "Prüfen Sie die Meldung oben. Wenn sie unverständlich ist, ist es ein Fehler auf "
            "unserer Seite — bitte melden Sie sie mit dem Dateinamen."
        ),
        fix_en=(
            "Act on the message above. If it is not actionable, that is a defect on our side — "
            "please report it with the filename."
        ),
    ),
    # -- the delivery has not declared itself --------------------------------------------------
    "echtdaten_undeclared": _Spec(
        field="echtdaten",
        severity="error",
        blocking=True,
        summary_de="echtdaten fehlt{where_short}.",
        summary_en="echtdaten is missing{where_short}.",
        message_de=(
            "Das Feld 'echtdaten' fehlt oder ist ungültig{where}. Diese Lieferung wird abgewiesen."
        ),
        message_en=(
            "The delivery does not declare whether it holds production data{where}. An undeclared "
            "delivery is refused rather than assumed to be synthetic."
        ),
        why_de=(
            "Ohne diese Angabe kann Azmoth nicht feststellen, ob die Lieferung echte "
            "Patientendaten enthält. Eine fehlende Angabe wird aus Sicherheitsgründen NICHT als "
            "„Testdaten“ angenommen, denn die Folgen sind nicht symmetrisch: eine "
            "anonymisierte "
            "Lieferung, die es nicht gesagt hat, kostet einen Befehl und einen zweiten Upload — "
            "eine echte, die durchgelassen wird, kostet eine Verarbeitung von Gesundheitsdaten "
            "ohne Rechtsgrundlage (Art. 9 DSGVO), ein Risiko nach § 203 StGB für die Praxis und "
            "eine Meldung."
        ),
        why_en=(
            "Without the declaration this deployment cannot tell whether the delivery holds real "
            "patients, and a missing declaration is not read as 'test data'. The costs are "
            "asymmetric: a re-upload versus an Art. 9 GDPR processing with no lawful basis."
        ),
        fix=(
            "1. Automatisiert: führen Sie das Anonymisierungsskript aus und laden Sie dessen "
            "Ausgabe hoch. Es setzt echtdaten=\"false\" in der Auftragsdatei und in den "
            "Nutzdaten und entfernt zugleich die Patientenidentität.\n"
            "2. Manuell: ergänzen Sie im PVS-Exportprofil das Attribut echtdaten=\"0\" (für "
            "Testdaten) beziehungsweise echtdaten=\"1\" (für Echtdaten, nur mit "
            "Rechtsgrundlage) am Element <auftrag>.\n"
            "Nur für Entwicklung: PADNEXT_ALLOW_REAL_DATA=1 nimmt Lieferungen ohne Erklärung an. "
            "Nicht für Produktionsdaten."
        ),
        fix_en=(
            "Run scripts/anonymize_padnext.py and upload its output, or fix the export to emit "
            "echtdaten=\"0\" on <auftrag>. Set PADNEXT_ALLOW_REAL_DATA=1 only with a lawful basis."
        ),
        command=_ANONYMISE,
        legacy_code=ErrorCode.ECHTDATEN_UNDECLARED,
    ),
    "echtdaten_unrecognised": _Spec(
        field="echtdaten",
        severity="error",
        blocking=True,
        summary_de="echtdaten trägt den unbekannten Wert '{value}'.",
        summary_en="echtdaten carries the unknown value '{value}'.",
        message_de=(
            "Das Feld 'echtdaten' enthält den Wert '{value}', der in der PADnext-Spezifikation "
            "nicht definiert ist (erlaubt sind '0'/'false' für Testdaten und '1'/'true' für "
            "Echtdaten). Diese Lieferung wird abgewiesen."
        ),
        message_en=(
            "The field 'echtdaten' says '{value}', which the PADnext specification does not "
            "define (only '0'/'false' and '1'/'true'). The delivery is refused."
        ),
        why_de=(
            "Ein deutsches PVS, das echtdaten=\"ja\" schreibt, meint: ja, das sind echte Daten. "
            "Ein Leser, der das Wort nicht kennt und auf „Testdaten“ zurückfällt, kehrt die "
            "Aussage der Datei genau um — und tut es lautlos. Deshalb wird jeder Wert außerhalb "
            "der vier definierten abgewiesen, in beide Richtungen: „nein“ ebenso wie „ja“. "
            "Eine "
            "Regel, die Deutsch zu interpretieren versucht, trifft irgendwann ein Wort, das sie "
            "falsch versteht."
        ),
        why_en=(
            "A PVS writing echtdaten=\"ja\" means yes, this is real data. A reader that falls "
            "back to 'test data' inverts the file's own statement, silently. So every value "
            "outside the four defined ones is refused, in both directions."
        ),
        fix=(
            "1. Im PVS-Exportprofil: echtdaten=\"0\" für Testdaten, echtdaten=\"1\" für "
            "Echtdaten. Kein „ja“, kein „nein“, kein leerer Wert.\n"
            "2. Sofort: führen Sie das Anonymisierungsskript aus, es schreibt den korrekten Wert."
        ),
        fix_en=(
            "Emit echtdaten=\"0\" or echtdaten=\"1\" from the export profile, or run "
            "scripts/anonymize_padnext.py which writes the correct value."
        ),
        command=_ANONYMISE,
        legacy_code=ErrorCode.ECHTDATEN_UNDECLARED,
    ),
    "real_data_refused": _Spec(
        field="echtdaten",
        severity="error",
        blocking=True,
        summary_de="Als Echtdaten gekennzeichnet — Verarbeitung nicht gestattet.",
        summary_en="Flagged as production data — processing not permitted.",
        message_de=(
            "Die Lieferung ist als Echtdaten gekennzeichnet (echtdaten=\"{value}\"). Das "
            "Hochladen von Echtdaten ist in diesem Betrieb nicht gestattet."
        ),
        message_en=(
            "The delivery is flagged as production data (echtdaten=\"{value}\"). This deployment "
            "processes synthetic data only and has refused it."
        ),
        why_de=(
            "Dieser Betrieb verarbeitet ausschließlich pseudonymisierte Testdaten. Das ist keine "
            "Aussage über Ihre Berechtigung, sondern über diese Installation: es gibt hier keine "
            "Rechtsgrundlage und keine technisch-organisatorischen Maßnahmen für eine "
            "Verarbeitung nach Art. 9 DSGVO."
        ),
        why_en=(
            "This deployment holds no lawful basis and no controls for Art. 9 GDPR processing. "
            "Nothing about the caller is being denied — the content is refused."
        ),
        fix=(
            "1. Führen Sie das Anonymisierungsskript aus und laden Sie dessen Ausgabe hoch.\n"
            "2. Nur für einen Betrieb mit Rechtsgrundlage und den Maßnahmen aus "
            "docs/compliance/PRIVATE_DATA_WARNING.md: PADNEXT_ALLOW_REAL_DATA=1."
        ),
        fix_en=(
            "Run scripts/anonymize_padnext.py and upload its output. Set PADNEXT_ALLOW_REAL_DATA=1 "
            "only with a lawful basis and the controls in docs/compliance/PRIVATE_DATA_WARNING.md."
        ),
        command=_ANONYMISE,
        legacy_code=ErrorCode.REAL_DATA_REFUSED,
    ),
    # -- advisory ------------------------------------------------------------------------------
    "transfernr_missing": _Spec(
        field="transfernr",
        severity="warning",
        blocking=False,
        summary_de="Auftragsdatei nennt keine Transfernummer.",
        summary_en="The order file carries no transfer number.",
        message_de="Die Auftragsdatei nennt keine Transfernummer (auftrag/@transfernr).",
        message_en="The order file carries no transfer number (auftrag/@transfernr).",
        why_de=(
            "Die Transfernummer ist die Kennung, unter der Praxis und Rechenzentrum dieselbe "
            "Lieferung benennen. Ohne sie lässt sich ein Prüfbericht später keiner "
            "Übermittlung "
            "mehr zuordnen — der Bericht selbst ist davon unberührt."
        ),
        why_en=(
            "The transfer number is how practice and clearing centre name the same delivery. "
            "Without it a report cannot be tied back to a transmission later."
        ),
        fix=(
            "Ergänzen Sie im PVS-Exportprofil das Attribut transfernr am Element <auftrag>. Es "
            "ist eine laufende Nummer je Empfänger."
        ),
        fix_en="Add the transfernr attribute to <auftrag> in the export profile.",
    ),
    "transfernr_unknown": _Spec(
        field="transfernr",
        severity="info",
        blocking=False,
        summary_de="Ohne Auftragsdatei: Transfernummer unbekannt.",
        summary_en="No order file, so the transfer number is unknown.",
        message_de=(
            "Ohne Auftragsdatei ist die Transfernummer nicht bekannt. Es wurden nur die Nutzdaten "
            "hochgeladen."
        ),
        message_en="No order file was supplied, so the transfer number is unknown.",
        why_de=(
            "Nutzdaten allein sind eine unterstützte Eingabe — die Transfernummer, das "
            "Verschlüsselungsverfahren und die maßgebliche echtdaten-Angabe stehen aber in der "
            "Auftragsdatei und fehlen dann im Bericht."
        ),
        why_en=(
            "A bare payload is a supported input, but the transfer number, the encryption method "
            "and the authoritative echtdaten declaration all live in the order file."
        ),
        fix=(
            "Laden Sie den vollständigen .padx-Container hoch, wenn diese Angaben im Bericht "
            "stehen sollen."
        ),
        fix_en="Upload the full .padx container if those fields should appear on the report.",
    ),
    "unsupported_version": _Spec(
        field="version",
        severity="warning",
        blocking=False,
        summary_de="PADnext-Version {value} statt {expected}.",
        summary_en="PADnext version {value} instead of {expected}.",
        message_de=(
            "PADnext-Version {value} erkannt; geprüft wird gegen Version {expected}. Die "
            "Lieferung wurde trotzdem gelesen."
        ),
        message_en=(
            "PADnext version {value} detected; this engine validates against {expected}. The "
            "delivery was read anyway."
        ),
        why_de=(
            "Der Aufbau von PADnext ist zwischen den Nebenversionen stabil, deshalb ist das ein "
            "Hinweis und keine Ablehnung. Sollten in Ihrer Version Felder anders belegt sein, "
            "können einzelne Positionen unvollständig gelesen worden sein — jede solche Stelle "
            "steht als eigener Hinweis im Bericht."
        ),
        why_en=(
            "PADnext framing is stable across minor versions, so this is a note rather than a "
            "refusal. Anything actually misread is reported as its own finding."
        ),
        fix=(
            "Stellen Sie Ihr PVS auf den Export von PADnext {expected} um, wenn es das anbietet. "
            "Solange die Hinweise im Bericht leer bleiben, ist nichts zu tun."
        ),
        fix_en="Update the PVS export to PADnext {expected} if it offers that.",
    ),
    "version_unknown": _Spec(
        field="version",
        severity="info",
        blocking=False,
        summary_de="Keine PADnext-Version angegeben.",
        summary_en="No PADnext version given.",
        message_de=(
            "Die Lieferung nennt keine PADnext-Version (nachrichtentyp/@version). Geprüft wurde "
            "gegen Version {expected}."
        ),
        message_en=(
            "The delivery names no PADnext version (nachrichtentyp/@version). Validated against "
            "{expected}."
        ),
        why_de=(
            "Ohne Versionsangabe kann nicht geprüft werden, ob der Aufbau der Datei zu den "
            "Annahmen dieses Lesers passt."
        ),
        why_en="Without a version there is no way to check the framing against our assumptions.",
        fix="Ergänzen Sie im Export das Attribut version am Element <nachrichtentyp>.",
        fix_en="Add the version attribute to <nachrichtentyp>.",
    ),
}


#: The reader's blanket `PadnextError` refusals, keyed by a fragment of the message each raises.
#:
#: Sniffing a message is not a nice way to classify an exception, and it is the honest trade here.
#: The alternative is a subclass per refusal in `reader.py` — six new exception types whose only
#: job is to be caught once, in this module, by a validator the reader knows nothing about. That
#: is a larger change to the security-relevant reader than it is worth, and the failure mode of
#: this version is contained: an unrecognised message falls through to the generic code below,
#: which is still blocking, still a 422, and still carries the reader's own text as the message a
#: user reads. Nothing becomes *wrong*, only less specific — and
#: `test_every_reader_refusal_is_classified` fails if a message is reworded, so it does not decay
#: silently either.
_READER_REFUSALS: tuple[tuple[str, str], ...] = (
    ("above the safety limit", "container_too_large"),
    ("escapes the archive root", "container_member_escapes"),
    ("cannot be opened", "container_unreadable"),
    ("above the", "xml_too_large"),
    ("DOCTYPE", "xml_doctype_refused"),
    ("does not start with", "not_xml"),
)


def classify_refusal(message: str, *, fallback: str) -> str:
    """Which issue code one of the reader's `PadnextError` messages corresponds to."""
    for fragment, code in _READER_REFUSALS:
        if fragment in message:
            return code
    return fallback


def _issue(code: str, **subs: Any) -> ValidationError:
    """Build one issue from the catalog, substituting `{...}` placeholders into every text.

    A code that is not in the catalog is a programming error and raises: an issue with an empty
    German message is worse than a crash in CI, because it reaches a practice as a blank error.
    """
    spec = CATALOG[code]

    def fill(text: str) -> str:
        if not text or "{" not in text:
            return text
        try:
            return text.format(**subs)
        except (KeyError, IndexError):  # pragma: no cover - a template with an unbound name
            return text

    line = subs.get("line")
    return ValidationError(
        code=code,
        field=str(subs.get("field", spec.field)),
        path=str(subs.get("path", "")),
        line=int(line) if isinstance(line, int) and line > 0 else None,
        column=subs.get("column") if isinstance(subs.get("column"), int) else None,
        severity=spec.severity,
        blocking=spec.blocking,
        summary_de=fill(spec.summary_de),
        summary_en=fill(spec.summary_en),
        message_de=fill(spec.message_de),
        message_en=fill(spec.message_en),
        why_de=fill(spec.why_de),
        why_en=fill(spec.why_en),
        fix=fill(spec.fix),
        fix_en=fill(spec.fix_en),
        command=fill(spec.command),
        legacy_code=spec.legacy_code,
        legacy_status=spec.legacy_status,
        legacy_message=str(subs.get("legacy_message") or "") or fill(spec.message_de),
        legacy_details=dict(subs.get("legacy_details") or {}),
    )


#: How wide the collapsed one-line summary may be before it is cut. Chosen to fit one line at
#: 390 px in the web UI's body size; the catalogued summaries are all well inside it and this only
#: ever bites on a reader finding, whose text was written for a report rather than for a row.
MAX_SUMMARY_CHARS = 120


def one_line(text: str) -> str:
    """The first sentence of `text`, at most `MAX_SUMMARY_CHARS`, ending in a full stop or an ellipsis.

    Cut at a word boundary, never mid-word: a summary reading "Feld 'posanzahl' enthält keine lesb…"
    costs the reader the one piece of information the line had. Falls back to the whole string when
    it is already short enough, which is the common case.
    """
    collapsed = " ".join(text.split())
    if not collapsed:
        return ""
    # A sentence boundary is a better cut than a length one when there is one in range.
    stop = collapsed.find(". ")
    if 0 < stop + 1 <= MAX_SUMMARY_CHARS:
        return collapsed[: stop + 1]
    if len(collapsed) <= MAX_SUMMARY_CHARS:
        return collapsed
    clipped = collapsed[: MAX_SUMMARY_CHARS - 1]
    spaced = clipped.rsplit(" ", 1)[0] if " " in clipped else clipped
    return f"{spaced} …"


def issue_from_finding(finding: Warning_) -> ValidationError:
    """Carry one of the reader's findings into the same shape, keeping its existing `type` as code.

    The reader's finding types (`padnext_position_without_ziffer`, …) are already on every audit
    report and already read by the web UI, so they are not renamed into this module's namespace.
    Only the reader's German prose exists for them; `message_en` stays empty rather than being
    machine-translated, and the UI falls back to the German — which is the primary language here
    anyway.

    Never blocking. A reader finding is by construction something the reader carried on past, and
    promoting one to an error here would refuse deliveries that are audited today.
    """
    return ValidationError(
        code=finding.type,
        field=finding.ziffer or "",
        severity=finding.severity,
        blocking=False,
        # The reader has only a long form, so the collapsed line is derived from it rather than
        # left empty — an empty summary would render as a row with a badge and no sentence.
        summary_de=one_line(finding.message),
        message_de=finding.message,
        why_de=(
            "Diese Stelle wurde gelesen, aber nicht vollständig geprüft. Sie erscheint als "
            "Hinweis auf dem Prüfbericht."
            if finding.severity != "info"
            else ""
        ),
        fix=(
            "Prüfen Sie die genannte Position im PVS. Ein einzelner nicht prüfbarer Posten "
            "verhindert die Prüfung der übrigen nicht."
            if finding.severity == "error"
            else ""
        ),
    )


def issue_from_violation(violation: SchemaViolation, *, blocking: bool = True) -> ValidationError:
    """One schema violation as an issue, with libxml2's line, column and a readable element path."""
    base = _issue(
        "xsd_violation",
        detail=violation.message,
        field=violation.element,
        path=violation.path,
        line=violation.line,
        column=violation.column,
    )
    if blocking:
        return base
    return ValidationError(**{**base.__dict__, "blocking": False, "severity": "warning"})


# ==============================================================================================
# what could be read anyway
# ==============================================================================================


@dataclass
class ParsedPreview:
    """What the document says, read as tolerantly as possible and trusted for nothing.

    This exists for one reason: "everything is broken" and "one field is wrong" produce very
    different next actions from the person holding the file, and an error response that shows
    3 invoices and 47 positions alongside a single missing attribute is telling the truth about
    which of the two it is.

    Deliberately computed from its own recovering parse rather than from the audited delivery, so
    it is available for a document that does not parse at all — a truncated export still shows the
    invoices it did manage to write. Nothing here is used for billing, for pricing or for any
    verdict; it is a description of the file, not a reading of it.
    """

    invoice_count: int = 0
    case_count: int = 0
    #: `<goziffer>` elements. Other position types are counted separately, because the audit does
    #: not model them and a single total would overstate what was checked.
    position_count: int = 0
    other_position_count: int = 0
    first_service_date: str | None = None
    last_service_date: str | None = None
    nachrichtentyp: str = ""
    version: str = ""
    transfernr: str = ""
    echtdaten_declared: str | None = None
    invoice_ids: list[str] = dc_field(default_factory=list)
    container_members: list[str] = dc_field(default_factory=list)
    first_invoice: dict[str, Any] | None = None
    #: True when the preview came from a recovering parse of a document that is not well formed,
    #: so a reader knows the counts are a floor rather than the truth.
    recovered: bool = False
    #: The line of the element that should carry `@echtdaten`, so an *absent* attribute still has
    #: a position to point at — "line 38, on <rechnungen>" is where to type it. Only ever the
    #: payload root: the order file is read with `xml.etree`, which does not track lines, and it
    #: is only the declaration site when it declared something (`resolve_echtdaten`).
    declaration_line: int | None = None

    @property
    def date_range(self) -> str:
        """`01.09.2026 bis 15.09.2026`, the single date, or empty. German order, for a German UI."""
        first, last = self.first_service_date, self.last_service_date
        if not first:
            return ""
        if not last or last == first:
            return _de_date(first)
        return f"{_de_date(first)} bis {_de_date(last)}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "invoice_count": self.invoice_count,
            "case_count": self.case_count,
            "position_count": self.position_count,
            "other_position_count": self.other_position_count,
            "first_service_date": self.first_service_date,
            "last_service_date": self.last_service_date,
            "date_range": self.date_range,
            "nachrichtentyp": self.nachrichtentyp,
            "version": self.version,
            "transfernr": self.transfernr,
            "echtdaten_declared": self.echtdaten_declared,
            "invoice_ids": self.invoice_ids,
            "container_members": self.container_members,
            "first_invoice": self.first_invoice,
            "recovered": self.recovered,
            "declaration_line": self.declaration_line,
        }


def _de_date(iso: str) -> str:
    """`2026-09-01` → `01.09.2026`. Anything else is returned untouched rather than guessed at."""
    parts = iso.split("-")
    if len(parts) == 3 and len(parts[0]) == 4 and all(p.isdigit() for p in parts):
        return f"{parts[2]}.{parts[1]}.{parts[0]}"
    return iso


def _tolerant_parser() -> etree.XMLParser:
    """The preview's parser: recovering, and otherwise as locked down as the validator's.

    `recover=True` is the whole point — a truncated export is exactly the case where showing what
    *was* written is worth something. It is safe to pair with the rest because recovery only makes
    libxml2 continue past a syntax error; it does not re-enable entity expansion, DTD loading or
    network access, all of which stay off. The size ceiling (`MAX_XML_BYTES`) has already been
    applied by the caller, and `huge_tree=False` keeps the depth and node limits in force.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        recover=True,
    )


def build_preview(
    payload: bytes, *, order: dict | None = None, members: list[str] | None = None
) -> ParsedPreview:
    """Count what the payload contains, whether or not it is valid, well formed or complete.

    Namespace-agnostic by local name. Files in the wild vary on the prefix and on declaring the
    namespace at all, and a preview that showed zero invoices for a file with a typo'd `xmlns`
    would be telling the reader the opposite of what is wrong.
    """
    order = order or {}
    preview = ParsedPreview(
        container_members=list(members or [])[:MAX_PREVIEW_IDS],
        transfernr=str(order.get("transfernr", "") or ""),
        echtdaten_declared=order.get("echtdaten_declared"),
        nachrichtentyp=str(order.get("nachrichtentyp", "") or ""),
        version=str(order.get("version", "") or ""),
    )
    if not payload:
        return preview

    try:
        root = etree.fromstring(payload, _tolerant_parser())
    except etree.XMLSyntaxError:
        # Recovery itself gave up — nothing at all was salvageable.
        preview.recovered = True
        return preview
    if root is None:  # pragma: no cover - libxml2 returns None for an empty document
        preview.recovered = True
        return preview

    dates: list[str] = []
    first_invoice_positions = 0
    first_invoice_id = ""
    first_behandlungsart: str | None = None

    for element in root.iter():
        if not isinstance(element.tag, str):
            continue  # a comment or a processing instruction
        name = _local(element.tag)
        if name == "rechnung":
            preview.invoice_count += 1
            if len(preview.invoice_ids) < MAX_PREVIEW_IDS:
                preview.invoice_ids.append(element.get("id", "") or "")
            if preview.invoice_count == 1:
                first_invoice_id = element.get("id", "") or ""
        elif name == "abrechnungsfall":
            preview.case_count += 1
        elif name == "goziffer":
            preview.position_count += 1
            if preview.invoice_count <= 1:
                first_invoice_positions += 1
        elif name in {"gozziffer", "entschaedigung", "auslagen", "sonstigeshonorar"}:
            preview.other_position_count += 1
        elif name == "datum":
            text = (element.text or "").strip()
            if text:
                dates.append(text)
        elif name == "behandlungsart" and first_behandlungsart is None:
            first_behandlungsart = (element.text or "").strip() or None
        elif name == "nachrichtentyp" and not preview.nachrichtentyp:
            preview.nachrichtentyp = (element.text or "").strip()
            preview.version = element.get("version", "") or preview.version

    # ISO 8601 dates sort lexicographically, which is why nothing is parsed into a date object
    # here: a `datum` that is not ISO (a PVS writing `20.07.2026`) must not raise inside a preview
    # whose entire job is to survive a malformed file.
    iso = sorted(d for d in dates if len(d) >= 10 and d[4] == "-" and d[7] == "-")
    if iso:
        preview.first_service_date, preview.last_service_date = iso[0], iso[-1]

    preview.declaration_line = root.sourceline or None

    if preview.echtdaten_declared is None:
        raw = root.get("echtdaten")
        preview.echtdaten_declared = raw.strip() if raw and raw.strip() else None

    if preview.invoice_count:
        preview.first_invoice = {
            "invoice_id": first_invoice_id,
            "behandlungsart": first_behandlungsart,
            "behandlungsart_label": BEHANDLUNGSART_LABEL.get(first_behandlungsart or "", ""),
            "position_count": first_invoice_positions,
        }
    return preview


# ==============================================================================================
# the result
# ==============================================================================================


@dataclass
class ValidationResult:
    """Everything wrong with one delivery, everything merely worth noting, and what was read.

    `delivery` and `findings` are the reader's own output, present when the document was readable.
    They are here so that a caller which validates and then audits does not parse the file twice —
    `app.api.padnext._audit_bytes` reads them straight out of this object.
    """

    status: Literal["valid", "validation_failed", "parse_failed"]
    errors: list[ValidationError] = dc_field(default_factory=list)
    warnings: list[ValidationError] = dc_field(default_factory=list)
    preview: ParsedPreview = dc_field(default_factory=ParsedPreview)
    delivery: PadnextDelivery | None = None
    findings: list[Warning_] = dc_field(default_factory=list)
    schema_violations: list[SchemaViolation] = dc_field(default_factory=list)
    source_name: str = ""
    schema_policy: str = "strict"

    @property
    def ok(self) -> bool:
        """True when the delivery can be audited. Identical to "the pipeline would not raise"."""
        return not self.errors

    @property
    def primary(self) -> ValidationError | None:
        """The error that becomes the HTTP failure.

        The first one, and the ordering is not incidental: `validate_bytes` appends in order of
        how fundamental a problem is — the bytes, then the document, then the framing, then the
        declaration, then the structure — so the first error is the one whose message is worth
        putting in the envelope. Reordering the pipeline changes which code a client sees, which
        is why the order is asserted by a test rather than left to read out of the code.
        """
        return self.errors[0] if self.errors else None

    def as_dict(self) -> dict[str, Any]:
        """The wire shape, honest about truncation."""
        return {
            "status": self.status,
            "source_name": self.source_name,
            "schema_policy": self.schema_policy,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [e.as_dict() for e in self.errors[:MAX_REPORTED_ISSUES]],
            "warnings": [w.as_dict() for w in self.warnings[:MAX_REPORTED_ISSUES]],
            "errors_omitted": max(0, len(self.errors) - MAX_REPORTED_ISSUES),
            "warnings_omitted": max(0, len(self.warnings) - MAX_REPORTED_ISSUES),
            "parsed_preview": self.preview.as_dict(),
        }

    def to_report(self) -> PadnextValidationReport:
        """The published wire model. One conversion, so no surface renders its own shape.

        `model_validate` rather than field-by-field construction: `as_dict` is already the wire
        shape (it is what `details` carries), so validating it here means the JSON an HTTP client
        sees and the JSON `scripts/validate_padnext.py` prints cannot drift — and a field added to
        the dataclass without a home in the model fails loudly under `extra="forbid"` instead of
        being silently dropped from the response.
        """
        return PadnextValidationReport.model_validate(self.as_dict())

    def raise_for_status(self) -> None:
        """Raise `PadnextValidationFailed` if anything is blocking. A no-op when `ok`."""
        if self.errors:
            raise PadnextValidationFailed(self)


class PadnextValidationFailed(PadnextError):
    """A delivery that failed validation, carrying every error rather than only the first.

    **It adopts the primary error's identity.** `error_code`, `http_status` and `message` are
    whatever that single problem produced before batching existed, and `details` still holds
    exactly the keys it held — `line`/`column`/`location` for malformed XML,
    `violations`/`violation_count` for a schema failure, `echtdaten_declared` for an undeclared
    one. A client switching on `error_code`, or reading `details.line`, cannot tell this class was
    introduced. What is new sits beside those keys: `errors`, `warnings`, `parsed_preview` and the
    two counts.

    A `PadnextError` subclass, so every `except PadnextError` written before this existed still
    catches it, and the class-level `error_code` / `http_status` are shadowed per instance because
    they now depend on which problem came first.
    """

    def __init__(self, result: ValidationResult) -> None:
        self.result = result
        primary = result.primary
        details: dict[str, Any] = dict(primary.legacy_details) if primary else {}

        if primary is not None:
            self.error_code = primary.legacy_code
            self.http_status = primary.legacy_status

        # The schema-violation details are assembled here rather than per issue because they
        # describe the whole set: `violation_count` is the honest total and the list is capped.
        if result.schema_violations and primary is not None and primary.code == "xsd_violation":
            details.setdefault("violation_count", len(result.schema_violations))
            details.setdefault(
                "violations",
                [
                    {
                        "message": v.message,
                        "line": v.line,
                        "column": v.column,
                        "path": v.path,
                        "location": v.location,
                    }
                    for v in result.schema_violations[:MAX_REPORTED_VIOLATIONS]
                ],
            )

        details.update(result.as_dict())
        message = primary.legacy_message if primary else "PADnext validation failed"
        super().__init__(message, details=details)


# ==============================================================================================
# the pass itself
# ==============================================================================================


def validate_bytes(
    data: bytes,
    *,
    source_name: str = "",
    schema_policy: PadnextSchemaPolicy | None = None,
    settings: Settings | None = None,
) -> ValidationResult:
    """Run every check on one delivery and collect the results. Never raises for a bad delivery.

    The order below is the contract — see `ValidationResult.primary`. It goes from the most
    fundamental problem to the least, and it short-circuits only where continuing is meaningless:
    bytes that are not a document cannot have their framing checked. Everything after a successful
    parse is collected, so a file with a schema violation *and* an undeclared `echtdaten` *and* a
    position counter that disagrees reports all three in one answer.

    `settings` and `schema_policy` are injected so a test can pin either without touching
    process-wide state, exactly as `read_delivery` allows.
    """
    settings = settings or get_settings()
    policy = schema_policy or settings.padnext_schema_policy
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []
    #: Findings from unpacking the container, before the payload is read. Kept apart from the
    #: reader's own list because `read_delivery` regenerates them — see step 1.
    container_findings: list[Warning_] = []
    order: dict = {}
    members: list[str] = []
    payload = data
    source = source_name or "lieferung.padx"

    def done(
        status: Literal["valid", "validation_failed", "parse_failed"], **extra: Any
    ) -> ValidationResult:
        return ValidationResult(
            status=status,
            errors=errors,
            warnings=warnings,
            source_name=source_name,
            schema_policy=str(policy),
            **extra,
        )

    # ── 1. the bytes ──────────────────────────────────────────────────────────────────────────
    #
    # No size check of its own here, deliberately. `parse_xml` in step 2 enforces `MAX_XML_BYTES`
    # on the *payload*, and a check here would apply it to the container — refusing a 40 MB `.padx`
    # whose extracted payload is 1 MB, which `read_delivery` reads without complaint. That is
    # exactly the kind of new refusal this module must not introduce; the container's own ceilings
    # (member count, uncompressed total) are enforced inside `unpack_container`, where they belong.
    if data[:4] == ZIP_MAGIC:
        try:
            extracted, members = unpack_container(data, container_findings)
            order = read_order_files(data, container_findings)
        except PadnextError as exc:
            errors.append(
                _issue(
                    classify_refusal(str(exc), fallback="container_unreadable"),
                    detail=str(exc),
                    value=str(exc),
                    size=len(data),
                    limit=MAX_XML_BYTES,
                    source=source,
                    legacy_message=str(exc),
                )
            )
            return done("parse_failed")
        # `container_findings` is deliberately NOT mapped into `warnings` here. Step 5 calls
        # `read_delivery`, which unpacks the same container and produces the same findings — and
        # mapping both would report every ignored member and every encryption notice twice, under
        # the same code, telling a user there are two problems where there is one. They are mapped
        # only on the path where step 5 raised and its findings were lost with it.
        if extracted is None:
            errors.append(_issue("container_without_payload", source=source))
            return done("parse_failed", preview=build_preview(b"", order=order, members=members))
        payload = extracted

    preview = build_preview(payload, order=order, members=members)

    # ── 2. the document ───────────────────────────────────────────────────────────────────────
    try:
        root = parse_xml(payload)
    except InvalidXmlError as exc:
        errors.append(
            _issue(
                "xml_syntax_error",
                # The reader's message is prefixed "XML is not well formed:", which reads as a
                # stutter behind "Ungültiges XML:". The parser's own text is what carries the
                # information, so the prefix is dropped and only that is interpolated.
                detail=exc.message.removeprefix("XML is not well formed: "),
                line=exc.line,
                column=exc.column,
                legacy_message=exc.message,
                legacy_details=exc.details,
            )
        )
        preview.recovered = True
        return done("parse_failed", preview=preview)
    except PadnextError as exc:
        # `parse_xml`'s three non-syntax refusals: a DOCTYPE, bytes that do not start with '<',
        # and a payload over `MAX_XML_BYTES`. Classified by message — see `_READER_REFUSALS`.
        errors.append(
            _issue(
                classify_refusal(str(exc), fallback="not_xml"),
                detail=str(exc),
                size=len(payload),
                limit=MAX_XML_BYTES,
                source=source,
                legacy_message=str(exc),
            )
        )
        return done("parse_failed", preview=preview)

    # ── 3. the right document ─────────────────────────────────────────────────────────────────
    root_name = _local(root.tag)
    if root_name == "auftrag":
        # An order file uploaded on its own. Its own declarations are still worth previewing —
        # this is the one upload where echtdaten and transfernr are present and the positions are
        # not, and saying so is more useful than a bare refusal.
        errors.append(_issue("order_file_uploaded", legacy_message=_ORDER_FILE_ONLY))
        order_only = read_order_files(b"", container_findings, root=root)
        return done(
            "validation_failed",
            preview=build_preview(b"", order=order_only, members=members),
        )
    if root_name != "rechnungen":
        errors.append(
            _issue(
                "unsupported_root",
                value=root_name,
                legacy_message=(
                    f"unsupported PADnext payload root <{root_name}>. This reader handles "
                    "<rechnungen> (message type ADL)."
                ),
            )
        )
        return done("validation_failed", preview=preview)

    # ── 4. the framing ────────────────────────────────────────────────────────────────────────
    violations = validate_payload(payload, policy=policy)
    blocking_schema = policy == PadnextSchemaPolicy.STRICT
    if violations:
        # The same structured log line `read_delivery` writes, and for the same reason: under
        # `warn` this is the only durable record that a non-conforming delivery was let through,
        # and the findings only travel to the caller. Written here because the inner read below
        # runs with the policy `off` and would log nothing.
        _log_violations(violations, policy=policy, source_name=source_name)
        legacy = describe_violations(violations)
        for violation in violations:
            reported = issue_from_violation(violation, blocking=blocking_schema)
            if blocking_schema:
                errors.append(
                    ValidationError(**{**reported.__dict__, "legacy_message": legacy})
                )
            else:
                warnings.append(reported)

    # ── 5. the reading ────────────────────────────────────────────────────────────────────────
    #
    # `read_delivery` is called rather than reimplemented, and with the schema policy set to `off`
    # because step 4 has already reported every violation — running it again would list each one
    # twice, once here and once as a reader finding. Its remaining refusals are collected.
    delivery: PadnextDelivery | None = None
    try:
        delivery, findings = read_delivery_for_validation(
            data, source_name=source_name, policy=policy
        )
        warnings.extend(issue_from_finding(f) for f in findings)
        if violations and not blocking_schema:
            # What `read_delivery` under `warn` would have put on the report itself. The inner
            # read ran with the policy `off`, so these have to be re-attached here or the
            # deviations vanish from `PadnextAuditReport.schema_warnings` — the field that is the
            # entire point of the `warn` policy.
            #
            # Appended *after* the warnings are built, deliberately: step 4 already reported every
            # one of these as an `xsd_violation` warning with a line, a column and a fix. Mapping
            # them a second time would list each deviation twice under two different codes, and a
            # user counting warnings would be told there are twice as many problems as there are.
            findings.extend(v.as_finding() for v in violations)
    except PadnextError as exc:
        # The reading raised, so its findings went with it — the container-level ones collected in
        # step 1 are all that survive, and they are the ones a caller would otherwise never see.
        findings = []
        warnings.extend(issue_from_finding(f) for f in container_findings)
        message = str(exc)
        if isinstance(exc, PadnextSchemaError):  # pragma: no cover - step 4 has it already
            pass
        elif "no <rechnung>" in message:
            errors.append(_issue("no_invoices", legacy_message=message))
        else:  # pragma: no cover - every other refusal is caught in an earlier step
            # Deliberately not relabelled as one of the specific codes. Every refusal the reader
            # can still raise here has been handled above, so reaching this line means the reader
            # grew a refusal this module does not know about — and guessing which category it
            # belongs to would put a confident wrong label on it. The reader's own message is
            # carried through verbatim, which is the one thing that is certainly right.
            errors.append(
                _issue(
                    classify_refusal(message, fallback="delivery_unreadable"),
                    detail=message,
                    value=message,
                    size=len(payload),
                    limit=MAX_XML_BYTES,
                    source=source,
                    legacy_message=message,
                )
            )

    # ── 6. the declaration ────────────────────────────────────────────────────────────────────
    #
    # Read straight from the document rather than from `delivery`, so it is still checked when the
    # reading in step 5 failed for an unrelated reason. `resolve_echtdaten` is the reader's own
    # precedence rule — order file first, payload root second — imported rather than repeated.
    echtdaten, declared = resolve_echtdaten(root, order)
    preview.echtdaten_declared = declared
    # The order file is the site only when it actually declared something, and it is read with
    # `xml.etree`, which does not track lines — so a line is reported for the payload root only.
    from_order = order.get("echtdaten_declared") is not None
    declaration_path = "auftrag/@echtdaten" if from_order else "rechnungen/@echtdaten"
    declaration_line = None if from_order else preview.declaration_line
    if not real_data_allowed(settings):
        if echtdaten is True:
            errors.append(
                _issue(
                    "real_data_refused",
                    value=declared or "1",
                    path=declaration_path,
                    line=declaration_line,
                    source=source,
                    legacy_message=_REAL_DATA,
                )
            )
        elif echtdaten is None:
            code = "echtdaten_unrecognised" if declared else "echtdaten_undeclared"
            errors.append(
                _issue(
                    code,
                    value=declared or "",
                    where=_declaration_site(order, root),
                    where_short=_declaration_site_short(order, root),
                    path=declaration_path,
                    line=declaration_line,
                    source=source,
                    legacy_message=_echtdaten_message(declared),
                    legacy_details={"echtdaten_declared": declared},
                )
            )

    # ── 7. the advisory checks ────────────────────────────────────────────────────────────────
    warnings.extend(_declaration_notes(order, delivery, preview))

    status: Literal["valid", "validation_failed", "parse_failed"] = (
        "validation_failed" if errors else "valid"
    )
    return done(
        status,
        preview=preview,
        delivery=delivery,
        findings=findings,
        schema_violations=list(violations),
    )


def read_delivery_for_validation(
    data: bytes, *, source_name: str, policy: PadnextSchemaPolicy
) -> tuple[PadnextDelivery, list[Warning_]]:
    """`read_delivery` with the schema gate turned off, because step 4 already ran it.

    Its own function so the reason is written down once. Passing `PadnextSchemaPolicy.OFF` here is
    not a relaxation: `validate_bytes` has already validated the same bytes against the same
    schema under the *configured* policy and turned every violation into a blocking error, so a
    second pass could only duplicate them. The delivery still records the policy it was audited
    under, which is why `policy` is threaded through to the report rather than dropped.
    """
    delivery, findings = read_delivery(
        data, source_name=source_name, schema_policy=PadnextSchemaPolicy.OFF
    )
    return delivery.model_copy(update={"schema_policy": str(policy)}), findings


def _declaration_site(order: dict, root: Any) -> str:
    """` in der Auftragsdatei (auftrag/@echtdaten)` — where the reader looked, for the long message."""
    if order:
        return " in der Auftragsdatei (auftrag/@echtdaten)"
    if root is not None:
        return " in den Nutzdaten (rechnungen/@echtdaten)"
    return ""


def _declaration_site_short(order: dict, root: Any) -> str:
    """The same, without the XML path — for the collapsed one-line summary.

    The path is already rendered beside the summary as its own location chip, so repeating it
    inside the sentence spends the line's width saying one thing twice. At 390 px that is the
    difference between a summary that fits and one that wraps to three lines, which is what the
    collapsed row exists to avoid.
    """
    if order:
        return " in der Auftragsdatei"
    if root is not None:
        return " in den Nutzdaten"
    return ""


def _declaration_notes(
    order: dict, delivery: PadnextDelivery | None, preview: ParsedPreview
) -> list[ValidationError]:
    """The non-blocking checks: transfer number and PADnext version.

    Both are warnings, and the transfer number is the one worth explaining. The brief called a
    missing `transfernr` an error; it cannot be, because a bare `*_padx.xml` is a supported upload
    and has no `<auftrag>` to carry one. Refusing it would remove a working path — the public demo
    and every test that reads the bundled payload without its container go through it — to enforce
    a field that affects nothing in the audit. So: a warning when an order file is present and
    silent, an informational note when there is no order file at all, and the report says which.
    """
    notes: list[ValidationError] = []

    if order:
        if not str(order.get("transfernr", "") or "").strip():
            notes.append(_issue("transfernr_missing"))
    else:
        notes.append(_issue("transfernr_unknown"))

    raw_version = (delivery.version if delivery else "") or preview.version
    version = _normalise_version(raw_version)
    if not version:
        notes.append(_issue("version_unknown", expected=SUPPORTED_VERSION))
    elif version != SUPPORTED_VERSION:
        notes.append(_issue("unsupported_version", value=version, expected=SUPPORTED_VERSION))
    return notes


def _normalise_version(raw: str) -> str:
    """`02.12` → `2.12`. The bundled order file uses the padded form and the spec allows it.

    Without this, every conforming delivery in existence would report `unsupported_version` — the
    warning would fire on exactly the files it is meant to stay quiet about, and would be ignored
    within a day.
    """
    parts = [p for p in raw.strip().split(".") if p != ""]
    if not parts or not all(p.isdigit() for p in parts):
        return raw.strip()
    return ".".join(str(int(p)) for p in parts)


# The three legacy messages that must survive verbatim, because a shipped test and a shipped
# client read substrings out of them. Kept here beside the issues that adopt them rather than
# duplicated at the raise sites.

_ORDER_FILE_ONLY = (
    "this is a PADnext Auftragsdatei (order file), not the payload. Send the "
    "*_padx.xml payload, or the .padx container holding both."
)

_REAL_DATA = (
    "Das Hochladen von Echtdaten ist im Pilotmodus nicht gestattet. Diese PADnext-Lieferung ist "
    "als Echtdaten gekennzeichnet (auftrag/@echtdaten). Bitte nutzen Sie das "
    "Azmoth-Anonymisierungsskript und laden Sie die Datei erneut hoch. — This PADnext "
    "delivery is "
    "flagged as production data (auftrag/@echtdaten). This deployment processes synthetic data "
    "only and has refused it. Set PADNEXT_ALLOW_REAL_DATA=1 only if you have a lawful basis and "
    "appropriate controls."
)


def _echtdaten_message(declared: str | None) -> str:
    """The refusal text `audit_delivery` produces, so the envelope's `message` does not change.

    Duplicated from `app.padnext.audit` deliberately rather than imported: that gate is the
    security control and must keep working with no dependency on this module, and its message is
    asserted there. `tests/test_padnext_validation.py::test_the_two_gates_say_the_same_thing`
    fails if the two ever drift.
    """
    value = (declared or "").strip()
    what = (
        f"Das Feld 'echtdaten' enthält den Wert '{value}', der in der PADnext-Spezifikation nicht "
        "definiert ist (erlaubt sind '0'/'false' für Testdaten und '1'/'true' für Echtdaten)."
        if value
        else "Das Feld 'echtdaten' fehlt oder ist ungültig."
    )
    return (
        f"{what} Diese Lieferung wird abgewiesen, weil ohne diese Angabe nicht feststellbar ist, "
        "ob sie echte Patientendaten enthält — und eine fehlende Angabe wird nicht als "
        "'Testdaten' angenommen. Bitte nutzen Sie das Anonymisierungsskript "
        "(scripts/anonymize_padnext.py); es setzt echtdaten=\"false\" in der Auftragsdatei und in "
        "den Nutzdaten. — This delivery does not declare whether it holds production data. An "
        "undeclared delivery is refused rather than assumed to be synthetic. Run "
        "scripts/anonymize_padnext.py and upload its output, or fix the export to emit "
        "echtdaten=\"0\". Set PADNEXT_ALLOW_REAL_DATA=1 only with a lawful basis."
    )


def validate_file(
    path: str | Path, *, schema_policy: PadnextSchemaPolicy | None = None
) -> ValidationResult:
    """`validate_bytes` for a path. What `scripts/validate_padnext.py` calls."""
    p = Path(path)
    if not p.is_file():
        raise PadnextError(f"no such PADnext file: {p}")
    return validate_bytes(p.read_bytes(), source_name=p.name, schema_policy=schema_policy)
