"""The commercial API: the key, the limit, the two audit paths, and the report.

What this file is actually protecting is a boundary rather than a feature. `/api/v1/audit/*` is the
first surface in this engine that a caller outside our own network reaches directly, so the
properties that matter are the ones the web tier used to provide for free:

* a request without a valid key gets nothing,
* a key names its own organisation and the caller cannot name a different one,
* a runaway integration cannot spend the whole service,
* a PDF, a JSON body or somebody's holiday photos are refused with a sentence that says what to
  send instead, before anything expensive happens.

The audit *verdicts* are not retested here. They belong to `test_padnext.py` and
`test_batch_audit.py`, and duplicating them would produce a second set of expected euro figures to
keep in step with the first. What is asserted instead is that this path reaches the *same* verdicts:
the report `POST /audit/single` returns for the bundled nine-error delivery is compared field for
field against the one `POST /padnext/audit` returns for the same bytes.

**The background work runs for real.** Starlette's `TestClient` completes the ASGI cycle before
returning, and `BackgroundTasks` are part of that cycle, so `client.post("/audit/bulk")` comes back
only once the drain has finished the job. That makes the bulk assertions a synchronous run of the
real queue against the real store — better than a mock, because it exercises the claim, the
threadpool hand-off, the JSON round trip and the archive deletion, all of which a mock would skip.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.api.apikeys import API_KEY_HEADER
from app.api.tenancy import ORGANIZATION_ID_HEADER
from app.config import PADNEXT_EXAMPLES_DIR, get_settings
from app.services.api_keys import KEY_PREFIX, TOKEN_LENGTH, split_token

from tests.conftest import TEST_ORGANIZATION_ID

#: The hand-written delivery with nine deliberate errors, one per position. The engine's own
#: benchmark file — see `docs/audit/ENGINE_STATE_OF_UNION.md` part 1 — so a report over it is
#: something a reader can check against a document rather than against another assertion.
NINE_ERROR_XML = PADNEXT_EXAMPLES_DIR / "00004711_20260726_ADL_000001_padx.xml"

#: A second practice, for the tenancy assertions. Shaped like a Better Auth id for the same reason
#: `TEST_ORGANIZATION_ID` is.
OTHER_ORGANIZATION_ID = "orgZq4Wm7Bn2Cx9Dv6Fk1Ht3Js5Lp8R"


# ------------------------------------------------------------------------------------------
# fixtures
# ------------------------------------------------------------------------------------------


@pytest.fixture
def delivery() -> bytes:
    return NINE_ERROR_XML.read_bytes()


def mint(client: TestClient, *, organization_id: str = TEST_ORGANIZATION_ID, name: str = "") -> str:
    """Issue a key through the real endpoint and return the token.

    Through the endpoint rather than by inserting a row, deliberately: the token a test
    authenticates with is then one that was produced by the code a customer's key comes from, so a
    change that broke minting could not be hidden by a fixture that built its own.
    """
    response = client.post(
        "/api/v1/settings/api-keys",
        json={"name": name},
        headers={ORGANIZATION_ID_HEADER: organization_id},
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


@pytest.fixture
def token(client: TestClient) -> str:
    return mint(client, name="Test-Integration")


def auth(token: str) -> dict[str, str]:
    return {API_KEY_HEADER: token}


def zip_of(files: dict[str, bytes]) -> bytes:
    """A ZIP built in memory. `{name: content}` — the names are the paths inside the archive."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


# ==========================================================================================
# 1. the key
# ==========================================================================================


