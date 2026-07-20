#!/usr/bin/env bash
# Bootstrap the canopy agent secret topology in 1Password.
#
# Idempotent. Creates the two-tier vault structure the Agent Runtime Registry
# reconciler resolves against:
#   Canopy-Shared      — secrets EVERY canopy agent needs
#   Agent-<Slug>       — one per agent: its own identity + integration secrets
#
# You run this yourself (via `!` in the Claude session, or a normal terminal) so
# the service-account token — the one credential that unlocks everything — stays
# in your hands and is never pasted into the conversation unless you choose to.
#
# Usage:
#   ./bootstrap_1password.sh echo ada hal eva
#
# Prereq: `op` CLI signed in to the Business account:
#   eval "$(op signin --account dimagi.1password.com)"
# (or enable the 1Password desktop-app CLI integration for Touch ID per command.)

set -euo pipefail

ACCOUNT="${OP_ACCOUNT:-dimagi.1password.com}"
SHARED_VAULT="Canopy-Shared"

# Per-agent items we scaffold as empty placeholders so `op://` references resolve
# immediately (the reconciler treats an empty field as "not provisioned yet" and
# surfaces it as needs-bootstrap rather than 404ing). Values are filled in later,
# either interactively (claude setup-token / gog login) or by the reconciler's
# write-back. Add fields here as the fleet's needs grow.
AGENT_ITEMS=("canopy-pat" "claude-oauth-token" "gog-token")

log() { printf '\033[1;36m▶ %s\033[0m\n' "$*"; }

ensure_signed_in() {
  if ! op whoami --account "$ACCOUNT" >/dev/null 2>&1; then
    echo "Not signed in to $ACCOUNT. Run:  eval \"\$(op signin --account $ACCOUNT)\"" >&2
    exit 1
  fi
}

ensure_vault() {
  local name="$1"
  if op vault get "$name" --account "$ACCOUNT" >/dev/null 2>&1; then
    log "vault exists: $name"
  else
    log "creating vault: $name"
    op vault create "$name" --account "$ACCOUNT" >/dev/null
  fi
}

ensure_placeholder_item() {
  # An "API Credential" item whose single 'credential' field is empty until minted.
  local vault="$1" title="$2"
  if op item get "$title" --vault "$vault" --account "$ACCOUNT" >/dev/null 2>&1; then
    log "  item exists: $vault/$title"
  else
    log "  scaffolding item: $vault/$title"
    op item create --category "API Credential" --title "$title" \
      --vault "$vault" --account "$ACCOUNT" "credential[password]=" >/dev/null
  fi
}

main() {
  if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <agent-slug> [agent-slug ...]" >&2
    exit 2
  fi
  ensure_signed_in

  log "=== Shared vault ==="
  ensure_vault "$SHARED_VAULT"

  for slug in "$@"; do
    # Capitalize first letter for the vault display name: echo -> Agent-Echo.
    local vault="Agent-$(printf '%s' "${slug:0:1}" | tr '[:lower:]' '[:upper:]')${slug:1}"
    log "=== Agent: $slug -> vault $vault ==="
    ensure_vault "$vault"
    for item in "${AGENT_ITEMS[@]}"; do
      ensure_placeholder_item "$vault" "$item"
    done
  done

  cat <<EOF

$(printf '\033[1;32m✓ Vault topology ready.\033[0m')

Next (owner-only) — mint the service-account token the runner uses. Grant it
READ on the shared vault, and READ+WRITE on the agent vaults it may run so the
reconciler can persist minted tokens (claude setup-token) back for cold boxes:

  op service-account create "canopy-cloud-runner" \\
    --account $ACCOUNT \\
    --vault "$SHARED_VAULT:read_items" \\$(for slug in "$@"; do
      v="Agent-$(printf '%s' "${slug:0:1}" | tr '[:lower:]' '[:upper:]')${slug:1}"
      printf '\n    --vault "%s:read_items,write_items" \\' "$v"
    done)
    --expires-in 90d

The command prints the token ONCE. Then store it for the cloud runner:

  aws secretsmanager put-secret-value \\
    --secret-id canopy/cloud-runner/op-service-account-token \\
    --secret-string "<TOKEN>"   # or create-secret the first time

For your laptop, export it (or the reconciler reads it from your op signin):
  export OP_SERVICE_ACCOUNT_TOKEN="<TOKEN>"
EOF
}

main "$@"
