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
# Roughly EUR 36/month at pay-as-you-go in germanywestcentral, so ~2.7 months on 100 EUR:
#
#     Standard_B2s   2 vCPU, 4 GiB      ~EUR 30/mo
#     64 GiB StandardSSD (E6)           ~EUR  5/mo
#     Standard static IPv4              ~EUR  4/mo    (Azure bills IPv4 addresses)
#     Egress                             ~EUR  0/mo    (first 100 GB/month is free)
#
# Those are estimates from list prices and they move. Check yours before committing:
#     az vm list-skus --location "$LOCATION" --size Standard_B2 --output table
#     https://azure.microsoft.com/pricing/calculator/
#
# **B2s is chosen for the BUILD, not the run.** `scripts/deploy.sh` builds on the box, and that
# build is two `next build`s (web and marketing) plus a node-gyp compile of better-sqlite3 in the
# deps stage. Next peaks well over 1 GiB per build. On a 2 GiB B1ms the build is OOM-killed — the
# symptom is a compose build that dies with exit 137 and no explanation. At rest the running stack
# fits in about 1.5 GiB, so B1ms would happily *run* what it cannot *build*; if the credit has to
# stretch further than the calendar, the move is to build images elsewhere and pull them, not to
# shrink this VM and hope.
#
# B2ms (8 GiB) is about twice the price for memory the build does not need, and would cut the
# runway to ~1.6 months. Standard_B2ls_v2 (2 vCPU, 4 GiB) is the same memory ~20% cheaper where it
# is available — set VM_SIZE to try it, and fall back to B2s if the region says no.
#
# ── Region ────────────────────────────────────────────────────────────────────────────────────
# germanywestcentral, and this is a compliance constraint rather than a latency preference.
# docs/AVV_TECHNICAL_ANNEX_DRAFT.md section 5.1 states that processing happens exclusively on
# systems inside the EU. Frankfurt satisfies that. Do not move this to eastus to save a euro.
#
# NOTE: deploying at all makes section 5.2 of that annex ("Unterauftragsverarbeiter: derzeit
# keine") untrue — Microsoft becomes a processor the moment this VM exists. That document has to
# name Microsoft Azure, with this region, before a practice signs it.

set -euo pipefail

# ── Settings ──────────────────────────────────────────────────────────────────────────────────
# Override any of these from the environment:  VM_SIZE=Standard_B2ls_v2 ./infra/azure/provision.sh

RG="${RG:-azmoth-pilot}"
LOCATION="${LOCATION:-germanywestcentral}"
VM_NAME="${VM_NAME:-azmoth-vm}"
VM_SIZE="${VM_SIZE:-Standard_B2s}"
ADMIN_USER="${ADMIN_USER:-azmoth}"

# Ubuntu 22.04 LTS, gen2, pinned by full URN rather than by the `Ubuntu2204` alias. An alias is
# resolved by whatever version of the CLI you happen to have; this is the same image every time.
IMAGE="${IMAGE:-Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest}"

# 64 GiB StandardSSD. Docker is the reason for the size, not Postgres: the build cache, two Node
# images and the engine's Soufflé toolchain add up to well over 20 GiB before a single row is
# written. StandardSSD rather than Premium because a pilot's write rate does not need provisioned
# IOPS, and rather than Standard HDD because Postgres on spinning-rust latency is miserable.
#
# There is no separate data disk, deliberately. It was considered for backups and rejected: a disk
# attached to this VM is destroyed with this VM, and docs/OPERATIONS.md already requires dumps to be
# kept off the same host as the database. They go to Blob Storage instead — see the storage account
# below and infra/scripts/backup-to-blob.sh.
OS_DISK_SIZE_GB="${OS_DISK_SIZE_GB:-64}"
OS_DISK_SKU="${OS_DISK_SKU:-StandardSSD_LRS}"

SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519.pub}"

IP_NAME="${IP_NAME:-${VM_NAME}-ip}"
NSG_NAME="${NSG_NAME:-${VM_NAME}-nsg}"
VNET_NAME="${VNET_NAME:-${VM_NAME}-vnet}"
SUBNET_NAME="${SUBNET_NAME:-${VM_NAME}-subnet}"

# Where backups land. Storage account names are globally unique, 3-24 chars, lowercase alphanumeric
# only — hence the suffix.
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

cat <<SUMMARY

  resource group   $RG
  location         $LOCATION          (EU — required by the AVV, see the header)
  vm               $VM_NAME ($VM_SIZE)
  image            $IMAGE
  os disk          ${OS_DISK_SIZE_GB} GiB $OS_DISK_SKU
  ssh key          $SSH_KEY
  ssh allowed from $MY_IP/32           (and nowhere else)
  storage account  $STORAGE_ACCOUNT/$BACKUP_CONTAINER

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
# everything not named here, so 8000 and 5432 need no explicit deny — they are closed because
# nothing opens them. A "deny 8000" rule is worse than no rule: it implies the absence of one means
# open, which is the opposite of how an NSG works.
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
# 4 GiB of swap on a 4 GiB machine. This is what makes `next build` survive its peak on B2s: the
# build is briefly memory-hungry and mostly idle on those pages afterwards, which is precisely the
# shape swap is good at. Without it the build is OOM-killed at exit 137 with no message.
#
# `--file /swapfile` on the OS disk rather than the ephemeral resource disk at /mnt: /mnt is wiped
# when the VM is deallocated, and a swap entry in fstab pointing at a file that no longer exists
# fails the boot.
#
# It is not a substitute for RAM at RUNTIME — a Postgres that swaps is a Postgres that has stopped
# being a database. Watch `free -m` after the first build; steady-state should show swap barely
# touched.

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
    # 10 rather than the default 60: prefer to keep Postgres pages resident and use swap for the
    # build spike, not for steady-state paging.
    sysctl -w vm.swappiness=10
    grep -q "^vm.swappiness" /etc/sysctl.conf || echo "vm.swappiness=10" >> /etc/sysctl.conf
    echo "swap configured"
  ' \
  --query 'value[0].message' --output tsv | tail -3

# ── 7. Blob Storage for backups ───────────────────────────────────────────────────────────────
# Small, cheap, and in the same region for the same AVV reason as the VM. A dump is a complete copy
# of every approval and audit event, so the container is private and the account refuses plain HTTP
# and TLS below 1.2. infra/scripts/backup-to-blob.sh encrypts before upload on top of that.

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

  NEXT — point DNS at that address and WAIT for it to resolve. Caddy gets its
  certificates over HTTP-01, which means Let's Encrypt fetches a token from
  these names over port 80. A name that does not resolve yet is a failed
  issuance and a retry backoff, not a warning.

      A   app.azmoth.com    $PUBLIC_IP
      A   api.azmoth.com    $PUBLIC_IP
      A   azmoth.com        $PUBLIC_IP
      A   www.azmoth.com    $PUBLIC_IP

  Check with:  dig +short app.azmoth.com

  THEN:        ./scripts/deploy.sh $PUBLIC_IP
────────────────────────────────────────────────────────────────────────────────

DONE
