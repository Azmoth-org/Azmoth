"""Turning a durable record into a file somebody outside this system can act on.

Two exports live here because they share one rule and nothing else: **the bytes are built from the
database row, never from an object a caller handed in.** Everything below takes either an ORM
record or a model that was just read back out of one.

    proposal  →  prop_<hex>.json           one approved draft, with its proof and its audit log
    batch     →  batch_<hex>_export.zip    three CSVs and a README, for a billing centre

The two formats are different on purpose and it is worth saying why, because "be consistent" would
be the wrong instinct here. A proposal export is read by a system — a PVS importer, or a person
checking one disputed line against the proof tree that produced it — and it has to carry nested,
irregularly-shaped evidence: proof atoms, an audit trail, a rule-coverage snapshot. JSON is the only
honest container for that; flattening a proof tree into a CSV row destroys the thing that makes it
evidence. A batch export is read by a billing centre reconciling hundreds of invoices, in the tool
billing centres actually use, and that is a spreadsheet. So one is JSON and the other is CSV, and
neither is a compromise.

**What the batch export must never do** is let the three honest buckets be read as one number. A CSV
is the easiest place in this whole codebase to lose that distinction — a column of euros invites a
SUM, and summing `unconfirmed_eur` into a "total at risk" would restate this engine's own rule
coverage as an accusation against a practice. So the buckets stay in named columns, the summary row
never carries a combined figure, and `README.txt` travels inside the ZIP carrying the same
disclaimer the screen shows. A file that leaves this system without that sentence attached is a file
that will be misread.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime
from typing import Any

from app.db.models import BatchFileRecord, BatchJobRecord, ProposalRecord, as_utc
from app.rules.rule_store import load_rules
from app.schemas.batch import BatchAggregateSummary, BatchFileStatus
from app.schemas.export import (
    AuditEventRecord,
    DecisionRecord,
    EngineIdentity,
    ProposalExport,
)
from app.schemas.padnext import PadnextAuditReport

# ------------------------------------------------------------------------------------------
# attachments
# ------------------------------------------------------------------------------------------

#: What a generated filename is allowed to contain before it goes into a response header.
#:
#: Every filename here is built from an id this service issued (`prop_<hex>`, `batch_<hex>`), so in
#: practice nothing else can occur. The check is still made, because the alternative is a header
#: whose contents came from a URL path: a newline in `Content-Disposition` is response splitting,
#: and a `"` ends the quoted string early. Refusing is right — there is no safe way to guess what a
#: caller meant by a filename with a CR in it.
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class UnsafeFilename(ValueError):
    """A generated filename did not match `SAFE_FILENAME`. A bug here, never a user's doing."""


def attachment_headers(filename: str) -> dict[str, str]:
    """`Content-Disposition` for a download, with the filename checked rather than trusted."""
    if not SAFE_FILENAME.match(filename):
        raise UnsafeFilename(
            f"refusing to put {filename!r} in a Content-Disposition header: only "
            "[A-Za-z0-9._-] is allowed, because this value reaches a response header."
        )
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def proposal_export_filename(proposal_id: str) -> str:
    """`prop_5f3a1b….json`.

    The id already carries its own prefix, so a `proposal_` in front of it would read
    `proposal_prop_5f3a1b….json`. The id alone is what a reader greps for anyway.
    """
    return f"{proposal_id}.json"


def batch_export_filename(batch_id: str) -> str:
    """`batch_4d980f…_export.zip`. Same reason as above — `batch_id` starts with `batch_`."""
    return f"{batch_id}_export.zip"


# ------------------------------------------------------------------------------------------
# the single-proposal export
# ------------------------------------------------------------------------------------------


def build_proposal_export(
    record: ProposalRecord,
    *,
    events: list[dict[str, Any]],
    exported_by: str,
    exported_at: datetime,
) -> ProposalExport:
    """Assemble the export document from the row that was just written.

    Called from inside `ProposalStore`'s export transaction, with `record` already transitioned to
    `EXPORTED` and `events` already including the `EXPORTED` row. Passing both in rather than
    re-reading them is what makes the document and the database agree by construction instead of by
    a second query that could see a different world.

    Every timestamp goes through `as_utc`: SQLite hands back a naive datetime, and an export whose
    approval time is silently off by an hour twice a year is worse than one with no timestamp.
    """
    return ProposalExport(
        proposal_id=record.proposal_id,
        case_id=record.case_id,
        status=record.status,
        created_at=as_utc(record.created_at),
        receipt_hash=record.receipt_hash,
        input_hash=record.input_hash,
        engine=EngineIdentity(
            catalog_version=record.catalog_version,
            catalog_sha256=record.catalog_sha256,
            rules_version=record.rules_version,
            rules_hash=record.rules_hash,
            logic_version=record.logic_version,
            solver_version=record.solver_version,
            rules_engine_version=record.rules_engine_version,
        ),
        decision=DecisionRecord(
            approved_by=record.approved_by,
            approved_at=as_utc(record.approved_at),
            rejected_by=record.rejected_by,
            rejected_at=as_utc(record.rejected_at),
            rejected_reason=record.rejected_reason,
            exported_by=exported_by,
            exported_at=exported_at,
        ),
        solver_result=record.solver_result_json,
        warnings=record.warnings_json or [],
        missing_documentation=record.missing_documentation_json or [],
        rule_coverage=record.rule_coverage_json,
        audit_events=[
            AuditEventRecord(
                event_type=event["event_type"],
                actor=event["actor"],
                timestamp=event["timestamp"],
                metadata=event["metadata"],
            )
            for event in events
        ],
    )


