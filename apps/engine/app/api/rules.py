"""The rule verification workflow — the internal tool that shrinks `unconfirmed`.

Most of this engine's constraint rules were extracted from the GOÄ's prose automatically. Under the
default policy an unverified one enforces nothing, which is part of why a PADnext audit puts so much
of an invoice in `unconfirmed`: that bucket is not an accusation, it is the boundary of what this
engine has been allowed to conclude. These three endpoints are how a billing expert moves it.

**The counts are not written down anywhere in this module, deliberately.** They move every time
somebody decides a rule, and a figure in a docstring is a claim nothing can keep true — the ones
that used to be here went stale and misstated the engine by an order of magnitude. `GET
/rules/coverage` is the answer, and it is computed.

    GET  /rules/review-queue        what is still undecided, with the evidence to decide it
    POST /rules/{rule_id}/review    a verdict, stored and merged immediately
    GET  /rules/coverage            where the effort has got to
    POST /rules/proposals           a pilot's report that a Ziffer has no rule at all

The fourth is a different kind of thing from the other three, and deliberately the simplest
endpoint in this module. It does not touch the pipeline, merges nothing and enforces nothing — it
writes one row to `rule_proposals` and returns. See `app.services.rule_proposals` and, on why this
is a new table rather than an overlay onto `rule_reviews`, the module docstring of `app.db.models`.

**The CSVs are never written.** A verdict goes into `rule_reviews` in Postgres and is merged onto
the parsed CSVs at load time. `data/rules/` is versioned source data whose changes need a reviewed
PR and a second approver (`CONTRIBUTING.md`), and an endpoint that edited it would route around
that on purpose-built infrastructure. See `app.services.rule_reviews`.

**A write refreshes the running engine.** `POST …/review` re-merges the pipeline's rule store
before it answers, so the coverage in the response is the coverage the very next solve will use.
That is per-process under multiple workers — stated in the service module rather than hidden, and
the failure mode is a rule enforced slightly later on one worker, never a wrong answer.

**`POST …/review` verifies its caller; the two reads above it do not.** Every other endpoint in
this router — and most of the engine's web-tier surface — trusts the Next.js proxy's `X-User-ID`
without checking it, which `app.api.identity` explains at length. This one write changes what every
subsequent audit enforces, for every practice, immediately, which is enough to be worth verifying
directly rather than trusting the network boundary alone — see `app.api.session_auth`.

These path functions are `async def` because they do database I/O. The one CPU-bound step — the
re-merge, which re-admits the whole rule table and rebuilds the three engines — goes to the
threadpool via
`run_in_threadpool`, the same shape `/solve` uses: the I/O is awaited on the loop, the work that
would block it is not.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Response
from starlette.concurrency import run_in_threadpool

from app.api.deps import pipeline, rule_proposals, rule_reviews
from app.api.identity import RequestActor
from app.api.ratelimit import RuleProposalRateLimit
from app.api.session_auth import VerifiedSession
from app.api.tenancy import RequestOrganization
from app.db.models import as_utc
from app.rules.rule_store import RuleReviewStatus
from app.schemas import RuleCoverage
from app.schemas.rule_proposals import RuleProposal, RuleProposalRequest
from app.schemas.rules import (
    ReviewableRule,
    RuleKind,
    RuleReviewQueue,
    RuleReviewRequest,
    RuleReviewResult,
)
from app.services import rule_reviews as review_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/rules", tags=["rules"])

#: How many queue entries one response may carry.
#:
#: The backlog can run to hundreds of rules, each with a full GOÄ sentence attached, so an unbounded
#: response is a megabyte of JSON to render a table a reviewer reads twenty rows of. The count that
#: matters — how much is actually left — is a field on the response, so paging never hides it.
DEFAULT_QUEUE_LIMIT = 100
MAX_QUEUE_LIMIT = 1000


def _not_found(rule_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": "rule_not_found",
            "message": (
                f"No rule {rule_id} in the loaded rule tables. Rule ids come from "
                "data/rules/*.csv — check GET /api/v1/rules/review-queue for the ones this engine "
                "actually loaded."
            ),
        },
    )


def _coverage() -> RuleCoverage:
    return pipeline().rule_coverage()


@router.get("/coverage", response_model=RuleCoverage)
async def rule_coverage() -> RuleCoverage:
    """How much of the rule set is verified, right now, reviews included.

    The same object every solve and audit carries, computed from the store the engine is actually
    holding — so a progress bar built from it cannot disagree with what the next audit enforces.
    """
    return _coverage()


@router.get("/review-queue", response_model=RuleReviewQueue)
async def review_queue(
    kind: RuleKind | None = Query(
        default=None,
        description=(
            "Show one rule type only. `zielleistung` first is the usual order of work: a wrong "
            "Zielleistung rule removes a position a practice was entitled to charge."
        ),
    ),
    limit: int = Query(default=DEFAULT_QUEUE_LIMIT, ge=1, le=MAX_QUEUE_LIMIT),
) -> RuleReviewQueue:
    """Rules that are unverified in the CSVs and that nobody has decided about yet.

    A rule leaves this queue when a review marks it `VERIFIED` or `REJECTED`. `PENDING` does not
    remove it, deliberately: a reviewer parking a rule they could not decide has not made it any
    safer, and a queue that hid parked rules would let the backlog quietly stop being the backlog.

    Sorted by rule type and then by id, so the list is stable across polls — a queue that reordered
    under a reviewer between reading a rule and clicking Verify would be worse than a slow one.
    """
    pipe = pipeline()
    records = await rule_reviews().records()

    #: Every constraint rule the store knows about, enforced or not, already carrying whatever
    #: review has been merged into it.
    undecided: list[ReviewableRule] = []
    for rule in sorted(
        pipe.rules.constraint_rules(), key=lambda r: (str(review_service.kind_of(r)), r.rule_id)
    ):
        if review_service.kind_of(rule) is None:  # pragma: no cover - analog rules never get here
            continue
        # Verified in the CSV, or already decided by a reviewer either way: not this queue's work.
        if rule.csv_verified or rule.review_status in {
            str(RuleReviewStatus.VERIFIED),
            str(RuleReviewStatus.REJECTED),
        }:
            continue
        undecided.append(review_service.describe(rule, records.get(rule.rule_id)))

    filtered = [r for r in undecided if kind is None or r.kind == kind]
    coverage = _coverage()

    return RuleReviewQueue(
        total_constraint_rules=coverage.total_constraint_rule_count,
        verified_rule_count=coverage.enforced_rule_count,
        review_verified_rule_count=coverage.review_verified_rule_count,
        rejected_rule_count=coverage.rejected_rule_count,
        # The whole backlog, not the page and not the filter — so "showing 100 of N" is honest.
        pending_rule_count=len(undecided),
        rules=filtered[:limit],
        truncated=len(filtered) > limit,
    )


@router.post("/{rule_id}/review", response_model=RuleReviewResult)
async def review_rule(
    rule_id: str,
    request: RuleReviewRequest,
    verified_user_id: VerifiedSession,
) -> RuleReviewResult:
    """Record a verdict on one rule and merge it into the running engine.

    `VERIFIED` makes the rule enforce exactly like a hand-curated one, which moves euros out of
    `unconfirmed` in every subsequent audit. `REJECTED` means a human read the machine-extracted
    rule and refused it: it never enforces again, not even under `UNVERIFIED_RULE_POLICY=block`,
    which does enforce merely-unverified rules. `PENDING` decides nothing and is a bookmark.

    Unlike the rest of this router, this endpoint verifies its caller — see
    `app.api.session_auth` — because a verdict here changes platform-wide rule enforcement for
    every practice, immediately. `verified_user_id` is the Better Auth user id the token names; the
    dependency is what actually gates the request, so an unused-looking parameter is doing real
    work.

    `reviewed_by` is required for a decision, for the same reason `approved_by` is on an approval:
    this changes what every future audit concludes about somebody's invoice. It is recorded
    verbatim from the request body, which lets the reviewer's display name (not just their Better
    Auth id) end up in `rule_reviews.reviewed_by`.

    The response carries the recomputed coverage, so a dashboard can update its progress bar from
    the same response rather than issuing a second request that could see a different world.
    """
    pipe = pipeline()
    if pipe.rules.rule_by_id(rule_id) is None:
        raise _not_found(rule_id)

    store = rule_reviews()
    record = await store.upsert(
        rule_id,
        status=request.status,
        reviewed_by=request.reviewed_by,
        review_notes=request.review_notes,
    )

    # Re-merge before answering, so the coverage below is what the next solve will actually use.
    # In a threadpool because re-parsing and re-admitting the whole rule table and rebuilding the
    # three engines
    # is CPU-bound, and it must not stall the loop for every other request in flight.
    await run_in_threadpool(pipe.apply_rule_reviews, await store.statuses())

    merged = pipe.rules.rule_by_id(rule_id)
    if merged is None or review_service.kind_of(merged) is None:  # pragma: no cover - defensive
        raise _not_found(rule_id)

    log.info("rule %s marked %s by %s", rule_id, request.status, request.reviewed_by or "-")
    return RuleReviewResult(
        rule=review_service.describe(merged, record),
        coverage=_coverage(),
    )


@router.post("/proposals", response_model=RuleProposal, status_code=201)
async def propose_rule(
    request: RuleProposalRequest,
    response: Response,
    organization: RequestOrganization,
    actor: RequestActor,
    limit: RuleProposalRateLimit,
) -> RuleProposal:
    """Record that a pilot hit a Ziffer this engine has no rule for at all.

    The button on an audit report that opens this dialog is `Regel fehlt? Ziffer melden`. Unlike
    every other write in this router, nothing here is verified against the catalog or the rule
    tables — a Ziffer that does not exist is itself a data point, and refusing the write would throw
    the report away over the one thing this endpoint cannot check offline (see `RuleProposalRecord`).

    Scoped to the caller's organisation and rate-limited per organisation — see
    `app.api.ratelimit.limit_rule_proposal` — because this is a browser-session endpoint with no
    API key to count against.
    """
    response.headers.update(limit.headers())
    record = await rule_proposals().create(
        ziffer=request.ziffer,
        context=request.context,
        receipt_hash=request.receipt_hash,
        organization_id=organization,
        created_by=actor,
    )
    log.info("rule proposal for ziffer %s reported by %s", record.ziffer, actor)
    return RuleProposal(
        id=str(record.id),
        ziffer=record.ziffer,
        context=record.context,
        receipt_hash=record.receipt_hash,
        created_at=as_utc(record.created_at),
    )
