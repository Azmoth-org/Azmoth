#!/usr/bin/env python3
"""Anonymise a PADnext delivery so that it may be uploaded to Azmoth.

    ./scripts/anonymize_padnext.py export.padx
    ./scripts/anonymize_padnext.py export.padx -o pilot-01.padx
    ./scripts/anonymize_padnext.py 00004711_20260726_ADL_000001_padx.xml --mode mask

Reads a `.padx` container, a bare `*_padx.xml` payload or an `.auf` order file, removes the
patient's identity from it, stamps `echtdaten="false"` on the root, and writes a NEW file. The
input is never modified and never overwritten.

The specification this implements, in German and with the legal reasoning, is
`docs/pilot/ANONYMIZATION_SPEC.md`. Read that one if the question is *why*; this header is *what*.

── Zero dependencies, and that is a requirement rather than a preference ──────────────────────
This runs on the practice's own machine, inside their network, on data that has not been
anonymised yet — which is the one moment in the whole pipeline where real patient data is in
motion. Asking a medical practice to `pip install` anything before that step means asking their IT
to approve a package tree nobody in this conversation has read. So: the standard library, Python
3.9 or newer, one file, no network access, no temporary files outside the output directory.

`python3 scripts/anonymize_padnext.py --selftest` proves the thing works on the machine it was
copied to, without needing a delivery to try it on.

── What it removes ────────────────────────────────────────────────────────────────────────────
Two modes, and the difference is what happens to a field this script has never heard of.

  strict (the default)  An ALLOWLIST. The payload is rebuilt from scratch containing only the
                        elements and attributes the engine actually reads — the invoice frame and
                        the GOÄ positions. Anything else is dropped, whether or not it is on any
                        list of identifiers. A `<patientenchip>` element invented by one PVS
                        vendor last spring is removed because it was not kept, not because it was
                        recognised.

  mask                  A DENYLIST. The document keeps its shape and known identifying fields are
                        emptied or replaced with a placeholder. Use it when a downstream tool
                        needs the original structure. It cannot be as safe as `strict`, and the
                        script says so in its summary every time it is used.

`strict` is the default because the failure modes are not symmetric. An allowlist that is too
narrow produces a report with a gap in it, which someone notices. A denylist that is too narrow
produces a file that looks anonymised, is not, and is uploaded.

── What it does NOT do ────────────────────────────────────────────────────────────────────────
It does not read free text for you. `<begruendung>` and `<text>` are written by a human and are
kept, because § 12 Abs. 3 GOÄ justifications are exactly what the audit has to see. A sentence
like "Bericht an Dr. Weber zum Befund von Frau Schmidt, geb. 14.03.1961" is personal data that no
element name marks as such. The residual scan at the end looks for the obvious shapes — dates of
birth, insurance-number patterns, IBANs, long digit runs — and prints what it found so a person
can look at it. It is a prompt for a human, not a filter, and the summary says so.

It is also not pseudonymisation with a key. Nothing is kept that would let the original be
recovered; the mapping does not exist, in this script or anywhere else. That is deliberate — see
the specification.

── Exit status ────────────────────────────────────────────────────────────────────────────────
    0   written
    1   the input could not be read, or the output could not be written
    2   bad usage
    3   written, but the residual scan found something AND --fail-on-residual was given
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

PAD_NS = "http://padinfo.de/ns/pad"

#: Same guards as `apps/engine/app/padnext/reader.py`. A delivery is a file somebody sends you.
MAX_XML_BYTES = 32 * 1024 * 1024
MAX_ZIP_MEMBERS = 64
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024

#: What replaces a masked value, rather than an empty element. An empty `<geburtsdatum/>` is
#: indistinguishable from a field the source system never filled in; this one is unmistakably the
#: work of this script, which matters when somebody three months later asks whether a given file
#: went through it.
PLACEHOLDER = "ANONYMISIERT"


# ── The allowlist: everything the engine reads out of a payload, and nothing else ──────────────
#
# Derived from `apps/engine/app/padnext/reader.py`. If the reader learns to read a new field, it
# goes here too — otherwise `strict` mode silently removes the input to a check that then reports
# nothing. `--selftest` audits this list against a delivery it builds itself.

KEEP_ELEMENTS = frozenset(
    {
        "rechnungen",
        "nachrichtentyp",
        "rechnung",
        "abrechnungsfall",
        "behandlungsart",
        "vertragsart",
        "minderungssatz",
        "positionen",
        "goziffer",
        "datum",
        "anzahl",
        "text",
        "faktor",
        "einzelbetrag",
        "begruendung",
        "punktzahl",
        "punktwert",
        "gesamtbetrag",
    }
)

#: Which attributes survive on which element. Anything not listed is dropped in `strict` mode —
#: including `aisrechnungsnr`, which is the practice's own invoice number and is a re-identifier
#: the moment anyone holds both this file and the practice's ledger.
KEEP_ATTRIBUTES = {
    # `schemaLocation` is the xsi hint. Kept because it identifies the PADnext version to a
    # receiving validator and identifies nobody — it is a URL to a public schema.
    "rechnungen": {"anzahl", "echtdaten", "schemaLocation"},
    "nachrichtentyp": {"version"},
    "rechnung": {"id"},
    "positionen": {"posanzahl"},
    "goziffer": {"positionsnr", "go", "ziffer", "analog"},
}


# ── The denylist: names that carry identity, matched on the LOCAL name, case-insensitively ─────
#
# Used by both modes. In `mask` it is the whole of the removal; in `strict` it is a second pass
# that also covers the order file, which is not rebuilt from an allowlist because it carries no
# patient data by specification and does carry the delivery framing the engine needs.
#
# The four names the pilot brief calls out — patient_name, patient_address, geburtsdatum,
# versichertennummer — are in here, along with the spellings real PVS exports actually use. The
# list is long on purpose and is still not a guarantee: that is what `strict` is for.

IDENTITY_ELEMENTS = frozenset(
    {
        # name
        "patient", "patient_name", "patientname", "patientenname", "patientendaten",
        "behandelter", "person", "name", "nachname", "vorname", "geburtsname",
        "titel", "namenszusatz", "vorsatzwort", "anrede",
        # who the invoice is addressed to, which for a minor is a different person and is still one
        "rechnungsempfaenger", "zahlungspflichtiger", "kostentraeger", "empfaengeradresse",
        # date of birth and sex
        "geburtsdatum", "gebdatum", "geburtstag", "geschlecht",
        # address
        "patient_address", "patientenadresse", "anschrift", "adresse", "wohnort",
        "strasse", "strassehausnummer", "hausnummer", "plz", "postleitzahl", "ort", "ortsteil",
        "land", "staat", "postfach",
        # contact
        "telefon", "telefonnummer", "telefonprivat", "telefondienst", "telefax", "fax",
        "email", "emailadresse", "mobil", "mobilnummer",
        # insurance and case identifiers
        "versichertennummer", "versichertennr", "versicherungsnummer", "versichertenid",
        "versichertenstatus", "kvnr", "krankenversicherung", "versicherung",
        "versicherungsnehmer", "versicherungsart", "tarif", "policennummer",
        "patientennummer", "patientenid", "patid", "fallnummer", "aktenzeichen",
        "chipkartennummer", "egknummer",
        # payment
        "iban", "bic", "kontonummer", "kontoinhaber", "blz", "bankverbindung", "bankname",
        "mandatsreferenz", "glaeubigerid", "sepa", "lastschrift",
        # free-form identity
        "unterschrift", "ausweisnummer", "steuernummer",
    }
)

#: Attributes carrying the same, matched the same way.
IDENTITY_ATTRIBUTES = frozenset(
    {
        "name", "vorname", "nachname", "geburtsdatum", "gebdatum", "geschlecht",
        "patientenname", "patientennummer", "patientenid", "patid",
        "versichertennummer", "versichertennr", "versicherungsnummer", "kvnr",
        "strasse", "plz", "ort", "telefon", "email", "iban", "bic",
        "aisrechnungsnr", "aispatientennr",
    }
)

#: The exception that keeps the order file valid. `auftrag > datei > name` is the FILENAME of the
#: payload, not a person's name, and removing it produces a container the receiving system cannot
#: match its own members against. Keyed by (parent local name, child local name).
KEEP_DESPITE_DENYLIST = frozenset({("datei", "name")})

#: Free text the audit needs and this script therefore keeps. Scanned, never emptied — unless
#: --redact-freetext says otherwise.
FREETEXT_ELEMENTS = frozenset({"text", "begruendung", "beschreibung", "bemerkung", "hinweis"})


# ── The residual scan ──────────────────────────────────────────────────────────────────────────
#
# Heuristics over the free text that survives. Every one of these fires on legitimate content
# sometimes — a `begruendung` may honestly cite the date of a report — so this reports and does
# not remove. `--fail-on-residual` turns the report into a non-zero exit for a CI pipeline that
# wants to be stricter than a person reading a terminal.

RESIDUAL_PATTERNS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("Datum im Format TT.MM.JJJJ (mögliches Geburtsdatum)", re.compile(r"\b\d{2}\.\d{2}\.(19|20)\d{2}\b")),
    ("Versichertennummer-Muster (Buchstabe + 9 Ziffern)", re.compile(r"\b[A-Z]\d{9}\b")),
    ("IBAN-Muster", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")),
    ("Ziffernfolge mit 8 oder mehr Stellen", re.compile(r"\b\d{8,}\b")),
    ("E-Mail-Adresse", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("Namensanrede (Herr/Frau/Dr./Prof. + Name)", re.compile(r"\b(?:Herrn?|Frau|Dr\.|Prof\.)\s+[A-ZÄÖÜ][a-zäöüß]{2,}")),
)


class AnonymiseError(RuntimeError):
    """The input cannot be processed. Always carries a sentence an operator can act on."""


# ── Small XML helpers, namespace-insensitive like the reader's ─────────────────────────────────


def local(tag: object) -> str:
    """The local name, with any `{namespace}` prefix stripped. Non-elements answer ''."""
    if not isinstance(tag, str):
        return ""  # a comment or a processing instruction; ElementTree gives those callables
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def attr_local(name: str) -> str:
    return name.rsplit("}", 1)[-1] if "}" in name else name


def parse_xml(data: bytes, *, what: str) -> ET.Element:
    """Parse untrusted XML, refusing a DOCTYPE outright.

    ElementTree does not fetch external entities but does expand internal ones, which is enough
    for a billion-laughs expansion. Refusing the declaration removes the class rather than
    bounding it — the same choice `apps/engine/app/padnext/reader.py` makes, and PADnext payloads
    do not carry one.
    """
    if len(data) > MAX_XML_BYTES:
        raise AnonymiseError(f"{what} is {len(data)} bytes, above the {MAX_XML_BYTES}-byte limit")
    if b"<!DOCTYPE" in data[:8192].upper():
        raise AnonymiseError(f"{what} declares a DOCTYPE, which this script refuses")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        line, column = getattr(exc, "position", (None, None))
        where = f" (Zeile {line}, Spalte {column})" if line is not None else ""
        raise AnonymiseError(f"{what} is not well-formed XML{where}: {exc}") from exc


def serialise(root: ET.Element) -> bytes:
    """Back to bytes, with the PADnext namespace as the default so no `ns0:` prefixes appear.

    Comments and processing instructions are gone by this point: ElementTree drops them on parse.
    That is a small win rather than a loss here — a comment in an export is as capable of holding
    a patient's name as an element is, and nothing downstream reads them.
    """
    ET.register_namespace("", PAD_NS)
    body = ET.tostring(root, encoding="utf-8", xml_declaration=False)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + body + b"\n"


# ── The report ─────────────────────────────────────────────────────────────────────────────────


class Report:
    """What the script did, so that the operator sees it and the spec can be checked against it."""

    def __init__(self) -> None:
        self.removed_elements: dict[str, int] = {}
        self.removed_attributes: dict[str, int] = {}
        self.masked: dict[str, int] = {}
        self.redacted_freetext = 0
        self.echtdaten_before: dict[str, str] = {}
        self.echtdaten_set: list[str] = []
        self.residual: list[tuple[str, str, str]] = []  # (element path, pattern label, excerpt)
        self.members: list[str] = []

    def removed_element(self, name: str) -> None:
        self.removed_elements[name] = self.removed_elements.get(name, 0) + 1

    def removed_attribute(self, name: str) -> None:
        self.removed_attributes[name] = self.removed_attributes.get(name, 0) + 1

    def mask(self, name: str) -> None:
        self.masked[name] = self.masked.get(name, 0) + 1

    @property
    def total_removed(self) -> int:
        return sum(self.removed_elements.values()) + sum(self.removed_attributes.values())


# ── The two transformations ────────────────────────────────────────────────────────────────────


def strip_identity(element: ET.Element, report: Report, *, parent_name: str = "") -> None:
    """The denylist pass. Removes identifying children, masks identifying attributes.

    Recursive and in place. A removed element takes its whole subtree with it — `<patient>` is on
    the list, so `<patient><name>…</name><geburtsdatum>…</geburtsdatum></patient>` goes as one
    unit and the children are never visited.
    """
    name = local(element.tag)

    for attribute in list(element.attrib):
        if attr_local(attribute).lower() in IDENTITY_ATTRIBUTES:
            del element.attrib[attribute]
            report.removed_attribute(f"{name}/@{attr_local(attribute)}")

    for child in list(element):
        child_name = local(child.tag)
        if not child_name:
            continue
        if (name, child_name.lower()) in KEEP_DESPITE_DENYLIST:
            continue
        if child_name.lower() in IDENTITY_ELEMENTS:
            element.remove(child)
            report.removed_element(child_name)
            continue
        strip_identity(child, report, parent_name=name)


def apply_allowlist(element: ET.Element, report: Report) -> None:
    """The `strict` pass over a payload. Keeps only what `KEEP_ELEMENTS` names.

    Runs BEFORE `strip_identity`, so the denylist afterwards is a second net over a document that
    should already contain nothing but positions — and if it ever catches something, that is worth
    knowing, which is why both counts appear in the summary.
    """
    name = local(element.tag)

    permitted = KEEP_ATTRIBUTES.get(name, frozenset())
    for attribute in list(element.attrib):
        if attr_local(attribute) not in permitted:
            del element.attrib[attribute]
            report.removed_attribute(f"{name}/@{attr_local(attribute)}")

    for child in list(element):
        child_name = local(child.tag)
        if not child_name:
            continue
        if child_name not in KEEP_ELEMENTS:
            element.remove(child)
            report.removed_element(child_name)
            continue
        apply_allowlist(child, report)


def scan_freetext(element: ET.Element, report: Report, *, path: str = "", redact: bool = False) -> None:
    """Look through the text that survived, and either report it or blank it."""
    name = local(element.tag)
    here = f"{path}/{name}" if path else name

    if name.lower() in FREETEXT_ELEMENTS and (element.text or "").strip():
        value = element.text.strip()
        if redact:
            element.text = PLACEHOLDER
            report.redacted_freetext += 1
        else:
            for label, pattern in RESIDUAL_PATTERNS:
                match = pattern.search(value)
                if match:
                    excerpt = value if len(value) <= 90 else value[:87] + "…"
                    report.residual.append((here, label, excerpt))
                    break  # one finding per field is enough to make somebody read it

    for child in element:
        if local(child.tag):
            scan_freetext(child, report, path=here, redact=redact)


def set_echtdaten(root: ET.Element, report: Report) -> None:
    """Stamp `echtdaten="false"` on the root, whatever was there before.

    On `<auftrag>` this is the attribute the PADnext specification defines. On `<rechnungen>` it is
    an addition — the subset schema in `data/schemas/padnext/` allows it (`xs:anyAttribute`), and
    `apps/engine/app/padnext/reader.py` reads it there so that a BARE payload, uploaded without its
    order file, still carries the declaration. Without that, a bare `*_padx.xml` has no way to say
    it was anonymised, and the engine now refuses a delivery that cannot say so.

    The previous value is recorded rather than discarded: "this file said echtdaten=1 before we
    touched it" is the single most useful line in the summary.
    """
    name = local(root.tag)
    before = root.get("echtdaten")
    if before is not None:
        report.echtdaten_before[name] = before
    root.set("echtdaten", "false")
    report.echtdaten_set.append(name)


def anonymise_document(data: bytes, *, mode: str, what: str, report: Report,
                       redact_freetext: bool = False) -> bytes:
    """One XML document in, one anonymised XML document out."""
    root = parse_xml(data, what=what)
    name = local(root.tag)

    if name == "rechnungen" and mode == "strict":
        apply_allowlist(root, report)

    strip_identity(root, report)
    scan_freetext(root, report, redact=redact_freetext)

    if name in {"auftrag", "rechnungen"}:
        set_echtdaten(root, report)

    return serialise(root)


# ── The container ──────────────────────────────────────────────────────────────────────────────


def is_order_file(filename: str) -> bool:
    lowered = Path(filename).name.lower()
    return lowered.endswith(".auf") or lowered.endswith("_auf.xml")


def is_payload(filename: str) -> bool:
    lowered = Path(filename).name.lower()
    return lowered.endswith(".xml") and not is_order_file(filename)


def refresh_checksums(order_root: ET.Element, payload: bytes) -> None:
    """Recompute `datei/dateilaenge/@laenge` and `@pruefsumme` over the rewritten payload.

    Anonymising the payload changes its length and its hash, so the values the sending system
    computed are now wrong. Leaving them wrong would make the container fail a conforming
    receiver's own integrity check — and would do it *after* the practice had been told the file
    was ready to send, which is the worst moment to find out.

    SHA-1 hex, lower case, 40 characters: the width the field carries in every PADnext export seen
    here and in the bundled fixture. It is an integrity check against corruption in transit, not a
    security control, and nothing in this repository treats it as one.
    """
    digest = hashlib.sha1(payload).hexdigest()  # noqa: S324 - transport integrity, not security
    for datei in order_root.iter():
        if local(datei.tag) != "dateilaenge":
            continue
        datei.set("laenge", str(len(payload)))
        datei.set("pruefsumme", digest)


def anonymise_container(data: bytes, *, mode: str, report: Report,
                        redact_freetext: bool = False) -> bytes:
    """A `.padx` in, a `.padx` out, with every member rewritten and the checksums refreshed."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise AnonymiseError(f"looks like a .padx container but cannot be opened: {exc}") from exc

    infos = [i for i in archive.infolist() if not i.is_dir()]
    if len(infos) > MAX_ZIP_MEMBERS:
        raise AnonymiseError(f"container holds {len(infos)} members, above the safety limit")
    if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
        raise AnonymiseError("container expands past the safety limit")
    for info in infos:
        parts = Path(info.filename).parts
        if ".." in parts or Path(info.filename).is_absolute():
            raise AnonymiseError(f"container member escapes the archive root: {info.filename!r}")

    report.members = [i.filename for i in infos]

    # The payload first: the order file's checksum is computed over the ANONYMISED bytes, so it
    # cannot be written until they exist.
    rewritten: dict[str, bytes] = {}
    payload_bytes: bytes | None = None
    payload_name: str | None = None

    for info in infos:
        if is_payload(info.filename):
            payload_bytes = anonymise_document(
                archive.read(info), mode=mode, what=info.filename, report=report,
                redact_freetext=redact_freetext,
            )
            rewritten[info.filename] = payload_bytes
            payload_name = info.filename
            break

    if payload_bytes is None:
        raise AnonymiseError(
            "container holds no payload XML. Expected a member named "
            "<kundennr>_<datum>_<typ>_<nr>_padx.xml"
        )

    for info in infos:
        if info.filename == payload_name:
            continue
        if is_order_file(info.filename):
            order_root = parse_xml(archive.read(info), what=info.filename)
            if local(order_root.tag) == "auftrag":
                strip_identity(order_root, report)
                set_echtdaten(order_root, report)
                refresh_checksums(order_root, payload_bytes)
                rewritten[info.filename] = serialise(order_root)
                continue
        # Anything else in the container is not something this script can vouch for, so it is not
        # carried over. A member it cannot read is a member it cannot promise is anonymised.
        report.removed_element(f"[Containerdatei] {info.filename}")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for name, payload in rewritten.items():
            target.writestr(name, payload)
    return out.getvalue()


