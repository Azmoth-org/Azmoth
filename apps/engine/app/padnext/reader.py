"""Read a PADnext delivery: either a `.padx` container or a bare payload XML.

Shape, from the PADneXt 2.12 specification (PADline GmbH / PVS-Verband, namespace
`http://padinfo.de/ns/pad`):

    auftrag                      the order file, unencrypted, describes the delivery
      @transfernr @echtdaten @erstellungsdatum @dateianzahl
      empfaenger / absender / nachrichtentyp / system / verschluesselung
      datei > name, dateilaenge@pruefsumme@laenge

    rechnungen @anzahl           the ADL payload
      nachrichtentyp
      rechnung @id
        abrechnungsfall
          behandlungsart, vertragsart, minderungssatz
          positionen @posanzahl
            goziffer @positionsnr @go @ziffer @analog
              datum, anzahl, text, faktor | einzelbetrag, begruendung,
              minderungssatz, punktzahl, punktwert, gesamtbetrag

This is a reader for the subset that affects whether a position is chargeable and what it should
cost. It is **not** a conforming PADnext implementation. Anything it does not understand becomes a
finding rather than being dropped — the same rule the GOÄ importer follows.

**The framing is validated; the positions are not.** Before anything is read out of a payload it is
checked against `data/schemas/padnext/padx_adl_v2.12.subset.xsd` — our own subset, because the
official XSD is not redistributable here. That check answers one question: is this an ADL payload at
all? Wrong root, wrong namespace, no message type, a counter that is not a number, a treatment code
outside the legal set, an Abrechnungsfall with no positions. Those refuse the delivery
(`PadnextSchemaError`, HTTP 422) because it cannot be audited or cannot be priced.

Everything below that line stays advisory, and deliberately so: a `goziffer` with no `@ziffer`, a
`faktor` reading "zwei", an `auslagen` line this engine does not model. The invoices most likely to
be wrong are the malformed ones, so a validator strict enough to refuse them would refuse exactly
the files a practice most needs read. `PADNEXT_SCHEMA_POLICY=warn` moves the framing check to the
same footing for the day a real export is 99 % conforming. See `app/padnext/schema.py`.

Encrypted payloads (`verschluesselung/@verfahren` other than 0 — the spec uses PKCS#7) are reported
as unsupported rather than half-handled.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree

from app.config import PadnextSchemaPolicy, get_settings
from app.errors import EngineError, ErrorCode
from app.padnext.schema import (
    MAX_REPORTED_VIOLATIONS,
    SchemaViolation,
    describe_violations,
    validate_payload,
)
from app.schemas import Warning_
from app.schemas.padnext import (
    PadnextCase,
    PadnextDelivery,
    PadnextInvoice,
    PadnextPosition,
)

log = logging.getLogger(__name__)

PAD_NS = "http://padinfo.de/ns/pad"

#: Guards for untrusted input. A PADnext delivery is a file someone sends you, so it is hostile
#: until proven otherwise.
MAX_XML_BYTES = 32 * 1024 * 1024
MAX_ZIP_MEMBERS = 64
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024

ZIP_MAGIC = b"PK\x03\x04"

#: PADnext filenames are kundennr_datum_nachrichtentyp_transfernr_padx.xml
PADX_NAME = re.compile(r"^(?P<kunde>[^_]+)_(?P<datum>\d{8})_(?P<typ>[A-Z]+)_(?P<nr>\d+)_padx\.xml$")


#: The only two spellings of `@echtdaten` that mean **production data**, and the only two that mean
#: **test data**. Both sets are closed, and everything outside them is *unrecognised* — which is a
#: third answer, not a synonym for the second.
#:
#: This used to be one line, `raw in {"1", "true"}`, and that line is the reason this comment
#: exists. It answers a three-valued question with a boolean, so every value it did not recognise
#: became `False` — "test data" — and a delivery whose order file said `echtdaten="ja"` was audited
#: as anonymised on the strength of a word the parser had never heard of. The failure is silent,
#: happens on exactly the exports a German PVS is most likely to produce, and produces no finding
#: anybody could notice. `parse_echtdaten` returns `None` for that case instead, and
#: `app.padnext.audit` refuses the delivery.
ECHTDATEN_REAL = frozenset({"1", "true"})
ECHTDATEN_TEST = frozenset({"0", "false"})


def parse_echtdaten(raw: str | None) -> bool | None:
    """`True` = production data, `False` = test data, `None` = absent or not recognised.

    `None` deliberately conflates "the attribute was not there" with "the attribute said 'ja'":
    both mean *this file has not told us whether it holds real patients*, and both are refused by
    the audit for the same reason. The two are still distinguishable downstream, because the raw
    string is carried alongside on `PadnextDelivery.echtdaten_declared` — the refusal message needs
    to quote it back, since "your file says 'ja' and I do not know what that means" is actionable
    and "something is wrong with echtdaten" is not.
    """
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in ECHTDATEN_REAL:
        return True
    if value in ECHTDATEN_TEST:
        return False
    return None


class PadnextError(EngineError, RuntimeError):
    """The delivery cannot be read at all. Distinct from a finding, which is a readable problem.

    `EngineError` is listed first so its keyword-taking constructor wins the MRO; `RuntimeError`
    stays a base so that every `except RuntimeError` written before the error catalog existed
    still catches this.

    `422 PADNEXT_UNREADABLE` by default — the request was well formed, the bytes were not a
    delivery this engine can process. Subclasses below narrow that where the cause is specific
    enough to deserve its own code and its own status.
    """

    error_code = ErrorCode.PADNEXT_UNREADABLE
    http_status = 422


class InvalidXmlError(PadnextError):
    """The bytes are not well-formed XML. `400`, and it names the line and column.

    Separated from its parent because well-formedness is a different conversation from schema
    conformance: a document that does not parse cannot be *anything*, so this is a `400` (the
    request itself is malformed) where a schema violation is a `422` (well formed, wrong content).
    Whoever has to fix the export needs the position, not the adjective — the parser knows it, and
    dropping it on the floor is what leaves someone grepping a 3 MB file by hand.

    Still a `PadnextError`, so every existing `except PadnextError` keeps working.
    """

    error_code = ErrorCode.INVALID_XML
    http_status = 400

    def __init__(
        self, message: str, *, line: int | None = None, column: int | None = None
    ) -> None:
        super().__init__(
            message,
            details={
                "line": line,
                "column": column,
                "location": f"line {line}, column {column}" if line is not None else "",
            },
        )
        self.line = line
        self.column = column


class PadnextSchemaError(PadnextError):
    """The payload is not an ADL document this engine can audit. Carries every violation.

    A `PadnextError` subclass so that `api/padnext.py`'s existing `except PadnextError` keeps
    turning it into a 422 with no new handler, and so a caller that only cares "unreadable
    delivery" needs no change. A caller that wants the detail reads `violations`, each of which
    carries a line, a column and a readable element path — see `app.padnext.schema`.
    """

    error_code = ErrorCode.PADNEXT_SCHEMA_VIOLATION
    http_status = 422

    def __init__(self, violations: list[SchemaViolation]) -> None:
        self.violations = list(violations)
        super().__init__(
            describe_violations(self.violations),
            details={
                "violation_count": len(self.violations),
                "violations": [
                    {
                        "message": v.message,
                        "line": v.line,
                        "column": v.column,
                        "path": v.path,
                        "location": v.location,
                    }
                    for v in self.violations
                ],
            },
        )


def _local(tag: str) -> str:
    """Strip the namespace. PADnext files in the wild vary on prefix and on declaring it at all."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text(element: ElementTree.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def _child(parent: ElementTree.Element, name: str) -> ElementTree.Element | None:
    for child in parent:
        if _local(child.tag) == name:
            return child
    return None


