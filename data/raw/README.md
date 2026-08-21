# Raw GOÄ snapshots

Files here are unmodified downloads. `manifest.json` records the URL, retrieval
timestamp and SHA-256 so a catalog build can always be traced back to its source.

## If the automatic download failed

```
The official GOÄ snapshot could not be downloaded automatically.

Nothing is faked and no substitute source is used. Do one of the following:

 1. Download the official XML by hand and place it here:

        <repo>/backend/data/raw/

    Open https://www.gesetze-im-internet.de/go__1982/ and use the "XML" download
    (direct link: https://www.gesetze-im-internet.de/go__1982/xml.zip). Then run:

        python scripts/fetch_goae.py --local <downloaded-file>
        python scripts/import_goae.py

 2. Or, if you hold a licensed GOÄ dataset, place it under data/licensed/ (git-ignored)
    and run:

        python scripts/import_goae.py --input data/licensed/<your-file>

 3. Or run with the bundled illustrative catalog. It is clearly marked
    provenance="illustrative" and rule_coverage="partial" everywhere it surfaces:

        python scripts/import_goae.py --illustrative
```
