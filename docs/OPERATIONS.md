# Running Azmoth

What an operator has to be able to do under pressure: know which database the engine is on, take a
backup, restore one, and find out what happened to a customer's request. Everything here is a
command, and every command has been run.

`make help` lists the targets. Development commands stay in `pnpm turbo` and `pytest` and are
deliberately not duplicated here — two ways to run one check is how one of them goes stale.

**Sections 1–6 are about the stack, wherever it runs — the commands assume a shell on the machine
running it.** [Section 7](#7-the-deployed-vm) is the pilot deployment: one VM, the same
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

The **local** compose files already point the engine and the web tier at the `postgres` service. On
the deployed VM there is no `postgres` service at all: the database is **Neon** — external, managed, in
`aws-eu-central-1` (AWS Europe, Frankfurt) — and both tiers reach it over TLS. SQLite appears in
exactly one place — the test suite, which forces in-memory SQLite in `tests/conftest.py` before any
application import, so a developer's `.env` cannot point a test run at a real database.

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

On the Azure deployment the equivalent is [`make azure-verify-db`](#75-the-database), and it asserts
one thing more: that the engine's database host has no `-pooler` in it, i.e. that the engine is on
Neon's **direct** endpoint rather than the pooler. That is not a preference about latency.
SQLAlchemy's asyncpg dialect prepares a *named* statement for every execute, and Neon's pooler is
PgBouncer in transaction mode, which mishandles them — so the engine behind the pooler does not fail
cleanly at startup, it raises intermittent `DuplicatePreparedStatementError` under concurrency. A
configuration that only breaks under load is one nobody catches by looking, which is why it is an
assertion rather than a line of documentation.

---

## 2. Backups

```bash
make backup-db                       # → backups/azmoth-<utc>.dump
make list-backups
BACKUP_DIR=/mnt/backups make backup-db
```

**Those three commands are the local stack's, they still work, and they must not be deleted.**
`make backup-db`, `make restore-db`, [`infra/scripts/backup-db.sh`](../infra/scripts/backup-db.sh)
and [`infra/scripts/restore-db.sh`](../infra/scripts/restore-db.sh) all dump and restore through
`docker compose exec postgres`, so they need a `postgres` container to exec into. A laptop running
[`docker-compose.yml`](../infra/docker/docker-compose.yml) has one; the deployed VM does not. Nothing
about them has gone stale — they are the right tools wherever the database and the compose file are
on the same machine.

**The script verifies the dump before claiming success.** It reads the archive's table of contents
back with `pg_restore --list` and fails if that does not work or if the archive contains no table
data. A backup script that only runs `pg_dump` produces a file nobody has opened, and the first time
anyone opens it is the day they need it.

Custom format (`-Fc`), not plain SQL: compressed, selectively restorable, and listable without a
server — which is what makes the verification possible.

`backups/` is git-ignored. A dump is a complete copy of every approval, audit event and API key hash
the deployment holds; a `git add -A` that swept one into a commit would put a practice's records in
a repository permanently.

### On the deployed VM the dump goes over the network

There is no `postgres` container there, so `backup-db.sh` has nothing to exec into and the deployed
path is a different script — one per cloud, differing only in where the encrypted file goes and what
credential gets it there:

| Cloud | Script | Destination | Credential |
|---|---|---|---|
| AWS | [`infra/scripts/backup-to-s3.sh`](../infra/scripts/backup-to-s3.sh) | S3 bucket, `eu-central-1` | EC2 instance profile |
| Azure | [`infra/scripts/backup-to-azure.sh`](../infra/scripts/backup-to-azure.sh) | Blob container, `germanywestcentral` | VM managed identity |

Both run `pg_dump` against Neon's **direct** endpoint over TLS, from inside a throwaway, pinned
`postgres:17-alpine` container.

```bash
# AWS
ssh "azmoth@$AZURE_HOST" 'sudo /opt/azmoth/repo/infra/scripts/backup-to-s3.sh'
# Azure
make azure-backup                    # dump Neon, verify, encrypt, push to Blob — now
```

**Why a container rather than the host's `pg_dump`.** A `pg_dump` older than the server refuses with
`server version mismatch`. Neon runs Postgres 17 and Ubuntu 22.04 ships 14, so the host package is
not an option, and adding the PGDG apt repository to a box whose whole purpose is to run three
pulled images buys one command at the price of a new moving part. A pinned image is one line, is the
same version on every run, and leaves nothing behind.

**Why the direct endpoint.** `pg_dump` holds one transaction open across hundreds of statements; a
transaction-mode pooler does not promise to keep that on a single server connection, and the result
is a dump that restores into a state which never existed. The script refuses outright if
`DATABASE_URL`'s host contains `-pooler` rather than dumping through it.

Everything else is inherited from `backup-db.sh` rather than dropped with it: it verifies the
archive with `pg_restore --list` and fails if no table data is listed, it age-encrypts the verified
dump to a **public** key whose private half is never on the VM, and it uploads with an identity the
cloud hands the box at run time rather than a stored key on disk.
[§ 7.6](#76-backups-off-the-vm) is the cron line that runs it, and installing that is still something
you have to do — a script in a repository is not a schedule.

### Why dump at all, when Neon has point-in-time restore

Because every Neon mechanism lives inside the Neon project.

On the Free plan the history window is **six hours, capped at 1 GB**. That is a rollback, not a
backup: it will undo a `DELETE` somebody ran at lunchtime, and it will do nothing for anything
noticed the next morning. The Launch plan extends the window to **seven days**, which is better and
is still the same shape of protection.

The shape is the problem. Instant restore, snapshots and branches all survive a dropped table.
**None of them survives a deleted project, a lapsed card, a compromised Neon login, or Neon's own
policy that Free-plan projects idle for 90 days or more are subject to deletion.** The principle
this document has always stated has not changed — keep the dumps off the same host as the database —
and a managed provider is a host. The encrypted dumps are the only copy that survives losing the
Neon account.

**One caveat since the VM moved to AWS.** Neon runs on AWS, so the backup bucket is now with the same
*provider* as the database rather than a different one. It is still a different account, a different
service and a different credential, which is what the principle above is asking for — but it is not
the provider diversity it used to be. A practice that wants that needs a third copy somewhere else
entirely. It is named as an open point in
[`docs/AVV_TECHNICAL_ANNEX_DRAFT.md`](AVV_TECHNICAL_ANNEX_DRAFT.md) § 9 rather than glossed over.

And test a restore on a schedule rather than on an incident. [§ 7.7](#77-restoring) is the
procedure; it needs the `age` private key, so it is a human's job rather than a cron line.

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

### Testing a restore without touching production — local stack only

Restore into a scratch database instead. **This recipe drives `docker compose exec postgres`, so it
runs against the local stack and nowhere else** — there is no `postgres` container on the deployed VM.
This is the check to run on a schedule:

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

### The same test when the database is Neon

The tempting translation — `CREATE DATABASE azmoth_restore_test` inside the production Neon project
— is the wrong one. It puts a scratch database in the project that holds real records, and every run
spends the Free plan's compute allowance to prove something Neon's own instant restore already
covers.

Restore into a **Neon branch** instead. A branch is a copy-on-write clone of its parent: seconds to
create, storage billed only for what diverges, and it has its own endpoint and its own connection
string — so a `pg_restore` into it cannot reach the live database however wrong the command is.
Create it in the Neon console (or with `neon branches create`), take its **direct** connection
string, restore into that, and delete the branch afterwards. [§ 7.7](#77-restoring) is the full
procedure with the commands.

A throwaway local container is the other honest answer, and it needs no Neon at all:

```bash
docker run -d --name azmoth-restore-test -e POSTGRES_PASSWORD=x \
  -v "$PWD/restore.dump:/restore.dump:ro" postgres:17-alpine
sleep 5                                  # the server initialises its data directory first

docker exec azmoth-restore-test \
  pg_restore --username postgres --dbname postgres --no-owner --exit-on-error /restore.dump
docker exec azmoth-restore-test \
  psql -U postgres -tAc "SELECT count(*) FROM proposals"

docker rm -f azmoth-restore-test
```

`pg_restore` runs *inside* the container on purpose: it is then guaranteed to be the same major
version as the server, which a laptop's `pg_restore` is not.

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

## 7. The deployed VM

One VM — on AWS a `t3.small` in `eu-central-1` (2 vCPU, 2 GiB, a 32 GiB gp3 volume); on Azure a
`Standard_B1ms` in `germanywestcentral` (1 vCPU, 2 GiB, a 32 GiB disk) — running the
same `docker-compose.yml` as everywhere else with
[`docker-compose.azure.yml`](../infra/docker/docker-compose.azure.yml) layered on top. That override
does five things, and its header lists them:

1. **it puts Caddy in front** — one process terminating TLS and renewing its own certificates;
2. **it unpublishes every other port**, so nothing on that box listens publicly except Caddy on 80
   and 443;
3. **it runs pre-built images from GHCR instead of building** — nothing is built on this VM;
4. **it takes the database off the box entirely** (Neon, `aws-eu-central-1`), profiling out
   `postgres`, and `marketing` with it, because the public site is Vercel's;
5. **it splits migrations off from the runtime** into a one-shot `engine-migrate` that runs on Neon's
   direct endpoint, with `RUN_MIGRATIONS=false` in the long-running engine.

The merge tags that make (2) and (3) work — `!reset` and `!override` — need **Docker Compose v2.24 or
newer**. On anything older, `ports` would be *concatenated* rather than replaced and the engine's
8000 would stay published on a public IP, so [`scripts/deploy.sh`](../scripts/deploy.sh) asserts the
version before it runs anything.

Provisioning and the first deploy are in [`docs/deploy/AWS.md`](deploy/AWS.md) (or
[`AZURE.md`](deploy/AZURE.md) for the Azure deployment). This section is what you do afterwards, and
almost none of it is provider-specific: it is SSH and `docker compose`.

Set the host once and every `azure-*` target below works. The variable and the target prefix kept
their names through the move to AWS — they mean "the deployment VM", and renaming them would touch
every target in the [`Makefile`](../Makefile) and every shell profile that exports one, for no
behaviour. Read `AZURE_HOST` as `VM_HOST`.

```bash
export AZURE_HOST=3.120.45.67
```

### 7.1 The shape of it

```
        internet
           │  :80  :443            ← the only ports the cloud firewall allows, and the only ones Docker publishes
           ▼
    ┌──────────────┐
    │    caddy     │  TLS, Let's Encrypt, renewals
    └──────┬───────┘
           │   app.azmoth.com ─────────► web:3000
           │   api.azmoth.com
           │     /api/v1/audit/*  ─────► engine:8000
           │     everything else ─────► 404
           ▼
    ┌──────────────────────────────────────────────┐
    │  compose network — no host ports at all      │
    │  web:3000  ──ENGINE_BASE_URL──►  engine:8000 │
    │  server-side only; no host port on either    │
    └────┬────────────────────────────────┬────────┘
         │ TLS, POOLED endpoint           │ TLS, DIRECT endpoint
         ▼                                ▼
    ┌──────────────────────────────────────────────┐
    │  Neon — external, managed. AWS Europe,       │
    │  Frankfurt (aws-eu-central-1).               │
    │    ep-…-pooler.…  ← web, Better Auth         │
    │    ep-….…         ← engine + both migrators  │
    └──────────────────────────────────────────────┘

    ┌──────────────────────────────────────────────┐
    │  Vercel — azmoth.com and www.azmoth.com,     │
    │  prerendered from apps/marketing. Reached    │
    │  from the browser over TLS, never via here.  │
    └──────────────────────────────────────────────┘
```

**`api.azmoth.com` is a path allowlist, not a proxy to the engine, and that is load-bearing.** The
engine authenticates nobody — [`app/api/tenancy.py`](../apps/engine/app/api/tenancy.py) says so
directly: `X-User-ID` and `X-Organization-ID` are asserted, not proven, and a caller who reaches the
engine directly "can name any organisation they like". Only `/api/v1/audit/*` is published, because
those endpoints verify an `X-API-Key` against the database and take the tenant from the stored row.
Adding a path to that allowlist is a security decision. See the header of
[`infra/docker/Caddyfile`](../infra/docker/Caddyfile).

**The two Neon endpoints in that diagram are not interchangeable either.** `DATABASE_URL` is the
direct string and it is what `alembic upgrade head`, Better Auth's migrator, the engine at runtime
and the backup job's `pg_dump` all use. `DATABASE_URL_POOLED` is the pooled string — the host with
`-pooler` in it — and exactly one thing uses it: Better Auth at runtime in the web tier, which talks
to Postgres through node-postgres, issues unnamed queries, and is a connection-per-request workload
of precisely the shape a pooler exists for. The engine is on the direct endpoint because asyncpg is
not pooler-safe and cannot be made so from a URL ([§ 1](#1-the-database-is-postgres-and-the-engine-refuses-to-pretend-otherwise)),
and because one long-lived container with `pool_size=5` and `max_overflow=10` does not need a pooler
in the first place.

### 7.2 Deploying a change

```bash
git commit -am "..."          # git archive ships HEAD, not your working tree
git push origin main          # the images are built from the pushed commit, not from your tree
gh run watch                  # wait for release-images.yml to finish building the three images
make deploy                   # pull HEAD's images, migrate, restart, wait for healthy
make preflight                # verify from outside, including that 8000 is still closed
```

**`make deploy` no longer builds anything on the box.** It pulls three images from GHCR at HEAD's
commit sha — `azmoth-engine`, `azmoth-web` and `azmoth-web-builder`, built by
`.github/workflows/release-images.yml` on a GitHub runner. So HEAD must have been **pushed** and that
workflow must have **finished**, or those tags do not exist in the registry.
[`scripts/deploy.sh`](../scripts/deploy.sh) HEADs all three manifests over the registry API from your
laptop *before* it touches the VM, because the alternative is discovering it after Docker has been
installed and the source shipped. The source is still shipped — `git archive HEAD` — but only for the
two compose files and the Caddyfile.

Migrations run as their own step, `docker compose run --rm engine-migrate`, on Neon's **direct**
endpoint, before anything that queries the schema is restarted. Its output and exit code land in your
terminal rather than in a container log, and a failure stops the deploy with the previous release
still serving against the old schema — which is a working system.

`make deploy` regenerates nothing. `/opt/azmoth/shared/.env` is written on the first deploy and left
alone on every one after — see the header of [`scripts/deploy.sh`](../scripts/deploy.sh) for why
regenerating `BETTER_AUTH_SECRET` logs everyone out.

**The Neon URLs are the same doctrine and they fail far more quietly.** `DATABASE_URL` and
`DATABASE_URL_POOLED` are written on the first deploy and never rewritten. Overwriting them with
another project's strings points a running deployment at an **empty** database — which comes up
perfectly healthy, migrates cleanly, and shows a practice none of their own records. Nothing anywhere
reports an error. Moving to a different Neon project is therefore a deliberate edit on the box, not a
side effect of deploying. Two keys are the exception, and they are *appended* only when entirely
absent and never rewritten: `SIGNUP_ALLOWLIST`, which the operator may have edited on the box, and
`DATABASE_URL_POOLED`, which did not exist before Neon and whose absence is invisible because the web
tier silently falls back to the direct endpoint.

To restart without pulling: `make deploy` with `--skip-pull` (`--skip-build` is kept as an alias for
it, since nothing builds any more), or `make azure-restart SERVICE=web`. To run only the migration,
without a full deploy: `make azure-migrate`.

**Rolling back:**

```bash
make rollback TAG=6a3c14c              # any sha whose images are still in the registry
```

A pull and a restart, not a rebuild — the images for that sha were built once and the tag *is* the
commit, which is what makes a rollback legible. `deploy.sh` prunes images older than a week, so a
week of releases is a week of rollback targets. Two things to know before using it:

- **It does not undo a migration.** If the deploy you are backing out of added one, the older image
  runs against the newer schema, and whether that is survivable depends entirely on the migration.
  Check before rolling back across one.
- **The compose files and the Caddyfile come from your HEAD, not from the tag.** That is right for
  rolling back the application and wrong if the infrastructure files also changed; check the older
  commit out first if so. `deploy.sh` warns when the tag is not HEAD.

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

Docker's json-file driver keeps logs until the disk is full. There is no build cache on this box any
more, so on a 32 GiB disk the logs and the pulled images are the two things that fill it:

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
ssh $AZURE_HOST 'sudo docker system prune -af --filter until=168h'   # keeps the last week's images
```

That prune removes images. It does not touch named volumes, so `azmoth-engine-uploads` and
`azmoth-caddy-data` are safe. Never add `--volumes` to it: `azmoth-caddy-data` holds the
certificates and the ACME account key, and Let's Encrypt rate-limits their replacement at five
duplicates a week. (`azmoth-postgres-data` is not on this box at all — the azure override profiles
the `postgres` service out, so the volume is never created.) Note that a prune with no `until`
filter also removes the previous release's images, which are exactly what a rollback pulls back
down — which is why `deploy.sh` uses `image prune --filter until=168h` rather than
`system prune -a`.

### 7.5 The database

It is not on this box, so nothing here is a `docker compose exec`. `make azure-psql` runs `psql` in
a throwaway pinned container on the VM and reads the connection string out of
`/opt/azmoth/shared/.env`, which means nothing is installed on the host and there is still exactly
one copy of that credential on it.

```bash
make azure-verify-db                   # on Neon? on the DIRECT endpoint? at schema head?
make azure-psql                        # an interactive session, in postgres:17-alpine
make azure-migrate                     # alembic upgrade head, without a full deploy
```

`make azure-verify-db` answers three questions rather than two. It prints the backend, whether the
URL is durable, `APP_ENV` and **the database host**, and it asserts that host has no `-pooler` in it.
Then it compares `alembic current` against `alembic heads` — which is the check that catches a
container running an image whose newest revision the database never received. `current` printing *a*
revision only ever proved that a migration had run at some point; it did not prove the schema is at
the head this image carries, and a missing column at runtime looks like an application bug for about
an hour.

A one-off query, in a session on the box:

```bash
ssh -t $AZURE_HOST
  set -a; . /opt/azmoth/shared/.env; set +a
  sudo docker run --rm -e PGURL="${DATABASE_URL/+asyncpg/}" postgres:17-alpine \
    sh -c 'psql "$PGURL" -c "SELECT count(*) FROM proposals;"'
```

Two details in that command are not decoration. The `+asyncpg` has to come off: it is SQLAlchemy's
driver suffix and libpq answers `invalid URI scheme: postgresql+asyncpg`. And the **single quotes**
around the `sh -c` script matter: `$PGURL` must be expanded by the *container's* shell, from the
container's environment, which is also what keeps the connection string out of `psql`'s own argument
list. Double quotes would expand it in your shell instead and hand `psql` a URL on its command line
— or, if you were not in a session that had sourced the env file, an empty one.

**The SSH tunnel is gone, and that is a genuine simplification rather than a lost capability.**
Reaching the old database from a local GUI meant holding `ssh -L 5432:localhost:5432` open into a
container, because 5432 was published nowhere. Neon is reachable from anywhere over TLS, so a GUI —
DataGrip, TablePlus, `psql` on your laptop — connects to the Neon host **directly** with the
connection string from the Neon console. There is no tunnel to keep alive and no port that ever needs
to leave the box.

Two things to keep in mind when you do. Use the **direct** endpoint for an interactive session:
`SET`/`RESET`, `LISTEN`/`NOTIFY`, session-level advisory locks and `WITH HOLD` cursors are all
unsupported through the pooler, and an interactive session is nothing but session state. And the
client should be at least as new as the server, which is Postgres 17.

**Adminer is not in this deployment at all.** In the base compose file it sits behind the `debug`
profile, which meant one `--profile debug` on the wrong box away from an unauthenticated front door
to every table. The azure override reassigns its profile with `!override` — which *replaces* the
list rather than appending to it — so `--profile debug` no longer reaches it, and it has nothing on
this box to connect to in any case. Neon's own SQL editor in the console is the replacement, and it
is behind a real login, which is precisely what Adminer never was.

### 7.6 Backups off the VM

The backup job — [`backup-to-s3.sh`](../infra/scripts/backup-to-s3.sh) on AWS,
[`backup-to-azure.sh`](../infra/scripts/backup-to-azure.sh) on Azure — no longer wraps
`backup-db.sh`: that script dumps through `docker compose exec postgres` and there is no such
container here. It runs `pg_dump` **over the network** against Neon's direct endpoint, from inside a
throwaway, pinned `postgres:17-alpine` container, then verifies the archive, encrypts it, and pushes
it to object storage in the same region. [§ 2](#2-backups) has the reasoning for the container and
for the direct endpoint.

```bash
# AWS
ssh "azmoth@$AZURE_HOST" 'sudo /opt/azmoth/repo/infra/scripts/backup-to-s3.sh'
# Azure
make azure-backup                      # run one now
```

Four properties worth knowing before you rely on it:

- **The VM holds no *storage* credential.** On AWS it is the EC2 instance profile
  `infra/aws/provision.sh` attached — an IAM role granting `s3:PutObject` and `s3:GetObject` on that
  one bucket — and the CLI takes short-lived, automatically rotated credentials from the instance
  metadata service. On Azure it is the VM's managed identity with `Storage Blob Data Contributor` on
  that one container. Either way there is no key on disk to steal from beside the dumps it would
  decrypt.

  Two AWS-specific consequences, both deliberate and both surprising the first time:
  `aws s3 ls s3://<bucket>` **from the VM answers AccessDenied** (no `s3:ListBucket` — you list from
  your laptop), and the VM cannot delete an object it wrote (no `s3:DeleteObject`). The metadata
  service is also IMDSv2-only with a hop limit of 1, so **a container cannot reach it at all** —
  which is why `pg_dump` runs in a container and `aws s3 cp` runs on the host.
- **The VM can encrypt and cannot decrypt.** `age` with a public key; the private key lives in your
  password manager and never touches the VM. Losing it loses every backup — that is the trade.
- **It reads the uploaded object back and compares its length** before reporting success, the same way it reads
  its own archive's table of contents with `pg_restore --list`. An upload that returned 200 and
  stored nothing is precisely the failure a backup process must not have.
- **The Neon connection string, however, IS a long-lived credential, and it does live on the box** —
  in `/opt/azmoth/shared/.env`, mode 600 — because the engine cannot connect without it and an
  unattended restart has to pull it off without a human present. That is the one credential the
  managed identity does not get rid of, and it is what this script's `pg_dump` uses too. Rotating it
  is **not** `ALTER ROLE`; Neon gives you no such thing to run. It is *"Reset password"* on the role
  in the Neon console, then editing both `DATABASE_URL` and `DATABASE_URL_POOLED` and re-running
  `scripts/deploy.sh`. Back that file up somewhere other than this VM: it is now the only copy of
  the credentials that can read the database, and without them the encrypted dumps in object storage
  cannot be restored anywhere.

Set it up once (on the VM), then schedule it:

```bash
# on your laptop, once
age-keygen -o azmoth-backup.key        # → put the private key in a password manager
ssh $AZURE_HOST
  echo 'AGE_RECIPIENT=age1ql3z...'          | sudo tee -a /opt/azmoth/shared/.env
  # AWS:
  echo 'STORAGE_BUCKET=azmoth-backups-xxxx' | sudo tee -a /opt/azmoth/shared/.env
  # Azure:
  echo 'STORAGE_ACCOUNT=azmothbackupxxxx'   | sudo tee -a /opt/azmoth/shared/.env
  sudo crontab -e
```

```cron
# 03:15 UTC daily. Output is mailed by cron if MAILTO is set; otherwise read the log.
# Substitute backup-to-azure.sh on an Azure box.
15 3 * * * /opt/azmoth/repo/infra/scripts/backup-to-s3.sh >> /var/log/azmoth-backup.log 2>&1
```

`sudo apt-get install -y age` used to be a line in that block, and installing the cloud CLI by hand
used to be a step before it. Both are now done by `scripts/deploy.sh`'s bootstrap, idempotently, on
every deploy — it asks the instance metadata service which cloud the box is in and installs `aws` or
`az` accordingly — because the backup job is the thing most likely to be set up "later", and a
missing binary is one more reason for later never to arrive. `postgresql-client` is deliberately
*not* installed; that is what the pinned `postgres:17-alpine` image is for.

Nothing prunes the uploaded objects, deliberately: a compromised VM must not be able to delete the
backups it just wrote. On AWS that is enforced rather than merely intended — the instance profile has
no `s3:DeleteObject`. Expire them with a lifecycle rule instead, which the VM's role does not permit
it to change.

**[AWS] Mind that the bucket is versioned when you write that rule.** A rule that expires *current*
versions leaves the noncurrent ones behind unless it also carries a `NoncurrentVersionExpiration`. A
rule that appears to delete old backups and does not is worse than no rule, because it is believed.

**[Azure] Mind Cool tier's 30-day minimum storage duration.** A blob removed before it is 30 days old
is billed as though it had lived for 30, so a rule that expires dumps at seven days saves nothing.
The same early-delete charge applies to a full overwrite, which is why the script uploads under a
timestamped name rather than rewriting one blob daily.

```bash
# AWS — from your LAPTOP; the VM has no s3:ListBucket
aws s3 ls s3://azmoth-backups-xxxx/db-backups/ --recursive --region eu-central-1 | tail

# Azure
az storage blob list --account-name azmothbackupxxxx --container-name db-backups \
  --auth-mode login --output table | tail
```

### 7.7 Restoring

There is no local Postgres to restore into any more, so the shape of this changed. The whole
procedure now runs from your laptop, because that is where the `age` private key is: download the
object, decrypt it locally, check it, and only then send it at Neon — and at a **branch** of Neon
first, not at the live database.

On AWS it *has* to run from your laptop for a second reason: the VM's instance profile has no
`s3:ListBucket`, so the box cannot even find the file. That is the policy working, not an obstacle to
route around.

`make azure-check-db` is not a restore drill and does not pretend to be. It is the database section
of the pre-flight — reachable, right endpoints, schema at head. It replaced `make azure-restore-test`,
which built a scratch database with `docker compose exec postgres` and could not be ported: a
throwaway database inside the production Neon project would spend the Free plan's compute allowance
on every invocation to prove something Neon's own instant restore already covers. A real drill needs
the private key, which is deliberately neither on the VM nor in CI, so it is a human's job — this
one.

```bash
# 1. find it
#    AWS:
aws s3 ls s3://azmoth-backups-xxxx/db-backups/2026/09/ --region eu-central-1
#    Azure:
az storage blob list --account-name azmothbackupxxxx --container-name db-backups \
  --auth-mode login --query "[].{name:name, size:properties.contentLength}" --output table

# 2. download and decrypt LOCALLY — the private key is in your password manager and nowhere else
#    AWS:
aws s3 cp s3://azmoth-backups-xxxx/db-backups/2026/09/azmoth-20260902T031500Z.dump.age \
  ./restore.dump.age --region eu-central-1
#    Azure:
az storage blob download --account-name azmothbackupxxxx --container-name db-backups \
  --name 2026/09/azmoth-20260902T031500Z.dump.age --file ./restore.dump.age --auth-mode login

age -d -i azmoth-backup.key ./restore.dump.age > ./restore.dump

# 3. check it BEFORE sending it anywhere
docker run --rm -i postgres:17-alpine pg_restore --list < ./restore.dump | grep -c "TABLE DATA"

# 4. restore into a NEON BRANCH, not into production.
#    Create the branch in the Neon console (or: neon branches create --name restore-check) and copy
#    its DIRECT connection string. A branch is a copy-on-write clone of its parent — seconds to
#    create, storage billed only for what diverges, its own endpoint — so nothing below can reach
#    the live database however wrong it is.
docker run --rm -v "$PWD/restore.dump:/restore.dump:ro" \
  -e PGURL='postgresql://USER:PW@ep-branch-xxx.eu-central-1.aws.neon.tech/azmoth?sslmode=require' \
  postgres:17-alpine \
  sh -c 'pg_restore --dbname "$PGURL" --no-owner --no-privileges --exit-on-error /restore.dump'

# 5. look at what you restored, on the branch, before promoting anything
docker run --rm -it \
  -e PGURL='postgresql://USER:PW@ep-branch-xxx.eu-central-1.aws.neon.tech/azmoth?sslmode=require' \
  postgres:17-alpine sh -c 'psql "$PGURL" -c "SELECT count(*) FROM proposals;"'
```

**Note the SINGLE quotes around the `sh -c` script.** `$PGURL` must be expanded by the *container's*
shell, from the container's environment. Double quotes expand it in your shell instead — on a laptop
where it is unset — so `pg_restore` is handed an empty `--dbname`, falls back to a local unix socket,
and fails with something about `/var/run/postgresql` that reads like a broken image rather than a
quoting mistake. Expanding it inside the container also keeps the credential out of `pg_restore`'s
own argument list. This is the same footgun the header of
[`backup-to-azure.sh`](../infra/scripts/backup-to-azure.sh) warns about, and it is worth being
careful with twice.

**Then make the branch the one the deployment uses, rather than restoring over the live database.**
Verifying on a branch and switching to it is reversible in both directions: edit `DATABASE_URL` and
`DATABASE_URL_POOLED` in `/opt/azmoth/shared/.env` to the branch's two strings and re-run
`scripts/deploy.sh` (a deliberate edit on the box, which is exactly the case
[§ 7.2](#72-deploying-a-change) reserves it for), or use the console's restore flow. Going straight
at production with `pg_restore --clean --if-exists` is not reversible — it drops the existing objects
first, so a dump that turns out to be the wrong one has taken the right one with it. The **local**
`make restore-db` path is unchanged and still has all three safety properties of
[§ 3](#3-restoring--and-how-to-test-one-without-risk) — the typed database name, the safety dump
first, `--clean --if-exists` — because there it has a `postgres` container to talk to.

**Step 3 is not optional.** `age` fails loudly on a corrupt file, but a dump that decrypts cleanly
can still be one taken while a migration was half-applied — and `pg_restore --list` is the cheapest
thing that would tell you.

**After any restore**, confirm the schema matches the running image. A dump from before a migration
restored into a database the running image is past leaves the engine querying columns that do not
exist, which looks like an application bug for about an hour:

```bash
make azure-verify-db
```

It compares `alembic current` against `alembic heads` as well as checking the endpoint, so a schema
that is behind the deployed image is a failure rather than a printed revision somebody has to
recognise. If it says the schema is behind: `make azure-migrate`.

### 7.8 Cost and the credit

#### [AWS]

```bash
aws ce get-cost-and-usage --time-period Start=$(date -u +%Y-%m-01),End=$(date -u -d '+1 month' +%Y-%m-01) \
  --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE
aws ec2 describe-instances --region eu-central-1 --filters Name=tag:Name,Values=azmoth-vm \
  --query 'Reservations[].Instances[].{id:InstanceId,type:InstanceType,state:State.Name}' --output table
```

About **EUR 22.25/month** on-demand in `eu-central-1`:

| Item | EUR/month |
|---|---|
| EC2 `t3.small` — 2 vCPU / 2 GiB, 730 h | 16.00 |
| Root volume, 32 GiB gp3 | 2.80 |
| Elastic IP, associated | 3.35 |
| S3 Standard, a few GB of dumps | ~0.10 |
| Egress | 0.00 — the first 100 GB/month is free |
| Neon, Free plan | 0.00 |
| GHCR — container storage and bandwidth | 0.00 — currently free on every plan |
| GitHub Actions, public repository | 0.00 |
| Vercel, Hobby | 0.00 |
| **total** | **~22.25** |

Three quarters of that is the instance, and it is a `t3.small` rather than a `t3.medium` only because
nothing is built on it — see the header of
[`infra/aws/provision.sh`](../infra/aws/provision.sh) for the ladder.

Stopping the instance stops the EC2 charge and **not** the other two: the EBS volume and the Elastic
IP go on billing about **EUR 6.15/month** between them. The Elastic IP is why the DNS records and the
certificates survive the gap.

```bash
aws ec2 stop-instances  --instance-ids <id> --region eu-central-1   # stops compute billing
aws ec2 start-instances --instance-ids <id> --region eu-central-1
```

Two AWS-specific traps, neither of which existed on Azure:

- **An Elastic IP that is allocated and associated with nothing bills at the same rate as one in
  use.** A torn-down pilot that forgot `aws ec2 release-address` goes on costing EUR 3.35/month
  indefinitely. It is the last line of the teardown in
  [AWS.md § 8](deploy/AWS.md#teardown).
- **`t3` defaults to `unlimited` CPU credits, which bills a surcharge instead of throttling.**
  `infra/aws/provision.sh` sets `CpuCredits=standard` so that it throttles instead. If solves feel
  slow, check `CPUCreditBalance` before reaching for the setting — the answer is `t3.medium`.

**There is no spending cap on an AWS account.** A fixed Azure credit stopped when it ran out; AWS
keeps billing. The budget alert below is not optional here.

#### [Azure]

```bash
make azure-cost
az vm list --resource-group azmoth-pilot --show-details --output table
```

About **EUR 20.29/month** at pay-as-you-go in `germanywestcentral` — roughly **4.9 months** of a
100 EUR credit:

| Item | EUR/month |
|---|---|
| VM, `Standard_B1ms` — 1 vCPU / 2 GiB | 15.04 |
| OS disk, 32 GiB StandardSSD (E4) | 2.06 |
| Standard static IPv4 | 3.14 |
| Blob Storage, Cool, a few GB of dumps | ~0.05 |
| Egress | 0.00 — the first 100 GB/month is free |
| Neon, Free plan | 0.00 |
| GHCR — container storage and bandwidth | 0.00 — currently free on every plan |
| GitHub Actions, public repository | 0.00 |
| Vercel, Hobby | 0.00 |
| **total** | **~20.29** |

Three quarters of that is the VM, and it is a `B1ms` rather than a `B2s` only because nothing is
built on it — see the header of [`infra/azure/provision.sh`](../infra/azure/provision.sh) for the
ladder of larger sizes and what each one costs in runway.

If the pilot pauses, the VM can be **deallocated** to stop compute charges. The disk and the static
IP keep billing, at about **EUR 5.20/month** — 2.06 plus 3.14 — and the static IP is why the DNS
records and the certificates survive the gap.

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

**Watch the Neon Free plan's allowances as well as the cloud bill, because they do not degrade —
they stop.** The Free plan gives 100 CU-hours per project per month, 0.5 GB of storage and 5 GB of
network transfer, and they are hard caps with no overage billing. When the compute allowance is
spent, Neon suspends the compute: **existing connections are dropped and new ones cannot open** until
the next billing period. There is no throttling step in between — the pilot goes down rather than
gets slower. Storage over 0.5 GB fails writes instead, and no data is deleted in either case. Both
are visible in the Neon console before they happen, and neither is visible in `az consumption`.

### 7.9 When it is broken

| What you see | Look here first |
|---|---|
| Browser warns about the certificate | `make azure-logs-caddy`. Caddy serves a self-signed certificate while ACME is failing. Usually DNS not resolving to this VM, or port 80 closed. |
| `403 INVALID_ORIGIN` on sign-in | `BETTER_AUTH_URL` is set to something that is not the browser's origin. Empty is correct unless you use Google sign-in. |
| Everyone logged out after a deploy | `BETTER_AUTH_SECRET` changed. It must not. Check `/opt/azmoth/shared/.env` against a backup of it. |
| `DuplicatePreparedStatementError`, or `prepared statement "__asyncpg_stmt_3__" already exists` | The engine is on Neon's **pooled** endpoint. `DATABASE_URL` and `DATABASE_URL_POOLED` are the wrong way round in `/opt/azmoth/shared/.env` — swap them and redeploy. It is intermittent and load-dependent, so it did not fail at startup and it never will — which is why `make azure-verify-db` asserts the endpoint rather than trusting it. |
| A deploy fails at `docker compose pull` | The images for that sha are not in the registry — the commit was never pushed, or `release-images.yml` has not finished or failed — or `GHCR_TOKEN` has expired. **Nothing was restarted: the previous release is still serving.** `gh run list --workflow=release-images.yml --limit 5`, and check the token at <https://github.com/settings/tokens> still has `read:packages`. |
| The first request after a quiet spell takes seconds | Neon's scale-to-zero. The compute suspends after five minutes idle and the next connection pays for the resume. It **cannot be disabled on the Free plan** (Launch can); it is not a fault, and it is why `MIGRATION_WAIT_SECONDS` defaults to 60. |
| Every connection refused at once, and nothing changed on the VM | Neon's Free-plan compute allowance is exhausted. Existing connections are dropped and new ones refused until the next billing period. Check the Neon console — nothing on this box will tell you, because from here it looks like the database is down. |
| The public site is down, the application is fine | That is **Vercel**, not this VM — check the Vercel dashboard. Then check nobody pointed `azmoth.com`'s A record here: there is no `marketing` container on this box, so Caddy would answer those names with its default site and burn a Let's Encrypt duplicate certificate trying. `scripts/preflight.sh` § 2b and `scripts/deploy.sh` both refuse on that. |
| A container killed with exit 137 | OOM on a 2 GiB box. `free -m` — the 4 GiB swapfile should be there; re-run the provisioning script for this box (`infra/aws/provision.sh` or `infra/azure/provision.sh`) if it is not. Nothing is built here any more, so this is a runtime spike (usually a Soufflé solve), not a build. |
| Containers restarting, no obvious cause | `df -h /`. A full disk looks like everything failing at once. |
| `502` from Caddy | The backend is not healthy yet. `make azure-ps`, then that service's logs. |
| Port 8000 answers from outside | Stop. The deploy did not use `docker-compose.azure.yml`. Anyone can write to the audit log as any practice until it is closed. |
