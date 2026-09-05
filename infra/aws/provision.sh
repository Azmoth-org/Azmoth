#!/usr/bin/env bash
#
# Provision the single VM Azmoth runs on, and nothing else. AWS edition.
#
#     ./infra/aws/provision.sh
#
# This is the AWS mirror of infra/azure/provision.sh. **The application architecture does not
# change**: Docker Compose and Caddy on one box, Neon for Postgres, Vercel for the marketing site,
# GHCR for the images. Only the provisioning moved, and it moved for one reason — an Azure for
# Students subscription cannot allocate compute in an EU region, and the AVV requires the EU. See
# docs/deploy/AWS.md § 1.
#
# Idempotent: every step checks whether the resource exists before creating it, so a run that fails
# halfway through — a quota refusal, a dropped connection — is fixed by running it again rather than
# by working out which half happened. It creates no RDS instance, no Aurora cluster, no load
# balancer and no NAT gateway; the whole stack is Docker Compose on one box, which is what makes a
# small budget last a pilot rather than a fortnight.
#
# It prints the public IP at the end. Point DNS at it before running scripts/deploy.sh, because
# Caddy gets its certificates over HTTP-01 and that requires the names to already resolve here.
#
# ── What this costs, and why these sizes ──────────────────────────────────────────────────────
# About EUR 22/month on-demand in eu-central-1:
#
#     t3.small  2 vCPU (burstable), 2 GiB   ~EUR 16.00/mo
#     32 GiB gp3 root volume                ~EUR  2.80/mo
#     Elastic IP, associated                ~EUR  3.35/mo  (AWS bills public IPv4 since Feb 2024)
#     S3 Standard, a few GB of dumps        ~EUR  0.10/mo
#     Egress                                ~EUR  0.00/mo  (100 GB/month is free)
#
# Those figures are converted from published on-demand USD rates for this region and they move.
# Check yours before committing:
#     aws ec2 describe-instance-types --instance-types t3.small --region eu-central-1
#     https://calculator.aws/
#
# It is roughly what the Azure box cost (EUR 20/mo for a Standard_B1ms), which is the point: this is
# a lift-and-shift of the hosting, not a resize of the application.
#
# **2 GiB is enough because this box does not BUILD anything.** Images are built by
# .github/workflows/release-images.yml on a GitHub runner and pulled from ghcr.io; see the header of
# infra/docker/docker-compose.azure.yml. Postgres left the box (it is Neon's) and so did the
# marketing site (Vercel's), which leaves caddy + engine + web at roughly 500-800 MiB resting, plus
# ~250 MiB for dockerd and the OS. The 4 GiB swapfile below is insurance for a Soufflé solve that
# spikes, not a crutch for a build.
#
# ── Burstable instances bill for CPU you did not budget for, unless you say otherwise ─────────
# t3 is a burstable family: it earns CPU credits at a baseline rate and spends them above it. AWS
# defaults t3 to **unlimited** mode, which does not throttle when the credits run out — it bills the
# surcharge instead. On a fixed pilot budget a surprise line item is worse than a slow solve, so
# this script sets `CpuCredits=standard`, where exhausting the credits throttles to the 20% baseline
# and costs nothing extra.
#
# If solves start feeling slow and `CPUCreditBalance` in CloudWatch sits at zero, that is this
# setting working as intended and the answer is the next rung of the ladder, not unlimited mode.
#
# ── If t3.small is not enough, there is a ladder ──────────────────────────────────────────────
#
#     INSTANCE_TYPE=t3.small     2 vCPU / 2 GiB   ~EUR 16.00/mo   (default)
#     INSTANCE_TYPE=t3.medium    2 vCPU / 4 GiB   ~EUR 32.00/mo
#
# **Not Graviton, however tempting the price is.** t4g.small is Arm and cheaper than any x86 SKU
# with the same memory, and it cannot run this stack: apps/engine/Dockerfile installs
# `x86_64-ubuntu-2204-souffle-2.5-Linux.deb`, and the engine is nothing without Soufflé. Moving to
# Arm is a new Soufflé build and a multi-arch image, not an INSTANCE_TYPE change. This is the same
# constraint that ruled out Standard_B2pls_v2 on Azure, and it has not changed by moving provider.
#
# ── Region ────────────────────────────────────────────────────────────────────────────────────
# eu-central-1 (Frankfurt), and this is a compliance constraint rather than a latency preference.
# docs/AVV_TECHNICAL_ANNEX_DRAFT.md § 5.1 states that processing happens exclusively on systems
# inside the EU. Frankfurt satisfies that. Do not move this to us-east-1 to save a euro — the script
# refuses to run outside an EU region for exactly that reason.
#
# One thing genuinely improves in the move: the database was already in Frankfurt and already on
# AWS. Neon has no Azure region any more (azure-gwc stopped accepting new projects on 7 April 2026),
# so the Neon project lives in aws-eu-central-1. Putting the VM there too means the engine and its
# database are in the same region of the same provider, instead of crossing between two.
#
# NOTE: deploying at all makes § 5.2 of that annex ("Unterauftragsverarbeiter") a list that has to
# be kept true. After this move it reads: AWS (this VM, its S3 backups, and the infrastructure Neon
# runs on), Neon/Databricks (the database), and Vercel (the public site). Microsoft leaves the list.
# See docs/deploy/AWS.md § 4.

set -euo pipefail

# The AWS CLI v2 pipes output through a pager, which turns every `--query` in this script into a
# prompt waiting for someone to press q. Off, for the life of this process only.
export AWS_PAGER=""

