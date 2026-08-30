"""Shared, lazily built singletons.

The pipeline loads a 1 MB catalog, 260 kB of rule CSVs and hashes both, so it is built once per
process and not per request. It is built lazily rather than at import time so that `import app.main`
works — for an OpenAPI export, say — on a machine with no Soufflé binary and no database.

The two service objects are singletons for a different reason. They are stateless: the state is in
Postgres, and a new `ProposalStore` or `BatchAuditService` per request would be free. What must not
be rebuilt is the connection pool underneath them (`app.db.session.Database`), and neither holds
one of its own — both ask `get_database()` each time — so the singletons here are only about not
allocating an object per request. `reset()` therefore leaves the database alone; disposing an
engine is async and belongs to the lifespan, which is where `reset_async()` does it.

`BatchAuditService` is the one that has to outlive its request: a `BackgroundTask` runs after the
response, and it holds the bound method it was handed. Keeping the instance process-wide means the
task cannot be running against an object the router has already discarded. It is also where the
bulk queue's per-process drain lock lives, so there must be exactly one of it — two instances would
each hold their own lock and could drain the same queue at once.

`ApiKeyStore` is on the hot path rather than outliving anything: it is asked to verify a credential
on every request to `/api/v1/audit/*`.
"""

from __future__ import annotations

from app.db.session import reset_database
from app.services.api_keys import ApiKeyStore
from app.services.batch_audit import BatchAuditService
from app.services.pipeline import Pipeline
from app.services.proposal_store import ProposalStore
from app.services.rule_reviews import RuleReviewStore

_pipeline: Pipeline | None = None
_proposals: ProposalStore | None = None
_batches: BatchAuditService | None = None
_rule_reviews: RuleReviewStore | None = None
_api_keys: ApiKeyStore | None = None


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


def batches() -> BatchAuditService:
    global _batches
    if _batches is None:
        # `pipeline` is passed rather than imported inside the service so the two singletons stay
        # the same objects: a batch must audit against the catalog and rule store the rest of the
        # process is using, not against a second copy it built for itself.
        _batches = BatchAuditService(pipeline_factory=pipeline)
    return _batches


def rule_reviews() -> RuleReviewStore:
    global _rule_reviews
    if _rule_reviews is None:
        _rule_reviews = RuleReviewStore()
    return _rule_reviews


def api_keys() -> ApiKeyStore:
    """The store every partner request authenticates through.

    A singleton for the same reason the other three are: it holds no connection of its own, and one
    object per request would allocate for nothing. It is on the hot path — one call per
    authenticated request — which is what makes "no connection pool of its own" load-bearing rather
    than tidy: `get_database()` hands back the process's pool each time, so verification borrows a
    connection and returns it rather than opening one.
    """
    global _api_keys
    if _api_keys is None:
        _api_keys = ApiKeyStore()
    return _api_keys


def reset() -> None:
    """Drop the in-process singletons. For tests that change settings between cases.

    Does not touch the database: the engine has to be disposed with an `await`, and a sync helper
    that quietly left a connection pool open would leak one per test. Use `reset_async`.
    """
    global _pipeline, _proposals, _batches, _rule_reviews, _api_keys
    _pipeline = None
    _proposals = None
    _batches = None
    _rule_reviews = None
    _api_keys = None

    # The rate limiter's counters are process-wide state of exactly the same kind, and a test that
    # exhausted a budget must not hand it to the next one. Cleared here rather than in a fixture of
    # its own so there is one thing to call between tests.
    from app.api.ratelimit import limiter

    limiter().reset()


async def reset_async() -> None:
    """`reset()`, plus disposing the database engine. What the test suite and the lifespan use."""
    reset()
    await reset_database()
