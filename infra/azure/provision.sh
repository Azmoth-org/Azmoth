#!/usr/bin/env bash
#
# Provision the single VM Azmoth runs on, and nothing else.
#
#     ./infra/azure/provision.sh
#
# Idempotent: every step checks whether the resource exists before creating it, so a run that fails
# halfway through — a quota refusal, a dropped connection — is fixed by running it again rather than
# by working out which half happened. It creates no managed database, no container service and no
# load balancer; the whole stack is Docker Compose on one box, which is what makes 100 EUR of credit
# last a pilot rather than a fortnight.
#
# It prints the public IP at the end. Point DNS at it before running scripts/deploy.sh, because
# Caddy gets its certificates over HTTP-01 and that requires the names to already resolve here.
#
# ── What this costs, and why these sizes ──────────────────────────────────────────────────────
# About EUR 20/month at pay-as-you-go in germanywestcentral, so ~4.9 months on a 100 EUR credit:
#
#     Standard_B1ms  1 vCPU, 2 GiB      ~EUR 15.04/mo
#     32 GiB StandardSSD (E4)           ~EUR  2.06/mo
#     Standard static IPv4              ~EUR  3.14/mo  (Azure bills IPv4 addresses)
#     Blob Storage, Cool, a few GB      ~EUR  0.05/mo
#     Egress                            ~EUR  0.00/mo  (first 100 GB/month is free)
#
# Those figures came from the Azure Retail Prices API in EUR for this region and they move. Check
# yours before committing:
#     az vm list-skus --location "$LOCATION" --size Standard_B1 --output table
#     https://azure.microsoft.com/pricing/calculator/
#
# **2 GiB is enough because this box no longer BUILDS anything.** Images are built by
# .github/workflows/release-images.yml on a GitHub runner and pulled from ghcr.io; see the header of
# infra/docker/docker-compose.azure.yml. That is what took the VM from B2s (4 GiB, EUR 30, 2.9
# months all-in) to B1ms, and it is the only reason a 100 EUR credit reaches four months.
#
# It is enough to RUN on, with room to spare rather than to burn. Postgres left the box (it is
# Neon's now) and so did the marketing site (Vercel's), which leaves caddy + engine + web at
# roughly 500-800 MiB resting, plus ~250 MiB for dockerd and the OS. The 4 GiB swapfile below is
# now insurance for a Soufflé solve that spikes, not a crutch for a build.
#
# 1 GiB was costed and rejected: Standard_B2ats_v2 is EUR 6.79/mo and would stretch the credit to
# eight months, but the resting stack does not fit in it, so the engine would page during exactly
# the solves the product exists to run.
#
# ── The size may not allocate, and there is a ladder for that ─────────────────────────────────
# B-series **v1** — B1s, B1ms, B2s, B1ls — retires 15 November 2028, and since 31 July 2026 has
# been under a growth restriction: new deployments, quota increases and any operation needing a
# fresh allocation "can fail", and availability "has already been restricted or removed in many
# regions, particularly for new deployments and newly created subscriptions". Whether
# germanywestcentral is affected is not documented either way.
#
# So if `az vm create` refuses this size, do not fight it — take the next rung and accept the
# shorter runway. Bsv2/Basv2 are the designated replacements and are not retiring:
#
#     VM_SIZE=Standard_B1ms      1 vCPU / 2 GiB   EUR 15.04   ~4.9 months   (default)
#     VM_SIZE=Standard_B2als_v2  2 vCPU / 4 GiB   EUR 27.08   ~3.1 months   AMD, not retiring
#     VM_SIZE=Standard_B2s       2 vCPU / 4 GiB   EUR 30.08   ~2.9 months   v1, retiring
#
# **Not Arm, however tempting the price is.** Standard_B2pls_v2 is 2 vCPU / 4 GiB for EUR 24.09 —
# cheaper than any x86 4 GiB SKU — and cannot run this stack: apps/engine/Dockerfile installs
# `x86_64-ubuntu-2204-souffle-2.5-Linux.deb`, and the engine is nothing without Soufflé. Moving to
# Arm is a new Soufflé build and a multi-arch image, not a VM_SIZE change.
#
# ── Region ────────────────────────────────────────────────────────────────────────────────────
# germanywestcentral, and this is a compliance constraint rather than a latency preference.
# docs/AVV_TECHNICAL_ANNEX_DRAFT.md section 5.1 states that processing happens exclusively on
# systems inside the EU. Frankfurt satisfies that. Do not move this to eastus to save a euro.
#
# The database is in Frankfurt too, but not here and not Microsoft's: Neon has no Azure region any
# more (azure-gwc stopped accepting new projects on 7 April 2026), so the Neon project lives in
# aws-eu-central-1 — AWS Europe, Frankfurt. Same city, same union, different provider.
#
# NOTE: deploying at all makes section 5.2 of that annex ("Unterauftragsverarbeiter: derzeit
# keine") untrue, now in four ways — Microsoft Azure (this VM), Neon/Databricks and AWS (the
# database), and Vercel (the public site). That document has to name all of them before a practice
# signs it. See docs/deploy/AZURE.md § 4.