def test_a_minted_key_is_returned_once_and_never_again(client):
    """The storage decision, asserted as a contract rather than trusted as a comment."""
    created = client.post(
        "/api/v1/settings/api-keys", json={"name": "PVS-Export nächtlich"}
    )
    assert created.status_code == 201, created.text
    body = created.json()

    token = body["token"]
    assert token.startswith(KEY_PREFIX)
    assert len(token) == TOKEN_LENGTH
    assert body["key_id"] == split_token(token)
    assert body["organization_id"] == TEST_ORGANIZATION_ID
    assert body["name"] == "PVS-Export nächtlich"

    listed = client.get("/api/v1/settings/api-keys")
    assert listed.status_code == 200, listed.text
    keys = listed.json()["keys"]
    assert [entry["key_id"] for entry in keys] == [body["key_id"]]
    # The secret is not merely absent from this response; there is no field it could live in.
    assert "token" not in keys[0]
    assert token not in listed.text


async def test_the_token_is_not_stored_anywhere_in_the_row(client):
    """A database dump must not be a set of credentials. This is that claim, checked.

    `async def` rather than driving a loop by hand: `pytest.ini` sets `asyncio_mode = auto`, and a
    `run_until_complete` inside a synchronous test would take the loop the `TestClient` is already
    using — which is how a transaction ends up interleaved with somebody else's.
    """
    from sqlalchemy import select

    from app.db.models import ApiKeyRecord
    from app.db.session import get_database

    token = mint(client)

    async with get_database().session() as session:
        records = (await session.execute(select(ApiKeyRecord))).scalars().all()
        rows = [
            {column: str(getattr(record, column)) for column in record.__table__.c.keys()}
            for record in records
        ]

    assert rows, "the key that was just minted has to be in there somewhere"
    for row in rows:
        assert token not in json.dumps(row)
        assert row["key_id"] in token, "the public half is the only part stored in the clear"


def test_a_second_mint_is_a_second_live_key_not_the_same_one(client, delivery):
    """Rotation: mint, deploy, revoke. Both keys work until the old one is revoked."""
    first, second = mint(client, name="alt"), mint(client, name="neu")
    assert first != second

    for token in (first, second):
        response = client.post(
            "/api/v1/audit/single", content=delivery, headers=auth(token)
        )
        assert response.status_code == 200, response.text


def test_a_revoked_key_stops_working_and_stays_in_the_listing(client, delivery):
    token = mint(client)
    key_id = split_token(token)

    assert client.post("/api/v1/audit/single", content=delivery, headers=auth(token)).status_code == 200

    revoked = client.delete(f"/api/v1/settings/api-keys/{key_id}")
    assert revoked.status_code == 200, revoked.text
    assert revoked.json() == {"key_id": key_id, "revoked": True}

    refused = client.post("/api/v1/audit/single", content=delivery, headers=auth(token))
    assert refused.status_code == 401
    assert refused.json()["error_code"] == "API_KEY_INVALID"

    # Still listed, with a timestamp: "revoked on the 3rd" and "never existed" are different
    # answers to the question somebody asks when an integration stops working.
    entry = client.get("/api/v1/settings/api-keys").json()["keys"][0]
    assert entry["key_id"] == key_id
    assert entry["revoked_at"] is not None


def test_revoking_is_idempotent_and_scoped_to_the_practice(client):
    token = mint(client)
    key_id = split_token(token)

    assert client.delete(f"/api/v1/settings/api-keys/{key_id}").status_code == 200
    assert client.delete(f"/api/v1/settings/api-keys/{key_id}").status_code == 200

    # Another practice cannot revoke it, and is told the key does not exist rather than that it is
    # not theirs — otherwise the endpoint enumerates issued key ids one guess at a time.
    foreign = client.delete(
        f"/api/v1/settings/api-keys/{key_id}",
        headers={ORGANIZATION_ID_HEADER: OTHER_ORGANIZATION_ID},
    )
    assert foreign.status_code == 404
    assert foreign.json()["error_code"] == "API_KEY_NOT_FOUND"


