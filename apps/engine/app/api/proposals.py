"""The human approval boundary.

The engine produces drafts. Somebody with the right to bill accepts one. These endpoints are that
boundary, and they are the reason `ProposalStatus` exists rather than a boolean: `DRAFT` is not
"not yet saved", it is "nobody has taken responsibility for this".

The record is durable and every decision is logged: the store writes the status change and its
audit row in one transaction against Postgres (`app.services.proposal_store`), so an approval
survives a restart and can be shown to have been made by a named person at a stated time. Two
things are still missing before this endpoint means what a regulator would want it to mean:
**authentication** — `approved_by` is a string the caller supplies, not an identity the service
verified — and a **retention policy**. Both are tracked in
`docs/compliance/PRIVATE_DATA_WARNING.md`.

These path functions are `async def`, unlike `/solve`. They do database I/O and nothing else, so
awaiting is exactly right; dispatching them to the threadpool would only add a hop.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import proposals
from app.schemas import ApprovalRequest, Proposal, ProposalStatus, RejectionRequest
from app.services.proposal_store import IllegalTransitionError, ProposalNotFound

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


@router.get("", response_model=list[Proposal])
async def list_proposals(status: ProposalStatus | None = Query(default=None)) -> list[Proposal]:
    return await proposals().list_proposals(status=status)


@router.get("/{proposal_id}", response_model=Proposal)
async def get_proposal(proposal_id: str) -> Proposal:
    # Reads one proposal and records a VIEWED event: who looked is part of the audit question.
    #
    # A comment rather than a docstring, deliberately. FastAPI publishes a path function's docstring
    # as the operation's `description`, so adding one here would change the committed OpenAPI
    # document — and this migration's contract with the frontend is that the document does not move.
    # The actor is `anonymous`, because this service authenticates nobody; see `ANONYMOUS_ACTOR` in
    # the store for why that value is deliberately conspicuous rather than plausible.
    try:
        return await proposals().get_proposal(proposal_id, record_view=True)
    except ProposalNotFound as exc:
        raise _not_found(proposal_id) from exc


@router.post("/{proposal_id}/approve", response_model=Proposal)
async def approve(proposal_id: str, request: ApprovalRequest) -> Proposal:
    """Accept a draft. `approved_by` is required — an unattributed approval is not one."""
    try:
        return await proposals().approve_proposal(
            proposal_id, approved_by=request.approved_by, note=request.note
        )
    except ProposalNotFound as exc:
        raise _not_found(proposal_id) from exc
    except IllegalTransitionError as exc:
        raise _conflict(exc) from exc


@router.post("/{proposal_id}/reject", response_model=Proposal)
async def reject(proposal_id: str, request: RejectionRequest) -> Proposal:
    """Refuse a draft, with a reason. Terminal: a rejected draft is not re-decided, it is re-run."""
    try:
        return await proposals().reject_proposal(
            proposal_id, rejected_by=request.rejected_by, reason=request.reason
        )
    except ProposalNotFound as exc:
        raise _not_found(proposal_id) from exc
    except IllegalTransitionError as exc:
        raise _conflict(exc) from exc


@router.post("/{proposal_id}/export", response_model=Proposal)
async def mark_exported(proposal_id: str) -> Proposal:
    """Record that an approved proposal left the system. Only reachable from APPROVED."""
    try:
        return await proposals().export_proposal(proposal_id)
    except ProposalNotFound as exc:
        raise _not_found(proposal_id) from exc
    except IllegalTransitionError as exc:
        raise _conflict(exc) from exc
