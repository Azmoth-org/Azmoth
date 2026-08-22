"""Exports: the single approved proposal, and the finished batch.

What these tests are guarding is not "a file comes back". It is that the file is a *record* — that
it was built from the durable row rather than from something in flight, that it cannot be produced
for a proposal nobody approved, and that what a billing centre eventually opens in a spreadsheet
still says which euros this engine can actually defend.

The batch half therefore reads the ZIP the way its consumer will: extract it, parse the CSVs with
`csv.DictReader`, and assert against the aggregate the database holds. Asserting on the bytes we
just wrote would prove only that the writer is self-consistent.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from decimal import Decimal

import pytest

from app.config import PADNEXT_EXAMPLES_DIR
from app.services.export import (
    FILES_CSV,
    FILE_COLUMNS,
    LINE_ITEMS_CSV,
    LINE_ITEM_COLUMNS,
    LIST_SEPARATOR,
    README_TXT,
    SUMMARY_COLUMNS,
    SUMMARY_CSV,
    UTF8_BOM,
)
from tests.conftest import solve_proposal

PAYLOAD_NAME = "00004711_20260726_ADL_000001_padx.xml"


# ------------------------------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------------------------------


def approved_proposal(client, manual_case, *, by: str = "Dr. Beispiel") -> dict:
    draft = solve_proposal(client, manual_case("case_001_knee"), case_id="ENC-export")
    response = client.post(
        f"/api/v1/proposals/{draft['proposal_id']}/approve",
        json={"approved_by": by, "note": "geprüft"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def export(client, proposal_id: str, *, by: str = "PVS-Anbindung", note: str = ""):
    return client.post(
        f"/api/v1/proposals/{proposal_id}/export",
        json={"exported_by": by, "note": note},
    )


def read_zip(payload: bytes) -> dict[str, str]:
    """Every member, decoded. The BOM is stripped here so the tests read the data, not the encoding."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return {
            name: archive.read(name).decode("utf-8").lstrip(UTF8_BOM)
            for name in archive.namelist()
        }


def rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text, newline="")))


# ==========================================================================================
# the single proposal
# ==========================================================================================


def test_exporting_a_draft_is_refused_with_409(client, manual_case):
    """A draft nobody approved is not a document. It is a suggestion."""
    draft = solve_proposal(client, manual_case("case_001_knee"))

    response = export(client, draft["proposal_id"])

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "illegal_transition"
    assert detail["current_status"] == "DRAFT"


def test_exporting_a_rejected_proposal_is_refused_with_409(client, manual_case):
    """REJECTED is terminal, so there is no route to EXPORTED from it — and there must not be.

    A rejected draft that could still be exported would let a refused invoice leave the building
    carrying a receipt hash and a version stamp, which is exactly the document a payer would read
    as an endorsement.
    """
    draft = solve_proposal(client, manual_case("case_001_knee"))
    pid = draft["proposal_id"]
    client.post(
        f"/api/v1/proposals/{pid}/reject",
        json={"rejected_by": "Dr. Beispiel", "reason": "Sonographie nicht dokumentiert"},
    )

    response = export(client, pid)

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["current_status"] == "REJECTED"


def test_export_without_a_name_is_refused(client, manual_case):
    """`exported_by` is required, for the same reason `approved_by` is."""
    approved = approved_proposal(client, manual_case)
    pid = approved["proposal_id"]

    assert client.post(f"/api/v1/proposals/{pid}/export", json={}).status_code == 422
    assert (
        client.post(
            f"/api/v1/proposals/{pid}/export", json={"exported_by": "  "}
        ).status_code
        == 422
    )
    # Still exportable afterwards: a refused request must not have consumed the one transition.
    assert export(client, pid).status_code == 200


def test_exporting_an_approved_proposal_moves_it_to_exported(client, manual_case):
    approved = approved_proposal(client, manual_case)
    pid = approved["proposal_id"]

    response = export(client, pid, by="PVS-Anbindung", note="Ticket 4711")
    assert response.status_code == 200, response.text

    document = response.json()
    assert document["status"] == "EXPORTED"
    assert document["decision"]["exported_by"] == "PVS-Anbindung"
    assert document["decision"]["exported_at"]

    # Read back off the database rather than trusting the document about itself.
    stored = client.get(f"/api/v1/proposals/{pid}").json()
    assert stored["status"] == "EXPORTED"