# ── Driving it ─────────────────────────────────────────────────────────────────────────────────


def default_output(source: Path) -> Path:
    """`export.padx` → `export.anonymized.padx`. Never the input, and never a silent overwrite."""
    return source.with_name(f"{source.stem}.anonymized{source.suffix}")


def run(source: Path, target: Path, *, mode: str, redact_freetext: bool) -> Report:
    if not source.is_file():
        raise AnonymiseError(f"no such file: {source}")
    try:
        data = source.read_bytes()
    except OSError as exc:
        raise AnonymiseError(f"cannot read {source}: {exc}") from exc
    if not data:
        raise AnonymiseError(f"{source} is empty")

    report = Report()
    if data[:4] == b"PK\x03\x04":
        result = anonymise_container(data, mode=mode, report=report, redact_freetext=redact_freetext)
    else:
        result = anonymise_document(
            data, mode=mode, what=source.name, report=report, redact_freetext=redact_freetext
        )

    try:
        target.write_bytes(result)
    except OSError as exc:
        raise AnonymiseError(f"cannot write {target}: {exc}") from exc
    return report


def print_report(report: Report, *, source: Path, target: Path, mode: str) -> None:
    def line(text: str = "") -> None:
        print(text, file=sys.stderr)

    line()
    line(f"  Eingabe   {source}")
    line(f"  Ausgabe   {target}")
    line(f"  Modus     {mode}" + ("  (Allowlist)" if mode == "strict" else "  (Denylist)"))
    if report.members:
        line(f"  Container {', '.join(report.members)}")
    line()

    for root_name in report.echtdaten_set:
        before = report.echtdaten_before.get(root_name)
        was = f'war echtdaten="{before}"' if before is not None else "war nicht gesetzt"
        marker = "  ⚠ ECHTDATEN" if before in {"1", "true", "True"} else "   "
        line(f'{marker}  <{root_name}> echtdaten="false" gesetzt ({was})')
    line()

    if report.removed_elements:
        line("  Entfernte Elemente:")
        for name, count in sorted(report.removed_elements.items(), key=lambda kv: (-kv[1], kv[0])):
            line(f"      {count:>4} ×  <{name}>")
    if report.removed_attributes:
        line("  Entfernte Attribute:")
        for name, count in sorted(report.removed_attributes.items(), key=lambda kv: (-kv[1], kv[0])):
            line(f"      {count:>4} ×  {name}")
    if report.redacted_freetext:
        line(f"  Freitextfelder geleert: {report.redacted_freetext}")
    if not report.total_removed and not report.redacted_freetext:
        line("  Nichts zu entfernen gefunden — die Datei enthielt keine erkannten Identitätsfelder.")
    line()

    if report.residual:
        line("  ⚠  RESTBEFUNDE IM FREITEXT — bitte selbst prüfen:")
        line("     Diese Felder bleiben erhalten, weil die Prüfung sie braucht (§ 12 Abs. 3 GOÄ).")
        line("     Das Skript kann nicht entscheiden, ob darin Patientendaten stehen. Sie können.")
        line()
        for path, label, excerpt in report.residual[:20]:
            line(f"      {path}")
            line(f"        {label}")
            line(f"        „{excerpt}“")
        if len(report.residual) > 20:
            line(f"      … und {len(report.residual) - 20} weitere")
        line()
        line("     Mit --redact-freetext werden diese Felder durch "
             f"„{PLACEHOLDER}“ ersetzt.")
        line("     Das entfernt aber auch die Begründungen, die die Prüfung bewertet.")
        line()

    if mode == "mask":
        line("  ⚠  Modus 'mask' ist eine Denylist: Felder, die dieses Skript nicht kennt,")
        line("     bleiben erhalten. Für den Upload nach Azmoth wird 'strict' empfohlen.")
        line()


