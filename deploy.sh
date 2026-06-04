#!/bin/bash
set -euo pipefail

PROJECT_ID="canopy-494811"
REGION="us-central1"
REPO="us-central1-docker.pkg.dev/${PROJECT_ID}/canopy-web"
SQL_INSTANCE="${PROJECT_ID}:${REGION}:canopy-web-db"
SERVICE_NAME="canopy-web"
TAG="${1:-latest}"
SKIP_TESTS="${SKIP_TESTS:-0}"
REQUIRE_AUTH_FLAG="${REQUIRE_AUTH:-True}"
ALLOW_NON_MAIN_DEPLOY="${ALLOW_NON_MAIN_DEPLOY:-0}"

# --------------------------------------------------------------------------
# Branch guard: production is deployed from `main` only. Everyone merges to
# main to ship — no deploying a feature branch's working tree.
#
# Under GitHub Actions the checkout is a detached HEAD at a specific SHA, and
# the CI deploy job enforces ref==main itself (see .github/workflows/ci.yml),
# so we skip the local branch check there. Emergency local override:
#   ALLOW_NON_MAIN_DEPLOY=1 ./deploy.sh
# --------------------------------------------------------------------------
if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
  echo "==> GitHub Actions run; branch enforcement handled by the workflow."
elif [ "${ALLOW_NON_MAIN_DEPLOY}" = "1" ]; then
  echo "==> ALLOW_NON_MAIN_DEPLOY=1 — BYPASSING the main-branch guard (emergency)."
else
  CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  if [ "${CURRENT_BRANCH}" != "main" ]; then
    echo "ERROR: refusing to deploy from branch '${CURRENT_BRANCH}'." >&2
    echo "       Production deploys must come from 'main'. Merge your branch first." >&2
    echo "       Emergency override: ALLOW_NON_MAIN_DEPLOY=1 ./deploy.sh" >&2
    exit 1
  fi
  git fetch origin main --quiet 2>/dev/null || true
  LOCAL_SHA="$(git rev-parse HEAD 2>/dev/null || echo)"
  REMOTE_SHA="$(git rev-parse origin/main 2>/dev/null || echo)"
  if [ -n "${REMOTE_SHA}" ] && [ "${LOCAL_SHA}" != "${REMOTE_SHA}" ]; then
    echo "ERROR: local main (${LOCAL_SHA:0:9}) is out of sync with origin/main (${REMOTE_SHA:0:9})." >&2
    echo "       Pull/push so you deploy exactly what's on origin/main." >&2
    echo "       Emergency override: ALLOW_NON_MAIN_DEPLOY=1 ./deploy.sh" >&2
    exit 1
  fi
  echo "==> Branch guard OK: on main, in sync with origin/main."
fi

if [ "${SKIP_TESTS}" = "1" ]; then
  echo "==> SKIP_TESTS=1, skipping pre-deploy verification"
else
  echo "==> Running backend tests..."
  uv run pytest

  echo "==> Building frontend (type check + bundle)..."
  (cd frontend && npm run build)
fi

echo "==> Building and pushing combined image via Cloud Build..."
# Cloud Build runs on linux/amd64 in GCP, so no local Docker required and no
# cross-arch headache from Apple Silicon. cloudbuild.yaml drives the build and
# tags both :${TAG} and :latest.
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --config=cloudbuild.yaml \
  --substitutions="_TAG=${TAG},_REPO=${REPO},_SERVICE=${SERVICE_NAME}" \
  .

echo "==> Deploying to Cloud Run..."
# Single service serves Django API + built React SPA (via WhiteNoise).
# --allow-unauthenticated is correct: the app's LoginRequiredMiddleware
# enforces the Google OAuth gate at the application layer.
gcloud run deploy "${SERVICE_NAME}" \
  --image="${REPO}/${SERVICE_NAME}:${TAG}" \
  --region="${REGION}" \
  --platform=managed \
  --port=8000 \
  --memory=1Gi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --add-cloudsql-instances="${SQL_INSTANCE}" \
  --set-env-vars="DJANGO_SETTINGS_MODULE=config.settings.production" \
  --set-env-vars="AI_BACKEND=api" \
  --set-env-vars="^|^AUTH_ALLOWED_EMAIL_DOMAIN=dimagi.com,dimagi-ai.com" \
  --set-env-vars="REQUIRE_AUTH=${REQUIRE_AUTH_FLAG}" \
  --set-env-vars="CANOPY_DRIVE_ROOT_FOLDER_ID=1cUv7wQXOvVwuZ86PdhkxpFcuB4Lm9fPz" \
  --set-secrets="SECRET_KEY=django-secret-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest,DATABASE_URL=canopy-db-url:latest,GOOGLE_OAUTH_CLIENT_ID=google-oauth-client-id:latest,GOOGLE_OAUTH_CLIENT_SECRET=google-oauth-client-secret:latest,CANOPY_DRIVE_SA_KEY_JSON=canopy-web-drive-sa:latest" \
  --allow-unauthenticated \
  --quiet

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --format="value(status.url)")
echo ""
echo "==> Deployment complete!"
echo "    URL: ${SERVICE_URL}"
echo ""
echo "    Authorized redirect URI in Google OAuth must include:"
echo "    ${SERVICE_URL}/accounts/google/login/callback/"
echo ""
echo "    To run migrations:"
echo "    gcloud run jobs execute canopy-web-migrate --region=${REGION}"
