# Deploying Azmoth on AWS

One EC2 instance, Docker Compose, Caddy in front. No ECS, no Kubernetes, no RDS, and no database on
the box either. Not because the managed alternatives are bad, but because this shape costs about
EUR 22/month and the alternatives cost several times that for a pilot that does not need them.

**The application architecture did not change when hosting moved from Azure to AWS.** The same three
containers, the same compose files, the same Caddyfile, the same images from GHCR, the same Neon
database. What changed is one provisioning script and one backup script. If you are reading this
expecting a migration, there is less to it than you think — and § 9 is the list of what actually
moved.

Three things run somewhere other than the instance, and each of them is why the instance is small:

| | Where | Why it is not on the box |
|---|---|---|
| The marketing site (`apps/marketing`) | **Vercel**, at `azmoth.com` + `www` | It has no database, no session and no engine. Moving it off removed the second `next build` from the deploy. |
| Postgres | **Neon**, `aws-eu-central-1` | A managed Postgres with point-in-time restore for 0 EUR beats a container that shares 2 GiB with the app. |
| The three images | **GHCR**, built by GitHub Actions | A `next build` peaks well over 1 GiB. Building on a runner is what keeps the box at 2 GiB. |

This document is the **why**. [`docs/deploy/RUNBOOK.md`](RUNBOOK.md) is the **what to type** — the
chronological, command-by-command procedure, including the Neon and Vercel setup. If you are
deploying right now, read that one and come back here when something looks arbitrary.

```
  ./infra/aws/provision.sh            EC2, Elastic IP, security group, S3 bucket, IAM role
  <create the Neon project>           aws-eu-central-1, and copy BOTH connection strings
  <point TWO A records at the IP>     app and api — NOT the apex, NOT www (see § 3)
  ./scripts/deploy.sh <ip>            pull from GHCR, migrate Neon, start behind Caddy
  ./scripts/preflight.sh <ip>         verify from outside
```

[`docs/deploy/AZURE.md`](AZURE.md) is the same document for the Azure deployment, which still
exists and still works. Where a section here says "unchanged", that document has the long version.

---

## 0. Why this moved off Azure

The Azure deployment was correct and it was working. It moved for one reason: **an Azure for
Students subscription cannot allocate compute in an EU region.** The AVV
([`docs/AVV_TECHNICAL_ANNEX_DRAFT.md`](../AVV_TECHNICAL_ANNEX_DRAFT.md) § 5.1) commits to processing
exclusively inside the European Union, and a subscription that can only give you a VM in the United
States cannot host this.

That is worth stating plainly, because the alternatives were considered and rejected:

- **Pay-as-you-go on Azure** would have worked. It also means putting a card behind a pilot that a
  student credit was covering, which is the decision this was trying to defer.
- **A US region with EU data** is not a workaround, it is a different AVV. The annex names Frankfurt
  and a practice signs it.
- **A bare VPS** (Hetzner, Scaleway) is genuinely cheaper and genuinely in Frankfurt. It was the
  runner-up. AWS won on one point: the database is already on AWS in `eu-central-1`, so putting the
  VM there too puts the engine and its database in the same region of the same provider instead of
  crossing between two — which is one fewer network path, one fewer provider in the AVV table, and
  one fewer thing to explain to a practice's lawyer.

Nothing about this was an architecture decision. It is a hosting decision that the architecture was
already indifferent to, which is the entire reason it was a two-script change.

---

## 1. The instance

**`t3.small` — 2 vCPU (burstable), 2 GiB RAM, 32 GiB gp3, Ubuntu 22.04 LTS, `eu-central-1`.**

### Why 2 GiB is enough

Nothing is built on this box. `.github/workflows/release-images.yml` builds the three images on a
GitHub runner and pushes them to `ghcr.io`; `scripts/deploy.sh` pulls them. What has to fit is what
has to *run*:

| | Resting |
|---|---|
| `caddy` | ~30 MiB |
| `engine` (FastAPI + Soufflé + Clingo, 1 MB catalog loaded at start) | ~350–500 MiB |
| `web` (Next.js standalone) | ~150–250 MiB |
| dockerd + the OS | ~250 MiB |

