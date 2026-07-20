#!/usr/bin/env bash
# Non-destructively migrate Echo's secrets from the flat AI-Agents vault into the
# new per-agent Agent-Echo vault (Agent Runtime Registry). Copies — never moves —
# so AI-Agents stays intact until the new path is proven end-to-end.
#
# What it copies (best-effort; skips any source it can't find):
#   Echo gmail/username        -> Agent-Echo/echo-gmail-account
#   Echo gmail/password        -> Agent-Echo/echo-gmail-password
#   Echo - config/sheet_id     -> Agent-Echo/echo-tasks-sheet-id
#   Echo - gog OAuth client    -> Agent-Echo/gog-oauth-client  (assembled credentials JSON)
#
# What it does NOT do (must be minted — printed at the end):
#   claude-oauth-token  (echo's `claude setup-token`)   — REQUIRED
#   canopy-pat          (echo's canopy-web PAT)          — REQUIRED
#   gog-token           (echo's gog refresh token; lives in the gog keyring, not AI-Agents)
#
# Prereq: signed in — `eval "$(op signin --account dimagi.1password.com)"` — or
# OP_SERVICE_ACCOUNT_TOKEN set. Run from anywhere.

set -euo pipefail

ACCOUNT="${OP_ACCOUNT:-dimagi.1password.com}"
SRC_VAULT="${SRC_VAULT:-AI-Agents}"
AGENT_VAULT="Agent-Echo"

log()  { printf '\033[1;36m▶ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[1;32m✓ %s\033[0m\n' "$*"; }
skip() { printf '  \033[1;33m– %s\033[0m\n' "$*"; }

# Upsert an item's `credential` field in Agent-Echo (create if the placeholder
# from the bootstrap doesn't exist).
put() {
  local item="$1" value="$2"
  if op item get "$item" --vault "$AGENT_VAULT" --account "$ACCOUNT" >/dev/null 2>&1; then
    op item edit "$item" --vault "$AGENT_VAULT" --account "$ACCOUNT" "credential=$value" >/dev/null
  else
    op item create --category "API Credential" --title "$item" \
      --vault "$AGENT_VAULT" --account "$ACCOUNT" "credential[password]=$value" >/dev/null
  fi
}

# Copy one op:// field from the source vault into an Agent-Echo item.
copy() {
  local src_ref="$1" dest_item="$2"
  local value
  if value="$(op read "op://$SRC_VAULT/$src_ref" --account "$ACCOUNT" 2>/dev/null)" && [[ -n "$value" ]]; then
    put "$dest_item" "$value"
    ok "$dest_item  (from $SRC_VAULT/$src_ref)"
  else
    skip "$dest_item  (source $SRC_VAULT/$src_ref not found — skipped)"
  fi
}

main() {
  log "Copying Echo's Google secrets $SRC_VAULT → $AGENT_VAULT (non-destructive)"
  copy "Echo gmail/username"      echo-gmail-account
  copy "Echo gmail/password"      echo-gmail-password
  copy "Echo - config/sheet_id"   echo-tasks-sheet-id

  # gog OAuth client: assemble the gog/Google "installed app" credentials JSON from
  # the client_id/client_secret fields, so gog-oauth-client resolves to a ready
  # credentials-echo.json file on any box.
  log "Assembling Echo's gog OAuth client JSON"
  local cid csec
  if cid="$(op read "op://$SRC_VAULT/Echo - gog OAuth client/client_id" --account "$ACCOUNT" 2>/dev/null)" \
     && csec="$(op read "op://$SRC_VAULT/Echo - gog OAuth client/client_secret" --account "$ACCOUNT" 2>/dev/null)" \
     && [[ -n "$cid" && -n "$csec" ]]; then
    local json
    json="$(printf '{"installed":{"client_id":"%s","client_secret":"%s","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","redirect_uris":["http://localhost"]}}' "$cid" "$csec")"
    put gog-oauth-client "$json"
    ok "gog-oauth-client  (assembled credentials-echo.json)"
  else
    skip "gog-oauth-client  (client_id/client_secret not found — skipped)"
  fi

  cat <<EOF

$(printf '\033[1;32m✓ Google secrets migrated (AI-Agents untouched).\033[0m')

$(printf '\033[1;31mSTILL REQUIRED\033[0m') — the two secrets a headless run needs, which must be MINTED:

  1) Echo's Claude token (run where Echo's Claude subscription is authed):
       claude setup-token
     then store it:
       op item edit claude-oauth-token --vault $AGENT_VAULT --account $ACCOUNT "credential=<TOKEN>"

  2) Echo's canopy-web PAT (mint one for echo, or reuse the runner's), then:
       op item edit canopy-pat --vault $AGENT_VAULT --account $ACCOUNT "credential=<PAT>"

Optional (only for turns that do Google work): mint Echo's gog refresh token on a
box, which lands in the gog keyring:
  gog login echo@dimagi-ai.com --client echo --services gmail,drive,docs,sheets,forms,slides,appscript
EOF
}

main "$@"