async def test_the_export_writes_an_exported_audit_event(client, manual_case):
    """The whole point of unlocking this feature: the export is now a logged, attributable act."""
    approved = approved_proposal(client, manual_case)
    pid = approved["proposal_id"]

    export(client, pid, by="Frau Muster", note="Ticket 4711")

    from app.api import deps

    events = await deps.proposals().audit_events(pid)

    assert [e["event_type"] for e in events] == ["CREATED", "APPROVED", "EXPORTED"]
    exported_event = events[-1]
    assert exported_event["actor"] == "Frau Muster"
    assert exported_event["metadata"]["from_status"] == "APPROVED"
    assert exported_event["metadata"]["note"] == "Ticket 4711"


def test_the_document_carries_the_receipt_hash_the_proposal_was_approved_under(
    client, manual_case
):
    """The identity check a dispute turns on.

    `receipt_hash` covers the catalog, the rule tables, the logic programs, the solver versions,
    the policy and the input. If the exported file's hash differed from the approved proposal's,
    the document would be describing an engine state nobody signed off on.
    """
    approved = approved_proposal(client, manual_case)

    document = export(client, approved["proposal_id"]).json()

    assert document["receipt_hash"] == approved["receipt_hash"]
    assert document["proposal_id"] == approved["proposal_id"]
    assert document["case_id"] == "ENC-export"
    assert document["engine"]["catalog_version"] == approved["catalog_version"]
    assert document["engine"]["catalog_sha256"] == approved["catalog_sha256"]
    assert document["engine"]["rules_version"] == approved["rules_version"]
    assert document["engine"]["logic_version"] == approved["logic_version"]


def test_the_document_carries_input_hash_which_the_api_never_returns(client, manual_case):
    """`input_hash` is a column the `Proposal` response deliberately omits.

    The export is the one place it surfaces, and it belongs there: it identifies the clinical input
    alone, so two exports sharing it and differing in `receipt_hash` are the same case coded by two
    engine states. That comparison is impossible from the API responses.
    """
    approved = approved_proposal(client, manual_case)

    document = export(client, approved["proposal_id"]).json()

    assert "input_hash" not in approved
    assert len(document["input_hash"]) == 64


def test_the_document_carries_the_approval_and_its_own_audit_log(client, manual_case):
    approved = approved_proposal(client, manual_case, by="Dr. Beispiel")

    document = export(client, approved["proposal_id"], by="PVS-Anbindung").json()

    assert document["decision"]["approved_by"] == "Dr. Beispiel"
    assert document["decision"]["approved_at"]
    assert document["decision"]["rejected_by"] is None

    # The log inside the file includes the EXPORTED row this very request wrote. A document whose
    # log stopped at APPROVED could not show that it is the export it claims to be.
    assert [e["event_type"] for e in document["audit_events"]] == [
        "CREATED",
        "APPROVED",
        "EXPORTED",
    ]
    assert document["audit_events"][-1]["actor"] == "PVS-Anbindung"


def test_the_document_carries_the_full_solver_result_and_its_proof(client, manual_case):
    """Accepted and blocked Ziffern, factors, amounts, the audit trail and the proof atoms.

    A summary is not evidence. The proof tree is the reason a position can be defended at all, so
    it has to survive the export rather than be flattened out of it.
    """
    approved = approved_proposal(client, manual_case)

    document = export(client, approved["proposal_id"]).json()
    coding = document["solver_result"]["coding"]

    assert coding["proposed_codes"], "an export with no positions is not an invoice draft"
    assert document["solver_result"]["audit_trail"]["solver_status"]
    assert document["solver_result"]["extraction"]

    line = coding["proposed_codes"][0]
    for field in ("ziffer", "factor", "factor_basis", "punkte", "amount_eur"):
        assert field in line, field
    assert line["proof"], "every accepted line carries the atoms that justify it"

    # Rule coverage travels too: a reader must not take "no finding" for "the rules confirmed it".
    assert document["rule_coverage"]["enforced_rule_count"] >= 0
    assert document["rule_coverage"]["rule_coverage"] == "partial"


def test_the_document_is_served_as_a_named_attachment(client, manual_case):
    approved = approved_proposal(client, manual_case)
    pid = approved["proposal_id"]

    response = export(client, pid)

    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"] == f'attachment; filename="{pid}.json"'
    # Pretty-printed and not ASCII-escaped: somebody will open this in an editor.
    assert response.text.startswith("{\n")
    assert json.loads(response.text)["proposal_id"] == pid