# ── Settings ──────────────────────────────────────────────────────────────────────────────────
# Override any of these from the environment:  INSTANCE_TYPE=t3.medium ./infra/aws/provision.sh

REGION="${REGION:-eu-central-1}"
INSTANCE_NAME="${INSTANCE_NAME:-azmoth-vm}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.small}"
ADMIN_USER="${ADMIN_USER:-azmoth}"

# Ubuntu 22.04 LTS, resolved at run time from Canonical's own SSM public parameter rather than
# written down here. An AMI id is region-specific AND changes with every image build, so a
# hardcoded one is a guarantee of deploying a months-old kernel — or of a "does not exist" error the
# day Canonical deregisters it. This parameter always names the current build.
#
# The Azure script pins a full image URN for the same reason it uses one at all: to be explicit
# about the version. Here the version IS explicit — 22.04 — and only the build floats.
AMI_SSM_PARAMETER="${AMI_SSM_PARAMETER:-/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id}"

# 32 GiB gp3. What has to fit is: Ubuntu, Docker, and three pulled images (engine ~300 MB, web
# ~350 MB, the web `builder` image ~1 GB, caddy ~50 MB) — under 2 GiB of images — plus the
# `azmoth-engine-uploads` volume holding bulk deliveries that have been accepted and not yet
# audited. 32 GiB is roughly ten times what is needed, which is the right margin for a volume nobody
# wants to resize during an incident.
#
# gp3 rather than gp2: it is cheaper per GiB, and its 3000 IOPS / 125 MB/s baseline is free and
# independent of size, where gp2 ties IOPS to capacity and would give a 32 GiB volume only 100.
# There is no separate data volume, deliberately: the database is Neon's, and encrypted dumps go to
# S3. See the bucket below and infra/scripts/backup-to-s3.sh.
ROOT_VOLUME_SIZE_GB="${ROOT_VOLUME_SIZE_GB:-32}"
ROOT_VOLUME_TYPE="${ROOT_VOLUME_TYPE:-gp3}"

SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519.pub}"
KEY_NAME="${KEY_NAME:-${INSTANCE_NAME}-key}"
SG_NAME="${SG_NAME:-${INSTANCE_NAME}-sg}"
IAM_ROLE_NAME="${IAM_ROLE_NAME:-${INSTANCE_NAME}-backup-role}"
IAM_PROFILE_NAME="${IAM_PROFILE_NAME:-${INSTANCE_NAME}-backup-profile}"

# Where backups land. S3 bucket names are globally unique across every AWS account on earth, 3-63
# characters, lowercase — hence the suffix, exactly as the Azure storage account name needed one.
#
# **Kept, deliberately, even though Neon has its own point-in-time restore.** The reasoning is at
# step 3 below and in docs/deploy/AWS.md § 6; the short version is that Neon's Free-plan history
# window is six hours, which is a rollback and not a backup, and that this bucket is the only copy
# of the data that survives losing the Neon account.
STORAGE_BUCKET="${STORAGE_BUCKET:-azmoth-backups-$(whoami | tr -cd 'a-z0-9' | cut -c1-6)}"

# The single address allowed to reach port 22. Detected, because the common mistake is to open SSH
# to the world "just for now" and never come back to it.
MY_IP="${MY_IP:-$(curl -fsS --max-time 10 https://api.ipify.org 2>/dev/null || true)}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31m !! %s\033[0m\n' "$*" >&2; exit 1; }

aws_() { aws --region "$REGION" "$@"; }

# ── Preconditions ─────────────────────────────────────────────────────────────────────────────

command -v aws >/dev/null || die "the AWS CLI is not installed.
   https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
   On Ubuntu:  sudo snap install aws-cli --classic"

aws sts get-caller-identity >/dev/null 2>&1 || die "not authenticated to AWS.
   Run:  aws configure          (or aws sso login, if your account uses IAM Identity Center)"

[ -f "$SSH_KEY" ] || die "no SSH public key at $SSH_KEY
   Generate one:  ssh-keygen -t ed25519 -C '$ADMIN_USER@azmoth'
   Or point SSH_KEY at an existing one."

# The public half, and only the public half. Pointing SSH_KEY at a private key by mistake would
# upload the private key to AWS as an authorized key — which works, and is a mistake nobody notices
# until they wonder why their private key is legible in a cloud console.
grep -q 'PRIVATE KEY' "$SSH_KEY" 2>/dev/null \
  && die "$SSH_KEY is a PRIVATE key. This wants the public half — normally the same path with .pub."

case "$REGION" in
  eu-*) : ;;
  *) die "REGION is '$REGION', which is not an EU region.
   docs/AVV_TECHNICAL_ANNEX_DRAFT.md § 5.1 states that processing happens exclusively on systems
   inside the European Union, and a practice signs that document. eu-central-1 (Frankfurt) is what
   the annex names and what the Neon project already uses.
   If you genuinely mean to provision outside the EU, change the annex first." ;;
esac

if [ -z "$MY_IP" ]; then
  # Refuse rather than default to 0.0.0.0/0. An SSH rule open to the internet is the single most
  # consequential thing this script could get wrong, and "the IP lookup failed" is not a reason to
  # make that decision on the operator's behalf.
  die "could not detect your public IP, and this script will not open SSH to the world.
   Pass it explicitly:  MY_IP=203.0.113.4 ./infra/aws/provision.sh"
fi

say "Account"
aws_ sts get-caller-identity --query '{account:Account, arn:Arn}' --output table

