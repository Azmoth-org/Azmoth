# Deploying Azmoth on Azure

One VM, Docker Compose, Caddy in front. No container service, no Kubernetes, and — now — no database
on the box either. Not because the managed alternatives are bad, but because a 100 EUR credit buys
roughly five months of this shape and about three weeks of the alternative, and a pilot needs the
months.

Three things run somewhere other than the VM, and each of them is why the VM got smaller:

| | Where | Why it is not on the VM |
|---|---|---|
| The marketing site (`apps/marketing`) | **Vercel**, at `azmoth.com` + `www` | It has no database, no session and no engine. Moving it off removed the second `next build` from the deploy. |
| Postgres | **Neon**, `aws-eu-central-1` | A managed Postgres with point-in-time restore for 0 EUR beats a container that shares 2 GiB with the app. |
| The three images | **GHCR**, built by GitHub Actions | A `next build` peaks well over 1 GiB. Building on a runner is what took the VM from 4 GiB to 2. |

This document is the **why**. [`docs/deploy/RUNBOOK.md`](RUNBOOK.md) is the **what to type** — the
chronological, command-by-command procedure, including the Neon and Vercel setup. If you are
deploying right now, read that one and come back here when something looks arbitrary.

```
  ./infra/azure/provision.sh          VM, static IP, firewall, backup storage
  <create the Neon project>           aws-eu-central-1, and copy BOTH connection strings
  <point TWO A records at the IP>     app and api — NOT the apex, NOT www (see § 3)
  ./scripts/deploy.sh <ip>            pull from GHCR, migrate Neon, start behind Caddy
  ./scripts/preflight.sh <ip>         verify from outside
```

---

## 1. The VM

**`Standard_B1ms` — 1 vCPU, 2 GiB RAM, 32 GiB StandardSSD (E4), Ubuntu 22.04 LTS (gen2),
`germanywestcentral`.**

### Why 2 GiB is enough now, and was not before

The old size was set by the **build**, not by the run. `scripts/deploy.sh` used to run
`docker compose build` over SSH, and that build was two `next build`s plus a node-gyp compile. Next
peaks well over 1 GiB per build, so a 2 GiB box was OOM-killed — exit 137, no message, reliably
misdiagnosed as a broken Dockerfile. The box had to be 4 GiB to build what it could comfortably run
in 1.5.

**Nothing is built on this box any more.**
[`.github/workflows/release-images.yml`](../../.github/workflows/release-images.yml) builds three
images on a GitHub runner and pushes them to `ghcr.io` tagged with the commit sha; the VM pulls
them. That single change is what took the VM from `Standard_B2s` (4 GiB, 30.08 EUR/mo, 2.9 months
of credit) to `Standard_B1ms` (2 GiB, 15.04 EUR/mo, 4.9 months), and it is the only reason a 100 EUR
credit reaches nearly five months rather than under three.

What is left to fit is the *run*: Caddy, the engine and the web tier, resting at roughly 500–800 MiB
between them, plus about 250 MiB for `dockerd` and the OS. Postgres left the box and so did the
marketing site, which is most of the difference from the old 1.5 GiB figure.

[`infra/azure/provision.sh`](../../infra/azure/provision.sh) still configures a **4 GiB swapfile**
with `vm.swappiness=10`, and the reason has changed even though the number has not. It used to be
what made `next build` survive its peak. Now it is runtime insurance: a Soufflé solve forks a
process whose peak nobody has characterised, and the failure mode without swap is the OOM killer
choosing a victim — which on a box running three containers means the `web` container disappearing
while somebody was mid-approval.

Swap is not a substitute for RAM. If `free -m` shows swap in *steady* use rather than touched at
peaks, the machine is too small — take the next rung of the ladder below rather than adding more
swap. `scripts/preflight.sh` checks both the swapfile and the available memory at rest for exactly
this reason.

### The size may not allocate, and there is a ladder for that

**B-series v1 — `B1s`, `B1ms`, `B2s`, `B1ls` — retires 15 November 2028**, and since **31 July
2026** has been under a *growth restriction*: new deployments, quota increases, and any operation
needing a fresh allocation (start-after-deallocate, redeploy, resize) can fail. Microsoft's wording
is that availability "has already been restricted or removed in many regions, particularly for new
deployments and newly created subscriptions". Whether `germanywestcentral` is affected is not
documented either way, so `provision.sh` asks `az vm list-skus` before it creates anything and warns
rather than refuses.

If `az vm create` refuses the size, do not fight it — take the next rung and accept the shorter
runway. Bsv2/Basv2/Bpsv2 are the designated replacements and are not retiring:

| `VM_SIZE` | vCPU / GiB | EUR/mo | Runway on 100 EUR | |
|---|---|---|---|---|
| **`Standard_B1ms`** | **1 / 2** | **15.04** | **~4.9 months** | **the default** |
| `Standard_B2als_v2` | 2 / 4 | 27.08 | ~3.1 months | AMD, not retiring |
| `Standard_B2s` | 2 / 4 | 30.08 | ~2.9 months | v1, retiring, growth-restricted |

```bash
VM_SIZE=Standard_B2als_v2 ./infra/azure/provision.sh
```

### Why not the others

Prices are Linux pay-as-you-go in `germanywestcentral`, from the Azure Retail Prices API in EUR at
730 hours. Runway figures anywhere in this document are the VM plus the fixed 5.25 EUR/month of
disk, static IP and Blob from the cost table below.

| Size | vCPU / GiB | EUR/mo | Verdict |
|---|---|---|---|
| `Standard_B1ls` | 1 / 0.5 | 3.80 | Half a gigabyte, most of which is the OS and `dockerd`. Not a candidate. |
| `Standard_B1s` | 1 / 1 | 7.52 | The resting stack does not fit; the engine would page during exactly the solves the product exists to run. |
| `Standard_B2ats_v2` (AMD) | 2 / 1 | 6.79 | Eight months of runway and the same 1 GiB problem. Costed and rejected. |
| **`Standard_B1ms`** | **1 / 2** | **15.04** | **Runs the stack with headroom. ~4.9 months.** |
| `Standard_B2pls_v2` (Arm) | 2 / 4 | 24.09 | Cheapest 4 GiB SKU of any architecture — **and it cannot run the engine.** See below. |
| `Standard_B2als_v2` (AMD) | 2 / 4 | 27.08 | The fallback. Cheapest x86 4 GiB, and not retiring. |
| `Standard_B2s` | 2 / 4 | 30.08 | The old default. v1, growth-restricted, and dearer than the AMD equivalent. |
| `Standard_B2ls_v2` | 2 / 4 | 30.08 | **Not cheaper than `B2s`.** An earlier version of this document claimed ~20% cheaper and a comment in the repo said the same; both were wrong. Identical price, newer series. |
| `Standard_B2s_v2` | 2 / 8 | 60.15 | Twice the price for memory nothing here needs. Cuts the runway to ~1.5 months. |