def test_a_proposal_can_only_be_exported_once(client, manual_case):
    """EXPORTED is terminal. The second attempt is a 409, not a second file.

    That is deliberate and worth keeping: the export records a decision, and two records of one
    decision is exactly what the lifecycle exists to prevent.
    """
    approved = approved_proposal(client, manual_case)
    pid = approved["proposal_id"]

    assert export(client, pid).status_code == 200

    again = export(client, pid, by="Jemand anders")
    assert again.status_code == 409
    assert again.json()["detail"]["current_status"] == "EXPORTED"


def test_exporting_an_unknown_proposal_is_a_404(client):
    response = export(client, "prop_deadbeefdeadbeef")
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "proposal_not_found"


# ==========================================================================================
# the batch
# ==========================================================================================


@pytest.fixture(scope="module")
def example_payload() -> bytes:
    return (PADNEXT_EXAMPLES_DIR / PAYLOAD_NAME).read_bytes()


@pytest.fixture
def completed_batch(client, example_payload):
    """Two files that audit and one that cannot be read — the brief's shape, and the real one.

    Reuses the synthetic payload builder from the batch tests rather than a second copy, so the
    two suites cannot drift about what a small invoice contains.
    """
    from tests.test_batch_audit import NOT_A_DELIVERY, SMALL_INVOICE_POSITIONS, payload

    response = client.post(
        "/api/v1/padnext/batch",
        files=[
            ("files", ("full_padx.xml", example_payload, "application/xml")),
            (
                "files",
                (
                    "small_padx.xml",
                    payload(SMALL_INVOICE_POSITIONS, count=3, invoice_id="SYNTH-SMALL"),
                    "application/xml",
                ),
            ),
            ("files", ("broken.xml", NOT_A_DELIVERY, "application/octet-stream")),
        ],
    )
    assert response.status_code == 202, response.text
    batch_id = response.json()["batch_id"]

    job = client.get(f"/api/v1/padnext/batch/{batch_id}").json()
    assert job["status"] == "COMPLETED"
    assert job["completed_file_count"] == 2
    assert job["failed_file_count"] == 1
    return job


async def test_exporting_a_batch_that_has_not_completed_is_refused(database):
    """A running batch has a roll-up of "as far as we got", which is not a document.

    Driven against the service rather than the API because `TestClient` finishes the background
    task before it returns — there is no moment during an HTTP test at which a batch is unfinished.
    """
    from app.schemas.batch import BatchJobStatus
    from app.services.batch_audit import BatchAuditService, BatchNotExportable

    service = BatchAuditService(database)
    accepted, _ = await service.create_batch([("one.xml", b"<x/>")])

    with pytest.raises(BatchNotExportable) as raised:
        await service.export_batch(accepted.batch_id)

    assert raised.value.status is BatchJobStatus.PENDING
    assert "not COMPLETED" in str(raised.value)


async def test_exporting_a_failed_batch_is_refused(database):
    """A FAILED batch has no roll-up at all, so there is nothing honest to put in a summary row."""
    from app.schemas.batch import BatchJobStatus
    from app.services.batch_audit import BatchAuditService, BatchNotExportable

    def broken_pipeline():
        raise RuntimeError("the rules engine is not available")

    service = BatchAuditService(database, pipeline_factory=broken_pipeline)
    accepted, payloads = await service.create_batch([("one.xml", b"<x/>")])
    await service.process_batch(accepted.batch_id, payloads)

    with pytest.raises(BatchNotExportable) as raised:
        await service.export_batch(accepted.batch_id)

    assert raised.value.status is BatchJobStatus.FAILED


def test_exporting_an_unknown_batch_is_a_404(client):
    response = client.post("/api/v1/padnext/batch/batch_deadbeefdeadbeef/export")
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "batch_not_found"


def test_the_batch_export_is_a_named_zip_with_the_four_members(client, completed_batch):
    batch_id = completed_batch["batch_id"]

    response = client.post(f"/api/v1/padnext/batch/{batch_id}/export")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="{batch_id}_export.zip"'
    )

    members = read_zip(response.content)
    assert set(members) == {SUMMARY_CSV, LINE_ITEMS_CSV, FILES_CSV, README_TXT}