# ── The default VPC, which this script uses and does not create ───────────────────────────────
# An EC2 instance needs a subnet, and a subnet needs a VPC. Every AWS account gets a default VPC per
# region with a public subnet in each availability zone and an internet gateway already attached,
# which is exactly the topology a single public box wants.
#
# Using it rather than creating one is a deliberate limit on what this script owns. A custom VPC
# means a route table, an internet gateway, subnets in at least two AZs to keep future options open,
# and — the moment anything private appears — a NAT gateway at roughly EUR 33/month, which is more
# than the VM. That is architecture this deployment does not have and should not grow by accident.
say "Default VPC in $REGION"
VPC_ID="$(aws_ ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text 2>/dev/null || echo "None")"

[ "$VPC_ID" != "None" ] && [ -n "$VPC_ID" ] \
  || die "this account has no default VPC in $REGION.
   Recreate it — it is free, and it is the topology this script expects:
       aws ec2 create-default-vpc --region $REGION"

SUBNET_ID="$(aws_ ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" Name=default-for-az,Values=true \
  --query 'sort_by(Subnets, &AvailabilityZone)[0].SubnetId' --output text)"

[ "$SUBNET_ID" != "None" ] && [ -n "$SUBNET_ID" ] \
  || die "the default VPC $VPC_ID has no default subnet in $REGION."

echo "    vpc     $VPC_ID"
echo "    subnet  $SUBNET_ID"

# ── Which AMI, resolved now so it can be printed before anything is created ───────────────────
say "Resolving the current Ubuntu 22.04 LTS AMI"
AMI_ID="$(aws_ ssm get-parameters --names "$AMI_SSM_PARAMETER" \
  --query 'Parameters[0].Value' --output text 2>/dev/null || echo "None")"

[ "$AMI_ID" != "None" ] && [ -n "$AMI_ID" ] \
  || die "could not resolve an AMI from the SSM parameter:
       $AMI_SSM_PARAMETER
   That parameter is published by Canonical and is public, so this is normally a permissions
   problem: the caller needs ssm:GetParameters. List what is available with:
       aws ssm get-parameters-by-path --region $REGION \\
         --path /aws/service/canonical/ubuntu/server/22.04/stable/current --recursive"

echo "    $AMI_ID"

# The root device name is read off the AMI rather than assumed. Ubuntu uses /dev/sda1, Amazon Linux
# uses /dev/xvda, and a block device mapping naming a device the AMI does not have is silently
# ignored — which would produce an instance with the AMI's default 8 GiB root volume instead of 32.
ROOT_DEVICE="$(aws_ ec2 describe-images --image-ids "$AMI_ID" \
  --query 'Images[0].RootDeviceName' --output text)"
echo "    root device $ROOT_DEVICE"

cat <<SUMMARY

  region           $REGION            (EU — required by the AVV, see the header)
  vpc / subnet     $VPC_ID / $SUBNET_ID   (the account default, not created here)
  instance         $INSTANCE_NAME ($INSTANCE_TYPE, CPU credits: standard)
  image            $AMI_ID  (Ubuntu 22.04 LTS, resolved from SSM)
  root volume      ${ROOT_VOLUME_SIZE_GB} GiB $ROOT_VOLUME_TYPE, encrypted
  ssh key          $SSH_KEY  -> key pair '$KEY_NAME'
  ssh allowed from $MY_IP/32           (and nowhere else)
  s3 bucket        $STORAGE_BUCKET     (private, versioned, TLS-only)
  iam role         $IAM_ROLE_NAME      (s3:PutObject/GetObject on that bucket only)

  NOT created by this script, and both are required before deploying:
    - the Neon project (aws-eu-central-1) and its two connection strings
    - the Vercel project for azmoth.com  — already live; leave its DNS alone

SUMMARY

read -r -p "Create these resources? [y/N] " reply
[ "$reply" = "y" ] || [ "$reply" = "Y" ] || { echo "aborted"; exit 1; }

# ── 1. Key pair ───────────────────────────────────────────────────────────────────────────────
# Imported, not generated. `aws ec2 create-key-pair` makes a key on AWS's side and hands you the
# private half exactly once — which means the private key was generated somewhere other than the
# machine that will use it, and a copy of it existed in an API response. Importing the public half
# of a key you already have keeps the private half where it has always been.
#
# ed25519 is supported for imported EC2 key pairs on Linux instances, so the same
# ~/.ssh/id_ed25519.pub the Azure box used works unchanged.

say "1/7 key pair: $KEY_NAME"
if aws_ ec2 describe-key-pairs --key-names "$KEY_NAME" >/dev/null 2>&1; then
  # Not re-imported. AWS stores only a fingerprint, and replacing the key pair would not change the
  # authorized_keys of an instance that already exists — it would only make the console disagree
  # with the box. If the key really changed, edit ~/.ssh/authorized_keys over SSH.
  echo "    exists — leaving it alone"
else
  aws_ ec2 import-key-pair \
    --key-name "$KEY_NAME" \
    --public-key-material "fileb://$SSH_KEY" \
    --output none
  echo "    imported from $SSH_KEY"
fi

# ── 2. Security group ─────────────────────────────────────────────────────────────────────────
# Three inbound rules and no more. A security group is default-deny for ingress — anything not
# named here is closed because nothing opens it — so port 8000 needs no explicit deny. There is no
# such thing as a deny rule in a security group, which is worth knowing before you go looking for
# one: the Azure NSG had priorities and an implicit DenyAllInBound, this has neither.
#
# The default EGRESS rule (allow all) is left exactly as AWS creates it. That is what lets the
# engine reach Neon in Frankfurt over TLS on 5432 and lets Docker pull from ghcr.io. If you ever
# tighten it, those are the two flows to remember — a locked-down egress rule set is a stack that
# comes up healthy and cannot read a single proposal.
#
# This is the outer wall. infra/docker/docker-compose.azure.yml is the inner one — it unpublishes
# those ports from Docker as well, because a published Docker port writes its own iptables rules
# and is reachable even when the host firewall thinks otherwise. (That file's name says azure and
# its content is about not publishing ports; it is unchanged and correct on either provider.)