def test_minting_needs_a_session_not_a_key(client):
    """The chicken and egg, made explicit: this endpoint cannot be behind the credential it issues."""
    from app.main import app

    deps.reset()
    with TestClient(app) as bare:
        response = bare.post("/api/v1/settings/api-keys", json={"name": "x"})
    deps.reset()

    assert response.status_code == 403
    assert response.json()["error_code"] == "ORGANIZATION_REQUIRED"


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({}, "API_KEY_REQUIRED"),
        ({API_KEY_HEADER: ""}, "API_KEY_REQUIRED"),
        ({API_KEY_HEADER: "   "}, "API_KEY_REQUIRED"),
        ({API_KEY_HEADER: "nonsense"}, "API_KEY_INVALID"),
        ({API_KEY_HEADER: f"{KEY_PREFIX}deadbeefcafe_" + "0" * 48}, "API_KEY_INVALID"),
    ],
)
def test_the_partner_surface_refuses_a_request_without_a_valid_key(
    client, delivery, headers, expected
):
    response = client.post("/api/v1/audit/single", content=delivery, headers=headers)
    assert response.status_code == 401, response.text
    assert response.json()["error_code"] == expected


def test_a_well_formed_token_with_the_wrong_secret_is_indistinguishable_from_an_unknown_one(
    client, delivery
):
    """Three failures, one answer. Anything else is an oracle.

    A caller who could tell "unknown key" from "wrong secret" could confirm that a `key_id` has
    been issued without holding its token, one guess at a time.
    """
    token = mint(client)
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")

    unknown = client.post(
        "/api/v1/audit/single",
        content=delivery,
        headers=auth(f"{KEY_PREFIX}aaaaaaaaaaaa_" + "b" * 48),
    )
    wrong_secret = client.post("/api/v1/audit/single", content=delivery, headers=auth(tampered))

    assert unknown.status_code == wrong_secret.status_code == 401
    assert unknown.json()["error_code"] == wrong_secret.json()["error_code"] == "API_KEY_INVALID"
    assert unknown.json()["message"] == wrong_secret.json()["message"]


def test_a_key_carries_its_own_organisation_and_no_header_can_change_it(client, delivery):
    """The security property the whole partner surface rests on.

    The request *also* carries `X-Organization-ID` — the `client` fixture sets it on everything —
    and naming a different practice in it must change nothing, because the partner path does not
    read that header at all.
    """
    token = mint(client, organization_id=OTHER_ORGANIZATION_ID)

    accepted = client.post(
        "/api/v1/audit/bulk",
        files={"file": ("x.zip", zip_of({"a_padx.xml": NINE_ERROR_XML.read_bytes()}), "application/zip")},
        headers=auth(token),
    )
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["batch_id"]

    # Readable with the key that created it, whatever the tenancy header says.
    mine = client.get(
        f"/api/v1/audit/bulk/{job_id}",
        headers={**auth(token), ORGANIZATION_ID_HEADER: TEST_ORGANIZATION_ID},
    )
    assert mine.status_code == 200, mine.text

    # And invisible to the other practice's key — as a 404, not a 403.
    theirs = client.get(f"/api/v1/audit/bulk/{job_id}", headers=auth(mint(client)))
    assert theirs.status_code == 404
    assert theirs.json()["error_code"] == "AUDIT_JOB_NOT_FOUND"


# ==========================================================================================
# 2. the single audit
# ==========================================================================================


def test_the_nine_error_delivery_is_audited_and_answers_200(client, token, delivery):
    """`200` with findings, not a 4xx. The status describes the API call, not the invoice."""
    response = client.post("/api/v1/audit/single", content=delivery, headers=auth(token))
    assert response.status_code == 200, response.text

    report = response.json()
    assert len(report["positions"]) == 9, "one position per deliberate error in the fixture"
    assert report["findings"], "a file with nine planted errors must produce findings"
    assert report["receipt_hash"]
    assert report["catalog_version"]

    # The three buckets reconcile, which is the arithmetic the whole product rests on.
    from decimal import Decimal

    bucketed = (
        Decimal(report["confirmed_fine_eur"])
        + Decimal(report["confirmed_wrong_eur"])
        + Decimal(report["unconfirmed_eur"])
    )
    assert abs(bucketed - Decimal(report["claimed_total_eur"])) <= Decimal("0.01")


