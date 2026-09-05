# Runbook — deploying Azmoth from nothing

Chronological. Every step is a command to paste and an output to check against. Follow it top to
bottom the first time; afterwards you only ever need [§ 5](#5-deploy) and [§ 6](#6-rollback).

[`docs/deploy/AWS.md`](AWS.md) is the companion document and answers *why* — why this instance size,
why Neon rather than RDS, why the engine does not use the connection pooler.
[`docs/deploy/AZURE.md`](AZURE.md) is the same document for the Azure deployment. This file answers
*what to type*. When they disagree, the companion document is the one that was reasoned about; tell
someone.

Budget about **75 minutes** end to end, of which roughly 15 is waiting for a GitHub Actions build
and 10 is waiting for DNS.

```
  § 1  local prep          aws configure, gh auth, one SSH key, one age key
  § 2  provision           the VM, a fixed IP, the firewall, swap, backup storage
  § 3  Neon                the project, the database, BOTH connection strings
  § 4  DNS                 two A records — and two that must NOT move
  § 5  deploy              pull, migrate, start, verify
  § 6  rollback            when § 5 was a mistake
```

## Which cloud

**This runbook covers both, and only § 1 and § 2 differ.** Azmoth runs on one Ubuntu box with Docker
Compose; `scripts/deploy.sh` needs a host it can `ssh` to as a sudoer and does not care who is
billing for it. So from § 3 onward there is one path, not two.

| | Default | Alternative |
|---|---|---|
| Provisioning | `infra/aws/provision.sh` — EC2 `t3.small`, `eu-central-1` | `infra/azure/provision.sh` — `Standard_B1ms`, `germanywestcentral` |
| Backups | `infra/scripts/backup-to-s3.sh` — S3 + instance profile | `infra/scripts/backup-to-azure.sh` — Blob + managed identity |

**AWS is the default because an Azure for Students subscription cannot allocate EU compute**, and
[the AVV](../AVV_TECHNICAL_ANNEX_DRAFT.md) § 5.1 requires the EU. [AWS.md § 0](AWS.md#0-why-this-moved-off-azure)
is the full reasoning. Azure remains correct and supported if you have a subscription that can host
in Frankfurt.

Steps that differ are marked **[AWS]** and **[Azure]**. Do one, skip the other.

> **On the name `AZURE_HOST`.** The shell variable and the `make azure-*` targets below kept their
> names through the move. They mean "the deployment VM", whichever cloud it is in — renaming them
> would touch every target in the [`Makefile`](../../Makefile) and every shell profile that has one
> exported, for no behaviour. Read `AZURE_HOST` as `VM_HOST`.

> **What this runbook does NOT set up.** The marketing site at `azmoth.com` is already live on
> Vercel and is not touched by any of this. If a step below seems to ask you to move its DNS, you
> have misread it — see [§ 4](#4-dns).

---

## What you are building

```
                    azmoth.com          app.azmoth.com   api.azmoth.com
                    www.azmoth.com              │              │
                          │                     └──────┬───────┘
                          ▼                            ▼
                    ┌──────────┐              ┌─────────────────┐
                    │  Vercel  │              │  EC2 t3.small   │  eu-central-1
                    │  static  │              │  Ubuntu 22.04   │  2 GiB + 4 GiB swap
                    └──────────┘              │                 │
                                              │  caddy  → TLS   │
                                              │  web:3000       │
                                              │  engine:8000    │  never public
                                              └────────┬────────┘
                                                       │ TLS
                                   ┌───────────────────┴────────────────┐
                                   ▼                                    ▼
                          ┌─────────────────┐                 ┌──────────────────┐
                          │ Neon Postgres   │                 │ S3 bucket        │
                          │ aws-eu-central-1│                 │ encrypted dumps  │
                          └─────────────────┘                 └──────────────────┘

     On Azure the middle box is a Standard_B1ms in germanywestcentral and the right-hand
     box is Blob Storage. Everything else on this diagram is identical.
```

Three things run on the VM. The database is Neon's, the public site is Vercel's, and the images are
built by GitHub Actions — nothing is compiled on the box, which is why 2 GiB is enough.

---

## 1. Local prep

### 1.1 The tools

```bash
aws --version       # [AWS]   https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
                    #         Ubuntu: sudo snap install aws-cli --classic
az version          # [Azure] https://learn.microsoft.com/cli/azure/install-azure-cli
gh --version        # GitHub CLI — https://cli.github.com
docker --version    # for the Caddyfile and compose checks below
jq --version        # deploy.sh uses it to check the image manifests
dig -v              # bind9-dnsutils on Debian/Ubuntu
age --version       # https://github.com/FiloSottile/age  — apt install age
```

You need **one** of `aws` and `az` — whichever cloud you are provisioning in. Everything else on
that list is needed either way.

`jq` is not optional in spirit: without it `deploy.sh` skips the pre-flight manifest check and you
find out about a missing image after Docker has been installed on the VM.

### 1.2 Sign in

**[AWS]**

```bash
aws configure          # or, if your account uses IAM Identity Center: aws sso login
aws sts get-caller-identity --query '{account:Account, arn:Arn}' --output table
```

```
|                       GetCallerIdentity                        |
+------------------+---------------------------------------------+
|  account         |  123456789012                               |
|  arn             |  arn:aws:iam::123456789012:user/azmoth-ops  |
+------------------+---------------------------------------------+
```

**Check the account before you create anything.** `provision.sh` uses whatever profile is current,
and creating a pilot in a colleague's account is annoying to unpick. If you keep several, pin one:

```bash
export AWS_PROFILE=azmoth-pilot
```

Do **not** set `AWS_DEFAULT_REGION` to anything outside the EU in that profile. `provision.sh`
refuses a non-`eu-` region rather than quietly building the pilot in Virginia, but the refusal is
easier to read if it never fires.

**[Azure]**

```bash
az login
az account show --query '{name:name, id:id}' --output table
```

```
Name                 Id
-------------------  ------------------------------------
Azmoth Pilot         4f86d9ff-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

If you have more than one subscription, pin the right one now — `provision.sh` uses whatever is
current and creating a pilot in the wrong subscription is annoying to unpick:

```bash
az account set --subscription "Azmoth Pilot"
```

**Both**

```bash
gh auth status
```

```
✓ Logged in to github.com account oussamakhadraoui (keyring)
  - Token scopes: 'gist', 'read:org', 'repo', 'workflow'
```

### 1.3 Set a budget alert before you create anything

**[AWS]** This matters more here than it did on Azure. A fixed Azure credit stopped when it ran out;
**an AWS account has no spending cap and will keep billing a card.** A budget alert is the only thing
that tells you.

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
aws budgets create-budget --account-id "$ACCOUNT" --budget '{
  "BudgetName": "azmoth-pilot",
  "BudgetLimit": { "Amount": "40", "Unit": "USD" },
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST"
}'
```

40 USD against an expected ~24 USD/month ([AWS.md § 1](AWS.md#what-the-whole-thing-costs)) leaves
room for a bad week without alerting on a normal one. Add a notification so it reaches you rather
than sitting in the console — Billing → Budgets → *azmoth-pilot* → **Add alert threshold**, 80% of
budgeted amount, to your address.

**[Azure]** A fixed credit that runs out takes the pilot offline with no warning. Do this first, not
later.

```bash
az consumption budget create --budget-name azmoth-pilot --amount 100 \
  --category Cost --time-grain Monthly \
  --start-date "$(date -u +%Y-%m-01)" --end-date "$(date -u -d '+1 year' +%Y-%m-01)"
```

If your subscription does not support `az consumption` (some student and sponsorship offers do not),
set it in the portal under **Cost Management → Budgets** instead. Do not skip it.

### 1.4 The two keys you have to generate

**An SSH keypair**, if you do not already have one. `provision.sh` refuses to run without a public
key and refuses to open port 22 to the internet.

```bash
[ -f ~/.ssh/id_ed25519 ] || ssh-keygen -t ed25519 -C 'azmoth-ops'
ssh-add -l          # confirm the agent has it
```

**An `age` keypair for the backups.** Generate it **on your laptop** and put the private half in a
password manager immediately.

```bash
age-keygen -o azmoth-backup.key
```

```
Public key: age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p
```

Copy the public key — you will paste it into the VM's env file in [§ 5.4](#54-finish-the-backup-setup).

> **The private key must never reach the VM.** That is the whole property: the box can encrypt a
> backup and cannot read one back, so a compromised host cannot exfiltrate the dumps sitting next to
> it. The cost of that property is that **losing the private key loses every backup.** Put it in the
> password manager now, not after the first backup runs.

### 1.5 A GitHub token for pulling images

The VM pulls private images from GHCR, so it needs a token. Create a **classic** personal access
token whose only scope is `read:packages`:

<https://github.com/settings/tokens/new?scopes=read:packages&description=azmoth-vm-pull>

`read:packages` cannot push an image, cannot read the repository source, and cannot act on the
account. It is the least a `docker pull` can be given. `deploy.sh` prompts for it if you do not put
it in the environment; either way it ends up only in `/opt/azmoth/shared/.env` at mode 600.

### 1.6 Push the commit you intend to deploy

Nothing is built on the VM, so the images must exist before you deploy. Push, then wait for the
workflow.

```bash
git push origin main
gh run list --workflow=release-images.yml --limit 3
gh run watch
```

```
✓ main release-images · 18234567890
  Triggered via push about 14 minutes ago

JOBS
✓ azmoth-engine in 6m12s (ID 51234567890)
✓ azmoth-web in 9m48s (ID 51234567891)
✓ azmoth-web-builder in 4m03s (ID 51234567892)
✓ images-ready in 3s (ID 51234567893)
```

`images-ready` going green is the signal. Three images now exist at `ghcr.io/<owner>/azmoth-*` tagged
with the commit sha — that sha is what `deploy.sh` deploys and what a rollback names.

---

## 2. Provision

Both scripts are idempotent — every step checks before it creates, so a run that fails halfway (a
capacity refusal, a dropped connection) is fixed by running it again rather than by working out
which half happened. Both refuse to start without an SSH public key, and both **refuse to open port
22 to the internet**: if the script cannot detect your public IP it stops and asks for it rather
than defaulting to `0.0.0.0/0`.

### 2a. [AWS]

```bash
./infra/aws/provision.sh
```

It prints a summary and asks before creating anything:

```
==> Default VPC in eu-central-1
    vpc     vpc-0a1b2c3d4e5f
    subnet  subnet-0a1b2c3d4e5f
==> Resolving the current Ubuntu 22.04 LTS AMI
    ami-0abcdef1234567890
    root device /dev/sda1

  region           eu-central-1            (EU — required by the AVV, see the header)
  vpc / subnet     vpc-0a1b2c3d4e5f / subnet-0a1b2c3d4e5f   (the account default, not created here)
  instance         azmoth-vm (t3.small, CPU credits: standard)
  image            ami-0abcdef1234567890  (Ubuntu 22.04 LTS, resolved from SSM)
  root volume      32 GiB gp3, encrypted
  ssh key          /home/you/.ssh/id_ed25519.pub  -> key pair 'azmoth-vm-key'
  ssh allowed from 203.0.113.4/32           (and nowhere else)
  s3 bucket        azmoth-backups-you     (private, versioned, TLS-only)
  iam role         azmoth-vm-backup-role  (s3:PutObject/GetObject on that bucket only)

  NOT created by this script, and both are required before deploying:
    - the Neon project (aws-eu-central-1) and its two connection strings
    - the Vercel project for azmoth.com  — already live; leave its DNS alone

Create these resources? [y/N]
```

Then, over three or four minutes:

```
==> 1/7 key pair: azmoth-vm-key
    imported from /home/you/.ssh/id_ed25519.pub
==> 2/7 security group: azmoth-vm-sg
    created sg-0a1b2c3d4e5f
    80 opened to the world (HTTP - ACME HTTP-01 challenge and the redirect to HTTPS)
    443 opened to the world (HTTPS - Caddy terminates TLS here)
    ssh: allowing 203.0.113.4/32 and revoking everything else on 22
      authorised 203.0.113.4/32
==> 3/7 S3 bucket for backups: azmoth-backups-you
    created in eu-central-1
    public access: blocked (all four settings)
    versioning: enabled
    encryption at rest: SSE-S3 (AES256)
    bucket policy: plain HTTP denied
==> 4/7 IAM role and instance profile: azmoth-vm-backup-role
    policy: s3:PutObject, s3:GetObject on azmoth-backups-you/* — and nothing else
==> 5/7 instance: azmoth-vm
    created i-0a1b2c3d4e5f
    running
==> 6/7 Elastic IP
    allocated eipalloc-0a1b2c3d4e5f
    associated with i-0a1b2c3d4e5f
    address: 3.120.45.67
==> 7/7 swap and the 'azmoth' user
    swapfile created and enabled
    vm.swappiness=10
```

It ends by printing the public IP and the two DNS records. **Write the IP down.**

If step 7 says *"not reachable over SSH yet"*, that is fine and expected on a brand-new instance —
cloud-init is still booting. It configured the swapfile and the `azmoth` user itself; run the script
again in a minute to confirm.

**Exactly six resources, and no more.** No RDS, no Aurora, no load balancer, no NAT gateway, no
custom VPC. If you find one of those in the account, this script did not make it.

#### If the instance type will not launch

```
!! run-instances failed. ... InsufficientInstanceCapacity
```

```bash
INSTANCE_TYPE=t3.medium ./infra/aws/provision.sh
```

| `INSTANCE_TYPE` | | ~EUR/mo |
|---|---|---|
| `t3.small` | 2 vCPU / 2 GiB | 16.00 — the default |
| `t3.medium` | 2 vCPU / 4 GiB | 32.00 |

Do not reach for `t4g.small` even though Graviton is cheaper:
[`apps/engine/Dockerfile`](../../apps/engine/Dockerfile) installs an `x86_64` Soufflé package, and
the engine is nothing without Soufflé.

Note that on a rerun the script **leaves an existing instance alone** — that is the idempotence
working, not the flag being ignored. Resizing an existing box is a stop/modify/start; see
[AWS.md § 1](AWS.md#the-ladder).

#### Save the address into your shell

Everything below assumes these. (`AZURE_HOST` is the historical name for "the deployment VM" — see
the note in [Which cloud](#which-cloud) — and the `make` targets read it.)

```bash
export AZURE_HOST=3.120.45.67           # whatever provision.sh printed
export AWS_REGION=eu-central-1
export STORAGE_BUCKET=azmoth-backups-you
```

### 2b. [Azure]

```bash
./infra/azure/provision.sh
```

It prints a summary and asks before creating anything:

```
==> Checking Standard_B1ms is available in germanywestcentral
    available, no restrictions reported

  resource group   azmoth-pilot
  location         germanywestcentral          (EU — required by the AVV, see the header)
  vm               azmoth-vm (Standard_B1ms)
  image            Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest
  os disk          32 GiB StandardSSD_LRS
  ssh key          /home/you/.ssh/id_ed25519.pub
  ssh allowed from 203.0.113.4/32           (and nowhere else)
  storage account  azmothbackupyou/db-backups

  NOT created by this script, and both are required before deploying:
    - the Neon project (aws-eu-central-1) and its two connection strings
    - the Vercel project for azmoth.com  — already live; leave its DNS alone

Create these resources? [y/N]
```

Then, over three or four minutes:

```
==> 1/7 resource group: azmoth-pilot
    created
==> 2/7 static public IP: azmoth-vm-ip
    created
    address: 20.79.12.34
==> 3/7 network security group: azmoth-vm-nsg
    ssh created (from 203.0.113.4/32)
    http created (from *)
    https created (from *)
==> 4/7 virtual network: azmoth-vm-vnet
==> 5/7 virtual machine: azmoth-vm
    created
==> 6/7 swap
    swap configured
==> 7/7 storage account for backups: azmothbackupyou
    container db-backups created
==>     managed identity for backups
    granted Storage Blob Data Contributor on db-backups
```

It ends by printing the public IP and the two DNS records. **Write the IP down.**

#### If the VM size will not allocate

```
!! Standard_B1ms is offered but RESTRICTED for this subscription:
   NotAvailableForSubscription
```

B-series **v1** has been growth-restricted since 31 July 2026 and retires 15 November 2028. Take the
next rung and accept the shorter runway:

```bash
VM_SIZE=Standard_B2als_v2 ./infra/azure/provision.sh    # 2 vCPU / 4 GiB, AMD, not retiring
```

| `VM_SIZE` | | EUR/mo | Months on 100 EUR |
|---|---|---|---|
| `Standard_B1ms` | 1 vCPU / 2 GiB | 15.04 | ~4.9 — the default |
| `Standard_B2als_v2` | 2 vCPU / 4 GiB | 27.08 | ~3.1 — AMD, not retiring |
| `Standard_B2s` | 2 vCPU / 4 GiB | 30.08 | ~2.9 — v1, retiring |

Do not reach for the Arm sizes even though `Standard_B2pls_v2` is the cheapest 4 GiB SKU there is at
24.09 EUR: [`apps/engine/Dockerfile`](../../apps/engine/Dockerfile) installs an `x86_64` Soufflé
package, and the engine is nothing without Soufflé.

#### Save the resource-group name into your shell

Everything below assumes these:

```bash
export AZURE_HOST=20.79.12.34          # whatever provision.sh printed
export RG=azmoth-pilot
```

---

**From here on there is one path.** § 3 to § 6 are identical on both clouds — the database, the DNS,
the deploy and the rollback do not know or care which one you chose. The only exception is
[§ 5.4](#54-finish-the-backup-setup), where the backup job differs.

---

## 3. Neon

### 3.1 Create the project

1. <https://console.neon.tech> → **New project**
2. Name: `azmoth-pilot`
3. **Region: `AWS Europe (Frankfurt) — aws-eu-central-1`**
4. Postgres version: 17 (the default)
5. Database name: `azmoth`

> **The region cannot be changed afterwards, and Azure is not on the list.** Neon deprecated every
> Azure region on 7 April 2026 and no longer accepts new projects in any of them on any plan, so
> co-locating the database with the VM at one provider is no longer possible. `aws-eu-central-1` is
> still Frankfurt and still the EU, which is what
> [`docs/AVV_TECHNICAL_ANNEX_DRAFT.md`](../AVV_TECHNICAL_ANNEX_DRAFT.md) § 5.1 requires — but it puts
> AWS into the sub-processor chain alongside Neon and its parent Databricks. See § 5.2 of that
> annex, which this change is why you have to update.

Verify the region before you go further, because everything downstream is cheap to redo and this is
not:

```bash
# In the console: Settings → General. The region is shown next to the project name.
# Or, if you have a Neon API key:
curl -sS -H "Authorization: Bearer $NEON_API_KEY" \
  https://console.neon.tech/api/v2/projects | jq -r '.projects[] | "\(.name)\t\(.region_id)"'
```

```
azmoth-pilot	aws-eu-central-1
```

### 3.2 Copy BOTH connection strings

This is the step people get wrong, so it is worth going slowly.

In the console: **Dashboard → Connect** (or the **Connect** button). You will see a connection string
and a **Connection pooling** toggle. You need the string **both ways round**.

**Toggle OFF → the DIRECT string.** This is `DATABASE_URL`.

```
postgresql://azmoth:npg_XXXXXXXX@ep-cool-darkness-a1b2c3d4.eu-central-1.aws.neon.tech/azmoth?sslmode=require
```

**Toggle ON → the POOLED string.** This is `DATABASE_URL_POOLED`. The only difference is `-pooler`
in the hostname:

```
postgresql://azmoth:npg_XXXXXXXX@ep-cool-darkness-a1b2c3d4-pooler.eu-central-1.aws.neon.tech/azmoth?sslmode=require
                                                          ^^^^^^^
```

### 3.3 Add the `+asyncpg` driver suffix

The engine's URL carries its driver, because SQLAlchemy takes the driver from the scheme. Neon gives
you a plain `postgresql://`; the deployment wants `postgresql+asyncpg://`.

`apps/web/lib/auth-db.ts` strips the suffix for node-postgres and the backup job
(`backup-to-s3.sh`, or `backup-to-azure.sh` on Azure) strips it for `pg_dump`, so **one value with
the suffix serves all three consumers** — you do not need a second copy without it.

```bash
# Paste the two strings from the console. -s so they are not echoed and do not land in the
# terminal's scrollback; they contain the role's password.
read -rsp 'direct string:  ' DIRECT; echo
read -rsp 'pooled string:  ' POOLED; echo

# sed rather than shell pattern substitution, because the pattern contains slashes and the
# bash/zsh escaping for that is its own small trap.
export DATABASE_URL="$(printf '%s' "$DIRECT" | sed 's#^postgresql://#postgresql+asyncpg://#')"
export DATABASE_URL_POOLED="$(printf '%s' "$POOLED" | sed 's#^postgresql://#postgresql+asyncpg://#')"

# Sanity check, with the credentials masked:
printf '%s\n' "$DATABASE_URL" "$DATABASE_URL_POOLED" | sed -E 's#//[^@]*@#//USER:PW@#'
```

```
postgresql+asyncpg://USER:PW@ep-cool-darkness-a1b2c3d4.eu-central-1.aws.neon.tech/azmoth?sslmode=require
postgresql+asyncpg://USER:PW@ep-cool-darkness-a1b2c3d4-pooler.eu-central-1.aws.neon.tech/azmoth?sslmode=require
```

The first must **not** contain `-pooler`. The second must. `deploy.sh` checks both and refuses to
continue if they are the wrong way round, but check them yourself — it is one glance.

### 3.4 Which one goes where, and why

You do not paste these anywhere by hand. `deploy.sh` reads them from the environment on the first
deploy and writes them into `/opt/azmoth/shared/.env` (mode 600), where they stay. But it is worth
knowing what it wires them to, because the split looks backwards until you know why:

| | endpoint | who uses it |
|---|---|---|
| `DATABASE_URL` | **direct** | `alembic upgrade head`, Better Auth's table creation, **the engine at runtime**, `pg_dump` |
| `DATABASE_URL_POOLED` | **pooled** | Better Auth at runtime, in the `web` container — and nothing else |

Migrations and `pg_dump` on the direct endpoint is Neon's own guidance: a transaction-mode pooler
does not support the session-level advisory locks a migration tool uses, nor SQL-level
`PREPARE`/`DEALLOCATE`, nor `CREATE INDEX CONCURRENTLY`, and a dump needs one snapshot held across
hundreds of statements.

**The engine on the direct endpoint is the counter-intuitive one.** SQLAlchemy's asyncpg dialect
calls `prepare()` for every statement and asyncpg names those `__asyncpg_stmt_N__` from a
per-connection counter — through a transaction-mode pooler, a recipe for intermittent
`DuplicatePreparedStatementError`. The widely-repeated fix `?prepared_statement_cache_size=0` does
not work: it clears SQLAlchemy's reuse cache but both paths still mint a named statement. The
configuration that does work needs `prepared_statement_name_func` and `NullPool`, which are Python
arguments in `apps/engine/app/db/session.py` and cannot be expressed in a URL. And the engine does
not need a pooler: it is one long-lived container holding at most fifteen connections.

Better Auth is the opposite case — node-postgres issues plain unnamed queries, and every route
handler is a short burst with idle gaps, which is exactly what the pooler is for.

### 3.5 Two Neon settings worth changing now

**Set a spend limit** (Settings → Billing), even on the Free plan. On Free, exhausting the monthly
compute allowance **drops existing connections and refuses new ones** until the next billing period
— the pilot goes down rather than degrades.

**Know that the compute suspends after five minutes of inactivity** and that this cannot be disabled
on the Free plan. The first request after a quiet period pays a cold start. That is why
`MIGRATION_WAIT_SECONDS` defaults to 60, and why a deploy after a quiet weekend occasionally needs a
second run.

Upgrading to **Launch** (usage-based, no monthly minimum — roughly 3–8 EUR/month at pilot volume)
buys a 7-day point-in-time-restore window instead of 6 hours, scheduled backups, and the ability to
turn scale-to-zero off. The budget accommodates it; see [`AZURE.md`](AZURE.md) § 4.

---

## 4. DNS

**Two records, at the IP `provision.sh` printed.** That is the whole list.

| Type | Name | Value | TTL |
|---|---|---|---|
| A | `app.azmoth.com` | `20.79.12.34` | 300 |
| A | `api.azmoth.com` | `20.79.12.34` | 300 |

> ### Do not touch `azmoth.com` or `www.azmoth.com`
>
> They are served by **Vercel** and they are live. This VM has no marketing container and
> [`infra/docker/Caddyfile`](../../infra/docker/Caddyfile) has no site block for those names.
>
> Pointing them here does two bad things at once: the public site starts answering from a box that
> does not have it, and Caddy requests a Let's Encrypt certificate for a name Vercel already holds
> one for — burning one of five duplicate certificates per week.
>
> `deploy.sh` **refuses to run** if either name resolves to the VM. That refusal is the only fatal
> DNS condition in the script, and it is there because this is a mistake somebody makes by following
> an older version of this document.

### Verify propagation

Wait for it. Caddy gets its certificates over HTTP-01, which means Let's Encrypt fetches a token from
these names over port 80 — a name that does not resolve yet is a failed issuance and a retry backoff,
not a warning.

```bash
dig +short app.azmoth.com
dig +short api.azmoth.com
```

```
20.79.12.34
20.79.12.34
```

Check the ones that must **not** have moved:

```bash
dig +short azmoth.com
dig +short www.azmoth.com
```

```
76.76.21.21
cname.vercel-dns.com.
```

Anything other than Vercel there — and in particular your VM's IP — stop and fix the record before
going on.

Your resolver may be caching. Ask an authoritative one, and a public one, to be sure:

```bash
dig +short @1.1.1.1 app.azmoth.com
dig +short @8.8.8.8 app.azmoth.com
dig +trace app.azmoth.com | tail -3
```

If a name still does not resolve after ten minutes, check the TTL of whatever record was there
before — that is usually the answer.

---

## 5. Deploy

### 5.1 The first deploy

Both Neon strings are required, and only this once. They are already exported from
[§ 3.3](#33-add-the-asyncpg-driver-suffix):

```bash
./scripts/deploy.sh "$AZURE_HOST" \
  --domain azmoth.com \
  --acme-email ops@azmoth.com \
  --signup-allowlist "you@azmoth.com,pilot@praxis-nord.de"
```

`--signup-allowlist` is not optional in spirit. It is the only thing between `/signup` and the open
internet — there is no invitation flow and no email verification behind it. Omit it and the script
defaults to `admin@<domain>` and shouts about it.

Expect 6–10 minutes. The shape of it:

```
==> Checking the local tree
    branch  main
    commit  737a889
    registry ghcr.io/azmoth-org
    tag      737a8891f0c4...
    deployment files present at HEAD

==> Checking the VM is reachable
    ok

==> Checking DNS
    app.azmoth.com           20.79.12.34
    api.azmoth.com           20.79.12.34

==> Checking the marketing site is still Vercel's
    azmoth.com               76.76.21.21
    www.azmoth.com           no A record (a CNAME to Vercel is normal)

==> GitHub registry token
    Paste it (not echoed):

==> Checking the images exist in ghcr.io/azmoth-org
    azmoth-engine:737a8891f0c4                          present
    azmoth-web:737a8891f0c4                             present
    azmoth-web-builder:737a8891f0c4                     present

==> 1/5 Bootstrapping the VM (Docker, Compose, firewall)
    installed jq
    installing Docker from Docker's apt repository...
    installed Docker version 27.3.1, build ce12230
    docker compose 2.29.7 (>= 2.24, '!reset' supported)
    ufw: 22, 80, 443 allowed; default deny incoming
    unattended security upgrades enabled
    installed age (encrypts backups to a public key)
    cloud: aws (from the instance metadata service)
    installing the AWS CLI (for the backup job's instance-profile credentials)...
    installed aws-cli/2.28.1 Python/3.13.4 Linux/6.8.0-1029-aws

==> 2/5 Shipping the source (commit 737a889)
    1483 files

==> 3/5 Environment and secrets
    DATABASE_URL ok — ep-cool-darkness-a1b2c3d4.eu-central-1.aws.neon.tech
    DATABASE_URL_POOLED ok — ep-cool-darkness-a1b2c3d4-pooler.eu-central-1.aws.neon.tech
    generating /opt/azmoth/shared/.env
    generated, mode 600, owner azmoth

==> 4/5 Pulling, migrating and starting
    .env + release.env installed into repo/infra/docker/.env

    resolved services:
      caddy engine engine-migrate web web-auth-migrate
    published ports: 443,80
    ok — only Caddy publishes
    logged in to ghcr.io as oussamakhadraoui

    pulling 737a8891f0c4...
    pulled

    ── migrating (alembic upgrade head, on the DIRECT endpoint) ──
    INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial
    ...
    INFO  [alembic.runtime.migration] Running upgrade 0008 -> 0009_api_usage_logs

    ── migrating (Better Auth tables) ──
    created 7 tables

    starting...
    waiting for containers to report healthy (up to 5 minutes)....
    all healthy

    NAME              SERVICE   STATUS              PORTS
    azmoth-caddy-1    caddy     Up 40s (healthy)    0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
    azmoth-engine-1   engine    Up 1m (healthy)
    azmoth-web-1      web       Up 45s (healthy)

==> 5/5 Verifying
    the engine reached Neon, on the right endpoint, and the schema is at head:
      backend  : postgresql
      durable  : True
      APP_ENV  : production
      db host  : ep-cool-darkness-a1b2c3d4.eu-central-1.aws.neon.tech
      migration: 0009_api_usage_logs (head: 0009_api_usage_logs)
      web tier : ep-cool-darkness-a1b2c3d4-pooler.eu-central-1.aws.neon.tech (pooled — correct)

    published ports on this host (only Caddy's 80/443 should appear):
      0.0.0.0:80
      0.0.0.0:443
```

Three lines in that output are the ones worth reading rather than skimming:

- `published ports: 443,80` and `ok — only Caddy publishes` — the engine's 8000 is not on the host.
- `db host` has **no** `-pooler` and `web tier` **has** it. That is the split working.
- `migration: X (head: X)` — the schema is at the newest revision this image carries, not merely at
  some revision.

### 5.2 Pre-flight — what "green" means

```bash
./scripts/preflight.sh "$AZURE_HOST" --domain azmoth.com
```

This checks from the **outside**, which is the point: `docker compose ps` proves the containers are
up and proves nothing about what the internet can reach.

```
Pre-flight — azmoth.com (20.79.12.34)

1. What the internet can reach [SEC]
  ✓ port 80 is open (it must be)
  ✓ port 443 is open (it must be)
  ✓ port 8000 (engine) is closed
  ✓ port 5432 (postgres — external, nothing local) is closed
  ✓ port 3000 (web) is closed
  ✓ port 3001 (marketing — on Vercel, not here) is closed
  ✓ port 8080 (adminer — profiled out) is closed

2. TLS certificates
  ✓ app.azmoth.com — Let's Encrypt, 89 days left
  ✓ api.azmoth.com — Let's Encrypt, 89 days left
  ✓ http://app.azmoth.com redirects to HTTPS (308)

2b. azmoth.com is still served by Vercel, not by this VM [SEC]
  ✓ azmoth.com → 76.76.21.21 (not this VM)
  ✓ www.azmoth.com → 76.76.21.21 (not this VM)
  ✓ https://www.azmoth.com/ → 200 (served by Vercel)

3. api.azmoth.com exposes the partner API and nothing else [SEC]
  ✓ POST /api/v1/audit/single without a key → 401 (reachable, and refusing)
  ✓ GET /api/v1/health → 200
  ✓ GET /openapi.json → 200 (integrators can generate a client)
  ✓ /api/v1/solve → 404 (not published)
  ✓ /api/v1/proposals → 404 (not published)
  ✓ /api/v1/padnext/audit → 404 (not published)
  ✓ /api/v1/settings/api-keys → 404 (not published)
  ✓ /api/v1/rules → 404 (not published)
  ✓ /api/v1/demo → 404 (not published)

4. The application
  ✓ https://app.azmoth.com/api/health → 200
  ✓ https://app.azmoth.com/ answered 307
  – no session cookie on an anonymous request

5. On the box
  ✓ caddy is running (healthy)
  ✓ web is running (healthy)
  ✓ engine is running (healthy)
  ✓ no local postgres container (the database is Neon's)
  ✓ [SEC] sign-up allowlist is set in the running web container: you@azmoth.com,...
  ✓ 4096 MiB of swap present (headroom for a solver spike on 2 GiB)
  ✓ 1180 MiB memory available at rest
  ✓ root filesystem 22% used

6. The Neon database [SEC for the endpoint split]
  ✓ the engine can query Neon (select 1 round-tripped)
  ✓ the engine is on a durable Postgres database (postgresql)
  ✓ [SEC] the engine is on Neon's DIRECT endpoint (ep-cool-...aws.neon.tech)
  ✓ the web tier is on Neon's POOLED endpoint (correct for Better Auth)
  ✓ schema is at head (0009_api_usage_logs)
  ✗ no dump has ever been taken on this box

────────────────────────────────────────────────────────────
  38 passed   1 failed   1 skipped
────────────────────────────────────────────────────────────
```

**Green means exit status 0**, which means every check passed. On a fresh deployment the backup
check fails and that is correct — you have not taken one yet. Do [§ 5.4](#54-finish-the-backup-setup)
and re-run.

Any `✗` marked **[SEC]** stops the pilot. Those are the ones that would be an incident rather than an
outage: an open port 8000, a published engine endpoint, an empty sign-up allowlist, or the engine on
the pooled endpoint.

### 5.3 Every deploy after the first

```bash
git push origin main
gh run watch                                   # wait for images-ready
make deploy                                    # AZURE_HOST is already exported
make preflight
```

No secrets, no flags. `/opt/azmoth/shared/.env` already holds them and `deploy.sh` leaves it alone —
regenerating `BETTER_AUTH_SECRET` would log every user out, and overwriting the Neon URLs would point
a running deployment at a different database, which comes up healthy, migrates cleanly, and shows a
practice none of their own records.

### 5.4 Finish the backup setup

Nothing takes a backup for you, and Neon's Free-plan history window is **six hours** — a rollback,
not a backup.

**This is the one step after § 2 that differs by cloud.** Both scripts refuse to run without their
storage setting and `AGE_RECIPIENT` — deliberately, because a backup job that quietly does nothing
is worse than one that fails.

**[AWS]**

```bash
ssh "azmoth@$AZURE_HOST" bash -s <<EOF
set -e
grep -q '^STORAGE_BUCKET=' /opt/azmoth/shared/.env || \
  echo 'STORAGE_BUCKET=$STORAGE_BUCKET' >> /opt/azmoth/shared/.env
grep -q '^AGE_RECIPIENT=' /opt/azmoth/shared/.env || \
  echo 'AGE_RECIPIENT=age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p' >> /opt/azmoth/shared/.env
chmod 600 /opt/azmoth/shared/.env
EOF
```

**[Azure]**

```bash
STORAGE_ACCOUNT="$(az storage account list --resource-group "$RG" \
  --query '[0].name' --output tsv)"
echo "$STORAGE_ACCOUNT"

ssh "azmoth@$AZURE_HOST" bash -s <<EOF
set -e
grep -q '^STORAGE_ACCOUNT=' /opt/azmoth/shared/.env || \
  echo 'STORAGE_ACCOUNT=$STORAGE_ACCOUNT' >> /opt/azmoth/shared/.env
grep -q '^AGE_RECIPIENT=' /opt/azmoth/shared/.env || \
  echo 'AGE_RECIPIENT=age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p' >> /opt/azmoth/shared/.env
grep -q '^BACKUP_CONTAINER=' /opt/azmoth/shared/.env || \
  echo 'BACKUP_CONTAINER=db-backups' >> /opt/azmoth/shared/.env
chmod 600 /opt/azmoth/shared/.env
EOF
```

**Both.** Replace that `age1ql3z...` with **your** public key from
[§ 1.4](#14-the-two-keys-you-have-to-generate).

Take a backup now, so you find out today whether it works. `make azure-backup` runs the Azure
script; on AWS run the S3 one directly:

```bash
# [AWS]
ssh "azmoth@$AZURE_HOST" 'sudo /opt/azmoth/repo/infra/scripts/backup-to-s3.sh'
# [Azure]
make azure-backup
```

```
==> 1/6 dumping Neon over the network
    /opt/azmoth/backups/azmoth-20260902T183012Z.dump (48K)
==> 2/6 verifying the archive
    readable, 11 tables with data
==> 3/6 encrypting
    encrypted to /opt/azmoth/backups/azmoth-20260902T183012Z.dump.age (48K)
==> 4/6 checking the instance profile
    ok — azmoth-vm-backup-role via an assumed role; no credential is stored on this VM
==> 5/6 uploading
    s3://azmoth-backups-you/db-backups/2026/09/azmoth-20260902T183012Z.dump.age
    verified: 49152 bytes, matching the local file
==> 6/6 pruning local copies older than 7 days
==> done
```

On Azure, step 4 reads `authenticating with the VM's managed identity` instead, and step 5 prints a
container path. Everything else is the same script.

Then schedule it — substituting `backup-to-azure.sh` on Azure:

```bash
ssh "azmoth@$AZURE_HOST" \
  '(crontab -l 2>/dev/null | grep -v backup-to-; \
    echo "15 3 * * * /opt/azmoth/repo/infra/scripts/backup-to-s3.sh >> /var/log/azmoth-backup.log 2>&1") \
   | crontab -'
ssh "azmoth@$AZURE_HOST" 'crontab -l'
```

> **[AWS] `aws s3 ls` from the VM will say AccessDenied, and that is correct.** The instance profile
> grants `s3:PutObject` and `s3:GetObject` and deliberately not `s3:ListBucket` or
> `s3:DeleteObject` — the box can write a backup and cannot enumerate or destroy one. List from your
> laptop with your own credentials. [AWS.md § 6](AWS.md#no-credential-on-the-vm-and-the-vm-cannot-read-its-own-backups)
> has the full table of what is absent and why.

### 5.5 Back up the env file, and then the checks a script cannot do

```bash
ssh "azmoth@$AZURE_HOST" 'sudo cat /opt/azmoth/shared/.env'
```

Put that in your password manager. It is now the **only** copy of the credentials that can read the
database — without it, the encrypted dumps in the backup bucket cannot be restored anywhere.

Then work down the manual list `preflight.sh` prints in its § 7. The three that matter most:

- Sign up, sign in, sign out in a browser, and confirm an address **not** on the allowlist is refused.
- Upload a PADnext delivery and confirm the report renders, and that a delivery with no `echtdaten`
  attribute is refused with `ECHTDATEN_UNDECLARED`.
- **Do the restore drill once**, from [`docs/OPERATIONS.md` § 7.7](../OPERATIONS.md#77-restoring).
  It needs the `age` private key, which is why no script does it for you, and it is the only thing
  that turns "a backup exists" into "a backup restores".

---

## 6. Rollback

A rollback is a **pull and a restart**, not a rebuild. The images for every recent commit are still
in GHCR, and `deploy.sh` keeps a week of them on the box.

### 6.1 Find the tag to go back to

```bash
ssh "azmoth@$AZURE_HOST" 'cat /opt/azmoth/RELEASE'     # what is running now
git log --oneline -10                                   # candidates
```

### 6.2 Roll back

```bash
make rollback TAG=6a3c14c
# or:  ./scripts/deploy.sh "$AZURE_HOST" --tag 6a3c14c
```

You will see a warning, and it is worth reading rather than dismissing:

```
 !! deploying tag 6a3c14c, which is NOT your HEAD (737a889).
 !! The source shipped to the box comes from HEAD, so the compose files and Caddyfile will be
 !! HEAD's while the application images are 6a3c14c's.
```

That is correct for rolling back the **application**. If the bad deploy also changed a compose file
or the Caddyfile, check out the older commit first so the infra files match:

```bash
git checkout 6a3c14c
./scripts/deploy.sh "$AZURE_HOST"
```

### 6.3 What a rollback does NOT undo

> **Migrations.** `deploy.sh` runs `alembic upgrade head` on every deploy and there is no automatic
> downgrade. If the deploy you are rolling back added a migration, the database is now at the newer
> schema and the older image is about to query it.
>
> Usually that is fine — an added column or table is invisible to older code. It is **not** fine if
> the migration dropped or renamed something the older image still selects.

Check before you roll back across a migration:

```bash
git diff --stat 6a3c14c..HEAD -- apps/engine/alembic/versions/
```

Nothing listed: roll back freely.

Something listed: read it. If it is additive, roll back. If it is destructive, you have two options,
and the first is almost always right:

1. **Roll forward instead.** Fix the bug on top of HEAD, push, deploy. A ten-minute fix beats a
   schema downgrade under pressure.
2. **Downgrade deliberately**, then roll back the image:

   ```bash
   ssh "azmoth@$AZURE_HOST" 'cd /opt/azmoth/repo && \
     sudo COMPOSE_PROJECT_NAME=azmoth docker compose \
       -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.azure.yml \
       run --rm --entrypoint alembic engine-migrate downgrade -1'
   make rollback TAG=6a3c14c
   ```

   Take a backup first — `make azure-backup` — because a downgrade that drops a column drops the
   data in it, and Neon's Free-plan history window is six hours.

### 6.4 Verify the rollback took

```bash
ssh "azmoth@$AZURE_HOST" 'cat /opt/azmoth/RELEASE'
make azure-ps
make preflight
```

`preflight.sh` will fail its schema check if the older image's `alembic heads` is behind the
database, which is exactly the situation § 6.3 is about. A failure there after a deliberate rollback
across an additive migration is expected and is not, by itself, a reason to panic — but read the
message rather than assuming.

### 6.5 If the deploy never got that far

The steps are deliberately ordered so that a failure before `up -d` changes nothing:

| Failed at | State | What to do |
|---|---|---|
| the manifest check | nothing touched | push the commit, or `--tag` an older one |
| `docker compose pull` | **previous release still serving** | check `gh run list`, and that the token has not expired |
| the alembic step | **previous release still serving**, old schema | read the error; a Neon cold-start timeout just needs a re-run |
| the Better Auth step | engine schema migrated, sessions may not be | re-run; sign-in shows a 500 until it succeeds |
| the health wait | new containers up, not healthy | `make azure-logs SERVICE=web` — the script prints the last 40 lines itself |

Only the last row leaves you mid-deploy. Everything above it left a working system running.

---

## Where to go next

| | |
|---|---|
| Why any of this is shaped this way | [`docs/deploy/AZURE.md`](AZURE.md) |
| Day-two operations — logs, psql, restores, cost, failure modes | [`docs/OPERATIONS.md` § 7](../OPERATIONS.md#7-the-deployed-vm) |
| What `api.azmoth.com` publishes, and why not more | [`infra/docker/Caddyfile`](../../infra/docker/Caddyfile) header |
| The sub-processors this deployment created | [`docs/AVV_TECHNICAL_ANNEX_DRAFT.md`](../AVV_TECHNICAL_ANNEX_DRAFT.md) § 5.2 |