set -euo pipefail

# ── Settings ──────────────────────────────────────────────────────────────────────────────────
# Override any of these from the environment:  VM_SIZE=Standard_B2als_v2 ./infra/azure/provision.sh

RG="${RG:-azmoth-pilot}"
LOCATION="${LOCATION:-germanywestcentral}"
VM_NAME="${VM_NAME:-azmoth-vm}"
VM_SIZE="${VM_SIZE:-Standard_B1ms}"
ADMIN_USER="${ADMIN_USER:-azmoth}"

# Ubuntu 22.04 LTS, gen2, pinned by full URN rather than by the `Ubuntu2204` alias. An alias is
# resolved by whatever version of the CLI you happen to have; this is the same image every time.
IMAGE="${IMAGE:-Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest}"

# 32 GiB StandardSSD, down from 64 because there is no build cache on this box any more. What has
# to fit is: Ubuntu, Docker, and three pulled images (engine ~300 MB, web ~350 MB, the web `builder`
# image ~1 GB, caddy ~50 MB) — under 2 GiB of images, plus the `azmoth-engine-uploads` volume
# holding bulk deliveries that have been accepted and not yet audited. 32 GiB is roughly ten times
# what is needed, which is the right margin for a disk whose size cannot be reduced later.
#
# StandardSSD rather than Premium because a pilot's write rate does not need provisioned IOPS, and
# rather than Standard HDD because container start latency on spinning rust is miserable — and it
# is barely cheaper (E4 32 GiB is EUR 2.06/mo against S6 64 GiB at EUR 2.58).
#
# Note that disks bill on the PROVISIONED size tier, not on bytes used, and keep billing while the
# VM is deallocated. Going from E6 (64 GiB) to E4 (32 GiB) is therefore a real EUR 2.06/month, or
# about five days of runway.
#
# There is no separate data disk, deliberately, and now there is even less reason for one: the
# database is Neon's. Encrypted dumps go to Blob Storage — see the storage account below and
# infra/scripts/backup-to-azure.sh.
OS_DISK_SIZE_GB="${OS_DISK_SIZE_GB:-32}"
OS_DISK_SKU="${OS_DISK_SKU:-StandardSSD_LRS}"

SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519.pub}"

IP_NAME="${IP_NAME:-${VM_NAME}-ip}"
NSG_NAME="${NSG_NAME:-${VM_NAME}-nsg}"
VNET_NAME="${VNET_NAME:-${VM_NAME}-vnet}"
SUBNET_NAME="${SUBNET_NAME:-${VM_NAME}-subnet}"

# Where backups land. Storage account names are globally unique, 3-24 chars, lowercase alphanumeric
# only — hence the suffix.
#
# **Kept, deliberately, even though Neon has its own point-in-time restore.** The reasoning is in
# step 7 below and in docs/deploy/AZURE.md § 6; the short version is that Neon's Free-plan history
# window is six hours, which is a rollback and not a backup, and that this container is the only
# copy of the data that survives losing the Neon account.
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-azmothbackup$(whoami | tr -cd 'a-z0-9' | cut -c1-6)}"
BACKUP_CONTAINER="${BACKUP_CONTAINER:-db-backups}"

# The single address allowed to reach port 22. Detected, because the common mistake is to open SSH
# to the world "just for now" and never come back to it.
MY_IP="${MY_IP:-$(curl -fsS --max-time 10 https://api.ipify.org 2>/dev/null || true)}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
have() { az "$@" >/dev/null 2>&1; }

# ── Preconditions ─────────────────────────────────────────────────────────────────────────────

command -v az >/dev/null || {
  echo "!! the Azure CLI is not installed — https://learn.microsoft.com/cli/azure/install-azure-cli" >&2
  exit 1
}

