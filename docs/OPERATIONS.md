# Running Azmoth

What an operator has to be able to do under pressure: know which database the engine is on, take a
backup, restore one, and find out what happened to a customer's request. Everything here is a
command, and every command has been run.

`make help` lists the targets. Development commands stay in `pnpm turbo` and `pytest` and are
deliberately not duplicated here — two ways to run one check is how one of them goes stale.

**Sections 1–6 are about the stack, wherever it runs — the commands assume a shell on the machine
running it.** [Section 7](#7-the-azure-deployment) is the pilot deployment: one Azure VM, the same
Docker Compose stack behind Caddy, and an `azure-*` Makefile target for each command below that you
would otherwise run over SSH by hand. If you are holding a laptop rather than a server, you probably
want section 7.

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

**What is not automated.** Nothing in this repository schedules `make backup-db`. Keep the dumps off
the same host as the database, and test a restore on a schedule rather than on an incident.

On the Azure deployment both of those have an answer:
[`infra/scripts/backup-to-azure.sh`](../infra/scripts/backup-to-azure.sh) dumps, verifies, encrypts
and pushes to Blob Storage, and [§ 7.6](#76-backups-off-the-vm) is the cron line that runs it. It is
still something you have to install — a script in a repository is not a schedule.

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

---

## 7. The Azure deployment

One VM in `germanywestcentral`, running the same `docker-compose.yml` as everywhere else with
[`docker-compose.azure.yml`](../infra/docker/docker-compose.azure.yml) layered on top. That override
does two things: it puts Caddy in front, and it unpublishes every other port. Nothing on that box
listens publicly except Caddy on 80 and 443.

Provisioning and the first deploy are in
[`docs/deploy/AZURE.md`](deploy/AZURE.md). This section is what you do afterwards.

Set the host once and every `azure-*` target below works:

```bash
export AZURE_HOST=20.79.12.34
```

### 7.1 The shape of it

```
        internet
           │  :80  :443            ← the only ports the NSG allows, and the only ones Docker publishes
           ▼
    ┌──────────────┐
    │    caddy     │  TLS, Let's Encrypt, renewals
    └──────┬───────┘
           │   app.azmoth.com ─────────► web:3000 ──┐
           │   www.azmoth.com ─────────► marketing  │  ENGINE_BASE_URL, server-side only
           │   api.azmoth.com           :3000       │
           │     /api/v1/audit/*  ─────► engine:8000◄┘
           │     everything else ─────► 404
           ▼
    ┌──────────────────────────────────────────────┐
    │  compose network — no host ports at all      │
    │  web:3000   engine:8000   postgres:5432      │
    └──────────────────────────────────────────────┘
```

**`api.azmoth.com` is a path allowlist, not a proxy to the engine, and that is load-bearing.** The
engine authenticates nobody — [`app/api/tenancy.py`](../apps/engine/app/api/tenancy.py) says so
directly: `X-User-ID` and `X-Organization-ID` are asserted, not proven, and a caller who reaches the
engine directly "can name any organisation they like". Only `/api/v1/audit/*` is published, because
those endpoints verify an `X-API-Key` against the database and take the tenant from the stored row.
Adding a path to that allowlist is a security decision. See the header of
[`infra/docker/Caddyfile`](../infra/docker/Caddyfile).

### 7.2 Deploying a change

```bash
git commit -am "..."          # git archive ships HEAD, not your working tree
make deploy                   # build on the box, restart, wait for healthy
make preflight                # verify from outside, including that 8000 is still closed
```

`make deploy` regenerates nothing. `/opt/azmoth/shared/.env` is written on the first deploy and left
alone on every one after — see the header of [`scripts/deploy.sh`](../scripts/deploy.sh) for why
regenerating `BETTER_AUTH_SECRET` logs everyone out and why regenerating `POSTGRES_PASSWORD` is
worse than useless.

To restart without a rebuild: `make deploy` with `--skip-build`, or `make azure-restart SERVICE=web`.

### 7.3 Logs

Same JSON, one object per line, same `request_id`, as in [§ 4](#4-finding-out-what-happened-to-a-request).

```bash
make azure-logs                        # engine, followed
make azure-logs SERVICE=web
make azure-logs-caddy                  # TLS and certificate problems live here
```

Piping through `jq` needs the pipe to run locally, so for anything analytical, pull the lines down:

```bash
ssh $AZURE_HOST 'cd /opt/azmoth/repo && sudo docker compose \
  -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.azure.yml \
  logs --no-color --tail 5000 engine' \
  | jq -c 'select(.http_status >= 500)'
```

```bash
# everything one request did, from the id in the customer's error response
... | jq -c 'select(.request_id == "1b2344c3…")'
# everything one practice did
... | jq -c 'select(.organization_id == "org_…")'
```

Docker's json-file driver keeps logs until the disk is full. On a 64 GiB box that is months away,
and it is still the second most likely thing to fill the disk after the build cache:

```bash
ssh $AZURE_HOST 'sudo du -sh /var/lib/docker/containers/*/*-json.log | sort -h | tail'
```

### 7.4 Restarting

```bash
make azure-ps                          # what is running, and is it healthy
make azure-restart SERVICE=web
make azure-restart SERVICE=engine
make azure-restart SERVICE=caddy       # after editing the Caddyfile — see below
```

**Restarting `caddy` is not how you reload a Caddyfile change.** The file is bind-mounted from the
release directory, so an edit made over SSH is undone by the next `make deploy`, which replaces that
directory. Edit `infra/docker/Caddyfile` in the repository, commit, and `make deploy`. If you are
testing a change interactively, `docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile`
applies it without dropping connections — and remember it will not survive.

**A restart is not a fix for a full disk**, which is the failure that most often presents as
containers dying:

```bash
ssh $AZURE_HOST 'df -h / && docker system df'
ssh $AZURE_HOST 'sudo docker system prune -af --filter until=168h'   # keeps the last week's cache
```

That prune removes images and build cache. It does not touch named volumes, so
`azmoth-postgres-data`, `azmoth-engine-uploads` and `azmoth-caddy-data` are safe. Never add `--volumes`
to it.

### 7.5 The database

No port is published, so everything goes through `docker compose exec`. This is not a workaround —
it is why unpublishing 5432 cost nothing.

```bash
make azure-verify-db                   # on Postgres? migrated to which revision?
make azure-psql                        # an interactive session
```

```bash
# a one-off query
ssh $AZURE_HOST 'cd /opt/azmoth/repo && sudo docker compose \
  -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.azure.yml \
  exec -T postgres psql -U azmoth -d azmoth -c "SELECT count(*) FROM proposals;"'
```

Reaching it from a local GUI is an SSH tunnel, which is the only reason 5432 would ever need to
leave the box:

```bash
ssh -L 5432:localhost:5432 $AZURE_HOST \
  'cd /opt/azmoth/repo && sudo docker compose -f infra/docker/docker-compose.yml \
   -f infra/docker/docker-compose.azure.yml exec postgres sleep 3600'
```

Adminer, if you want it, is behind the `debug` profile and binds to `127.0.0.1` only, so it is
reachable through `ssh -L 8080:localhost:8080` and from nowhere else. Bring it down when you are
done — it is an unauthenticated front door to every table.

### 7.6 Backups off the VM

[`infra/scripts/backup-to-azure.sh`](../infra/scripts/backup-to-azure.sh) wraps `backup-db.sh`,
encrypts the verified dump, and pushes it to Blob Storage in the same region.

```bash
make azure-backup                      # run one now
```

Three properties worth knowing before you rely on it:

- **The VM holds no credential.** Authentication is the VM's managed identity, granted
  `Storage Blob Data Contributor` on that one container by `infra/azure/provision.sh`. There is no
  storage key on disk to steal from beside the dumps it would decrypt.
- **The VM can encrypt and cannot decrypt.** `age` with a public key; the private key lives in your
  password manager and never touches the VM. Losing it loses every backup — that is the trade.
- **It reads the blob back and compares its length** before reporting success, the same way
  `backup-db.sh` reads its own archive's table of contents. An upload that returned 200 and stored
  nothing is precisely the failure a backup process must not have.

Set it up once (on the VM), then schedule it:

```bash
# on your laptop, once
age-keygen -o azmoth-backup.key        # → put the private key in a password manager
ssh $AZURE_HOST
  echo 'AGE_RECIPIENT=age1ql3z...'        | sudo tee -a /opt/azmoth/shared/.env
  echo 'STORAGE_ACCOUNT=azmothbackupxxxx' | sudo tee -a /opt/azmoth/shared/.env
  sudo apt-get install -y age
  sudo crontab -e
```

```cron
# 03:15 UTC daily. Output is mailed by cron if MAILTO is set; otherwise read the log.
15 3 * * * /opt/azmoth/repo/infra/scripts/backup-to-azure.sh >> /var/log/azmoth-backup.log 2>&1
```

Nothing prunes the blobs, deliberately: a compromised VM must not be able to delete the backups it
just wrote. Expire them with a lifecycle policy on the storage account instead, which the VM's role
does not permit it to change.

```bash
az storage blob list --account-name azmothbackupxxxx --container-name db-backups \
  --auth-mode login --output table | tail
```

### 7.7 Restoring

Same script and the same safety properties as [§ 3](#3-restoring--and-how-to-test-one-without-risk):
it makes you type the database name, it takes a safety dump of the current state first, and it
restores with `--clean --if-exists`.

**Test a restore without touching production** — this is the one to schedule:

```bash
make azure-restore-test
```

It restores the newest dump into a scratch database, compares row counts table by table, and drops
it again. `make preflight` runs the same check.

**A real restore, from a local dump on the VM:**

```bash
ssh -t $AZURE_HOST
cd /opt/azmoth/repo
ls -lht /opt/azmoth/backups/*.dump

sudo COMPOSE_PROJECT_NAME=azmoth \
  COMPOSE_FILE=infra/docker/docker-compose.yml \
  BACKUP_DIR=/opt/azmoth/backups \
  ./infra/scripts/restore-db.sh /opt/azmoth/backups/azmoth-20260830T031500Z.dump
```

**From a blob** — the case that matters, because it is the one where the VM's own disk is gone.
The dump is decrypted **on your laptop**, since that is where the private key is:

```bash
# 1. find it
az storage blob list --account-name azmothbackupxxxx --container-name db-backups \
  --auth-mode login --query "[].{name:name, size:properties.contentLength}" --output table

# 2. download and decrypt LOCALLY
az storage blob download --account-name azmothbackupxxxx --container-name db-backups \
  --name 2026/08/azmoth-20260830T031500Z.dump.age --file ./restore.dump.age --auth-mode login
age -d -i azmoth-backup.key ./restore.dump.age > ./restore.dump

# 3. check it before sending it anywhere
pg_restore --list ./restore.dump | grep -c "TABLE DATA"

# 4. ship it up and restore
scp ./restore.dump $AZURE_HOST:/opt/azmoth/backups/
ssh -t $AZURE_HOST 'cd /opt/azmoth/repo && sudo COMPOSE_PROJECT_NAME=azmoth \
  COMPOSE_FILE=infra/docker/docker-compose.yml BACKUP_DIR=/opt/azmoth/backups \
  ./infra/scripts/restore-db.sh /opt/azmoth/backups/restore.dump'
```

Step 3 is not optional. `age` fails loudly on a corrupt file, but a dump that decrypts cleanly can
still be one taken while a migration was half-applied — and `pg_restore --list` is the cheapest
thing that would tell you.

**After any restore**, confirm the schema matches the running image. A dump from before a migration
restored into a container that is past it leaves the engine querying columns that do not exist:

```bash
make azure-verify-db
```

### 7.8 Cost and the credit

```bash
make azure-cost
az vm list --resource-group azmoth-pilot --show-details --output table
```

Roughly EUR 36/month — about 2.7 months of a 100 EUR credit. If the pilot pauses, the VM can be
**deallocated** to stop compute charges; the disk and the static IP keep billing at around EUR 9/month,
and the static IP is why the DNS records and certificates survive the gap.

```bash
az vm deallocate --resource-group azmoth-pilot --name azmoth-vm   # stops compute billing
az vm start      --resource-group azmoth-pilot --name azmoth-vm
```

`az vm stop` is not the same thing and is the expensive mistake: it shuts the guest down and keeps
the VM allocated, so it bills exactly as if it were running. Always `deallocate`.

Set a budget alert. A fixed credit that runs out takes the pilot offline with no warning:

```bash
az consumption budget create --budget-name azmoth-pilot --amount 100 \
  --category Cost --time-grain Monthly \
  --start-date $(date -u +%Y-%m-01) --end-date $(date -u -d '+1 year' +%Y-%m-01)
```

### 7.9 When it is broken

| What you see | Look here first |
|---|---|
| Browser warns about the certificate | `make azure-logs-caddy`. Caddy serves a self-signed certificate while ACME is failing. Usually DNS not resolving to this VM, or port 80 closed. |
| `403 INVALID_ORIGIN` on sign-in | `BETTER_AUTH_URL` is set to something that is not the browser's origin. Empty is correct unless you use Google sign-in. |
| Everyone logged out after a deploy | `BETTER_AUTH_SECRET` changed. It must not. Check `/opt/azmoth/shared/.env` against a backup of it. |
| `password authentication failed` | `POSTGRES_PASSWORD` was edited after the volume was initialised. The image only applies it to an empty data directory. Fix with `ALTER ROLE`, not by editing the file again. |
| Build dies at exit 137, no message | OOM. Check `free -m` for the 4 GiB swapfile; re-run `infra/azure/provision.sh` if it is missing. |
| Containers restarting, no obvious cause | `df -h /`. A full disk looks like everything failing at once. |
| `502` from Caddy | The backend is not healthy yet. `make azure-ps`, then that service's logs. |
| Port 8000 answers from outside | Stop. The deploy did not use `docker-compose.azure.yml`. Anyone can write to the audit log as any practice until it is closed. |