**Not Arm, however tempting the price is.**
[`apps/engine/Dockerfile:26`](../../apps/engine/Dockerfile) pins
`SOUFFLE_DEB=x86_64-ubuntu-2204-souffle-2.5-Linux.deb`, and the engine is nothing without Soufflé.
So `release-images.yml` builds `linux/amd64` only, deliberately: publishing an arm64 *web* image
alone would let somebody provision a `B2pls_v2`, point DNS at it, and discover the engine cannot run
there. Moving to Arm is a new Soufflé build, a multi-arch image and a re-run of the golden snapshots
— the version is part of the receipt hash — not a `VM_SIZE` change.

B-series are burstable: a percentage baseline that banks credits while idle. A pilot's traffic does
not come close to the baseline, and the thing that used to burn the credits — the build — is gone.

### The disk is 32 GiB, down from 64

There is no build cache on this box any more, so what has to fit is Ubuntu, Docker, three pulled
images (engine ~300 MB, web ~350 MB, the `web-builder` image ~1 GB, Caddy ~50 MB — under 2 GiB
together) and the `azmoth-engine-uploads` volume. 32 GiB is roughly ten times what is needed, which
is the right margin for a disk whose size **cannot be reduced later**.

StandardSSD rather than Premium because a pilot's write rate does not need provisioned IOPS, and
rather than Standard HDD because container start latency on spinning rust is miserable and the
saving is negative anyway — E4 (32 GiB SSD) is 2.06 EUR/mo against S6 (64 GiB HDD) at 2.58.

Disks bill on the **provisioned size tier, not on bytes used**, and keep billing while the VM is
deallocated. Going from E6 to E4 is therefore a real 2.06 EUR/month, or about five days of runway.

### What the whole thing costs

| | EUR/month |
|---|---|
| `Standard_B1ms` VM | 15.04 |
| 32 GiB StandardSSD (E4) | 2.06 |
| Standard static IPv4 | 3.14 |
| Blob Storage, Cool, a few GB of dumps | ~0.05 |
| Egress | 0.00 — first 100 GB/month is free |
| **Neon**, Free plan | 0.00 |
| **GHCR**, container storage and bandwidth | 0.00 |
| **GitHub Actions** | 0.00 — within the 2,000 free minutes/month |
| **Vercel**, Hobby | 0.00 |
| **Total** | **20.29** |

**~4.9 months on 100 EUR.** Four of the nine lines are zero, and three of those four are zero
*because somebody else is currently choosing to make them zero*:

- **GHCR.** GitHub's billing documentation says, verbatim, "Container image storage and bandwidth
  for the Container registry is currently free" — all plans, any volume — with **at least one
  month's notice** before that changes. If it ever does, the published prices are $0.25/GB-month of
  storage and $0.50/GB of egress, and the first thing to reconsider is the `azmoth-web-builder`
  image, which is the largest of the three and exists to run one script (see § 5).
- **Actions.** 2,000 minutes/month on GitHub Free for a personal account; `ubuntu-latest` bills at
  $0.006/minute beyond that. Three cached image builds per push is comfortably inside it for a
  pilot's commit rate. Public repositories are unmetered entirely.
- **Vercel Hobby** is free for non-commercial use. A pilot with paying practices needs a paid plan,
  and that line stops being zero — but it is a decision about the marketing site, not about this
  deployment, and it does not change the VM's runway.

Prices move. Check yours before committing:

```bash
az vm list-skus --location germanywestcentral --size Standard_B1 --output table
make azure-cost                                   # what the pilot has spent so far, and on what
# and https://azure.microsoft.com/pricing/calculator/
```

> **Check what the credit actually is before planning around it.** A "100 EUR credit" is almost
> certainly **Azure for Students — $100 USD, valid 12 months, no credit card**. The Azure free
> account's credit is **$200 and expires in 30 days**, which is a fortnight of evaluation and not a
> pilot; converting it to pay-as-you-go within those 30 days is also what unlocks the 12-months-free
> service tier (750 h/month of `B1s`, `B2pts_v2` or `B2ats_v2` — all 1 GiB, none of which run this
> stack). Getting these two confused is the difference between a five-month runway and a four-week
> one.

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
to save a euro.

The database is in Frankfurt too — but not here, and not Microsoft's. See § 4.

> **One thing to fix before a practice signs anything.** That same annex, § 5.2, says
> "**Unterauftragsverarbeiter: derzeit keine**" — currently no sub-processors, and explicitly no
> external storage services. Deploying this makes that untrue in **four** ways, and every one of
> them has to be named in the document before it goes to a customer:
>
> | Sub-processor | What it holds | Where |
> |---|---|---|
> | **Microsoft Azure** | the VM, and the encrypted dumps in Blob Storage | `germanywestcentral` (Frankfurt) |
> | **Neon, LLC / Databricks, Inc.** | every proposal, approval and audit event | `aws-eu-central-1` (Frankfurt) |
> | **Amazon Web Services** | the infrastructure Neon runs on | `aws-eu-central-1` (Frankfurt) |
> | **Vercel** | the public marketing site — no patient data | Vercel's edge |
>
> Two details a lawyer will ask about, so they are here rather than discovered. **Neon's own
> sub-processor page 308-redirects to `databricks.com/legal/databricks-subprocessors`** — Databricks
> acquired Neon in May 2025 and Neon's platform terms now read "Databricks, Inc., the parent company
> of Neon, LLC". That Databricks list is long and mostly US-located, and Neon's schedule adds
> **Grafana Labs (US)** on top of it. And the self-serve DPA at `neon.com/dpa` is a click-accept
> *schedule*, not a signed contract: an executable AVV has to be requested from Databricks legal.
>
> This is a paperwork change rather than an architecture one, but it is a blocker on the pilot
> rather than on the deployment.

### No separate data disk

It was considered for backups and rejected, and there is now even less reason for one: the database
is not on this box at all. A disk attached to this VM is deleted with this VM, and
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

Idempotent — every step checks before it creates, so a run that fails halfway (a quota refusal, a
dropped connection) is fixed by running it again rather than by working out which half happened.
Override anything from the environment:

```bash
VM_SIZE=Standard_B2als_v2 LOCATION=germanywestcentral RG=azmoth-pilot ./infra/azure/provision.sh
```

