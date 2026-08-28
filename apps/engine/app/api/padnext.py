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
from datetime import datetime

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

from app.api.deps import batches, pipeline
from app.api.identity import RequestActor
from app.api.tenancy import RequestOrganization
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


@router.post("/audit", response_model=PadnextAuditReport)
def padnext_audit(request: Request, body: bytes = Body(default=b"")) -> PadnextAuditReport:
    """Audit a PADnext delivery against the GOÄ rules.

    The body is the file itself, not a JSON wrapper or a multipart upload: either a `.padx`
    container (a ZIP, sniffed by magic bytes) or a bare `*_padx.xml` payload. Taking raw bytes
    avoids a `python-multipart` dependency for what is one file per request.

    A delivery flagged as production data is refused with 422 — see `app.padnext.audit` and
    `docs/compliance/PRIVATE_DATA_WARNING.md`.

    Failures carry `error_code`: `EMPTY_REQUEST_BODY` (400), `INVALID_XML` (400, with the line and
    column in `details`), `PADNEXT_SCHEMA_VIOLATION` (422, every violation in `details`),
    `PADNEXT_UNREADABLE` (422), `UNKNOWN_ZIFFER` (422, when no position is in this catalog at
    all), `REAL_DATA_REFUSED` (422) and `RULES_ENGINE_UNAVAILABLE` (503, retryable). See
    `docs/errors.md`.
    """
    if not body:
        raise EmptyRequestBody(
            "Empty body. POST the PADnext file itself — a .padx container or a *_padx.xml "
            "payload — with Content-Type application/xml or application/octet-stream."
        )

    source_name = request.headers.get("x-padnext-filename", "")
    # `read_delivery` raises `InvalidXmlError` (400, with the line and column), `PadnextSchemaError`
    # (422, with every violation) or a bare `PadnextError` (422). All three are in the catalog and
    # all three are rendered by the handler, so there is nothing to translate here.
    delivery, read_findings = read_delivery(body, source_name=source_name)

    pipe = pipeline()
    _refuse_if_no_position_is_in_the_catalog(delivery, pipe.catalog)

    # `RealDataRefused` (422) and `SouffleError` (503, retryable) likewise carry their own status.
    return audit_delivery(
        delivery,
        catalog=pipe.catalog,
        rules=pipe.rules,
        souffle_run=pipe.souffle.run,
        read_findings=read_findings,
        settings=pipe.settings,
    )


def _refuse_if_no_position_is_in_the_catalog(delivery, catalog) -> None:
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

    service = batches()
    try:
        accepted, payloads = await service.create_batch(
            uploads, actor=actor, organization_id=organization
        )
    except EmptyBatch as exc:  # pragma: no cover - guarded above; belt and braces
        raise HTTPException(status_code=400, detail={"error": "empty_batch", "message": str(exc)}) from exc

    background_tasks.add_task(service.process_batch, accepted.batch_id, payloads)
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
