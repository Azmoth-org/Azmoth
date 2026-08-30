# Running Azmoth

What an operator has to be able to do under pressure: know which database the engine is on, take a
backup, restore one, and find out what happened to a customer's request. Everything here is a
command, and every command has been run.

`make help` lists the targets. Development commands stay in `pnpm turbo` and `pytest` and are
deliberately not duplicated here — two ways to run one check is how one of them goes stale.

---

## 1. The database is Postgres, and the engine refuses to pretend otherwise

`DATABASE_URL` defaults to SQLite so that `pytest` and a bare `uvicorn` need no server. **That
default is not a deployment target**: one writer, one file inside a container a redeploy replaces,
no replication, no encryption at rest.

The engine enforces this rather than documenting it. Under `APP_ENV=production` a non-Postgres
`DATABASE_URL` is a **startup failure**, not a warning
([`app/db/session.py`](../apps/engine/app/db/session.py), `assert_production_database`) — a warning
gets read once and forgotten, a refusal to start cannot be. `DATABASE_AUTO_CREATE=true` in
production is refused for the same reason: the schema must arrive through `alembic upgrade head`, so
that a rollback exists and the migration history describes the database.

Both compose files already point the engine and the web tier at the `postgres` service. SQLite
appears in exactly one place — the test suite, which forces in-memory SQLite in `tests/conftest.py`
before any application import, so a developer's `.env` cannot point a test run at a real database.

Check a running deployment:

```bash
make verify-db
```

```
DATABASE_URL backend : postgresql
durable              : True
APP_ENV              : production
0009_api_usage_logs
```

The last line is `alembic current`. If it is behind the newest file in
`apps/engine/alembic/versions/`, the container is running an older image — which is exactly what a
missing table at runtime looks like before anyone works out why.

---

## 2. Backups

```bash
make backup-db                       # → backups/azmoth-<utc>.dump
make list-backups
BACKUP_DIR=/mnt/backups make backup-db
```

**The script verifies the dump before claiming success.** It reads the archive's table of contents
back with `pg_restore --list` and fails if that does not work or if the archive contains no table
data. A backup script that only runs `pg_dump` produces a file nobody has opened, and the first time
anyone opens it is the day they need it.

Custom format (`-Fc`), not plain SQL: compressed, selectively restorable, and listable without a
server — which is what makes the verification possible.

`backups/` is git-ignored. A dump is a complete copy of every approval, audit event and API key hash
the deployment holds; a `git add -A` that swept one into a commit would put a practice's records in
a repository permanently.

**What is not automated.** Nothing schedules this. Put `make backup-db` on a cron or a systemd timer
in the deployment, keep the dumps off the same host as the database, and test a restore on a
schedule rather than on an incident.

---

## 3. Restoring — and how to test one without risk

```bash
make restore-db FILE=backups/azmoth-20260830T030553Z.dump
```

It is destructive and behaves accordingly:

1. It prints what is about to be replaced and **requires the database name to be typed**. There is
   no `--force`, deliberately: a restore should not be reachable by pressing up-arrow and enter.
2. It takes a **safety dump of the current state first**. Restoring the wrong file is recoverable if
   what it replaced still exists, and unrecoverable otherwise.
3. It restores with `--clean --if-exists`, so the existing objects are dropped rather than merged
   into. A merged restore leaves rows from two points in time in one table — worse than either state
   and impossible to reason about afterwards.

### Testing a restore without touching production

Restore into a scratch database instead. This is the check to run on a schedule:

```bash
DUMP=$(ls -t backups/*.dump | head -1)
C="docker compose -f infra/docker/docker-compose.yml exec -T postgres"

$C psql -U azmoth -d postgres -c "DROP DATABASE IF EXISTS azmoth_restore_test;" \
                               -c "CREATE DATABASE azmoth_restore_test;"
$C pg_restore -U azmoth -d azmoth_restore_test --no-owner --exit-on-error < "$DUMP"

for t in proposals audit_events batch_jobs batch_files api_keys api_usage_logs rule_reviews; do
  live=$($C psql -U azmoth -d azmoth               -tAc "SELECT count(*) FROM $t")
  rest=$($C psql -U azmoth -d azmoth_restore_test  -tAc "SELECT count(*) FROM $t")
  printf "  %-16s live=%-6s restored=%-6s %s\n" "$t" "$live" "$rest" \
    "$([ "$live" = "$rest" ] && echo OK || echo MISMATCH)"
done

$C psql -U azmoth -d postgres -c "DROP DATABASE azmoth_restore_test;"
```

This was run against the live stack while writing this document: `pg_restore` exited 0 and every
table's count matched.

---

## 4. Finding out what happened to a request

Logs are one JSON object per line (`LOG_FORMAT=json`), and every line carries the request id.

```bash
make logs | jq -c 'select(.logger == "app.request")'
```

```json
{"ts":"…","level":"INFO","logger":"app.request","message":"POST /api/v1/audit/bulk -> 202",
 "request_id":"1b2344c3…","key_id":"66a927daf14b","organization_id":"org_…",
 "job_id":"batch_36cf…","http_route":"/api/v1/audit/bulk","http_status":202,"duration_ms":51.9}
```

A customer reporting a failure quotes the request id from their error response — it is in
`details.request_id` on every `500`, not only in the header, because a support conversation starts
with a screenshot.

```bash
make logs | jq -c 'select(.request_id == "1b2344c3…")'        # every line that request produced
make logs | jq -c 'select(.organization_id == "org_…")'        # everything one practice did
make logs | jq -c 'select(.http_status >= 500)'                # what is broken
```

Unhandled `500`s are also rows in `error_log` — type, message, route, request id, tenant, and no
invoice content:

```sql
SELECT occurred_at, exception_type, http_route, request_id, organization_id
FROM error_log ORDER BY occurred_at DESC LIMIT 20;
```

---

## 5. Usage and billing

Consumption per practice is in `api_usage_logs`, and per key through
`GET /api/v1/settings/usage` (or the **API-Schlüssel** screen in the web application).

```sql
SELECT api_key_id, count(*) AS requests, sum(bytes_processed) AS bytes,
       count(*) FILTER (WHERE status_code >= 400) AS failed
FROM api_usage_logs
WHERE organization_id = 'org_…' AND timestamp >= date_trunc('month', now())
GROUP BY api_key_id ORDER BY requests DESC;
```

**One caveat that matters before an invoice is sent.** Rows are buffered in memory and flushed in
batches of 25 or after 15 seconds, and flushed again on a clean shutdown. A process *killed* with a
partial buffer loses those rows. It is metering good enough to price a pilot, not a financial
ledger; if an invoice built from it is ever disputed, the buffer has to go and the write has to
become synchronous — see the note at the top of
[`app/services/usage.py`](../apps/engine/app/services/usage.py). Count in the customer's favour
until then.

---

## 6. Uploads

A bulk job's ZIP lives on a mounted volume between the `202` and the report, and is deleted when the
job reaches a terminal status (`RETAIN_BULK_UPLOADS=false`).

```bash
docker compose -f infra/docker/docker-compose.yml exec engine du -sh /var/lib/azmoth/uploads
```

If that grows without bound, either jobs are not completing — check for `PROCESSING` rows older than
an hour — or somebody set `RETAIN_BULK_UPLOADS=true` to debug an integration and left it on.

```sql
SELECT batch_id, status, created_at, upload_path FROM batch_jobs
WHERE status IN ('PENDING','PROCESSING') ORDER BY created_at;
```

A restart requeues those automatically; the archive is what makes that possible.
