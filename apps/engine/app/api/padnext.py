"""Check already-coded PADnext deliveries against the GOÄ rules — one file, or many.

`POST /padnext/audit` is the single-file path and it is unchanged: raw bytes in, a
`PadnextAuditReport` out, synchronously. Sync (`def`) for the same reason as `solve` — the audit
runs Soufflé.

`POST /padnext/batch`, `GET /padnext/batch` and `GET /padnext/batch/{batch_id}` are the batch path.
They exist because a practice's real question is not "is this invoice defensible" but "is our
billing systematically wrong, and where" — and that question needs a hundred files, which is far too
long for one request to hold open. So the batch path is asynchronous by necessity rather than by
taste: the upload is accepted with a `202` and a handle, a `BackgroundTask` audits the files, and the
caller polls.

`GET /padnext/batch` (no id) is the listing, and it is what makes the durability real. The handle
from the `202` lives in the caller's memory, so without a listing a finished batch became
unreachable the moment a browser reloaded — its roll-up still in Postgres with nothing able to ask
for it. It is also where a batch closed by the startup recovery becomes visible.

**The batch path is organisation-scoped; `POST /padnext/audit` deliberately is not.** A batch is a
stored record — it has rows, a listing, a roll-up and an export — so it has an owner, and every one
of the four batch endpoints requires `X-Organization-ID` and filters on it (`app.api.tenancy`). The
single-file audit stores nothing: bytes in, a report out, no row written and nothing to read back.
There is no record for a tenant to own, so requiring a tenant would be a gate in front of an empty
room. A batch belonging to another practice answers `404` rather than `403`, for the same reason
`/proposals/{id}` does — see that module.

The two paths share `read_delivery` and `audit_delivery` and nothing else. That is deliberate: the
single-file endpoint is a shipped contract, so the batch path was built alongside it rather than by
reshaping it around a second caller. What must not diverge is the verdict on a given file, and that
lives in the shared functions.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)

from starlette.concurrency import run_in_threadpool

from app.api.deps import batches, pipeline
from app.api.identity import RequestActor
from app.api.quota import apply as apply_quota, check_and_refuse, optional_quota
from app.api.tenancy import RequestOrganization
from app.core.observability import record_invoices
from app.errors import EmptyRequestBody, UnknownZifferError
from app.padnext import audit_delivery, read_delivery
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
    BatchNotExportable,
    BatchNotFound,
    EmptyBatch,
)
from app.services.export import attachment_headers, batch_export_filename
from app.services.pdf import render_batch_report, render_single_report

log = logging.getLogger(__name__)

router = APIRouter(prefix="/padnext", tags=["padnext"])

#: How many deliveries one batch may carry.
#:
#: A ceiling rather than no ceiling, because `BackgroundTasks` holds every uploaded file in this
#: process's memory for the length of the job (see `app.services.batch_audit`) and processes them
#: on one worker. 500 files at the per-file cap is well inside what the container is given, and a
#: practice with more than that has a job for a durable queue, not for this MVP.
MAX_BATCH_FILES = 500

#: The largest single delivery a batch will accept, and the largest total across the batch.
#:
#: The per-file figure matches what the reader already enforces (`app.padnext.reader`). The total
#: is the one that actually protects the process: 500 files could each be under the per-file limit
#: and still be far more than the memory available, so both are checked.
MAX_BATCH_FILE_BYTES = 8 * 1024 * 1024
MAX_BATCH_TOTAL_BYTES = 64 * 1024 * 1024


def _audit_bytes(body: bytes, *, source_name: str) -> PadnextAuditReport:
    """Read one delivery and audit it. Synchronous, and the only place that work happens.

    Extracted so the JSON endpoint and the PDF endpoint cannot drift: the two must return the same
    verdicts and the same `receipt_hash` for the same bytes, and the way to guarantee that is for
    there to be one function rather than two that look alike.

    **Deliberately not `async`.** The solve is a blocking subprocess. `POST /padnext/audit` is an
    `async def` (it awaits a quota read) and hands this to the threadpool; `POST /padnext/audit.pdf`
    is a plain `def`, which FastAPI dispatches to the threadpool itself. Either way the event loop
    is never blocked — `tests/test_production_fixes.py::test_no_solve_ever_runs_on_the_event_loop`
    is the guard rail that says so, and it is the reason this split exists at all.
    """
    if not body:
        raise EmptyRequestBody(
            "Empty body. POST the PADnext file itself — a .padx container or a *_padx.xml "
            "payload — with Content-Type application/xml or application/octet-stream."
        )

    # `read_delivery` raises `InvalidXmlError` (400, with the line and column), `PadnextSchemaError`
    # (422, with every violation) or a bare `PadnextError` (422). All three are in the catalog and
    # all three are rendered by the handler, so there is nothing to translate here.
    delivery, read_findings = read_delivery(body, source_name=source_name)

    pipe = pipeline()
    refuse_catalog_mismatch(delivery, pipe.catalog)

    # `RealDataRefused` (422) and `SouffleError` (503, retryable) likewise carry their own status.
    return audit_delivery(
        delivery,
        catalog=pipe.catalog,
        rules=pipe.rules,
        souffle_run=pipe.souffle.run,
        read_findings=read_findings,
        settings=pipe.settings,
    )


@router.post("/audit", response_model=PadnextAuditReport)
async def padnext_audit(
    request: Request, response: Response, body: bytes = Body(default=b"")
) -> PadnextAuditReport:
    """Audit a PADnext delivery against the GOÄ rules.

    The body is the file itself, not a JSON wrapper or a multipart upload: either a `.padx`
    container (a ZIP, sniffed by magic bytes) or a bare `*_padx.xml` payload. Taking raw bytes
    avoids a `python-multipart` dependency for what is one file per request.

    A delivery flagged as production data is refused with 422 — see `app.padnext.audit` and
    `docs/compliance/PRIVATE_DATA_WARNING.md`.

    Failures carry `error_code`: `EMPTY_REQUEST_BODY` (400), `INVALID_XML` (400, with the line and
    column in `details`), `PADNEXT_SCHEMA_VIOLATION` (422, every violation in `details`),
    `PADNEXT_UNREADABLE` (422), `UNKNOWN_ZIFFER` (422, when no position is in this catalog at
    all), `REAL_DATA_REFUSED` (422), `QUOTA_EXCEEDED` (429, only for a caller that named a practice)
    and `RULES_ENGINE_UNAVAILABLE` (503, retryable). See `docs/errors.md`.

    **The billing quota applies here only when the caller names a practice.** This endpoint stores
    nothing and is unscoped by design, so the tenant is read optionally rather than required — the
    contract, including the case of a call that names no practice at all, is unchanged. Every call
    the web tier proxies does name one (it comes from the session, see `apps/web/lib/engine.ts`), so
    in practice a signed-in reader's audit is counted and checked, and `/demo`'s visitor is not.
    `app.api.quota` states the consequence of that in full.

    `async def` for one reason: the quota check is a database read. The audit itself is handed to the
    threadpool, because a blocking solve on the event loop would serialise the whole service — see
    `_audit_bytes`.
    """
    # Before the body is parsed, so a practice over its quota is refused without the engine doing
    # the work — and before the empty-body check, because "you have no quota left" is the more
    # actionable of the two answers for a caller who managed to send both problems at once.
    quota = await optional_quota(request, requested=1)

    report = await run_in_threadpool(
        _audit_bytes, body, source_name=request.headers.get("x-padnext-filename", "")
    )

    # One delivery, counted only once it demonstrably was audited — the same rule `/audit/single`
    # follows. A request that named no practice writes no usage row at all (there is nobody to
    # attribute it to), so this is a no-op for `/demo`.
    if quota is not None:
        record_invoices(1)
    apply_quota(response, quota)
    return report


@router.post(
    "/audit.pdf",
    response_class=Response,
    responses={
        200: {
            "description": "Der Prüfbericht als PDF, `pruefbericht_<Datei>.pdf`.",
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        },
    },
)
def padnext_audit_pdf(
    request: Request,
    actor: RequestActor,
    body: bytes = Body(default=b""),
) -> Response:
    """Dieselbe Prüfung wie `POST /padnext/audit`, als druckbarer Prüfbericht.

    Der Bericht trägt den Erstellungszeitpunkt, die Rechnungsnummer aus der Lieferung, die
    Rechtsgrundlage und die Regel-ID zu jeder Beanstandung sowie die Freigabezeile, auf der die
    ärztliche Prüfung dokumentiert wird.

    ---

    The printable twin of `POST /padnext/audit`, and deliberately the same request: the file
    itself as the body, the same headers, the same refusals with the same `error_code`s.

    **It audits rather than looking a report up, and that is the honest shape here.** A single
    audit stores nothing — that is stated at the top of this module and is what keeps this endpoint
    outside tenancy — so there is no stored report to render and the only way to produce one is to
    run the audit. The audit is deterministic and takes a few hundred milliseconds, so the PDF this
    returns carries the *same* verdicts and the same `receipt_hash` as the JSON the caller already
    has. The receipt hash printed on the document is what lets them confirm that.

    Unlike the JSON, this response carries a wall clock: `Erstellt am`, and `/CreationDate` in the
    document metadata. A report that goes into a client file has to say when it was drawn, so two
    downloads of one delivery differ in exactly that stamp and in nothing else.

    **This endpoint is deliberately not counted against the billing quota**, even though it runs a
    real audit. It renders a report for a delivery the practice has already been charged for once,
    and charging again for the printable copy — or refusing the download because the quota ran out
    between reading the verdicts and printing them — would be indefensible. The consequence is that
    a caller who only ever used this endpoint would audit for free; it is reachable from the web
    tier, behind a session, by the same reader who just paid for the JSON, and closing that would
    mean either double-billing or storing reports, which is what the module docstring rules out.
    """
    # The shared audit, not the JSON endpoint: that one is a coroutine now (it awaits a quota
    # read), and this handler is a plain `def` so FastAPI keeps dispatching it to the threadpool.
    report = _audit_bytes(body, source_name=request.headers.get("x-padnext-filename", ""))
    document = render_single_report(
        report,
        organization=request.headers.get("x-organization-id") or None,
        generated_at=datetime.now(timezone.utc),
    )
    log.info(
        "padnext/audit.pdf by %s: %d positions, %d pages",
        actor,
        len(report.positions),
        document.count(b"/Type /Page /Parent"),
    )
    return Response(
        content=document,
        media_type="application/pdf",
        headers={
            **attachment_headers(pruefbericht_filename(report.source_name)),
            # A Prüfbericht carries a timestamp and a practice's billing detail; it must not sit in
            # a shared cache on the way back to the browser.
            "Cache-Control": "no-store",
        },
    )


#: `[A-Za-z0-9._-]` is all `attachment_headers` will pass, because the value reaches a response
#: header. A PADnext filename is client-supplied, so it is reduced to that set here rather than
#: being trusted and rejected at the header.
_UNSAFE_IN_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def pruefbericht_filename(source_name: str) -> str:
    """`pruefbericht_00004711_20260726_ADL_000001_padx.pdf`, or a safe fallback.

    The delivery's own name is carried into the download because a billing centre auditing forty
    files needs the forty PDFs to sort beside the forty XMLs. It is sanitised rather than trusted:
    the name arrives in a request header, and `attachment_headers` would otherwise refuse the whole
    response over a space in it.
    """
    stem = _UNSAFE_IN_FILENAME.sub("_", source_name.rsplit("/", 1)[-1]).strip("._-")
    for suffix in (".xml", ".padx", ".XML", ".PADX"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    return f"pruefbericht_{stem}.pdf" if stem else "pruefbericht.pdf"


def refuse_catalog_mismatch(delivery, catalog) -> None:
    """Refuse a delivery whose GOÄ positions are, without exception, unknown to this catalog.

    **This is narrow on purpose, and the narrowness is the whole design.** A delivery with *some*
    unknown Ziffern is audited exactly as before: each unknown position gets the `unknown_ziffer`
    verdict, lands in the `unconfirmed` bucket and lowers `coverage_ratio`. That is a deliberate
    product decision — rule coverage here is partial, and telling a practice its position is wrong
    when the truth is that our catalog does not contain it would be a false statement about their
    invoice.

    What that reasoning does not cover is the case where *every* GOÄ position is unknown. Then it
    is not a gap in coverage, it is a mismatch: the delivery was coded against a different edition
    of the fee schedule (or is not GOÄ at all), and the report we would return says nothing about
    anything — 0 % coverage, every position unconfirmed, a receipt hash over a verdict-free
    document. A caller is much better served by `422 UNKNOWN_ZIFFER` listing the codes and naming
    the catalog they were checked against, which is enough to work out which edition they meant.

    Checked here in the route rather than inside `audit_delivery`, so the library keeps producing a
    report for any input and only the HTTP contract takes a position on it.

    Public (it lost its leading underscore) because the commercial `POST /api/v1/audit/single`
    makes the identical refusal and must keep making the identical one. Two endpoints that disagree
    about whether a delivery is auditable would be a difference a partner discovers by getting two
    different answers to the same file.
    """
    goae = [p for p in delivery.positions() if p.is_goae]
    if not goae:
        # Nothing to say: a delivery that charges only other fee schedules is out of scope, and
        # `audit_delivery` already reports that per position.
        return
    unknown = [p.ziffer for p in goae if catalog.get(p.ziffer) is None]
    if len(unknown) < len(goae):
        return

    raise UnknownZifferError(
        f"Keine der {len(goae)} GOÄ-Positionen dieser Lieferung ist im geladenen Katalog "
        f"{catalog.catalog_version} enthalten. Das ist kein Abdeckungsproblem, sondern ein "
        "Katalogkonflikt: die Lieferung wurde vermutlich gegen eine andere Fassung der GOÄ "
        "kodiert. Es wird kein Bericht erstellt, weil er zu jeder Position 'nicht beurteilbar' "
        "sagen würde.",
        unknown_ziffern=unknown,
        catalog_version=catalog.catalog_version,
        details={"goae_position_count": len(goae)},
    )


# ------------------------------------------------------------------------------------------
# the batch path
# ------------------------------------------------------------------------------------------


def _batch_not_found(batch_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": "batch_not_found",
            "message": (
                f"No batch {batch_id}. Batches are stored durably, so this id was never issued by "
                "this database — check it, or re-upload via POST /api/v1/padnext/batch."
            ),
        },
    )


@router.post(
    "/batch",
    response_model=BatchAuditAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def padnext_batch(
    background_tasks: BackgroundTasks,
    response: Response,
    actor: RequestActor,
    organization: RequestOrganization,
    files: list[UploadFile] = File(
        ...,
        description=(
            "The PADnext deliveries to audit — .padx containers or *_padx.xml payloads. "
            "Synthetic data only."
        ),
    ),
) -> BatchAuditAccepted:
    """Accept many PADnext deliveries and audit them in the background.

    Returns `202` with a `batch_id` immediately; the audit itself has not started. Poll
    `GET /api/v1/padnext/batch/{batch_id}` for progress, and read `aggregate_summary` once the
    status is `COMPLETED`.

    Multipart rather than raw bytes, unlike the single-file endpoint: many files in one request is
    what multipart is for, and there is no way to delimit them in a raw body. That is why the
    engine now depends on `python-multipart`.

    A delivery flagged as production data is refused per file, not per batch — the file is marked
    `FAILED` with the reason and the rest of the batch proceeds. See
    `docs/compliance/PRIVATE_DATA_WARNING.md`.
    """
    if not files:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "empty_batch",
                "message": (
                    "No files received. POST a multipart/form-data body with one or more `files` "
                    "parts, each a .padx container or a *_padx.xml payload."
                ),
            },
        )

    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "too_many_files",
                "message": (
                    f"{len(files)} files in one batch; this API accepts at most "
                    f"{MAX_BATCH_FILES}. Split the upload."
                ),
                "max_files": MAX_BATCH_FILES,
            },
        )

    # Read every upload here, in the request handler. `UploadFile` is closed as soon as the
    # response is sent, so a background task that tried to read it would find an empty stream —
    # and it would find it *after* the client had already been told the batch was accepted.
    uploads: list[tuple[str, bytes]] = []
    total = 0
    for upload in files:
        content = await upload.read()
        await upload.close()
        name = upload.filename or "unnamed"

        if not content:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "empty_file",
                    "message": f"{name!r} is empty. An empty part is a client bug, not a delivery.",
                    "filename": name,
                },
            )
        if len(content) > MAX_BATCH_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": "file_too_large",
                    "message": (
                        f"{name!r} is {len(content)} bytes; a single delivery may be at most "
                        f"{MAX_BATCH_FILE_BYTES}."
                    ),
                    "filename": name,
                    "max_bytes": MAX_BATCH_FILE_BYTES,
                },
            )
        total += len(content)
        if total > MAX_BATCH_TOTAL_BYTES:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": "batch_too_large",
                    "message": (
                        f"The batch exceeds {MAX_BATCH_TOTAL_BYTES} bytes in total. Split it."
                    ),
                    "max_bytes": MAX_BATCH_TOTAL_BYTES,
                },
            )
        uploads.append((name, content))

    # The quota, once the parts have been read and counted, and before any of them is queued.
    # Refused as a unit for the same reason `/audit/bulk` is: a batch that audited eleven of thirty
    # files because a ceiling was reached mid-run is worse for the practice than being told up front.
    #
    # The tenant here is required rather than optional — this endpoint writes rows and is in
    # `SCOPED_OPERATIONS` — so there is no "unmetered" branch, unlike `/padnext/audit`.
    quota = await check_and_refuse(organization, requested=len(uploads))

    service = batches()
    try:
        accepted, payloads = await service.create_batch(
            uploads, actor=actor, organization_id=organization
        )
    except EmptyBatch as exc:  # pragma: no cover - guarded above; belt and braces
        raise HTTPException(status_code=400, detail={"error": "empty_batch", "message": str(exc)}) from exc

    background_tasks.add_task(service.process_batch, accepted.batch_id, payloads)
    # On acceptance, not on completion — `/audit/bulk` carries the full reasoning. `file_count` is
    # what the `202` promised, so it is what is counted.
    record_invoices(accepted.file_count)
    apply_quota(response, quota)
    return accepted


@router.get("/batch", response_model=BatchAuditJobList)
async def padnext_batch_list(
    organization: RequestOrganization,
    status: BatchJobStatus | None = Query(
        default=None,
        description=(
            "Only batches in this state. Omit for every state. `PROCESSING` is what is still "
            "running; `FAILED` is what broke, including anything the startup recovery closed."
        ),
    ),
    created_after: datetime | None = Query(
        default=None,
        description=(
            "Only batches created at or after this instant — **inclusive**, so a batch stamped "
            "exactly here is returned. ISO-8601; a value without an offset is read as UTC."
        ),
    ),
    limit: int = Query(
        default=DEFAULT_BATCH_LIST_LIMIT,
        ge=1,
        le=MAX_BATCH_LIST_LIMIT,
        description="How many batches to return. `total` always reports every match.",
    ),
    offset: int = Query(default=0, ge=0, description="How many matches to skip. 0 is the newest."),
) -> BatchAuditJobList:
    """A page of the batches this database holds, newest first, as headers without their files.

    This is what makes a durable batch reachable again. A `batch_id` is issued once and the browser
    holds it in memory, so before this endpoint existed a page reload orphaned a finished batch —
    the roll-up was still in Postgres and nothing could ask for it. It is also where an operator
    sees a batch that was `FAILED` by the startup recovery, and reads why in `error_message`.

    Rows carry the stored `aggregate_summary` but **not** `files`: a listing that shipped every
    delivery's full audit report would be megabytes to render a table. Open one with
    `GET /api/v1/padnext/batch/{batch_id}` for the per-file detail.

    Scoped to the calling organisation, and `total` is recounted under that filter as well, so a
    practice sees its own batches and its own count. `total` is recounted under `status` and
    `created_after` too, so it says how many batches match and never how many rows the table holds. The rows themselves stay in `jobs` — not `items`,
    which is what the newer `GET /api/v1/proposals` envelope uses. The two disagree because this one
    shipped first and renaming a field in a contract already committed to `packages/contracts/`
    would break a client to buy symmetry.

    The page size ceiling is now 100, down from 500; `limit=200` is a `422` where it used to be
    served. See `MAX_BATCH_LIST_LIMIT` for why.

    Declared before `/batch/{batch_id}` for readability only — the two paths are distinct templates
    and neither shadows the other.
    """
    return await batches().list_batches(
        status=status,
        created_after=created_after,
        limit=limit,
        offset=offset,
        organization_id=organization,
    )


@router.get("/batch/{batch_id}", response_model=BatchAuditJob)
async def padnext_batch_status(
    batch_id: str, organization: RequestOrganization
) -> BatchAuditJob:
    """The batch's progress, and its result once it is done.

    While the job runs, `files` carries each delivery's status and no report — a two-second poll
    over a hundred files must not ship a hundred full audit reports per tick. Once the status is
    terminal, every completed file's `report` is the same `PadnextAuditReport` the single-file
    endpoint would have returned, and `aggregate_summary` holds the roll-up.

    `files` arrives sorted by `confirmed_wrong_eur` descending — riskiest first. Sorted here rather
    than in the client because the amounts are exact decimal strings that a JavaScript client must
    not parse back into numbers.
    """
    try:
        return await batches().load_batch(batch_id, organization_id=organization)
    except BatchNotFound as exc:
        raise _batch_not_found(batch_id) from exc


@router.post(
    "/batch/{batch_id}/report.pdf",
    response_class=Response,
    responses={
        200: {
            "description": "Der Stapel-Prüfbericht als PDF, `<batch_id>_pruefbericht.pdf`.",
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        },
        409: {"description": "Der Stapel ist nicht abgeschlossen; es gibt keinen Bericht."},
    },
)
async def padnext_batch_report_pdf(
    batch_id: str, organization: RequestOrganization
) -> Response:
    """Einen abgeschlossenen Stapel als druckbaren Prüfbericht.

    ---

    The web tier's route to the batch Prüfbericht. The partner API has carried this since the bulk
    endpoint shipped (`POST /api/v1/audit/{job_id}/pdf`); the application had only the CSV export
    beside it, so the one artefact a Rechnungsprüfer actually files was reachable by API key and
    not by the people using the product.

    Both routes render through `app.services.pdf.render_batch_report` over the same
    `BatchAuditJob`, so a batch downloaded here and the same batch downloaded with an API key are
    byte-identical — including the date, which comes from the job's own completion time rather
    than from the clock. Re-downloading a finished batch next week gives the same file.

    `COMPLETED` only, for the reason the CSV export gives: a running batch would produce totals
    that are a snapshot of an unidentifiable moment, and a caveat printed beside them does not
    survive the document being pulled out of a folder three weeks later.
    """
    try:
        job = await batches().load_batch(batch_id, organization_id=organization)
    except BatchNotFound as exc:
        raise _batch_not_found(batch_id) from exc

    if job.status != BatchJobStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "batch_not_completed",
                "message": (
                    f"Stapel {batch_id} ist {job.status}, nicht COMPLETED. Ein Bericht wird erst "
                    "erstellt, wenn jede Lieferung ein Verdikt hat. — The batch has not "
                    "completed, so there is no report to render."
                ),
                "current_status": str(job.status),
            },
        ) from None

    document = render_batch_report(job, organization_id=organization)
    return Response(
        content=document,
        media_type="application/pdf",
        headers={
            **attachment_headers(f"{batch_id}_pruefbericht.pdf"),
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "/batch/{batch_id}/export",
    response_class=Response,
    responses={
        200: {
            "description": (
                "A ZIP archive named `{batch_id}_export.zip` holding `batch_summary.csv`, "
                "`batch_line_items.csv`, `batch_files.csv` and a `README.txt` that defines the "
                "three buckets."
            ),
            "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
        },
        409: {"description": "The batch has not completed, so there is no roll-up to export."},
    },
)
async def padnext_batch_export(
    batch_id: str, organization: RequestOrganization
) -> Response:
    """Download a completed batch as CSVs, for a billing centre.

    Only a `COMPLETED` batch can be exported. A running one would produce totals that are a
    snapshot of an unidentifiable moment, and a `FAILED` one has no roll-up at all — both are
    `409` rather than a file with a caveat attached, because a caveat does not survive being
    opened in a spreadsheet three weeks later.

    Read-only: unlike the proposal export this changes no status and writes no audit row, so the
    same archive can be downloaded repeatedly and is byte-identical each time. See
    `app.services.batch_audit.export_batch` for why the two exports differ on that.

    CSV rather than JSON because the reader is a Rechnungsprüfer with a spreadsheet. The archive
    carries a `README.txt` stating that `unconfirmed` is the boundary of this engine's rule
    coverage and not a finding against the practice — a CSV outlives the screen it came from, and
    that sentence has to travel with the numbers.
    """
    try:
        archive = await batches().export_batch(batch_id, organization_id=organization)
    except BatchNotFound as exc:
        raise _batch_not_found(batch_id) from exc
    except BatchNotExportable as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "batch_not_completed",
                "message": str(exc),
                "current_status": str(exc.status),
            },
        ) from exc

    return Response(
        content=archive,
        media_type="application/zip",
        headers=attachment_headers(batch_export_filename(batch_id)),
    )
