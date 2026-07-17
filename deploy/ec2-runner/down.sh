#!/usr/bin/env bash
# Spin DOWN: terminate the instance, delete the security group + key pair, and
# remove local state. Safe to run repeatedly.
set -euo pipefail
cd "$(dirname "$0")"

[[ -f .state.json ]] || { echo "no .state.json — nothing to tear down"; exit 0; }
read -r PROFILE REGION IID SG KEY KEYFILE <<<"$(python3 -c '
import json; s=json.load(open(".state.json"))
print(s["profile"], s["region"], s["instance_id"], s["security_group"], s["key_name"], s["key_file"])')"
AWS=(aws --profile "$PROFILE" --region "$REGION")

echo ">> terminating $IID"
"${AWS[@]}" ec2 terminate-instances --instance-ids "$IID" >/dev/null
"${AWS[@]}" ec2 wait instance-terminated --instance-ids "$IID"

echo ">> deleting security group $SG"
# ENIs can linger briefly after termination; retry a few times.
for i in 1 2 3 4 5; do
  if "${AWS[@]}" ec2 delete-security-group --group-id "$SG" 2>/dev/null; then break; fi
  echo "   (SG still in use — retry $i)"; sleep 10
done

echo ">> deleting key pair $KEY"
"${AWS[@]}" ec2 delete-key-pair --key-name "$KEY" || true
rm -f "$KEYFILE" .state.json
echo "==> DOWN + cleaned up."
