# Deploying Azmoth on Azure

One VM, Docker Compose, Caddy in front. No managed database, no container service, no Kubernetes —
not because those are bad, but because a 100 EUR credit buys roughly three months of this and about
three weeks of the alternative, and a pilot needs the months.

Start to finish is about forty minutes, most of it the first build.

```
  ./infra/azure/provision.sh          create the VM, IP, firewall, backup storage
  <point DNS at the address>          and wait for it to resolve
  ./scripts/deploy.sh <ip>            ship, build, start
  ./scripts/preflight.sh <ip>         verify from outside
```

---

## 1. The VM

**`Standard_B2s` — 2 vCPU, 4 GiB RAM, 64 GiB StandardSSD, Ubuntu 22.04 LTS (gen2),
`germanywestcentral`.**

### Why 4 GiB, when the stack runs in 1.5

The size is set by the **build**, not by the run. `scripts/deploy.sh` builds on the box, and that
build is two `next build`s — `apps/web` and `apps/marketing` — plus a node-gyp compile of
`better-sqlite3` in the deps stage. Next peaks well over 1 GiB per build.

On a 2 GiB B1ms the build is OOM-killed. The symptom is a compose build that exits 137 with no
message, which reliably gets misdiagnosed as a broken Dockerfile. At rest the running stack — four
containers plus a one-shot migrator — sits at about 1.5 GiB, so B1ms would happily *run* what it
cannot *build*.

Two things follow from that, and both are already handled:

- `infra/azure/provision.sh` configures a **4 GiB swapfile** with `vm.swappiness=10`. The build's
  peak is brief and mostly idle afterwards, which is exactly the shape swap is good at. Postgres
  should never touch it — check `free -m` after the first build.
- `scripts/deploy.sh` builds **one service at a time**. Compose builds in parallel by default, and
  two concurrent `next build`s on this box lose to the OOM killer even with swap.

### Why not the others

| Size | RAM | ~EUR/mo | Verdict |
|---|---|---|---|
| `Standard_B1s` | 1 GiB | ~7 | Will not build. Will barely run. |
| `Standard_B1ms` | 2 GiB | ~14 | Runs the stack; the build is OOM-killed. Only viable if you build images elsewhere and pull them. |
| **`Standard_B2s`** | **4 GiB** | **~30** | **Builds and runs. ~2.7 months on the credit.** |
| `Standard_B2ls_v2` | 4 GiB | ~25 | Same memory, newer series, ~20% cheaper. Try it; fall back to B2s if the region has no capacity. |
| `Standard_B2ms` | 8 GiB | ~60 | Twice the price for memory the build does not need. Cuts the runway to ~1.6 months. |

B-series are burstable: 2 vCPU with a 40% combined baseline that banks credits while idle. A build
burns through them and a pilot's traffic does not come close, which is the right trade here.

### What it costs

| | ~EUR/month |
|---|---|
| `Standard_B2s` | 30 |
| 64 GiB StandardSSD (E6) | 5 |
| Standard static IPv4 | 4 |
| Egress (first 100 GB free) | 0 |
| Blob Storage, Cool, a few GB | <1 |
| **Total** | **~36** |

**~2.7 months on 100 EUR.** These are list prices from memory and they move — check yours:

```bash
az vm list-skus --location germanywestcentral --size Standard_B2 --output table
# and https://azure.microsoft.com/pricing/calculator/
```

Set a budget alert on day one. A fixed credit that runs out takes the pilot offline with no warning:

```bash
az consumption budget create --budget-name azmoth-pilot --amount 100 \
  --category Cost --time-grain Monthly \
  --start-date $(date -u +%Y-%m-01) --end-date $(date -u -d '+1 year' +%Y-%m-01)
```

### Why `germanywestcentral`

This is a compliance constraint, not a latency preference.
[`docs/AVV_TECHNICAL_ANNEX_DRAFT.md`](../AVV_TECHNICAL_ANNEX_DRAFT.md) § 5.1 states that processing
happens exclusively on systems inside the EU. Frankfurt satisfies it. Do not move this to `eastus`
to save four euros.