def test_the_partner_path_reaches_the_same_verdict_as_the_web_tier(client, token, delivery):
    """The one thing that must never diverge between the two surfaces.

    Not "both produce a report" but "both produce *this* report": every field is compared, so a
    change that made the partner path audit under a different policy, catalog or rule set would
    fail here rather than being discovered by a customer comparing two screens.
    """
    partner = client.post("/api/v1/audit/single", content=delivery, headers=auth(token))
    internal = client.post("/api/v1/padnext/audit", content=delivery)

    assert partner.status_code == internal.status_code == 200
    left, right = partner.json(), internal.json()

    # Timings differ run to run and say nothing about the verdict.
    for key in ("solve_time_ms", "total_time_ms"):
        left.pop(key, None)
        right.pop(key, None)

    assert left == right


def test_multipart_and_a_raw_body_are_the_same_request(client, token, delivery):
    """Both kinds of integrator exist; refusing one would be an arbitrary tax on half of them."""
    raw = client.post("/api/v1/audit/single", content=delivery, headers=auth(token))
    form = client.post(
        "/api/v1/audit/single",
        files={"file": ("00004711_20260726_ADL_000001_padx.xml", delivery, "application/xml")},
        headers=auth(token),
    )

    assert raw.status_code == form.status_code == 200, form.text
    assert raw.json()["receipt_hash"] == form.json()["receipt_hash"]
    # The filename is metadata and is echoed, so the two do differ in exactly one field.
    assert form.json()["source_name"].endswith("_padx.xml")


def test_a_padx_container_is_accepted_as_a_single_delivery(client, token):
    """A `.padx` is a ZIP, and a ZIP is not automatically a bulk upload."""
    container = (PADNEXT_EXAMPLES_DIR / "00004711_20260726_ADL_000001.padx").read_bytes()
    response = client.post("/api/v1/audit/single", content=container, headers=auth(token))
    assert response.status_code == 200, response.text
    assert response.json()["positions"]


