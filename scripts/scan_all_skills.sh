#!/usr/bin/env bash
# Scan skills for all projects that have a repo_url.
#
# Usage:
#   ./scripts/scan_all_skills.sh [API_URL]
#
set -euo pipefail

API_URL="${1:-https://canopy-web-backend-hhhi4yut3q-uc.a.run.app}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Fetching project list from ${API_URL} ..."

curl -s "${API_URL}/api/projects/" | python3 -c "
import sys, json
data = json.load(sys.stdin)
projects = data['data'] if 'data' in data else data
for p in projects:
    repo = p.get('repo_url', '')
    if repo:
        # Strip https://github.com/ prefix
        repo = repo.replace('https://github.com/', '')
        print(p['slug'] + ' ' + repo)
" | while read -r slug repo; do
  echo "--- ${slug} (${repo}) ---"
  "${SCRIPT_DIR}/scan_skills.sh" "$repo" "$API_URL" || echo "  FAILED for ${slug}"
done

echo "Done."