say "2/7 security group: $SG_NAME"
SG_ID="$(aws_ ec2 describe-security-groups \
  --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")"

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  SG_ID="$(aws_ ec2 create-security-group \
    --group-name "$SG_NAME" \
    --description "Azmoth: SSH from the operator only, HTTP and HTTPS from anywhere" \
    --vpc-id "$VPC_ID" \
    --query GroupId --output text)"
  echo "    created $SG_ID"
else
  echo "    exists $SG_ID"
fi

# HTTP and HTTPS from anywhere. Idempotent by catching the duplicate rather than by asking first:
# AWS answers InvalidPermission.Duplicate, which is the same information a lookup would have given
# and one API call instead of two.
#
# 80 is not optional and not a weakening: Let's Encrypt's HTTP-01 challenge arrives here, and Caddy
# serves the redirect to 443 from it. Closing 80 does not add security, it stops TLS from working.
open_port() {
  local port="$1" description="$2"
  if aws_ ec2 authorize-security-group-ingress \
       --group-id "$SG_ID" \
       --ip-permissions "IpProtocol=tcp,FromPort=$port,ToPort=$port,IpRanges=[{CidrIp=0.0.0.0/0,Description=\"$description\"}]" \
       --output none 2>/dev/null; then
    echo "    $port opened to the world ($description)"
  else
    echo "    $port already open to the world"
  fi
}

open_port 80  "HTTP - ACME HTTP-01 challenge and the redirect to HTTPS"
open_port 443 "HTTPS - Caddy terminates TLS here"

# ── SSH, from one address, updated on every run ───────────────────────────────────────────────
# Revoked and re-added rather than skipped, because MY_IP changes when the operator's ISP
# reassigns it and a rerun is how this rule is meant to be corrected. That is the same behaviour as
# the Azure script's `nsg rule update`, which needs a loop here because a security group holds a
# LIST of CIDRs on one rule rather than one rule per source.
#
# Every 22/tcp CIDR that is not the current address is removed. An operator who deliberately added
# a second address — a colleague, an office range — will find it gone after a rerun, and that is
# the intended trade: an SSH allowlist that accumulates entries nobody remembers adding is how a
# stale address stays authorised for a year.
echo "    ssh: allowing $MY_IP/32 and revoking everything else on 22"
# shellcheck disable=SC2016  # the backticks are JMESPath literal syntax, not a shell substitution
existing_ssh_cidrs="$(aws_ ec2 describe-security-groups --group-ids "$SG_ID" \
  --query 'SecurityGroups[0].IpPermissions[?FromPort==`22`].IpRanges[].CidrIp' \
  --output text 2>/dev/null | tr '\t' '\n' | grep -v '^$' || true)"

for cidr in $existing_ssh_cidrs; do
  [ "$cidr" = "$MY_IP/32" ] && continue
  aws_ ec2 revoke-security-group-ingress \
    --group-id "$SG_ID" \
    --ip-permissions "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=$cidr}]" \
    --output none 2>/dev/null \
    && echo "      revoked $cidr"
done

if aws_ ec2 authorize-security-group-ingress \
     --group-id "$SG_ID" \
     --ip-permissions "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=$MY_IP/32,Description=\"SSH from the operator address only\"}]" \
     --output none 2>/dev/null; then
  echo "      authorised $MY_IP/32"
else
  echo "      $MY_IP/32 was already authorised"
fi

echo
echo "    inbound rules now:"
aws_ ec2 describe-security-groups --group-ids "$SG_ID" \
  --query 'SecurityGroups[0].IpPermissions[].{port:FromPort, protocol:IpProtocol, source:IpRanges[0].CidrIp}' \
  --output table

# ── 3. S3 bucket for backups ──────────────────────────────────────────────────────────────────
# Small, cheap, and in the same region for the same AVV reason as the instance. A dump is a complete
# copy of every approval and audit event, so the bucket blocks all public access, refuses plain HTTP
# by policy, and keeps versions. infra/scripts/backup-to-s3.sh encrypts before upload on top of all
# of that.
#
# ── Why this survives the move to Neon ────────────────────────────────────────────────────────
# Neon has native point-in-time restore, so the obvious move was to delete this bucket and the
# instance profile with it. It was costed at about EUR 0.10/month for a pilot's worth of dumps, and
# kept, for three reasons that are worth naming because "the managed database has backups" is the
# argument that usually wins:
#
#   1. **Neon's Free-plan history window is six hours, capped at 1 GB.** That is a rollback, not a
#      backup. Launch extends it to seven days for usage-based cents — worth doing — but seven days
#      is still not an archive for records a practice is legally obliged to be able to produce.
#
#   2. **It is the only copy that survives losing the Neon account.** Every Neon mechanism —
#      instant restore, snapshots, branches — lives inside the Neon project. A billing lapse, a
#      deleted project, a compromised Neon login, or Neon's own note that Free-plan projects
#      inactive for 90 days "are subject to deletion" all take the database and its backups
#      together. docs/OPERATIONS.md § 2 has always required dumps to be kept off the same host as
#      the database; a managed provider is a host.
#
#      Note that this is now a copy inside the same PROVIDER as the database — Neon runs on AWS —
#      which it was not on Azure. It is still a different account, a different service and a
#      different credential, which is what the requirement is actually about. If that is not enough
#      for a given practice, the answer is a second copy somewhere else entirely, not moving the VM.
#
#   3. **It also holds the things that are not in the database.** An encrypted copy of
#      /opt/azmoth/shared/.env — which contains the Neon connection strings, without which the dumps
#      are just files — and nothing else on this box is backed up at all.