def _children(parent: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [c for c in parent if _local(c.tag) == name]


def _decimal(raw: str, *, field: str, findings: list[Warning_]) -> Decimal | None:
    """Parse a decimal, or record why not. Never returns a float — money stays exact."""
    if not raw:
        return None
    try:
        return Decimal(raw.replace(",", "."))
    except InvalidOperation:
        findings.append(
            Warning_(
                type="padnext_unparsable_number",
                severity="warning",
                message=f"Feld '{field}' enthält keinen lesbaren Dezimalwert: {raw!r}",
            )
        )
        return None


def _int(raw: str, *, field: str, findings: list[Warning_]) -> int | None:
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        findings.append(
            Warning_(
                type="padnext_unparsable_number",
                severity="warning",
                message=f"Feld '{field}' enthält keine lesbare Ganzzahl: {raw!r}",
            )
        )
        return None


def parse_xml(data: bytes) -> ElementTree.Element:
    """Parse untrusted XML.

    A DOCTYPE is rejected outright. ElementTree does not fetch external entities, but it does
    expand internal ones, which is enough for a billion-laughs expansion; refusing the declaration
    removes the whole class rather than trying to bound it.
    """
    if len(data) > MAX_XML_BYTES:
        raise PadnextError(
            f"XML is {len(data)} bytes, above the {MAX_XML_BYTES}-byte limit for this endpoint"
        )

    head = data[:4096].lstrip()
    if head[:1] != b"<":
        raise PadnextError("not XML: the payload does not start with '<'")
    if b"<!DOCTYPE" in data[:8192].upper().replace(b"<!DOCTYPE ", b"<!DOCTYPE"):
        raise PadnextError(
            "XML declares a DOCTYPE, which this reader refuses (entity-expansion risk). "
            "PADnext payloads do not need one."
        )

    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        # `position` is (line, column), 1-based, and is the whole reason this is not just a
        # re-raise: "not well formed" without a position is unactionable on a real export.
        line, column = getattr(exc, "position", (None, None))
        raise InvalidXmlError(
            f"XML is not well formed: {exc}", line=line, column=column
        ) from exc


def _unpack_container(data: bytes, findings: list[Warning_]) -> tuple[bytes | None, list[str]]:
    """Pull the payload XML out of a `.padx` ZIP, reading the order file for context.

    Returns (payload_bytes_or_None, member_names).
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise PadnextError(f"looks like a ZIP container but cannot be opened: {exc}") from exc

    infos = archive.infolist()
    if len(infos) > MAX_ZIP_MEMBERS:
        raise PadnextError(f"container holds {len(infos)} members, above the safety limit")
    total = sum(i.file_size for i in infos)
    if total > MAX_UNCOMPRESSED_BYTES:
        raise PadnextError(f"container expands to {total} bytes, above the safety limit")

    members = [i.filename for i in infos]

    payload: bytes | None = None
    for info in infos:
        name = Path(info.filename).name
        if info.is_dir() or name.startswith("."):
            continue
        # Path traversal in a member name is never legitimate here.
        if ".." in Path(info.filename).parts or Path(info.filename).is_absolute():
            raise PadnextError(f"container member escapes the archive root: {info.filename!r}")

        lowered = name.lower()
        if lowered.endswith(".auf") or lowered.endswith("_auf.xml"):
            continue  # the order file; handled by the caller via _read_order_file
        if PADX_NAME.match(name) or lowered.endswith("_padx.xml"):
            payload = archive.read(info)
        elif lowered.endswith(".xml") and payload is None:
            payload = archive.read(info)
        else:
            findings.append(
                Warning_(
                    type="padnext_container_member_ignored",
                    severity="info",
                    message=(
                        f"Datei '{info.filename}' im Container wurde nicht als Nutzdaten "
                        "erkannt und nicht gelesen."
                    ),
                )
            )
    return payload, members


def _read_order_file(data: bytes, findings: list[Warning_]) -> dict:
    """Whatever the `auftrag` root tells us. Only ever used for context, never for billing."""
    info: dict = {}
    try:
        root = parse_xml(data)
    except PadnextError as exc:
        findings.append(
            Warning_(
                type="padnext_order_file_unreadable",
                severity="warning",
                message=f"Auftragsdatei konnte nicht gelesen werden: {exc}",
            )
        )
        return info

    if _local(root.tag) != "auftrag":
        return info

    raw_echt = root.get("echtdaten")
    if raw_echt is not None and raw_echt.strip():
        # Both the parsed tri-state and the string as written. The audit needs the first to decide
        # and the second to explain — see `parse_echtdaten`.
        info["echtdaten"] = parse_echtdaten(raw_echt)
        info["echtdaten_declared"] = raw_echt.strip()
    info["transfernr"] = root.get("transfernr", "")

    typ = _child(root, "nachrichtentyp")
    if typ is not None:
        info["nachrichtentyp"] = _text(typ)
        info["version"] = typ.get("version", "")

    encryption = _child(root, "verschluesselung")
    if encryption is not None and (encryption.get("verfahren") or "0") != "0":
        findings.append(
            Warning_(
                type="padnext_encrypted_payload",
                severity="error",
                message=(
                    "Die Auftragsdatei deklariert ein Verschlüsselungsverfahren "
                    f"({encryption.get('verfahren')}). Verschlüsselte Nutzdaten werden von "
                    "diesem Proof of Concept nicht entschlüsselt."
                ),
            )
        )
    return info


def _parse_position(
    element: ElementTree.Element, findings: list[Warning_]
) -> PadnextPosition | None:
    ziffer = (element.get("ziffer") or "").strip()
    positionsnr = (element.get("positionsnr") or "").strip()

    if not ziffer:
        findings.append(
            Warning_(
                type="padnext_position_without_ziffer",
                severity="error",
                message=(
                    f"Position {positionsnr or '(ohne Nummer)'} hat kein @ziffer-Attribut und "
                    "wurde nicht geprüft."
                ),
            )
        )
        return None

    faktor = _decimal(
        _text(_child(element, "faktor")), field=f"goziffer[{positionsnr}]/faktor", findings=findings
    )
    einzelbetrag = _decimal(
        _text(_child(element, "einzelbetrag")),
        field=f"goziffer[{positionsnr}]/einzelbetrag",
        findings=findings,
    )
    if faktor is not None and einzelbetrag is not None:
        findings.append(
            Warning_(
                type="padnext_faktor_and_einzelbetrag",
                severity="warning",
                ziffer=ziffer,
                message=(
                    f"Position {positionsnr} gibt sowohl faktor als auch einzelbetrag an. Die "
                    "Spezifikation erlaubt nur eines von beiden."
                ),
            )
        )

    return PadnextPosition(
        positionsnr=positionsnr or ziffer,
        go=(element.get("go") or "GOÄ").strip(),
        ziffer=ziffer,
        analog_for=(element.get("analog") or "").strip() or None,
        datum=_text(_child(element, "datum")) or None,
        anzahl=_int(_text(_child(element, "anzahl")), field="anzahl", findings=findings) or 1,
        text=_text(_child(element, "text")),
        faktor=faktor,
        einzelbetrag=einzelbetrag,
        begruendung=_text(_child(element, "begruendung")) or None,
        minderungssatz=_decimal(
            _text(_child(element, "minderungssatz")),
            field=f"goziffer[{positionsnr}]/minderungssatz",
            findings=findings,
        ),
        punktzahl=_int(_text(_child(element, "punktzahl")), field="punktzahl", findings=findings),
        punktwert=_decimal(
            _text(_child(element, "punktwert")),
            field=f"goziffer[{positionsnr}]/punktwert",
            findings=findings,
        ),
        gesamtbetrag=_decimal(
            _text(_child(element, "gesamtbetrag")),
            field=f"goziffer[{positionsnr}]/gesamtbetrag",
            findings=findings,
        ),
    )


def _parse_case(element: ElementTree.Element, findings: list[Warning_]) -> PadnextCase:
    positionen = _child(element, "positionen")
    positions: list[PadnextPosition] = []
    declared: int | None = None

    if positionen is not None:
        declared = _int(positionen.get("posanzahl", ""), field="posanzahl", findings=findings)
        for child in positionen:
            name = _local(child.tag)
            if name == "goziffer":
                parsed = _parse_position(child, findings)
                if parsed is not None:
                    positions.append(parsed)
            elif name in {"gozziffer", "entschaedigung", "auslagen", "sonstigeshonorar", "text"}:
                # Real position types this POC does not model. Reported, never silently skipped.
                findings.append(
                    Warning_(
                        type="padnext_position_type_not_modelled",
                        severity="warning",
                        message=(
                            f"Positionstyp '{name}' wird von diesem Proof of Concept nicht "
                            "geprüft und ist im Ergebnis nicht enthalten."
                        ),
                    )
                )

    return PadnextCase(
        behandlungsart=_text(_child(element, "behandlungsart")) or None,
        vertragsart=_text(_child(element, "vertragsart")) or None,
        minderungssatz=_decimal(
            _text(_child(element, "minderungssatz")),
            field="abrechnungsfall/minderungssatz",
            findings=findings,
        ),
        positions=positions,
        declared_position_count=declared,
    )


def _log_violations(
    violations: list[SchemaViolation],
    *,
    policy: PadnextSchemaPolicy,
    source_name: str,
) -> None:
    """Record a framing violation as one structured line, whichever way the policy resolves it.

    Under `warn` this is the *only* durable record that the delivery was not conforming: the
    findings travel to whoever called the API, and nobody operating the pilot sees them. A file
    that was let through has to be answerable three weeks later — which export, which rule, which
    line — and the request id `JsonFormatter` attaches from the context ties it to the upload that
    carried it (`app.core.observability`).

    Logged under `strict` too, at `error`. A refusal already reaches the caller as a 422, but the
    operator watching the pilot is the person who has to decide whether the policy should move,
    and that decision needs both halves of the picture in the same stream.

    **Nothing here identifies a patient.** `source_name` is a filename, and `rule`, `line`,
    `column` and `path` are positions in a document — never element *content*, which is where a
    name or a diagnosis would be. `message` is libxml2's, which quotes the offending value for a
    datatype error (`'viele'` is not an integer); that is a control field by construction, since
    the schema only constrains framing. Kept for that reason, and capped like the exception is.
    """
    detail = [
        {
            "rule": v.rule,
            "line": v.line,
            "column": v.column,
            "path": v.path,
            "message": v.message,
        }
        for v in violations[:MAX_REPORTED_VIOLATIONS]
    ]
    warned = policy != PadnextSchemaPolicy.STRICT
    log.log(
        logging.WARNING if warned else logging.ERROR,
        "PADnext framing violated (%d violation(s)), policy=%s: %s",
        len(violations),
        str(policy),
        "audited anyway" if warned else "delivery refused",
        extra={
            "event": "padnext_schema_violation",
            "padnext_schema_policy": str(policy),
            "padnext_schema_outcome": "audited" if warned else "refused",
            "violation_count": len(violations),
            "violations": detail,
            "source_name": source_name,
        },
    )


def read_delivery(
    data: bytes,
    *,
    source_name: str = "",
    schema_policy: PadnextSchemaPolicy | None = None,
) -> tuple[PadnextDelivery, list[Warning_]]:
    """Read a `.padx` container or a bare payload XML into a delivery plus any findings.

    `schema_policy` overrides `PADNEXT_SCHEMA_POLICY` for one call, which is what lets a test pin
    a policy without touching process-wide settings. `None` means "whatever is configured".
    """
    findings: list[Warning_] = []
    order: dict = {}
    members: list[str] = []
    payload = data

    if data[:4] == ZIP_MAGIC:
        extracted, members = _unpack_container(data, findings)
        # Read the order file separately so its echtdaten flag and encryption notice survive.
        archive = zipfile.ZipFile(io.BytesIO(data))
        for info in archive.infolist():
            name = Path(info.filename).name.lower()
            if name.endswith(".auf") or name.endswith("_auf.xml"):
                order = _read_order_file(archive.read(info), findings)
                break
        if extracted is None:
            raise PadnextError(
                "container holds no payload XML. Expected a member named "
                "<kundennr>_<datum>_<typ>_<nr>_padx.xml"
            )
        payload = extracted

    root = parse_xml(payload)
    root_name = _local(root.tag)

    if root_name == "auftrag":
        raise PadnextError(
            "this is a PADnext Auftragsdatei (order file), not the payload. Send the "
            "*_padx.xml payload, or the .padx container holding both."
        )
    if root_name != "rechnungen":
        raise PadnextError(
            f"unsupported PADnext payload root <{root_name}>. This reader handles <rechnungen> "
            "(message type ADL)."
        )

    # The framing gate. Deliberately here and not earlier: the three checks above own their own
    # messages — "send the payload, not the order file", "unsupported root" — and each names what
    # to do instead, which a schema violation cannot. Deliberately here and not later: nothing
    # below this line should be reading positions out of a document that is not an ADL payload.
    policy = schema_policy or get_settings().padnext_schema_policy
    violations = validate_payload(payload, policy=policy)
    if violations:
        _log_violations(violations, policy=policy, source_name=source_name)
        if policy == PadnextSchemaPolicy.STRICT:
            raise PadnextSchemaError(violations)
        findings.extend(v.as_finding() for v in violations)

    typ = _child(root, "nachrichtentyp")
    nachrichtentyp = _text(typ) or order.get("nachrichtentyp", "")
    version = (typ.get("version", "") if typ is not None else "") or order.get("version", "")

    invoices: list[PadnextInvoice] = []
    for rechnung in _children(root, "rechnung"):
        cases = [_parse_case(case, findings) for case in _children(rechnung, "abrechnungsfall")]
        if not cases:
            findings.append(
                Warning_(
                    type="padnext_invoice_without_case",
                    severity="warning",
                    message=(
                        f"Rechnung '{rechnung.get('id', '')}' enthält keinen Abrechnungsfall "
                        "und wurde übersprungen."
                    ),
                )
            )
            continue
        invoices.append(PadnextInvoice(invoice_id=rechnung.get("id", ""), cases=cases))

    if not invoices:
        raise PadnextError("payload contains no <rechnung> with an <abrechnungsfall>")

    declared_invoices = _int(root.get("anzahl", ""), field="rechnungen/@anzahl", findings=findings)

    # ── Where the anonymisation declaration comes from ────────────────────────────────────────
    #
    # The order file first, because that is where the PADnext specification puts `@echtdaten` and
    # a container that has one is the authoritative case.
    #
    # Then the payload root, which the specification does NOT define an `@echtdaten` for — it is an
    # extension, permitted by the subset schema's `xs:anyAttribute` on `<rechnungen>`, and it exists
    # for one situation: a BARE `*_padx.xml` uploaded without its order file. That is a supported
    # input (the API takes either) and it has no `<auftrag>` to carry the flag, so before this it
    # could not declare anything at all. Now that an undeclared delivery is refused, "cannot
    # declare" would have meant "can never be audited", which would have removed a working path
    # rather than securing one. `scripts/anonymize_padnext.py` writes the attribute in both places.
    #
    # The order file wins where both are present and disagree. It is the document the sending
    # system signs the delivery with, and a payload that contradicts it is not a tie to break in
    # the payload's favour.
    declared = order.get("echtdaten_declared")
    echtdaten = order.get("echtdaten")
    if declared is None:
        raw_root = root.get("echtdaten")
        if raw_root is not None and raw_root.strip():
            declared = raw_root.strip()
            echtdaten = parse_echtdaten(raw_root)

    delivery = PadnextDelivery(
        nachrichtentyp=nachrichtentyp,
        version=version,
        echtdaten=echtdaten,
        echtdaten_declared=declared,
        declared_invoice_count=declared_invoices,
        invoices=invoices,
        container_members=members,
        source_name=source_name,
        schema_policy=str(policy),
    )

    # Consistency checks the spec explicitly puts these counters there for.
    if declared_invoices is not None and declared_invoices != len(invoices):
        findings.append(
            Warning_(
                type="padnext_invoice_count_mismatch",
                severity="warning",
                message=(
                    f"<rechnungen anzahl=\"{declared_invoices}\"> stimmt nicht mit den "
                    f"{len(invoices)} gelesenen Rechnungen überein."
                ),
            )
        )
    for invoice in invoices:
        for case in invoice.cases:
            if (
                case.declared_position_count is not None
                and case.declared_position_count != len(case.positions)
            ):
                findings.append(
                    Warning_(
                        type="padnext_position_count_mismatch",
                        severity="warning",
                        message=(
                            f"Rechnung '{invoice.invoice_id}': <positionen posanzahl="
                            f"\"{case.declared_position_count}\"> stimmt nicht mit den "
                            f"{len(case.positions)} gelesenen GOÄ-Positionen überein. "
                            "Andere Positionstypen werden nicht mitgezählt."
                        ),
                    )
                )

    return delivery, findings


def read_file(
    path: str | Path, *, schema_policy: PadnextSchemaPolicy | None = None
) -> tuple[PadnextDelivery, list[Warning_]]:
    p = Path(path)
    if not p.is_file():
        raise PadnextError(f"no such PADnext file: {p}")
    return read_delivery(p.read_bytes(), source_name=p.name, schema_policy=schema_policy)
