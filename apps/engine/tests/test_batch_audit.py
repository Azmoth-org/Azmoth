"""Batch PADnext audit: the roll-up arithmetic, and the endpoints around it.

The commercially load-bearing claim in this feature is one line of arithmetic — that the three
honest buckets add up across a hundred invoices the same way they add up inside one — so it is
tested twice, from two directions.

`test_aggregate_reports_*` drives `aggregate_reports` directly with hand-built reports whose
figures were chosen to be checkable by eye. No database, no Soufflé, no HTTP: if the sums are
wrong, exactly these fail and they say by how much.

`test_a_batch_of_three_files_*` drives the real endpoints with real synthetic deliveries and
asserts the stored aggregate equals the sum of the per-file reports the same run produced. That is
the weaker assertion — it cannot catch an error made identically in both places — but it is the one
that proves the parts are wired together at all.

**Why the background task runs without being mocked.** Starlette's `TestClient` completes the ASGI
cycle before returning, and background tasks are part of that cycle, so `client.post(…)` returns
only once the batch has actually been processed. That is a synchronous run of the real task against
the real store — better than a mock, because it exercises the session handling and the JSON
round-trip that a mock would have skipped.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import PADNEXT_EXAMPLES_DIR
from app.schemas.batch import BatchFileStatus, BatchJobStatus
from app.schemas.padnext import PadnextAuditedPosition, PadnextAuditReport
from app.services.batch_audit import aggregate_reports, risk_sort_key

PAYLOAD_NAME = "00004711_20260726_ADL_000001_padx.xml"


# ------------------------------------------------------------------------------------------
# synthetic deliveries
# ------------------------------------------------------------------------------------------


def payload(positions: str, *, count: int, invoice_id: str) -> bytes:
    """Wrap `<goziffer>` elements in the smallest ADL payload the reader accepts.

    Hand-built rather than copied from the bundled example so a test can choose exactly which
    defects a file carries — the whole point of a batch test is that the files differ.
    """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- SYNTHETIC. No real patient, no real practice, no real invoice. -->
<rechnungen anzahl="1" xmlns="http://padinfo.de/ns/pad">
  <nachrichtentyp version="02.12">ADL</nachrichtentyp>
  <rechnung id="{invoice_id}">
    <abrechnungsfall>
      <behandlungsart>0</behandlungsart>
      <vertragsart>1</vertragsart>
      <positionen posanzahl="{count}">
{positions}
      </positionen>
    </abrechnungsfall>
  </rechnung>
</rechnungen>
""".encode()


#: Three positions, one per bucket outcome we want to see: a justified 301 that a verified
#: Zielleistung rule confirms, the 200 that same rule removes, and a factor over the § 5 Höchstsatz.
SMALL_INVOICE_POSITIONS = """        <goziffer positionsnr="1" go="GOÄ" ziffer="301">
          <datum>2026-07-20</datum><anzahl>1</anzahl><text>Punktion eines Kniegelenks</text>
          <faktor>2.6</faktor>
          <begruendung>Erschwerte Punktion bei ausgepraegtem Reizzustand.</begruendung>
          <gesamtbetrag>24.25</gesamtbetrag>
        </goziffer>
        <goziffer positionsnr="2" go="GOÄ" ziffer="200">
          <datum>2026-07-20</datum><anzahl>1</anzahl><text>Verband</text>
          <faktor>2.3</faktor><gesamtbetrag>6.03</gesamtbetrag>
        </goziffer>
        <goziffer positionsnr="3" go="GOÄ" ziffer="3">
          <datum>2026-07-20</datum><anzahl>1</anzahl><text>Eingehende Beratung</text>
          <faktor>4.0</faktor><begruendung>Sehr ausfuehrliches Gespraech.</begruendung>
          <gesamtbetrag>34.97</gesamtbetrag>
        </goziffer>"""

#: Not a PADnext delivery at all. The third file of every batch test, and the reason the batch has
#: to survive one: a user dragging a folder in will include a stray file sooner or later.
NOT_A_DELIVERY = b"this is not XML, and it is certainly not a PADnext container\n"


@pytest.fixture(scope="module")
def example_payload() -> bytes:
    return (PADNEXT_EXAMPLES_DIR / PAYLOAD_NAME).read_bytes()


@pytest.fixture
def three_files(example_payload):
    """The batch under test: the bundled nine-position example, a small invoice, and a bad file."""
    return [
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
    ]


# ------------------------------------------------------------------------------------------
# the arithmetic, on its own
# ------------------------------------------------------------------------------------------


