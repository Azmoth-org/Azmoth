#!/usr/bin/env python3
"""Prüfe eine PADnext-Lieferung, ohne sie hochzuladen — validate a PADnext delivery locally.

    ./scripts/validate_padnext.py lieferung.padx
    ./scripts/validate_padnext.py export_padx.xml --json
    ./scripts/validate_padnext.py *.padx --quiet
    ./scripts/validate_padnext.py lieferung.padx --schema-policy warn

Prints every error and every warning the engine would report, with the line, the XML path, why it
matters and how to fix it — the same list `POST /padnext/validate` returns, because it is the same
function (`app.padnext.validation.validate_bytes`). Nothing is uploaded and nothing is stored.

── Why this exists ────────────────────────────────────────────────────────────────────────────
The loop it removes is the expensive one. Without it, finding out whether an export profile is
right means uploading a file, reading a refusal, changing the profile, and uploading again — and
each pass through that loop needs a network, an account, a quota unit and a browser. A PVS vendor
adjusting a template does that fifteen times. Here it is a second, offline, in a terminal, against
the same checks.

It is also the honest answer to "can I try this without sending you patient data": yes, and this
is the command.

── Exit status ────────────────────────────────────────────────────────────────────────────────
    0   valid — the delivery is readable; warnings may still have been printed
    1   validation failed — the document was read and something in it is refused
    2   bad usage, or a file that could not be opened
    3   parse failed — the bytes are not a document this engine can read at all

`1` and `3` are separated because the next action differs: a `1` is a field to change in an export
profile, a `3` is a broken or truncated file. A single failure code would make a shell script
treat "your echtdaten attribute is missing" and "this is a PDF" as the same problem.

── This one needs the engine's environment, unlike `anonymize_padnext.py` ─────────────────────
`scripts/anonymize_padnext.py` is stdlib-only on purpose: it runs on the practice's own machine, on
data that has not been anonymised yet, and asking their IT to approve a package tree before that
step is not reasonable. This script has the opposite constraint — it must agree with the engine
exactly, down to the schema and the message texts, and reimplementing that in the standard library
would produce a second validator that drifts. So it imports the engine, and it says so clearly if
the environment is not there.

    apps/engine/.venv/bin/python scripts/validate_padnext.py lieferung.padx
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Where `app` lives. Two layouts, and the fallback is not defensive padding — it is what lets CI
#: run this script's tests. In a checkout the engine is `apps/engine`; inside the engine image the
#: app is unpacked at the root (`/srv/app`, see `app.config._find_repo_root`, which resolves the
#: same two cases) and this file is copied next to it. Without the fallback the eleven CLI tests in
#: `tests/test_padnext_validation.py` cannot run in the image, and CI runs the suite only there —
#: they would have to be skipped, which is the one thing this repo's CI is built not to do.
ENGINE = REPO_ROOT / "apps" / "engine"
if not (ENGINE / "app").is_dir():
    ENGINE = REPO_ROOT

#: Exit codes, named because a shell script reading them should be able to quote this file.
EXIT_VALID = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_UNREADABLE = 3

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
RED, YELLOW, GREEN, BLUE = "\033[31m", "\033[33m", "\033[32m", "\033[34m"


def _quiet_engine_logging(debug: bool) -> None:
    """Keep the engine's operator logging out of a terminal report.

    `app.padnext.reader` writes one structured line per schema violation — deliberately, because
    on a running service that is the only durable record that a non-conforming delivery was let
    through under `PADNEXT_SCHEMA_POLICY=warn`. Nobody is watching a log stream here: the report
    below already names every violation with its line, and the same text arriving twice, once
    unformatted and interleaved with the header, makes the report look broken.

    `--debug` puts it back, because the one time it is wanted is when this script disagrees with
    the API and the question is which policy each of them actually ran under.
    """
    logging.getLogger("app").setLevel(logging.DEBUG if debug else logging.CRITICAL)
    if debug:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)


def _import_engine() -> Any:
    """Import the validator, or explain what is missing and exit rather than tracebacking.

    A `ModuleNotFoundError` for `lxml` at the top of a 300-line traceback is the least useful
    possible answer to "I ran the script and it did not work", and the fix is one line of shell.
    """
    sys.path.insert(0, str(ENGINE))
    try:
        from app.padnext.validation import validate_bytes  # noqa: PLC0415
    except ImportError as exc:
        sys.stderr.write(
            f"Die Engine-Umgebung fehlt: {exc}\n\n"
            "Dieses Skript nutzt denselben Validator wie die API und braucht daher deren\n"
            "Abhängigkeiten (lxml, pydantic). Mit dem Engine-Interpreter aufrufen:\n\n"
            f"    {ENGINE.relative_to(REPO_ROOT)}/.venv/bin/python "
            f"{Path(__file__).relative_to(REPO_ROOT)} <datei>\n\n"
            "Falls die venv fehlt:\n\n"
            "    cd apps/engine && python3 -m venv .venv && "
            ".venv/bin/pip install -r requirements.txt\n\n"
            "— This script shares the engine's validator and needs its dependencies. Run it with\n"
            "  the engine's interpreter, as shown above.\n"
        )
        raise SystemExit(EXIT_USAGE) from exc
    return validate_bytes


# ==============================================================================================
# the report
# ==============================================================================================


def _colour(enabled: bool):
    """Return a `paint(text, code)`. Colour is opt-out and off when stdout is not a terminal."""

    def paint(text: str, code: str) -> str:
        return f"{code}{text}{RESET}" if enabled else text

    return paint


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line if line else "" for line in text.splitlines())


def print_report(result: Any, path: Path, *, paint, verbose: bool, stream=sys.stdout) -> None:
    """The human-readable report. German, because the reader of an error here is a practice.

    Every issue prints its four sections — what, where, why, how — and `--quiet` prints only the
    first. The "why" is not decoration: an instruction without a reason is followed until it is
    inconvenient, and `echtdaten="1"` is one character away from `echtdaten="0"`.
    """
    errors, warnings = result.errors, result.warnings
    status = {
        "valid": paint("✔ gültig", GREEN),
        "validation_failed": paint("✖ Prüfung fehlgeschlagen", RED),
        "parse_failed": paint("✖ Datei nicht lesbar", RED),
    }[result.status]

    write = stream.write
    write(f"\n{paint('PADnext-Validierungsbericht', BOLD)}\n")
    write("=" * 60 + "\n")
    write(f"Datei:   {path}\n")
    write(f"Status:  {status}")
    if errors or warnings:
        counts = []
        if errors:
            counts.append(f"{len(errors)} Fehler")
        if warnings:
            counts.append(f"{len(warnings)} Hinweis(e)")
        write(f" ({', '.join(counts)})")
    write("\n")
    write(f"Schema:  {result.schema_policy}\n")

    for label, issues, code in (
        ("Fehler (blockierend)", errors, RED),
        ("Hinweise (nicht blockierend)", warnings, YELLOW),
    ):
        if not issues:
            continue
        write(f"\n{paint(label, BOLD)}\n")
        for number, issue in enumerate(issues, start=1):
            head = f"  {number}. [{issue.code}]"
            if issue.location:
                head += f" {issue.location}"
            write(paint(head, code) + "\n")
            write(_indent(issue.message_de, "     ") + "\n")
            if verbose and issue.why_de:
                write(_indent(paint("Warum:", DIM), "     ") + "\n")
                write(_indent(issue.why_de, "       ") + "\n")
            if verbose and issue.fix:
                write(_indent(paint("Lösung:", DIM), "     ") + "\n")
                write(_indent(issue.fix, "       ") + "\n")
            if issue.command:
                write(_indent(paint(f"$ {issue.command}", BLUE), "     ") + "\n")
            write("\n")

    preview = result.preview

    # Suppressed when the document yielded nothing at all — a PDF, an empty file, a container
    # with no payload. A block headed "was gelesen wurde" listing three zeros reads as a second
    # failure rather than as reassurance, and its "beschädigtes Dokument" line is simply wrong
    # about a file that was never XML. `ParsedPreview` in the web UI suppresses itself on the same
    # condition, for the same reason.
    if not preview.invoice_count and not preview.position_count:
        if not errors:
            write(paint("Diese Datei kann geprüft werden.", GREEN) + "\n")
        write("\n")
        return

    write(f"{paint('Gelesen (auch bei Fehlern)', BOLD)}\n")
    if preview.recovered:
        write(
            "  "
            + paint(
                "Die Zahlen stammen aus einer Notfall-Lesung eines beschädigten Dokuments —\n"
                "  sie sind eine Untergrenze, nicht der tatsächliche Inhalt.",
                DIM,
            )
            + "\n"
        )
    write(f"  Rechnungen:            {preview.invoice_count}\n")
    write(f"  Abrechnungsfälle:      {preview.case_count}\n")
    write(f"  GOÄ/GOZ-Positionen:    {preview.position_count}\n")
    if preview.other_position_count:
        write(
            f"  weitere Positionen:    {preview.other_position_count} "
            + paint("(von dieser Prüfung nicht bewertet)", DIM)
            + "\n"
        )
    if preview.date_range:
        write(f"  Leistungszeitraum:     {preview.date_range}\n")
    if preview.nachrichtentyp or preview.version:
        write(f"  Nachrichtentyp:        {preview.nachrichtentyp or '—'} {preview.version}\n")
    if preview.transfernr:
        write(f"  Transfernummer:        {preview.transfernr}\n")
    write(f"  echtdaten:             {preview.echtdaten_declared or '— (nicht erklärt)'}\n")
    if preview.first_invoice:
        first = preview.first_invoice
        art = first.get("behandlungsart_label") or first.get("behandlungsart") or "—"
        write(
            f"  erste Rechnung:        {first.get('invoice_id') or '(ohne Nummer)'}, "
            f"{first.get('position_count', 0)} Positionen, {art}\n"
        )
    if preview.container_members:
        write(f"  Container:             {', '.join(preview.container_members)}\n")
    write("\n")

    if not errors:
        write(paint("Diese Datei kann geprüft werden.", GREEN) + "\n")
    elif not verbose:
        write(
            paint(
                "Ohne --quiet steht zu jedem Punkt die Begründung und die Lösung dabei.", DIM
            )
            + "\n"
        )
    write("\n")


def exit_code_for(result: Any) -> int:
    if result.status == "parse_failed":
        return EXIT_UNREADABLE
    return EXIT_VALID if result.ok else EXIT_INVALID


# ==============================================================================================
# main
# ==============================================================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate_padnext.py",
        description=(
            "Prüft eine PADnext-Lieferung lokal und meldet ALLE Fehler und Hinweise auf einmal. "
            "Validate a PADnext delivery locally, reporting every problem at once."
        ),
        epilog=(
            "Exit: 0 gültig · 1 Prüfung fehlgeschlagen · 2 Aufruffehler · 3 Datei nicht lesbar"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("files", nargs="*", type=Path, help="eine oder mehrere PADnext-Dateien")
    parser.add_argument(
        "--json",
        action="store_true",
        help="statt des Berichts das JSON ausgeben, das die API liefert",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="nur die Meldungen, ohne Begründung und Lösung",
    )
    parser.add_argument(
        "--schema-policy",
        choices=("strict", "warn", "off"),
        help="Schemaprüfung überschreiben; ohne Angabe gilt PADNEXT_SCHEMA_POLICY",
    )
    parser.add_argument("--no-color", action="store_true", help="keine ANSI-Farben")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="die Log-Ausgaben der Engine mitschreiben (nach stderr)",
    )
    args = parser.parse_args(argv)

    if not args.files:
        parser.print_help()
        return EXIT_USAGE

    validate_bytes = _import_engine()
    _quiet_engine_logging(args.debug)
    from app.config import PadnextSchemaPolicy  # noqa: PLC0415 - after the path is set up

    policy = PadnextSchemaPolicy(args.schema_policy) if args.schema_policy else None
    paint = _colour(not args.no_color and sys.stdout.isatty())

    # The worst outcome across every file, so `validate_padnext.py *.padx` in a pre-commit hook
    # fails on the batch rather than on whichever file happened to be last.
    worst = EXIT_VALID
    documents: list[dict[str, Any]] = []

    for path in args.files:
        if not path.is_file():
            sys.stderr.write(f"Keine solche Datei: {path}\n")
            worst = max(worst, EXIT_USAGE)
            continue
        result = validate_bytes(path.read_bytes(), source_name=path.name, schema_policy=policy)
        if args.json:
            documents.append({"file": str(path), **result.as_dict()})
        else:
            print_report(result, path, paint=paint, verbose=not args.quiet)
        worst = max(worst, exit_code_for(result))

    if args.json:
        # One document for one file, a list for several: a caller piping into `jq` for the common
        # case should not have to index into an array of one.
        payload = documents[0] if len(documents) == 1 else documents
        print(json.dumps(payload, indent=2, ensure_ascii=False))

    return worst


if __name__ == "__main__":
    sys.exit(main())
