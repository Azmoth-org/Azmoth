"""Read the ZIP a bulk upload arrives as, safely, without unpacking it to disk.

`POST /api/v1/audit/bulk` takes one archive holding many PADnext deliveries. This module is the
only thing that opens it, and it is deliberately pure: bytes in, member names or member bytes out.
No database, no HTTP, no filesystem — which is what lets the interesting cases (a bomb, a traversal,
an archive of holiday photos) be tested directly rather than through a background task.

**The archive is inspected before the job exists.** `inspect_archive` runs in the request handler,
so a ZIP that cannot be opened, holds nothing auditable or is a decompression bomb is a `400` on
the upload — not a job row that the caller polls for thirty seconds before being told it failed.
By the time a `202` goes out, the engine knows how many deliveries it accepted and what they are
called, which is also what lets the very first status poll report `0 / 12` instead of `0 / ?`.

**Three guards, and each is a real attack rather than tidiness.**

*Member count* bounds how many rows one request can insert.

*Uncompressed size* is the important one. A 50 MiB ZIP of zeroes expands to something on the order
of a terabyte, and a worker that called `read()` on it would take the process down with it. The
declared `file_size` is summed **before** anything is read, and then the actual bytes are counted
again as members are extracted — because the declared size is a number in the archive's own header
and therefore a number the attacker wrote.

*Path traversal* in a member name (`../../etc/…`, or an absolute path) is refused outright. Nothing
here writes a member to disk, so it could not currently escape anything — and that is exactly the
kind of "safe for now" that stops being true when somebody adds a cache directory later.

**What counts as a delivery.** `*.xml` and `*.padx`, at any depth, skipping directories, dotfiles
and `__MACOSX/` (which every ZIP made on a Mac carries and which holds nothing). PADnext order
files — `*.auf` and `*_auf.xml` — are skipped too: they are metadata beside a delivery, not a
delivery, and auditing one would produce a report about nothing. Anything else is ignored rather
than refused, so a partner who leaves a `README.txt` or their PVS's log file in the archive gets
their invoices audited instead of an error.
"""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

log = logging.getLogger(__name__)


class BulkArchiveError(ValueError):
    """The archive cannot be used. Rendered as a `400` by the route.

    A plain `ValueError` subclass rather than an `EngineError`, because this module has no opinion
    about HTTP and is driven by tests that do not want one. `app.api.audit` maps it.
    """


class ArchiveUnreadable(BulkArchiveError):
    """Not a ZIP, or a ZIP whose directory is corrupt."""


class ArchiveTooLarge(BulkArchiveError):
    """Too many members, or too many bytes once expanded."""

    def __init__(self, message: str, *, limit: int, observed: int) -> None:
        super().__init__(message)
        self.limit = limit
        self.observed = observed


class ArchiveHasNoDeliveries(BulkArchiveError):
    """A readable archive holding no `.xml` or `.padx` member.

    Its own class because the fix is completely different from the other two: the caller's archive
    is fine, they just zipped the wrong thing — most often a folder of PDFs, which is the same
    mistake `/audit/single` refuses with `UNSUPPORTED_INPUT_FORMAT`.
    """


@dataclass(frozen=True)
class ArchiveMember:
    """One delivery inside the archive: where it is, and what to call it.

    `name` is the path inside the archive and is the identity used everywhere — it is what goes in
    `batch_files.filename`, what the report is labelled with, and what the caller matches their own
    records against. Two members can share a *basename* (`praxis_a/rechnung.xml` and
    `praxis_b/rechnung.xml`), so the basename is not usable as a handle and is not offered as one.
    """

    name: str
    size: int


def _is_delivery(info: zipfile.ZipInfo) -> bool:
    """Whether this member is something to audit, by name and by shape.

    Directories, dotfiles and macOS resource forks are skipped silently: they are present in almost
    every real archive and reporting each one as an ignored member would bury the actual result.
    """
    if info.is_dir():
        return False
    parts = PurePosixPath(info.filename).parts
    if any(part.startswith(".") for part in parts) or "__MACOSX" in parts:
        return False

    name = PurePosixPath(info.filename).name.lower()
    if name.endswith(".auf") or name.endswith("_auf.xml"):
        return False
    return name.endswith(".xml") or name.endswith(".padx")