def make_report(
    *,
    claimed: str,
    fine: str,
    wrong: str,
    unconfirmed: str,
    buckets: tuple[int, int, int] = (0, 0, 0),
) -> PadnextAuditReport:
    """A report with only the fields the roll-up reads, and positions to match the bucket counts.

    `PadnextAuditReport` refuses to exist unless its three buckets sum to its claimed total, so
    every fixture below is already a valid financial statement about one invoice — which is what
    makes "the sum of valid statements is a valid statement" a meaningful thing to assert.
    """
    fine_n, wrong_n, unconfirmed_n = buckets
    positions = [
        PadnextAuditedPosition(positionsnr=str(i), ziffer="1", go="GOÄ", bucket=bucket)
        for i, bucket in enumerate(
            ["confirmed_fine"] * fine_n
            + ["confirmed_wrong"] * wrong_n
            + ["unconfirmed"] * unconfirmed_n,
            start=1,
        )
    ]
    return PadnextAuditReport(
        claimed_total_eur=Decimal(claimed),
        confirmed_fine_eur=Decimal(fine),
        confirmed_wrong_eur=Decimal(wrong),
        unconfirmed_eur=Decimal(unconfirmed),
        positions=positions,
    )


def test_aggregate_reports_sums_each_bucket_and_keeps_the_identity():
    """Three invoices, hand-picked so every column is checkable in your head.

        claimed   fine    wrong   unconfirmed
        100.00    40.00   25.00   35.00
        250.50    0.00    250.50  0.00
         49.50    9.50    0.00    40.00
        ------------------------------------
        400.00    49.50   275.50  75.00      → 49.50 + 275.50 + 75.00 == 400.00
    """
    summary = aggregate_reports(
        [
            make_report(claimed="100.00", fine="40.00", wrong="25.00", unconfirmed="35.00"),
            make_report(claimed="250.50", fine="0.00", wrong="250.50", unconfirmed="0.00"),
            make_report(claimed="49.50", fine="9.50", wrong="0.00", unconfirmed="40.00"),
        ],
        file_count=3,
        failed_file_count=0,
    )

    assert summary.claimed_total_eur == Decimal("400.00")
    assert summary.confirmed_fine_eur == Decimal("49.50")
    assert summary.confirmed_wrong_eur == Decimal("275.50")
    assert summary.unconfirmed_eur == Decimal("75.00")
    assert (
        summary.confirmed_fine_eur + summary.confirmed_wrong_eur + summary.unconfirmed_eur
        == summary.claimed_total_eur
    )
    # (49.50 + 275.50) / 400.00
    assert summary.coverage_ratio == pytest.approx(0.8125)
    assert summary.completed_file_count == 3
    assert summary.failed_file_count == 0


def test_the_coverage_ratio_weights_by_money_not_by_file():
    """A €1 fully-audited invoice must not drag a €999 unaudited one up to 50 % coverage.

    This is the specific mistake the field's docstring warns about, so it gets its own test: a mean
    of the two per-file ratios is 0.5, and the honest answer is 0.001.
    """
    summary = aggregate_reports(
        [
            make_report(claimed="1.00", fine="1.00", wrong="0.00", unconfirmed="0.00"),
            make_report(claimed="999.00", fine="0.00", wrong="0.00", unconfirmed="999.00"),
        ],
        file_count=2,
        failed_file_count=0,
    )

    assert summary.claimed_total_eur == Decimal("1000.00")
    assert summary.coverage_ratio == pytest.approx(0.001)
    assert summary.coverage_ratio != pytest.approx(0.5)


def test_a_failed_file_contributes_no_euros_but_is_counted():
    """The roll-up must state what it is missing, not quietly speak for the whole upload."""
    summary = aggregate_reports(
        [make_report(claimed="80.00", fine="80.00", wrong="0.00", unconfirmed="0.00")],
        file_count=3,
        failed_file_count=2,
    )

    assert summary.file_count == 3
    assert summary.completed_file_count == 1
    assert summary.failed_file_count == 2
    assert summary.claimed_total_eur == Decimal("80.00")


def test_an_empty_batch_aggregates_to_zero_rather_than_dividing_by_it():
    summary = aggregate_reports([], file_count=0, failed_file_count=0)
    assert summary.claimed_total_eur == Decimal("0.00")
    assert summary.coverage_ratio == 0.0


