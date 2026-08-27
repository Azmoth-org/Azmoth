#!/usr/bin/env python3
"""Fetch an official GOÄ snapshot and record its provenance.

Source of record
----------------
The GOÄ (Gebührenordnung für Ärzte) is federal secondary legislation. Its consolidated text,
*including the Gebührenverzeichnis*, is published by the Bundesamt für Justiz at
gesetze-im-internet.de as XML. German law (§ 5 UrhG) places official works in the public
domain, so this text may be redistributed — which is why the derived catalog is committed.

This script does not scrape commercial GOÄ databases, Kommentare, or any paid catalog. If you
have licensed data, put it in ``data/licensed/`` (git-ignored) and point the importer at it.

    python scripts/fetch_goae.py                 # official source
    python scripts/fetch_goae.py --url ...       # or an explicit URL
    python scripts/fetch_goae.py --local FILE    # or a file you downloaded yourself
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE_ROOT))

from app.config import RAW_DIR  # noqa: E402

MANIFEST_PATH = RAW_DIR / "manifest.json"

DEFAULT_SOURCE_URL = "https://www.gesetze-im-internet.de/go__1982/xml.zip"
SOURCE_NAME = "Gebührenordnung für Ärzte (GOÄ), konsolidierte Fassung"
SOURCE_PUBLISHER = "Bundesamt für Justiz / Bundesministerium der Justiz — gesetze-im-internet.de"

OFFLINE_INSTRUCTIONS = """\
The official GOÄ snapshot could not be downloaded automatically.

Nothing is faked and no substitute source is used. Do one of the following:

 1. Download the official XML by hand and place it here:

        {raw_dir}/

    Open https://www.gesetze-im-internet.de/go__1982/ and use the "XML" download
    (direct link: {url}). Then run:

        python scripts/fetch_goae.py --local <downloaded-file>
        python scripts/import_goae.py

 2. Or, if you hold a licensed GOÄ dataset, place it under data/licensed/ (git-ignored)
    and run:

        python scripts/import_goae.py --input data/licensed/<your-file>

 3. Or run with the bundled illustrative catalog. It is clearly marked
    provenance="illustrative" and rule_coverage="partial" everywhere it surfaces:

        python scripts/import_goae.py --illustrative
"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_if_zip(path: Path) -> Path:
    """gesetze-im-internet.de serves a zip containing a single XML document."""
    if not zipfile.is_zipfile(path):
        return path
    with zipfile.ZipFile(path) as archive:
        members = [n for n in archive.namelist() if n.lower().endswith(".xml")]
        if not members:
            raise RuntimeError(f"{path.name} is a zip but contains no .xml member")
        if len(members) > 1:
            raise RuntimeError(
                f"{path.name} contains {len(members)} XML members; expected exactly one: {members}"
            )
        target = path.with_suffix(".xml")
        with archive.open(members[0]) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return target


def download(url: str, timeout: float) -> Path:
    import urllib.error
    import urllib.request

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / "goae_source.zip"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "azmoth-goae-fetcher/0.3 (+official GOÄ snapshot fetcher)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status} from {url}")
            with open(target, "wb") as fh:
                shutil.copyfileobj(response, fh)
    except (urllib.error.URLError, OSError, RuntimeError) as exc:
        raise RuntimeError(f"could not fetch {url}: {exc}") from exc
    return target


def write_manifest(raw_file: Path, *, url: str, note: str = "") -> dict:
    manifest = {
        "source_url": url,
        "source_name": SOURCE_NAME,
        "publisher": SOURCE_PUBLISHER,
        "legal_status": "Amtliches Werk, gemeinfrei nach § 5 UrhG — redistribution permitted",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "raw_file": raw_file.name,
        "sha256": sha256_file(raw_file),
        "bytes": raw_file.stat().st_size,
    }
    if note:
        manifest["note"] = note
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def write_offline_readme(url: str) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "README.md").write_text(
        "# Raw GOÄ snapshots\n\n"
        "Files here are unmodified downloads. `manifest.json` records the URL, retrieval\n"
        "timestamp and SHA-256 so a catalog build can always be traced back to its source.\n\n"
        "## If the automatic download failed\n\n```\n"
        + OFFLINE_INSTRUCTIONS.format(raw_dir=RAW_DIR, url=url)
        + "```\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--url",
        default=os.environ.get("GOAE_SOURCE_URL", DEFAULT_SOURCE_URL),
        help="source URL (env: GOAE_SOURCE_URL)",
    )
    parser.add_argument("--local", help="use a file already on disk instead of downloading")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    write_offline_readme(args.url)

    if args.local:
        source = Path(args.local)
        if not source.exists():
            print(f"error: {source} does not exist", file=sys.stderr)
            return 2
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        landed = RAW_DIR / source.name
        if source.resolve() != landed.resolve():
            shutil.copy2(source, landed)
        raw = _extract_if_zip(landed)
        manifest = write_manifest(raw, url=f"file://{source.resolve()}", note="user-provided local file")
    else:
        print(f"fetching {args.url}")
        try:
            downloaded = download(args.url, args.timeout)
        except RuntimeError as exc:
            print(f"\nerror: {exc}\n", file=sys.stderr)
            print(OFFLINE_INSTRUCTIONS.format(raw_dir=RAW_DIR, url=args.url), file=sys.stderr)
            return 1
        raw = _extract_if_zip(downloaded)
        manifest = write_manifest(raw, url=args.url)

    print(f"raw file : {raw}")
    print(f"bytes    : {manifest['bytes']:,}")
    print(f"sha256   : {manifest['sha256']}")
    print(f"manifest : {MANIFEST_PATH}")
    print("\nnext: python scripts/import_goae.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