@pytest.mark.parametrize(
    ("body", "detected"),
    [
        (b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj", "pdf"),
        (b'{"extraction": {"patient": {"age": 50}}}', "json"),
        (b"[1, 2, 3]", "json"),
        (b"Sehr geehrte Damen und Herren,", "unknown"),
    ],
)
def test_a_body_that_is_not_padnext_is_refused_with_400_naming_what_it_was(
    client, token, body, detected
):
    """The constraint the brief states outright, and the reason it is worth a code of its own.

    A PDF that reached the XML parser would come back as "not well-formed at line 1, column 1",
    which sends an integrator looking at our parser. Naming the format sends them to their export
    step, which is where the problem is.
    """
    response = client.post("/api/v1/audit/single", content=body, headers=auth(token))
    assert response.status_code == 400, response.text
    envelope = response.json()
    assert envelope["error_code"] == "UNSUPPORTED_INPUT_FORMAT"
    assert envelope["details"]["detected"] == detected
    assert envelope["details"]["accepted"] == ["xml", "zip"]


def test_an_empty_body_says_so_rather_than_naming_a_format(client, token):
    response = client.post("/api/v1/audit/single", content=b"", headers=auth(token))
    assert response.status_code == 400
    assert response.json()["error_code"] == "EMPTY_REQUEST_BODY"


def test_a_delivery_above_the_single_file_limit_is_refused_at_the_perimeter(client, token):
    """413 from the middleware, on the header alone, before the body is read."""
    limit = get_settings().max_single_xml_bytes
    response = client.post(
        "/api/v1/audit/single",
        content=b"",
        headers={
            **auth(token),
            "Content-Length": str(limit + 1),
            "Content-Type": "application/xml",
        },
    )
    assert response.status_code == 413, response.text
    body = response.json()
    assert body["error_code"] == "REQUEST_TOO_LARGE"
    assert body["details"]["max_bytes"] == limit
    assert "Rejected before reading the body" in body["message"]


def test_the_perimeter_limit_is_per_path_not_global(client):
    """The bulk endpoint's ceiling is higher than the single one's, and both differ from the global.

    Without the per-path override a 50 MB archive would be refused by a 32 MiB perimeter that the
    bulk endpoint's own documented limit says should accept it — a contradiction a caller would
    discover in production.
    """
    from app.core.limits import RequestSizeLimitMiddleware

    settings = get_settings()
    middleware = RequestSizeLimitMiddleware(
        None,
        max_bytes=settings.max_request_bytes,
        overrides=[
            ("/api/v1/audit/bulk", settings.max_bulk_zip_bytes),
            ("/api/v1/audit/single", settings.max_single_xml_bytes),
        ],
    )
    assert middleware.limit_for("/api/v1/audit/bulk") == settings.max_bulk_zip_bytes
    assert middleware.limit_for("/api/v1/audit/single") == settings.max_single_xml_bytes
    assert middleware.limit_for("/api/v1/padnext/audit") == settings.max_request_bytes
    assert settings.max_single_xml_bytes < settings.max_request_bytes < settings.max_bulk_zip_bytes


# ==========================================================================================
# 3. the bulk audit
# ==========================================================================================


def test_a_zip_of_three_deliveries_is_queued_and_completed(client, token, delivery):
    """The whole asynchronous path, end to end, against the real queue."""
    archive = zip_of(
        {
            "praxis/rechnung_1_padx.xml": delivery,
            "praxis/rechnung_2_padx.xml": delivery,
            "rechnung_3_padx.xml": delivery,
            # Not deliveries. Skipped rather than refused, so a partner's README does not cost them
            # their upload.
            "README.txt": b"nicht zu pruefen",
            "__MACOSX/._rechnung_1_padx.xml": b"junk",
        }
    )

    accepted = client.post(
        "/api/v1/audit/bulk",
        files={"file": ("upload.zip", archive, "application/zip")},
        headers=auth(token),
    )
    assert accepted.status_code == 202, accepted.text
    body = accepted.json()
    assert body["status"] == "PENDING"
    assert body["file_count"] == 3, "the three .xml members, and neither of the other two"
    job_id = body["batch_id"]

    # `TestClient` runs background tasks inside the request cycle, so the drain has already
    # finished by the time the 202 came back.
    status = client.get(f"/api/v1/audit/bulk/{job_id}", headers=auth(token))
    assert status.status_code == 200, status.text
    job = status.json()

    assert job["status"] == "COMPLETED"
    assert job["file_count"] == 3
    assert job["completed_file_count"] == 3
    assert job["failed_file_count"] == 0
    assert sorted(entry["filename"] for entry in job["files"]) == [
        "praxis/rechnung_1_padx.xml",
        "praxis/rechnung_2_padx.xml",
        "rechnung_3_padx.xml",
    ]

    summary = job["aggregate_summary"]
    assert summary["completed_file_count"] == 3
    # Three copies of one delivery: the roll-up is exactly three times one report.
    from decimal import Decimal

    single = client.post("/api/v1/audit/single", content=delivery, headers=auth(token)).json()
    assert Decimal(summary["claimed_total_eur"]) == 3 * Decimal(single["claimed_total_eur"])
    assert Decimal(summary["confirmed_wrong_eur"]) == 3 * Decimal(single["confirmed_wrong_eur"])

    # And every delivery carries the same report the single endpoint produces for those bytes.
    for entry in job["files"]:
        assert entry["report"]["receipt_hash"] == single["receipt_hash"]


def test_the_archive_is_written_to_disk_and_removed_once_the_job_is_terminal(client, token, delivery):
    """Durability, then retention. Both halves of the storage decision in one test."""
    settings = get_settings()
    root = Path(settings.bulk_upload_dir)

    accepted = client.post(
        "/api/v1/audit/bulk",
        files={"file": ("upload.zip", zip_of({"a_padx.xml": delivery}), "application/zip")},
        headers=auth(token),
    )
    job_id = accepted.json()["batch_id"]

    assert client.get(f"/api/v1/audit/bulk/{job_id}", headers=auth(token)).json()["status"] == "COMPLETED"
    # Nothing left under the organisation's directory: a billing delivery is kept for exactly as
    # long as it takes to produce the report from it.
    assert list(root.rglob("upload.zip")) == []


def test_a_delivery_that_cannot_be_read_fails_its_own_row_and_not_the_job(client, token, delivery):
    """One corrupt member out of three is a line in the report, not a failed upload."""
    archive = zip_of(
        {
            "gut_1_padx.xml": delivery,
            "kaputt_padx.xml": b"<rechnungen>unclosed",
            "gut_2_padx.xml": delivery,
        }
    )
    accepted = client.post(
        "/api/v1/audit/bulk",
        files={"file": ("upload.zip", archive, "application/zip")},
        headers=auth(token),
    )
    job = client.get(
        f"/api/v1/audit/bulk/{accepted.json()['batch_id']}", headers=auth(token)
    ).json()

    assert job["status"] == "COMPLETED", "the run completed; one delivery did not"
    assert job["completed_file_count"] == 2
    assert job["failed_file_count"] == 1
    failed = [entry for entry in job["files"] if entry["status"] == "FAILED"]
    assert len(failed) == 1
    assert failed[0]["filename"] == "kaputt_padx.xml"
    assert failed[0]["error_message"], "a failure must name itself"
    assert failed[0]["report"] is None


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        (b"%PDF-1.7\n", 400, "UNSUPPORTED_INPUT_FORMAT"),
        (b"<rechnungen/>", 400, "UNSUPPORTED_INPUT_FORMAT"),
        (b"PK\x03\x04 and then nothing that is a zip", 400, "ARCHIVE_UNREADABLE"),
    ],
)
def test_a_bulk_upload_that_is_not_a_usable_archive_is_refused_before_a_job_exists(
    client, token, payload, status, code
):
    """A 400 on the upload, not a job the caller polls for thirty seconds before it fails."""
    before = client.get("/api/v1/audit/bulk", headers=auth(token)).json()["total"]

    response = client.post(
        "/api/v1/audit/bulk",
        files={"file": ("upload.zip", payload, "application/zip")},
        headers=auth(token),
    )
    assert response.status_code == status, response.text
    assert response.json()["error_code"] == code

    after = client.get("/api/v1/audit/bulk", headers=auth(token)).json()["total"]
    assert after == before, "a refused upload must leave no job behind"