def test_position_counts_are_summed_per_bucket():
    summary = aggregate_reports(
        [
            make_report(
                claimed="10.00", fine="10.00", wrong="0.00", unconfirmed="0.00", buckets=(2, 0, 0)
            ),
            make_report(
                claimed="20.00", fine="0.00", wrong="5.00", unconfirmed="15.00", buckets=(0, 1, 3)
            ),
        ],
        file_count=2,
        failed_file_count=0,
    )

    assert summary.position_count == 6
    assert summary.confirmed_fine_positions == 2
    assert summary.confirmed_wrong_positions == 1
    assert summary.unconfirmed_positions == 3


def test_the_aggregate_refuses_to_exist_if_the_buckets_do_not_reconcile():
    """The same refusal a single report makes. Constructed by hand, because summation cannot
    produce it — which is the point: if this ever fires in production it is a bug, not rounding."""
    from app.schemas.batch import BatchAggregateSummary

    with pytest.raises(ValueError, match="do not reconcile"):
        BatchAggregateSummary(
            claimed_total_eur=Decimal("100.00"),
            confirmed_fine_eur=Decimal("10.00"),
            confirmed_wrong_eur=Decimal("10.00"),
            unconfirmed_eur=Decimal("10.00"),
        )


def test_files_sort_riskiest_first_and_unaudited_last():
    """`confirmed_wrong_eur` descending, with failed files after every audited one."""
    from app.schemas.batch import BatchFileResult

    audited_low = BatchFileResult(
        filename="low.xml",
        status=BatchFileStatus.COMPLETED,
        report=make_report(claimed="50.00", fine="50.00", wrong="0.00", unconfirmed="0.00"),
    )
    audited_high = BatchFileResult(
        filename="high.xml",
        status=BatchFileStatus.COMPLETED,
        report=make_report(claimed="900.00", fine="0.00", wrong="900.00", unconfirmed="0.00"),
    )
    failed = BatchFileResult(
        filename="broken.xml", status=BatchFileStatus.FAILED, error_message="PadnextError: nope"
    )

    ordered = sorted([failed, audited_low, audited_high], key=risk_sort_key)
    assert [f.filename for f in ordered] == ["high.xml", "low.xml", "broken.xml"]


# ------------------------------------------------------------------------------------------
# the endpoints, end to end
# ------------------------------------------------------------------------------------------


def test_the_batch_endpoint_accepts_the_upload_with_202_and_a_handle(client, three_files):
    response = client.post("/api/v1/padnext/batch", files=three_files)

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["batch_id"].startswith("batch_")
    assert body["file_count"] == 3
    # PENDING is what was true when the row was written. The task has in fact already run by the
    # time TestClient returns, which is why every later assertion reads the GET and not this body.
    assert body["status"] == "PENDING"


def test_a_batch_of_three_files_aggregates_to_the_sum_of_its_reports(client, three_files):
    """The end-to-end claim: the stored roll-up is exactly the per-file reports added up.

    Asserted against the reports the same run produced rather than against hard-coded euros, so the
    test does not have to be edited every time the catalog moves — a change that moved the money
    would move both sides together, and `test_aggregate_reports_*` above is what pins the
    arithmetic itself.
    """
    batch_id = client.post("/api/v1/padnext/batch", files=three_files).json()["batch_id"]

    job = client.get(f"/api/v1/padnext/batch/{batch_id}")
    assert job.status_code == 200, job.text
    body = job.json()

    assert body["status"] == "COMPLETED"
    assert body["file_count"] == 3
    assert body["processed_file_count"] == 3
    assert body["completed_file_count"] == 2
    assert body["failed_file_count"] == 1
    assert body["completed_at"] is not None

    reports = [f["report"] for f in body["files"] if f["status"] == "COMPLETED"]
    assert len(reports) == 2

    summary = body["aggregate_summary"]
    for field in (
        "claimed_total_eur",
        "confirmed_fine_eur",
        "confirmed_wrong_eur",
        "unconfirmed_eur",
    ):
        expected = sum((Decimal(r[field]) for r in reports), Decimal("0.00"))
        assert Decimal(summary[field]) == expected, field

    identity = (
        Decimal(summary["confirmed_fine_eur"])
        + Decimal(summary["confirmed_wrong_eur"])
        + Decimal(summary["unconfirmed_eur"])
    )
    assert identity == Decimal(summary["claimed_total_eur"])

    audited = Decimal(summary["confirmed_fine_eur"]) + Decimal(summary["confirmed_wrong_eur"])
    assert summary["coverage_ratio"] == pytest.approx(
        float(audited / Decimal(summary["claimed_total_eur"]))
    )