> **One thing to fix before a practice signs anything.** That same annex, § 5.2, says
> "**Unterauftragsverarbeiter: derzeit keine**" — currently no subprocessors, and explicitly no
> external storage services. Deploying on Azure makes both untrue: Microsoft becomes a processor the
> moment this VM exists, and Blob Storage is an external storage service. The document has to name
> Microsoft Azure with the region before it goes to a customer. This is a paperwork change, not an
> architecture one, but it is a blocker on the pilot rather than on the deployment.

### No separate data disk

It was considered for backups and rejected. A disk attached to this VM is deleted with this VM, and
[`docs/OPERATIONS.md`](../OPERATIONS.md) § 2 already requires dumps to be kept off the same host as
the database — which a disk in the same resource group is, for every failure that actually happens.
Backups go to Blob Storage; see § 6.

---

## 2. Provisioning

### The short way

```bash
az login
./infra/azure/provision.sh
```

Idempotent — every step checks before it creates, so a run that fails halfway is fixed by running it
again. Override anything from the environment:

```bash
VM_SIZE=Standard_B2ls_v2 LOCATION=germanywestcentral RG=azmoth-pilot ./infra/azure/provision.sh
```

It refuses to start without an SSH public key, and it **refuses to open port 22 to the internet** —
if it cannot detect your public IP it stops and asks for it rather than defaulting to `0.0.0.0/0`.

### The same thing by hand

If you would rather run the commands yourself, this is what the script does.

```bash
RG=azmoth-pilot
LOCATION=germanywestcentral
VM=azmoth-vm
MY_IP=$(curl -s https://api.ipify.org)

# 1. Resource group. One group holds everything, so teardown is a single delete with nothing
#    orphaned quietly accruing charges.
az group create --name $RG --location $LOCATION

# 2. Static public IP.
#    Static, not dynamic: a dynamic address is released on deallocate and comes back different,
#    which breaks the DNS records the certificates depend on.
#    Standard SKU: Basic is retired, and Standard denies inbound unless an NSG allows it
#    (Basic allowed it unless an NSG denied it).
az network public-ip create --resource-group $RG --name ${VM}-ip \
  --sku Standard --allocation-method Static --version IPv4

# 3. Network Security Group — three inbound rules and no more.
az network nsg create --resource-group $RG --name ${VM}-nsg

#    SSH, from one address only. Priority 100: lowest number wins, and this is the rule most
#    likely to need to beat something added later by a portal click.
az network nsg rule create --resource-group $RG --nsg-name ${VM}-nsg --name ssh \
  --priority 100 --direction Inbound --access Allow --protocol Tcp \
  --source-address-prefixes $MY_IP/32 --destination-port-ranges 22

#    HTTP. Not optional: Let's Encrypt's HTTP-01 challenge arrives here and Caddy serves the
#    redirect to 443 from it. Closing 80 does not harden anything, it stops TLS working.
az network nsg rule create --resource-group $RG --nsg-name ${VM}-nsg --name http \
  --priority 200 --direction Inbound --access Allow --protocol Tcp \
  --source-address-prefixes '*' --destination-port-ranges 80

az network nsg rule create --resource-group $RG --nsg-name ${VM}-nsg --name https \
  --priority 210 --direction Inbound --access Allow --protocol Tcp \
  --source-address-prefixes '*' --destination-port-ranges 443

# 4. Network.
az network vnet create --resource-group $RG --name ${VM}-vnet \
  --address-prefix 10.0.0.0/16 --subnet-name ${VM}-subnet --subnet-prefix 10.0.1.0/24

# 5. The VM. Ubuntu 22.04 LTS gen2, pinned by full URN rather than the `Ubuntu2204` alias —
#    an alias resolves to whatever your CLI version thinks it means.
az vm create --resource-group $RG --name $VM \
  --image Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest \
  --size Standard_B2s \
  --admin-username azmoth --authentication-type ssh \
  --ssh-key-values ~/.ssh/id_ed25519.pub \
  --public-ip-address ${VM}-ip --nsg ${VM}-nsg \
  --vnet-name ${VM}-vnet --subnet ${VM}-subnet \
  --os-disk-size-gb 64 --storage-sku StandardSSD_LRS

az network public-ip show --resource-group $RG --name ${VM}-ip --query ipAddress --output tsv
```

### There is no rule denying port 8000, and there should not be

