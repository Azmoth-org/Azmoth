"""Where proposals live between being produced and being approved.

Deliberately in-memory: the brief is explicit that no database is to be built yet, and inventing a
schema now would be inventing the retention policy, the access control and the audit log with it —
all three of which are legal questions before they are engineering ones (see
`docs/compliance/PRIVATE_DATA_WARNING.md`).

What that costs is stated rather than hidden: proposals do not survive a restart, and they are not
shared between workers. `ProposalStore` is the seam a real repository implements — four methods,
no SQL leaking upward.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import datetime, timezone

from app.schemas import Proposal, ProposalStatus


class ProposalNotFound(KeyError):
    def __init__(self, proposal_id: str) -> None:
        super().__init__(proposal_id)
        self.proposal_id = proposal_id


class IllegalTransition(RuntimeError):
    """A status change the lifecycle does not allow. Refused, never silently applied."""

    def __init__(self, current: ProposalStatus, requested: ProposalStatus) -> None:
        super().__init__(
            f"A proposal in status {current} cannot become {requested}. "
            f"Allowed from {current}: {', '.join(str(s) for s in ALLOWED[current]) or 'nothing'}."
        )
        self.current = current
        self.requested = requested


#: DRAFT is the only state a decision can be made in, and an APPROVED proposal can only go on to
#: be EXPORTED. A REJECTED or EXPORTED proposal is terminal: re-deciding one would mean the
#: approval record no longer describes what was billed.
ALLOWED: dict[ProposalStatus, tuple[ProposalStatus, ...]] = {
    ProposalStatus.DRAFT: (ProposalStatus.APPROVED, ProposalStatus.REJECTED),
    ProposalStatus.APPROVED: (ProposalStatus.EXPORTED,),
    ProposalStatus.REJECTED: (),
    ProposalStatus.EXPORTED: (),
}


class ProposalStore:
    def __init__(self, max_entries: int = 512) -> None:
        self._max = max(1, max_entries)
        self._data: OrderedDict[str, Proposal] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, proposal: Proposal) -> Proposal:
        with self._lock:
            self._data[proposal.proposal_id] = proposal
            self._data.move_to_end(proposal.proposal_id)
            while len(self._data) > self._max:
                self._data.popitem(last=False)
        return proposal

    def get(self, proposal_id: str) -> Proposal:
        with self._lock:
            proposal = self._data.get(proposal_id)
        if proposal is None:
            raise ProposalNotFound(proposal_id)
        return proposal

    def list(self, *, status: ProposalStatus | None = None) -> list[Proposal]:
        with self._lock:
            values = list(self._data.values())
        return [p for p in values if status is None or p.status is status]

    def transition(
        self,
        proposal_id: str,
        to: ProposalStatus,
        *,
        by: str | None = None,
        reason: str | None = None,
    ) -> Proposal:
        proposal = self.get(proposal_id)
        if to not in ALLOWED[proposal.status]:
            raise IllegalTransition(proposal.status, to)

        updated = proposal.model_copy(update={"status": to})
        if to is ProposalStatus.APPROVED:
            updated.approved_at = datetime.now(timezone.utc)
            updated.approved_by = by
        elif to is ProposalStatus.REJECTED:
            updated.rejected_reason = reason
        return self.put(updated)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