# ── Self-test ──────────────────────────────────────────────────────────────────────────────────


def selftest() -> int:
    """Prove the script works, on a delivery it builds itself, with no fixture on disk.

    This is what an operator runs to check the copy they were sent is intact, and what CI runs to
    check a change here did not quietly stop removing something.
    """
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"  ok    {name}")
        else:
            print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
            failures.append(name)

    payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<rechnungen anzahl="1" xmlns="{PAD_NS}">
  <nachrichtentyp version="02.12">ADL</nachrichtentyp>
  <rechnungsersteller><name>Praxis Dr. Weber</name></rechnungsersteller>
  <rechnung id="RG-1" aisrechnungsnr="INTERN-88123">
    <patient patid="P-4711" geburtsdatum="1961-03-14">
      <patient_name>Schmidt</patient_name>
      <vorname>Erika</vorname>
      <patient_address><strasse>Hauptstr. 3</strasse><plz>10115</plz><ort>Berlin</ort></patient_address>
      <geburtsdatum>1961-03-14</geburtsdatum>
      <versichertennummer>A123456789</versichertennummer>
    </patient>
    <patientenchip>irgendein-vendor-feld-das-niemand-kennt</patientenchip>
    <abrechnungsfall>
      <behandlungsart>0</behandlungsart>
      <vertragsart>1</vertragsart>
      <positionen posanzahl="1">
        <goziffer positionsnr="1" go="GOÄ" ziffer="1">
          <datum>2026-07-20</datum>
          <anzahl>1</anzahl>
          <text>Beratung</text>
          <faktor>3.5</faktor>
          <begruendung>Ausführliche Beratung, Frau Schmidt, geb. 14.03.1961</begruendung>
          <gesamtbetrag>16.32</gesamtbetrag>
        </goziffer>
      </positionen>
    </abrechnungsfall>
  </rechnung>
