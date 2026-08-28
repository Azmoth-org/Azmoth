"""`POST /api/v1/solve` — clinical entities in, a receipted DRAFT proposal out.

The handler is `async def` and the *solve* is not. The pipeline shells out to Soufflé and runs
Clingo in-process, both CPU-bound and both blocking, so running it on the event loop would stall
every other request for its duration — it goes to the threadpool via `run_in_threadpool`, which is
the same pool FastAPI would have used for a plain `def` handler. What changed is that persisting the
result is now a database write, and awaiting it directly is much better than the alternative: a sync
handler would have to bridge back to the loop from a worker thread to reach the async driver, which
works but hides a foot-gun for the next person to touch this file.

So: the CPU-bound part still runs off the loop, and the I/O-bound part is awaited on it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.api.deps import pipeline, proposals
from app.api.identity import RequestActor
from app.api.tenancy import RequestOrganization
from app.schemas import Proposal, SolveRequest

log = logging.getLogger(__name__)

router = APIRouter(tags=["solve"])


@router.post("/solve", response_model=Proposal)
async def solve(
    request: SolveRequest, actor: RequestActor, organization: RequestOrganization
) -> Proposal:
    """Run the deterministic pipeline and store the result as a DRAFT proposal.

    The response is a proposal, never an invoice: `status` is `DRAFT` and stays there until a
    named person approves it via `POST /api/v1/proposals/{id}/approve`. `receipt_hash` identifies
    the catalog, rule tables, logic programs, solver versions, policy and input that produced it.

    The draft is stamped with the calling organisation, which is what makes it visible to that
    practice and to no other. A request that does not name one is refused with `403` before the
    solve runs — there is no default tenant to file a billing draft under, and inventing one would
    put a real encounter in a bucket nobody owns. See `docs/errors.md` under
    `ORGANIZATION_REQUIRED` for what to send.

    Failures carry `error_code`: `ORGANIZATION_REQUIRED` (403) if the request does not say which
    practice it is for, `VALIDATION_ERROR` (422) if the extraction does not match the schema,
    `SOLVER_TIMEOUT` (504) if the optimiser found no answer set inside `SOLVER_TIMEOUT_SECONDS`,
    `RULES_ENGINE_UNAVAILABLE` (503, retryable) if Soufflé could not be run, and
    `TRANSIENT_DB_FAILURE` (503, retryable) if the draft could not be stored. See `docs/errors.md`.
    """
    # No `try/except` for the four solver failures any more. `ValidationFailed`, `ClingoTimeout`,
    # `SouffleError` and `ClingoError` all carry their own status, code and details now, and
    # `app.api.errors.engine_error_handler` renders them — including when one is raised from
    # somewhere this function cannot see. What the mapping *is* has not changed: 500, 504, 503,
    # 500 respectively, and `docs/errors.md` is where it is written down.
    #
    # One thing did change, deliberately. The optimiser's program text and the Soufflé fact dump
    # used to be in the response body; they are in the log now. Both are the injected facts of a
    # patient encounter, and an error body is the last place they belong.
    proposal = await run_in_threadpool(
        pipeline().propose,
        request.extraction,
        setting=request.setting,
        case_id=request.case_id,
    )

    # Read back off the row that was written, not echoed from the object in hand: if persisting
    # ever lost or mangled a field, the first request would say so instead of the first restart.
    # The `CREATED` audit event is written in the same transaction.
    #
    # `actor` is the Better Auth user id the web tier forwarded, or `anonymous` for a call with no
    # session — a direct `curl`, `/docs`, the test suite. It lands on `proposals.created_by` and on
    # the `CREATED` event; see `app.api.identity` for why the header is recorded but not trusted.
    return await proposals().create_proposal(
        proposal, actor=actor, organization_id=organization
    )
