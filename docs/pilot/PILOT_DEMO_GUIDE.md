# Pilot Demo Guide

**Week 3 — the pilot.** One page, printable, to be followed live in front of a practice or a PVS.
Every command below is copy-pasteable and was run against this build.

Two things to have decided before you open a terminal in front of anyone:

- **Which policy the stack is running.** `PADNEXT_SCHEMA_POLICY=warn` for a pilot against real
  exports; `strict` for the synthetic demo below. § 0 says how to check without guessing.
- **That the delivery is synthetic, and that it says so.** `PADNEXT_ALLOW_REAL_DATA` is `false` in
  both compose files, so a delivery flagged `echtdaten="true"` is refused with
  `REAL_DATA_REFUSED` — by design, and not something to work around on a laptop.

  A delivery that says *nothing* is refused too, with `ECHTDATEN_UNDECLARED`: only `"0"` and
  `"false"` get through, and `"ja"`, an empty value or a missing attribute do not. **If a practice
  brings their own export to the demo, it will almost certainly be refused on this**, and that is
  the moment to show them `scripts/anonymize_padnext.py` rather than the moment to be surprised:

  ```bash
  python3 scripts/anonymize_padnext.py ihr-export.padx -o demo.padx
  ```

  It needs nothing but Python 3.9, runs on their machine, and never touches the original. See
  [`ANONYMIZATION_SPEC.md`](ANONYMIZATION_SPEC.md) — written to be handed to their DSB — and
  `docs/compliance/PRIVATE_DATA_WARNING.md`.

---

## Prerequisites — what a partner sends, and over which period

Before a partner exports anything, two filters go on their export, in this order:

**1. The last twelve months, by Leistungsdatum.** Ask for invoices whose treatment dates fall
inside the last 6–12 months, and say why rather than only asking: this build prices every audit
against **one** catalog edition, `goae_current`, because that is the only edition in
`data/catalogs/` holding real numbers — the historical ones beside it are synthetic fixtures
(`data/catalogs/README.md`). A 2020 invoice is therefore measured against the 2026 fee schedule.
Most positions are unaffected; the ones that are not produce a finding indistinguishable from a
correct one, and that is a finding a partner may take to a payer.

**2. Then anonymise.** `scripts/anonymize_padnext.py`, on their machine, as above. Filtering first
means the script runs over less data and the delivery that leaves their building is the smallest
one that answers the question.

Nothing here is enforced, and that is deliberate — **an older delivery is audited, not refused**:

```bash
# a delivery whose newest <datum> is more than PILOT_MAX_INVOICE_AGE_DAYS old
curl -sS -X POST http://localhost:8000/api/v1/padnext/audit \
  -H "Content-Type: application/xml" -H "X-API-Key: $KEY" \
  --data-binary @alt.xml | jq '{status: "200", pilot_warnings, latest_service_date}'

# {
#   "status": "200",
#   "pilot_warnings": [
#     "Das Leistungsdatum dieser Abrechnung liegt mehr als 12 Monate zurück. Da diese Engine den
#      aktuellen GOÄ-Katalog verwendet, können historische Regelabweichungen nicht erkannt werden."
#   ],
#   "latest_service_date": "2020-07-20"
# }
```

Every verdict, bucket, euro and the receipt hash are exactly what the same delivery produces with
recent dates — `apps/engine/tests/test_pilot_scope.py` asserts that directly. The warning is
top-level (`pilot_warnings`, never merged into `findings` or `schema_warnings`), the web app prints
it above the result, and the Prüfbericht prints it beside the terms.

The window is `PILOT_MAX_INVOICE_AGE_DAYS`, 365 by default. Check what the stack actually booted
with, the same way § 0 checks the schema policy:

```bash
docker compose -f infra/docker/docker-compose.yml exec engine \
  python -c "from app.config import get_settings; print(get_settings().pilot_max_invoice_age_days)"
```

`pilot_scope_checked: false` on a report means the question was never asked — either the check is
off (`0`) or no position carried a readable `<datum>`. An empty `pilot_warnings` is only "this
delivery is recent" when `pilot_scope_checked` is `true`.

---

## 0. Bring the stack up, and confirm what it is running

```bash
docker compose -f infra/docker/docker-compose.yml up --build -d
```