def test_the_summary_csv_matches_the_aggregate_in_the_database(client, completed_batch):
    """One row, eleven columns, and every figure equal to what `GET /batch/{id}` reports.

    Compared against the API's own aggregate rather than against hard-coded euros: a catalog change
    would move both together, and `test_batch_audit.py` is what pins the arithmetic itself.
    """
    batch_id = completed_batch["batch_id"]
    summary = completed_batch["aggregate_summary"]

    members = read_zip(client.post(f"/api/v1/padnext/batch/{batch_id}/export").content)
    parsed = rows(members[SUMMARY_CSV])

    assert len(parsed) == 1
    row = parsed[0]
    assert list(row) == SUMMARY_COLUMNS

    assert row["batch_id"] == batch_id
    assert row["total_files"] == "3"
    assert row["successful_files"] == "2"
    assert row["failed_files"] == "1"
    assert row["total_claimed_eur"] == summary["claimed_total_eur"]
    assert row["confirmed_fine_eur"] == summary["confirmed_fine_eur"]
    assert row["confirmed_wrong_eur"] == summary["confirmed_wrong_eur"]
    assert row["unconfirmed_eur"] == summary["unconfirmed_eur"]
    assert float(row["coverage_ratio"]) == pytest.approx(summary["coverage_ratio"])
    assert row["created_at"] and row["completed_at"]

    # The identity survives the round trip through CSV text.
    assert (
        Decimal(row["confirmed_fine_eur"])
        + Decimal(row["confirmed_wrong_eur"])
        + Decimal(row["unconfirmed_eur"])
        == Decimal(row["total_claimed_eur"])
    )


def test_the_summary_csv_has_no_column_that_merges_the_buckets(client, completed_batch):
    """The one thing a spreadsheet must not be handed.

    A column adding the three buckets together would be mostly `unconfirmed` — this engine's own
    rule-coverage gap — and every SUM downstream would inherit it as an accusation.
    """
    batch_id = completed_batch["batch_id"]
    members = read_zip(client.post(f"/api/v1/padnext/batch/{batch_id}/export").content)

    header = rows(members[SUMMARY_CSV])[0]
    for forbidden in ("at_risk", "at_risk_eur", "total_at_risk", "disputed_eur"):
        assert forbidden not in header


def test_the_line_items_csv_has_one_row_per_audited_position(client, completed_batch):
    """Exactly the positions of the completed files, and nothing from the one that failed."""
    batch_id = completed_batch["batch_id"]

    expected = [
        (file["filename"], position)
        for file in completed_batch["files"]
        if file["status"] == "COMPLETED"
        for position in file["report"]["positions"]
    ]

    members = read_zip(client.post(f"/api/v1/padnext/batch/{batch_id}/export").content)
    parsed = rows(members[LINE_ITEMS_CSV])

    assert len(parsed) == len(expected)
    assert list(parsed[0]) == LINE_ITEM_COLUMNS
    assert all(len(row) == len(LINE_ITEM_COLUMNS) for row in parsed)

    assert "broken.xml" not in {row["filename"] for row in parsed}

    by_key = {(row["filename"], row["positionsnr"]): row for row in parsed}
    for filename, position in expected:
        row = by_key[(filename, position["positionsnr"])]
        assert row["ziffer"] == f"{position['go']} {position['ziffer']}"
        assert row["description"] == position["official_text"]
        assert row["bucket"] == position["bucket"]
        assert row["bucket_reason"] == position["bucket_reason"]
        # Amounts are the engine's exact decimal strings, never re-formatted.
        assert row["claimed_amount_eur"] == (position["claimed_amount_eur"] or "")
        assert row["verified_rule_ids"] == LIST_SEPARATOR.join(position["verified_rule_ids"])
        assert row["advisory_rule_ids"] == LIST_SEPARATOR.join(position["advisory_rule_ids"])


def test_every_bucket_value_in_the_csv_is_one_of_the_three(client, completed_batch):
    """A fourth value would mean the export invented a category the schema does not have."""
    batch_id = completed_batch["batch_id"]
    members = read_zip(client.post(f"/api/v1/padnext/batch/{batch_id}/export").content)

    buckets = {row["bucket"] for row in rows(members[LINE_ITEMS_CSV])}
    assert buckets <= {"confirmed_fine", "confirmed_wrong", "unconfirmed"}
    assert buckets, "the fixture batch has positions, so this must not be empty"