say "3/7 S3 bucket for backups: $STORAGE_BUCKET"
if aws_ s3api head-bucket --bucket "$STORAGE_BUCKET" >/dev/null 2>&1; then
  echo "    exists"
else
  # LocationConstraint is required for every region except us-east-1, and omitting it there is what
  # silently creates a bucket in Virginia. This script refuses non-EU regions above, so it is always
  # passed.
  aws_ s3api create-bucket \
    --bucket "$STORAGE_BUCKET" \
    --create-bucket-configuration "LocationConstraint=$REGION" \
    --output none \
    || die "could not create the bucket '$STORAGE_BUCKET'.
   S3 bucket names are globally unique across every AWS account, so 'BucketAlreadyExists' means
   somebody else has it — pick another:
       STORAGE_BUCKET=azmoth-backups-praxisnord ./infra/aws/provision.sh
   'BucketAlreadyOwnedByYou' means it is yours in ANOTHER region, which would put clinical data
   outside the region the AVV names. Delete it or choose a new name."
  echo "    created in $REGION"
fi

# Applied on every run, not only at creation. These four settings are the difference between a
# private bucket and a public one, and a bucket that already existed — created by hand, or by an
# earlier version of this script — is exactly the one whose settings nobody has checked.
aws_ s3api put-public-access-block \
  --bucket "$STORAGE_BUCKET" \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" \
  --output none
echo "    public access: blocked (all four settings)"

# Versioning, which is doing a specific job here rather than being a default best practice: the
# instance profile below grants PutObject, and PutObject on an existing key overwrites it. With
# versioning on, an overwrite — accidental, or by something that got onto the box — creates a new
# version and leaves the old one retrievable. Combined with no s3:DeleteObject in the policy, a
# compromised VM cannot destroy a backup it already wrote.
aws_ s3api put-bucket-versioning \
  --bucket "$STORAGE_BUCKET" \
  --versioning-configuration Status=Enabled \
  --output none
echo "    versioning: enabled"

# Server-side encryption at rest with S3-managed keys. On by default for new buckets since January
# 2023, and stated anyway because this bucket may predate that or may have been made by hand — and
# because "encrypted at rest" is a sentence that appears in the AVV.
#
# SSE-S3 rather than SSE-KMS: a customer-managed KMS key would add a per-request charge and a second
# thing to grant the instance profile, to protect against a threat that age already covers. The real
# protection here is that the dump is encrypted BEFORE it leaves the VM, to a public key whose
# private half is not on AWS at all. See infra/scripts/backup-to-s3.sh.
aws_ s3api put-bucket-encryption \
  --bucket "$STORAGE_BUCKET" \
  --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}' \
  --output none
echo "    encryption at rest: SSE-S3 (AES256)"

# TLS-only, as a bucket policy. `aws:SecureTransport` is false for plain HTTP, and this denies
# everything in that case — including to the instance profile and to you. It is the S3 equivalent of
# the Azure storage account's `--https-only true`.
tls_policy="$(mktemp)"
trap 'rm -f "$tls_policy"' EXIT
cat > "$tls_policy" <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyUnencryptedTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::$STORAGE_BUCKET",
        "arn:aws:s3:::$STORAGE_BUCKET/*"
      ],
      "Condition": { "Bool": { "aws:SecureTransport": "false" } }
    }
  ]
}
POLICY

aws_ s3api put-bucket-policy --bucket "$STORAGE_BUCKET" --policy "file://$tls_policy" --output none
echo "    bucket policy: plain HTTP denied"

# ── 4. The instance's identity, so no AWS key is ever written to the box ──────────────────────
# An IAM role assumed by the instance through an instance profile, granting s3:PutObject and
# s3:GetObject on THIS BUCKET'S OBJECTS and nothing else. The backup job then calls `aws s3 cp` with
# no credentials configured at all: the SDK reads a short-lived, automatically rotated set from the
# instance metadata service. This is the direct equivalent of the Azure system-assigned managed
# identity, and it is here for the same reason.
#
# The alternative is an access key pair in ~/.aws/credentials on the VM, and the difference matters:
# an access key is a long-lived credential, it would sit next to the very dumps it protects, and
# rotating it means finding every copy. The role cannot be read off the disk, its credentials expire
# by themselves, and it is revoked by detaching one policy.
#
# ── What is deliberately NOT in this policy ───────────────────────────────────────────────────
#   s3:DeleteObject      — a compromised VM must not be able to destroy the backups it wrote.
#                          Retention is a bucket lifecycle rule, set by you, not by the box.
#   s3:ListBucket        — the box has no reason to enumerate what is in there. `aws s3 cp` to a
#                          known key does not need it. You list from your laptop, with your own
#                          credentials. (A consequence worth knowing: `aws s3 ls` ON the VM will
#                          answer AccessDenied. That is this line, working.)
#   s3:PutBucketPolicy,  — the bucket-level settings above are what keep this private. An
#   s3:PutBucketAcl        account-level or bucket-level grant would let a compromised VM make a
#                          bucket of clinical records public, which is the failure this whole
#                          arrangement exists to prevent.

