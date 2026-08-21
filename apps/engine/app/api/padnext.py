"""`POST /api/v1/padnext/audit` — check an already-coded delivery against the GOÄ rules.

Sync (`def`) for the same reason as `solve`: the audit runs Soufflé.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from app.api.deps import pipeline
from app.padnext import PadnextError, RealDataRefused, audit_delivery, read_delivery
from app.schemas import PadnextAuditReport
from app.solvers.souffle_engine import SouffleError

router = APIRouter(prefix="/padnext", tags=["padnext"])


@router.post("/audit", response_model=PadnextAuditReport)
def padnext_audit(request: Request, body: bytes = Body(default=b"")) -> PadnextAuditReport:
    """Audit a PADnext delivery against the GOÄ rules.

    The body is the file itself, not a JSON wrapper or a multipart upload: either a `.padx`
    container (a ZIP, sniffed by magic bytes) or a bare `*_padx.xml` payload. Taking raw bytes
    avoids a `python-multipart` dependency for what is one file per request.

    A delivery flagged as production data is refused with 422 — see `app.padnext.audit` and
    `docs/compliance/PRIVATE_DATA_WARNING.md`.
    """
    if not body:
        raise HTTPException(
            status_code=400,
            detail=(
                "Empty body. POST the PADnext file itself — a .padx container or a *_padx.xml "
                "payload — with Content-Type application/xml or application/octet-stream."
            ),
        )

    source_name = request.headers.get("x-padnext-filename", "")
    try:
        delivery, read_findings = read_delivery(body, source_name=source_name)
    except PadnextError as exc:
        raise HTTPException(status_code=422, detail=f"Unreadable PADnext delivery: {exc}") from exc

    pipe = pipeline()
    try:
        return audit_delivery(
            delivery,
            catalog=pipe.catalog,
            rules=pipe.rules,
            souffle_run=pipe.souffle.run,
            read_findings=read_findings,
            settings=pipe.settings,
        )
    except RealDataRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SouffleError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
