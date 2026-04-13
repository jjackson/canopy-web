#!/usr/bin/env bash
# Scan a GitHub repo's skills/ directory and PATCH the project in canopy-web.
#
# Usage:
#   ./scripts/scan_skills.sh jjackson/ace https://canopy-web-backend-hhhi4yut3q-uc.a.run.app
#
set -euo pipefail

REPO="${1:?Usage: scan_skills.sh OWNER/REPO API_URL}"
API_URL="${2:?Usage: scan_skills.sh OWNER/REPO API_URL}"

# Derive slug from repo name (owner/repo -> repo)
SLUG="${REPO#*/}"

echo "Scanning ${REPO} skills/ ..."

# Fetch the skills/ directory listing; handle missing directory gracefully
RESPONSE=$(gh api "repos/${REPO}/contents/skills" 2>/dev/null || echo "[]")

# If the response is an object (error message) instead of an array, treat as empty
if echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if isinstance(d,list) else 1)" 2>/dev/null; then
  SKILLS_JSON=$(echo "$RESPONSE" | python3 -c "
import sys, json
entries = json.load(sys.stdin)
skills = [{'name': e['name'], 'path': 'skills/' + e['name']} for e in entries if e['type'] == 'dir']
print(json.dumps(skills))
")
else
  SKILLS_JSON="[]"
fi

COUNT=$(echo "$SKILLS_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
echo "Found ${COUNT} skills in ${REPO}"

# PATCH the project
curl -s -X PATCH "${API_URL}/api/projects/${SLUG}/" \
  -H "Content-Type: application/json" \
  -d "{\"skills\": ${SKILLS_JSON}}" | python3 -c "
import sys, json
resp = json.load(sys.stdin)
if resp.get('success'):
    print('Updated ${SLUG}: ' + str(len(resp['data'].get('skills', []))) + ' skills')
else:
    print('Error: ' + json.dumps(resp), file=sys.stderr)
    sys.exit(1)
"
