#!/bin/bash
set -euo pipefail

PROJECT_ID="connect-labs"
REGION="us-central1"
REPO="us-central1-docker.pkg.dev/${PROJECT_ID}/canopy-web"
SQL_INSTANCE="${PROJECT_ID}:${REGION}:canopy-web-db"
SERVICE_NAME="canopy-web"
TAG="${1:-latest}"
SKIP_TESTS="${SKIP_TESTS:-0}"
REQUIRE_AUTH_FLAG="${REQUIRE_AUTH:-True}"

if [ "${SKIP_TESTS}" = "1" ]; then
  echo "==> SKIP_TESTS=1, skipping pre-deploy verification"
else
  echo "==> Running backend tests..."
  uv run pytest

  echo "==> Building frontend (type check + bundle)..."
  (cd frontend && npm run build)
fi

echo "==> Building and pushing combined image..."
# --platform linux/amd64 is required because Cloud Run only runs amd64/linux
# and docker build on Apple Silicon defaults to arm64.
docker build --platform linux/amd64 -t "${REPO}/${SERVICE_NAME}:${TAG}" -f Dockerfile .
docker push "${REPO}/${SERVICE_NAME}:${TAG}"

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
  --set-env-vars="AUTH_ALLOWED_EMAIL_DOMAIN=dimagi.com" \
  --set-env-vars="REQUIRE_AUTH=${REQUIRE_AUTH_FLAG}" \
  --set-secrets="SECRET_KEY=django-secret-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest,DATABASE_URL=canopy-db-url:latest,GOOGLE_OAUTH_CLIENT_ID=google-oauth-client-id:latest,GOOGLE_OAUTH_CLIENT_SECRET=google-oauth-client-secret:latest" \
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
