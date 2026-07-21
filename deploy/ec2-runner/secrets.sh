#!/usr/bin/env bash
# Put/update the runner's secrets in Secrets Manager. Values are read from a FILE
# (or stdin) so they never land in shell history.
#
#   ./secrets.sh canopy path/to/pat.txt          # canopy-web PAT
#   ./secrets.sh claude path/to/claude-token.txt # claude OAuth token
#   echo -n "<token>" | ./secrets.sh claude -     # or via stdin
set -euo pipefail
cd "$(dirname "$0")"

PROFILE="${AWS_PROFILE:-labs}"
REGION="${AWS_REGION:-us-east-1}"
AWS=(aws --profile "$PROFILE" --region "$REGION")

kind="${1:-}"; src="${2:-}"
case "$kind" in
  canopy) SECRET=canopy/cloud-runner/canopy-pat ;;
  claude) SECRET=canopy/cloud-runner/claude-oauth-token ;;
  *) echo "usage: ./secrets.sh {canopy|claude} <file|->" >&2; exit 1 ;;
esac
[[ -n "$src" ]] || { echo "give a file path or - for stdin" >&2; exit 1; }

if [[ "$src" == "-" ]]; then VALUE=$(cat); else VALUE=$(cat "$src"); fi
VALUE="${VALUE%$'\n'}"  # strip a single trailing newline
[[ -n "$VALUE" ]] || { echo "empty value" >&2; exit 1; }

if "${AWS[@]}" secretsmanager describe-secret --secret-id "$SECRET" >/dev/null 2>&1; then
  "${AWS[@]}" secretsmanager put-secret-value --secret-id "$SECRET" --secret-string "$VALUE" >/dev/null
  echo "updated $SECRET (${#VALUE} chars)"
else
  "${AWS[@]}" secretsmanager create-secret --name "$SECRET" \
    --description "canopy cloud runner ($kind)" --secret-string "$VALUE" >/dev/null
  echo "created $SECRET (${#VALUE} chars)"
fi