It refuses to start without an SSH public key, and it **refuses to open port 22 to the internet** —
if it cannot detect your public IP it stops and asks for it rather than defaulting to `0.0.0.0/0`.

It creates no managed database, no container service and no load balancer. It does create a Blob
Storage account and grants the VM a managed identity on one container — see § 6 for why that
survived the move to Neon.

### The same thing by hand

If you would rather run the commands yourself, this is what the script does.

```bash
RG=azmoth-pilot
LOCATION=germanywestcentral
VM=azmoth-vm
MY_IP=$(curl -s https://api.ipify.org)

# 1. Resource group. One group holds everything, so teardown is a single delete with nothing
#    orphaned quietly accruing charges — which is the failure mode that eats a fixed credit.
az group create --name $RG --location $LOCATION

# 2. Static public IP.
#    Static, not dynamic: a dynamic address is released on deallocate and comes back different,
#    which breaks the DNS records the certificates depend on.
#    Standard SKU: Basic was retired in September 2025, and Standard denies inbound unless an NSG
#    allows it (Basic allowed it unless an NSG denied it).
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
  --size Standard_B1ms \
  --admin-username azmoth --authentication-type ssh \
  --ssh-key-values ~/.ssh/id_ed25519.pub \
  --public-ip-address ${VM}-ip --nsg ${VM}-nsg \
  --vnet-name ${VM}-vnet --subnet ${VM}-subnet \
  --os-disk-size-gb 32 --storage-sku StandardSSD_LRS

az network public-ip show --resource-group $RG --name ${VM}-ip --query ipAddress --output tsv
```

### No outbound rule for the database, and that is worth knowing

Azure allows outbound traffic by default, so nothing here opens anything for Neon. The engine
reaches Frankfurt over TLS on 5432 rather than a container on localhost, and that flow is invisible
in the NSG because it needs no rule.

If you ever tighten egress, **that is the flow to remember**. A locked-down outbound rule set is a
stack that comes up healthy, passes its own healthchecks, and cannot read a single proposal.

### There is no rule denying port 8000, and there should not be

Azure's own `DenyAllInBound` sits at priority 65500 and catches everything the three rules above do
not name. **8000 is closed because nothing opens it.** Adding an explicit "deny 8000" rule would be
worse than useless: it implies that the absence of such a rule means open, which is the opposite of
how an NSG works, and it would leave 8001 and every other port looking unprotected by comparison.

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

The NSG is the outer wall.
[`infra/docker/docker-compose.azure.yml`](../../infra/docker/docker-compose.azure.yml) is the inner
one: it unpublishes 8000 (engine) and 3000 (web) from Docker entirely, and 5432 and 3001 disappear
along with the `postgres` and `marketing` services that used to publish them.

Both exist because **a published Docker port bypasses the host firewall**. Docker writes its own
`DOCKER-USER` iptables rules, so a container publishing 8000 is reachable even when `ufw` insists it
is not. The NSG does stop it — but the NSG is also the thing edited in a portal by someone who does
not know what 8000 is, and a published port is added by someone editing compose. Neither wall alone
would catch the other's mistake.

The `!reset` merge tag is what does the unpublishing, and it needs **Docker Compose v2.24 or
newer**. Compose's default for `ports` is to *concatenate* the base list with the override's, so on
an older Compose the tag is not understood, `8000:8000` survives, and the engine is published on a
public IP. `scripts/deploy.sh` asserts the version before it runs anything.

---

## 3. DNS — **two** records, and two that must not move

Point **two** A records at the address `provision.sh` printed, and wait for them to resolve before
deploying. Caddy gets certificates over HTTP-01, which means Let's Encrypt fetches a token from
these names over port 80. A name that does not resolve yet is a failed issuance and a retry backoff,
not a warning.

| Type | Name | Value |
|---|---|---|
| A | `app.azmoth.com` | the VM's public IP |
| A | `api.azmoth.com` | the VM's public IP |

That is the whole list.

> **Do NOT point `azmoth.com` or `www.azmoth.com` at this VM.** An earlier version of this document
> listed four A records, all at the VM, and following it now would do two things at once. The
> marketing site is **live on Vercel** at those names; there is no `marketing` container in this
> deployment and [`infra/docker/Caddyfile`](../../infra/docker/Caddyfile) has no site block for
> them, so Caddy would answer with its default site and **the public site would go down**. Caddy
> would then also request a Let's Encrypt certificate for a name Vercel already holds one for,
> burning one of five weekly duplicates and leaving the site answering from whichever of the two
> DNS resolution happened to reach — a marketing outage that gets diagnosed as a TLS problem.
>
> Leave those records wherever Vercel put them. The apex→`www` redirect that used to live in the
> Caddyfile is Vercel's to make now, because Vercel is the only thing that can see both names.

```bash
dig +short app.azmoth.com        # should print the VM's IP
dig +short api.azmoth.com        # should print the VM's IP
dig +short azmoth.com            # must NOT be the VM's IP
dig +short www.azmoth.com        # must NOT be the VM's IP  (a CNAME to Vercel is normal)
```

This is not left to a reader's care. `scripts/deploy.sh` **refuses to deploy** — the only fatal DNS
condition in the script — if the apex or `www` resolves to the host you are deploying to, and
`scripts/preflight.sh` § 2b asserts the same thing on every run and marks it `[SEC]`. That check
replaced an old one which fetched `https://www.azmoth.com/` and expected a 200: with the site on
Vercel that passed no matter what the VM was doing, so it reported the deployment healthy on the
strength of a service the deployment has nothing to do with.

> **The domain is `azmoth.com`.** [`infra/docker/.env.example`](../../infra/docker/.env.example) and
> `scripts/deploy.sh` both default to it; the `.de` the repository used to carry is gone. Everything
> is still parameterised — `./scripts/deploy.sh <ip> --domain <yours>` derives `app.` and `api.`
> from it and does not touch the apex — but changing the domain now also means changing it in the
> Vercel project, because the marketing pages are statically prerendered and the URL is baked in at
> build time.

---

## 4. The database — Neon, and why it is on AWS

**Neon, external, project region `aws-eu-central-1` (AWS Europe, Frankfurt), Free plan.**

There is no `postgres` container, no `postgres-data` volume and no `POSTGRES_PASSWORD` anywhere in
this deployment. The base compose file still defines `postgres` — it is still the right standalone
stack for a laptop — but the Azure override assigns it a profile nothing enables, which removes it
from `docker compose config` and from `up` entirely, and its volume with it. `docker compose config
--services` on the pair is the check that it worked, and `scripts/deploy.sh` runs exactly that
assertion before starting anything.