def test_the_files_csv_names_the_file_that_could_not_be_read(client, completed_batch):
    """Without this the archive would describe a cleaner batch than the one uploaded.

    `batch_line_items.csv` has no row for a failed delivery, so an archive with only the two CSVs
    the brief names could not answer "which invoices were never opened?" — and the summary's
    `failed_files: 1` would be a count with nothing behind it.
    """
    batch_id = completed_batch["batch_id"]
    members = read_zip(client.post(f"/api/v1/padnext/batch/{batch_id}/export").content)
    parsed = rows(members[FILES_CSV])

    assert len(parsed) == 3
    assert list(parsed[0]) == FILE_COLUMNS

    by_name = {row["filename"]: row for row in parsed}
    assert set(by_name) == {"full_padx.xml", "small_padx.xml", "broken.xml"}

    broken = by_name["broken.xml"]
    assert broken["status"] == "FAILED"
    assert broken["error_message"].startswith("PadnextError:")
    # Empty, not zero: zero would read as "this invoice claimed nothing", which is a statement we
    # have no basis to make about a file we could not open.
    assert broken["claimed_total_eur"] == ""
    assert broken["confirmed_wrong_eur"] == ""
    assert broken["position_count"] == ""

    audited = by_name["small_padx.xml"]
    assert audited["status"] == "COMPLETED"
    assert audited["error_message"] == ""
    assert Decimal(audited["claimed_total_eur"]) > 0


def test_the_readme_carries_the_unconfirmed_disclaimer(client, completed_batch):
    """A CSV outlives the screen it came from, so the sentence has to travel with it."""
    batch_id = completed_batch["batch_id"]
    members = read_zip(client.post(f"/api/v1/padnext/batch/{batch_id}/export").content)
    text = members[README_TXT]

    assert "KEIN Befund gegen die Praxis" in text
    assert "NICHT zu einer Summe" in text
    assert "confirmed_fine + confirmed_wrong + unconfirmed = total_claimed" in text
    # And it names its own members, so the archive explains itself.
    for member in (SUMMARY_CSV, LINE_ITEMS_CSV, FILES_CSV):
        assert member in text


def test_the_csvs_are_rfc4180_utf8_with_a_bom(client, completed_batch):
    """The format choice, asserted so it cannot drift silently.

    Excel needs the BOM to read UTF-8 rather than guessing a code page — a mangled Leistungstext in
    a document a payer reads is a real problem. CRLF and comma are RFC 4180, which is what every
    non-Excel consumer expects.
    """
    batch_id = completed_batch["batch_id"]
    with zipfile.ZipFile(
        io.BytesIO(client.post(f"/api/v1/padnext/batch/{batch_id}/export").content)
    ) as archive:
        for name in (SUMMARY_CSV, LINE_ITEMS_CSV, FILES_CSV):
            raw = archive.read(name).decode("utf-8")
            assert raw.startswith(UTF8_BOM), name
            assert "\r\n" in raw, name
            assert raw.splitlines()[0].lstrip(UTF8_BOM).count(",") >= 8, name


def test_exporting_the_same_batch_twice_gives_identical_bytes(client, completed_batch):
    """Read-only and deterministic: re-downloading must not produce a different checksum."""
    batch_id = completed_batch["batch_id"]

    first = client.post(f"/api/v1/padnext/batch/{batch_id}/export").content
    second = client.post(f"/api/v1/padnext/batch/{batch_id}/export").content

    assert first == second

    # And the job is untouched — a batch export is a rendering, not a decision.
    job = client.get(f"/api/v1/padnext/batch/{batch_id}").json()
    assert job["status"] == "COMPLETED"


def test_the_line_items_are_ordered_riskiest_file_first(client, completed_batch):
    """The CSV and the screen must agree on what "riskiest first" means.

    A reconciler comparing the exported file against the dashboard should not have to re-sort one
    of them to line the two up.
    """
    batch_id = completed_batch["batch_id"]
    members = read_zip(client.post(f"/api/v1/padnext/batch/{batch_id}/export").content)

    screen_order = [f["filename"] for f in completed_batch["files"] if f["status"] == "COMPLETED"]

    seen: list[str] = []
    for row in rows(members[LINE_ITEMS_CSV]):
        if not seen or seen[-1] != row["filename"]:
            seen.append(row["filename"])

    assert seen == screen_order