def test_a_failed_file_does_not_cost_the_batch_its_other_results(client, three_files):
    """The requirement stated plainly: one bad file is marked FAILED and the rest still audit."""
    batch_id = client.post("/api/v1/padnext/batch", files=three_files).json()["batch_id"]
    body = client.get(f"/api/v1/padnext/batch/{batch_id}").json()

    # The job itself completed. A run in which one delivery was unreadable is a run with a result,
    # not a broken job — see `BatchJobStatus` for why FAILED is reserved for the machinery.
    assert body["status"] == "COMPLETED"
    assert body["error_message"] is None

    by_name = {f["filename"]: f for f in body["files"]}
    broken = by_name["broken.xml"]
    assert broken["status"] == "FAILED"
    assert broken["report"] is None
    assert broken["error_message"]
    # Named, not generic: the reader's own exception type is what tells a user this was not a
    # PADnext file rather than that the engine was down.
    assert broken["error_message"].startswith("PadnextError:")

    assert by_name["full_padx.xml"]["status"] == "COMPLETED"
    assert by_name["small_padx.xml"]["status"] == "COMPLETED"
    assert by_name["full_padx.xml"]["report"]["positions"]


def test_the_files_come_back_sorted_riskiest_first(client, three_files):
    """Sorted by the engine, because the web app may not parse an amount into a number."""
    batch_id = client.post("/api/v1/padnext/batch", files=three_files).json()["batch_id"]
    files = client.get(f"/api/v1/padnext/batch/{batch_id}").json()["files"]

    wrongs = [Decimal(f["report"]["confirmed_wrong_eur"]) for f in files if f["report"]]
    assert wrongs == sorted(wrongs, reverse=True)
    # The unreadable file has no risk figure, so it cannot sit above one that has.
    assert files[-1]["filename"] == "broken.xml"


def test_each_report_in_a_batch_matches_the_single_file_endpoint(client, example_payload):
    """The batch must not be a second, subtly different auditor.

    Both paths call the same `read_delivery` / `audit_delivery`, and this is what proves they still
    do: the same bytes through both endpoints must produce the same three buckets and the same
    receipt hash — the hash covers the catalog, the rules, the policy and the verdicts, so an
    agreement here is an agreement about all of them.
    """
    single = client.post(
        "/api/v1/padnext/audit",
        content=example_payload,
        headers={"Content-Type": "application/xml", "x-padnext-filename": PAYLOAD_NAME},
    )
    assert single.status_code == 200, single.text

    batch_id = client.post(
        "/api/v1/padnext/batch",
        files=[("files", (PAYLOAD_NAME, example_payload, "application/xml"))],
    ).json()["batch_id"]
    batched = client.get(f"/api/v1/padnext/batch/{batch_id}").json()["files"][0]["report"]

    for field in (
        "claimed_total_eur",
        "confirmed_fine_eur",
        "confirmed_wrong_eur",
        "unconfirmed_eur",
        "receipt_hash",
    ):
        assert batched[field] == single.json()[field], field


def test_a_single_file_batch_aggregates_to_that_file(client, example_payload):
    """A batch of one is the degenerate case, and it must agree with the report inside it."""
    batch_id = client.post(
        "/api/v1/padnext/batch",
        files=[("files", (PAYLOAD_NAME, example_payload, "application/xml"))],
    ).json()["batch_id"]
    body = client.get(f"/api/v1/padnext/batch/{batch_id}").json()

    report, summary = body["files"][0]["report"], body["aggregate_summary"]
    assert summary["claimed_total_eur"] == report["claimed_total_eur"]
    assert summary["confirmed_wrong_eur"] == report["confirmed_wrong_eur"]
    assert summary["coverage_ratio"] == pytest.approx(report["coverage_ratio"])
    assert summary["position_count"] == len(report["positions"])


def test_a_batch_in_which_every_file_fails_still_completes_with_its_errors(client):
    """Not FAILED: the useful output of such a run is the per-file messages, and a status that
    says "nothing to see" would hide them."""
    batch_id = client.post(
        "/api/v1/padnext/batch",
        files=[
            ("files", ("a.xml", NOT_A_DELIVERY, "application/octet-stream")),
            ("files", ("b.xml", NOT_A_DELIVERY, "application/octet-stream")),
        ],
    ).json()["batch_id"]
    body = client.get(f"/api/v1/padnext/batch/{batch_id}").json()

    assert body["status"] == "COMPLETED"
    assert body["failed_file_count"] == 2
    assert body["completed_file_count"] == 0
    assert all(f["error_message"] for f in body["files"])

    summary = body["aggregate_summary"]
    assert Decimal(summary["claimed_total_eur"]) == Decimal("0.00")
    assert summary["coverage_ratio"] == 0.0
    # The roll-up says it speaks for nothing, which is the honest reading of this batch.
    assert summary["completed_file_count"] == 0
    assert summary["failed_file_count"] == 2


