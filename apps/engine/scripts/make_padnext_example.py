#!/usr/bin/env python3
"""Zip the synthetic PADnext order file and payload into a `.padx` container.

A real delivery is a compressed pair: the unencrypted Auftragsdatei plus the payload. The two XML
files are committed in readable form — this only packages them, so the container path
(`app/padnext/reader.py` sniffing ZIP magic, reading `@echtdaten` from the order file) has something
to exercise and a demo has one file to drag in.

    python scripts/make_padnext_example.py

Deterministic by construction: ZIP entry timestamps are fixed, so rebuilding does not produce a
different file and dirty the working tree.

**This also guards a second, unrelated copy of the same payload.** `PAYLOAD` below is committed
twice: here, as the golden `case_a_known_answer` fixture, and again — by hand, because it predates
this script and is meant to be dragged into the upload box directly rather than unpacked from a
container — at `padnext_example/`. The two diverged once: an edit here fixed position 6's
`<punktwert>` from a cents figure to the euro one the arithmetic actually uses, and nobody carried
the fix to the other copy, so the bundled example kept producing an extra, undocumented finding
that this file's own comment no longer described. `check_bundled_example_matches_canonical` below
is what a rebuild now catches that with, rather than a customer noticing the mismatch first.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from app.config import PADNEXT_EXAMPLES_DIR, REPO_ROOT  # noqa: E402

EXAMPLES = PADNEXT_EXAMPLES_DIR

ORDER = "00004711_20260726_ADL_000001.auf"
PAYLOAD = "00004711_20260726_ADL_000001_padx.xml"
CONTAINER = "00004711_20260726_ADL_000001.padx"

#: The second, hand-maintained copy of `PAYLOAD` — see the module docstring. Not `PADNEXT_EXAMPLES_DIR`:
#: that resolves to `logic/tests/cases/padnext/`, this is the top-level directory a person drags a
#: file out of.
BUNDLED_EXAMPLE_DIR = REPO_ROOT / "padnext_example"

#: Fixed so the container is byte-stable across rebuilds.
FIXED_DATE = (2026, 7, 26, 9, 30, 0)

#: The two spellings of `@echtdaten` that mean test data. `parse_echtdaten` also accepts `1`/`true`
#: for production data, which this example must never claim.
#:
#: The attribute has to be on the *payload* root and not only on the `.auf` order file, even though
#: the PADnext specification puts it on `<auftrag>`: an undeclared delivery is refused with
#: `422 ECHTDATEN_UNDECLARED` (`app/padnext/audit.py`), and the public demo, every test, and anyone
#: dragging the bare `*_padx.xml` into the upload box read this payload *without* its container,
#: where there is no `<auftrag>` to inherit the declaration from. `resolve_echtdaten` in
#: `app/padnext/reader.py` reads the order file first and the payload root second, for that reason.
#: The example shipped without it once, and the symptom was the demo file being rejected by the demo.
_SYNTHETIC_VALUES = ('echtdaten="0"', 'echtdaten="false"')


def check_declares_test_data(payload: Path) -> None:
    """Refuse to package a payload that does not declare itself synthetic.

    The container is what a demo drags in, so a payload that cannot say what it is produces a
    `422` at exactly the moment somebody is being shown the product. Checking here rather than
    trusting the committed file is the difference between that failure surfacing in this script,
    which one person runs deliberately, and surfacing in front of a customer.

    Comments are stripped before the root element is located, so the long note *about* the
    attribute at the top of the committed payload cannot satisfy the check on its own.
    """
    text = payload.read_text(encoding="utf-8")
    without_comments = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    match = re.search(r"<rechnungen\b[^>]*>", without_comments, re.DOTALL)
    root = (match.group(0) if match else "").replace(" ", "").replace("\n", "").replace("'", '"')

    if not any(value in root for value in _SYNTHETIC_VALUES):
        raise SystemExit(
            f"{payload.name}: <rechnungen> does not declare echtdaten=\"0\". A bare payload with no "
            "declaration is refused with 422 ECHTDATEN_UNDECLARED — add the attribute to the root "
            "element, not only to the .auf order file."
        )


def _without_comments(text: str) -> str:
    """The XML with every `<!-- ... -->` block removed.

    Both copies of `PAYLOAD` open with one long comment explaining the file — necessarily worded
    differently, because one talks about the `.padx` container this script builds and the other
    about being dragged into the upload box bare. Stripping comments before comparing is what lets
    the two prose introductions differ freely while the billing data they introduce may not.
    """
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def check_bundled_example_matches_canonical(canonical: Path) -> None:
    """The billing content of `padnext_example/{PAYLOAD}` must equal this file's, exactly.

    The one permitted difference is `@echtdaten`'s spelling: this file uses `"false"`, and the
    bundled copy uses `"0"` — added deliberately so a bare drag-and-drop of *that* file still
    declares itself before `app/padnext/audit.py` gets to ask. `_SYNTHETIC_VALUES` is the pair this
    script already accepts for its own copy; normalising both files to the first of the two before
    comparing is what lets that one difference through without also letting a `<punktwert>`, a
    `<gesamtbetrag>` or anything else drift silently a second time.

    Run from `build()`, even though the bundled file is never zipped into `CONTAINER`: rebuilding
    the fixture is the moment a developer who just edited a position is already in this script, and
    catching the drift here means the failure is a `SystemExit` with the fix in its message, not a
    customer's demo showing a finding this file's own comment no longer promises.
    """
    bundled = BUNDLED_EXAMPLE_DIR / PAYLOAD
    if not bundled.is_file():
        raise SystemExit(f"missing bundled example: {bundled}")

    def normalised(path: Path) -> str:
        text = _without_comments(path.read_text(encoding="utf-8"))
        for value in _SYNTHETIC_VALUES:
            text = text.replace(value, _SYNTHETIC_VALUES[0])
        return text

    ours, theirs = normalised(canonical), normalised(bundled)
    if ours != theirs:
        raise SystemExit(
            f"{bundled} has drifted from {canonical}: same file, two committed copies, and their "
            "billing content (everything outside the XML comments) no longer matches byte for "
            f"byte. Re-derive {bundled} from {canonical} — copy it, then re-apply only the "
            "echtdaten=\"0\" attribute and the copy's own introductory comment — and re-run this "
            "script."
        )


def build(target: Path | None = None) -> Path:
    out = target or (EXAMPLES / CONTAINER)
    missing = [n for n in (ORDER, PAYLOAD) if not (EXAMPLES / n).is_file()]
    if missing:
        raise SystemExit(f"missing source file(s): {', '.join(missing)}")

    check_declares_test_data(EXAMPLES / PAYLOAD)
    check_bundled_example_matches_canonical(EXAMPLES / PAYLOAD)

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in (ORDER, PAYLOAD):
            info = zipfile.ZipInfo(filename=name, date_time=FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, (EXAMPLES / name).read_bytes())
    return out


if __name__ == "__main__":
    written = build()
    print(f"wrote {written} ({written.stat().st_size} bytes)")
    sys.exit(0)