| | |
|---|---|
| `http://localhost:3000` | **the demo** — review and audit UI |
| `http://localhost:3000/padnext` | upload one delivery, see the audit |
| `http://localhost:3000/padnext/batch` | upload a ZIP, watch the job, export |
| `http://localhost:3000/settings/api-keys` | mint and revoke keys, and the usage summary |
| `http://localhost:8000/docs` | the engine's OpenAPI page |
| `http://localhost:3001` | the marketing site |

Confirm the policy the engine actually booted with — never assume it from the `.env` you *meant*
to copy:

```bash
docker compose -f infra/docker/docker-compose.yml exec engine \
  python -c "from app.config import get_settings; print(get_settings().padnext_schema_policy)"
```

To run the pilot under `warn`, set it in `infra/docker/.env` and recreate the engine. The compose
files default to `strict`, so this is an explicit act:

```bash
echo 'PADNEXT_SCHEMA_POLICY=warn' >> infra/docker/.env
docker compose -f infra/docker/docker-compose.yml up -d --force-recreate engine
```

Starting from scratch, `cp infra/docker/.env.example infra/docker/.env` gives you that line already
set — but read the file first: it also carries `BETTER_AUTH_SECRET=` empty and a placeholder
Postgres password, both of which the stack needs filled in before `web` will come up.

---

## 1. Mint an API key

**In the demo, do this in the UI** — `http://localhost:3000/settings/api-keys` → *New key*. The
secret is shown exactly once, in a dialog, and never again. That is worth showing a partner
deliberately: it is the same property their own credential store has to respect.

The curl equivalent, for a scripted setup:

```bash
export ENGINE=http://localhost:8000
export ORG=org7Kd2Vn8Qs4Rt6Yw1Zx3Bc5Ef9Gh0J     # your practice's organisation id
export USER=demo-operator

curl -sS -X POST "$ENGINE/api/v1/settings/api-keys" \
     -H "Content-Type: application/json" \
     -H "X-Organization-ID: $ORG" \
     -H "X-User-ID: $USER" \
     -d '{"name": "Pilot demo key"}'
```

```jsonc
{
  "key_id": "ab12cd34ef56",
  "name": "Pilot demo key",
  "token": "azm_live_…",        // the only time this is ever returned
  "organization_id": "org7Kd2…",
  "created_at": "2026-08-30T09:14:22Z"
}
```

```bash
export AZMOTH_KEY='azm_live_…'    # paste the token
```

> **Why this call carries a session header and not a key.** The first key has to be issued to
> somebody who does not have one yet, so the mint endpoint is gated on the web tier's verified
> session (`X-Organization-ID` + `X-User-ID`) rather than on `X-API-Key`. Reaching it with curl
> works here only because compose publishes port 8000 on the demo machine. In a real deployment the
> engine is not addressable from outside the web tier, and this is the reason.

---

## 2. Audit the nine-error synthetic delivery

The file is committed at `logic/tests/cases/padnext/00004711_20260726_ADL_000001_padx.xml`.

```bash
export PADX=logic/tests/cases/padnext/00004711_20260726_ADL_000001_padx.xml

curl -sS -X POST "$ENGINE/api/v1/audit/single" \
     -H "X-API-Key: $AZMOTH_KEY" \
     -H "Content-Type: application/xml" \
     --data-binary "@$PADX"
```

The numbers to read out loud, straight from the response:

```bash
curl -sS -X POST "$ENGINE/api/v1/audit/single" \
     -H "X-API-Key: $AZMOTH_KEY" \
     -H "Content-Type: application/xml" \
     --data-binary "@$PADX" \
  | jq '{claimed_total_eur, confirmed_fine_eur, confirmed_wrong_eur, unconfirmed_eur,
         coverage_ratio, schema_policy, schema_warnings,
         findings: (.findings | length), positions: (.positions | length)}'
```

```jsonc
{
  "claimed_total_eur":   "251.54",   // what the invoice charges
  "confirmed_fine_eur":   "24.25",   // green  — provably correct
  "confirmed_wrong_eur":  "88.49",   // red    — provably not chargeable as claimed
  "unconfirmed_eur":     "138.80",   // amber  — NOT a finding; the limit of our rule coverage
  "coverage_ratio": 0.4482,
  "schema_policy": "strict",
  "schema_warnings": [],
  "findings": 11,
  "positions": 9
}
```

**Three sentences to say while that is on screen**, because they are the ones that get misread:

