#!/usr/bin/env bash
# infra/aws/audit-leftovers.sh — what is still in the account, and what bills.
# Every BILLABLE section saying "none" = your AWS bill is $0.
set -uo pipefail
export AWS_PAGER=""        # no pager, no (END), everything prints straight through
R="${REGION:-eu-central-1}"

show() {
  local out
  out="$(aws "$@" --output table 2>&1)"
  if [ -z "$out" ] || [ "$out" = "None" ]; then
    echo "    none ✅"
  else
    printf '%s\n' "$out" | sed 's/^/    /'
  fi
}

echo "== [BILLABLE] EC2 instances not terminated =="
show ec2 describe-instances --region "$R" \
  --query "Reservations[*].Instances[?State.Name!='terminated'].[InstanceId,State.Name,Tags[?Key=='Name'].Value|[0]]"

echo "== [BILLABLE] Elastic IPs (unattached = charged) =="
show ec2 describe-addresses --region "$R" \
  --query "Addresses[].[PublicIp,AllocationId,AssociationId||'unattached']"

echo "== [BILLABLE] EBS volumes =="
show ec2 describe-volumes --region "$R" --query "Volumes[].[VolumeId,State,Size]"

echo "== [BILLABLE] S3 buckets =="
show s3api list-buckets --query "Buckets[].Name"

echo "== [BILLABLE] Load balancers / NAT gateways =="
show elbv2 describe-load-balancers --region "$R" --query "LoadBalancers[].LoadBalancerName"
show ec2 describe-nat-gateways --region "$R" --query "NatGateways[?State!='deleted'].[NatGatewayId,State]"

echo "== [FREE, safe to keep] SGs / key pairs / IAM =="
show ec2 describe-security-groups --region "$R" --query "SecurityGroups[?GroupName!='default'].[GroupName]"
show ec2 describe-key-pairs --region "$R" --query "KeyPairs[].KeyName"
show iam list-roles --query "Roles[?contains(RoleName,'azmoth')].RoleName"

echo; echo "== audit done — all BILLABLE sections 'none' = \$0 bill =="