az account show >/dev/null 2>&1 || {
  echo "!! not logged in. Run: az login" >&2
  exit 1
}

[ -f "$SSH_KEY" ] || {
  echo "!! no SSH public key at $SSH_KEY" >&2
  echo "   Generate one:  ssh-keygen -t ed25519 -C '$ADMIN_USER@azmoth'" >&2
  echo "   Or point SSH_KEY at an existing one." >&2
  exit 1
}

if [ -z "$MY_IP" ]; then
  # Refuse rather than default to 0.0.0.0/0. An SSH rule open to the internet is the single most
  # consequential thing this script could get wrong, and "the IP lookup failed" is not a reason to
  # make that decision on the operator's behalf.
  echo "!! could not detect your public IP, and this script will not open SSH to the world." >&2
  echo "   Pass it explicitly:  MY_IP=203.0.113.4 ./infra/azure/provision.sh" >&2
  exit 1
fi

say "Subscription"
az account show --query '{name:name, id:id}' --output table

# ── Is the requested size actually allocatable here? ──────────────────────────────────────────
# Asked before anything is created, because the answer changed under this script's feet. B-series
# v1 has been growth-restricted since 31 July 2026 (see the header), and the failure without this
# check lands at step 5 — after the IP, NSG and VNet exist — as a SkuNotAvailable that reads like a
# transient capacity problem rather than a retirement.
#
# A warning rather than a refusal: `restrictions` reports zone-level exclusions too, which do not
# stop a size being used in the region, and a false stop here would be worse than a false warning.
say "Checking $VM_SIZE is available in $LOCATION"
SIZE_RESTRICTIONS="$(az vm list-skus --location "$LOCATION" --size "$VM_SIZE" \
  --query "[?name=='$VM_SIZE'].restrictions[].reasonCode" --output tsv 2>/dev/null || true)"

if ! az vm list-skus --location "$LOCATION" --size "$VM_SIZE" \
     --query "[?name=='$VM_SIZE'].name" --output tsv 2>/dev/null | grep -qx "$VM_SIZE"; then
  echo "    !! $VM_SIZE is not offered in $LOCATION at all." >&2
  echo "       Take the next rung of the ladder in this script's header:" >&2
  echo "         VM_SIZE=Standard_B2als_v2 ./infra/azure/provision.sh    # 4 GiB, AMD, ~3.1 months" >&2
  exit 1
elif [ -n "$SIZE_RESTRICTIONS" ]; then
  echo "    !! $VM_SIZE is offered but RESTRICTED for this subscription:"
  echo "       $(echo "$SIZE_RESTRICTIONS" | sort -u | tr '\n' ' ')"
  echo "       B-series v1 has been growth-restricted since July 2026 and retires 2028-11-15."
  echo "       If 'az vm create' fails below, re-run with VM_SIZE=Standard_B2als_v2."
else
  echo "    available, no restrictions reported"
fi

cat <<SUMMARY

  resource group   $RG
  location         $LOCATION          (EU — required by the AVV, see the header)
  vm               $VM_NAME ($VM_SIZE)
  image            $IMAGE
  os disk          ${OS_DISK_SIZE_GB} GiB $OS_DISK_SKU
  ssh key          $SSH_KEY
  ssh allowed from $MY_IP/32           (and nowhere else)
  storage account  $STORAGE_ACCOUNT/$BACKUP_CONTAINER

  NOT created by this script, and both are required before deploying:
    - the Neon project (aws-eu-central-1) and its two connection strings
    - the Vercel project for azmoth.com  — already live; leave its DNS alone

SUMMARY

read -r -p "Create these resources? [y/N] " reply
[ "$reply" = "y" ] || [ "$reply" = "Y" ] || { echo "aborted"; exit 1; }

# ── 1. Resource group ─────────────────────────────────────────────────────────────────────────
# One group holds everything, so `az group delete --name azmoth-pilot` is a complete teardown with
# nothing orphaned quietly accruing charges — which is the failure mode that eats a fixed credit.

say "1/7 resource group: $RG"
if have group show --name "$RG"; then
  echo "    exists"
else
  az group create --name "$RG" --location "$LOCATION" --output none
  echo "    created"
fi

