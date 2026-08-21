#!/usr/bin/env python3
"""Zip the synthetic PADnext order file and payload into a `.padx` container.

A real delivery is a compressed pair: the unencrypted Auftragsdatei plus the payload. The two XML
files are committed in readable form — this only packages them, so the container path
(`app/padnext/reader.py` sniffing ZIP magic, reading `@echtdaten` from the order file) has something
to exercise and a demo has one file to drag in.

    python scripts/make_padnext_example.py

Deterministic by construction: ZIP entry timestamps are fixed, so rebuilding does not produce a
different file and dirty the working tree.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from app.config import PADNEXT_EXAMPLES_DIR  # noqa: E402

EXAMPLES = PADNEXT_EXAMPLES_DIR

ORDER = "00004711_20260726_ADL_000001.auf"
PAYLOAD = "00004711_20260726_ADL_000001_padx.xml"
CONTAINER = "00004711_20260726_ADL_000001.padx"

#: Fixed so the container is byte-stable across rebuilds.
FIXED_DATE = (2026, 7, 26, 9, 30, 0)


def build(target: Path | None = None) -> Path:
    out = target or (EXAMPLES / CONTAINER)
    missing = [n for n in (ORDER, PAYLOAD) if not (EXAMPLES / n).is_file()]
    if missing:
        raise SystemExit(f"missing source file(s): {', '.join(missing)}")

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
