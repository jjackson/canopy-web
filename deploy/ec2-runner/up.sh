#!/usr/bin/env bash
# Spin UP a canopy cloud-runner EC2 instance (ephemeral). Writes deploy/ec2-runner/
# .state.json with everything down.sh needs to tear it back down.
#
#   aws sso login --profile labs      # once, interactively (you run this)
#   ./up.sh                           # launch
#   ./setup.sh                        # provision + start the runner
#   ./down.sh                         # terminate + clean up
set -euo pipefail
cd "$(dirname "$0")"

PROFILE="${AWS_PROFILE:-labs}"
REGION="${AWS_REGION:-us-east-1}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.medium}"
NAME="${NAME:-canopy-cloud-runner}"
STATE=".state.json"
AWS=(aws --profile "$PROFILE" --region "$REGION")

if [[ -f "$STATE" ]]; then
  echo "!! $STATE already exists — an instance may be up. Run ./down.sh first, or rm $STATE." >&2
  exit 1
fi

echo ">> account check"; "${AWS[@]}" sts get-caller-identity --query Account --output text

# Ubuntu 24.04 LTS (canonical SSM public parameter — no hardcoded AMI to rot).
AMI=$("${AWS[@]}" ssm get-parameters \
  --names /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
  --query 'Parameters[0].Value' --output text)
echo ">> AMI: $AMI"

MYIP=$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')
echo ">> your IP (SSH allow): $MYIP/32"

KEY="${NAME}-key"
KEYFILE="./${KEY}.pem"
echo ">> creating key pair $KEY"
"${AWS[@]}" ec2 create-key-pair --key-name "$KEY" \
  --query 'KeyMaterial' --output text > "$KEYFILE"
chmod 600 "$KEYFILE"

echo ">> creating security group"
VPC=$("${AWS[@]}" ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text)
SG=$("${AWS[@]}" ec2 create-security-group --group-name "${NAME}-sg" \
  --description "canopy cloud runner (ephemeral)" --vpc-id "$VPC" \
  --query 'GroupId' --output text)
"${AWS[@]}" ec2 authorize-security-group-ingress --group-id "$SG" \
  --protocol tcp --port 22 --cidr "${MYIP}/32" >/dev/null

echo ">> launching $INSTANCE_TYPE"
IID=$("${AWS[@]}" ec2 run-instances --image-id "$AMI" --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY" --security-group-ids "$SG" \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=20,VolumeType=gp3}' \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME},{Key=purpose,Value=canopy-cloud-runner}]" \
  --query 'Instances[0].InstanceId' --output text)
echo ">> instance $IID — waiting for running + status ok"
"${AWS[@]}" ec2 wait instance-status-ok --instance-ids "$IID"

IP=$("${AWS[@]}" ec2 describe-instances --instance-ids "$IID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

cat > "$STATE" <<JSON
{"profile":"$PROFILE","region":"$REGION","instance_id":"$IID","public_ip":"$IP","security_group":"$SG","key_name":"$KEY","key_file":"$KEYFILE","ssh_user":"ubuntu"}
JSON

echo ""
echo "==> UP. instance=$IID ip=$IP"
echo "    ssh: ssh -i $KEYFILE ubuntu@$IP"
echo "    next: fill runner.env, then ./setup.sh"