1. `200` is the answer even though the invoice is wrong. The status describes the API call. Nine
   findings is a *successful* audit.
2. The three amounts add up to the claim and are never summed into one "at risk" headline. Only
   `confirmed_wrong_eur` may be presented as exposure — and even that is "cannot be billed as
   submitted", not a settled refund.
3. `unconfirmed_eur` is the boundary of *our* rule coverage, not an accusation against the
   practice. Today it is the largest of the three, and saying so first is the whole pitch.

Every euro amount is a decimal **string**. Parse it with a decimal type; a double loses cents.

### The same thing in the UI

`http://localhost:3000/padnext` → drop the same file. Same report, position by position, with the
bucket summary and the findings panel. Use this one with a clinician; use curl with an integrator.

---

## 3. Fetch the PDF

**On the partner API the PDF is rendered for a bulk job, not for a single audit** — so the curl
demo path is: zip the delivery, submit it, poll until it is done, print it. Three commands.

In the application both are one click. `/padnext` renders the Prüfbericht for the delivery on
screen (»Prüfbericht exportieren«, beside the report) and `/padnext/batch/history` renders the
aggregated one for any completed batch. The single-delivery document is produced by auditing the
delivery again rather than by reading a stored report — the single audit deliberately stores
nothing — which is safe because the audit is deterministic: the `receipt_hash` printed on the PDF
is the one in the JSON, and that is how a reader confirms the two are the same audit.

```bash
# 1. one delivery in a ZIP (a real partner's archive holds a month of them)
zip -j /tmp/pilot_demo.zip "$PADX"

# 2. submit — 202 immediately, before any auditing has happened
# the field is `batch_id`; it is the id you poll and print with
JOB=$(curl -sS -X POST "$ENGINE/api/v1/audit/bulk" \
        -H "X-API-Key: $AZMOTH_KEY" \
        -F "file=@/tmp/pilot_demo.zip" | jq -r .batch_id)
echo "job: $JOB"

# 3. poll until COMPLETED (no webhook — polling is the contract)
until [ "$(curl -sS "$ENGINE/api/v1/audit/bulk/$JOB" \
             -H "X-API-Key: $AZMOTH_KEY" | jq -r .status)" = "COMPLETED" ]; do
  sleep 1
done

# 4. print it
curl -sS -X POST "$ENGINE/api/v1/audit/$JOB/pdf" \
     -H "X-API-Key: $AZMOTH_KEY" \
     -o "/tmp/${JOB}_pruefbericht.pdf"

xdg-open "/tmp/${JOB}_pruefbericht.pdf"
```

Asking for the PDF before the job finishes is a `409` with `AUDIT_JOB_NOT_COMPLETED`, deliberately:
a partial roll-up on paper is a number somebody reconciles against three weeks later with no way to
tell which moment it was a snapshot of. The same job renders byte-identical output every time.

In the UI the same thing is `http://localhost:3000/padnext/batch`.

---

## 4. Show the pilot policy doing its job

This is the demo that matters for week 3, and it is worth doing *live* with a partner's own export.

```bash
# under strict: refused at the door, with a line number
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$ENGINE/api/v1/audit/single" \
     -H "X-API-Key: $AZMOTH_KEY" -H "Content-Type: application/xml" \
     --data-binary @their_export.xml
# 422

# under warn (§ 0), the same bytes:
curl -sS -X POST "$ENGINE/api/v1/audit/single" \
     -H "X-API-Key: $AZMOTH_KEY" -H "Content-Type: application/xml" \
     --data-binary @their_export.xml \
  | jq '{schema_policy, schema_warnings, positions: (.positions | length), confirmed_wrong_eur}'
# 200 — audited, with every deviation named at the top level
```

And the operator's copy of the same event, which is what makes `warn` safe rather than merely
permissive — one structured line per delivery, carrying the request id of the upload:

```bash
docker compose -f infra/docker/docker-compose.yml logs engine \
  | grep padnext_schema_violation | tail -1 | jq .
```

