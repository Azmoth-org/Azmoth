"""The Azmoth monogram, as the bytes a PDF image XObject wants. Nothing else.

**Generated data. Regenerate with the snippet at the bottom of this docstring.**

## Why the report's logo is a committed blob and not a file read

`app/services/pdf.py` states two properties it will not give up: **no dependency** beyond the
standard library, and **byte-identical output for identical input**. A logo has to be reconciled with
both, and the obvious approaches fail one or the other.

* Reading a PNG from disk at render time needs a PNG *decoder* — the IDAT stream is zlib plus a
  per-scanline filter that has to be undone — which is either Pillow (a dependency, and a large one)
  or thirty lines of pixel arithmetic in the middle of a document writer.
* Fetching it, obviously, is worse.
* Compressing raw pixels at render time with `zlib.compress` would make the PDF's bytes depend on
  the zlib build of whichever machine rendered it. `test_pdf_report.py` asserts that two renders of
  one delivery are identical; it would still pass on any single machine and the *claim* would be
  false.

So what is committed is the **already-deflated stream**, exactly as it goes into the file. Rendering
it is `base64.b64decode` — standard library, no decoding of an image format, and the same bytes
everywhere forever.

## What it is

    128 x 128, 8 bits per component, /DeviceGray, /FlateDecode

Grayscale and flattened onto white, because `/DeviceGray` has no alpha channel and the page it lands
on is white. An `/SMask` would add a second stream and a second object to carry transparency that
nothing here needs.

128 px for a mark drawn at 26 pt is about 350 dpi at final size, which is above what any office
laser resolves. The whole thing is 4 kB deflated — smaller than one page of this report's text.

## Regenerating it

The monogram comes from the same trimmed asset the web applications use, so it cannot drift from
them. From the repository root:

    node -e '
      const sharp = require("sharp"), zlib = require("zlib");
      sharp("apps/marketing/public/brand/azmoth-mark.png")
        .resize(128, 128, { fit: "contain", background: "#ffffff" })
        .flatten({ background: "#ffffff" }).greyscale().raw().toBuffer()
        .then(raw => process.stdout.write(
          zlib.deflateSync(raw, { level: 9 }).toString("base64")));
    '

and paste the result below. A manual step on purpose: this runs perhaps once a year, and a build step
that needs a native image library to produce a constant is a build step that breaks in CI for no
benefit. `scripts/build-brand-assets.mjs` produces the input.
"""

from __future__ import annotations

import base64

#: Pixels per side. Square, because every surface that shows the mark reserves a square box.
MARK_WIDTH = 128
MARK_HEIGHT = 128

#: Bits per component, and the colour space. Named rather than inlined into the XObject dictionary
#: so a change here cannot leave the dictionary describing something the stream is not.
MARK_BITS = 8
MARK_COLOR_SPACE = "/DeviceGray"

#: The deflated pixel data, base64 of exactly what goes into the content stream. See the docstring.
_MARK_BASE64 = (
    "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"
    "3VL2K/x8rP/9Y1p9qt/o/n99HtZ/AWFEf1g="
)


def mark_stream() -> bytes:
    """The `/FlateDecode` stream for the monogram XObject.

    Decoded on every call rather than at import: this module is imported by anything that touches the
    PDF writer, including an OpenAPI export on a machine that will never render a report, and an
    eagerly decoded blob is memory held for the life of every such process. A `b64decode` of 5 kB is
    microseconds, and a report is rendered once per request.
    """
    return base64.b64decode(_MARK_BASE64)


__all__ = [
    "MARK_BITS",
    "MARK_COLOR_SPACE",
    "MARK_HEIGHT",
    "MARK_WIDTH",
    "mark_stream",
]
