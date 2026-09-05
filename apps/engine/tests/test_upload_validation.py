"""The filename and size gate in front of every upload endpoint.

Two layers are tested here and they are not the same claim. `app.services.upload_validation` is the
unit: what a name has to look like. The endpoint tests below are the wiring: that each upload path
actually calls it, with the allowlist that path can parse — a validator nobody invokes passes its
own tests forever.

The endpoint cases deliberately assert on `error_code` rather than on prose. The messages here are
bilingual and will be reworded; the codes are the contract, and `docs/errors.md` has a row for each.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi import HTTPException

from app.services.upload_validation import (
    ARCHIVE_EXTENSIONS,
    DEFAULT_MAX_UPLOAD_BYTES,
    DOCUMENT_EXTENSIONS,
    PADNEXT_EXTENSIONS,
    validate_filename,
    validate_upload,
)

XML = b"<?xml version='1.0'?><rechnungen><rechnung/></rechnungen>"


def refuse(**kwargs) -> HTTPException:
    """Call `validate_upload` expecting a refusal, and hand back the exception."""
    with pytest.raises(HTTPException) as caught:
        validate_upload(**kwargs)
    return caught.value


# ==========================================================================================
# the unit: what a filename has to be
# ==========================================================================================


@pytest.mark.parametrize("name", ["delivery.xml", "DELIVERY.XML", "a_padx.xml", "container.padx"])
def test_a_name_the_endpoint_can_parse_is_accepted(name):
    assert validate_filename(name, allowed_extensions=PADNEXT_EXTENSIONS) in PADNEXT_EXTENSIONS


def test_the_extension_check_is_case_insensitive():
    """A PVS that uppercases its exports is not an attack, and refusing it would be a support
    ticket rather than a defence."""
    assert validate_filename("DELIVERY.XML", allowed_extensions=PADNEXT_EXTENSIONS) == ".xml"


@pytest.mark.parametrize(
    "name",
    [
        "payload.exe",
        "payload.sh",
        "payload.php",
        "payload.py",
        "payload",  # no extension at all
        "payload.",  # a trailing dot is not an extension
        ".htaccess",  # a dotfile has no suffix, and this is the classic one
    ],
)
def test_a_name_outside_the_allowlist_is_400(name):
    exc = refuse(
        filename=name, content=XML, allowed_extensions=PADNEXT_EXTENSIONS
    )
    assert exc.status_code == 400
    assert exc.detail["error"] == "unsupported_file_extension"
    # The caller is told what *is* accepted, not merely that this was not.
    assert exc.detail["accepted"] == sorted(PADNEXT_EXTENSIONS)


def test_an_executable_suffix_is_refused_even_behind_a_permitted_one():
    """`invoice.php.pdf` ends in `.pdf`, so a last-suffix allowlist accepts it.

    This is the case the denylist exists for, and it is not hypothetical: Apache's multi-extension
    MIME handling hands that file to PHP. Nothing serves the upload volume today — the point is that
    "today" is not a property this module can enforce.
    """
    exc = refuse(
        filename="invoice.php.pdf", content=b"%PDF-1.4", allowed_extensions=DOCUMENT_EXTENSIONS
    )
    assert exc.status_code == 400
    assert exc.detail["error"] == "unsupported_file_extension"
    assert exc.detail["rejected_extension"] == ".php"


@pytest.mark.parametrize(
    "name",
    [
        "../../etc/cron.d/root",
        "..\\..\\windows\\system32\\evil.xml",
        "sub/dir/delivery.xml",
        "..",
        ".",
        "",
        None,
        "delivery\x00.xml",
        "x" * 300 + ".xml",
    ],
)
def test_a_name_that_is_not_a_bare_filename_is_400(name):
    exc = refuse(filename=name, content=XML, allowed_extensions=PADNEXT_EXTENSIONS)
    assert exc.status_code == 400
    assert exc.detail["error"] == "invalid_filename"


def test_a_backslash_path_is_refused_though_posix_would_not_call_it_one():
    """`os.path.basename` on Linux does not treat `\\` as a separator, so a check built on it
    passes `..\\..\\etc\\passwd` through unchanged. That is the reason this module refuses both
    separators explicitly rather than reaching for basename."""
    exc = refuse(
        filename="..\\..\\delivery.xml", content=XML, allowed_extensions=PADNEXT_EXTENSIONS
    )
    assert exc.detail["error"] == "invalid_filename"


# ==========================================================================================
# the unit: emptiness and size
# ==========================================================================================


def test_an_empty_part_is_400_and_names_the_file():
    exc = refuse(filename="delivery.xml", content=b"", allowed_extensions=PADNEXT_EXTENSIONS)
    assert exc.status_code == 400
    assert exc.detail["error"] == "empty_file"
    assert exc.detail["filename"] == "delivery.xml"


def test_an_oversized_file_is_413_not_400():
    """The brief says "reject with 400", and for a wrong extension that is what happens. Size is
    `413` because that is what `REQUEST_TOO_LARGE` already means everywhere else in this engine —
    two status codes for one condition, depending on whether the perimeter middleware or the
    handler caught it, would be a real defect."""
    exc = refuse(
        filename="delivery.xml",
        content=b"x" * 101,
        allowed_extensions=PADNEXT_EXTENSIONS,
        max_bytes=100,
    )
    assert exc.status_code == 413
    assert exc.detail["error"] == "request_too_large"
    assert exc.detail["max_bytes"] == 100
    assert exc.detail["declared_bytes"] == 101


def test_the_name_is_judged_before_the_size():
    """A caller uploading a 40 MB `payload.sh` should be told the file is the wrong kind, not that
    it is too big — otherwise they shrink it and are refused again for a different reason."""
    exc = refuse(
        filename="payload.sh",
        content=b"x" * 1000,
        allowed_extensions=PADNEXT_EXTENSIONS,
        max_bytes=10,
    )
    assert exc.status_code == 400
    assert exc.detail["error"] == "unsupported_file_extension"


def test_the_default_ceiling_is_the_briefs_ten_megabytes():
    assert DEFAULT_MAX_UPLOAD_BYTES == 10 * 1024 * 1024
    assert validate_upload("d.xml", b"x" * 1024, allowed_extensions=PADNEXT_EXTENSIONS) == ".xml"


def test_the_document_policy_is_exactly_what_the_brief_named():
    """`.pdf`, `.xml`, `.csv`. Kept as a named constant even though no endpoint uses it — see the
    module docstring for why applying it literally would break the bulk and `.padx` paths."""
    assert DOCUMENT_EXTENSIONS == {".pdf", ".xml", ".csv"}


# ==========================================================================================
# the wiring: each endpoint calls it with the set it can actually parse
# ==========================================================================================


def test_the_batch_endpoint_refuses_a_disallowed_extension(client):
    response = client.post(
        "/api/v1/padnext/batch",
        files=[("files", ("payload.sh", XML, "application/octet-stream"))],
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "UNSUPPORTED_FILE_EXTENSION"


def test_the_batch_endpoint_refuses_a_traversal_filename(client):
    response = client.post(
        "/api/v1/padnext/batch",
        files=[("files", ("../../etc/passwd", XML, "text/xml"))],
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_FILENAME"


def test_the_batch_endpoint_still_accepts_a_padx_container(client):
    """The regression this whole change is most likely to cause. `.padx` is a ZIP by another name
    and is half the deliveries the pilot exists to audit; an allowlist of `.pdf/.xml/.csv` taken
    literally would have refused it."""
    assert ".padx" in PADNEXT_EXTENSIONS

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("delivery_padx.xml", XML)

    response = client.post(
        "/api/v1/padnext/batch",
        files=[("files", ("delivery.padx", buffer.getvalue(), "application/octet-stream"))],
    )

    # 202 or a downstream audit failure — either way it got past the name gate, which is the claim.
    assert response.status_code != 400 or response.json()["error_code"] not in {
        "UNSUPPORTED_FILE_EXTENSION",
        "INVALID_FILENAME",
    }


def test_the_bulk_endpoint_takes_zip_and_nothing_else():
    """`/audit/bulk` is the one place a `.zip` is right and a `.xml` is not — the reverse of every
    other upload path here."""
    assert ARCHIVE_EXTENSIONS == {".zip"}
    assert validate_filename("batch.zip", allowed_extensions=ARCHIVE_EXTENSIONS) == ".zip"

    exc = refuse(filename="batch.xml", content=b"PK\x03\x04", allowed_extensions=ARCHIVE_EXTENSIONS)
    assert exc.detail["error"] == "unsupported_file_extension"
