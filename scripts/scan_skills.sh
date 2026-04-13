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

# Scan multiple possible skill locations
SKILLS_JSON=$(python3 -c "
import subprocess, json, sys

repo = '${REPO}'
skill_dirs = [
    ('skills', 'skills/'),
    ('plugins/canopy/skills', 'plugins/canopy/skills/'),
    ('plugins/ace/skills', 'plugins/ace/skills/'),
]

all_skills = []
for api_path, prefix in skill_dirs:
    try:
        result = subprocess.run(
            ['gh', 'api', f'repos/{repo}/contents/{api_path}'],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            continue
        entries = json.loads(result.stdout)
        if not isinstance(entries, list):
            continue
        for e in entries:
            if e['type'] == 'dir':
                all_skills.append({'name': e['name'], 'path': prefix + e['name']})
    except Exception:
        continue

print(json.dumps(all_skills))
")

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
