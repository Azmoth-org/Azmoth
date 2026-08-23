"""Paging and filtering the two list endpoints, and the one number that makes them honest.

`GET /api/v1/proposals` and `GET /api/v1/padnext/batch` are the two reads whose result set grows
without bound, and both now serve a page. The load-bearing claim in that is not `limit` — it is
`total`: a page that reports only its own length lets a `limit` silently become "how many records
exist", and a review queue that cannot state its own size is not a queue. So every test here that
pages also asserts on `total`, and the filtering tests assert that `total` moved *with* the filter
rather than staying at the table count.

**Where each layer is tested, and why the split.** The store and the batch service are driven
directly for the arithmetic — clamping, filter composition, `total` under a filter — because at that
level a failure names the query rather than the response. The HTTP tests then assert only what the
router adds: that a value outside the declared range is a `422` and never a clamped success, that
the envelope carries the four fields, and that the defaults are the ones the OpenAPI document
publishes. Duplicating the arithmetic over HTTP would buy nothing and cost a solve per assertion.

**Two pages never overlap, and that is a statement about the tie-break, not the offset.** Both
tables stamp `created_at` from the application clock (`utcnow`), so two rows written in the same
microsecond are possible; without a deterministic second sort key the two `SELECT`s behind two pages
could order that pair differently and the same row would appear on both pages, or on neither. The
disjointness assertions are what would fail if a tie-break were dropped.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import PADNEXT_EXAMPLES_DIR
from app.schemas import ProposalStatus
from app.schemas.batch import BatchJobStatus
from app.services.batch_audit import (
    DEFAULT_BATCH_LIST_LIMIT,
    MAX_BATCH_LIST_LIMIT,
    BatchAuditService,
)
from app.services.proposal_store import (
    DEFAULT_PROPOSAL_LIST_LIMIT,
    MAX_PROPOSAL_LIST_LIMIT,
)
from tests.conftest import solve_proposal
from tests.factories import make_proposal
from tests.test_batch_audit import PAYLOAD_NAME

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def example_payload() -> bytes:
    return (PADNEXT_EXAMPLES_DIR / PAYLOAD_NAME).read_bytes()


@pytest.fixture
def one_file(example_payload):
    """One readable delivery. Enough for every assertion here: these tests are about which rows a
    listing returns, and the per-file audit is `test_batch_audit.py`'s subject, not this module's.
    """
    return [("files", ("full_padx.xml", example_payload, "application/xml"))]


async def _seed(store, count: int, *, case_id: str = "ENC-1", minute_offset: int = 0) -> list[str]:
    """`count` proposals a minute apart, oldest first. Returns their ids in creation order.

    Explicit `created_at` rather than whatever the clock says, because every assertion below is
    about order and a test whose ordering depends on how fast the machine ran is not an assertion.
    """
    return [
        (
            await store.create_proposal(
                make_proposal(
                    case_id=case_id,
                    created_at=BASE + timedelta(minutes=minute_offset + index),
                )
            )
        ).proposal_id
        for index in range(count)
    ]


# ==========================================================================================
# proposals — the store
# ==========================================================================================


async def test_the_proposal_pages_partition_the_table_without_hiding_its_size(store):
    created = await _seed(store, 5)

    first = await store.list_proposals(limit=2, offset=0)
    second = await store.list_proposals(limit=2, offset=2)
    third = await store.list_proposals(limit=2, offset=4)

    assert (first.total, second.total, third.total) == (5, 5, 5), "total is the table, not the page"
    assert (first.limit, first.offset) == (2, 0)
    assert (len(first.items), len(second.items), len(third.items)) == (2, 2, 1)

    # Newest first, and the three pages reassemble the table exactly once.
    walked = [p.proposal_id for page in (first, second, third) for p in page.items]
    assert walked == list(reversed(created))
    assert len(set(walked)) == 5, "no row may appear on two pages"


async def test_an_offset_past_the_end_is_an_empty_page_and_not_an_error(store):
    """A UI that lands on page 9 of a table that shrank to 3 rows must render "nothing here",
    not a 500 and not the last page pretending to be the ninth."""
    await _seed(store, 3)

    page = await store.list_proposals(limit=10, offset=99)

    assert page.items == []
    assert (page.total, page.offset) == (3, 99), "the total still says what it could have shown"


async def test_the_proposal_total_counts_the_filtered_set_and_not_the_table(store):
    created = await _seed(store, 4)
    await store.approve_proposal(created[0], approved_by="Dr. B")
    await store.approve_proposal(created[1], approved_by="Dr. B")

    drafts = await store.list_proposals(status=ProposalStatus.DRAFT)
    approved = await store.list_proposals(status=ProposalStatus.APPROVED, limit=1)

    assert (drafts.total, len(drafts.items)) == (2, 2)
    # The point of the case: one row asked for, two matching, four in the table.
    assert (approved.total, len(approved.items)) == (2, 1)
    assert {p.status for p in approved.items} == {ProposalStatus.APPROVED}


async def test_filtering_by_case_id_composes_with_the_status_filter(store):
    """Both filters at once, because the bug this catches is a `where` clause that replaced the
    previous one instead of adding to it — which returns a plausible page and the wrong total."""
    wanted = await _seed(store, 2, case_id="ENC-WANTED")
    other = await _seed(store, 3, case_id="ENC-OTHER", minute_offset=10)
    await store.approve_proposal(wanted[0], approved_by="Dr. B")
    await store.approve_proposal(other[0], approved_by="Dr. B")

    by_case = await store.list_proposals(case_id="ENC-WANTED")
    both = await store.list_proposals(case_id="ENC-WANTED", status=ProposalStatus.APPROVED)

    assert (by_case.total, {p.case_id for p in by_case.items}) == (2, {"ENC-WANTED"})
    assert both.total == 1
    assert [p.proposal_id for p in both.items] == [wanted[0]]


async def test_a_case_id_that_matches_nothing_is_an_empty_page_with_a_zero_total(store):
    """Exact match, not a substring: `ENC` must not find `ENC-1`. Documented in the store, and
    asserted here because the cheap implementation of a filter box is a `LIKE`."""
    await _seed(store, 2, case_id="ENC-1")

    prefix = await store.list_proposals(case_id="ENC")
    blank = await store.list_proposals(case_id="   ")

    assert (prefix.total, prefix.items) == (0, [])
    assert blank.total == 2, "a cleared input box is no filter, not a search for the empty string"


async def test_the_proposal_listing_clamps_a_hostile_limit_rather_than_serving_it(store):
    """The router refuses these with a `422`; the store clamps. Both, on purpose — the store is
    also called from the suite and from any future non-HTTP caller, and a `limit=10**9` reaching
    the database from either direction would read the table into memory."""
    await _seed(store, 1)

    assert (await store.list_proposals(limit=10**9)).limit == MAX_PROPOSAL_LIST_LIMIT
    assert (await store.list_proposals(limit=0)).limit == 1
    assert (await store.list_proposals(offset=-5)).offset == 0
    assert (await store.list_proposals()).limit == DEFAULT_PROPOSAL_LIST_LIMIT


async def test_count_and_the_listing_total_agree_under_the_same_filters(store):
    """Two code paths answer "how many", and a dashboard that showed both would show them side by
    side. They must not be able to disagree."""
    created = await _seed(store, 3, case_id="ENC-A")
    await _seed(store, 2, case_id="ENC-B", minute_offset=10)
    await store.approve_proposal(created[0], approved_by="Dr. B")

    for kwargs in (
        {},
        {"status": ProposalStatus.DRAFT},
        {"status": ProposalStatus.APPROVED},
        {"case_id": "ENC-A"},
        {"case_id": "ENC-B", "status": ProposalStatus.DRAFT},
    ):
        assert await store.count(**kwargs) == (await store.list_proposals(**kwargs)).total, kwargs


# ==========================================================================================
# proposals — over HTTP
# ==========================================================================================


def test_the_proposal_listing_is_an_empty_envelope_rather_than_an_empty_array(client):
    """The shape is asserted whole, defaults included, because it is the contract a client codes
    against — and because it is what changed: this used to be `[]`."""
    assert client.get("/api/v1/proposals").json() == {
        "items": [],
        "total": 0,
        "limit": DEFAULT_PROPOSAL_LIST_LIMIT,
        "offset": 0,
    }


def test_the_proposal_listing_pages_over_http_and_reports_the_whole_total(client, manual_case):
    ids = [
        solve_proposal(client, manual_case(case))["proposal_id"]
        for case in ("case_001_knee", "case_002_cardiology", "case_003_dermatology")
    ]

    first = client.get("/api/v1/proposals", params={"limit": 2, "offset": 0}).json()
    second = client.get("/api/v1/proposals", params={"limit": 2, "offset": 2}).json()

    assert (first["total"], second["total"]) == (3, 3)
    assert (len(first["items"]), len(second["items"])) == (2, 1)
    assert {p["proposal_id"] for p in first["items"]}.isdisjoint(
        {p["proposal_id"] for p in second["items"]}
    )
    assert {p["proposal_id"] for page in (first, second) for p in page["items"]} == set(ids)


def test_the_proposal_listing_filters_by_case_id_over_http(client, manual_case):
    """`case_id` reaches the query rather than being accepted and ignored — the failure mode of a
    filter wired into the signature but not into the `where` clause.

    `case_id` is the caller's own handle for the encounter and travels on the `SolveRequest`, so it
    is set here rather than read off a case fixture: the bundled cases leave it null, which is
    exactly the value that would make this test pass without the filter doing anything.
    """
    knee = solve_proposal(client, manual_case("case_001_knee"), case_id="ENC-KNEE")
    other = solve_proposal(client, manual_case("case_002_cardiology"), case_id="ENC-HEART")
    unlabelled = solve_proposal(client, manual_case("case_003_dermatology"))

    body = client.get("/api/v1/proposals", params={"case_id": "ENC-KNEE"}).json()

    assert body["total"] == 1
    assert [p["proposal_id"] for p in body["items"]] == [knee["proposal_id"]]
    # Both of the others are excluded, and the null one is the interesting half: a filter built as
    # `case_id == None` in SQL matches nothing, which would look like a working filter here.
    assert client.get("/api/v1/proposals").json()["total"] == 3
    assert {other["case_id"], unlabelled["case_id"]} == {"ENC-HEART", None}


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=101", "limit=99999", "offset=-1", "limit=abc", "status=NOPE"],
)
def test_the_proposal_listing_refuses_a_parameter_outside_its_range(client, query):
    """A `422`, never a clamped success. A caller who asked for 500 rows and silently got 100 would
    read the page as the whole answer, which is the one failure `total` cannot rescue them from."""
    assert client.get(f"/api/v1/proposals?{query}").status_code == 422


def test_a_listed_proposal_still_carries_every_field_the_detail_view_has(client, manual_case):
    """The envelope is additive: `items[i]` is the same `Proposal` the endpoint served as a bare
    array element, rule-coverage counts and all. A listing model that dropped them would be the one
    place in this API where a draft appears without its coverage caveat."""
    created = solve_proposal(client, manual_case("case_001_knee"))

    listed = client.get("/api/v1/proposals").json()["items"][0]

    assert listed == created


def test_the_proposal_listing_is_newest_first_over_http(client, manual_case):
    """Reversed from what this endpoint used to serve, and asserted so the reversal is deliberate
    rather than incidental to the rewrite."""
    first = solve_proposal(client, manual_case("case_001_knee"))
    second = solve_proposal(client, manual_case("case_002_cardiology"))

    listed = [p["proposal_id"] for p in client.get("/api/v1/proposals").json()["items"]]

    assert listed == [second["proposal_id"], first["proposal_id"]]


# ==========================================================================================
# batches — the service
# ==========================================================================================


async def _seed_batches(service, count: int) -> list[str]:
    return [
        (await service.create_batch([(f"f{index}.xml", b"<x/>")]))[0].batch_id
        for index in range(count)
    ]


async def test_the_batch_listing_filters_by_status_and_recounts_the_total(database):
    """`PROCESSING` after a restart is "what is still running" and `FAILED` is "what the reaper
    closed" — the two questions an operator actually has. A `total` left at the table count would
    make either answer meaningless."""
    service = BatchAuditService(database)
    ids = await _seed_batches(service, 3)
    await service._complete(ids[0])
    await service._fail_quietly(ids[1], "boom")

    completed = await service.list_batches(status=BatchJobStatus.COMPLETED)
    failed = await service.list_batches(status=BatchJobStatus.FAILED)
    pending = await service.list_batches(status=BatchJobStatus.PENDING)

    assert (completed.total, [j.batch_id for j in completed.jobs]) == (1, [ids[0]])
    assert (failed.total, [j.batch_id for j in failed.jobs]) == (1, [ids[1]])
    assert (pending.total, [j.batch_id for j in pending.jobs]) == (1, [ids[2]])
    assert (await service.list_batches()).total == 3


async def test_created_after_is_inclusive_of_the_instant_it_names(database):
    """Inclusive, and pinned here because "after" reads exclusive to about half of everyone. A
    boundary row silently dropped is the kind of defect a date picker never surfaces."""
    service = BatchAuditService(database)
    ids = await _seed_batches(service, 3)
    stamps = {
        job.batch_id: job.created_at for job in (await service.list_batches()).jobs
    }
    middle = stamps[ids[1]]

    from_middle = await service.list_batches(created_after=middle)
    from_after_everything = await service.list_batches(
        created_after=max(stamps.values()) + timedelta(seconds=1)
    )

    assert {job.batch_id for job in from_middle.jobs} == {ids[1], ids[2]}
    assert from_middle.total == 2, "the total follows the filter"
    assert (from_after_everything.total, from_after_everything.jobs) == (0, [])


async def test_created_after_reads_a_naive_value_as_utc(database):
    """SQLite hands back the naive UTC string `utcnow` wrote and Postgres a `timestamptz`, so a
    value bound without normalisation compares a wall clock against an instant on one dialect and
    not the other. `as_utc` is what makes these two filters the same filter."""
    service = BatchAuditService(database)
    await _seed_batches(service, 2)
    stamp = min(job.created_at for job in (await service.list_batches()).jobs)

    aware = await service.list_batches(created_after=stamp)
    naive = await service.list_batches(created_after=stamp.replace(tzinfo=None))
    other_zone = await service.list_batches(
        created_after=stamp.astimezone(timezone(timedelta(hours=2)))
    )

    assert aware.total == naive.total == other_zone.total == 2


async def test_the_two_batch_filters_compose(database):
    service = BatchAuditService(database)
    ids = await _seed_batches(service, 3)
    await service._complete(ids[0])
    await service._complete(ids[2])
    stamps = {job.batch_id: job.created_at for job in (await service.list_batches()).jobs}

    both = await service.list_batches(
        status=BatchJobStatus.COMPLETED, created_after=stamps[ids[1]]
    )

    assert (both.total, [job.batch_id for job in both.jobs]) == (1, [ids[2]])


async def test_a_batch_filter_that_matches_nothing_is_an_empty_page(database):
    service = BatchAuditService(database)
    await _seed_batches(service, 2)

    listing = await service.list_batches(status=BatchJobStatus.PROCESSING)

    assert (listing.total, listing.jobs) == (0, [])
    assert (listing.limit, listing.offset) == (DEFAULT_BATCH_LIST_LIMIT, 0)


async def test_the_batch_page_ceiling_is_now_a_hundred(database):
    """Down from 500. Asserted against the constant *and* the literal, so lowering it again cannot
    pass by moving the constant the test reads."""
    service = BatchAuditService(database)
    await _seed_batches(service, 1)

    assert MAX_BATCH_LIST_LIMIT == 100 == MAX_PROPOSAL_LIST_LIMIT
    assert (await service.list_batches(limit=500)).limit == 100


# ==========================================================================================
# batches — over HTTP
# ==========================================================================================


def test_the_batch_listing_filters_by_status_over_http(client, one_file):
    """The `TestClient` runs the background task inside the request, so the batch is `COMPLETED`
    by the time the listing is read — see the note at the top of `test_batch_audit.py`."""
    accepted = client.post("/api/v1/padnext/batch", files=one_file).json()

    completed = client.get("/api/v1/padnext/batch", params={"status": "COMPLETED"}).json()
    processing = client.get("/api/v1/padnext/batch", params={"status": "PROCESSING"}).json()

    assert [job["batch_id"] for job in completed["jobs"]] == [accepted["batch_id"]]
    assert completed["total"] == 1
    assert (processing["jobs"], processing["total"]) == ([], 0)


def test_the_batch_listing_filters_by_created_after_over_http(client, one_file):
    accepted = client.post("/api/v1/padnext/batch", files=one_file).json()
    created_at = accepted["created_at"]

    inclusive = client.get("/api/v1/padnext/batch", params={"created_after": created_at}).json()
    later = client.get(
        "/api/v1/padnext/batch", params={"created_after": "2099-01-01T00:00:00Z"}
    ).json()

    assert [job["batch_id"] for job in inclusive["jobs"]] == [accepted["batch_id"]]
    assert (later["jobs"], later["total"]) == ([], 0)


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=101", "offset=-1", "status=NOPE", "created_after=yesterday"]
)
def test_the_batch_listing_refuses_a_parameter_outside_its_range(client, query):
    assert client.get(f"/api/v1/padnext/batch?{query}").status_code == 422