# ── 2. Static public IP ───────────────────────────────────────────────────────────────────────
# Static, not dynamic: a dynamic address is released when the VM is deallocated and comes back
# different, which breaks the DNS records the certificates depend on. Standard SKU because Basic is
# retired (September 2025) and because Standard is secure-by-default — it denies inbound traffic
# unless an NSG allows it, where Basic allowed it unless an NSG denied it.

say "2/7 static public IP: $IP_NAME"
if have network public-ip show --resource-group "$RG" --name "$IP_NAME"; then
  echo "    exists"
else
  az network public-ip create \
    --resource-group "$RG" \
    --name "$IP_NAME" \
    --sku Standard \
    --allocation-method Static \
    --version IPv4 \
    --output none
  echo "    created"
fi

PUBLIC_IP="$(az network public-ip show --resource-group "$RG" --name "$IP_NAME" \
  --query ipAddress --output tsv)"
echo "    address: $PUBLIC_IP"

# ── 3. Network Security Group ─────────────────────────────────────────────────────────────────
# Three inbound rules and no more. Azure's own DenyAllInBound sits at priority 65500 and catches
# everything not named here, so 8000 needs no explicit deny — it is closed because nothing opens it.
# A "deny 8000" rule is worse than no rule: it implies the absence of one means open, which is the
# opposite of how an NSG works.
#
# Note what is NOT needed here any more: an OUTBOUND rule for the database. Azure allows outbound
# by default, and the engine now reaches Frankfurt over TLS on 5432 rather than a container on
# localhost. If you ever tighten egress, that is the flow to remember — a locked-down outbound rule
# set is a stack that comes up healthy and cannot read a single proposal.
#
# This is the outer wall. infra/docker/docker-compose.azure.yml is the inner one — it unpublishes
# those ports from Docker as well, because a published Docker port writes its own iptables rules
# and is reachable even when the host firewall thinks otherwise.

say "3/7 network security group: $NSG_NAME"
if have network nsg show --resource-group "$RG" --name "$NSG_NAME"; then
  echo "    exists"
else
  az network nsg create --resource-group "$RG" --name "$NSG_NAME" --output none
  echo "    created"
fi

nsg_rule() {
  local name="$1" priority="$2" port="$3" source="$4" description="$5"
  if have network nsg rule show --resource-group "$RG" --nsg-name "$NSG_NAME" --name "$name"; then
    # Updated rather than skipped: MY_IP changes when the operator's ISP reassigns it, and a rerun
    # is how the SSH rule is meant to be corrected.
    az network nsg rule update \
      --resource-group "$RG" --nsg-name "$NSG_NAME" --name "$name" \
      --priority "$priority" --destination-port-ranges "$port" --source-address-prefixes "$source" \
      --description "$description" --output none
    echo "    $name updated (from $source)"
  else
    az network nsg rule create \
      --resource-group "$RG" --nsg-name "$NSG_NAME" --name "$name" \
      --priority "$priority" --direction Inbound --access Allow --protocol Tcp \
      --source-address-prefixes "$source" --source-port-ranges '*' \
      --destination-address-prefixes '*' --destination-port-ranges "$port" \
      --description "$description" --output none
    echo "    $name created (from $source)"
  fi
}

# SSH, from one address. Priority 100 — lowest number wins in an NSG, and this is the rule most
# likely to need to beat something added later by a well-meaning portal click.
nsg_rule ssh   100 22  "$MY_IP/32" "SSH from the operator's address only"
# HTTP. Not optional and not a weakening: Let's Encrypt's HTTP-01 challenge arrives here, and Caddy
# serves the redirect to 443 from it. Closing 80 does not add security, it stops TLS from working.
nsg_rule http  200 80  '*'         "HTTP - ACME HTTP-01 challenge and the redirect to HTTPS"
nsg_rule https 210 443 '*'         "HTTPS - Caddy terminates TLS here"

echo
echo "    inbound rules now:"
az network nsg rule list --resource-group "$RG" --nsg-name "$NSG_NAME" \
  --query "sort_by([].{priority:priority, name:name, port:destinationPortRange, source:sourceAddressPrefix, access:access}, &priority)" \
  --output table

# ── 4. Network ────────────────────────────────────────────────────────────────────────────────

say "4/7 virtual network: $VNET_NAME"
if have network vnet show --resource-group "$RG" --name "$VNET_NAME"; then
  echo "    exists"
