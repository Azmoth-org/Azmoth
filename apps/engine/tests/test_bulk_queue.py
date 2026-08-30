"""The parts of the bulk path that are not an endpoint: the archive, the queue, the document.

`tests/test_partner_api.py` drives all three through HTTP, which proves they are wired together.
This file drives them directly, which is where the *interesting* cases live — a zip bomb, a member
that escapes the archive root, a job interrupted by a restart. None of those can be produced
comfortably through a `TestClient`, and each is the kind of thing that is only ever tested if it is
easy to test.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from app.config import PADNEXT_EXAMPLES_DIR, Settings
from app.db.models import BatchJobRecord
from app.padnext.formats import InputFormat, detect_format
from app.schemas.batch import BatchFileStatus, BatchJobStatus
from app.services.batch_audit import BatchAuditService
from app.services.bulk_archive import (
    ArchiveHasNoDeliveries,
    ArchiveTooLarge,
    ArchiveUnreadable,
    inspect_archive,
    read_member,
)
from app.services.uploads import bulk_job_dir, discard_bulk_upload, store_bulk_upload

from tests.conftest import TEST_ORGANIZATION_ID

DELIVERY = (PADNEXT_EXAMPLES_DIR / "00004711_20260726_ADL_000001_padx.xml").read_bytes()


def zip_bytes(entries: dict[str, bytes], *, compress: bool = True) -> bytes:
    buffer = io.BytesIO()
    mode = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    with zipfile.ZipFile(buffer, "w", mode) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


# ==========================================================================================
# 1. the format sniffer
# ==========================================================================================


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b"", InputFormat.EMPTY),
        (b"   \n\t ", InputFormat.EMPTY),
        (b"<?xml version='1.0'?><rechnungen/>", InputFormat.XML),
        (b"\xef\xbb\xbf<?xml version='1.0'?>", InputFormat.XML),
        (b"PK\x03\x04rest of a zip", InputFormat.ZIP),
        (b"%PDF-1.7\n", InputFormat.PDF),
        (b'  \n {"a": 1}', InputFormat.JSON),
        (b"[]", InputFormat.JSON),
        (b"just some prose", InputFormat.UNKNOWN),
    ],
)
def test_the_format_is_decided_by_the_bytes(body, expected):
    assert detect_format(body) is expected


def test_a_pdf_named_xml_is_still_a_pdf():
    """The whole reason nothing here looks at a filename.

    A browser will happily let somebody upload `rechnung.xml` that is a PDF, and a PVS export
    script with the wrong variable will do it every night. Trusting the name would send that
    delivery to the XML parser, which would report a syntax error at line 1 — and the integrator
    would go looking at our parser rather than at their export.
    """
    assert detect_format(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3") is InputFormat.PDF


def test_a_bom_does_not_hide_the_xml_behind_it():
    """A Windows-based PVS writes one routinely. It is not whitespace by any definition, and it is
    nonetheless in front of the `<`."""
    assert detect_format("﻿<rechnungen/>".encode("utf-8")) is InputFormat.XML


# ==========================================================================================
# 2. the archive
# ==========================================================================================


LIMITS = {"max_members": 500, "max_uncompressed_bytes": 256 * 1024 * 1024}


def test_only_deliveries_are_taken_and_the_rest_is_ignored_not_refused():
    """A partner's README must not cost them their upload."""
    members = inspect_archive(
        zip_bytes(
            {
                "praxis/b_padx.xml": DELIVERY,
                "praxis/a_padx.xml": DELIVERY,
                "c.padx": DELIVERY,
                "README.txt": b"hinweise",
                "export.log": b"log",
                "__MACOSX/._a_padx.xml": b"junk",
                ".hidden/x_padx.xml": b"junk",
                "auftrag_auf.xml": b"<auftrag/>",
                "00004711_20260726_ADL_000001.auf": b"<auftrag/>",
            }
        ),
        **LIMITS,
    )
    assert [member.name for member in members] == [
        "c.padx",
        "praxis/a_padx.xml",
        "praxis/b_padx.xml",
    ]


def test_the_order_is_stable_whatever_the_archive_says():
    """Two uploads of the same content must give the same job shape.

    Otherwise "the third file failed" is a sentence that means something different in each
    direction of a support conversation.
    """
    forwards = zip_bytes({"c_padx.xml": DELIVERY, "a_padx.xml": DELIVERY, "b_padx.xml": DELIVERY})
    backwards = zip_bytes({"b_padx.xml": DELIVERY, "a_padx.xml": DELIVERY, "c_padx.xml": DELIVERY})

    assert [m.name for m in inspect_archive(forwards, **LIMITS)] == [
        m.name for m in inspect_archive(backwards, **LIMITS)
    ]