say "4/7 IAM role and instance profile: $IAM_ROLE_NAME"
# IAM is a GLOBAL service. The role and the instance profile below are not in eu-central-1 and
# cannot be — there is no such thing as a regional IAM role. Nothing they can reach is outside the
# region: the only resource named in the policy is the Frankfurt bucket.
trust_policy="$(mktemp)"
inline_policy="$(mktemp)"
trap 'rm -f "$tls_policy" "$trust_policy" "$inline_policy"' EXIT

cat > "$trust_policy" <<'TRUST'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ec2.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
TRUST

cat > "$inline_policy" <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "WriteAndReadBackupObjects",
      "Effect": "Allow",
      "Action": [ "s3:PutObject", "s3:GetObject" ],
      "Resource": "arn:aws:s3:::$STORAGE_BUCKET/*"
    }
  ]
}
POLICY

if aws iam get-role --role-name "$IAM_ROLE_NAME" >/dev/null 2>&1; then
  echo "    role exists"
else
  aws iam create-role \
    --role-name "$IAM_ROLE_NAME" \
    --assume-role-policy-document "file://$trust_policy" \
    --description "Azmoth: lets the pilot VM write encrypted database dumps to $STORAGE_BUCKET" \
    --output none
  echo "    role created"
fi

# Put rather than create: an inline policy of the same name is replaced, so a rerun after the bucket
# name changed corrects the resource ARN instead of leaving a policy pointing at a bucket that is
# no longer the backup target.
aws iam put-role-policy \
  --role-name "$IAM_ROLE_NAME" \
  --policy-name "s3-backup-write" \
  --policy-document "file://$inline_policy" \
  --output none
echo "    policy: s3:PutObject, s3:GetObject on $STORAGE_BUCKET/* — and nothing else"

if aws iam get-instance-profile --instance-profile-name "$IAM_PROFILE_NAME" >/dev/null 2>&1; then
  echo "    instance profile exists"
else
  aws iam create-instance-profile --instance-profile-name "$IAM_PROFILE_NAME" --output none
  echo "    instance profile created"
fi

# An instance profile holds at most one role, and adding a role to a profile that already has one
# fails rather than replacing it. So this is asked rather than attempted.
profile_role="$(aws iam get-instance-profile --instance-profile-name "$IAM_PROFILE_NAME" \
  --query 'InstanceProfile.Roles[0].RoleName' --output text 2>/dev/null || echo "None")"

if [ "$profile_role" = "$IAM_ROLE_NAME" ]; then
  echo "    role already in the profile"
elif [ "$profile_role" = "None" ] || [ -z "$profile_role" ]; then
  aws iam add-role-to-instance-profile \
    --instance-profile-name "$IAM_PROFILE_NAME" \
    --role-name "$IAM_ROLE_NAME" \
    --output none
  echo "    role added to the profile"
else
  die "the instance profile '$IAM_PROFILE_NAME' already holds a different role: $profile_role
   An instance profile holds one role. Either that profile belongs to something else — pick another
   name with IAM_PROFILE_NAME= — or detach the old role deliberately:
       aws iam remove-role-from-instance-profile \\
         --instance-profile-name $IAM_PROFILE_NAME --role-name $profile_role"
fi

# ── 5. The instance ───────────────────────────────────────────────────────────────────────────
# Password authentication is off because the Ubuntu AMI ships with it off and no password is set —
# there is nothing to authenticate with but the key pair imported at step 1.
#
# ── IMDSv2 only, and this is not a formality ──────────────────────────────────────────────────
# `HttpTokens=required` makes the instance metadata service refuse the old unauthenticated GET and
# demand a PUT-issued session token first. The reason is specific: the metadata endpoint is where
# the role's credentials come from, and IMDSv1 could be reached by any server-side request forgery
# in anything running on the box — a URL fetcher handed `http://169.254.169.254/...` would hand back
# a working credential. IMDSv2 requires a PUT with a header, which a naive proxied GET cannot make.
#
# `HttpPutResponseHopLimit=1` keeps the token from surviving a hop into a Docker bridge network, so
# a container cannot reach the metadata service at all. The backup job runs `aws` on the HOST, so
# this costs nothing; if you ever need an AWS SDK inside a container here, that is a decision to
# make deliberately rather than a limit to raise in passing.

say "5/7 instance: $INSTANCE_NAME"
INSTANCE_ID="$(aws_ ec2 describe-instances \
  --filters "Name=tag:Name,Values=$INSTANCE_NAME" \
            "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text 2>/dev/null || echo "None")"

if [ "$INSTANCE_ID" != "None" ] && [ -n "$INSTANCE_ID" ]; then
  echo "    exists — leaving it alone ($INSTANCE_ID)"
else
  # ── First-boot configuration ────────────────────────────────────────────────────────────────
  # cloud-init runs this once, on the first boot, and never again. Everything in it is therefore
  # also checked or reapplied by step 7 below over SSH, so that a rerun of this script still
  # converges on a box that was created before some of it existed.
  #
  # It does two things:
  #
  #   1. Creates the ADMIN_USER. The Ubuntu AMI's default login is `ubuntu`; scripts/deploy.sh
  #      defaults to `azmoth`, which is what the Azure box had. Creating the user here means
  #      deploy.sh and the runbook are identical on both providers rather than differing by a flag
  #      somebody has to remember.
  #
  #   2. The swapfile. 4 GiB on a 2 GiB machine. Nothing is built here, so this is runtime
  #      insurance: a Soufflé solve forks a process whose peak nobody has characterised, and the
  #      failure mode without swap is the OOM killer choosing a victim — which on this box means the
  #      `web` container disappearing while somebody was mid-approval.
  #
  #      Swap is not a substitute for RAM. If `free -m` shows swap in steady use rather than touched
  #      at peaks, the machine is too small — take t3.medium rather than adding more swap.
  user_data="$(mktemp)"
  trap 'rm -f "$tls_policy" "$trust_policy" "$inline_policy" "$user_data"' EXIT

  cat > "$user_data" <<USERDATA