else
  az network vnet create \
    --resource-group "$RG" --name "$VNET_NAME" \
    --address-prefix 10.0.0.0/16 \
    --subnet-name "$SUBNET_NAME" --subnet-prefix 10.0.1.0/24 \
    --output none
  echo "    created"
fi

# ── 5. The VM ─────────────────────────────────────────────────────────────────────────────────
# Password authentication is off — `--authentication-type ssh` is the default for a Linux image
# given `--ssh-key-values`, and it is stated anyway because it is the property that matters most on
# a box with a public IP.

say "5/7 virtual machine: $VM_NAME"
if have vm show --resource-group "$RG" --name "$VM_NAME"; then
  echo "    exists — leaving it alone"
else
  az vm create \
    --resource-group "$RG" \
    --name "$VM_NAME" \
    --image "$IMAGE" \
    --size "$VM_SIZE" \
    --admin-username "$ADMIN_USER" \
    --authentication-type ssh \
    --ssh-key-values "$SSH_KEY" \
    --public-ip-address "$IP_NAME" \
    --nsg "$NSG_NAME" \
    --vnet-name "$VNET_NAME" \
    --subnet "$SUBNET_NAME" \
    --os-disk-size-gb "$OS_DISK_SIZE_GB" \
    --storage-sku "$OS_DISK_SKU" \
    --output none
  echo "    created"
fi

# ── 6. Swap ───────────────────────────────────────────────────────────────────────────────────
# 4 GiB of swap on a 2 GiB machine, and the reason has changed even though the number has not.
#
# It used to be what made `next build` survive its peak. Nothing is built here now, so this is
# purely runtime insurance: three containers resting at 500-800 MiB on a 2 GiB box leaves real
# headroom, but a Soufflé solve forks a process whose peak nobody has characterised, and the
# failure mode without swap is the OOM killer choosing a victim — which on this box means the
# `web` container disappearing while somebody was mid-approval.
#
# `--file /swapfile` on the OS disk rather than the ephemeral resource disk at /mnt: /mnt is wiped
# when the VM is deallocated, and a swap entry in fstab pointing at a file that no longer exists
# fails the boot.
#
# Swap is not a substitute for RAM. If `free -m` shows swap in steady use rather than touched at
# peaks, the machine is too small — take the next rung of the VM_SIZE ladder in the header rather
# than adding more swap.

say "6/7 swap"
az vm run-command invoke \
  --resource-group "$RG" --name "$VM_NAME" \
  --command-id RunShellScript \
  --scripts '
    set -e
    if [ -f /swapfile ]; then echo "swapfile already present"; exit 0; fi
    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q "^/swapfile" /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
    # 10 rather than the default 60: prefer to keep the engine and web pages resident and use
    # swap for a solver spike, not for steady-state paging.
    #
    # NOTE for editors: this whole block is inside a single-quoted --scripts argument, so an
    # apostrophe anywhere in it — including in a comment like this one — terminates the quoting and
    # truncates the script that reaches the VM. Avoid possessives and contractions in here.
    sysctl -w vm.swappiness=10
    grep -q "^vm.swappiness" /etc/sysctl.conf || echo "vm.swappiness=10" >> /etc/sysctl.conf
    echo "swap configured"
  ' \
  --query 'value[0].message' --output tsv | tail -3

# ── 7. Blob Storage for backups ───────────────────────────────────────────────────────────────
# Small, cheap, and in the same region for the same AVV reason as the VM. A dump is a complete copy
# of every approval and audit event, so the container is private and the account refuses plain HTTP
# and TLS below 1.2. infra/scripts/backup-to-azure.sh encrypts before upload on top of that.
#
# ── Why this survives the move to Neon ────────────────────────────────────────────────────────
# Neon has native point-in-time restore, so the obvious move was to delete this account and the
# managed identity with it. It was costed at about EUR 0.05/month for a pilot's worth of dumps, and
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
#   3. **It also holds the things that are not in the database.** An encrypted copy of
#      /opt/azmoth/shared/.env — which now contains the Neon connection strings, without which the
#      dumps are just files — and nothing else on this box is backed up at all.
#
# What DID change is what gets dumped. There is no local Postgres to `docker compose exec` into, so
# infra/scripts/backup-to-azure.sh now runs `pg_dump` over the network against Neon's DIRECT
# endpoint, in a throwaway `postgres:17-alpine` container. See that script's header.

say "7/7 storage account for backups: $STORAGE_ACCOUNT"
if have storage account show --resource-group "$RG" --name "$STORAGE_ACCOUNT"; then
  echo "    exists"
