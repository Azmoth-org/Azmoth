"""Shared, lazily built singletons.

The pipeline loads a 1 MB catalog, 260 kB of rule CSVs and hashes both, so it is built once per
process and not per request. It is built lazily rather than at import time so that `import app.main`
works — for an OpenAPI export, say — on a machine with no Soufflé binary and no database.

The store is a singleton for a different reason. It is stateless: the state is in Postgres, and a
new `ProposalStore` per request would be free. What must not be rebuilt is the connection pool
underneath it (`app.db.session.Database`), and the store holds none of its own — it asks
`get_database()` each time — so the singleton here is only about not allocating an object per
request. `reset()` therefore leaves the database alone; disposing an engine is async and belongs to
the lifespan, which is where `reset_async()` does it.
"""

from __future__ import annotations

from app.db.session import reset_database
from app.services.pipeline import Pipeline
from app.services.proposal_store import ProposalStore

_pipeline: Pipeline | None = None
_proposals: ProposalStore | None = None


def pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline()
    return _pipeline


def proposals() -> ProposalStore:
    global _proposals
    if _proposals is None:
        _proposals = ProposalStore()
    return _proposals


def reset() -> None:
    """Drop the in-process singletons. For tests that change settings between cases.

    Does not touch the database: the engine has to be disposed with an `await`, and a sync helper
    that quietly left a connection pool open would leak one per test. Use `reset_async`.
    """
    global _pipeline, _proposals
    _pipeline = None
    _proposals = None


async def reset_async() -> None:
    """`reset()`, plus disposing the database engine. What the test suite and the lifespan use."""
    reset()
    await reset_database()