# ------------------------------------------------------------------------------------------
# the batch export
# ------------------------------------------------------------------------------------------

SUMMARY_CSV = "batch_summary.csv"
LINE_ITEMS_CSV = "batch_line_items.csv"
FILES_CSV = "batch_files.csv"
README_TXT = "README.txt"

#: Separator inside the two rule-id columns.
#:
#: A pipe rather than a comma (which is the field delimiter) or a space (a rule id could in
#: principle contain one). A cell reading `zl_man_301_200|excl_5_7` is unambiguously a list.
LIST_SEPARATOR = "|"

#: RFC 4180: comma-delimited, CRLF, quotes doubled. `csv.writer`'s defaults, named here because the
#: choice is deliberate and has a known cost.
#:
#: The cost is German Excel. A de-DE locale expects `;` between fields and `,` inside a number, so
#: double-clicking one of these files puts every row in one column. The alternative is worse: with
#: `;` and a de-DE locale, Excel reads `24.25` as a *date*, and an export that silently turns
#: €24.25 into 24 May is not a rounding problem, it is a corrupted invoice. So the file stays
#: standard, the amounts stay exactly the strings the engine computed, and `README.txt` tells the
#: reader to use Data → From Text/CSV rather than double-click. Every non-Excel consumer — a PVS
#: importer, `csv.reader`, `pandas.read_csv` — gets a file that needs no special casing at all.
CSV_DIALECT: dict[str, Any] = {"lineterminator": "\r\n"}

#: Prepended to every CSV so Excel detects UTF-8 instead of guessing a legacy code page. Without it
#: "Ultraschalluntersuchung eines Organs" is fine but "Röntgen" is not, and a mangled Leistungstext
#: in a document a payer reads is a real problem.
UTF8_BOM = "﻿"

SUMMARY_COLUMNS = [
    "batch_id",
    "created_at",
    "completed_at",
    "total_files",
    "successful_files",
    "failed_files",
    "total_claimed_eur",
    "confirmed_fine_eur",
    "confirmed_wrong_eur",
    "unconfirmed_eur",
    "coverage_ratio",
]

LINE_ITEM_COLUMNS = [
    "filename",
    "positionsnr",
    "ziffer",
    "description",
    "claimed_amount_eur",
    "bucket",
    "bucket_reason",
    "verified_rule_ids",
    "advisory_rule_ids",
]

FILE_COLUMNS = [
    "filename",
    "status",
    "claimed_total_eur",
    "confirmed_fine_eur",
    "confirmed_wrong_eur",
    "unconfirmed_eur",
    "coverage_ratio",
    "position_count",
    "error_message",
]


def _csv(rows: list[list[str]], columns: list[str]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, **CSV_DIALECT)
    writer.writerow(columns)
    writer.writerows(rows)
    return UTF8_BOM + buffer.getvalue()


def _iso(value: datetime | None) -> str:
    """A timestamp a spreadsheet and a parser can both read, or empty. Never a guess."""
    stamped = as_utc(value)
    return stamped.isoformat() if stamped else ""


def summary_rows(job: BatchJobRecord, summary: BatchAggregateSummary | None) -> list[list[str]]:
    """One row. The whole batch, in the eleven columns a billing centre reconciles against.

    Note what is absent: any column that adds two buckets together. `total_claimed_eur` is the
    claim, and the three buckets partition it — there is deliberately no "at risk" column for a
    spreadsheet to inherit, because at batch scale that number would be mostly this engine's own
    unverified rule coverage.

    `coverage_ratio` is written as the engine's own float, at full precision rather than rounded to
    a percentage: it is the one value here that is not money, and a reader who wants "51 %" can
    format it themselves. Rounding on the way out would make the file disagree with the screen.
    """
    if summary is None:
        return []
    return [
        [
            job.batch_id,
            _iso(job.created_at),
            _iso(job.completed_at),
            str(summary.file_count),
            str(summary.completed_file_count),
            str(summary.failed_file_count),
            str(summary.claimed_total_eur),
            str(summary.confirmed_fine_eur),
            str(summary.confirmed_wrong_eur),
            str(summary.unconfirmed_eur),
            repr(summary.coverage_ratio),
        ]
    ]


