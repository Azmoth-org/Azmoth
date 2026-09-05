"""What an uploaded file has to be before any of it is parsed, opened or written.

## This is the *second* gate, not the first

`app.padnext.formats.detect_format` already classifies every upload by its leading bytes, and that
check is the stronger of the two: it is what catches a PDF named `delivery.xml`, and its docstring
is emphatic that nothing should look at a name. Nothing here contradicts that. `detect_format`
answers *"what are these bytes"*, which decides whether the engine can parse them; this module
answers *"what is this file called and how big is it"*, which decides whether it is safe to have
received it at all.

Both are needed because they fail differently and the difference is not academic:

* A file whose bytes are XML and whose name is `../../etc/cron.d/root` is perfectly parseable. Byte
  sniffing has no opinion on it whatsoever.
* A file whose bytes are XML and whose name is `payload.xml.sh` is parseable too, and is the shape
  of an upload that becomes a problem the moment anything on the box treats the directory as
  anything but opaque bytes.
* A 400 MB file is refused here having cost one length check, rather than after
  `zipfile`/`lxml` have been asked what is inside it.

So: names are validated, never trusted, and never used to decide a *format*.

## Why the extension allowlist is not configurable

`upload_max_bytes` is a setting because operators legitimately tune it — a practice with larger
deliveries raises it and nothing about the threat model changes. The extension allowlist is a
frozen constant in this file instead, and that asymmetry is deliberate. An env var that widens an
allowlist is a security control that is one typo in a `.env` away from being off, and the failure is
silent: the deployment keeps working, and nobody discovers `UPLOAD_EXTENSIONS=.pdf,.xml,.csv,.php`
until it matters. The set of formats this engine can actually parse is a property of the code, not
of a deployment, so it lives with the code.

## The three sets, and why there is more than one

The pilot brief names `.pdf`, `.xml` and `.csv` — that is `DOCUMENT_EXTENSIONS`, and it is the right
policy for a general document intake. It is *not* the right policy for the endpoints this engine
actually has, and applying it literally would break the product in two places rather than harden it:

* A PADnext delivery is a `*_padx.xml` **or** a `.padx` container. `.padx` is a ZIP by another name
  (`app.padnext.formats` recognises it by its `PK\\x03\\x04` header, not its suffix), and refusing it
  would refuse half the deliveries the pilot exists to audit.
* `POST /api/v1/audit/bulk` takes a `.zip` of many deliveries. That is the commercial bulk contract
  documented in `docs/api/PARTNER_API.md`.

Neither `.pdf` nor `.csv` is a valid input to any upload endpoint here — `_refuse_wrong_format` in
`app.api.audit` *explicitly rejects* a PDF body, and has a bilingual message for it. So an allowlist
of exactly `{.pdf, .xml, .csv}` would simultaneously forbid two formats the engine needs and permit
two it has no reader for, which is worse than either the status quo or the intent behind the brief.

The intent is what is implemented: every endpoint declares the narrowest set it can actually parse,
and anything outside it is a `400`. `DOCUMENT_EXTENSIONS` is kept as the named default for a future
intake endpoint that really does take documents, so the brief's policy has a home rather than being
silently dropped.

## The denylist is not redundant with the allowlist

`_DANGEROUS_EXTENSIONS` looks like belt-and-braces over an allowlist that already rejects everything
not named — and for the *final* suffix it is. It is not redundant for the ones before it. `Path`
reports the suffix of `invoice.php.pdf` as `.pdf`, which the allowlist accepts; a web server
configured with Apache's multi-extension MIME handling would nonetheless hand that file to PHP. No
such server sits in front of the upload volume today, and the whole point of the check is that
"today" is not a property this file can enforce.
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from pathlib import PurePosixPath

from fastapi import HTTPException

log = logging.getLogger(__name__)

#: Per-file ceiling when a caller names none. 10 MiB, from the pilot hardening brief.
#:
#: Every upload endpoint in this engine currently passes its own, stricter, number instead — 5 MiB
#: on `/audit/single`, 8 MiB per member on `/padnext/batch` — so this is the floor a new endpoint
#: gets for free rather than a limit anything relies on today. It is expressed in MiB rather than
#: MB because every other size in this codebase is, and having one "MB" mean 10**6 while its
#: neighbours mean 2**20 is a discrepancy that only ever surfaces in an argument about a rejected
#: file.
DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024

#: The general document policy: `.pdf`, `.xml`, `.csv`.
#:
#: Not currently the allowlist of any endpoint, and the module docstring says why — no upload
#: endpoint here reads a PDF or a CSV. Named and exported so that the policy exists in one place
#: when an intake endpoint needs it, instead of being re-typed from the brief months later.
DOCUMENT_EXTENSIONS = frozenset({".pdf", ".xml", ".csv"})

#: What a PADnext delivery may be called: a bare payload or a container.
#:
#: The container's real test is its `PK\x03\x04` header — see `app.padnext.formats` — and this only
#: says the *name* is not obviously something else.
PADNEXT_EXTENSIONS = frozenset({".xml", ".padx"})

#: What `POST /api/v1/audit/bulk` may be called. One archive holding many deliveries.
ARCHIVE_EXTENSIONS = frozenset({".zip"})

#: Suffixes refused anywhere in a filename, not merely at the end. See the module docstring for the
#: `invoice.php.pdf` case this exists for.
#:
#: Not exhaustive, and it does not need to be: the allowlist is what decides acceptance, and this
#: only removes the narrow class of names that an allowlist checking the final suffix would let
#: through. Adding to it is cheap; relying on it alone would not be.
_DANGEROUS_EXTENSIONS = frozenset(
    {
        ".ashx",
        ".asp",
        ".aspx",
        ".bat",
        ".cgi",
        ".cmd",
        ".com",
        ".dll",
        ".exe",
        ".htaccess",
        ".jar",
        ".js",
        ".jsp",
        ".jspx",
        ".mjs",
        ".msi",
        ".phar",
        ".php",
        ".php3",
        ".php4",
        ".php5",
        ".php7",
        ".phps",
        ".phtml",
        ".pl",
        ".ps1",
        ".py",
        ".pyc",
        ".rb",
        ".scr",
        ".sh",
        ".so",
        ".svg",
        ".swf",
        ".vbs",
        ".war",
        ".wsf",
    }
)

#: Longest filename accepted. Generous for a real delivery name and far below any filesystem limit,
#: so a 4 kB name cannot reach a log line, a database column or a path join.
MAX_FILENAME_LENGTH = 255


def _reject(
    status_code: int, error: str, message: str, **details: object
) -> HTTPException:
    """Build the refusal in the shape `app.api.errors.http_exception_handler` expects.

    `error` becomes `error_code` upper-cased and every other key lands in `details`, so a refusal
    raised here is indistinguishable from one raised by a route — same envelope, same catalogued
    code, and the client's existing error handling covers it without being told about a new shape.
    """
    return HTTPException(status_code=status_code, detail={"error": error, "message": message, **details})


def validate_filename(filename: str | None, *, allowed_extensions: Collection[str]) -> str:
    """Check the name alone and return the accepted lower-cased suffix. Raises on anything else.

    Split out from `validate_upload` because it is useful on its own: a caller streaming a large
    upload wants to refuse the name before it has read a single byte, and a caller iterating an
    archive's members has a name and no separate content to check.

    The traversal check is the reason `PurePosixPath` appears here and the reason a bare
    `os.path.basename` would not do. `basename` on Linux does not treat `\\` as a separator, so
    `..\\..\\etc\\passwd` passes through it unchanged — harmless on this host, and exactly the kind
    of value that stops being harmless the moment a name is echoed into something running on
    Windows or joined by a client. The separators are refused outright rather than stripped: a name
    containing one is a caller sending a path where a filename belongs, which is a bug worth
    reporting rather than silently correcting into something else.
    """
    name = (filename or "").strip()

    if not name:
        raise _reject(
            400,
            "invalid_filename",
            "Die hochgeladene Datei hat keinen Namen. — The upload carries no filename; a "
            "multipart part must declare one.",
        )

    if len(name) > MAX_FILENAME_LENGTH:
        raise _reject(
            400,
            "invalid_filename",
            f"Der Dateiname ist {len(name)} Zeichen lang; erlaubt sind höchstens "
            f"{MAX_FILENAME_LENGTH}. — The filename is too long.",
            max_length=MAX_FILENAME_LENGTH,
        )

    if "\x00" in name:
        raise _reject(
            400,
            "invalid_filename",
            "Der Dateiname enthält ein Nullbyte. — The filename contains a NUL byte.",
        )

    if "/" in name or "\\" in name or name in {".", ".."}:
        # Logged, unlike the other refusals in this function. A long name or a missing one is a
        # client bug; a path separator in a filename field is the signature of somebody trying to
        # write outside the upload directory, and it should be visible in the log without anyone
        # having enabled debug logging first.
        log.warning("upload refused: filename %r contains a path component", name)
        raise _reject(
            400,
            "invalid_filename",
            "Der Dateiname darf keinen Pfad enthalten. — The filename must be a bare name, not a "
            "path.",
        )

    # Every suffix, not just the last. `PurePosixPath("a.php.pdf").suffixes` is `[".php", ".pdf"]`.
    suffixes = [suffix.lower() for suffix in PurePosixPath(name).suffixes]
    dangerous = sorted(set(suffixes) & _DANGEROUS_EXTENSIONS)
    if dangerous:
        log.warning("upload refused: filename %r carries executable suffix(es) %s", name, dangerous)
        raise _reject(
            400,
            "unsupported_file_extension",
            f"Der Dateiname enthält die unzulässige Endung {dangerous[0]!r}. — The filename "
            f"carries a disallowed executable extension.",
            rejected_extension=dangerous[0],
            accepted=sorted(allowed_extensions),
        )

    # `suffixes` is empty for a name with no dot at all *and* for a dotfile such as `.htaccess`,
    # which `PurePosixPath` treats as a stem rather than a suffix. Both land here and are refused,
    # which is the outcome wanted for each.
    extension = suffixes[-1] if suffixes else ""
    if extension not in allowed_extensions:
        raise _reject(
            400,
            "unsupported_file_extension",
            f"Dateityp {extension or '(ohne Endung)'} wird hier nicht angenommen; erlaubt sind "
            f"{', '.join(sorted(allowed_extensions))}. — This endpoint accepts only "
            f"{', '.join(sorted(allowed_extensions))}.",
            rejected_extension=extension,
            accepted=sorted(allowed_extensions),
        )

    return extension


def validate_upload(
    filename: str | None,
    content: bytes,
    *,
    allowed_extensions: Collection[str],
    max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> str:
    """Name, then emptiness, then size. Returns the accepted suffix; raises `HTTPException`.

    **Name first, deliberately.** Checking size first would be marginally cheaper, but it would
    also mean that a caller uploading a 40 MB `payload.sh` is told the file is too large — and so
    retries it smaller, and is told the same thing again in a different way. Refusing the thing that
    is categorically wrong before the thing that is quantitatively wrong gives a client one error to
    fix rather than two in sequence.

    **`413` for the size, `400` for everything else.** The brief this implements says "reject with
    400", and for a wrong extension that is exactly right — it is a bad request in the plain sense.
    An oversized body is `413` because that is what `docs/errors.md` already says
    `REQUEST_TOO_LARGE` is, what `RequestSizeLimitMiddleware` already answers at the perimeter, and
    what the two existing upload endpoints already return. Two status codes for one condition,
    depending on whether the limiter or the handler caught it first, would be a genuine defect.

    The size check here is not a substitute for `RequestSizeLimitMiddleware`. That one screens on
    `Content-Length` and refuses before the body is buffered, which is the check that matters for
    resource exhaustion; this one is what holds for a chunked upload that declared no length, and
    it is per-file rather than per-request — a 60 MB multipart body of ten 6 MB parts is under any
    request ceiling and over this one.
    """
    extension = validate_filename(filename, allowed_extensions=allowed_extensions)

    if not content:
        raise _reject(
            400,
            "empty_file",
            f"{filename!r} ist leer. — {filename!r} is empty; an empty part is a client bug, not a "
            "delivery.",
            filename=filename,
        )

    if len(content) > max_bytes:
        raise _reject(
            413,
            "request_too_large",
            f"{filename!r} ist {len(content)} Bytes gross; erlaubt sind höchstens {max_bytes}. — "
            f"{filename!r} exceeds the per-file limit for this endpoint.",
            filename=filename,
            max_bytes=max_bytes,
            declared_bytes=len(content),
        )

    log.debug(
        "upload accepted: %r (%s, %d bytes, limit %d)", filename, extension, len(content), max_bytes
    )
    return extension


__all__ = [
    "ARCHIVE_EXTENSIONS",
    "DEFAULT_MAX_UPLOAD_BYTES",
    "DOCUMENT_EXTENSIONS",
    "MAX_FILENAME_LENGTH",
    "PADNEXT_EXTENSIONS",
    "validate_filename",
    "validate_upload",
]
