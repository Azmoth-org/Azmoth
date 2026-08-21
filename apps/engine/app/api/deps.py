"""Shared, lazily built singletons.

The pipeline loads a 1 MB catalog, 260 kB of rule CSVs and hashes both, so it is built once per
process and not per request. It is built lazily rather than at import time so that `import app.main`
works — for an OpenAPI export, say — on a machine with no Soufflé binary.
"""

from __future__ import annotations

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
    """Drop both singletons. For tests that change settings between cases."""
    global _pipeline, _proposals
    _pipeline = None
    _proposals = None