def line_item_rows(files: list[BatchFileRecord]) -> list[list[str]]:
    """One row per claimed position, across every audited file.

    A file that could not be read contributes no rows — it has no positions — which is exactly why
    `batch_files.csv` exists alongside this one. Reconciling row counts against `successful_files`
    without it would leave a reader unable to tell "this invoice was clean" from "this invoice was
    never opened".

    Amounts are written as the exact decimal strings the engine produced. Nothing here parses,
    rounds or re-formats a monetary value.
    """
    rows: list[list[str]] = []
    for record in files:
        if record.status != str(BatchFileStatus.COMPLETED) or not record.report_json:
            continue
        report = PadnextAuditReport.model_validate(record.report_json)
        for position in report.positions:
            rows.append(
                [
                    record.filename,
                    position.positionsnr,
                    f"{position.go} {position.ziffer}".strip(),
                    position.official_text,
                    "" if position.claimed_amount_eur is None else str(position.claimed_amount_eur),
                    position.bucket,
                    position.bucket_reason,
                    LIST_SEPARATOR.join(position.verified_rule_ids),
                    LIST_SEPARATOR.join(position.advisory_rule_ids),
                ]
            )
    return rows


def file_rows(files: list[BatchFileRecord]) -> list[list[str]]:
    """One row per uploaded delivery, audited or not.

    Beyond the two CSVs the brief names, and here for a reason the rest of this codebase argues for
    repeatedly: an export that lists only the files it managed to audit describes a cleaner batch
    than the one that was actually uploaded. The failed ones are named, with the reason, and their
    money columns are empty rather than zero — zero would read as "this invoice claimed nothing",
    which is a statement, and we have none to make.
    """
    rows: list[list[str]] = []
    for record in files:
        report = (
            PadnextAuditReport.model_validate(record.report_json)
            if record.status == str(BatchFileStatus.COMPLETED) and record.report_json
            else None
        )
        rows.append(
            [
                record.filename,
                record.status,
                str(report.claimed_total_eur) if report else "",
                str(report.confirmed_fine_eur) if report else "",
                str(report.confirmed_wrong_eur) if report else "",
                str(report.unconfirmed_eur) if report else "",
                repr(report.coverage_ratio) if report else "",
                str(len(report.positions)) if report else "",
                record.error_message or "",
            ]
        )
    return rows