</rechnungen>
""".encode()

    order = f"""<?xml version="1.0" encoding="UTF-8"?>
<auftrag transfernr="1" echtdaten="1" dateianzahl="1" xmlns="{PAD_NS}">
  <nachrichtentyp version="02.12">ADL</nachrichtentyp>
  <datei id="d1">
    <name>00004711_20260726_ADL_000001_padx.xml</name>
    <dateilaenge pruefsumme="0000000000000000000000000000000000000000" laenge="0"/>
  </datei>
</auftrag>
""".encode()

    print("\nstrict mode, bare payload")
    report = Report()
    out = anonymise_document(payload, mode="strict", what="selftest", report=report)
    text = out.decode()
    root = ET.fromstring(out)

    check('root carries echtdaten="false"', root.get("echtdaten") == "false", root.get("echtdaten") or "")
    for gone in ("Erika", "Hauptstr", "10115", "Berlin", "A123456789",
                 "P-4711", "INTERN-88123", "patientenchip", "Praxis Dr. Weber",
                 "<patient_name>", "<geburtsdatum>", "<versichertennummer>"):
        check(f"{gone!r} is gone", gone not in text)

    # The surname survives — inside <begruendung>, where a human typed it into a sentence, and
    # NOT in any structured field. That is the honest limit of this script and the reason the
    # residual scan exists, so it is asserted rather than glossed over: a future change that
    # started emptying free text by default would break this check and have to argue with it.
    check("no structured field still holds the surname",
          "<patient_name>Schmidt" not in text and "Schmidt</" not in text.replace(
              "Frau Schmidt, geb. 14.03.1961</begruendung>", ""))
    check("the surname DOES survive in the free text, unredacted, by design",
          "Frau Schmidt" in text)
    check("the GOÄ position survived", "ziffer=\"1\"" in text and "16.32" in text)
    check("the justification survived", "Ausführliche Beratung" in text)
    check("an unknown vendor element was dropped by the allowlist",
          "patientenchip" in report.removed_elements)
    check("the residual scan flagged the name left in the free text",
          any("begruendung" in path for path, _, _ in report.residual),
          f"{report.residual}")

    print("\nmask mode, bare payload")
    masked = Report()
    out_masked = anonymise_document(payload, mode="mask", what="selftest", report=masked)
    masked_text = out_masked.decode()
    check("identity fields are gone in mask mode too", "A123456789" not in masked_text)
    check("mask mode KEEPS the unknown vendor element (that is the point of the warning)",
          "patientenchip" in masked_text)

    print("\n.padx container")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("00004711_20260726_ADL_000001.auf", order)
        z.writestr("00004711_20260726_ADL_000001_padx.xml", payload)
    creport = Report()
    result = anonymise_container(buffer.getvalue(), mode="strict", report=creport)

    with zipfile.ZipFile(io.BytesIO(result)) as z:
        names = sorted(z.namelist())
        auf = z.read("00004711_20260726_ADL_000001.auf")
        pay = z.read("00004711_20260726_ADL_000001_padx.xml")
    auf_root = ET.fromstring(auf)

    check("both members survive", len(names) == 2, str(names))
    check('the order file now says echtdaten="false"', auf_root.get("echtdaten") == "false")
    check('the order file previously said echtdaten="1", and that was reported',
          creport.echtdaten_before.get("auftrag") == "1")
    check("the payload inside the container is anonymised", b"A123456789" not in pay)
    check("datei/name was NOT stripped — it is a filename, not a person",
          b"00004711_20260726_ADL_000001_padx.xml" in auf)

    digest = hashlib.sha1(pay).hexdigest()  # noqa: S324
    laenge = next(e for e in auf_root.iter() if local(e.tag) == "dateilaenge")
    check("the checksum was recomputed over the anonymised payload",
          laenge.get("pruefsumme") == digest, f"{laenge.get('pruefsumme')} != {digest}")
    check("the length was recomputed", laenge.get("laenge") == str(len(pay)))

    print("\nredaction")
    redacted = Report()
    out_redacted = anonymise_document(payload, mode="strict", what="selftest",
                                      report=redacted, redact_freetext=True)
    check("--redact-freetext empties the justification",
          b"Frau Schmidt" not in out_redacted and PLACEHOLDER.encode() in out_redacted)

    print("\nrefusals")
    for bad, why in (
        (b"<!DOCTYPE foo []><rechnungen/>", "a DOCTYPE"),
        (b"<rechnungen", "malformed XML"),
    ):
        try:
            anonymise_document(bad, mode="strict", what="selftest", report=Report())
            check(f"{why} is refused", False, "no error raised")
        except AnonymiseError:
            check(f"{why} is refused", True)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}\n")
        return 1
    print("all self-tests passed\n")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="anonymize_padnext.py",
        description="Anonymise a PADnext delivery for upload to Azmoth. "
                    "See docs/pilot/ANONYMIZATION_SPEC.md.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit status: 0 written · 1 unreadable input · 2 bad usage · "
               "3 residual findings with --fail-on-residual",
    )
    parser.add_argument("input", nargs="?", type=Path,
                        help="the .padx container, *_padx.xml payload or .auf order file")
    parser.add_argument("-o", "--output", type=Path,
                        help="where to write it (default: <input>.anonymized.<ext>)")
    parser.add_argument("--mode", choices=("strict", "mask"), default="strict",
                        help="strict = allowlist, keep only what the engine reads (default); "
                             "mask = denylist, keep the document shape")
    parser.add_argument("--redact-freetext", action="store_true",
                        help=f"also replace <text>/<begruendung> with '{PLACEHOLDER}'. "
                             "Removes the justifications the audit evaluates.")
    parser.add_argument("--fail-on-residual", action="store_true",
                        help="exit 3 if the residual scan finds anything in the free text")
    parser.add_argument("--force", action="store_true",
                        help="overwrite the output file if it already exists")
    parser.add_argument("--quiet", action="store_true", help="only print the output path")
    parser.add_argument("--selftest", action="store_true",
                        help="run the built-in checks and exit; needs no input file")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.selftest:
        return selftest()
    if args.input is None:
        parser.error("an input file is required (or --selftest)")

    source: Path = args.input
    target: Path = args.output or default_output(source)

    if target.resolve() == source.resolve():
        print(f"!! refusing to write over the input: {source}", file=sys.stderr)
        print("   The original is the only copy of the un-anonymised data. Choose another -o.",
              file=sys.stderr)
        return 2
    if target.exists() and not args.force:
        print(f"!! {target} already exists. Pass --force to overwrite it.", file=sys.stderr)
        return 2

    try:
        report = run(source, target, mode=args.mode, redact_freetext=args.redact_freetext)
    except AnonymiseError as exc:
        print(f"!! {exc}", file=sys.stderr)
        return 1

    if args.quiet:
        print(target)
    else:
        print_report(report, source=source, target=target, mode=args.mode)
        print(target)

    if report.residual and args.fail_on_residual:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