def test_an_unknown_batch_id_is_a_404_that_says_what_to_do(client):
    response = client.get("/api/v1/padnext/batch/batch_deadbeefdeadbeef")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"] == "batch_not_found"
    assert "padnext/batch" in detail["message"]


def test_a_batch_with_no_files_is_refused(client):
    """FastAPI rejects a multipart body with no `files` part before the handler runs."""
    response = client.post("/api/v1/padnext/batch", files=[])
    assert response.status_code in {400, 422}, response.text


def test_an_empty_file_part_is_refused_rather_than_stored_as_a_failed_row(client):
    """An empty part is a client bug, so it fails the request instead of becoming a batch of one
    FAILED file the user has to go and read."""
    response = client.post(
        "/api/v1/padnext/batch",
        files=[("files", ("empty.xml", b"", "application/xml"))],
    )
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["error"] == "empty_file"


def test_too_many_files_is_refused_at_the_perimeter(client, monkeypatch):
    """The ceiling exists because every uploaded file sits in this process's memory."""
    from app.api import padnext as padnext_api

    monkeypatch.setattr(padnext_api, "MAX_BATCH_FILES", 2)
    response = client.post(
        "/api/v1/padnext/batch",
        files=[("files", (f"f{i}.xml", NOT_A_DELIVERY, "application/xml")) for i in range(3)],
    )
    assert response.status_code == 413, response.text
    assert response.json()["detail"]["error"] == "too_many_files"


def test_the_single_file_endpoint_still_takes_raw_bytes(client, example_payload):
    """The brief froze `/padnext/audit`. Asserted here as well as in `test_padnext.py`, because
    adding `python-multipart` to the engine is exactly the change that could have tempted someone
    to convert it to a multipart upload."""
    response = client.post(
        "/api/v1/padnext/audit",
        content=example_payload,
        headers={"Content-Type": "application/xml", "x-padnext-filename": PAYLOAD_NAME},
    )
    assert response.status_code == 200, response.text
    assert response.json()["source_name"] == PAYLOAD_NAME


# ------------------------------------------------------------------------------------------
# the store, without HTTP
# ------------------------------------------------------------------------------------------


async def test_reports_are_withheld_while_the_job_is_still_running(database):
    """A two-second poll over a hundred files must not ship a hundred audit reports per tick.

    Driven against the store rather than the API because `TestClient` finishes the background task
    before it returns — there is no moment during an HTTP test at which a job is `PROCESSING`.
    """
    from app.db.models import BatchFileRecord, BatchJobRecord
    from app.services.batch_audit import BatchAuditService

    service = BatchAuditService(database)
    accepted, _ = await service.create_batch([("one.xml", b"<x/>")])

    report = make_report(claimed="10.00", fine="10.00", wrong="0.00", unconfirmed="0.00")
    async with database.session() as session:
        from sqlalchemy import select

        job = (
            await session.execute(
                select(BatchJobRecord).where(BatchJobRecord.batch_id == accepted.batch_id)
            )
        ).scalar_one()
        job.status = str(BatchJobStatus.PROCESSING)
        record = (
            await session.execute(
                select(BatchFileRecord).where(BatchFileRecord.batch_job_id == job.id)
            )
        ).scalar_one()
        record.status = str(BatchFileStatus.COMPLETED)
        record.report_json = report.model_dump(mode="json")

    running = await service.load_batch(accepted.batch_id)
    assert running.status is BatchJobStatus.PROCESSING
    assert running.processed_file_count == 1
    assert running.files[0].status is BatchFileStatus.COMPLETED
    assert running.files[0].report is None, "a running job must not ship reports to a poller"
    assert running.aggregate_summary is None