Azure's own `DenyAllInBound` sits at priority 65500 and catches everything the three rules above do
not name. **8000 and 5432 are closed because nothing opens them.** Adding an explicit "deny 8000"
rule would be worse than useless: it implies that the absence of such a rule means open, which is the
opposite of how an NSG works, and it would leave 8001 and every other port looking unprotected by
comparison.

Verify rather than assume:

```bash
az network nsg rule list --resource-group $RG --nsg-name ${VM}-nsg \
  --query "sort_by([].{priority:priority,name:name,port:destinationPortRange,source:sourceAddressPrefix}, &priority)" \
  --output table
```

And from outside, which is the check that actually counts — `./scripts/preflight.sh` does this:

```bash
nc -zv -w5 <public-ip> 8000     # must time out
```

### Two walls, not one

The NSG is the outer wall. [`infra/docker/docker-compose.azure.yml`](../../infra/docker/docker-compose.azure.yml)
is the inner one: it unpublishes 8000, 5432, 3000 and 3001 from Docker entirely.

Both exist because **a published Docker port bypasses the host firewall**. Docker writes its own
`DOCKER-USER` iptables rules, so a container publishing 8000 is reachable even when `ufw` insists it
is not. The NSG does stop it — but the NSG is also the thing edited in a portal by someone who does
not know what 8000 is. Neither wall alone would catch the other's mistake.

---

## 3. DNS

Point four records at the address `provision.sh` printed, **and wait for them to resolve before
deploying**. Caddy gets certificates over HTTP-01, which means Let's Encrypt fetches a token from
these names over port 80. A name that does not resolve yet is a failed issuance and a retry backoff,
not a warning.

| Type | Name | Value |
|---|---|---|
| A | `app.azmoth.com` | the public IP |
| A | `api.azmoth.com` | the public IP |
| A | `azmoth.com` | the public IP |
| A | `www.azmoth.com` | the public IP |

```bash
dig +short app.azmoth.com        # should print your VM's IP
```

> **The domain is `azmoth.com`.** `infra/docker/.env.example`, `scripts/deploy.sh` and the marketing
> build arguments all point there; the `.de` the repository used to carry is gone. Everything is
> still parameterised — `./scripts/deploy.sh <ip> --domain <yours>` overrides it — but the default is
> now a decision rather than a placeholder, because the domain is baked into the statically
> prerendered marketing pages at build time: changing it later means a rebuild, not a restart.

---

## 4. Deploying

```bash
./scripts/deploy.sh 20.79.12.34 --domain azmoth.com --acme-email ops@azmoth.com
```

It installs Docker and the Compose plugin if missing, ships the source, generates secrets on first
run, builds, starts, and waits for every healthcheck. First run is 15–25 minutes; afterwards it is
a few minutes because the layers that dominate are cached on the manifests alone.

Re-running it is the normal way to deploy a change:

```bash
git commit -am "fix the thing"
make deploy AZURE_HOST=20.79.12.34
```

Three things worth knowing about it:

**It ships `git archive HEAD`, not your working tree.** Uncommitted changes are not deployed, and it
warns and asks before continuing if you have any. The upside is no credential on the server — a
`git clone` of a private repository means a deploy key living on a box with a public IP — and no
possibility of sweeping up an ignored file, since `git archive` carries tracked files only.

**The secrets are generated once and then never again.** `/opt/azmoth/shared/.env` lives outside the
release directory and is left alone on every deploy after the first. This is the part a deploy
script most often gets wrong:

- `BETTER_AUTH_SECRET` signs every session cookie. A new value on each deploy signs sessions the
  next container cannot verify, and every user is silently logged out on every deploy.
- `POSTGRES_PASSWORD` is worse. The postgres image applies it **only when initialising an empty data
  directory**. On the second deploy the volume already exists, initdb is skipped, and a new password
  is simply never applied — so the engine connects with a password the database does not have, and
  the stack fails with `password authentication failed` for a value that looks perfectly correct in
  the file. Rotating it is a deliberate `ALTER ROLE`, in that order.

**Back that file up.** Copy `/opt/azmoth/shared/.env` into a password manager. Losing it does not
lose the database, but it does mean extracting the password from a running container before you can
ever restart the stack.

---

## 5. TLS, and what `api.azmoth.com` actually serves

