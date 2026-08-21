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
cost. It is **not** a conforming PADnext implementation and does not validate against the official
XSD, which is not redistributed here. Anything it does not understand becomes a finding rather than
being dropped — the same rule the GOÄ importer follows.

Encrypted payloads (`verschluesselung/@verfahren` other than 0 — the spec uses PKCS#7) are reported
as unsupported rather than half-handled.
"""

from __future__ import annotations

import io
import re
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree

from app.schemas import Warning_
from app.schemas.padnext import (
    PadnextCase,
    PadnextDelivery,
    PadnextInvoice,
    PadnextPosition,
)

PAD_NS = "http://padinfo.de/ns/pad"

#: Guards for untrusted input. A PADnext delivery is a file someone sends you, so it is hostile
#: until proven otherwise.
MAX_XML_BYTES = 32 * 1024 * 1024
MAX_ZIP_MEMBERS = 64
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024

ZIP_MAGIC = b"PK\x03\x04"

#: PADnext filenames are kundennr_datum_nachrichtentyp_transfernr_padx.xml
PADX_NAME = re.compile(r"^(?P<kunde>[^_]+)_(?P<datum>\d{8})_(?P<typ>[A-Z]+)_(?P<nr>\d+)_padx\.xml$")


class PadnextError(RuntimeError):
    """The delivery cannot be read at all. Distinct from a finding, which is a readable problem."""


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
        raise PadnextError(f"XML is not well formed: {exc}") from exc


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

    raw_echt = (root.get("echtdaten") or "").strip().lower()
    if raw_echt:
        # The spec allows both boolean spellings; "0"/"false" mean test data.
        info["echtdaten"] = raw_echt in {"1", "true"}
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


def read_delivery(
    data: bytes, *, source_name: str = ""
) -> tuple[PadnextDelivery, list[Warning_]]:
    """Read a `.padx` container or a bare payload XML into a delivery plus any findings."""
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

    delivery = PadnextDelivery(
        nachrichtentyp=nachrichtentyp,
        version=version,
        echtdaten=order.get("echtdaten"),
        declared_invoice_count=declared_invoices,
        invoices=invoices,
        container_members=members,
        source_name=source_name,
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


def read_file(path: str | Path) -> tuple[PadnextDelivery, list[Warning_]]:
    p = Path(path)
    if not p.is_file():
        raise PadnextError(f"no such PADnext file: {p}")
    return read_delivery(p.read_bytes(), source_name=p.name)