#!/bin/bash
set -eux

# 1. the deploy user, with the same key the operator just imported
if ! id -u "$ADMIN_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$ADMIN_USER"
fi
usermod -aG sudo "$ADMIN_USER"
install -d -m 700 -o "$ADMIN_USER" -g "$ADMIN_USER" "/home/$ADMIN_USER/.ssh"
install -m 600 -o "$ADMIN_USER" -g "$ADMIN_USER" \\
  /home/ubuntu/.ssh/authorized_keys "/home/$ADMIN_USER/.ssh/authorized_keys"
printf '%s ALL=(ALL) NOPASSWD:ALL\\n' "$ADMIN_USER" > /etc/sudoers.d/90-azmoth
chmod 440 /etc/sudoers.d/90-azmoth

# 2. swap
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
# 10 rather than the default 60: prefer to keep the engine and web pages resident and use swap for
# a solver spike, not for steady-state paging.
sysctl -w vm.swappiness=10
grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
USERDATA

  INSTANCE_ID="$(aws_ ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --subnet-id "$SUBNET_ID" \
    --security-group-ids "$SG_ID" \
    --associate-public-ip-address \
    --iam-instance-profile "Name=$IAM_PROFILE_NAME" \
    --credit-specification "CpuCredits=standard" \
    --metadata-options "HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1" \
    --block-device-mappings "[{\"DeviceName\":\"$ROOT_DEVICE\",\"Ebs\":{\"VolumeSize\":$ROOT_VOLUME_SIZE_GB,\"VolumeType\":\"$ROOT_VOLUME_TYPE\",\"Encrypted\":true,\"DeleteOnTermination\":true}}]" \
    --user-data "file://$user_data" \
    --tag-specifications \
      "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME},{Key=Project,Value=azmoth}]" \
      "ResourceType=volume,Tags=[{Key=Name,Value=$INSTANCE_NAME-root},{Key=Project,Value=azmoth}]" \
    --query 'Instances[0].InstanceId' --output text)" \
    || die "run-instances failed.
   If it says 'Invalid IAM Instance Profile name', IAM has not finished propagating the profile
   created a moment ago — wait ten seconds and run this script again, which is what idempotence is
   for. If it says 'InsufficientInstanceCapacity' or 'VcpuLimitExceeded', take the other rung:
       INSTANCE_TYPE=t3.medium ./infra/aws/provision.sh"

  echo "    created $INSTANCE_ID"
  echo "    waiting for it to reach 'running'..."
  aws_ ec2 wait instance-running --instance-ids "$INSTANCE_ID"
  echo "    running"
fi

# ── 6. Elastic IP ─────────────────────────────────────────────────────────────────────────────
# The address an instance gets by default is released when it stops and comes back different, which
# breaks the DNS records the certificates depend on. An Elastic IP is the fixed one.
#
# It is not free and it is not optional: since 1 February 2024 AWS bills every public IPv4 address,
# in use or not, at roughly EUR 3.35/month. The instance needs a public address to serve on and DNS
# needs one that does not move, so this is a line item rather than a choice. The one thing worth
# remembering is the other half of that pricing change — an Elastic IP that is allocated and NOT
# associated with anything is billed at the same rate, so a torn-down pilot that left one behind
# goes on costing money. `aws ec2 release-address` is the end of the teardown.
#
# Found by tag rather than by address, because the address is what we are trying to learn.

say "6/7 Elastic IP"
ALLOCATION_ID="$(aws_ ec2 describe-addresses \
  --filters "Name=tag:Name,Values=$INSTANCE_NAME-eip" \
  --query 'Addresses[0].AllocationId' --output text 2>/dev/null || echo "None")"

if [ "$ALLOCATION_ID" = "None" ] || [ -z "$ALLOCATION_ID" ]; then
  ALLOCATION_ID="$(aws_ ec2 allocate-address \
    --domain vpc \
    --tag-specifications \
      "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$INSTANCE_NAME-eip},{Key=Project,Value=azmoth}]" \
    --query AllocationId --output text)"
  echo "    allocated $ALLOCATION_ID"
else
  echo "    exists $ALLOCATION_ID"
fi

associated_to="$(aws_ ec2 describe-addresses --allocation-ids "$ALLOCATION_ID" \
  --query 'Addresses[0].InstanceId' --output text 2>/dev/null || echo "None")"

if [ "$associated_to" = "$INSTANCE_ID" ]; then
  echo "    already associated with $INSTANCE_ID"
else
  # Association is idempotent in effect: re-associating the same address with the same instance is
  # accepted and re-associating it with a DIFFERENT instance moves it, which is what a rebuilt box
  # needs. `--allow-reassociation` is what permits the second case.
  aws_ ec2 associate-address \
    --allocation-id "$ALLOCATION_ID" \
    --instance-id "$INSTANCE_ID" \
    --allow-reassociation \
    --output none
  echo "    associated with $INSTANCE_ID"
fi

PUBLIC_IP="$(aws_ ec2 describe-addresses --allocation-ids "$ALLOCATION_ID" \
  --query 'Addresses[0].PublicIp' --output text)"
echo "    address: $PUBLIC_IP"