else
  az storage account create \
    --resource-group "$RG" \
    --name "$STORAGE_ACCOUNT" \
    --location "$LOCATION" \
    --sku Standard_LRS \
    --kind StorageV2 \
    --access-tier Cool \
    --min-tls-version TLS1_2 \
    --https-only true \
    --allow-blob-public-access false \
    --output none
  echo "    created"
fi

if have storage container show --account-name "$STORAGE_ACCOUNT" --name "$BACKUP_CONTAINER" --auth-mode login; then
  echo "    container $BACKUP_CONTAINER exists"
else
  az storage container create \
    --account-name "$STORAGE_ACCOUNT" \
    --name "$BACKUP_CONTAINER" \
    --public-access off \
    --auth-mode login \
    --output none
  echo "    container $BACKUP_CONTAINER created"
fi

# ── The VM's identity, so no storage key is ever written to the box ───────────────────────────
# A system-assigned managed identity, granted "Storage Blob Data Contributor" on this container
# only. The VM then authenticates with `az login --identity` and Azure hands it a short-lived token.
#
# The alternative is a storage account key in a file on the VM, and the difference matters here: a
# key is a long-lived credential with full control of the account, it would sit next to the very
# dumps it protects, and rotating it means finding every copy. The identity cannot be read off the
# disk, expires by itself, and is revoked by deleting one role assignment.
#
# **Contributor, not Owner, and scoped to the container.** The backup job needs to write blobs. It
# does not need to change the container's public-access setting, which is what the account-level
# roles would let a compromised VM do — turning a private container of clinical records public.

say "    managed identity for backups"
PRINCIPAL_ID="$(az vm identity show --resource-group "$RG" --name "$VM_NAME" \
  --query principalId --output tsv 2>/dev/null || true)"

if [ -z "$PRINCIPAL_ID" ] || [ "$PRINCIPAL_ID" = "null" ]; then
  PRINCIPAL_ID="$(az vm identity assign --resource-group "$RG" --name "$VM_NAME" \
    --query systemAssignedIdentity --output tsv)"
  echo "    identity assigned"
  # The role assignment below fails with "principal does not exist" if it is made before Entra ID
  # has replicated the new principal. A few seconds is enough and retrying is cheaper than
  # explaining the error.
  sleep 20
else
  echo "    identity exists"
fi

CONTAINER_SCOPE="$(az storage account show --resource-group "$RG" --name "$STORAGE_ACCOUNT" \
  --query id --output tsv)/blobServices/default/containers/$BACKUP_CONTAINER"

if az role assignment list --assignee "$PRINCIPAL_ID" --scope "$CONTAINER_SCOPE" \
     --role "Storage Blob Data Contributor" --query '[0].id' --output tsv 2>/dev/null | grep -q .; then
  echo "    role assignment exists"
else
  # Retried: role assignment is the step that most often loses a race with Entra ID replication.
  for attempt in 1 2 3 4 5; do
    if az role assignment create \
         --assignee-object-id "$PRINCIPAL_ID" \
         --assignee-principal-type ServicePrincipal \
         --role "Storage Blob Data Contributor" \
         --scope "$CONTAINER_SCOPE" \
         --output none 2>/dev/null; then
      echo "    granted Storage Blob Data Contributor on $BACKUP_CONTAINER"
      break
    fi
    [ "$attempt" = 5 ] && {
      echo "    !! could not create the role assignment after 5 attempts." >&2
      echo "       You may lack User Access Administrator on the subscription. Grant it manually:" >&2
      echo "       az role assignment create --assignee-object-id $PRINCIPAL_ID \\" >&2
      echo "         --assignee-principal-type ServicePrincipal \\" >&2
      echo "         --role 'Storage Blob Data Contributor' --scope '$CONTAINER_SCOPE'" >&2
      break
    }
    echo "    waiting for the identity to replicate (attempt $attempt/5)..."
    sleep 15
  done
fi

# ── Done ──────────────────────────────────────────────────────────────────────────────────────

cat <<DONE

────────────────────────────────────────────────────────────────────────────────
  Public IP:  $PUBLIC_IP
  SSH:        ssh $ADMIN_USER@$PUBLIC_IP
  VM size:    $VM_SIZE   (see the header for the fallback ladder and the runway)

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
────────────────────────────────────────────────────────────────────────────────

DONE
