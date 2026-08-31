"""`X-Organization-ID`: one practice cannot see or decide another's records.

Until `0006` an organisation was something the UI *showed*. The rail named it, the session carried
it, and no query filtered by it — the note on the `organization()` plugin in `apps/web/lib/auth.ts`
said so plainly: "the identity half of multi-tenancy landing before the authorisation half, not
multi-tenancy". This module is the tests for the other half.

Five claims, and each of them is a distinct way the boundary could be wrong.

**A request that names no organisation is refused.** `403 ORGANIZATION_REQUIRED`, on every endpoint
that touches a proposal or a batch. Not a default tenant, not an empty result: a default would be a
bug whose symptom appears months later as "Praxis B can see our drafts", and the whole point of
refusing is that a call site which forgot the header fails on its first request instead.

**What one practice writes, another cannot read.** The listing, the single read, the batch listing
and the batch read — all four filtered, and `total` counted under the same filter so a queue length
is a practice's own and not the table's.

**What one practice writes, another cannot decide.** Read scoping is decorative if approve, reject
and export are reachable by knowing an id, so those are asserted separately. Approving somebody
else's invoice draft is the worst thing this boundary prevents.

**Another practice's record is a `404`, never a `403`.** `403 this exists and is not yours` is an
oracle: a caller with a `prop_…` id learns whether it is real. `404` says only that this tenant has
no such proposal, which is true and is all they are entitled to know.

**A new endpoint cannot forget to scope.** The last test walks the application's route table and
asserts that every proposal and batch operation declares the dependency. That one exists because the
store's `organization_id` parameters default to `None` — see the note on `ProposalStore` — so the
guarantee that no HTTP path is unscoped is not a property of the store, it is this test.

The header is asserted rather than proven, exactly like `X-User-ID`; `app/api/tenancy.py` says at
length why that is worth enforcing anyway and where a verified token would go.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.api.tenancy import (
    MAX_ORGANIZATION_ID_LENGTH,
    ORGANIZATION_ID_HEADER,
    _sanitise,
)
from app.errors import ErrorCode
from tests.conftest import TEST_ORGANIZATION_ID

#: Two practices. Both shaped like Better Auth ids, so nothing here can come to depend on a tenant
#: being human-readable.
PRAXIS_A = "orgAa1Bb2Cc3Dd4Ee5Ff6Gg7Hh8Ii9Jj"
PRAXIS_B = "orgKk1Ll2Mm3Nn4Oo5Pp6Qq7Rr8Ss9Tt"

NOT_A_DELIVERY = b"<nonsense/>"


@pytest.fixture
def delivery_bytes():
    """One readable PADnext delivery, from the bundled synthetic example.

    Read here rather than reusing `tests/test_batch_audit.py`'s fixtures: importing another test
    module's fixtures couples two files that have nothing to do with each other, and what this one
    needs is simply "bytes the reader accepts".
    """
    from app.config import PADNEXT_EXAMPLES_DIR

    return (PADNEXT_EXAMPLES_DIR / "00004711_20260726_ADL_000001_padx.xml").read_bytes()


def _as(client: TestClient, organization_id: str):
    """A request-kwargs helper: `client.get(path, **_as(client, PRAXIS_A))`.

    The `client` fixture already sets `TEST_ORGANIZATION_ID` on every request, so a per-call header
    is what overrides it. Written as a helper rather than repeated inline because the thing every
    test in this file varies is exactly this one value.
    """
    del client
    return {"headers": {ORGANIZATION_ID_HEADER: organization_id}}


@pytest.fixture
def unscoped_client():
    """A client that sends **no** organisation header at all — the refusal case.

    Built here rather than by clearing a header on the shared `client`, because "the fixture sets it
    and this test unsets it" is a thing that silently stops working when the fixture changes.
    """
    from app.main import app

    deps.reset()
    with TestClient(app) as test_client:
        yield test_client
    deps.reset()


def _draft_for(client: TestClient, organization_id: str) -> str:
    response = client.post(
        "/api/v1/solve", json={"extraction": {}}, **_as(client, organization_id)
    )
    assert response.status_code == 200, response.text
    return response.json()["proposal_id"]


def _batch_for(client: TestClient, organization_id: str) -> str:
    response = client.post(
        "/api/v1/padnext/batch",
        files=[("files", ("one.xml", NOT_A_DELIVERY, "application/octet-stream"))],
        **_as(client, organization_id),
    )
    assert response.status_code == 202, response.text
    return response.json()["batch_id"]


# ==========================================================================================
# a request that names no organisation is refused
# ==========================================================================================


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("post", "/api/v1/solve", {"json": {"extraction": {}}}),
        ("get", "/api/v1/proposals", {}),
        ("get", "/api/v1/proposals/prop_whatever", {}),
        ("post", "/api/v1/proposals/prop_whatever/approve", {"json": {"approved_by": "Dr. B"}}),
        (
            "post",
            "/api/v1/proposals/prop_whatever/reject",
            {"json": {"rejected_by": "Dr. B", "reason": "nein"}},
        ),
        ("post", "/api/v1/proposals/prop_whatever/export", {"json": {"exported_by": "Dr. B"}}),
        ("get", "/api/v1/padnext/batch", {}),
        ("get", "/api/v1/padnext/batch/batch_whatever", {}),
        ("post", "/api/v1/padnext/batch/batch_whatever/export", {}),
    ],
)
def test_every_scoped_endpoint_refuses_a_request_with_no_organisation(
    unscoped_client, method, path, kwargs
):
    """`403`, and the refusal comes *before* the lookup — note the ids that do not exist.

    A `404` on `prop_whatever` would mean the endpoint had already gone to the database, which is
    the wrong order: the tenant is what decides whether the caller may ask the question at all.
    """
    response = getattr(unscoped_client, method)(path, **kwargs)

    assert response.status_code == 403, response.text
    body = response.json()
    assert body["error_code"] == ErrorCode.ORGANIZATION_REQUIRED
    assert body["details"]["header"] == ORGANIZATION_ID_HEADER
    # The message has to say what to send. A `403` whose body is "Forbidden" costs an afternoon.
    assert ORGANIZATION_ID_HEADER.lower() in body["message"].lower()


def test_the_batch_upload_refuses_before_reading_the_files(unscoped_client):
    """Separately from the table above, because this one is a multipart POST.

    It matters that the refusal happens without the upload being read into memory: the endpoint
    accepts up to 64 MB, and an unauthenticated caller must not be able to make the process buffer
    that to be told no.
    """
    response = unscoped_client.post(
        "/api/v1/padnext/batch",
        files=[("files", ("one.xml", NOT_A_DELIVERY, "application/octet-stream"))],
    )

    assert response.status_code == 403, response.text
    assert response.json()["error_code"] == ErrorCode.ORGANIZATION_REQUIRED


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_a_blank_header_is_the_same_as_no_header(unscoped_client, value):
    """A proxy that forwarded an unset variable sends `""`. That must be refused, not stored.

    Compose does exactly this with `"${VAR:-}"`, and a tenant whose id is the empty string would be
    a shared bucket that every misconfigured deployment wrote into.
    """
    response = unscoped_client.get(
        "/api/v1/proposals", headers={ORGANIZATION_ID_HEADER: value}
    )

    assert response.status_code == 403, response.text
    assert response.json()["error_code"] == ErrorCode.ORGANIZATION_REQUIRED


# ==========================================================================================
# health and the stateless audit are deliberately NOT scoped
# ==========================================================================================


def test_health_answers_without_an_organisation(unscoped_client):
    """The container healthcheck calls this. A tenant requirement here would report every container
    unhealthy forever — and there is nothing tenant-specific in the response to protect."""
    assert unscoped_client.get("/api/v1/health").status_code == 200


def test_the_single_file_audit_answers_without_an_organisation(unscoped_client, delivery_bytes):
    """`POST /padnext/audit` writes no row, so there is no record for a tenant to own.

    Gating it would be a lock on an empty room, and it would break the one endpoint a practice can
    reasonably call from a script.
    """
    response = unscoped_client.post(
        "/api/v1/padnext/audit",
        content=delivery_bytes,
        headers={"Content-Type": "application/xml"},
    )

    assert response.status_code == 200, response.text


# ==========================================================================================
# what one practice writes, another cannot read
# ==========================================================================================


def test_a_listing_shows_only_the_calling_practices_proposals(client):
    a_proposal = _draft_for(client, PRAXIS_A)
    _draft_for(client, PRAXIS_B)
    _draft_for(client, PRAXIS_B)

    listing = client.get("/api/v1/proposals", **_as(client, PRAXIS_A)).json()

    assert [item["proposal_id"] for item in listing["items"]] == [a_proposal]
    # `total` under the same filter, not the size of the table. A queue that reported three when the
    # practice has one would be a leak of how busy everybody else is.
    assert listing["total"] == 1


def test_a_practice_with_no_records_gets_an_empty_page_rather_than_everybody_elses(client):
    _draft_for(client, PRAXIS_A)

    listing = client.get("/api/v1/proposals", **_as(client, PRAXIS_B)).json()

    assert listing["items"] == []
    assert listing["total"] == 0


def test_reading_another_practices_proposal_is_a_404(client):
    proposal_id = _draft_for(client, PRAXIS_A)

    response = client.get(f"/api/v1/proposals/{proposal_id}", **_as(client, PRAXIS_B))

    assert response.status_code == 404, response.text


def test_a_batch_listing_shows_only_the_calling_practices_batches(client):
    a_batch = _batch_for(client, PRAXIS_A)
    _batch_for(client, PRAXIS_B)

    listing = client.get("/api/v1/padnext/batch", **_as(client, PRAXIS_A)).json()

    assert [job["batch_id"] for job in listing["jobs"]] == [a_batch]
    assert listing["total"] == 1


def test_reading_another_practices_batch_is_a_404(client):
    batch_id = _batch_for(client, PRAXIS_A)

    assert client.get(f"/api/v1/padnext/batch/{batch_id}", **_as(client, PRAXIS_A)).status_code == 200
    assert (
        client.get(f"/api/v1/padnext/batch/{batch_id}", **_as(client, PRAXIS_B)).status_code == 404
    )


def test_exporting_another_practices_batch_is_a_404_not_a_409(client, delivery_bytes):
    """The order of the two checks matters. `409 not completed` would confirm the batch exists.

    A batch that has finished is `409`-exportable or `200`-exportable depending on its status, and
    either answer tells a caller something about a record they may not see. The tenant filter is in
    the `WHERE`, so the status check never runs for a batch belonging to somebody else.
    """
    batch_id = client.post(
        "/api/v1/padnext/batch",
        files=[("files", ("one_padx.xml", delivery_bytes, "application/xml"))],
        **_as(client, PRAXIS_A),
    ).json()["batch_id"]

    response = client.post(
        f"/api/v1/padnext/batch/{batch_id}/export", **_as(client, PRAXIS_B)
    )

    assert response.status_code == 404, response.text


# ==========================================================================================
# what one practice writes, another cannot decide
# ==========================================================================================


def test_another_practice_cannot_approve_a_draft(client):
    """The write this whole boundary exists for. Read scoping is decoration without it."""
    proposal_id = _draft_for(client, PRAXIS_A)

    refused = client.post(
        f"/api/v1/proposals/{proposal_id}/approve",
        json={"approved_by": "Dr. Fremd"},
        **_as(client, PRAXIS_B),
    )

    assert refused.status_code == 404, refused.text
    # And the draft is untouched — a refused approval that had already written the status would be
    # the same bug with a `404` in front of it.
    owner_view = client.get(f"/api/v1/proposals/{proposal_id}", **_as(client, PRAXIS_A)).json()
    assert owner_view["status"] == "DRAFT"
    assert owner_view["approved_by"] is None


def test_another_practice_cannot_reject_a_draft(client):
    proposal_id = _draft_for(client, PRAXIS_A)

    refused = client.post(
        f"/api/v1/proposals/{proposal_id}/reject",
        json={"rejected_by": "Dr. Fremd", "reason": "gefällt mir nicht"},
        **_as(client, PRAXIS_B),
    )

    assert refused.status_code == 404, refused.text
    assert (
        client.get(f"/api/v1/proposals/{proposal_id}", **_as(client, PRAXIS_A)).json()["status"]
        == "DRAFT"
    )


def test_another_practice_cannot_export_an_approved_proposal(client):
    """Approved by its owner, then export attempted by a stranger.

    `EXPORTED` is terminal and reachable exactly once, so an export taken by the wrong practice does
    not merely leak the document — it consumes the owner's only chance to take it.
    """
    proposal_id = _draft_for(client, PRAXIS_A)
    approved = client.post(
        f"/api/v1/proposals/{proposal_id}/approve",
        json={"approved_by": "Dr. Eigen"},
        **_as(client, PRAXIS_A),
    )
    assert approved.status_code == 200, approved.text

    refused = client.post(
        f"/api/v1/proposals/{proposal_id}/export",
        json={"exported_by": "Dr. Fremd"},
        **_as(client, PRAXIS_B),
    )

    assert refused.status_code == 404, refused.text
    # Still exportable by the practice it belongs to.
    assert (
        client.post(
            f"/api/v1/proposals/{proposal_id}/export",
            json={"exported_by": "Dr. Eigen"},
            **_as(client, PRAXIS_A),
        ).status_code
        == 200
    )


# ==========================================================================================
# the organisation reaches the record
# ==========================================================================================


async def test_a_created_proposal_carries_its_organisation_in_a_queryable_column(database):
    """The column, not only the filter. "Every draft this practice produced" is a query on it."""
    from sqlalchemy import select

    from app.db.models import ProposalRecord
    from app.services.proposal_store import ProposalStore
    from tests.factories import make_proposal

    created = await ProposalStore(database).create_proposal(
        make_proposal(), organization_id=PRAXIS_A
    )

    async with database.session() as session:
        statement = select(ProposalRecord.organization_id).where(
            ProposalRecord.proposal_id == created.proposal_id
        )
        assert (await session.execute(statement)).scalar_one() == PRAXIS_A


async def test_a_batch_job_carries_its_organisation(database):
    from sqlalchemy import select

    from app.db.models import BatchJobRecord
    from app.services.batch_audit import BatchAuditService

    accepted, _ = await BatchAuditService(database=database).create_batch(
        [("one_padx.xml", b"<x/>")], organization_id=PRAXIS_A
    )

    async with database.session() as session:
        statement = select(BatchJobRecord.organization_id).where(
            BatchJobRecord.batch_id == accepted.batch_id
        )
        assert (await session.execute(statement)).scalar_one() == PRAXIS_A


async def test_a_legacy_row_with_no_organisation_belongs_to_nobody(database):
    """The nullability decision, asserted rather than only documented.

    A row written before `0006` carries `NULL`, and the filter is an equality — so it matches no
    tenant. That makes it unreachable rather than visible to everyone, which is the direction this
    ambiguity has to fail in. If somebody ever "fixes" the filter to admit `NULL`, this fails.
    """
    from app.services.proposal_store import ProposalStore
    from tests.factories import make_proposal

    store = ProposalStore(database)
    await store.create_proposal(make_proposal())  # no organisation: a legacy row

    assert (await store.list_proposals(organization_id=PRAXIS_A)).total == 0
    assert await store.count(organization_id=PRAXIS_A) == 0
    # Still there — unreachable, not deleted.
    assert await store.count() == 1


# ==========================================================================================
# a hostile or malformed value
# ==========================================================================================


def test_control_characters_are_stripped_from_the_organisation_id():
    """Same treatment as the actor header, and for the same reason: the value reaches a log."""
    assert _sanitise("org\nEVIL") == "orgEVIL"


def test_an_over_long_value_is_truncated_to_the_column_width():
    """Both columns are `String(256)`. Postgres raises on a longer value; SQLite stores it whole,
    and the two backends then disagree about which rows a filter matches."""
    assert len(_sanitise("o" * (MAX_ORGANIZATION_ID_LENGTH * 3))) == MAX_ORGANIZATION_ID_LENGTH


def test_a_forged_organisation_id_simply_matches_nothing(client):
    """The engine does not check that an organisation *exists*, and does not need to.

    `organization` is Better Auth's table in the web tier's half of the schema; querying it from here
    would couple the engine to a migrator it does not control. An id that names nothing matches no
    rows — an empty list, which is the correct answer to "show me the drafts of a practice with
    none" — and, crucially, is **not** a way to reach anybody else's.
    """
    _draft_for(client, PRAXIS_A)

    listing = client.get("/api/v1/proposals", **_as(client, "org-that-never-existed")).json()

    assert listing["items"] == []
    assert listing["total"] == 0


# ==========================================================================================
# it stays out of the published contract
# ==========================================================================================


def test_the_organisation_header_is_absent_from_the_openapi_document(client):
    """Transport between our two tiers, not part of the contract the frontend generates from.

    Declared as a `Request` dependency for exactly this reason — see `app/api/tenancy.py`. The
    assertion is here because the reason is easy to forget and the regression is silent.
    """
    document = client.get("/openapi.json")
    assert document.status_code == 200

    assert ORGANIZATION_ID_HEADER not in document.text.lower(), (
        "X-Organization-ID leaked into the OpenAPI document. It is transport between the web tier "
        "and the engine, not part of the contract @workspace/contracts generates types from — "
        "declare it with a Request dependency, never as a Header parameter."
    )


# ==========================================================================================
# a new endpoint cannot forget to scope
# ==========================================================================================


#: Operations that read or write tenant-owned rows and must therefore declare the dependency.
#:
#: Written as `(method, path)` rather than derived from the routers, because the point of the test
#: is to be a list somebody has to *think about*: adding an endpoint under `/proposals` or
#: `/padnext/batch` fails here until it is either added to this list and scoped, or deliberately
#: exempted below with a reason.
SCOPED_OPERATIONS = {
    ("POST", "/api/v1/solve"),
    ("GET", "/api/v1/proposals"),
    ("GET", "/api/v1/proposals/{proposal_id}"),
    ("POST", "/api/v1/proposals/{proposal_id}/approve"),
    ("POST", "/api/v1/proposals/{proposal_id}/reject"),
    ("POST", "/api/v1/proposals/{proposal_id}/export"),
    ("POST", "/api/v1/padnext/batch"),
    ("GET", "/api/v1/padnext/batch"),
    ("GET", "/api/v1/padnext/batch/{batch_id}"),
    ("POST", "/api/v1/padnext/batch/{batch_id}/export"),
    ("POST", "/api/v1/padnext/batch/{batch_id}/report.pdf"),
}

#: Endpoints under a scoped prefix that are deliberately unscoped, each with the reason.
UNSCOPED_BY_DESIGN = {
    # Stores nothing: bytes in, a report out. No record for a tenant to own.
    ("POST", "/api/v1/padnext/audit"),
    # The same audit, rendered as a PDF instead of JSON. Unscoped for the identical reason and no
    # other: it runs `padnext_audit` and writes nothing, so there is still no record with an owner.
    # It *reads* `X-Organization-ID` when the caller sends one, purely to print "Praxis / Konto" on
    # the document — a label, not a filter. Nothing is looked up by it and no data is withheld
    # without it, which is exactly why that is a header read and not the tenant dependency.
    ("POST", "/api/v1/padnext/audit.pdf"),
}


def _declared_operations() -> dict[tuple[str, str], bool]:
    """`{(method, full path): declares the tenant dependency}` for the three routers that have one.

    Read off `router.routes` rather than off `app.routes`, deliberately. Both describe the same
    endpoints, but the application's own route list is a structure FastAPI reshapes between versions
    — this one is currently wrapped in an internal `_IncludedRouter` whose contents are not part of
    any published API — while an `APIRouter`'s `routes` is a plain list of `APIRoute` and has been
    for years. A guard rail that silently stops finding any routes would pass forever while checking
    nothing, so it is built on the stable structure. `API_PREFIX` is imported rather than repeated,
    so a change to the mount point moves this with it.
    """
    from fastapi.routing import APIRoute

    from app.api import padnext, proposals, solve
    from app.api.tenancy import require_organization
    from app.main import API_PREFIX

    operations: dict[tuple[str, str], bool] = {}
    for module in (solve, proposals, padnext):
        for route in module.router.routes:
            if not isinstance(route, APIRoute):
                continue
            scoped = any(
                dependency.call is require_organization
                for dependency in route.dependant.dependencies
            )
            for method in route.methods:
                if method in {"HEAD", "OPTIONS"}:
                    continue
                operations[(method, API_PREFIX + route.path)] = scoped
    return operations


def test_every_endpoint_that_touches_a_record_declares_the_tenant_dependency():
    """The guard rail behind the store's `organization_id=None` default.

    `ProposalStore` and `BatchAuditService` treat `None` as unscoped, which is the right default for
    the hundred-odd tests that drive them against their own isolated database and the wrong one for
    an HTTP path. What makes that safe is that no HTTP path reaches them without a tenant — and that
    is not a property of the store. It is this test.
    """
    operations = _declared_operations()

    assert operations, (
        "no operations were found, so this test is checking nothing. The routers were probably "
        "restructured — see the note in `_declared_operations`."
    )

    unscoped = {key for key in SCOPED_OPERATIONS if not operations.get(key)}
    assert not unscoped, (
        f"these endpoints read or write tenant-owned rows and do not require X-Organization-ID: "
        f"{sorted(unscoped)}. Annotate the path function with `RequestOrganization` and pass it to "
        f"the store."
    )


def test_no_endpoint_under_a_scoped_prefix_is_unclassified():
    """The other direction: an endpoint added tomorrow has to be a decision, not an omission.

    Without this, a new `GET /proposals/{id}/history` would ship unscoped and nothing would notice —
    the test above only checks the operations somebody already listed. Failing here forces the
    author to either scope it or write down why it needs no tenant.
    """
    classified = SCOPED_OPERATIONS | UNSCOPED_BY_DESIGN

    unclassified = sorted(set(_declared_operations()) - classified)

    assert not unclassified, (
        f"{unclassified} are endpoints under a tenant-scoped router that nobody classified. Add "
        f"each to SCOPED_OPERATIONS and scope it, or to UNSCOPED_BY_DESIGN with the reason."
    )


def test_the_shared_client_fixture_sends_an_organisation():
    """A cheap assertion guarding an expensive mistake.

    If `TEST_ORGANIZATION_ID` ever stopped being sent, several hundred tests would start failing
    with `403` and the diagnosis would be "the tenancy change broke everything" rather than "the
    fixture stopped setting a header". Naming it here makes the first look land in the right place.
    """
    assert TEST_ORGANIZATION_ID
    assert _sanitise(TEST_ORGANIZATION_ID) == TEST_ORGANIZATION_ID