That is 800 MiB–1 GiB resting on a 2 GiB box. Postgres left the box (it is Neon's) and so did the
marketing site (Vercel's), which is what made this fit at all.

The 4 GiB swapfile is **runtime insurance, not a build crutch**: a Soufflé solve forks a process
whose peak nobody has characterised, and the failure mode without swap is the OOM killer picking a
victim — which on this box means the `web` container vanishing while somebody was mid-approval.
`vm.swappiness=10` keeps it as insurance rather than as a habit.

If `free -m` shows swap in *steady* use rather than touched at peaks, the machine is too small. Take
`t3.medium`. Do not add more swap.

### Burstable instances, and the setting that stops a surprise bill

`t3` earns CPU credits at a baseline rate and spends them above it. **AWS defaults `t3` to
`unlimited` mode, which does not throttle when the credits run out — it bills a surcharge instead.**
On a pilot budget an unexpected line item is worse than a slow solve, so `infra/aws/provision.sh`
sets `CpuCredits=standard`: exhausting the credits throttles to the 20% baseline and costs nothing
extra.

If solves start feeling slow and CloudWatch's `CPUCreditBalance` sits at zero, that is this setting
working as designed. The answer is `t3.medium`, not `unlimited`.

```bash
aws ec2 describe-instance-credit-specifications --instance-ids <id> --region eu-central-1
```

### The ladder

| | vCPU / RAM | ~EUR/month | Notes |
|---|---|---|---|
| `t3.small` | 2 / 2 GiB | ~16.00 | default |
| `t3.medium` | 2 / 4 GiB | ~32.00 | the one rung up |

```bash
INSTANCE_TYPE=t3.medium ./infra/aws/provision.sh
```

**Changing this on an existing box is not what that command does.** The script sees an instance with
the `Name=azmoth-vm` tag and leaves it alone — that is the idempotence working. Resizing is a stop,
a `modify-instance-attribute`, and a start:

```bash
aws ec2 stop-instances  --instance-ids <id> --region eu-central-1
aws ec2 wait instance-stopped --instance-ids <id> --region eu-central-1
aws ec2 modify-instance-attribute --instance-id <id> --instance-type t3.medium --region eu-central-1
aws ec2 start-instances --instance-ids <id> --region eu-central-1
```

The Elastic IP survives that, which is exactly why it is an Elastic IP.

### Not Graviton, however tempting the price is

`t4g.small` is Arm, is cheaper than any x86 SKU with the same memory, and **cannot run this stack**.
`apps/engine/Dockerfile` installs `x86_64-ubuntu-2204-souffle-2.5-Linux.deb`, and the engine is
nothing without Soufflé. Moving to Arm is a new Soufflé build and a multi-arch image, not an
`INSTANCE_TYPE` change.

This is the same constraint that ruled out `Standard_B2pls_v2` on Azure. Changing cloud did not
change it.

### The disk is 32 GiB gp3

What has to fit is Ubuntu, Docker, three pulled images (engine ~300 MB, web ~350 MB, the web
`builder` image ~1 GB, caddy ~50 MB — under 2 GiB in total), and the `azmoth-engine-uploads` volume
holding bulk deliveries that have been accepted and not yet audited. 32 GiB is roughly ten times what
is needed, which is the right margin for a volume nobody wants to resize during an incident.

**gp3 rather than gp2**: cheaper per GiB, and its 3000 IOPS / 125 MB/s baseline is free and
independent of capacity. gp2 ties IOPS to size and would give a 32 GiB volume only 100 — enough, but
for no saving.

The volume is created with `Encrypted=true`. There is no separate data volume, deliberately: the
database is Neon's and the dumps go to S3.

### What the whole thing costs

| | ~EUR/month |
|---|---|
| `t3.small`, on-demand, 730 h | 16.00 |
| 32 GiB gp3 | 2.80 |
| Elastic IP, associated | 3.35 |
| S3 Standard, a few GB of dumps | 0.10 |
| Egress (first 100 GB free) | 0.00 |
| **Total** | **~22.25** |

Converted from published on-demand USD rates for `eu-central-1`, and they move. Check before
committing: <https://calculator.aws/>.

Two things that are easy to miss:

- **AWS bills every public IPv4 address** — allocated or in use — since 1 February 2024. That is the
  EUR 3.35 line, and it is not optional: the box needs a public address to serve on and DNS needs one
  that does not move. It is also the line that keeps billing after a careless teardown, because an
  Elastic IP that is allocated and associated with *nothing* costs the same. `aws ec2 release-address`
  is the end of the teardown.
- **A stopped instance still bills for its EBS volume and its Elastic IP.** Stopping the box saves
  the EUR 16 and not the other EUR 6.

### Region: `eu-central-1`, and it is not a preference

[`docs/AVV_TECHNICAL_ANNEX_DRAFT.md`](../AVV_TECHNICAL_ANNEX_DRAFT.md) § 5.1 states that processing
happens exclusively on systems inside the European Union. Frankfurt satisfies that.

`infra/aws/provision.sh` **refuses to run** with a `REGION` that does not start with `eu-`. That is
deliberate and it is not a formality: the failure mode it prevents is a resource created in
`us-east-1` because a shell had `AWS_DEFAULT_REGION` set from something else, discovered months later
by a lawyer rather than by an engineer.

One thing genuinely improves here over Azure: Neon has no Azure region any more (`azure-gwc` stopped
accepting new projects on 7 April 2026), so the database was always in `aws-eu-central-1`. The VM is
now in the same region of the same provider rather than in a different provider's Frankfurt.

---

## 2. Provisioning

### The short way

```bash
aws configure          # or: aws sso login
./infra/aws/provision.sh
```

Idempotent — every step checks before it creates, so a run that fails halfway (a capacity refusal, a
dropped connection) is fixed by running it again rather than by working out which half happened.
Override anything from the environment:

```bash
INSTANCE_TYPE=t3.medium STORAGE_BUCKET=azmoth-backups-praxisnord ./infra/aws/provision.sh
```

It refuses to start without an SSH public key, it refuses to run outside an EU region, and it
**refuses to open port 22 to the internet** — if it cannot detect your public IP it stops and asks
for it rather than defaulting to `0.0.0.0/0`.

### Exactly six resources, and no more

| | Name | Why |
|---|---|---|
| EC2 key pair | `azmoth-vm-key` | Your existing `~/.ssh/id_ed25519.pub`, **imported**, not generated |
| Security group | `azmoth-vm-sg` | Three inbound rules: 22 from you, 80 and 443 from anywhere |
| Elastic IP | tagged `azmoth-vm-eip` | A fixed address, because DNS and certificates depend on it |
| EC2 instance | `azmoth-vm` | The box |
| S3 bucket | `azmoth-backups-<suffix>` | Private, versioned, TLS-only |
| IAM role + instance profile | `azmoth-vm-backup-role` | `s3:PutObject`/`s3:GetObject` on that bucket only |

**No RDS. No Aurora. No load balancer. No NAT gateway. No custom VPC.** If you find one of those in
this account, this script did not make it.

### It uses the default VPC and does not create one

An instance needs a subnet and a subnet needs a VPC. Every account gets a default VPC per region with
a public subnet in each availability zone and an internet gateway already attached — exactly the
topology a single public box wants.

Using it is a deliberate limit on what this script owns. A custom VPC means a route table, an
internet gateway, subnets in at least two AZs to keep options open, and — the moment anything private
appears — a **NAT gateway at roughly EUR 33/month, which is more than the VM**. That is architecture
this deployment does not have and should not grow by accident.

If the account has no default VPC (some organisations delete them), recreate it. It is free:

```bash
aws ec2 create-default-vpc --region eu-central-1
```

### The AMI is resolved, never hardcoded

```
/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id
```

An AMI id is region-specific *and* changes with every image Canonical builds. A hardcoded one is a
guarantee of deploying a months-old kernel, or of a `does not exist` failure the day it is
deregistered. This SSM public parameter always names the current 22.04 build.

The script also reads `RootDeviceName` off the resolved AMI rather than assuming `/dev/sda1`. A block
device mapping that names a device the AMI does not have is **silently ignored** — which would give
you the AMI's default 8 GiB root volume instead of 32, and no error.

### The security group

Three inbound rules. A security group is default-deny for ingress, so **8000 is closed because
nothing opens it** — and there is no such thing as a deny rule in a security group, which is worth
knowing before you go looking for one. The Azure NSG had priorities and an implicit
`DenyAllInBound`; this has neither.

The default **egress** rule (allow all) is left as AWS creates it. That is what lets the engine reach
Neon in Frankfurt over TLS on 5432 and lets Docker pull from `ghcr.io`. Those are the two flows to
remember if you ever tighten it: a locked-down egress rule set is a stack that comes up healthy,
passes its own healthchecks, and cannot read a single proposal.

**The SSH rule is rewritten on every run.** Your ISP reassigns your address, and re-running the
script is how that rule is meant to be corrected — same behaviour as the Azure script's
`nsg rule update`, but it needs a loop here because a security group holds a *list* of CIDRs on one
rule rather than one rule per source. Every `22/tcp` CIDR that is not your current address is
revoked. If you deliberately added a colleague's address, it will be gone after a rerun, and that is
the intended trade: an SSH allowlist that accumulates entries nobody remembers adding is how a stale
address stays authorised for a year.

```bash
aws ec2 describe-security-groups --group-names azmoth-vm-sg --region eu-central-1 \
  --query 'SecurityGroups[0].IpPermissions[].{port:FromPort,source:IpRanges[0].CidrIp}' --output table
```

And from outside, which is the check that actually counts — `./scripts/preflight.sh` does this:

```bash
nc -zv -w5 <public-ip> 8000     # must time out
```

### Two walls, not one

The security group is the outer wall.
[`infra/docker/docker-compose.azure.yml`](../../infra/docker/docker-compose.azure.yml) is the inner
one: it unpublishes 8000 (engine) and 3000 (web) from Docker entirely.

> **On that filename.** It says `azure` and it is used unchanged on AWS. Its content is about *not
> publishing ports* and about which services are profiled out — neither of which is an Azure fact.
> Renaming it would touch every compose invocation in `deploy.sh`, `preflight.sh`, `OPERATIONS.md`
> and the `Makefile` for no behavioural gain, so it was left alone. Read it as
> "docker-compose.**single-public-box**.yml".

Both walls exist because **a published Docker port bypasses the host firewall**. Docker writes its
own `DOCKER-USER` iptables rules, so a container publishing 8000 is reachable even when `ufw` insists
it is not. The security group does stop it — but the security group is also the thing edited in a
console by someone who does not know what 8000 is, and a published port is added by someone editing
compose. Neither wall alone would catch the other's mistake.

The `!reset` merge tag does the unpublishing and needs **Docker Compose v2.24 or newer**.
`scripts/deploy.sh` asserts the version before it runs anything.

### IMDSv2 only

The instance is created with `HttpTokens=required` and `HttpPutResponseHopLimit=1`.

This is not a checkbox. The instance metadata service at `169.254.169.254` is **where the IAM role's
credentials come from**. Under IMDSv1 it answered an unauthenticated `GET`, which means any
server-side request forgery in anything running on the box — a URL fetcher handed
`http://169.254.169.254/...` — hands back a working AWS credential. IMDSv2 requires a `PUT` with a
header first, which a naive proxied `GET` cannot make.

The hop limit of 1 stops the token surviving a hop into a Docker bridge network, so **a container
cannot reach the metadata service at all**. That is why `pg_dump` runs in a container and `aws s3 cp`
runs on the host. If you ever need an AWS SDK inside a container here, raising that limit is a
decision to make deliberately rather than a limit to bump in passing.

### The `azmoth` user

The Ubuntu AMI logs in as `ubuntu`. `scripts/deploy.sh` defaults to `azmoth`, which is what the Azure
box had, so cloud-init creates that user on first boot with the same authorized key and passwordless
sudo. That is the only reason `./scripts/deploy.sh <ip>` is identical on both providers rather than
needing a `--user` flag somebody has to remember.

cloud-init runs **once**, so step 7 of the script re-checks the user and the swapfile over SSH and
fixes them if they are missing. That is what makes a rerun converge on an instance that already
existed. It is not fatal if SSH is not answering yet — a fresh instance takes a minute or two, and
the honest report is "could not check yet, run me again".

> Why SSH and not SSM Run Command, which would be the closer analogue of Azure's
> `vm run-command invoke`: SSM needs the `AmazonSSMManagedInstanceCore` managed policy on the
> instance role. That policy grants far more than "write objects to one bucket", on the box holding
> the clinical data. Keeping the role at two S3 actions is worth reaching for the SSH key the script
> already required.

### The same thing by hand

```bash
REGION=eu-central-1
VM=azmoth-vm
MY_IP=$(curl -s https://api.ipify.org)
BUCKET=azmoth-backups-example
VPC=$(aws ec2 describe-vpcs --region $REGION --filters Name=isDefault,Values=true \
        --query 'Vpcs[0].VpcId' --output text)
SUBNET=$(aws ec2 describe-subnets --region $REGION --filters Name=vpc-id,Values=$VPC \
        Name=default-for-az,Values=true --query 'Subnets[0].SubnetId' --output text)

# 1. Key pair. IMPORTED, not created: `create-key-pair` generates the private half on AWS's side
#    and returns it once, which means it existed in an API response. Import keeps your private key
#    where it has always been.
aws ec2 import-key-pair --region $REGION --key-name ${VM}-key \
  --public-key-material fileb://~/.ssh/id_ed25519.pub

# 2. Security group — three inbound rules and no more. Egress stays as AWS creates it (allow all),
#    which is what lets the engine reach Neon and Docker reach ghcr.io.
SG=$(aws ec2 create-security-group --region $REGION --group-name ${VM}-sg --vpc-id $VPC \
      --description "Azmoth: SSH from the operator only, HTTP and HTTPS from anywhere" \
      --query GroupId --output text)

aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG \
  --ip-permissions "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=$MY_IP/32}]"

#    80 is not optional: Let's Encrypt's HTTP-01 challenge arrives here and Caddy serves the
#    redirect to 443 from it. Closing 80 does not harden anything, it stops TLS working.
aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG \
  --ip-permissions "IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0}]"
aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG \
  --ip-permissions "IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0}]"

# 3. The bucket. Private, versioned, TLS-only — see § 6.
aws s3api create-bucket --region $REGION --bucket $BUCKET \
  --create-bucket-configuration LocationConstraint=$REGION
aws s3api put-public-access-block --bucket $BUCKET --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-versioning --bucket $BUCKET --versioning-configuration Status=Enabled

# 4. The role the instance assumes, so no AWS key is ever written to the box. The inline policy is
#    two actions on one bucket's objects — see § 6 for what is deliberately absent from it.
aws iam create-role --role-name ${VM}-backup-role --assume-role-policy-document \
  '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam put-role-policy --role-name ${VM}-backup-role --policy-name s3-backup-write \
  --policy-document \
  "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:PutObject\",\"s3:GetObject\"],\"Resource\":\"arn:aws:s3:::$BUCKET/*\"}]}"
aws iam create-instance-profile --instance-profile-name ${VM}-backup-profile
aws iam add-role-to-instance-profile --instance-profile-name ${VM}-backup-profile \
  --role-name ${VM}-backup-role

# 5. The instance. AMI resolved from SSM, never hardcoded. IMDSv2 required. CPU credits standard so
#    exhausting the burst budget throttles rather than bills.
AMI=$(aws ssm get-parameters --region $REGION \
  --names /aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id \
  --query 'Parameters[0].Value' --output text)

ID=$(aws ec2 run-instances --region $REGION --image-id $AMI --instance-type t3.small \
  --key-name ${VM}-key --subnet-id $SUBNET --security-group-ids $SG \
  --iam-instance-profile Name=${VM}-backup-profile \
  --credit-specification CpuCredits=standard \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1 \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":32,"VolumeType":"gp3","Encrypted":true}}]' \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$VM}]" \
  --query 'Instances[0].InstanceId' --output text)

# 6. Elastic IP. A default public address is released when the instance stops and comes back
#    different, which breaks the DNS the certificates depend on.
ALLOC=$(aws ec2 allocate-address --region $REGION --domain vpc --query AllocationId --output text)
aws ec2 wait instance-running --region $REGION --instance-ids $ID
aws ec2 associate-address --region $REGION --allocation-id $ALLOC --instance-id $ID

aws ec2 describe-addresses --region $REGION --allocation-ids $ALLOC \
  --query 'Addresses[0].PublicIp' --output text
```

The script does one more thing this listing does not: the swapfile and the `azmoth` user, via
user-data on first boot and via SSH on every rerun.

---

## 3. DNS — **two** records, and two that must not move

Unchanged from Azure, and the reasoning is at length in [AZURE.md § 3](AZURE.md#3-dns--two-records-and-two-that-must-not-move).
The short version:

```
A   app.azmoth.com    <elastic-ip>
A   api.azmoth.com    <elastic-ip>
```

**`azmoth.com` and `www.azmoth.com` stay on Vercel.** This box has no marketing container and its
Caddyfile has no site block for those names, so pointing them here takes the public site down *and*
makes Caddy request a Let's Encrypt certificate for a name Vercel already holds — burning one of five
weekly duplicates. Both `scripts/deploy.sh` and `scripts/preflight.sh` refuse outright if the apex
resolves to the VM. It is the only DNS condition in either script that is fatal.

Point DNS **before** running `scripts/deploy.sh` and wait for it to resolve. Caddy gets its
certificates over HTTP-01, which means Let's Encrypt fetches a token from these names over port 80. A
name that does not resolve yet is a failed issuance and a retry backoff, not a warning.

```bash
dig +short app.azmoth.com
dig +short azmoth.com          # must NOT be the elastic IP
```

Nothing here uses Route 53. The domain's DNS is wherever it already is, and moving it would be a
change with no benefit and one more AWS resource to bill for.

---

## 4. The database — still Neon, still `aws-eu-central-1`

**Unchanged, and this is the section where "we moved to AWS" most invites a wrong assumption.**
Moving the VM to AWS did **not** move the database to RDS, and should not. The reasoning is in
[AZURE.md § 4](AZURE.md#4-the-database--neon-and-why-it-is-on-aws) in full; the parts that matter
after the move:

- **Neon's Free plan is EUR 0.** The smallest RDS instance that would run this is roughly EUR 25/month
  on top of everything in § 1 — more than doubling the cost of the deployment to get a database that
  is worse suited to it (no scale-to-zero, no branching, no instant restore).
- `infra/aws/provision.sh` creates **no RDS instance and no Aurora cluster**, deliberately and
  by design. If you want one, that is a separate decision with a separate AVV entry.
- The Neon project was always in `aws-eu-central-1`. It is now in the same region as the VM, which
  removes a cross-provider network path but changes nothing about the connection strings.

**Two connection strings, and they are not interchangeable.** Unchanged:

| | Which | Used by |
|---|---|---|
| `DATABASE_URL` | **direct** (no `-pooler` in the host) | `alembic upgrade head`, Better Auth's migrator, the engine at runtime, `pg_dump` |
| `DATABASE_URL_POOLED` | **pooled** (host contains `-pooler`) | Better Auth at runtime, in the web tier only |

`scripts/deploy.sh` validates both — scheme, quoting, `$`, and the `-pooler` infix in the right one —
before it ships a byte. **That validation was not touched by the move to AWS and must keep working.**
The counter-intuitive half (why the *engine* gets the *direct* endpoint) is
[AZURE.md § 4](AZURE.md#why-the-engine-gets-the-direct-endpoint--the-least-obvious-decision-here);
the short version is that SQLAlchemy's asyncpg dialect mints named prepared statements that a
transaction-mode pooler mishandles, and the symptom is an intermittent
`DuplicatePreparedStatementError` under concurrency rather than a clean failure now.

---

## 5. Deploying

**Unchanged.** `scripts/deploy.sh` needs an Ubuntu host it can `ssh` to as a sudoer; it does not care
which cloud that host is in. See [AZURE.md § 5](AZURE.md#5-deploying) for the long version of *why*
nothing is built on the box, why the source is still shipped as `git archive HEAD`, why the secrets
are written once and never again, and why a rollback is a pull and a restart.

```bash
DATABASE_URL='postgresql+asyncpg://…@ep-xxx.eu-central-1.aws.neon.tech/azmoth?sslmode=require' \
DATABASE_URL_POOLED='postgresql+asyncpg://…@ep-xxx-pooler.eu-central-1.aws.neon.tech/azmoth?sslmode=require' \
  ./scripts/deploy.sh <elastic-ip> --signup-allowlist "you@azmoth.com"
```

The one AWS-aware thing it does: during bootstrap it asks the **instance metadata service** which
cloud the box is in, and installs `aws` or `az` accordingly for the backup job. It asks the box
rather than taking a flag because the box is the thing that knows, and because a wrong flag would
fail silently — the symptom is a backup job that refuses to run, discovered weeks later.

On a host that is in neither cloud it installs neither, says so, and deploys anyway. The stack runs
fine; the backup job will not, because there is no instance profile for it to use.

---

## 6. Backups

**An encrypted `pg_dump` of Neon, pushed to a private S3 bucket by
[`infra/scripts/backup-to-s3.sh`](../../infra/scripts/backup-to-s3.sh).**

This is the direct mirror of `backup-to-azure.sh`. Everything about *what* is backed up and *how it
is protected* is identical — the same dump over the network, the same archive verification, the same
`age` encryption to a key that is not on the box. Only the destination and the credential changed.
`backup-to-azure.sh` is not deleted; a deployment still on Azure needs it.

### Why an off-host copy at all, when Neon has point-in-time restore

1. **Neon's Free-plan history window is six hours, capped at 1 GB.** That is a rollback, not a
   backup. Launch extends it to seven days for usage-based cents — worth doing — but seven days is
   still not an archive for records a practice is legally obliged to be able to produce.
2. **It is the only copy that survives losing the Neon account.** Instant restore, snapshots and
   branches all live *inside* the Neon project. A billing lapse, a deleted project, a compromised
   login, or Neon's own note that Free-plan projects idle for 90 days "are subject to deletion" take
   the database and its backups together.
3. **It holds the things that are not in the database** — an encrypted copy of
   `/opt/azmoth/shared/.env`, which contains the Neon connection strings, without which the dumps are
   just files.

> **One thing to be honest about after the move.** Neon runs on AWS, so this bucket is now with the
> same *provider* as the database rather than a different one. It is still a different account, a
> different service and a different credential, which is what
> [`docs/OPERATIONS.md`](../OPERATIONS.md) § 2 is actually asking for. A practice that wants provider
> diversity needs a third copy somewhere else entirely, and that is a conversation to have rather
> than something to imply by silence.

### No credential on the VM, and the VM cannot read its own backups

Two separate mechanisms, and it is worth keeping them separate in your head:

**The credential.** An IAM role assumed through an EC2 instance profile. The AWS CLI picks up
short-lived, automatically rotated credentials from the metadata service. There is no
`~/.aws/credentials` on the box and no access key anywhere on disk. The alternative — an access key
pair in a file — is a long-lived credential sitting next to the very dumps it protects, and rotating
it means finding every copy.

What the role deliberately **cannot** do:

| Absent | Why |
|---|---|
| `s3:DeleteObject` | A compromised VM must not be able to destroy the backups it wrote. Retention is a bucket lifecycle rule, set from your laptop. |
| `s3:ListBucket` | The box has no reason to enumerate the bucket. `aws s3 ls s3://<bucket>` **from the VM answers AccessDenied — that is the policy working.** List from your laptop. |
| `s3:PutBucketPolicy`, `s3:PutBucketAcl` | An account- or bucket-level grant would let a compromised VM make a bucket of clinical records public. That is the failure this whole arrangement exists to prevent. |

Bucket versioning backs the first row up: `PutObject` on an existing key would overwrite it, and with
versioning on the old version survives. The script also refuses to upload to a key that already
exists, so an overwrite would take a clock going backwards *and* a deliberate edit.

**The encryption.** S3 encrypts objects at rest with its own keys (SSE-S3, set as a bucket default).
That protects against a stolen disk in a datacentre and **not** against the bucket being made
readable by a misconfiguration. So the dump is encrypted *before it leaves the VM*, with `age`, to a
**public** key. The private half is never on the VM.

A compromised VM can therefore write backups and cannot read back a single one — and neither can
anyone who gets read access to the bucket.

```bash
# on your laptop, once
age-keygen -o azmoth-backup.key
# → Public key: age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p
```

Keep `azmoth-backup.key` in a password manager and **nowhere else**. Losing it loses every backup.
That is the trade, and it is stated here rather than discovered.

```bash
# on the VM
sudo tee -a /opt/azmoth/shared/.env <<'ENV'
STORAGE_BUCKET=azmoth-backups-xxxxxx
AGE_RECIPIENT=age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p
ENV

# 03:15 UTC daily
crontab -e
# 15 3 * * * /opt/azmoth/repo/infra/scripts/backup-to-s3.sh >> /var/log/azmoth-backup.log 2>&1
```

The script **refuses to run** without both `STORAGE_BUCKET` and `AGE_RECIPIENT`. Deliberately: a
backup job that quietly does nothing is worse than one that fails, and a dump that goes up
unencrypted is a complete copy of every approval and audit event protected only by a bucket setting.

`ALLOW_UNENCRYPTED_BACKUP=1` exists as an escape hatch and shouts about itself in the log that cron
mails, because "we meant to set that up later" is how it stays unset for the life of a pilot.

### What ends up in the bucket

```
s3://azmoth-backups-xxxxxx/db-backups/2026/09/azmoth-20260902T031500Z.dump.age
```

Laid out by date, so listing a month is a prefix query rather than a scan. The dump is
`pg_dump --format=custom`, taken over the network against Neon's **direct** endpoint in a pinned
`postgres:17-alpine` container — a container because `pg_dump` must be at least as new as the server
and Ubuntu 22.04 ships 14; the direct endpoint because a dump holds one transaction open across
hundreds of statements and a transaction-mode pooler does not promise to keep it on one server
connection. The script refuses a `-pooler` host outright.

Every dump is verified with `pg_restore --list` **before** it is encrypted and uploaded, and the
uploaded object's size is read back and compared. A backup nobody has opened is a file, not a backup.

### Retention

Local copies are pruned after 7 days. **Objects in S3 are never deleted by the script** — the role
has no `s3:DeleteObject`, so a compromised VM could not delete them even if the script were edited to
try. Retention in the bucket is a lifecycle rule you set:

```bash
aws s3api put-bucket-lifecycle-configuration --bucket azmoth-backups-xxxxxx \
  --lifecycle-configuration file://lifecycle.json
```

Mind that the bucket is **versioned**: a rule that expires current versions leaves noncurrent ones
behind unless it also has a `NoncurrentVersionExpiration`. A rule that appears to delete old backups
and does not is worse than no rule, because it is believed.

Storage class is left at STANDARD. STANDARD_IA is cheaper per GB and carries a 30-day minimum billing
duration and a 128 KB minimum object size; on a pilot's few GB the saving is cents and the
early-deletion penalty is a real trap. Transition on age with a lifecycle rule if it ever matters —
do not pick a class per upload.

### Restoring

The procedure is [`docs/OPERATIONS.md`](../OPERATIONS.md) § 7.7 and it has not changed except for the
download command. **Restore into a Neon branch, not over production**, and do the decryption on your
laptop, because that is where the private key is:

```bash
# 1. find it — from your LAPTOP, with your own credentials. The VM cannot list.
aws s3 ls s3://azmoth-backups-xxxxxx/db-backups/2026/09/ --region eu-central-1

# 2. download and decrypt locally
aws s3 cp s3://azmoth-backups-xxxxxx/db-backups/2026/09/azmoth-20260902T031500Z.dump.age . \
  --region eu-central-1
age -d -i azmoth-backup.key azmoth-20260902T031500Z.dump.age > restored.dump

# 3. check it BEFORE sending it anywhere
pg_restore --list restored.dump | head -40
```

**Do a restore drill once, by hand, before the pilot sees real data.** `preflight.sh` cannot do it —
it needs the `age` private key, which is deliberately not on the VM and not in CI — so it is on the
manual checklist instead, and a manual checklist item is one that gets skipped unless somebody
decides not to.

---

## 7. Pre-flight

```bash
./scripts/preflight.sh <elastic-ip> --domain azmoth.com
```

**Unchanged**, and provider-agnostic by construction: it checks from the *outside*, over HTTP, TLS
and DNS, which is the point — `docker compose ps` proves the containers are up and proves nothing
about what the internet can reach. See [AZURE.md § 7](AZURE.md#7-pre-flight-checklist).

Two things it now does differently, both cosmetic: it asks the metadata service which cloud the box
is in so that it names the right backup script in its hints, and its firewall hint prints both the
`aws ec2 describe-security-groups` and the `az network nsg rule list` form.

Checks marked `[SEC]` are the ones that would be a security incident rather than an outage. Exit
status is 0 only if every check passes.

---

## 8. Day two

Everything in [AZURE.md § 8](AZURE.md#8-day-two) applies. The AWS-specific equivalents:

```bash
# what is running
ssh azmoth@<ip> 'cat /opt/azmoth/RELEASE'

# stop the box overnight — saves the EUR 16, not the EBS or the Elastic IP
aws ec2 stop-instances  --instance-ids <id> --region eu-central-1
aws ec2 start-instances --instance-ids <id> --region eu-central-1
#   The Elastic IP survives. DNS does not need to change. That is why it is elastic.

# burst credits, if solves feel slow
aws cloudwatch get-metric-statistics --region eu-central-1 \
  --namespace AWS/EC2 --metric-name CPUCreditBalance \
  --dimensions Name=InstanceId,Value=<id> \
  --start-time "$(date -u -d '6 hours ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --period 3600 --statistics Average

# what it is costing
aws ce get-cost-and-usage --time-period Start=2026-09-01,End=2026-10-01 \
  --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE
```

**Set a budget alert before you create anything**, not after. AWS has no spending cap — a fixed
credit on Azure stopped when it ran out, and an AWS account does not:

```bash
aws budgets create-budget --account-id <account> --budget \
  '{"BudgetName":"azmoth-pilot","BudgetLimit":{"Amount":"40","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST"}'
```

### Teardown

```bash
aws ec2 terminate-instances --instance-ids <id> --region eu-central-1
aws ec2 release-address --allocation-id <alloc> --region eu-central-1   # ← the one people forget
aws ec2 delete-security-group --group-id <sg> --region eu-central-1
aws iam remove-role-from-instance-profile --instance-profile-name azmoth-vm-backup-profile \
  --role-name azmoth-vm-backup-role
aws iam delete-instance-profile --instance-profile-name azmoth-vm-backup-profile
aws iam delete-role-policy --role-name azmoth-vm-backup-role --policy-name s3-backup-write
aws iam delete-role --role-name azmoth-vm-backup-role
```

There is no single `az group delete` equivalent — that is the one thing Azure genuinely did better
here, and it is why the list above is worth keeping. **Release the Elastic IP.** An allocated,
unassociated address bills at the same rate as one in use, and an abandoned pilot that left one
behind goes on costing EUR 3.35/month forever.

The bucket is left out of that list on purpose. Deleting it deletes the backups.

---

## 9. What actually changed, and what did not

| | Status |
|---|---|
| `infra/aws/provision.sh` | **new** |
| `infra/scripts/backup-to-s3.sh` | **new** |
| `infra/azure/provision.sh`, `backup-to-azure.sh` | unchanged, still work |
| `scripts/deploy.sh` | detects the cloud and installs `aws` or `az`; hints and comments updated. No behavioural change on Azure. |
| `scripts/preflight.sh` | names the right backup script and firewall command. No check added or removed. |
| `infra/docker/docker-compose.yml`, `docker-compose.azure.yml`, `Caddyfile` | **untouched** |
| `apps/*` | **untouched** |
| Neon, the connection strings, the endpoint split | **untouched** |
| Vercel and the marketing site | **untouched** |
| GHCR and `release-images.yml` | **untouched** |
| `docs/AVV_TECHNICAL_ANNEX_DRAFT.md` § 5 | **updated** — the sub-processor list is now three, not four |

The AVV change is the one with consequences outside this repository. Microsoft leaves the list; AWS
now appears for the VM and the backups as well as for the infrastructure Neon runs on. That is a
document a practice signs, so it has to be right before anyone does.
