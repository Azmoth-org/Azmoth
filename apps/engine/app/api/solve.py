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

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from app.api.deps import pipeline, proposals
from app.schemas import Proposal, SolveRequest
from app.solvers.clingo_solver import ClingoError, ClingoTimeout
from app.solvers.souffle_engine import SouffleError
from app.validation.validator import ValidationFailed

log = logging.getLogger(__name__)

router = APIRouter(tags=["solve"])


@router.post("/solve", response_model=Proposal)
async def solve(request: SolveRequest) -> Proposal:
    """Run the deterministic pipeline and store the result as a DRAFT proposal.

    The response is a proposal, never an invoice: `status` is `DRAFT` and stays there until a
    named person approves it via `POST /api/v1/proposals/{id}/approve`. `receipt_hash` identifies
    the catalog, rule tables, logic programs, solver versions, policy and input that produced it.
    """
    try:
        proposal = await run_in_threadpool(
            pipeline().propose,
            request.extraction,
            setting=request.setting,
            case_id=request.case_id,
        )
    except ValidationFailed as exc:
        # Independent validation contradicted the solver. Never returned as a valid invoice.
        raise HTTPException(
            status_code=500,
            detail={
                "error": "validation_failed",
                "message": (
                    "The independent validation pass disagreed with the solver. No draft is "
                    "returned; this is a defect in the engine, not in the input."
                ),
                "violations": [v.model_dump() for v in exc.violations],
            },
        ) from exc
    except ClingoTimeout as exc:
        raise HTTPException(
            status_code=504,
            detail={
                "error": "solver_timeout",
                "message": str(exc),
                "timeout_seconds": exc.timeout_seconds,
            },
        ) from exc
    except SouffleError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "rules_engine_failed",
                "message": str(exc),
                "stderr": exc.stderr,
                "facts": exc.fact_dump,
            },
        ) from exc
    except ClingoError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "optimizer_failed", "message": str(exc), "program": exc.program},
        ) from exc

    # Read back off the row that was written, not echoed from the object in hand: if persisting
    # ever lost or mangled a field, the first request would say so instead of the first restart.
    # The `CREATED` audit event is written in the same transaction.
    return await proposals().create_proposal(proposal)
