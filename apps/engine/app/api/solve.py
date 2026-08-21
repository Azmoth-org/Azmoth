"""`POST /api/v1/solve` — clinical entities in, a receipted DRAFT proposal out.

Declared `def`, not `async def`, deliberately: the pipeline shells out to Soufflé and runs Clingo
in-process, both CPU-bound and both blocking. FastAPI runs a sync path function in its threadpool,
so the event loop keeps serving while a solve is in flight. Making this `async def` would block
every other request for the duration of the solve.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.api.deps import pipeline, proposals
from app.schemas import Proposal, SolveRequest
from app.solvers.clingo_solver import ClingoError, ClingoTimeout
from app.solvers.souffle_engine import SouffleError
from app.validation.validator import ValidationFailed

log = logging.getLogger(__name__)

router = APIRouter(tags=["solve"])


@router.post("/solve", response_model=Proposal)
def solve(request: SolveRequest) -> Proposal:
    """Run the deterministic pipeline and store the result as a DRAFT proposal.

    The response is a proposal, never an invoice: `status` is `DRAFT` and stays there until a
    named person approves it via `POST /api/v1/proposals/{id}/approve`. `receipt_hash` identifies
    the catalog, rule tables, logic programs, solver versions, policy and input that produced it.
    """
    try:
        proposal = pipeline().propose(
            request.extraction, setting=request.setting, case_id=request.case_id
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

    return proposals().put(proposal)