async def test_the_batch_is_marked_failed_when_the_machinery_breaks(database):
    """A broken pipeline is not a broken *file*: the job fails, and says why.

    The distinction matters commercially. "Ninety-nine invoices are clean" computed over rows that
    were never written is a false statement; "the batch failed" is a true one.
    """
    from app.services.batch_audit import BatchAuditService

    def factory():
        raise RuntimeError("the rules engine is not available")

    service = BatchAuditService(database, pipeline_factory=factory)
    accepted, payloads = await service.create_batch([("one.xml", b"<x/>")])

    await service.process_batch(accepted.batch_id, payloads)

    job = await service.load_batch(accepted.batch_id)
    assert job.status is BatchJobStatus.FAILED
    assert "rules engine is not available" in job.error_message
    assert job.aggregate_summary is None


async def test_a_batch_with_no_files_is_refused_by_the_store(database):
    from app.services.batch_audit import BatchAuditService, EmptyBatch

    with pytest.raises(EmptyBatch):
        await BatchAuditService(database).create_batch([])


async def test_two_uploads_with_the_same_name_both_get_a_row(database):
    """A file picker will happily hand over two `rechnung.xml`s. Refusing the batch over it would
    be worse than showing the name twice."""
    from app.services.batch_audit import BatchAuditService

    service = BatchAuditService(database)
    accepted, payloads = await service.create_batch([("same.xml", b"<a/>"), ("same.xml", b"<b/>")])

    assert accepted.file_count == 2
    assert len({file_id for file_id, _ in payloads}) == 2

    job = await service.load_batch(accepted.batch_id)
    assert [f.filename for f in job.files] == ["same.xml", "same.xml"]


# ------------------------------------------------------------------------------------------
# recovery: a batch a dead process left behind
# ------------------------------------------------------------------------------------------


async def _force_status(database, batch_id: str, status: BatchJobStatus) -> None:
    """Put a job into a status the happy path would never leave it in.

    What a killed process leaves behind cannot be produced by calling the service — `process_batch`
    always reaches a terminal state or fails loudly — so the row is written directly. That is the
    point: the reaper's whole job is to clean up state no code path can create on purpose.
    """
    from sqlalchemy import select

    from app.db.models import BatchJobRecord

    async with database.session() as session:
        job = (
            await session.execute(
                select(BatchJobRecord).where(BatchJobRecord.batch_id == batch_id)
            )
        ).scalar_one()
        job.status = str(status)


@pytest.mark.parametrize("stranded", [BatchJobStatus.PENDING, BatchJobStatus.PROCESSING])
async def test_an_interrupted_batch_is_failed_at_startup_rather_than_left_in_limbo(
    database, stranded
):
    """Both interruptible statuses are reaped, not just `PROCESSING`.

    A process that died between the `202` and the background task's first write leaves `PENDING`,
    which is the same permanent limbo reached one step earlier — so both are covered.
    """
    from app.services.batch_audit import INTERRUPTED_MESSAGE, BatchAuditService

    service = BatchAuditService(database)
    accepted, _ = await service.create_batch([("one.xml", b"<x/>")])
    await _force_status(database, accepted.batch_id, stranded)

    reaped = await service.reap_interrupted_batches()

    assert reaped == [accepted.batch_id]
    job = await service.load_batch(accepted.batch_id)
    assert job.status is BatchJobStatus.FAILED
    assert job.error_message == INTERRUPTED_MESSAGE
    assert job.completed_at is not None
    assert job.aggregate_summary is None, "a partial roll-up is worse than none"


async def test_reaping_leaves_the_files_pending_rather_than_claiming_they_failed(database):
    """A delivery nobody got to is not a delivery that failed its audit.

    `PENDING` under a `FAILED` job reads correctly — "we never reached this file" — and it keeps
    `processed_file_count` honest about how far the interrupted run had got.
    """
    from app.services.batch_audit import BatchAuditService

    service = BatchAuditService(database)
    accepted, payloads = await service.create_batch(
        [("a.xml", b"<a/>"), ("b.xml", b"<b/>"), ("c.xml", b"<c/>")]
    )

    # One file landed before the process died; the other two never started.
    await service._write_file_outcome(
        payloads[0][0],
        status=BatchFileStatus.COMPLETED,
        report_json=make_report(
            claimed="10.00", fine="10.00", wrong="0.00", unconfirmed="0.00"
        ).model_dump(mode="json"),
    )
    await _force_status(database, accepted.batch_id, BatchJobStatus.PROCESSING)

    await service.reap_interrupted_batches()

    job = await service.load_batch(accepted.batch_id)
    assert job.status is BatchJobStatus.FAILED
    assert job.completed_file_count == 1
    assert job.failed_file_count == 0, "no file failed — the run was abandoned"
    assert job.processed_file_count == 1
    assert sorted(f.status for f in job.files) == sorted(
        [BatchFileStatus.COMPLETED, BatchFileStatus.PENDING, BatchFileStatus.PENDING]
    )