```jsonc
{
  "level": "WARNING",
  "logger": "app.padnext.reader",
  "message": "PADnext framing violated (2 violation(s)), policy=warn: audited anyway",
  "request_id": "a3f1485eafc44a2491d1defc6ae2a190",
  "event": "padnext_schema_violation",
  "padnext_schema_outcome": "audited",
  "violation_count": 2,
  "violations": [
    { "rule": "SCHEMAV_CVC_ENUMERATION_VALID",     "line": 9,  "path": "…/behandlungsart", "message": "…" },
    { "rule": "SCHEMAV_CVC_DATATYPE_VALID_1_2_1",  "line": 10, "path": "…/positionen",     "message": "…" }
  ]
}
```

**Collect these.** Every line here is one deviation between our hand-written subset XSD and a real
PVS export, with the rule that fired and the element path. That list is the work item for week 4:
each one is either a schema we should widen or an export the vendor should fix, and until the pilot
ran there was no way to tell which.

`warn` changes *only* whether bad framing is fatal. It does not relax how positions are judged, and
it does not touch `PADNEXT_ALLOW_REAL_DATA`.

---

## 5. The four metrics we are tracking

Write these down per session, per participant. They are the pilot's actual output — the demo is
just how we get to them.

### 1. Precision — of `confirmed_wrong` only

> Of the positions the engine put in `confirmed_wrong_eur`, what share does a billing expert agree
> is not chargeable as claimed?

```
precision = agreed_confirmed_wrong_positions / all_confirmed_wrong_positions
```

The only bucket this is measured on, because it is the only one we present as exposure. A false
positive here is the failure that ends a pilot: it sends a practice to argue a position that was
fine. Record every disagreement with its Ziffer and the rule id that produced it.

### 2. Recall proxy — findings the reviewer had, that we did not

True recall needs a fully adjudicated corpus, which we do not have. The proxy: hand the reviewer
the same invoice cold, take their list of problems, and count how many the engine also found.

```
recall_proxy = engine_findings ∩ reviewer_findings / reviewer_findings
```

Log each miss with whether it was **out of coverage** (no verified rule maps to that Ziffer — went
to amber, correctly) or **in coverage and missed** (a rule exists and did not fire). Only the second
is a defect. The first is the number that tells us which rules to verify next.

### 3. Time saved

Wall-clock, per invoice, same reviewer, same difficulty:

- **baseline** — reviewing the invoice as they do today
- **assisted** — reviewing it with the report open

Report the median and the spread, not the mean; one pathological invoice moves a mean and tells you
nothing. Note separately how long they spend on the amber bucket, which is where the assisted path
can be *slower* if the presentation is wrong.

### 4. Amber-bucket comprehension

The one that decides whether the honest three-way split survives contact with users. Ask, without
prompting, after they have read the report:

> "What does this figure mean?" — pointing at `unconfirmed_eur`.

Score it three ways, and record the participant's own words:

- **correct** — "the engine has no verified rule for these, it hasn't judged them"
- **wrong-alarming** — "these are also probably wrong" / "this is money at risk"
- **wrong-dismissive** — "these are fine"

Both wrong answers are product defects, and they need opposite fixes. `wrong-alarming` means we are
about to be accused of inflating exposure; `wrong-dismissive` means the amber bucket is being read
as a clean bill of health. Target: no `wrong-alarming` answers at all.

---

## Appendix — quick reference

| | |
|---|---|
| Auth header | `X-API-Key: $AZMOTH_KEY` |
| Single audit | `POST /api/v1/audit/single` — 5 MiB, 100/min per key |
| Bulk audit | `POST /api/v1/audit/bulk` — 50 MB, 500 members, 10/hour per key |
| Job status | `GET /api/v1/audit/bulk/{job_id}` — poll; no webhook |
| PDF (Stapel) | `POST /api/v1/audit/{job_id}/pdf` — `COMPLETED` jobs only |
| PDF (eine Lieferung) | `POST /api/v1/padnext/audit.pdf` — the file in, the report out |
| Keys | `POST`/`GET`/`DELETE /api/v1/settings/api-keys` — session-gated, not key-gated |
| Full contract | [`docs/api/PARTNER_API.md`](../api/PARTNER_API.md) |
| Error codes | [`docs/errors.md`](../errors.md) |
| Operations | [`docs/OPERATIONS.md`](../OPERATIONS.md) |
| Data handling | [`docs/DATA_HANDLING_POLICY.md`](../DATA_HANDLING_POLICY.md) |

Every request carries `X-Request-ID` in and out. When a pilot user says "the upload didn't work",
ask for that id — it is the join key across every log line the request produced, including the ones
from inside the reader and the solver.
