# Licensed GOÄ data

Drop a licensed GOÄ dataset here and point the importer at it:

    python scripts/import_goae.py --input data/licensed/<your-file>

Everything in this directory except this README is git-ignored, so licensed material cannot be
committed by accident. Check your licence before redistributing anything from here.

The bundled catalog does not need this: it is built from the official GOÄ text published at
gesetze-im-internet.de, which is an amtliches Werk and public domain under § 5 UrhG.

## The official PADneXt schema

Same rule, different artefact. `app/padnext/schema.py` validates the framing of every delivery
against `data/schemas/padnext/padx_adl_v2.12.subset.xsd` — a subset we wrote, because the official
`padx_adl_v2.12.xsd` is a trade association's interface specification and carries no § 5 UrhG
exemption, so it is not committed here.

If you hold it under a licence that permits it, put it at:

    data/licensed/padnext/padx_adl_v2.12.xsd

`Settings.padnext_xsd_path` prefers it automatically — no code change, no restart of anything but
the process. Expect it to be stricter than the subset: a real conforming schema requires
`goziffer/@ziffer` and types every amount, so deliveries this engine deliberately audits-with-findings
today will be refused outright. `PADNEXT_SCHEMA_POLICY=warn` is the way to see what it would reject
before making it fatal.