### Why not an Azure region

Matching the VM's region would have kept the sub-processor list to one name, and it is not
available: **Neon deprecated all of its Azure regions on 7 April 2026 and no longer accepts new
projects in any of them, on any plan.** `azure-gwc` is gone, the Azure Native Integration is
retired, and feature updates for existing Azure-region projects stop on 5 October 2026. Neon offers
eight AWS regions, of which two are in the EU: `aws-eu-central-1` (Frankfurt) and `aws-eu-west-2`
(London).

So: `aws-eu-central-1`. Same city as the VM, same union, different provider —
[`docs/AVV_TECHNICAL_ANNEX_DRAFT.md`](../AVV_TECHNICAL_ANNEX_DRAFT.md) § 5.1 ("ausschliesslich
innerhalb der Europäischen Union") holds, and that is the point of choosing Frankfurt over London.

What it changes is § 5.2. **Neon, LLC / Databricks, Inc.** and **Amazon Web Services** both join the
sub-processor list, alongside Microsoft Azure for the VM and Vercel for the public site — four names
where the annex currently says there are none. The full table, and the two details a lawyer will ask
about (Neon's sub-processor page redirecting to Databricks', and the self-serve DPA being a
click-accept schedule rather than a signed contract), are in the blockquote in § 1.

**The region is fixed at project creation and cannot be changed.** Getting it wrong means creating a
new project and dumping and restoring into it. `scripts/preflight.sh` § 7 has a manual checkbox for
confirming it in the console, because nothing on the VM can tell you what region a connection string
terminates in.

### Two connection strings, and they are not interchangeable

Both come out of the Neon console's Connect dialog. The difference is the "Connection pooling"
toggle, and it shows up in the hostname as a `-pooler` infix:

```
DATABASE_URL         ep-cool-darkness-a1b2c3d4.eu-central-1.aws.neon.tech
DATABASE_URL_POOLED  ep-cool-darkness-a1b2c3d4-pooler.eu-central-1.aws.neon.tech
                                             ^^^^^^^
```

| | Endpoint | Consumers |
|---|---|---|
| `DATABASE_URL` | **direct** (non-pooled) | `alembic upgrade head` (`engine-migrate`); Better Auth's table creation (`web-auth-migrate`); **the engine at runtime**; `pg_dump` (`backup-to-azure.sh`) |
| `DATABASE_URL_POOLED` | **pooled** (PgBouncer, transaction mode) | Better Auth at runtime, in the `web` service. Nothing else. |

Three of the four direct-endpoint consumers are uncontroversial. Two of them are **migrations**, and
Neon's own SQLAlchemy guidance says so in as many words: "using a pooled connection string for
migrations can be prone to errors. For this reason, we recommend using a direct (non-pooled)
connection when performing migrations." A transaction-mode pooler does not support session-level
advisory locks — which is how a migration tool stops two runners colliding — nor SQL-level
`PREPARE`/`DEALLOCATE`, nor `CREATE INDEX CONCURRENTLY`. The third, **`pg_dump`**, holds one
transaction open across hundreds of statements and a transaction-mode pooler does not promise to
keep it on one server connection; the result would be a dump that restores into a state that never
existed.

The fourth — **the engine at runtime** — is the interesting one.

### Why the engine gets the DIRECT endpoint — the least obvious decision here

Every instinct says a pooler is free performance and you take it. For this engine it is not, and the
reason is specific enough to be worth writing down, because the fix that the internet will offer you
does not work.

Neon's pooler is PgBouncer in **transaction mode**, with `max_prepared_statements=1000` and
settings Neon states plainly are "not user-configurable". SQLAlchemy's asyncpg dialect calls
`asyncpg.connection.prepare()` for **every** statement, and asyncpg names those prepared statements
`__asyncpg_stmt_N__` from a per-connection counter. Through a transaction-mode pooler — where a
"connection" the client thinks it owns is a different server connection from one transaction to the
next — that is the classic source of intermittent
`DuplicatePreparedStatementError: prepared statement "__asyncpg_stmt_3__" already exists`.

The two URL-level fixes you will be offered:

| | What it actually does |
|---|---|
| `?prepared_statement_cache_size=0` | **Does not fix it.** It sets SQLAlchemy's reuse cache to `None` and nothing else. Both the cached and uncached code paths still call `prepare(operation, name=self._prepared_statement_name_func())`, and the default name function **returns `None`** — at which point asyncpg falls back to `named = (statement_cache_size > 0)`, which is `True`, and mints `__asyncpg_stmt_N__` anyway. Named prepared statements are still created on every execute. |
| `?statement_cache_size=0` | **Worse.** SQLAlchemy's `create_connect_args` only int-coerces `prepared_statement_cache_size`, so asyncpg receives the string `'0'` and raises `TypeError: '<' not supported between instances of 'str' and 'int'` at startup. |

The configuration SQLAlchemy actually prescribes for PgBouncer is `prepared_statement_name_func`
(a function returning a UUID-suffixed name) **plus `poolclass=NullPool`** — and both are Python
arguments to `create_async_engine`. They live in
[`apps/engine/app/db/session.py`](../../apps/engine/app/db/session.py)`::build_engine` and
**cannot be expressed in a URL at all.** SQLAlchemy also wants PgBouncer configured to `DISCARD` on
connection return, which on Neon is one of the settings that is not user-configurable.

There is a real chance none of this bites. Neon runs PgBouncer 1.22 or newer, which remaps
protocol-level prepared statement names per client connection, and Neon states protocol-level
prepared statements *are* supported on pooled connections. It may well work in practice. But Neon
documents **nothing** about asyncpg — zero hits for "asyncpg" across its docs index — and "probably
fine" is not a property to give an append-only clinical audit log. The failure would not be a clean
refusal at startup either. It would be an intermittent, concurrency-dependent 500 that appears under
load and vanishes when anyone looks.

**And the engine does not need a pooler in the first place.** It is *one* long-lived container with
`pool_size=5` and `max_overflow=10`, so it holds at most fifteen connections against a Neon compute
that allows far more. A pooler earns its keep against connection-per-request workloads — which is
`web`, which is why the pooled string goes there.

Better Auth is the mirror image of all of this, and it genuinely benefits. It talks to Postgres
through node-postgres (`pg`), which issues plain unnamed queries and does not use protocol-level
prepared statements, so it is safe behind a transaction-mode pooler in a way asyncpg is not. And
every Next.js route handler is a short burst of queries with idle gaps between them — exactly the
shape the pooler exists for. On the direct endpoint a busy moment could open one connection per
concurrent request.

The split is asserted, not assumed. `scripts/deploy.sh` refuses a `DATABASE_URL` whose host contains
`-pooler` and refuses a `DATABASE_URL_POOLED` whose host does not, checks after starting that the
*running* engine container resolved a non-pooled host, and `scripts/preflight.sh` § 6 marks the same
check `[SEC]`. `backup-to-azure.sh` refuses a pooled URL outright.

One note on the URL itself: the `+asyncpg` suffix is SQLAlchemy's — the driver is part of the
scheme. Neon gives you a plain `postgresql://`; add `+asyncpg`. `apps/web/lib/auth-db.ts` strips it
for node-postgres and `backup-to-azure.sh` strips it for libpq, so one stored value serves all three
consumers.

### The Free plan's limits are worth an operator's attention

The Free plan is genuinely sufficient for a pilot, and its edges are sharper than a managed
database's usually are:

| | Free plan |
|---|---|
| Storage | **0.5 GB per project.** Over it, writes fail. |
| Compute | **100 CU-hours per project per month.** |
| Network transfer | 5 GB/month |
| Scale to zero | After 5 minutes idle, and **cannot be disabled on Free** |
| History window | **6 hours, capped at 1 GB** |
| Scheduled backups | None. One manual snapshot. |
| Support / SLA | Community; no SLA. Compliance certificates (SOC 2, ISO, HIPAA) are Scale-plan features. |

Two of those have operational consequences rather than merely numbers.

**Scale-to-zero means the first request after an idle spell is a cold start.** This is why
`MIGRATION_WAIT_SECONDS` exists and defaults to 60: the first connection of a deploy is very often
against a suspended compute, and the cost of that timeout being too short is a failed deploy that
reads like a broken migration. It is set on both `engine-migrate` and `engine` — the first for the
ordered case, the second so the engine survives a cold start on an unattended restart. Neon's own
SQLAlchemy advice for the same reason: `pool_pre_ping=True` and a `pool_recycle` at or below the
scale-to-zero delay.

**Exhausting the allowance is a hard cap, not an overage bill.** Neon's wording is that compute is
suspended and "existing connections drop and new ones can't open" until the next billing period.
There is no overage billing and no data is deleted — but the pilot **goes down**, mid-session, and
it does not degrade first. Watch it in the console, or set a spend limit. `preflight.sh` names this
explicitly as the thing that makes a previously-working `select 1` start failing.

One more, further out: Free-plan projects idle for 90 days or more are subject to deletion as of
5 October 2026. That is one of the three reasons the Blob Storage backups survived the move to Neon
— see § 6.

### When to upgrade, and what it costs

The **Launch** plan is usage-based with **no monthly minimum** (the old $5 floor was dropped in
December 2025): **$0.106 per CU-hour** and **$0.35/GB-month** of storage. At pilot volume that is
roughly **3–8 EUR/month**, which the 20.29 EUR budget in § 1 accommodates without changing the
runway much.

What it buys is worth knowing before you need it: a **7-day history window** instead of six hours,
the ability to **disable scale-to-zero** (so no cold starts), scheduled backups, and 100 snapshots.
The upgrade trigger is any one of: the Free storage or compute cap coming into view, a cold start
becoming visible to a practice, or the six-hour history window being too short to be useful during
an incident.

Rotating the credentials is a Neon-console operation — "Reset password" on the role — followed by
editing **both** lines in `/opt/azmoth/shared/.env` and re-running `scripts/deploy.sh`. There is no
`ALTER ROLE` for you to run.

An operator's `psql` is now a client pointed at the Neon URL, not a `docker compose exec`:

```bash
make azure-psql AZURE_HOST=20.79.12.34     # runs psql in a container on the VM; installs nothing
```

---

## 5. Deploying

```bash
./scripts/deploy.sh 20.79.12.34 --domain azmoth.com --acme-email ops@azmoth.com
```

It installs Docker and the Compose plugin if missing, ships the source, writes the secrets on the
first run only, logs in to `ghcr.io`, **pulls** the three images for the commit, runs both
migrators against Neon's direct endpoint, starts the stack behind Caddy, and waits for every
healthcheck. First run is a few minutes, dominated by the `apt` install and the pull; afterwards it
is faster. Re-running it is the normal way to deploy a change.

The step-by-step, including what to have ready before you start, is
[`docs/deploy/RUNBOOK.md`](RUNBOOK.md). What follows is the four things about it that are decisions
rather than steps.

### Nothing is built on the VM

`.github/workflows/release-images.yml` builds and pushes three images tagged with the commit sha:

| Image | From | What for |
|---|---|---|
| `ghcr.io/<owner>/azmoth-engine` | `apps/engine/Dockerfile` | FastAPI, Soufflé, Clingo |
| `ghcr.io/<owner>/azmoth-web` | `apps/web/Dockerfile` | the traced Next.js standalone bundle |
| `ghcr.io/<owner>/azmoth-web-builder` | `apps/web/Dockerfile`, `target: builder` | **only** to run Better Auth's migrator |

The third is the non-obvious one, and it looks like waste. `web-auth-migrate` runs
`pnpm --filter web auth:migrate`, and the shipped runtime image carries no pnpm, no scripts and no
TypeScript — that is the whole point of the standalone trace. On a box that builds nothing there is
no `builder` stage to reach for locally, so it has to be published. It is by far the largest of the
three and it exists to run one script; that is an acceptable trade only while GHCR does not charge
for container storage. If that changes, the alternative is to bake `auth:migrate` into the runtime
image rather than publish a second copy of the build.

So **the commit you deploy must have been pushed, and its workflow must have finished.**
`deploy.sh` checks the manifests exist over the registry API from your laptop, before it touches the
VM, because the alternative is discovering it after Docker has been installed and the source
shipped.

The override enforces this rather than trusting it: `build: !reset null` deletes the base file's
build section outright, so the stack can only ever pull. Leaving `build:` in place and relying on
nobody passing `--build` would not do — `compose up` builds on its own when a named image is absent
locally, so a failed `docker pull` would silently become an on-box build. With no build section, a
missing image is an error that names the tag.

The VM needs a registry credential to pull private images: a GitHub **classic** personal access
token whose only scope is `read:packages`. It cannot push an image, cannot read the repository
source and cannot act on the account — it is the least a `docker pull` can be given. `deploy.sh`
prompts for it without echoing and stores it in `/opt/azmoth/shared/.env` at mode 600, because an
unattended restart has to be able to pull without a human. A fine-grained token is not used because
those have never covered organisation-owned packages reliably.

### It ships `git archive HEAD`, not your working tree

Uncommitted changes are not deployed, and `deploy.sh` warns and asks before continuing if you have
any. The images carry the application; the VM still needs the two compose files and the Caddyfile,
and `git archive` sends exactly the commit you have checked out with no credential on the server —
a `git clone` of a private repository means a deploy key living on a box with a public IP. It also
cannot sweep up an ignored file, because `git archive` carries tracked files only.

`/opt/azmoth/RELEASE` records the commit, so `ssh <host> cat /opt/azmoth/RELEASE` answers "what is
running" — and it is the same string as the image tag, which is what makes the rollback below
legible rather than a guess.

### The secrets are written once and then never again

`/opt/azmoth/shared/.env` lives outside the release directory, so shipping a new source tree cannot
overwrite it. It is created if absent and **left alone if present**. This is the part a deploy
script most often gets wrong:

- **`BETTER_AUTH_SECRET`** signs every session cookie. A new value on each deploy signs sessions the
  next container cannot verify, and every user is silently logged out on every deploy.
- **The two Neon URLs** are worse, in a quieter way. Overwriting them with a different project's
  strings points a running deployment at an empty database — which comes up **perfectly healthy**,
  migrates **cleanly**, and shows a practice none of their own records. Moving to a different Neon
  project is a deliberate edit on the box, not a side effect of deploying.

"Written once, then never touched" has a failure mode of its own, though: a variable added to the
repository *after* the first deploy never reaches a box that has already been deployed to, and the
symptom is a control that reads as wired up in git and is absent in production. So two keys are
**backfilled** — appended to an existing `.env` only when missing *entirely*, never rewritten
whatever their existing value, including empty:

- **`SIGNUP_ALLOWLIST`**, because it is not a secret and the operator may have edited the guest list
  on the box. A deploy that silently reset it would be a regression dressed as a fix.
- **`DATABASE_URL_POOLED`**, because it did not exist before Neon and its absence is *invisible*
  rather than loud — the web tier falls back to the direct endpoint, which works, just chattier.
  That is exactly the kind of thing that stays absent for the life of a pilot.

**Back that file up.** Copy `/opt/azmoth/shared/.env` into a password manager. It is now the only
copy of the credentials that can read the database, which means losing it also makes the encrypted
dumps in Blob Storage unrestorable — see § 6.

### Rolling back is a pull and a restart

```bash
./scripts/deploy.sh 20.79.12.34 --tag <older-sha>
```

Because the image tag *is* the commit, and because the box builds nothing, a rollback is a
`docker pull` of an older tag and a restart. Not a rebuild from an older commit, and not a
twenty-minute wait. `deploy.sh` keeps a week of previous images on the box for exactly this —
`docker image prune --filter until=168h`, deliberately not `system prune -a`, which would delete the
rollback targets.

**It does not undo a migration.** `alembic upgrade head` ran forward; nothing runs it back. If the
release you are rolling away from added one, check that the older image tolerates the newer schema
before you roll back to it. `deploy.sh` says this in its closing output, and
[`docs/deploy/RUNBOOK.md`](RUNBOOK.md) § 6 is the procedure.

`deploy.sh` also warns when `--tag` is not your HEAD, because the source shipped to the box always
comes from HEAD: the compose files and Caddyfile will be HEAD's while the application images are the
older tag's. That is correct for rolling back the application and wrong if the infra files also
changed — check out the older commit if so.

---

## 5b. TLS, and what `api.azmoth.com` actually serves

[`infra/docker/Caddyfile`](../../infra/docker/Caddyfile) handles TLS with no certificate management
on your part: Caddy requests from Let's Encrypt on first start, renews unattended, and stores both
the certificates and the ACME account key in the `azmoth-caddy-data` volume.

That volume is now **the most important state on the box, by a distance** — the database is not here
any more, so it is the only thing that is expensive to lose. Losing it means re-issuing every
certificate on the next start, and Let's Encrypt rate-limits duplicates to **five per week**. Two or
three deploys that each wipe it and the pilot has no HTTPS until the window rolls.
`docker compose down` keeps it; only `down -v` removes it.

Caddy deliberately has **no `depends_on`**. It must come up whatever the application is doing: if
`web` is crash-looping on a bad image, an ordered start would mean Caddy never runs, never answers
the HTTP-01 challenge, and the certificate expires while somebody debugs Next.js. Its `health_uri`
handles a backend that is not ready — that is a 502 for a few seconds, not a deployment with no TLS.

| Hostname | Serves |
|---|---|
| `app.azmoth.com` | `web:3000` — the review and audit UI, plus HSTS |
| `api.azmoth.com` | **`/api/v1/audit/*`, `/api/v1/health`, `/openapi.json`, `/docs` — and 404 for everything else** |

There is no third row, and that absence is the point: `azmoth.com` and `www.azmoth.com` are
Vercel's. See § 3. HSTS is set on the application host only and not in the shared hardening snippet,
because `max-age` is a promise a browser will not let you take back for its duration — right for a
host that is HTTPS-only for the life of the deployment, wrong as a blanket default. It carries no
`preload`, which is the same promise made irrevocably and to every browser at once.

### The `api.` allowlist is the one design decision here worth arguing about

`api.azmoth.com` terminates TLS for the engine, and it does **not** proxy the whole engine, because
the engine cannot safely be on the public internet as it stands. The codebase says so itself, in
[`apps/engine/app/api/tenancy.py`](../../apps/engine/app/api/tenancy.py):

> The header is asserted, not proven … the engine is not published to the browser in
> `infra/docker/docker-compose.yml`, and every call therefore arrives from one trusted proxy that
> sets both headers from a session it verified against the database. **A caller who can reach the
> engine directly can name any organisation they like** — which is true of `X-User-ID` today and is
> exactly why the engine must not be exposed.

`/api/v1/solve`, `/api/v1/proposals/*`, `/api/v1/padnext/*`, `/api/v1/settings/*`, `/api/v1/rules/*`
and `/api/v1/demo/*` take their identity and their tenant from `X-User-ID` and `X-Organization-ID`,
which the Next.js proxy sets from a verified session. Published directly, anyone could set those
headers to anything: anonymous writes into an append-only audit log, and any practice's drafts
readable by naming their organisation id.

`/api/v1/audit/*` is different, and it is the surface
[`docs/api/PARTNER_API.md`](../api/PARTNER_API.md) documents as commercial. Every endpoint under it
takes `RequestApiKey`: the token in `X-API-Key` is verified against the `api_keys` table on every
request and the tenant comes out of the stored row, so no header can name someone else's practice.
That is safe to publish, so that is what is published.

The allowlist answers **404 rather than 403** for the rest — a 403 confirms the path exists, which
tells someone probing this host exactly which endpoints to come back to when the auth model
changes.

**What would earn a wider allowlist** is the change `identity.py` names: a Better Auth JWT the
engine verifies itself, with the signature check landing in `require_organization`. Every endpoint
downstream already takes its tenant from there rather than from a query parameter, so it is a
contained change — it is just not this week's.

---

## 6. Backups

[`infra/scripts/backup-to-azure.sh`](../../infra/scripts/backup-to-azure.sh) dumps Neon, verifies
the archive, encrypts it, and pushes it off the VM to Blob Storage in the same region.

```bash
make azure-backup AZURE_HOST=20.79.12.34
```

### Why an off-host copy at all, when Neon has point-in-time restore

This is the question worth answering properly, because "the managed database has backups" is the
argument that usually wins. The Blob Storage account was costed at about **0.05 EUR/month** for a
pilot's worth of dumps and kept, for three reasons:

1. **Neon's Free-plan history window is six hours, capped at 1 GB.** That is a *rollback*, not a
   backup. Launch extends it to seven days for usage-based cents and is worth doing — but seven days
   is still not an archive for records a practice is legally obliged to be able to produce.

2. **It is the only copy that survives losing the Neon account.** Instant restore, snapshots and
   branches all live *inside the Neon project*. They survive a dropped table; none of them survives
   a deleted project, a lapsed card, a compromised Neon login, or Neon's own policy that Free-plan
   projects idle for 90 days "are subject to deletion". `docs/OPERATIONS.md` § 2 has always required
   dumps to be kept off the same host as the database, and **a managed provider is a host**.

3. **It also holds the things that are not in the database** — an encrypted copy of
   `/opt/azmoth/shared/.env`, which now contains the Neon connection strings, without which the
   dumps are just files. Nothing else on this box is backed up at all.

**Blob Storage, not a second disk.** A disk attached to this VM dies with this VM, with the resource
group, and with the subscription when the credit runs out. A blob survives all three and costs
0.0086 EUR per gigabyte-month in the Cool tier.

### What changed in the dump itself

There is no local Postgres to `docker compose exec` into, so the dump is taken **over the network**:
a throwaway `postgres:17-alpine` container runs `pg_dump` against Neon's **direct** endpoint.

- **A container, not a host package.** `pg_dump` must be at least as new as the server, and Neon
  runs Postgres 17. Installing `postgresql-client-17` on Ubuntu 22.04 (which ships 14) means adding
  the PGDG apt repository to a box whose whole point is that it runs three pulled images. A pinned
  image is one line, is the same version on every run, and leaves nothing behind.
- **The direct endpoint**, and the script refuses a `-pooler` URL outright. A dump holds one
  transaction open across hundreds of statements; a transaction-mode pooler does not promise to keep
  it on one server connection, and the result is a dump that restores into a state that never
  existed.

`infra/scripts/backup-db.sh` and `restore-db.sh` are **not** deleted. They remain the correct tools
for the local docker-compose stack, where there is a postgres container to exec into.

The archive is then read back with `pg_restore --list` before it is uploaded. A backup script that
only runs `pg_dump` produces a file nobody has opened, and the first time anyone opens it is the day
they need it.

### No credential on the VM, and the VM cannot read its own backups

Blob authentication is the VM's **system-assigned managed identity**, granted
`Storage Blob Data Contributor` on that one container. `az login --identity` gets a short-lived
token from the instance metadata endpoint. A storage account key would be a long-lived credential
with full control of the account, sitting on disk next to the very dumps it protects, and rotating
it would mean finding every copy. Contributor and not Owner, and scoped to the container: the job
needs to write blobs, not to change the container's public-access setting, which is what an
account-level role would let a compromised VM do.

The dump is encrypted with **`age`, to a public key**, and the matching private key never touches
the VM. A compromised VM can therefore write backups and cannot read back a single one — and neither
can anyone who gains read access to the container. Azure's at-rest encryption protects against a
stolen disk in a datacentre; this protects against the container being made readable by a
misconfiguration, which is the failure that actually happens.

Set it up once:

```bash
# on your laptop
age-keygen -o azmoth-backup.key          # → the private key goes in a password manager, nowhere else

# on the VM
echo 'AGE_RECIPIENT=age1ql3z...'        | sudo tee -a /opt/azmoth/shared/.env
echo 'STORAGE_ACCOUNT=azmothbackupxxxx' | sudo tee -a /opt/azmoth/shared/.env
sudo crontab -e
```

```cron
15 3 * * * /opt/azmoth/repo/infra/scripts/backup-to-azure.sh >> /var/log/azmoth-backup.log 2>&1
```

(`age` and the Azure CLI are installed by `deploy.sh`'s bootstrap step, because the backup job is
the thing most likely to be set up "later" and a missing binary is one more reason for later never
to arrive.)

Blobs are laid out by date and uploaded with `--overwrite false` under a timestamped name, so the
job can never destroy an earlier backup. That also avoids the Cool tier's early-deletion penalty:
overwriting a blob counts as a delete, so a daily job that reused one name would be billed 30 days
of storage for each of them. Mind the same 30-day minimum if you write a lifecycle policy —
expiring a blob at seven days is billed as though it lived for thirty.

Losing the private key loses every backup. That is the trade, and it is worth making — but put the
key in the password manager *now*, not after the first backup runs.

Restoring, including from a blob when the VM's disk is gone, is
[`docs/OPERATIONS.md` § 7.7](../OPERATIONS.md#77-restoring). Restore into a **scratch Neon branch**,
not over the live database.

---

## 7. Pre-flight checklist

```bash
./scripts/preflight.sh 20.79.12.34 --domain azmoth.com
```

It checks from the **outside**, which is the point: `docker compose ps` proves the containers are up
and proves nothing about what the internet can reach. Exit status is 0 only if everything passes.
Checks marked `[SEC]` would be a security incident rather than an outage; a failure in any of them
should stop the pilot.

What it verifies:

**Ports [SEC]**
- 80 and 443 open
- **8000 closed** — the engine, which authenticates nobody
- 5432, 3000, 3001, 8080 closed. Three of those cannot be open any more — the database is Neon's,
  the marketing site is Vercel's, and adminer is profiled out — and they are still checked, because
  the case this list exists for is somebody adding a service back.

**TLS**
- A real Let's Encrypt certificate on **two** names, with days remaining — not the self-signed one
  Caddy serves while ACME is failing, which from a browser looks like a scary warning rather than
  "issuance is in a backoff"
- `http://` redirects to `https://`

**`azmoth.com` is still Vercel's [SEC]**
- Neither the apex nor `www` resolves to this VM
- `https://www.azmoth.com/` answers 200 — a statement about Vercel, not about the VM, which is why
  it is in its own section

**The `api.` allowlist [SEC]**
- `POST /api/v1/audit/single` without a key → `401` (reachable, and refusing)
- `/api/v1/health` and `/openapi.json` → `200`
- `/api/v1/solve`, `/api/v1/proposals`, `/api/v1/padnext/audit`, `/api/v1/settings/api-keys`,
  `/api/v1/rules`, `/api/v1/demo` → **`404`**

**The application**
- `/api/health` → 200; `/` answers a sign-in page rather than the app
- Any cookie set carries `Secure`

**On the box**
- **Three** long-running services running and healthy: caddy, web, engine. `engine-migrate` and
  `web-auth-migrate` are one-shots that exit 0 and have no health status; they are checked by their
  effect on the schema instead.
- No `postgres` container is running — one would mean the deploy resolved the base file without the
  Azure override, which also means port 8000 is probably published
- `SIGNUP_ALLOWLIST` read out of the **running** web container, not out of the file on disk [SEC]
- The 4 GiB swapfile exists, and there is memory available at rest — meaningful now in a way it was
  not on a 4 GiB build box
- Root filesystem under 80%

**The Neon database [SEC for the endpoint split]**

This replaced the old local-Postgres restore test, which cannot run here — it built a scratch
database with `docker compose exec postgres psql`. It could not simply be ported, either: creating a
throwaway database inside the Neon project on every preflight would burn the Free plan's compute
allowance to prove something Neon's own instant restore already covers. What is checked instead is
that the three things the design depends on are true in the **running containers**:

1. The engine reaches Neon at all — `select 1` round-trips — and is on Postgres rather than the
   SQLite default, so approvals are durable
2. The engine is on the **direct** endpoint and `web` is on the **pooled** one, not the reverse and
   not both on one
3. **`alembic current` equals `alembic heads`** — the schema is at the newest revision the deployed
   image carries, not merely at *some* revision

(3) is the one the old check could not make. `alembic current` printing a revision proved a
migration had run at some point; it did not prove the container was not running an older image
against a newer database, or a newer image against a database the migration step failed to advance.
A missing column at runtime looks like an application bug for about an hour.

**Backups**
- A dump has actually been taken on this box, and the newest is no more than two days old. Nothing
  here *takes* one — that would dump clinical data on every preflight — so it asks the cheaper
  question. A real restore drill needs the `age` private key, which is deliberately not on the VM
  or in CI, so it stays a manual step.

### Then, by hand

`preflight.sh` prints this list at the end of every run, so it is not something to remember. The
authoritative copy is in the script; the ones in **bold** below are blockers on the pilot rather
than tasks.

- [ ] **Sign up, sign in, sign out** in a browser — and confirm an address that is **not** on
      `SIGNUP_ALLOWLIST` is refused. That variable is the whole of the admission control on a public
      box: there is no invitation flow and no email verification behind it, and an empty value
      admits nobody.
- [ ] Upload a PADnext delivery and confirm the report renders, and that `schema_warnings` appears
      on a non-conforming export (`PADNEXT_SCHEMA_POLICY=warn` is the pilot setting)
- [ ] Confirm a delivery with no `echtdaten` attribute is refused with `ECHTDATEN_UNDECLARED`, and
      that `scripts/anonymize_padnext.py` produces one that is accepted. This is the pilot's
      data-protection boundary; it is worth seeing it work once rather than assuming it.
- [ ] Mint an API key and call `/api/v1/audit/single` from your laptop with it
- [ ] **Copy `/opt/azmoth/shared/.env` off this VM.** It holds both Neon connection strings —
      without them the encrypted dumps in Blob Storage are files nobody can restore anywhere.
- [ ] Store the `age` private key. Losing it loses every backup.
- [ ] Install the backup cron — nothing does it for you
- [ ] **Do the restore drill, once.** Download a blob, decrypt it locally, `pg_restore --list` it,
      and restore into a scratch Neon branch rather than over the live database.
      `docs/OPERATIONS.md` § 7.7.
- [ ] **In the Neon console: confirm the project region is `aws-eu-central-1`** and not a US region.
      It cannot be changed after creation.
- [ ] In the Neon console: set a spend limit, or watch the Free plan's compute allowance.
      Exhausting it drops live connections and refuses new ones until the next billing period — the
      pilot goes down, not degrades. What the Launch plan costs and when it is worth upgrading is
      § 4; what the whole deployment costs is § 1.
- [ ] **Name all four sub-processors** in `docs/AVV_TECHNICAL_ANNEX_DRAFT.md` § 5.2, which currently
      says there are none. See the table in § 1.
- [ ] **Request an executable AVV/DPA from Databricks** for the Neon project. The self-serve
      `neon.com/dpa` is a click-accept schedule, not a signed contract, and a practice's lawyer will
      ask for the latter.

---

## 8. Day two

Everything operational — logs, restarts, `psql`, restores, cost, and a table of failure modes — is
[`docs/OPERATIONS.md` § 7](../OPERATIONS.md#7-the-deployed-vm).

The one command worth knowing before you need it:

```bash
az vm deallocate --resource-group azmoth-pilot --name azmoth-vm
```

That stops compute billing if the pilot pauses. Disk and IP keep billing — 2.06 + 3.14 =
**~5.20 EUR/month** — and the static IP is what makes the DNS records and certificates survive the
gap. **`az vm stop` is not the same thing**: it shuts the guest down and leaves the VM allocated,
billing exactly as if it were running.

Two things a deallocation does not pause, and one it might not survive:

- **Neon** keeps running. On Free that costs nothing, but a project idle for 90 days or more is
  subject to deletion — a long pause needs a dump taken *before* it, not after.
- **Vercel** keeps serving the marketing site, which is usually what you want: the public site
  stays up while the application is paused.
- **B-series v1 has been growth-restricted since July 2026**, and a start-after-deallocate is
  exactly an operation that needs a fresh allocation. If `az vm start` refuses, that is the
  restriction rather than a transient capacity problem, and the fallback ladder in § 1 is the
  answer. The static IP and the Blob account survive a VM rebuilt at a different size, so the DNS
  records stay valid — but the `azmoth-caddy-data` volume does not, so expect Caddy to re-issue and
  mind the five-per-week duplicate limit (§ 5b).