# ── 7. Swap, verified rather than assumed ─────────────────────────────────────────────────────
# The swapfile and the deploy user are configured by cloud-init on the FIRST boot, and cloud-init
# does not run again. So this step checks over SSH and applies them if they are missing, which is
# what makes a rerun of this script converge on an instance that already existed.
#
# Over SSH rather than through SSM Run Command, which would be the closer analogue of the Azure
# script's `vm run-command invoke`. SSM needs the AmazonSSMManagedInstanceCore managed policy on the
# instance role — a policy that grants far more than "write objects to one bucket", on the box
# holding the clinical data. Keeping the role at two S3 actions is worth reaching for the SSH key
# this script already required.
#
# Not fatal if it cannot connect. A freshly created instance takes a minute or two before sshd
# answers, and cloud-init has already done the work — the honest report is "could not check yet".

say "7/7 swap and the '$ADMIN_USER' user"
SSH_OPTS=(-o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -o BatchMode=yes)

ssh_user=""
for candidate in "$ADMIN_USER" ubuntu; do
  if ssh "${SSH_OPTS[@]}" "$candidate@$PUBLIC_IP" true 2>/dev/null; then
    ssh_user="$candidate"
    break
  fi
done

if [ -z "$ssh_user" ]; then
  echo "    not reachable over SSH yet — a new instance takes a minute or two to boot."
  echo "    cloud-init configures both on first boot. Re-run this script to verify:"
  echo "      ./infra/aws/provision.sh"
elif [ "$ssh_user" = "ubuntu" ]; then
  echo "    !! reachable as 'ubuntu' but not as '$ADMIN_USER' — cloud-init has not finished, or"
  echo "       this instance predates the user being created. Fixing it over SSH:"
  # shellcheck disable=SC2029  # ADMIN_USER is meant to expand HERE — it is this script's setting,
  # not the remote box's, and the remote heredoc is quoted so nothing else does.
  ssh "${SSH_OPTS[@]}" "ubuntu@$PUBLIC_IP" "ADMIN_USER='$ADMIN_USER' bash -s" <<'FIXUSER'
set -euo pipefail
if ! id -u "$ADMIN_USER" >/dev/null 2>&1; then
  sudo useradd --create-home --shell /bin/bash "$ADMIN_USER"
fi
sudo usermod -aG sudo "$ADMIN_USER"
sudo install -d -m 700 -o "$ADMIN_USER" -g "$ADMIN_USER" "/home/$ADMIN_USER/.ssh"
sudo install -m 600 -o "$ADMIN_USER" -g "$ADMIN_USER" \
  /home/ubuntu/.ssh/authorized_keys "/home/$ADMIN_USER/.ssh/authorized_keys"
printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$ADMIN_USER" | sudo tee /etc/sudoers.d/90-azmoth >/dev/null
sudo chmod 440 /etc/sudoers.d/90-azmoth
echo "    $ADMIN_USER created"
FIXUSER
fi

if [ -n "$ssh_user" ]; then
  ssh "${SSH_OPTS[@]}" "$ssh_user@$PUBLIC_IP" bash -s <<'SWAP'
set -euo pipefail
if [ -f /swapfile ] && swapon --show=NAME --noheadings | grep -qx /swapfile; then
  echo "    swapfile present and active ($(free -m | awk '/Swap:/ {print $2}') MiB)"
else
  sudo fallocate -l 4G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  echo "    swapfile created and enabled"
fi
sudo sysctl -w vm.swappiness=10 >/dev/null
grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf >/dev/null
echo "    vm.swappiness=$(cat /proc/sys/vm/swappiness)"
SWAP
fi

# ── Done ──────────────────────────────────────────────────────────────────────────────────────

cat <<DONE

────────────────────────────────────────────────────────────────────────────────
  Public IP:   $PUBLIC_IP
  SSH:         ssh $ADMIN_USER@$PUBLIC_IP
  Instance:    $INSTANCE_ID ($INSTANCE_TYPE) in $REGION
  Backups to:  s3://$STORAGE_BUCKET   (private, versioned, TLS-only)

  NEXT — point DNS at that address and WAIT for it to resolve. Caddy gets its
  certificates over HTTP-01, which means Let's Encrypt fetches a token from
  these names over port 80. A name that does not resolve yet is a failed
  issuance and a retry backoff, not a warning.

  TWO records. That is the whole list:

      A   app.azmoth.com    $PUBLIC_IP
      A   api.azmoth.com    $PUBLIC_IP

  ** DO NOT point azmoth.com or www.azmoth.com here. **
  They are served by Vercel and are live. This box has no marketing container
  and its Caddyfile has no site block for those names, so moving their A
  records would take the public site down and Caddy would then request a
  certificate for a name Vercel already holds. Leave them on Vercel.

  Check with:  dig +short app.azmoth.com
               dig +short azmoth.com          # must NOT be $PUBLIC_IP

  BEFORE DEPLOYING you also need a Neon project and both of its connection
  strings — the direct one and the pooled one. docs/deploy/RUNBOOK.md § 3 is
  the five-minute version; deploy.sh refuses to start without them.

  THEN:        ./scripts/deploy.sh $PUBLIC_IP

  AFTER THAT, to finish the backup job, add these to /opt/azmoth/shared/.env
  on the box — it refuses to run without both, deliberately:

      STORAGE_BUCKET=$STORAGE_BUCKET
      AGE_RECIPIENT=age1...        # the PUBLIC half of a keypair you generate
                                   # on your LAPTOP: age-keygen -o azmoth-backup.key
────────────────────────────────────────────────────────────────────────────────

DONE
