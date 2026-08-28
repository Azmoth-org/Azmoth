"""The human approval boundary.

The engine produces drafts. Somebody with the right to bill accepts one. These endpoints are that
boundary, and they are the reason `ProposalStatus` exists rather than a boolean: `DRAFT` is not
"not yet saved", it is "nobody has taken responsibility for this".

The record is durable and every decision is logged: the store writes the status change and its
audit row in one transaction against Postgres (`app.services.proposal_store`), so an approval
survives a restart and can be shown to have been made by a named person at a stated time.

Two things are still missing before this endpoint means what a regulator would want it to mean.
**The identity is asserted, not proven.** `approved_by` is a string the caller supplies, and the
`X-User-ID` the web tier now forwards (`app.api.identity`) is a header this service records without
verifying — so the log holds both "who signed" and "which account was signed in", and nothing here
requires them to agree. A Better Auth JWT the engine verifies itself is what closes that. And there
is still no **retention policy**. Both are tracked in `docs/compliance/PRIVATE_DATA_WARNING.md`.

**Every endpoint here is organisation-scoped.** `RequestOrganization` reads the `X-Organization-ID`
header the web tier sets from the session's active practice and refuses a request without one with a
`403` (`app.api.tenancy`). The tenant is then part of the `WHERE` on every read and every write, so
a proposal belonging to another practice is a `404` here — not a `403`, which would confirm that a
guessed `prop_…` id exists and merely belongs to somebody else. That distinction is the whole point:
the id is the only thing an attacker has, and the answer must not tell them whether it was a good
guess.

These path functions are `async def`, unlike `/solve`. They do database I/O and nothing else, so
awaiting is exactly right; dispatching them to the threadpool would only add a hop.

`POST /{id}/export` is the one that returns a file rather than a model. It answers with the JSON
export document as an attachment, assembled inside the same transaction that marks the proposal
`EXPORTED` and writes the audit event — see `app.services.proposal_store.export_proposal_document`
for why that has to be one transaction rather than a transition followed by a read.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Response

from app.api.deps import proposals
from app.api.identity import RequestActor
from app.api.tenancy import RequestOrganization
from app.schemas import (
    ApprovalRequest,
    ExportRequest,
    Proposal,
    ProposalExport,
    ProposalList,
    ProposalStatus,
    RejectionRequest,
)
from app.services.export import attachment_headers, proposal_export_filename
from app.services.proposal_store import (
    DEFAULT_PROPOSAL_LIST_LIMIT,
    MAX_PROPOSAL_LIST_LIMIT,
    IllegalTransitionError,
    ProposalNotFound,
)

router = APIRouter(prefix="/proposals", tags=["proposals"])


def _not_found(proposal_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": "proposal_not_found",
            "message": (
                f"No proposal {proposal_id}. Proposals are stored durably, so this id was never "
                "issued by this database — check it, or re-run POST /api/v1/solve."
            ),
        },
    )


def _conflict(exc: IllegalTransitionError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "error": "illegal_transition",
            "message": str(exc),
            "current_status": str(exc.current),
            "requested_status": str(exc.requested),
        },
    )


@router.get("", response_model=ProposalList)
async def list_proposals(
    organization: RequestOrganization,
    status: ProposalStatus | None = Query(
        default=None,
        description=(
            "Only proposals in this lifecycle state. Omit for every state. `DRAFT` is the review "
            "queue: nobody has taken responsibility for those yet."
        ),
    ),
    case_id: str | None = Query(
        default=None,
        description=(
            "Only proposals carrying exactly this `case_id` — the caller's own identifier for the "
            "encounter, matched in full rather than as a substring. Blank is the same as omitting "
            "it."
        ),
    ),
    limit: int = Query(
        default=DEFAULT_PROPOSAL_LIST_LIMIT,
        ge=1,
        le=MAX_PROPOSAL_LIST_LIMIT,
        description="How many proposals to return. `total` always reports every match.",
    ),
    offset: int = Query(default=0, ge=0, description="How many matches to skip. 0 is the newest."),
) -> ProposalList:
    """One page of proposals, newest first, with the count of every match beside it.

    Scoped to the calling organisation. `total` is recounted under that filter too, so a practice's
    review queue reports its own backlog and never the size of the table.

    **This returns an envelope, where it previously returned a bare JSON array.** A client reading
    the old shape sees `items`. The change is not cosmetic: without `total` a caller cannot tell
    fifty proposals from the first fifty of nine hundred, and a review queue whose size it cannot
    state is not a queue. `total` counts everything matching `status` and `case_id`, not the page.

    Unpaginated is no longer an option, and that is deliberate rather than an oversight. The old
    call took the newest 500 rows unconditionally and each of those carries a whole `solver_result`;
    on a table that only grows, "all records" is a response size that depends on how long the
    service has been running. Omitting `limit` gets the newest 50 — a default, not a cap on what is
    reachable, since `offset` walks the rest.

    Ordered `created_at DESC`, tie-broken on the surrogate key so two proposals stamped in the same
    microsecond cannot swap places between two reads and make paging skip or repeat one. Note that
    this reverses what the endpoint used to return: it served the newest page *ascending*, which
    cannot be paged coherently. See `app.services.proposal_store.list_proposals`.
    """
    return await proposals().list_proposals(
        status=status,
        case_id=case_id,
        limit=limit,
        offset=offset,
        organization_id=organization,
    )


@router.get("/{proposal_id}", response_model=Proposal)
async def get_proposal(
    proposal_id: str, actor: RequestActor, organization: RequestOrganization
) -> Proposal:
    # Reads one proposal and records a VIEWED event: who looked is part of the audit question.
    #
    # A comment rather than a docstring, deliberately. FastAPI publishes a path function's docstring
    # as the operation's `description`, so adding one here would change the committed OpenAPI
    # document — and this migration's contract with the frontend is that the document does not move.
    # `actor` is a `Depends` on the request object rather than a declared header, for that same
    # reason: it stays out of the document.
    #
    # It is the Better Auth user id the web tier forwarded, and it falls back to `anonymous` for a
    # call that carried no session — see `ANONYMOUS_ACTOR` in the store for why that value is
    # deliberately conspicuous rather than plausible. A `VIEWED` row now names a person for every
    # read that came through the UI, which is the half of "who looked at this record" that a
    # clinical audit log has to be able to answer.
    try:
        return await proposals().get_proposal(
            proposal_id, record_view=True, actor=actor, organization_id=organization
        )
    except ProposalNotFound as exc:
        raise _not_found(proposal_id) from exc


@router.post("/{proposal_id}/approve", response_model=Proposal)
async def approve(
    proposal_id: str, request: ApprovalRequest, organization: RequestOrganization
) -> Proposal:
    """Accept a draft. `approved_by` is required — an unattributed approval is not one.

    Scoped: another practice's draft is a `404`, so an approval cannot be taken on a record the
    caller may not see. This is the write the boundary exists for — a reader that could approve by
    id would make the read scoping decorative.
    """
    try:
        return await proposals().approve_proposal(
            proposal_id,
            approved_by=request.approved_by,
            note=request.note,
            organization_id=organization,
        )
    except ProposalNotFound as exc:
        raise _not_found(proposal_id) from exc
    except IllegalTransitionError as exc:
        raise _conflict(exc) from exc


@router.post("/{proposal_id}/reject", response_model=Proposal)
async def reject(
    proposal_id: str, request: RejectionRequest, organization: RequestOrganization
) -> Proposal:
    """Refuse a draft, with a reason. Terminal: a rejected draft is not re-decided, it is re-run.

    Scoped like the approval.
    """
    try:
        return await proposals().reject_proposal(
            proposal_id,
            rejected_by=request.rejected_by,
            reason=request.reason,
            organization_id=organization,
        )
    except ProposalNotFound as exc:
        raise _not_found(proposal_id) from exc
    except IllegalTransitionError as exc:
        raise _conflict(exc) from exc


@router.post(
    "/{proposal_id}/export",
    response_model=ProposalExport,
    responses={
        200: {
            "description": (
                "The export document, as a downloadable attachment named "
                "`{proposal_id}.json`."
            ),
            "content": {"application/json": {}},
        },
        409: {"description": "The proposal is not APPROVED, so there is nothing to export."},
    },
)
async def export_proposal(
    proposal_id: str, request: ExportRequest, organization: RequestOrganization
) -> Response:
    """Export an approved proposal, and record that it left the system.

    Only reachable from `APPROVED`; anything else is a `409`. The transition to `EXPORTED` is
    terminal, so a proposal can be exported exactly once — which is the point, since the export is
    the record of a decision rather than a report that can be regenerated on a whim.

    `exported_by` is required. It is written to the `EXPORTED` audit event and into the document
    itself, and it is recorded rather than verified: this service authenticates nobody.

    The response body is the `ProposalExport` document with a `Content-Disposition: attachment`
    header. It is served as a `Response` rather than returned as a model so the header and the
    exact bytes are ours — a browser must be able to save this file, and the JSON is
    pretty-printed because a human opening it in an editor is a first-class use.
    """
    try:
        document = await proposals().export_proposal_document(
            proposal_id,
            exported_by=request.exported_by,
            note=request.note,
            organization_id=organization,
        )
    except ProposalNotFound as exc:
        raise _not_found(proposal_id) from exc
    except IllegalTransitionError as exc:
        raise _conflict(exc) from exc

    # `mode="json"` so every Decimal becomes its exact string and every datetime an ISO-8601
    # instant — the same serialisation the API uses everywhere else. `ensure_ascii=False` because
    # a Leistungstext contains umlauts and an escaped one is unreadable in the saved file.
    body = json.dumps(
        document.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=False
    )
    return Response(
        content=body,
        media_type="application/json",
        headers=attachment_headers(proposal_export_filename(document.proposal_id)),
    )