def _reject_traversal(info: zipfile.ZipInfo) -> None:
    if ".." in PurePosixPath(info.filename).parts or Path(info.filename).is_absolute():
        raise ArchiveUnreadable(
            f"Ein Archiv-Eintrag verlässt das Archiv-Wurzelverzeichnis: {info.filename!r}. "
            "Das Archiv wird nicht verarbeitet. — An archive member escapes the archive root."
        )


def inspect_archive(
    content: bytes, *, max_members: int, max_uncompressed_bytes: int
) -> list[ArchiveMember]:
    """The deliveries this archive holds, in a stable order. Raises on anything unusable.

    Sorted by name rather than left in the archive's own order, so a batch's file list — and
    therefore the order the worker audits them in and the rows it writes — is the same whatever
    produced the ZIP. Two uploads of the same content give the same job shape, which is what makes
    a support conversation about "the third file" possible.

    Nothing is decompressed here. The sizes are the declared ones, which is enough to refuse an
    obvious bomb cheaply; `read_member` counts the real bytes, because a declared size is a number
    the archive's author chose.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchiveUnreadable(
            "Das hochgeladene Archiv kann nicht geöffnet werden — es ist kein gültiges ZIP oder "
            f"wurde unvollständig übertragen ({exc}). — The uploaded archive is not a readable "
            "ZIP file."
        ) from exc

    infos = archive.infolist()
    for info in infos:
        _reject_traversal(info)

    declared = sum(info.file_size for info in infos)
    if declared > max_uncompressed_bytes:
        raise ArchiveTooLarge(
            f"Das Archiv entpackt sich auf {declared} Bytes; erlaubt sind höchstens "
            f"{max_uncompressed_bytes}. — The archive expands to more than the permitted size.",
            limit=max_uncompressed_bytes,
            observed=declared,
        )

    members = [
        ArchiveMember(name=info.filename, size=info.file_size)
        for info in infos
        if _is_delivery(info)
    ]
    if len(members) > max_members:
        raise ArchiveTooLarge(
            f"Das Archiv enthält {len(members)} Lieferungen; erlaubt sind höchstens "
            f"{max_members}. Teilen Sie den Upload auf. — The archive holds more deliveries than "
            "one job may carry; split the upload.",
            limit=max_members,
            observed=len(members),
        )
    if not members:
        raise ArchiveHasNoDeliveries(
            "Das Archiv enthält keine PADnext-Lieferung. Erwartet werden *.xml- oder "
            "*.padx-Dateien; Ordner, versteckte Dateien und Auftragsdateien (*.auf) werden "
            "übersprungen. — The archive holds no *.xml or *.padx member to audit."
        )

    members.sort(key=lambda member: member.name)
    log.info(
        "bulk archive holds %d deliveries out of %d members (%d bytes declared)",
        len(members),
        len(infos),
        declared,
    )
    return members


def read_member(content: bytes, name: str, *, max_bytes: int) -> bytes:
    """One member's bytes, refusing to expand past `max_bytes`.

    Reads in chunks against the open stream rather than calling `ZipFile.read`, which allocates the
    whole decompressed member before anyone can object to its size. That distinction is the entire
    protection: a member declaring 1 kB and expanding to 40 GB is the ordinary shape of a zip bomb,
    and `read()` would have allocated the 40 GB before returning it to be checked.

    `max_bytes` is the *whole archive's* remaining budget, passed in by the caller, so a bomb split
    across two hundred members is refused as surely as one in a single member.
    """
    archive = zipfile.ZipFile(io.BytesIO(content))
    buffer = bytearray()
    with archive.open(name) as stream:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            buffer.extend(chunk)
            if len(buffer) > max_bytes:
                raise ArchiveTooLarge(
                    f"Der Archiv-Eintrag {name!r} entpackt sich auf mehr als {max_bytes} Bytes. "
                    "— An archive member expands beyond the permitted size.",
                    limit=max_bytes,
                    observed=len(buffer),
                )
    return bytes(buffer)


__all__ = [
    "ArchiveHasNoDeliveries",
    "ArchiveMember",
    "ArchiveTooLarge",
    "ArchiveUnreadable",
    "BulkArchiveError",
    "inspect_archive",
    "read_member",
]