async def test_reaping_does_not_touch_a_batch_that_finished_or_already_failed(database):
    """Idempotence, and the property that makes running this on every start safe."""
    from app.services.batch_audit import BatchAuditService

    service = BatchAuditService(database)
    done, payloads = await service.create_batch([("one.xml", b"<x/>")])
    await service._write_file_outcome(
        payloads[0][0],
        status=BatchFileStatus.COMPLETED,
        report_json=make_report(
            claimed="10.00", fine="10.00", wrong="0.00", unconfirmed="0.00"
        ).model_dump(mode="json"),
    )
    await service._complete(done.batch_id)

    assert await service.reap_interrupted_batches() == []
    assert await service.reap_interrupted_batches() == []

    job = await service.load_batch(done.batch_id)
    assert job.status is BatchJobStatus.COMPLETED
    assert job.error_message is None
    assert job.aggregate_summary is not None


async def test_reaping_an_empty_table_is_a_no_op(database):
    from app.services.batch_audit import BatchAuditService

    assert await BatchAuditService(database).reap_interrupted_batches() == []


# ------------------------------------------------------------------------------------------
# the listing: what makes a durable batch reachable again
# ------------------------------------------------------------------------------------------


async def test_the_listing_returns_batches_newest_first_with_the_whole_total(database):
    from app.services.batch_audit import BatchAuditService

    service = BatchAuditService(database)
    created = []
    for index in range(3):
        accepted, _ = await service.create_batch([(f"f{index}.xml", b"<x/>")])
        created.append(accepted.batch_id)

    listing = await service.list_batches()

    assert listing.total == 3
    assert len(listing.jobs) == 3
    # Newest first. `created_at` is stamped per call, so the last created must lead.
    assert listing.jobs[0].batch_id == created[-1]
    assert [job.created_at for job in listing.jobs] == sorted(
        (job.created_at for job in listing.jobs), reverse=True
    )


async def test_the_listing_carries_the_rollup_but_never_the_files(database):
    """The listing is a header. `aggregate_summary` is what makes it useful; `files` is what would
    make it megabytes."""
    from app.services.batch_audit import BatchAuditService

    service = BatchAuditService(database)
    accepted, payloads = await service.create_batch([("one.xml", b"<x/>")])
    await service._write_file_outcome(
        payloads[0][0],
        status=BatchFileStatus.COMPLETED,
        report_json=make_report(
            claimed="100.00", fine="40.00", wrong="25.00", unconfirmed="35.00"
        ).model_dump(mode="json"),
    )
    await service._complete(accepted.batch_id)

    row = (await service.list_batches()).jobs[0]

    assert row.status is BatchJobStatus.COMPLETED
    assert row.file_count == 1
    assert row.completed_file_count == 1
    assert row.aggregate_summary is not None
    assert row.aggregate_summary.claimed_total_eur == Decimal("100.00")
    assert row.aggregate_summary.confirmed_wrong_eur == Decimal("25.00")
    assert not hasattr(row, "files"), "a listing row has no files field to misread"


async def test_the_listing_counts_files_for_a_job_that_never_finished(database):
    """The counts come from `batch_files`, not from `aggregate_summary` — which is null on exactly
    the jobs whose progress a reader most wants to see."""
    from app.services.batch_audit import BatchAuditService

    service = BatchAuditService(database)
    accepted, payloads = await service.create_batch(
        [("a.xml", b"<a/>"), ("b.xml", b"<b/>"), ("c.xml", b"<c/>")]
    )
    await service._write_file_outcome(
        payloads[0][0],
        status=BatchFileStatus.COMPLETED,
        report_json=make_report(
            claimed="10.00", fine="10.00", wrong="0.00", unconfirmed="0.00"
        ).model_dump(mode="json"),
    )
    await service._write_file_outcome(
        payloads[1][0], status=BatchFileStatus.FAILED, error_message="PadnextError: unreadable"
    )
    await _force_status(database, accepted.batch_id, BatchJobStatus.PROCESSING)

    row = (await service.list_batches()).jobs[0]

    assert row.status is BatchJobStatus.PROCESSING
    assert row.file_count == 3
    assert (row.completed_file_count, row.failed_file_count, row.processed_file_count) == (1, 1, 2)
    assert row.aggregate_summary is None


