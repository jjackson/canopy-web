#!/usr/bin/env bash
# Spin UP the canopy cloud runner via CloudFormation. Idempotent (create or update).
# Secrets must already be in Secrets Manager — see ./secrets.sh.
#
#   aws sso login --profile labs
#   ./secrets.sh canopy <pat-file>     # once
#   ./secrets.sh claude <token-file>   # once (a VALID claude OAuth token)
#   ./up.sh                            # deploy the stack
#   ./down.sh                          # delete the stack
set -euo pipefail
cd "$(dirname "$0")"

PROFILE="${AWS_PROFILE:-labs}"
REGION="${AWS_REGION:-us-east-1}"
STACK="${STACK:-canopy-cloud-runner}"
AWS=(aws --profile "$PROFILE" --region "$REGION")

echo ">> account"; "${AWS[@]}" sts get-caller-identity --query Account --output text

# Secrets must exist first (the instance role reads them at boot).
for s in canopy/cloud-runner/canopy-pat canopy/cloud-runner/claude-oauth-token; do
  if ! "${AWS[@]}" secretsmanager describe-secret --secret-id "$s" >/dev/null 2>&1; then
    echo "!! missing secret '$s' — run ./secrets.sh first" >&2; exit 1
  fi
done

MYIP=$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')
echo ">> SSH allowed from ${MYIP}/32"

# Render: splice cloud_runner.py (base64) into the template. cloud_runner.py stays
# the single source of truth; the rendered template is a build artifact.
RENDERED=".runner.cfn.rendered.yaml"
# gzip+base64 (cloud-init decodes via `encoding: gz+b64`): the RC2 WS client pushed
# the plain-base64 UserData past EC2's 25.6 KB limit; gzip keeps it well under.
B64=$(python3 -c "import base64,gzip;print(base64.b64encode(gzip.compress(open('cloud_runner.py','rb').read())).decode())")
python3 - "$B64" > "$RENDERED" <<'PY'
import sys, pathlib
b64 = sys.argv[1]
tpl = pathlib.Path("runner.cfn.yaml").read_text()
sys.stdout.write(tpl.replace("CLOUD_RUNNER_PY_B64_PLACEHOLDER", b64))
PY

echo ">> validating template"
"${AWS[@]}" cloudformation validate-template --template-body "file://$RENDERED" >/dev/null

echo ">> deploying stack $STACK"
"${AWS[@]}" cloudformation deploy \
  --stack-name "$STACK" --template-file "$RENDERED" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides "SshCidr=${MYIP}/32" \
  ${EXTRA_PARAMS:-}

echo ">> outputs"
OUT=$("${AWS[@]}" cloudformation describe-stacks --stack-name "$STACK" \
  --query 'Stacks[0].Outputs' --output json)
IP=$(echo "$OUT" | python3 -c "import sys,json;print(next(o['OutputValue'] for o in json.load(sys.stdin) if o['OutputKey']=='PublicIp'))")
KID=$(echo "$OUT" | python3 -c "import sys,json;print(next(o['OutputValue'] for o in json.load(sys.stdin) if o['OutputKey']=='KeyPairId'))")

# Pull the CFN-managed private key out of SSM for SSH access.
KEYFILE="./${STACK}-key.pem"
"${AWS[@]}" ssm get-parameter --name "/ec2/keypair/${KID}" --with-decryption \
  --query 'Parameter.Value' --output text > "$KEYFILE"
chmod 600 "$KEYFILE"

echo ""
echo "==> UP. ip=$IP"
echo "    ssh:  ssh -i $KEYFILE ubuntu@$IP"
echo "    logs: ssh -i $KEYFILE ubuntu@$IP 'journalctl -u canopy-runner -f'"
echo "    cloud-init boots the runner automatically (give it ~3 min for node+claude)."