[`infra/docker/Caddyfile`](../../infra/docker/Caddyfile) handles TLS with no certificate management
on your part: Caddy requests from Let's Encrypt on first start, renews unattended, and stores both
in the `azmoth-caddy-data` volume.

That volume matters more than it looks. Losing it means re-issuing every certificate on the next
start, and Let's Encrypt rate-limits duplicates to **5 per week**. Two or three deploys that each
wipe it and the pilot has no HTTPS until the window rolls. `docker compose down` keeps it; only
`down -v` removes it.

| Hostname | Serves |
|---|---|
| `app.azmoth.com` | `web:3000` — the review and audit UI, plus HSTS |
| `www.azmoth.com` | `marketing:3000` |
| `azmoth.com` | redirect to `www` |
| `api.azmoth.com` | **`/api/v1/audit/*`, `/api/v1/health`, `/openapi.json`, `/docs` — and 404 for everything else** |

### That last row is deliberate, and it is the one design decision here worth arguing about

You asked for `api.azmoth.com` to terminate TLS for the engine, and it does. But it does **not**
proxy the whole engine, because the engine cannot safely be on the public internet as it stands. The
codebase says so itself, in [`apps/engine/app/api/tenancy.py`](../../apps/engine/app/api/tenancy.py):

> The header is asserted, not proven … the engine is not published to the browser in
> `infra/docker/docker-compose.yml`, and every call therefore arrives from one trusted proxy that
> sets both headers from a session it verified against the database. **A caller who can reach the
> engine directly can name any organisation they like** — which is true of `X-User-ID` today and is
> exactly why the engine must not be exposed.

`/api/v1/solve`, `/api/v1/proposals/*`, `/api/v1/padnext/*` and `/api/v1/settings/*` take their
identity and their tenant from `X-User-ID` and `X-Organization-ID`, which are set by the Next.js
proxy from a verified session. Published directly, anyone could set those headers to anything: write
proposals into an append-only audit log as any user, and read any practice's records by naming their
organisation id.

`/api/v1/audit/*` is different, and it is the surface
[`docs/api/PARTNER_API.md`](../api/PARTNER_API.md) actually documents as commercial. Every endpoint
under it takes `RequestApiKey`: the token in `X-API-Key` is verified against the `api_keys` table on
every request and the tenant comes out of the stored row, so no header can name someone else's
practice. That is safe to publish, so that is what is published.

The allowlist answers `404` rather than `403` for the rest — a `403` confirms the path exists, which
tells someone probing exactly what to come back for.

**What would earn a wider allowlist** is the change `identity.py` names: a Better Auth JWT the engine
verifies itself, with the signature check landing in `require_organization`. Every endpoint
downstream already takes its tenant from there rather than from a query parameter, so it is a
contained change — it is just not this week's.

---

## 6. Backups

[`infra/scripts/backup-to-azure.sh`](../../infra/scripts/backup-to-azure.sh) wraps the existing
`backup-db.sh` — which already verifies its own dump by reading the archive's table of contents —
then encrypts and pushes to Blob Storage in the same region.

```bash
make azure-backup AZURE_HOST=20.79.12.34
```

**Blob Storage, not a second disk.** A disk attached to this VM dies with this VM, and with the
resource group, and with the subscription when the credit runs out. A blob survives all three and
costs about a cent per gigabyte-month in the Cool tier.

**No credential on the VM.** Authentication is the VM's system-assigned managed identity, granted
`Storage Blob Data Contributor` on that one container. `az login --identity` gets a short-lived
token from the instance metadata endpoint. A storage account key would be a long-lived credential
with full control of the account, sitting on disk next to the very dumps it protects.

**The VM can encrypt and cannot decrypt.** The dump is encrypted with `age` to a *public* key; the
private key never touches the VM. A compromised VM can write backups and cannot read one back — and
neither can anyone who gains read access to the container. Azure's at-rest encryption protects
against a stolen disk in a datacentre; this protects against the container being made readable by a
misconfiguration, which is the failure that actually happens.

Set it up once:

```bash
# on your laptop
age-keygen -o azmoth-backup.key          # → the private key goes in a password manager, nowhere else

# on the VM
echo 'AGE_RECIPIENT=age1ql3z...'        | sudo tee -a /opt/azmoth/shared/.env
echo 'STORAGE_ACCOUNT=azmothbackupxxxx' | sudo tee -a /opt/azmoth/shared/.env
sudo apt-get install -y age
sudo crontab -e
```

