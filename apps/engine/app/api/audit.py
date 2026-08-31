"""The commercial API: PADnext in, JSON out, authenticated by key.

This is the surface a PVS vendor or a billing centre integrates against, and it is deliberately a
*separate* router from `/padnext/*` rather than a set of options bolted onto it. The two answer to
different callers and therefore to different rules:

                        /api/v1/padnext/*                /api/v1/audit/*
    caller              our own web tier, via a proxy    a third party, over the internet
    tenancy             X-Organization-ID, asserted      X-API-Key, verified; tenant from the row
    rate limits         none                             per key, per endpoint
    input               raw bytes / many parts           one file, or one ZIP
    frozen by           the frontend that consumes it    a contract a partner builds against

Keeping them apart is what lets each stay honest. The web tier's endpoints must not start demanding
an API key the browser has no way to hold; the partner endpoints must not start trusting a header a
caller can write. Both were tried as one endpoint with a mode flag and it is worse in the way that
matters most — the tenancy check becomes conditional, and a conditional tenancy check is one that
can be got past.

What the two share is the only thing that must never diverge: the verdict. Both call the same
`read_delivery` / `audit_delivery` through `app.services.batch_audit.audit_bytes`, against the same
catalog, rule store and policy, so a delivery audited here and the same delivery audited through the
web tier produce the same report and the same `receipt_hash`.

## The four endpoints

    POST /audit/single            one delivery, synchronously, the full report      200
    POST /audit/bulk              a ZIP of deliveries, queued                       202
    GET  /audit/bulk              this key's jobs, newest first                     200
    GET  /audit/bulk/{job_id}     progress, then the aggregated result              200
    POST /audit/{job_id}/pdf      a completed job as a Prüfbericht                  200

**`POST /audit/single` answers `200` even when the invoice is full of errors**, and that is the
contract rather than an oversight. The HTTP status describes the *API call*: a report listing nine
findings is a successful audit, and a client that treated it as a failure would retry a request
that worked. Non-2xx is reserved for "we could not produce a report at all" — a body that is not
PADnext, a delivery coded against another catalog, a rules engine that is down. `docs/errors.md`
enumerates those; everything else is in the body.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from starlette.concurrency import run_in_threadpool

# The part `request.form()` actually yields. **Not** `fastapi.UploadFile`, which subclasses this
# one: a form parsed by Starlette directly (which is what `_read_body` does, because the endpoint
# takes its body two different ways and cannot declare a parameter) contains the base class, so an
# `isinstance` against FastAPI's subclass is always False and every multipart upload looks like a
# missing file part. That is a mistake with no symptom until somebody posts a form.
from starlette.datastructures import UploadFile as FormUploadFile

from app.api.apikeys import RequestApiKey
from app.api.deps import batches, pipeline
from app.api.padnext import refuse_catalog_mismatch
from app.api.quota import SingleAuditQuota, apply as apply_quota, check_and_refuse
from app.api.ratelimit import BulkRateLimit, Decision, SingleRateLimit
from app.config import get_settings
from app.core.observability import bind, record_invoices
from app.errors import EmptyRequestBody, UnsupportedInputFormat
from app.padnext import audit_delivery, read_delivery
from app.padnext.formats import FORMAT_ADVICE, InputFormat, detect_format
from app.schemas import (
    BatchAuditAccepted,
    BatchAuditJob,
    BatchAuditJobList,
    BatchJobStatus,
    PadnextAuditReport,
)
from app.services.batch_audit import (
    DEFAULT_BATCH_LIST_LIMIT,
    MAX_BATCH_LIST_LIMIT,
    BatchNotFound,
    new_batch_id,
)
from app.services.bulk_archive import (
    ArchiveHasNoDeliveries,
    ArchiveTooLarge,
    ArchiveUnreadable,
    inspect_archive,
)
from app.services.export import attachment_headers
from app.services.pdf import render_batch_report
from app.services.uploads import discard_bulk_upload, store_bulk_upload

log = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])

#: The multipart field the two upload endpoints read. Named in the OpenAPI document and in
#: `docs/api/PARTNER_API.md`, because a partner's first integration attempt posts `upload` or
#: `data` and gets a 422 that has to say what the field is called.
UPLOAD_FIELD = "file"


# ------------------------------------------------------------------------------------------
# reading the body
# ------------------------------------------------------------------------------------------


async def _read_body(request: Request) -> tuple[bytes, str]:
    """The uploaded file's bytes and its declared name, from multipart or from a raw body.

    Both, because the two kinds of caller both exist and neither is wrong. A `curl -T` or a PVS
    that POSTs the export straight out of its writer sends a raw body; anything driving the API
    from a form, a Postman collection or an HTTP client library sends multipart. Refusing one of
    them would be an arbitrary tax on whichever half of integrators guessed differently.

    The filename is taken only as *metadata* — it is echoed into the report's `source_name` and
    used in log lines. Nothing branches on it: the format is decided by
    `app.padnext.formats.detect_format` from the bytes themselves, precisely so that a `.xml`
    holding a PDF is caught and a correct file with an odd name is not.
    """
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get(UPLOAD_FIELD)
        if upload is None:
            # Take whatever single file part there is, rather than insisting on the name. A caller
            # who sent exactly one file and called it something else has made a documentation
            # mistake, not a semantic one, and answering their request is better than correcting
            # their vocabulary.
            uploads = [value for value in form.values() if isinstance(value, FormUploadFile)]
            upload = uploads[0] if len(uploads) == 1 else None
        if not isinstance(upload, FormUploadFile):
            raise UnsupportedInputFormat(
                f"Die multipart-Anfrage enthält kein Dateifeld '{UPLOAD_FIELD}'. — The multipart "
                f"request carries no '{UPLOAD_FIELD}' file part.",
                details={"expected_field": UPLOAD_FIELD},
            )
        content = await upload.read()
        await upload.close()
        return content, upload.filename or ""

    return await request.body(), request.headers.get("x-padnext-filename", "")


def _refuse_wrong_format(content: bytes, *, allowed: set[InputFormat]) -> InputFormat:
    """Sniff the body and refuse anything outside `allowed`. Returns what it found.

    The refusal is the constraint the brief states plainly — a PDF or a JSON body is a `400` before
    anything else happens — and it is worth doing at this layer rather than letting the reader
    produce a schema violation. The two failures read completely differently to whoever has to fix
    them: "line 1, column 1: not well-formed" sends an integrator looking at our parser, and "you
    sent a PDF" sends them looking at their export step, which is where the problem is.
    """
    detected = detect_format(content)
    if detected in allowed:
        return detected
    if detected is InputFormat.EMPTY:
        raise EmptyRequestBody(
            "Der Request-Body ist leer. Senden Sie die PADnext-Datei selbst — als "
            f"multipart/form-data im Feld '{UPLOAD_FIELD}' oder als roher Body. — The request "
            "body is empty."
        )
    raise UnsupportedInputFormat(
        FORMAT_ADVICE[detected],
        details={
            "detected": str(detected),
            "accepted": sorted(str(value) for value in allowed),
        },
    )


def _apply(response: Response, limit: Decision) -> None:
    """Publish the caller's remaining budget on a successful response.

    On the success path specifically. A client that can see it has 4 of 100 requests left this
    minute can slow down before it is refused, which is the entire reason the headers exist —
    putting them only on the `429` would tell it after the fact. They are omitted when the limiter
    is disabled, because headers describing a budget nothing is counting are worse than none.
    """
    if get_settings().rate_limit_enabled:
        for name, value in limit.headers().items():
            response.headers[name] = value


def _job_not_found(job_id: str) -> HTTPException:
    """`404`, and the same refusal for "no such job" and "not yours".

    A `403` for another practice's job would confirm that the id exists, which is enough to
    enumerate uploads across tenants one guess at a time. The same reasoning as
    `ProposalStore.get_proposal` and `BatchAuditService.load_batch`, which is where the filter that
    produces this actually lives.
    """
    return HTTPException(
        status_code=404,
        detail={
            "error": "audit_job_not_found",
            "message": (
                f"Kein Auftrag {job_id} für diesen API-Schlüssel. — No job {job_id} belongs to "
                "this API key. Check the id, or start a new one with POST /api/v1/audit/bulk."
            ),
            "job_id": job_id,
        },
    )


# ------------------------------------------------------------------------------------------
# 1. the synchronous single audit
# ------------------------------------------------------------------------------------------


def _read_refuse_and_audit(content: bytes, *, source_name: str, pipe) -> PadnextAuditReport:
    """Read one delivery, refuse a catalog mismatch, audit it. Blocking — for the threadpool.

    The same three steps `POST /api/v1/padnext/audit` performs, in the same order, calling the same
    `read_delivery`, `refuse_catalog_mismatch` and `audit_delivery`. Spelled out here rather than
    routed through `app.services.batch_audit.audit_bytes` for one reason: the catalog-mismatch
    refusal needs the parsed `PadnextDelivery`, and `audit_bytes` does not hand one back — so
    reusing it would mean parsing every upload twice to ask a question the first parse already
    answered.

    What must not diverge between the two endpoints is the verdict, and that lives entirely in
    `read_delivery` and `audit_delivery`. This function contains no judgement of its own.
    """
    delivery, read_findings = read_delivery(content, source_name=source_name)
    refuse_catalog_mismatch(delivery, pipe.catalog)
    return audit_delivery(
        delivery,
        catalog=pipe.catalog,
        rules=pipe.rules,
        souffle_run=pipe.souffle.run,
        read_findings=read_findings,
        settings=pipe.settings,
    )



@router.post(
    "/single",
    response_model=PadnextAuditReport,
    summary="Eine PADnext-Lieferung prüfen (synchron)",
    openapi_extra={
        "requestBody": {
            "required": True,
            "description": (
                "Die PADnext-Lieferung selbst: eine `*_padx.xml` oder ein `.padx`-Container. "
                "Entweder als `multipart/form-data` im Feld `file`, oder als roher Request-Body "
                "mit `Content-Type: application/xml`. — The PADnext delivery itself, as multipart "
                "or as a raw body."
            ),
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "file": {
                                "type": "string",
                                "format": "binary",
                                "description": "*_padx.xml oder .padx",
                            }
                        },
                        "required": ["file"],
                    }
                },
                "application/xml": {"schema": {"type": "string", "format": "binary"}},
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
            },
        }
    },
)
async def audit_single(
    request: Request,
    response: Response,
    key: RequestApiKey,
    limit: SingleRateLimit,
    quota: SingleAuditQuota,
) -> PadnextAuditReport:
    """Prüft eine einzelne PADnext-Lieferung gegen die GOÄ und liefert den vollständigen Bericht.

    **Antwort.** `200` mit dem kompletten `PadnextAuditReport`: jede Position mit Verdikt und
    Begründung, alle Befunde (`findings`), die drei Beträge nach Belegbarkeit
    (`confirmed_fine_eur`, `confirmed_wrong_eur`, `unconfirmed_eur`), die Prüfabdeckung und der
    `receipt_hash` über Katalog, Regelstand, Logikprogramme, Solver-Versionen und Eingabe.

    **`200` gilt auch für eine fehlerhafte Rechnung.** Der HTTP-Status beschreibt den API-Aufruf,
    nicht die Rechnung: neun gefundene Fehler sind eine erfolgreiche Prüfung. Nicht-2xx bedeutet
    ausschliesslich, dass gar kein Bericht erstellt werden konnte.

    **Nicht beurteilbar ist kein Befund.** `unconfirmed_eur` ist die Grenze der Regelabdeckung
    dieser Engine, nicht ein Vorwurf gegen die Praxis. Die drei Beträge dürfen nie zu einer Summe
    zusammengefasst werden — siehe `docs/api/PARTNER_API.md`.

    ---

    Audits one PADnext delivery against the GOÄ and returns the complete report, synchronously.

    The response is the same `PadnextAuditReport` the web tier's `/padnext/audit` returns, produced
    by the same code against the same catalog — a delivery audited through either path gets the
    same verdicts and the same `receipt_hash`.

    Findings in the invoice are **not** an HTTP error: `200` means the audit ran. Errors carry
    `error_code` — `UNSUPPORTED_INPUT_FORMAT` (400, a PDF or JSON body), `EMPTY_REQUEST_BODY`
    (400), `INVALID_XML` (400), `REQUEST_TOO_LARGE` (413, above 5 MiB),
    `PADNEXT_SCHEMA_VIOLATION` (422), `UNKNOWN_ZIFFER` (422, when no position is in this catalog),
    `REAL_DATA_REFUSED` (422), `RATE_LIMIT_EXCEEDED` (429) and `RULES_ENGINE_UNAVAILABLE` (503).
    See `docs/errors.md`.

    Synchronous because one delivery is one Soufflé run of a few hundred milliseconds. The audit is
    handed to the threadpool rather than run here: this is an `async def` (it has to read the body)
    and a blocking solve on the event loop would serialise the whole service behind it.
    """
    settings = get_settings()
    content, source_name = await _read_body(request)

    # A `.padx` container is a ZIP and is legitimate input here — the reader unpacks it. What is
    # refused is a PDF, a JSON body, or bytes that are neither XML nor an archive.
    _refuse_wrong_format(content, allowed={InputFormat.XML, InputFormat.ZIP})

    if len(content) > settings.max_single_xml_bytes:
        # The perimeter middleware screens on Content-Length and this catches a chunked upload that
        # carried none. `413` with the endpoint's own limit rather than the global one, so the
        # number in the message is the number the caller has to get under.
        raise HTTPException(
            status_code=413,
            detail={
                "error": "request_too_large",
                "message": (
                    f"Die Lieferung ist {len(content)} Bytes gross; erlaubt sind höchstens "
                    f"{settings.max_single_xml_bytes}. Für viele Rechnungen nutzen Sie "
                    "POST /api/v1/audit/bulk. — The delivery exceeds the single-file limit; use "
                    "the bulk endpoint for an archive."
                ),
                "max_bytes": settings.max_single_xml_bytes,
                "declared_bytes": len(content),
            },
        )

    pipe = pipeline()
    # Raises the reader's own catalogued failures — `InvalidXmlError` (400), `PadnextSchemaError`
    # (422), `UnknownZifferError` (422), `RealDataRefused` (422), `SouffleError` (503) — each
    # carrying its own status. There is nothing to translate: the handlers in `app.api.errors`
    # render them.
    # `source_name` is passed through even when it is empty. Empty is what `POST /padnext/audit`
    # produces for a raw body with no filename header, and the two endpoints must return the same
    # document for the same bytes — substituting a placeholder here would make `source_name` the
    # one field on which they disagree.
    report = await run_in_threadpool(
        _read_refuse_and_audit, content, source_name=source_name, pipe=pipe
    )

    log.info(
        "audit/single by key %s: %d positions, coverage %.1f%%",
        key.key_id,
        len(report.positions),
        report.coverage_ratio * 100,
    )
    # One delivery audited, and only now that it demonstrably was. Declared *after* the audit
    # rather than beside the quota check above, because the quota check is a question ("may I") and
    # this is a fact ("I did") — a delivery that turned out to be unreadable is a `422` the practice
    # is not charged for, and putting the count before the audit would bill it.
    record_invoices(1)
    _apply(response, limit)
    apply_quota(response, quota)
    return report




# ------------------------------------------------------------------------------------------
# 2. the asynchronous bulk audit
# ------------------------------------------------------------------------------------------


@router.post(
    "/bulk",
    response_model=BatchAuditAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Viele PADnext-Lieferungen als ZIP prüfen (asynchron)",
)
async def audit_bulk(
    background_tasks: BackgroundTasks,
    key: RequestApiKey,
    limit: BulkRateLimit,
    response: Response,
    file: UploadFile = File(
        ...,
        description=(
            "Ein ZIP-Archiv mit den zu prüfenden PADnext-Lieferungen (`*.xml` / `*.padx`, auch in "
            "Unterordnern). Andere Dateien im Archiv werden übersprungen. — A ZIP holding the "
            "PADnext deliveries to audit; anything else in it is skipped."
        ),
    ),
) -> BatchAuditAccepted:
    """Nimmt ein ZIP mit vielen Lieferungen an und prüft sie im Hintergrund.

    **Antwort.** Sofort `202` mit `job_id` (Feld `batch_id`) und `status: "PENDING"`. Die Prüfung
    hat zu diesem Zeitpunkt noch nicht begonnen. `file_count` sagt bereits, wie viele Lieferungen
    im Archiv gefunden wurden — das Archiv wird vor der Antwort geöffnet und geprüft, damit ein
    unbrauchbares Archiv ein `400` ist und kein Auftrag, der nach 30 Sekunden fehlschlägt.

    Den Fortschritt liefert `GET /api/v1/audit/bulk/{job_id}`; das Gesamtergebnis steht dort,
    sobald `status` auf `COMPLETED` steht.

    **Grenzen.** Archiv höchstens 50 MB, entpackt höchstens 256 MiB, höchstens 500 Lieferungen,
    höchstens 10 Uploads pro Stunde und Schlüssel.

    ---

    Accepts a ZIP of PADnext deliveries and audits them in the background.

    The archive is written to disk **before** the response is sent, and that is what distinguishes
    this from the web tier's in-memory batch upload: the job survives a restart. A `202` here is a
    promise that the work will happen, not that a process currently holding the bytes will manage
    to finish.

    Returns `202` immediately with the handle to poll. Errors carry `error_code`:
    `UNSUPPORTED_INPUT_FORMAT` (400, not a ZIP), `ARCHIVE_UNREADABLE` (400, a corrupt ZIP),
    `ARCHIVE_HAS_NO_DELIVERIES` (400, a valid ZIP holding no `.xml`/`.padx`), `ARCHIVE_TOO_LARGE`
    (413), `REQUEST_TOO_LARGE` (413), `RATE_LIMIT_EXCEEDED` (429) and `UPLOAD_STORAGE_UNAVAILABLE`
    (503, retryable — the deployment's upload volume is not writable).
    """
    settings = get_settings()
    content = await file.read()
    await file.close()

    _refuse_wrong_format(content, allowed={InputFormat.ZIP})

    if len(content) > settings.max_bulk_zip_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "request_too_large",
                "message": (
                    f"Das Archiv ist {len(content)} Bytes gross; erlaubt sind höchstens "
                    f"{settings.max_bulk_zip_bytes}. Teilen Sie den Upload auf. — The archive "
                    "exceeds the bulk upload limit; split it."
                ),
                "max_bytes": settings.max_bulk_zip_bytes,
                "declared_bytes": len(content),
            },
        )

    # Opened here, in the request, so an unusable archive is a `400` on the upload rather than a
    # job the caller polls for half a minute before being told it failed. It also means the `202`
    # can state how many deliveries were accepted.
    try:
        members = await run_in_threadpool(
            inspect_archive,
            content,
            max_members=settings.max_bulk_archive_members,
            max_uncompressed_bytes=settings.max_bulk_uncompressed_bytes,
        )
    except ArchiveTooLarge as exc:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "archive_too_large",
                "message": str(exc),
                "limit": exc.limit,
                "observed": exc.observed,
            },
        ) from exc
    except ArchiveHasNoDeliveries as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "archive_has_no_deliveries", "message": str(exc)},
        ) from exc
    except ArchiveUnreadable as exc:
        raise HTTPException(
            status_code=400, detail={"error": "archive_unreadable", "message": str(exc)}
        ) from exc

    # The quota, now that the archive has said how many deliveries are in it — and before a single
    # one is queued. Refused as a unit: a job that audited 180 of 300 files and stopped because a
    # ceiling was reached mid-run is a job somebody has to reconcile by hand, which is a worse
    # outcome for the practice than being told up front that the archive is too big for what is
    # left of their period.
    #
    # After the archive is opened and before it is written to disk, so a refusal costs no storage.
    quota = await check_and_refuse(key.organization_id, requested=len(members))

    service = batches()
    # A batch id is minted before the row so the archive can be written under it. Both fail
    # together or neither happens: if the write throws, no job row exists to point at a file that
    # is not there.
    batch_id = new_batch_id()
    # Bound before the archive is written, so the two failures that can follow — a storage error
    # and a database error — both name the job they were for. A `503` whose log line does not say
    # which upload it was is a `503` nobody can follow up on.
    bind(job_id=batch_id)
    try:
        upload_path = await run_in_threadpool(
            store_bulk_upload,
            content,
            batch_id=batch_id,
            organization_id=key.organization_id,
            settings=settings,
        )
    except OSError as exc:
        log.error("could not store bulk upload for %s: %s", key.organization_id, exc)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "upload_storage_unavailable",
                "message": (
                    "Der Upload konnte nicht gespeichert werden; der Auftrag wurde nicht "
                    "angenommen. Versuchen Sie es erneut. — The upload could not be stored and "
                    "the job was not accepted; retry."
                ),
                "retry_after": 30,
            },
            headers={"Retry-After": "30"},
        ) from exc

    try:
        accepted = await service.create_bulk_job(
            members,
            upload_path=upload_path,
            organization_id=key.organization_id,
            actor=f"apikey:{key.key_id}",
            batch_id=batch_id,
        )
    except Exception:
        # The archive landed and the row did not, so nothing will ever name that file again — and
        # `app.services.uploads` deliberately has no sweeper for orphans, because deleting files
        # from a path no row points at is an operator's judgement rather than a service's. The one
        # moment it *is* safe to delete is here, where we know the path we just wrote and know that
        # nothing else has seen it. The original failure is re-raised: a `503` the caller can act
        # on is the answer, not a cleanup message.
        await run_in_threadpool(
            discard_bulk_upload,
            upload_path,
            settings=settings.model_copy(update={"retain_bulk_uploads": False}),
        )
        raise

    # The task carries nothing — it only says "there may be work". Losing it (a crash between the
    # response and the task) loses no work: the row is `PENDING` and the next upload's drain, or
    # the one the lifespan runs at startup, picks it up. That is the property the on-disk archive
    # buys, and it is why this is a drain rather than `process_batch(batch_id, payloads)`.
    background_tasks.add_task(service.drain_pending_jobs)

    log.info(
        "audit/bulk accepted %s with %d deliveries for key %s",
        accepted.batch_id,
        accepted.file_count,
        key.key_id,
    )
    # Counted on **acceptance**, not on completion, and that is a decision worth being explicit
    # about. The audit itself happens in a background task, long after this response and its usage
    # row; attributing the count there would mean the number depended on a `BackgroundTask` running,
    # and a process restart between the two would lose billable work that the practice was told had
    # been accepted. `file_count` is what the `202` promised, so it is what is counted.
    #
    # The consequence, stated: a delivery inside the archive that turns out to be unreadable is
    # still counted, where `/audit/single` would not count it. The archive was opened and validated
    # before this point, so the case is a malformed member rather than a malformed upload — and the
    # engine did the work of trying either way.
    record_invoices(accepted.file_count)
    _apply(response, limit)
    apply_quota(response, quota)
    return accepted


@router.get("/bulk", response_model=BatchAuditJobList, summary="Aufträge dieses Schlüssels")
async def audit_bulk_list(
    key: RequestApiKey,
    status_filter: BatchJobStatus | None = Query(
        default=None,
        alias="status",
        description=(
            "Nur Aufträge in diesem Zustand. — Only jobs in this state; omit for every state."
        ),
    ),
    created_after: datetime | None = Query(
        default=None,
        description=(
            "Nur Aufträge ab diesem Zeitpunkt, **einschliesslich**. ISO-8601; ein Wert ohne "
            "Zeitzone wird als UTC gelesen. — Inclusive lower bound on creation time."
        ),
    ),
    limit: int = Query(default=DEFAULT_BATCH_LIST_LIMIT, ge=1, le=MAX_BATCH_LIST_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> BatchAuditJobList:
    """Die Aufträge dieser Organisation, neueste zuerst, ohne die einzelnen Berichte.

    Ohne diese Liste wäre ein Auftrag verloren, sobald der Aufrufer seine `job_id` verliert — das
    Ergebnis läge in der Datenbank und nichts könnte danach fragen. Die Zeilen tragen die
    Gesamtauswertung, aber **nicht** `files`: eine Liste mit allen Einzelberichten wäre megabyteweise
    JSON für eine Tabelle.

    ---

    This key's organisation's jobs, newest first, as headers without their per-delivery reports.

    It exists for the same reason the web tier's batch listing does: a `job_id` is issued once, and
    an integration that loses it — a restarted worker, a lost log line — would otherwise have a
    finished job in the database that nothing can ask for. `total` is recounted under the filters,
    so it says how many jobs match rather than how many rows exist.
    """
    return await batches().list_batches(
        status=status_filter,
        created_after=created_after,
        limit=limit,
        offset=offset,
        organization_id=key.organization_id,
    )


@router.get(
    "/bulk/{job_id}",
    response_model=BatchAuditJob,
    summary="Fortschritt und Ergebnis eines Auftrags",
)
async def audit_bulk_status(job_id: str, key: RequestApiKey) -> BatchAuditJob:
    """Fortschritt des Auftrags — und, sobald er fertig ist, das vollständige Ergebnis.

    **Während der Auftrag läuft** trägt `files` je Lieferung nur den Status und keinen Bericht: ein
    Poll im Zwei-Sekunden-Takt über hundert Dateien darf nicht hundert vollständige Berichte pro
    Abruf übertragen. `processed_file_count` / `file_count` ist der Fortschritt.

    **Sobald `status` `COMPLETED` ist**, trägt jede geprüfte Lieferung ihren vollständigen
    `PadnextAuditReport` — identisch zu dem, was `POST /api/v1/audit/single` für dieselbe Datei
    geliefert hätte — und `aggregate_summary` die Gesamtauswertung.

    `files` ist nach `confirmed_wrong_eur` absteigend sortiert: das Riskanteste zuerst. Die
    Sortierung passiert hier, weil die Beträge exakte Dezimalzeichenketten sind, die ein
    JavaScript-Client nicht in Zahlen zurückparsen darf.

    ---

    Progress while it runs, the aggregated result once it is done. Poll this; there is no webhook.

    `PENDING` means queued and not yet started, `PROCESSING` means a worker has it, `COMPLETED`
    means every delivery reached a verdict, and `FAILED` means the job itself broke — a delivery
    that could not be read is **not** a failed job, it is a `FAILED` entry in `files` with a reason,
    and the rest of the archive is still audited.
    """
    bind(job_id=job_id)
    try:
        return await batches().load_batch(job_id, organization_id=key.organization_id)
    except BatchNotFound as exc:
        raise _job_not_found(job_id) from exc


# ------------------------------------------------------------------------------------------
# 3. the PDF
# ------------------------------------------------------------------------------------------


@router.post(
    "/{job_id}/pdf",
    response_class=Response,
    summary="Prüfbericht als PDF",
    responses={
        200: {
            "description": "Der Prüfbericht als PDF, `{job_id}_pruefbericht.pdf`.",
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        },
        409: {"description": "Der Auftrag ist noch nicht abgeschlossen."},
    },
)
async def audit_pdf(job_id: str, key: RequestApiKey) -> Response:
    """Den abgeschlossenen Auftrag als druckbaren Prüfbericht.

    Enthält die drei Beträge nach Belegbarkeit, die Prüfabdeckung, jede Lieferung einzeln (nach
    Risiko sortiert) und die Prüfgrundlage: Katalogfassung, Katalog-Hash, Regel- und Logikstand.
    Der Hinweis, dass »nicht beurteilbar« kein Befund gegen die Praxis ist, steht als Absatz neben
    der Zahl — ein PDF überlebt den Bildschirm, von dem es kam, und wird von Menschen gelesen,
    denen niemand die Lesart erklärt hat.

    Nur ein `COMPLETED`-Auftrag kann gedruckt werden. Ein laufender ergäbe Zahlen aus einem nicht
    identifizierbaren Moment, ein fehlgeschlagener hat gar keine Auswertung — beides ist `409`
    statt einer Datei mit einem Vorbehalt, denn ein Vorbehalt überlebt es nicht, drei Wochen später
    aus einem Ordner gezogen zu werden.

    ---

    A completed job as a printable Prüfbericht. `POST` rather than `GET` because it renders a
    document rather than reading a stored one, and because that is the shape the brief specifies;
    it is nonetheless read-only and idempotent — the same job produces byte-identical output every
    time, exactly as the CSV export does.

    Only `COMPLETED`. See `app.services.pdf` for why there is no PDF library behind this.
    """
    bind(job_id=job_id)
    try:
        job = await batches().load_batch(job_id, organization_id=key.organization_id)
    except BatchNotFound as exc:
        raise _job_not_found(job_id) from exc

    if job.status != BatchJobStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "audit_job_not_completed",
                "message": (
                    f"Auftrag {job_id} ist {job.status}, nicht COMPLETED. Ein Bericht wird erst "
                    "erstellt, wenn jede Lieferung ein Verdikt hat. — The job has not completed, "
                    "so there is no report to render."
                ),
                "current_status": str(job.status),
            },
        ) from None

    document = await run_in_threadpool(
        render_batch_report, job, organization_id=key.organization_id
    )
    return Response(
        content=document,
        media_type="application/pdf",
        headers=attachment_headers(f"{job_id}_pruefbericht.pdf"),
    )