def readme(job: BatchJobRecord, summary: BatchAggregateSummary | None) -> str:
    """The sentence that has to travel with the file.

    A CSV outlives the screen it was downloaded from. Somebody will open `batch_line_items.csv` in
    six months, see a `bucket` column with `unconfirmed` in most rows, and have to decide what that
    means about a practice's billing. If the answer is not in the ZIP, they will guess, and the
    likely guess — "unconfirmed means suspect" — is precisely the overclaim the three-bucket split
    was built to prevent. So the definitions ship with the data.

    German, because the reader is a German billing centre, with the English disclaimer alongside for
    the same reason the UI carries both.
    """
    claimed = summary.claimed_total_eur if summary else "0.00"
    audited = summary.completed_file_count if summary else 0
    failed = summary.failed_file_count if summary else 0
    total = summary.file_count if summary else 0

    # Read from the rule store rather than written into the prose. The sentence used to carry a
    # fixed pair of figures, which was both stale and the wrong denominator: it counted only
    # exclusions, while the buckets this paragraph explains turn on Zielleistung, specificity and
    # factor caps too. See tests/test_published_numbers.py for why no shipped text quotes a count.
    #
    # This is the shipped CSV store, not the pipeline's review-merged one, because `readme` is
    # handed a finished batch and not the engine that produced it. The two differ only by rules a
    # reviewer has promoted, so this can understate `enforced` and never overstate it — the safe
    # direction for a paragraph whose whole point is that the coverage is thinner than it looks.
    rules = load_rules()
    enforced = rules.enforced_rule_count()
    constraint = rules.constraint_rule_count()

    return f"""GOÄ-Stapelprüfung — Export
==========================

Stapel        {job.batch_id}
Erstellt      {_iso(job.created_at)}
Abgeschlossen {_iso(job.completed_at)}
Dateien       {total} hochgeladen, {audited} geprüft, {failed} nicht lesbar
Berechnet     {claimed} EUR (nur die geprüften Dateien)


Was in diesem Archiv liegt
--------------------------

{SUMMARY_CSV}      Eine Zeile: der ganze Stapel.
{LINE_ITEMS_CSV}   Eine Zeile je berechneter Position der geprüften Dateien.
{FILES_CSV}        Eine Zeile je hochgeladener Datei — auch die nicht lesbaren.
{README_TXT}            Diese Datei.


Die drei Bewertungsgruppen (Spalte "bucket")
--------------------------------------------

confirmed_wrong   Nachweislich nicht wie berechnet berechnungsfähig: eine verifizierte Regel,
                  der versionierte Katalog oder die Nachrechnung nach § 5 Abs. 1 GOÄ zeigt es.
                  Gegenüber einem Kostenträger belastbar.

confirmed_fine    Alle anwendbaren Prüfungen bestanden, und mindestens eine *verifizierte*
                  Regel war auf die Position anwendbar.

unconfirmed       Keine Aussage möglich: für diese Ziffer liegt keine von einem Menschen
                  geprüfte Regel vor, oder die vorhandenen Regeln sind nur beratend.

WICHTIG: "unconfirmed" ist KEIN Befund gegen die Praxis. Es ist die Grenze der Regelabdeckung
dieser Engine — nur {enforced} von {constraint} Regeln sind von einem Menschen verifiziert und
werden durchgesetzt; der Rest ist maschinell extrahiert und unter der Standard-Policy nicht
durchgesetzt. Über viele Rechnungen summiert ist "unconfirmed" deshalb
in der Regel der größte der drei Beträge, und er sagt nichts über die Abrechnungsqualität aus.
Die drei Beträge dürfen NICHT zu einer Summe "strittig" addiert werden.

(Unconfirmed positions require human review or rule verification. They are not findings.)


Beträge
-------

Alle Beträge sind exakte Dezimalzeichenketten, wie die Engine sie berechnet hat, mit einem
Punkt als Dezimaltrennzeichen. Sie wurden nicht gerundet und nicht umformatiert.

Es gilt je Datei und für den Stapel insgesamt:

    confirmed_fine + confirmed_wrong + unconfirmed = total_claimed

coverage_ratio = (confirmed_fine + confirmed_wrong) / total_claimed. Der Wert sagt, zu welchem
Anteil der berechneten Summe diese Prüfung überhaupt eine Aussage treffen konnte — NICHT, wie
viel davon falsch ist.


CSV-Format
----------

RFC 4180: Trennzeichen Komma, Zeilenende CRLF, UTF-8 mit BOM.

In Excel bitte über Daten → Aus Text/CSV importieren und als Trennzeichen das Komma sowie als
Gebietsschema Englisch (USA) wählen. Ein Doppelklick öffnet die Datei in einer deutschen
Excel-Version in einer einzigen Spalte — oder, schlimmer, interpretiert 24.25 als Datum.

Mehrfachwerte in den Spalten verified_rule_ids und advisory_rule_ids sind mit "{LIST_SEPARATOR}"
getrennt.


Rechtlicher Hinweis
-------------------

Dies ist ein Prüfergebnis, keine Rechnung und keine Rechtsberatung. Die Regelabdeckung ist
unvollständig. Die ärztliche bzw. abrechnungsfachliche Prüfung bleibt erforderlich.
"""


def build_batch_zip(
    job: BatchJobRecord,
    files: list[BatchFileRecord],
    summary: BatchAggregateSummary | None,
) -> bytes:
    """The whole export, as ZIP bytes.

    Deterministic: entry timestamps are fixed, so exporting the same finished batch twice produces
    identical bytes. That is worth the two extra lines — a billing centre that re-downloads a file
    and gets a different checksum has to wonder whether the data changed, and for a terminal batch
    it never can.
    """
    members = [
        (SUMMARY_CSV, _csv(summary_rows(job, summary), SUMMARY_COLUMNS)),
        (LINE_ITEMS_CSV, _csv(line_item_rows(files), LINE_ITEM_COLUMNS)),
        (FILES_CSV, _csv(file_rows(files), FILE_COLUMNS)),
        (README_TXT, readme(job, summary)),
    ]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, text in members:
            info = zipfile.ZipInfo(filename=name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, text.encode("utf-8"))
    return buffer.getvalue()


__all__ = [
    "FILES_CSV",
    "FILE_COLUMNS",
    "LINE_ITEMS_CSV",
    "LINE_ITEM_COLUMNS",
    "LIST_SEPARATOR",
    "README_TXT",
    "SUMMARY_COLUMNS",
    "SUMMARY_CSV",
    "UTF8_BOM",
    "UnsafeFilename",
    "attachment_headers",
    "batch_export_filename",
    "build_batch_zip",
    "build_proposal_export",
    "file_rows",
    "line_item_rows",
    "proposal_export_filename",
    "readme",
    "summary_rows",
]