```cron
15 3 * * * /opt/azmoth/repo/infra/scripts/backup-to-azure.sh >> /var/log/azmoth-backup.log 2>&1
```

Losing the private key loses every backup. That is the trade, and it is worth making — but put the
key in the password manager *now*, not after the first backup runs.

Restoring, including from a blob when the VM's disk is gone, is
[`docs/OPERATIONS.md` § 7.7](../OPERATIONS.md#77-restoring).

---

## 7. Pre-flight checklist

```bash
./scripts/preflight.sh 20.79.12.34 --domain azmoth.com
```

It checks from the **outside**, which is the point: `docker compose ps` proves the containers are up
and proves nothing about what the internet can reach. Exit status is 0 only if everything passes.

What it verifies:

**Ports [SEC]**
- 80 and 443 open
- **8000 closed** — the engine, which authenticates nobody
- 5432, 3000, 3001, 8080 closed

**TLS**
- A real Let's Encrypt certificate on all four names, with days remaining — not the self-signed one
  Caddy serves while ACME is failing, which from a browser looks like a scary warning rather than
  "issuance is in a backoff"
- `http://` redirects to `https://`

**The `api.` allowlist [SEC]**
- `POST /api/v1/audit/single` without a key → `401` (reachable, and refusing)
- `/api/v1/health` and `/openapi.json` → `200`
- `/api/v1/solve`, `/api/v1/proposals`, `/api/v1/padnext/audit`, `/api/v1/settings/api-keys`,
  `/api/v1/rules`, `/api/v1/demo` → **`404`**

**The application**
- `/api/health` → 200; the marketing site → 200
- Any cookie set carries `Secure`

**On the box**
- Every container running and healthy
- The engine is on Postgres, not the SQLite default, and `alembic current` reports a revision
- The 4 GiB swapfile exists — without it the next build is OOM-killed
- Root filesystem under 80% — a full disk looks like everything failing at once

**Backups**
- `backup-db.sh` produces a dump that passes its own verification
- **That dump restores into a scratch database and every row count matches.** This is the check that
  distinguishes "a file exists" from "a backup". It never touches the live database.

### Then, by hand

- [ ] **Decide who may register, and check it took.** `SIGNUP_ALLOWLIST` in
      `/opt/azmoth/shared/.env` is the whole of the admission control on a public box — there is no
      invitation flow behind it, and an empty value admits nobody. `deploy.sh` writes what
      `--signup-allowlist` gave it and defaults to `admin@<domain>` with a warning. Read it back
      out of the **running container**, not out of the file, because a value added after the last
      `up -d` is not in the process:

      ```bash
      make azure-shell   # then:
      sudo COMPOSE_PROJECT_NAME=azmoth docker compose \
        -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.azure.yml \
        exec -T web printenv SIGNUP_ALLOWLIST
      ```

      `scripts/preflight.sh` runs exactly this and fails on an empty answer.
- [ ] Sign up, sign in, sign out in a browser — and confirm an address that is **not** on the list
      is refused
- [ ] Upload a PADnext delivery and confirm the report renders
- [ ] Confirm `schema_warnings` appears on a report from a non-conforming export
      (`PADNEXT_SCHEMA_POLICY=warn` is the pilot setting)
- [ ] Mint an API key and call `/api/v1/audit/single` from your laptop with it
- [ ] Copy `/opt/azmoth/shared/.env` into a password manager
- [ ] Install the backup cron — nothing does it for you
- [ ] Store the `age` private key
- [ ] Name Microsoft Azure as a processor in the AVV annex § 5.2

---

## 8. Day two

Everything operational — logs, restarts, psql, restores, cost, and a table of failure modes — is
[`docs/OPERATIONS.md` § 7](../OPERATIONS.md#7-the-azure-deployment).

The one command worth knowing before you need it:

```bash
az vm deallocate --resource-group azmoth-pilot --name azmoth-vm
```

That stops compute billing if the pilot pauses. Disk and IP keep billing at ~9 EUR/month, and the
static IP is what makes the DNS records and certificates survive the gap. **`az vm stop` is not the
same thing** — it shuts the guest down and leaves the VM allocated, billing exactly as if it were
running.