def test_an_archive_of_pdfs_is_refused_with_a_sentence_that_says_what_to_send(client, token):
    """The likeliest first mistake: zipping the practice's invoice PDFs."""
    response = client.post(
        "/api/v1/audit/bulk",
        files={
            "file": (
                "upload.zip",
                zip_of({"rechnung_1.pdf": b"%PDF-1.7", "rechnung_2.pdf": b"%PDF-1.7"}),
                "application/zip",
            )
        },
        headers=auth(token),
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error_code"] == "ARCHIVE_HAS_NO_DELIVERIES"
    assert ".padx" in body["message"]


def test_the_listing_makes_a_job_reachable_after_its_id_is_lost(client, token, delivery):
    archive = zip_of({"a_padx.xml": delivery})
    ids = [
        client.post(
            "/api/v1/audit/bulk",
            files={"file": ("upload.zip", archive, "application/zip")},
            headers=auth(token),
        ).json()["batch_id"]
        for _ in range(2)
    ]

    listed = client.get("/api/v1/audit/bulk", headers=auth(token)).json()
    assert listed["total"] == 2
    assert {entry["batch_id"] for entry in listed["jobs"]} == set(ids)
    # A listing row carries the roll-up but not the per-delivery reports.
    assert all("files" not in entry for entry in listed["jobs"])
    assert all(entry["aggregate_summary"] is not None for entry in listed["jobs"])


# ==========================================================================================
# 4. the rate limit
# ==========================================================================================


@pytest.fixture
def tight_limits(monkeypatch):
    """Two requests a minute and one bulk upload an hour, so a test can actually reach the ceiling.

    The environment is set and `get_settings` is uncached, then both are undone — the limiter reads
    the settings per request, so nothing has to be rebuilt in between.
    """
    monkeypatch.setenv("RATE_LIMIT_SINGLE_PER_MINUTE", "2")
    monkeypatch.setenv("RATE_LIMIT_BULK_PER_HOUR", "1")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


def test_the_single_limit_refuses_the_request_after_the_budget_and_says_when_to_retry(
    client, token, delivery, tight_limits
):
    for _ in range(2):
        allowed = client.post("/api/v1/audit/single", content=delivery, headers=auth(token))
        assert allowed.status_code == 200, allowed.text
        assert allowed.headers["X-RateLimit-Limit"] == "2"

    refused = client.post("/api/v1/audit/single", content=delivery, headers=auth(token))
    assert refused.status_code == 429, refused.text
    body = refused.json()
    assert body["error_code"] == "RATE_LIMIT_EXCEEDED"
    assert body["details"]["limit"] == 2
    assert body["details"]["window_seconds"] == 60
    # Both the body field and the standard header, because a proxy honours one and a browser the
    # other.
    assert body["retry_after"] >= 1
    assert refused.headers["Retry-After"] == str(body["retry_after"])


def test_the_remaining_budget_is_published_on_the_way_up_not_only_on_the_refusal(
    client, token, delivery, tight_limits
):
    """A client that can see it has one request left can slow down before it is refused."""
    first = client.post("/api/v1/audit/single", content=delivery, headers=auth(token))
    second = client.post("/api/v1/audit/single", content=delivery, headers=auth(token))
    assert first.headers["X-RateLimit-Remaining"] == "1"
    assert second.headers["X-RateLimit-Remaining"] == "0"


def test_the_budget_is_per_key_so_one_runaway_integration_cannot_spend_anothers(
    client, delivery, tight_limits
):
    first, second = mint(client, name="a"), mint(client, name="b")
    for _ in range(2):
        assert client.post("/api/v1/audit/single", content=delivery, headers=auth(first)).status_code == 200
    assert client.post("/api/v1/audit/single", content=delivery, headers=auth(first)).status_code == 429

    assert client.post("/api/v1/audit/single", content=delivery, headers=auth(second)).status_code == 200


def test_the_two_buckets_do_not_share_a_budget(client, token, delivery, tight_limits):
    """The bulk limit is two orders of magnitude tighter, and spending it must not close the other.

    This is also the regression test for the eviction bug the limiter's map invites: a minute
    window's index is far larger than an hour window's, so an eviction that compared one against
    the other would silently wipe the bulk counters on the next single-file request.
    """
    archive = zip_of({"a_padx.xml": delivery})
    upload = {"file": ("upload.zip", archive, "application/zip")}

    assert client.post("/api/v1/audit/bulk", files=upload, headers=auth(token)).status_code == 202
    refused = client.post("/api/v1/audit/bulk", files=upload, headers=auth(token))
    assert refused.status_code == 429
    assert refused.json()["details"]["window_seconds"] == 3600

    # The single budget is untouched, and spending it does not give the bulk budget back.
    assert client.post("/api/v1/audit/single", content=delivery, headers=auth(token)).status_code == 200
    assert client.post("/api/v1/audit/bulk", files=upload, headers=auth(token)).status_code == 429


def test_an_unauthenticated_request_is_refused_before_it_costs_a_budget(client, delivery, tight_limits):
    """Order of operations: the key is verified first, so an anonymous flood cannot exhaust a key.

    If the limiter ran first it would have nothing to count against but the request itself, and the
    only thing it could protect would be a budget nobody owns.
    """
    for _ in range(5):
        assert client.post("/api/v1/audit/single", content=delivery).status_code == 401

    token = mint(client)
    assert client.post("/api/v1/audit/single", content=delivery, headers=auth(token)).status_code == 200


# ==========================================================================================
# 5. the PDF
# ==========================================================================================


def test_a_completed_job_renders_a_pdf(client, token, delivery):
    accepted = client.post(
        "/api/v1/audit/bulk",
        files={"file": ("upload.zip", zip_of({"a_padx.xml": delivery}), "application/zip")},
        headers=auth(token),
    )
    job_id = accepted.json()["batch_id"]

    response = client.post(f"/api/v1/audit/{job_id}/pdf", headers=auth(token))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == f'attachment; filename="{job_id}_pruefbericht.pdf"'

    document = response.content
    assert document.startswith(b"%PDF-1.4")
    assert document.rstrip().endswith(b"%%EOF")
    assert b"/Type /Catalog" in document

    # Rendering the same job twice gives the same bytes — the same property the CSV export has, and
    # the reason there is no creation timestamp in the document.
    again = client.post(f"/api/v1/audit/{job_id}/pdf", headers=auth(token))
    assert again.content == document


async def test_the_pdf_is_refused_while_the_job_is_not_finished(client, token):
    """A partial roll-up printed onto paper is a number somebody reconciles against three weeks
    later, with no way to tell which moment it was a snapshot of.

    The job is written directly rather than uploaded, because a job that goes through the endpoint
    is already `COMPLETED` by the time the `202` returns — `TestClient` runs the drain inside the
    request cycle. This is the only way to observe a non-terminal one.
    """
    from app.services.batch_audit import new_batch_id

    service = deps.batches()
    batch_id = new_batch_id()
    await service.create_bulk_job(
        [],
        upload_path="/nonexistent/upload.zip",
        organization_id=TEST_ORGANIZATION_ID,
        batch_id=batch_id,
    )

    response = client.post(f"/api/v1/audit/{batch_id}/pdf", headers=auth(token))
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error_code"] == "AUDIT_JOB_NOT_COMPLETED"
    assert body["details"]["current_status"] == "PENDING"


def test_the_pdf_states_the_engine_it_was_produced_under(client, token, delivery):
    """A report that cannot name its own catalog and rule set is not evidence of anything."""
    pytest.importorskip("shutil")
    import shutil
    import subprocess
    import tempfile

    if shutil.which("pdftotext") is None:
        pytest.skip("pdftotext is not installed; the PDF's text layer cannot be read here")

    accepted = client.post(
        "/api/v1/audit/bulk",
        files={"file": ("upload.zip", zip_of({"a_padx.xml": delivery}), "application/zip")},
        headers=auth(token),
    )
    job_id = accepted.json()["batch_id"]
    document = client.post(f"/api/v1/audit/{job_id}/pdf", headers=auth(token)).content

    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(document)
        handle.flush()
        text = subprocess.run(
            ["pdftotext", handle.name, "-"], capture_output=True, check=True
        ).stdout.decode("utf-8")

    assert "GOÄ-Prüfbericht" in text
    assert job_id in text
    assert TEST_ORGANIZATION_ID in text
    # The caveat travels with the numbers, because a PDF outlives the screen it came from.
    assert "Nicht beurteilbar" in text
    assert "KEIN Befund gegen die Praxis" in text
    # And the engine identity, so the figures can be reproduced.
    assert "goae_official_snapshot" in text
