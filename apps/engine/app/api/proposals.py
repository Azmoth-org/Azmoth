"""The human approval boundary.

The engine produces drafts. Somebody with the right to bill accepts one. These endpoints are that
boundary, and they are the reason `ProposalStatus` exists rather than a boolean: `DRAFT` is not
"not yet saved", it is "nobody has taken responsibility for this".

The store is in-memory (see `app.services.proposal_store` for what that costs and why no database
was invented here). An approval is therefore **not** durable and **not** an audit log — a real
pilot needs both, plus access control, before this endpoint means anything legally. That is stated
in the response and in `docs/compliance/PRIVATE_DATA_WARNING.md`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import proposals
from app.schemas import ApprovalRequest, Proposal, ProposalStatus, RejectionRequest
from app.services.proposal_store import IllegalTransition, ProposalNotFound

router = APIRouter(prefix="/proposals", tags=["proposals"])


def _get(proposal_id: str) -> Proposal:
    try:
        return proposals().get(proposal_id)
    except ProposalNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "proposal_not_found",
                "message": (
                    f"No proposal {proposal_id}. Proposals are held in memory and do not survive "
                    "a restart; re-run POST /api/v1/solve."
                ),
            },
        ) from exc


def _transition(
    proposal_id: str, to: ProposalStatus, *, by: str | None = None, reason: str | None = None
) -> Proposal:
    _get(proposal_id)
    try:
        return proposals().transition(proposal_id, to, by=by, reason=reason)
    except IllegalTransition as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "illegal_transition",
                "message": str(exc),
                "current_status": str(exc.current),
                "requested_status": str(exc.requested),
            },
        ) from exc


@router.get("", response_model=list[Proposal])
def list_proposals(status: ProposalStatus | None = Query(default=None)) -> list[Proposal]:
    return proposals().list(status=status)


@router.get("/{proposal_id}", response_model=Proposal)
def get_proposal(proposal_id: str) -> Proposal:
    return _get(proposal_id)


@router.post("/{proposal_id}/approve", response_model=Proposal)
def approve(proposal_id: str, request: ApprovalRequest) -> Proposal:
    """Accept a draft. `approved_by` is required — an unattributed approval is not one."""
    return _transition(proposal_id, ProposalStatus.APPROVED, by=request.approved_by)


@router.post("/{proposal_id}/reject", response_model=Proposal)
def reject(proposal_id: str, request: RejectionRequest) -> Proposal:
    """Refuse a draft, with a reason. Terminal: a rejected draft is not re-decided, it is re-run."""
    return _transition(proposal_id, ProposalStatus.REJECTED, reason=request.reason)


@router.post("/{proposal_id}/export", response_model=Proposal)
def mark_exported(proposal_id: str) -> Proposal:
    """Record that an approved proposal left the system. Only reachable from APPROVED."""
    return _transition(proposal_id, ProposalStatus.EXPORTED)