async def test_the_listing_pages_without_hiding_the_total(database):
    from app.services.batch_audit import BatchAuditService

    service = BatchAuditService(database)
    for index in range(5):
        await service.create_batch([(f"f{index}.xml", b"<x/>")])

    first = await service.list_batches(limit=2, offset=0)
    second = await service.list_batches(limit=2, offset=2)

    assert (first.total, second.total) == (5, 5), "total is the table, not the page"
    assert (first.limit, first.offset) == (2, 0)
    assert len(first.jobs) == 2 and len(second.jobs) == 2
    assert {job.batch_id for job in first.jobs}.isdisjoint({job.batch_id for job in second.jobs})


async def test_the_listing_clamps_a_hostile_limit(database):
    from app.services.batch_audit import MAX_BATCH_LIST_LIMIT, BatchAuditService

    service = BatchAuditService(database)
    await service.create_batch([("one.xml", b"<x/>")])

    assert (await service.list_batches(limit=10**9)).limit == MAX_BATCH_LIST_LIMIT
    assert (await service.list_batches(limit=0)).limit == 1
    assert (await service.list_batches(offset=-5)).offset == 0


# ------------------------------------------------------------------------------------------
# the listing over HTTP
# ------------------------------------------------------------------------------------------


def test_the_batch_listing_endpoint_finds_a_batch_the_client_no_longer_has_a_handle_for(
    client, three_files
):
    """The reason this endpoint exists: a reload loses the `batch_id`, and the roll-up is still
    in the database."""
    accepted = client.post("/api/v1/padnext/batch", files=three_files).json()

    listing = client.get("/api/v1/padnext/batch")
    assert listing.status_code == 200, listing.text
    body = listing.json()

    assert body["total"] >= 1
    row = next(job for job in body["jobs"] if job["batch_id"] == accepted["batch_id"])
    assert row["status"] == "COMPLETED"
    assert row["file_count"] == 3
    assert row["aggregate_summary"]["claimed_total_eur"]
    assert "files" not in row


def test_the_batch_listing_is_empty_rather_than_absent_when_nothing_has_run(client):
    body = client.get("/api/v1/padnext/batch").json()

    assert body == {"jobs": [], "total": 0, "limit": 50, "offset": 0}


def test_the_batch_listing_refuses_a_limit_outside_its_range(client):
    assert client.get("/api/v1/padnext/batch?limit=0").status_code == 422
    assert client.get("/api/v1/padnext/batch?limit=99999").status_code == 422
    assert client.get("/api/v1/padnext/batch?offset=-1").status_code == 422


def test_the_listing_path_does_not_shadow_the_detail_path(client, three_files):
    """`/batch` and `/batch/{id}` are distinct templates; a regression here would make one
    unreachable."""
    accepted = client.post("/api/v1/padnext/batch", files=three_files).json()

    detail = client.get(f"/api/v1/padnext/batch/{accepted['batch_id']}")
    assert detail.status_code == 200
    assert detail.json()["batch_id"] == accepted["batch_id"]
    assert len(detail.json()["files"]) == 3, "the detail path still carries the files"


async def test_reaping_clears_a_rollup_that_should_not_have_existed(database):
    """A `FAILED` batch must never carry totals, even one it somehow already had.

    `_complete` writes the summary and the `COMPLETED` status in one transaction, so a `PROCESSING`
    row holding a roll-up is unreachable through the service. This pins the reaper's guarantee
    anyway: whatever it marks `FAILED` has no totals afterwards, which is what
    `BatchAuditJob.aggregate_summary` documents and what the batch screen relies on when it refuses
    to render an evaluation for a failed run.
    """
    from app.services.batch_audit import BatchAuditService

    service = BatchAuditService(database)
    accepted, payloads = await service.create_batch([("one.xml", b"<x/>")])
    await service._write_file_outcome(
        payloads[0][0],
        status=BatchFileStatus.COMPLETED,
        report_json=make_report(
            claimed="100.00", fine="40.00", wrong="25.00", unconfirmed="35.00"
        ).model_dump(mode="json"),
    )
    await service._complete(accepted.batch_id)
    assert (await service.load_batch(accepted.batch_id)).aggregate_summary is not None

    # What a killed process cannot leave behind, written by hand so the guarantee is unconditional.
    await _force_status(database, accepted.batch_id, BatchJobStatus.PROCESSING)

    await service.reap_interrupted_batches()

    job = await service.load_batch(accepted.batch_id)
    assert job.status is BatchJobStatus.FAILED
    assert job.aggregate_summary is None, "a failed run must not present totals"
    assert (await service.list_batches()).jobs[0].aggregate_summary is None