def test_a_corrupt_archive_is_refused_by_name():
    with pytest.raises(ArchiveUnreadable):
        inspect_archive(b"PK\x03\x04 and then nothing", **LIMITS)


def test_an_archive_with_nothing_auditable_says_what_it_looked_for():
    with pytest.raises(ArchiveHasNoDeliveries, match=r"\*\.padx"):
        inspect_archive(zip_bytes({"a.pdf": b"%PDF-1.7", "b.pdf": b"%PDF-1.7"}), **LIMITS)


def test_a_member_that_escapes_the_archive_root_is_refused():
    """Nothing here writes a member to disk, so this could not currently escape anything — which is
    exactly the kind of "safe for now" that stops being true when a cache directory is added."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../../etc/passwd_padx.xml", b"<x/>")
    with pytest.raises(ArchiveUnreadable, match="escapes"):
        inspect_archive(buffer.getvalue(), **LIMITS)


def test_too_many_deliveries_is_refused_with_the_limit_it_hit():
    with pytest.raises(ArchiveTooLarge) as raised:
        inspect_archive(
            zip_bytes({f"{index:03d}_padx.xml": b"<x/>" for index in range(12)}),
            max_members=10,
            max_uncompressed_bytes=1_000_000,
        )
    assert raised.value.limit == 10
    assert raised.value.observed == 12


def test_a_decompression_bomb_is_refused_on_its_declared_size_before_anything_is_read():
    """One megabyte of zeroes compresses to about a kilobyte. A hundred of them is the shape of the
    attack, and the point is that the refusal costs a header read rather than a gigabyte."""
    bomb = zip_bytes({f"{index}_padx.xml": b"\0" * 1_000_000 for index in range(100)})
    assert len(bomb) < 200_000, "the fixture is only interesting if it is small on disk"

    with pytest.raises(ArchiveTooLarge) as raised:
        inspect_archive(bomb, max_members=500, max_uncompressed_bytes=10_000_000)
    assert raised.value.observed >= 100_000_000


def test_reading_a_member_stops_at_the_budget_rather_than_allocating_first():
    """The second guard, over the bytes that actually come out.

    The declared size is a number the archive's author wrote, so a member that claims to be small
    and expands to gigabytes gets past `inspect_archive`. `read_member` streams and stops.
    """
    archive = zip_bytes({"big_padx.xml": b"\0" * 1_000_000})
    assert len(read_member(archive, "big_padx.xml", max_bytes=2_000_000)) == 1_000_000
    with pytest.raises(ArchiveTooLarge):
        read_member(archive, "big_padx.xml", max_bytes=1000)


# ==========================================================================================
# 3. local storage
# ==========================================================================================


def test_an_upload_lands_under_its_organisation_and_its_job(tmp_path):
    settings = Settings(upload_dir=tmp_path)
    path = store_bulk_upload(
        b"content", batch_id="batch_abc", organization_id=TEST_ORGANIZATION_ID, settings=settings
    )

    assert path == tmp_path / "bulk" / TEST_ORGANIZATION_ID / "batch_abc" / "upload.zip"
    assert path.read_bytes() == b"content"
    # Organisation-first, so "delete everything belonging to this practice" and "how much disk is
    # this practice using" are each one path rather than a full-tree walk.
    assert path.parent.parent.name == TEST_ORGANIZATION_ID


def test_an_organisation_id_that_is_not_a_safe_directory_name_is_hashed_not_stripped(tmp_path):
    """Stripping is not injective: `a/b` and `ab` would strip to the same directory, and one
    practice's uploads would land in another's. Ugly in `ls` and correct is the right way round for
    a tenancy boundary."""
    settings = Settings(upload_dir=tmp_path)
    hostile = bulk_job_dir("batch_x", organization_id="../../etc", settings=settings)

    assert ".." not in hostile.parts
    assert hostile.is_relative_to(tmp_path)
    # And two different hostile ids stay different.
    other = bulk_job_dir("batch_x", organization_id="../../var", settings=settings)
    assert hostile != other


def test_the_archive_is_deleted_when_the_job_is_done_and_kept_when_asked(tmp_path):
    settings = Settings(upload_dir=tmp_path)
    path = store_bulk_upload(
        b"content", batch_id="batch_abc", organization_id="org", settings=settings
    )

    kept = discard_bulk_upload(
        path, settings=Settings(upload_dir=tmp_path, retain_bulk_uploads=True)
    )
    assert kept is False, "the return says whether the archive is gone, and it is not"
    assert path.exists(), "RETAIN_BULK_UPLOADS keeps it for an operator debugging an integration"

    assert discard_bulk_upload(path, settings=settings)
    assert not path.exists()
    assert not path.parent.exists(), "the job directory goes with it"


def test_a_path_outside_the_upload_directory_is_never_deleted(tmp_path):
    """The row this path comes from was written by us — and the alternative to a redundant check on
    an `rmtree` is a service that deletes whatever a corrupted row happens to name."""
    stranger = tmp_path / "important" / "data.txt"
    stranger.parent.mkdir()
    stranger.write_bytes(b"keep me")

    assert not discard_bulk_upload(stranger, settings=Settings(upload_dir=tmp_path / "uploads"))
    assert stranger.exists()


def test_deleting_an_archive_that_is_already_gone_is_not_a_failure(tmp_path):
    """It runs on the terminal transition of a background task: a file an operator cleaned up must
    not turn a COMPLETED job into a FAILED one."""
    settings = Settings(upload_dir=tmp_path)
    assert discard_bulk_upload(tmp_path / "bulk" / "org" / "batch_x" / "upload.zip", settings=settings)


# ==========================================================================================
# 4. the queue
# ==========================================================================================


@pytest.fixture
async def service(database) -> BatchAuditService:
    """A service on its own database, with no pipeline — the queue mechanics need neither."""
    return BatchAuditService(database=database)


async def _job(service: BatchAuditService, batch_id: str) -> BatchJobRecord:
    from sqlalchemy import select

    async with service.database.session() as session:
        return (
            await session.execute(
                select(BatchJobRecord).where(BatchJobRecord.batch_id == batch_id)
            )
        ).scalar_one()


async def test_a_claim_takes_a_job_exactly_once(service, tmp_path):
    """The cross-process guard, which is a conditional UPDATE rather than a lock server.

    Claiming twice must yield the job and then nothing. If the `rowcount` check were dropped, two
    processes would both audit the same archive and write two sets of reports over each other.
    """
    from app.services.bulk_archive import ArchiveMember

    await service.create_bulk_job(
        [ArchiveMember(name="a_padx.xml", size=4)],
        upload_path=tmp_path / "upload.zip",
        organization_id=TEST_ORGANIZATION_ID,
        batch_id="batch_claimtest",
    )

    first = await service._claim_next_bulk_job()
    second = await service._claim_next_bulk_job()

    assert first is not None and first[0] == "batch_claimtest"
    assert second is None, "a claimed job is no longer PENDING and must not be taken again"
    assert (await _job(service, "batch_claimtest")).status == str(BatchJobStatus.PROCESSING)


async def test_an_in_memory_batch_is_never_claimed_by_the_bulk_drain(service):
    """`POST /padnext/batch` writes a PENDING row too, and its bytes are in another task's memory.

    A drain that claimed one would set it PROCESSING and then find nothing to process — turning a
    perfectly good in-flight batch into a job that reports zero files audited.
    """
    accepted, _ = await service.create_batch(
        [("a_padx.xml", b"<x/>")], organization_id=TEST_ORGANIZATION_ID
    )
    assert (await _job(service, accepted.batch_id)).status == str(BatchJobStatus.PENDING)

    assert await service._claim_next_bulk_job() is None
    assert (await _job(service, accepted.batch_id)).status == str(BatchJobStatus.PENDING)


async def test_a_restart_requeues_a_bulk_job_and_fails_an_in_memory_batch(service, tmp_path):
    """The whole reason `batch_jobs.upload_path` exists, in one assertion.

    A bulk job's archive is still on disk, so an interrupted run is work that has not happened yet;
    an in-memory batch's payloads died with the process, so it is a run that can never continue.
    Treating both the same way would either strand the first forever or lie about the second.
    """
    from app.services.bulk_archive import ArchiveMember

    in_memory, _ = await service.create_batch(
        [("a_padx.xml", b"<x/>")], organization_id=TEST_ORGANIZATION_ID
    )
    resumable = await service.create_bulk_job(
        [ArchiveMember(name="a_padx.xml", size=4)],
        upload_path=tmp_path / "upload.zip",
        organization_id=TEST_ORGANIZATION_ID,
        batch_id="batch_resumable",
    )

    reaped = await service.reap_interrupted_batches()

    assert reaped == [in_memory.batch_id], "only what cannot be resumed is reported as given up on"
    assert (await _job(service, in_memory.batch_id)).status == str(BatchJobStatus.FAILED)

    requeued = await _job(service, resumable.batch_id)
    assert requeued.status == str(BatchJobStatus.PENDING)
    assert requeued.error_message is None, "a requeued job is not a failed one and must not say so"


async def test_a_resumed_job_does_not_re_audit_what_already_landed(service, tmp_path):
    """A restart costs the deliveries that were in flight, not the ones that had a verdict.

    Re-auditing a completed file would be harmless arithmetically and still wrong: it would
    overwrite a stored report with one produced under a possibly newer catalog, so a single job's
    rows could end up describing two different engine states.
    """
    from app.services.bulk_archive import ArchiveMember

    await service.create_bulk_job(
        [ArchiveMember(name="a_padx.xml", size=4), ArchiveMember(name="b_padx.xml", size=4)],
        upload_path=tmp_path / "upload.zip",
        organization_id=TEST_ORGANIZATION_ID,
        batch_id="batch_resume2",
    )

    first_id, first_name = (await service._pending_files("batch_resume2"))[0]
    assert first_name == "a_padx.xml"
    await service._write_file_outcome(
        first_id, status=BatchFileStatus.COMPLETED, report_json={"source_name": "a"}
    )

    still_owed = await service._pending_files("batch_resume2")
    assert [name for _, name in still_owed] == ["b_padx.xml"]


async def test_a_job_whose_archive_vanished_fails_with_the_path_in_the_message(service, tmp_path):
    """Operational, not a bad request: an unmounted volume or a cleanup script. The operator
    reading the row is the person who can fix it, so the row names the file."""
    from app.services.bulk_archive import ArchiveMember

    missing = tmp_path / "gone" / "upload.zip"
    await service.create_bulk_job(
        [ArchiveMember(name="a_padx.xml", size=4)],
        upload_path=missing,
        organization_id=TEST_ORGANIZATION_ID,
        batch_id="batch_gone",
    )

    processed = await service.drain_pending_jobs(settings=Settings(upload_dir=tmp_path))

    assert processed == ["batch_gone"]
    job = await _job(service, "batch_gone")
    assert job.status == str(BatchJobStatus.FAILED)
    assert str(missing) in job.error_message
    assert job.aggregate_summary_json is None, "a failed job has no roll-up to show"


# ==========================================================================================
# 5. the PDF
# ==========================================================================================


def test_the_pdf_writer_produces_a_document_a_reader_can_open():
    from app.services.pdf import PdfCanvas

    canvas = PdfCanvas(title="test")
    canvas.text("Prüfbericht", bold=True)
    canvas.paragraph("Ein Absatz mit Umlauten: äöüß, und einem Betrag von 1.234,56 €.")
    document = canvas.render()

    assert document.startswith(b"%PDF-1.4")
    assert document.rstrip().endswith(b"%%EOF")
    assert b"/Type /Catalog" in document
    assert b"startxref" in document
    # The cross-reference offsets must actually point at their objects, or a reader rejects the
    # file — this is the one part of a hand-written PDF that is easy to get subtly wrong.
    for number in (1, 2, 3, 4, 5):
        marker = f"{number} 0 obj".encode()
        assert marker in document


def test_a_long_report_flows_onto_more_than_one_page():
    from app.services.pdf import PdfCanvas

    canvas = PdfCanvas(title="test")
    for index in range(300):
        canvas.text(f"Zeile {index}")
    document = canvas.render()

    assert b"/Count 1 " not in document
    assert document.count(b"/Type /Page\n") == 0  # pages are inline dicts, not standalone lines
    assert b"/Type /Pages" in document


def test_the_same_input_renders_the_same_bytes():
    """No creation timestamp, no producer version, no id that depends on a dict's order.

    The same property `export_batch` has, for the same reason: two downloads of one finished job
    must not be two different documents.
    """
    from app.services.pdf import PdfCanvas

    def build() -> bytes:
        canvas = PdfCanvas(title="test")
        canvas.text("Prüfbericht")
        canvas.row([(0, "a"), (100, "b")])
        canvas.rule()
        return canvas.render()

    assert build() == build()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.00", "0,00 €"),
        ("12.50", "12,50 €"),
        ("1234.5", "1.234,50 €"),
        ("1234567.89", "1.234.567,89 €"),
        ("-40.10", "-40,10 €"),
    ],
)
def test_amounts_are_typeset_from_the_decimal_not_from_a_float(value, expected):
    """A cent that disappears into binary floating point is a cent a Rechnungsprüfer will find."""
    from decimal import Decimal

    from app.services.pdf import _euro

    assert _euro(Decimal(value)) == expected


def test_a_string_reaching_a_pdf_literal_cannot_break_out_of_it():
    """Parentheses and backslashes delimit and escape a PDF string. A filename carrying one — and
    a filename is client-supplied — would otherwise produce a document no reader can parse."""
    from app.services.pdf import _escape

    assert _escape("a(b)c\\d") == rb"a\(b\)c\\d"
    assert _escape("Zuschläge") == "Zuschläge".encode("cp1252")
    # Outside cp1252: substituted rather than raising, because a report that fails to render over
    # one character in a practice's name is a worse failure than a substituted one.
    assert _escape("Ω") == b"?"
