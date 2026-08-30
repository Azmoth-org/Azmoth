"""Where a bulk upload's bytes live between the `202` and the report.

`POST /api/v1/audit/bulk` answers before it has done any work, so the archive has to survive the
response. The in-memory batch path (`POST /api/v1/padnext/batch`) keeps its files in the process
and pays for it: a restart mid-run loses them, and the startup recovery can only mark the job
`FAILED`. Writing the archive first is what buys the bulk path the property that matters for a
commercial integration — a job that was accepted is a job that will be processed, across a deploy.

    <UPLOAD_DIR>/bulk/<organisation>/<batch_id>/upload.zip

**Local disk, deliberately, and it is a real constraint rather than a placeholder.** No S3, no
bucket, no object store — the same reasoning that keeps Celery and Redis out of this MVP. What it
costs is stated rather than hidden: the directory is not shared between hosts, so a bulk job is
processed by the process that accepted it or by its successor on the same volume, and horizontal
scaling needs a shared store before it needs anything else here.

**It is not writable in the container by default, and that is on purpose.** `/srv` is root-owned
and the engine runs as uid 10001 precisely so that nothing in a request path can write into the
image. A deployment therefore mounts a volume and points `UPLOAD_DIR` at it;
`infra/docker/docker-compose.yml` does. A missing or unwritable directory is reported by
`ensure_upload_root` at startup, as a log line naming the path, rather than as a `500` on the first
partner who uploads anything.

**Retention is the deletion on the terminal transition.** The archive is removed when its job
reaches `COMPLETED` or `FAILED`, because that is the moment its bytes stop being needed and start
being only a liability — a PADnext delivery is billing data about identifiable treatment, and the
report derived from it is already in the database. `RETAIN_BULK_UPLOADS=true` keeps them for an
operator debugging a systematically failing integration, and the setting's docstring says what that
means. Nothing here implements a sweeper for orphans: a directory whose job row was deleted is
unreachable, and deleting files from a path no row names is a job for an operator with a retention
policy, not for a service that would be guessing.

**A path is never built from anything a client sent.** The organisation comes from an API key row,
the batch id is generated here, and the filename is a constant. `_segment` is defence in depth on
top of that — see it for what a hostile organisation id would have to be for it to fire.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
from pathlib import Path

from app.config import Settings, get_settings

log = logging.getLogger(__name__)

#: The archive's name inside its job directory. Constant, so nothing a caller supplied ever becomes
#: a filename — the uploaded `filename` is display metadata and is stored in the database.
BULK_ARCHIVE_NAME = "upload.zip"

#: What a path segment may contain. Better Auth ids are 32 characters of `[A-Za-z0-9]`, so this
#: passes every real value through unchanged and keeps the directory tree readable to an operator.
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _segment(value: str) -> str:
    """One path component, guaranteed to be one.

    An organisation id reaches this having come out of the `api_keys` table, which got it from a
    header the web tier set from a verified session — so in practice it is always already safe and
    this returns it unchanged. The fallback exists because "in practice" is doing load-bearing work
    in that sentence: the column is a `String(256)` with no format constraint, and the one thing a
    directory name must never be able to contain is `..` or a separator.

    Hashing rather than stripping the offending characters, because stripping is not injective:
    `a/b` and `ab` would strip to the same directory and one practice's uploads would land in
    another's. A SHA-256 prefix is ugly in `ls` and correct, which is the right way round for a
    tenancy boundary.
    """
    if SAFE_SEGMENT.match(value):
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    log.warning(
        "organisation id is not usable as a directory name; storing under its hash %s", digest
    )
    return digest


def bulk_job_dir(batch_id: str, *, organization_id: str, settings: Settings | None = None) -> Path:
    """`<UPLOAD_DIR>/bulk/<organisation>/<batch_id>`. Pure path arithmetic; touches no disk.

    Organisation-first rather than batch-first, because the directory layout is also the answer to
    two operational questions: "delete everything belonging to this practice" and "how much disk is
    this practice using" are both one path with this nesting and a full-tree walk with the other.
    """
    settings = settings or get_settings()
    root = settings.bulk_upload_dir
    return root / _segment(organization_id) / _segment(batch_id)


def ensure_upload_root(settings: Settings | None = None) -> bool:
    """Create `UPLOAD_DIR` if it is missing, and report whether it is usable.

    Called once from the lifespan. It returns a bool and logs rather than raising, because an
    engine whose upload directory is unwritable can still serve `/solve`, `/padnext/audit`,
    `/audit/single` and every read endpoint — refusing to start would take a working service down
    over one feature. The bulk endpoint answers `503` when it cannot write, which is the honest
    place for that failure to appear.
    """
    settings = settings or get_settings()
    root = settings.bulk_upload_dir
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".writable"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as exc:
        log.error(
            "upload directory %s is not writable (%s) — POST /api/v1/audit/bulk will answer 503. "
            "Mount a writable volume and set UPLOAD_DIR to it; /srv is deliberately read-only to "
            "the runtime user in the container image.",
            root,
            exc,
        )
        return False
    return True


def store_bulk_upload(
    content: bytes, *, batch_id: str, organization_id: str, settings: Settings | None = None
) -> Path:
    """Write the archive and return where it went. Raises `OSError` if it cannot.

    Not caught here. The caller is a request handler that has not yet answered, so it can still
    turn the failure into a `503` naming the directory — which is a much better outcome than a job
    row pointing at a file that was never written.
    """
    directory = bulk_job_dir(batch_id, organization_id=organization_id, settings=settings)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / BULK_ARCHIVE_NAME
    path.write_bytes(content)
    log.info("bulk upload for %s stored at %s (%d bytes)", batch_id, path, len(content))
    return path


def discard_bulk_upload(path: str | Path, *, settings: Settings | None = None) -> bool:
    """Delete a finished job's archive and the directory it sat in. Never raises.

    Returns whether the archive is now gone — so `True` for a successful delete *and* for one that
    was already missing, and `False` both when `RETAIN_BULK_UPLOADS` kept it deliberately and when
    the delete failed. The two `False` cases are not distinguished because no caller acts on the
    difference: both mean "a file is still on disk", one of them on purpose.

    Never, because this is called from the terminal transition of a background task: an upload that
    could not be deleted must not turn a `COMPLETED` job into a `FAILED` one — the report is
    already written and is what the caller asked for. The failure is logged, and what is left
    behind is a file an operator can remove.

    The path is re-checked against `UPLOAD_DIR` before anything is removed. It comes from
    `batch_jobs.upload_path`, which this module wrote, so the check should never fire — and it is
    here because the alternative to a redundant check on an `rmtree` is a service that will delete
    whatever a corrupted or hand-edited row happens to name.
    """
    settings = settings or get_settings()
    if not settings.retain_bulk_uploads:
        target = Path(path)
        root = settings.bulk_upload_dir
        try:
            resolved = target.resolve()
            if not resolved.is_relative_to(root.resolve()):
                log.error(
                    "refusing to delete %s: it is outside the upload directory %s", resolved, root
                )
                return False
            shutil.rmtree(resolved.parent, ignore_errors=False)
        except FileNotFoundError:
            # Already gone — a retried completion, or an operator who cleaned up. Not a failure.
            return True
        except OSError as exc:
            log.warning("could not delete bulk upload %s: %s", target, exc)
            return False
        return True

    log.info("keeping bulk upload %s (RETAIN_BULK_UPLOADS=true)", path)
    return False


__all__ = [
    "BULK_ARCHIVE_NAME",
    "SAFE_SEGMENT",
    "bulk_job_dir",
    "discard_bulk_upload",
    "ensure_upload_root",
    "store_bulk_upload",
]
