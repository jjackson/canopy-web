#!/bin/bash
set -euo pipefail

PROJECT_ID="connect-labs"
REGION="us-central1"
REPO="us-central1-docker.pkg.dev/${PROJECT_ID}/canopy-web"
SQL_INSTANCE="${PROJECT_ID}:${REGION}:canopy-web-db"
TAG="${1:-latest}"
SKIP_TESTS="${SKIP_TESTS:-0}"

if [ "${SKIP_TESTS}" = "1" ]; then
  echo "==> SKIP_TESTS=1, skipping pre-deploy verification"
else
  echo "==> Running backend tests..."
  uv run pytest

  echo "==> Building frontend (type check + bundle)..."
  (cd frontend && npm run build)
fi

echo "==> Building and pushing backend image..."
# --platform linux/amd64 is required because Cloud Run only runs amd64/linux
# and docker build on Apple Silicon defaults to arm64.
docker build --platform linux/amd64 -t "${REPO}/backend:${TAG}" -f Dockerfile .
docker push "${REPO}/backend:${TAG}"

echo "==> Building and pushing frontend image..."
docker build --platform linux/amd64 -t "${REPO}/frontend:${TAG}" -f Dockerfile.frontend .
docker push "${REPO}/frontend:${TAG}"

echo "==> Deploying backend to Cloud Run..."
gcloud run deploy canopy-web-backend \
  --image="${REPO}/backend:${TAG}" \
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
  --set-secrets="SECRET_KEY=django-secret-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest,DATABASE_URL=canopy-db-url:latest" \
  --allow-unauthenticated \
  --quiet

BACKEND_URL=$(gcloud run services describe canopy-web-backend --region="${REGION}" --format="value(status.url)")
echo "==> Backend deployed at: ${BACKEND_URL}"

echo "==> Deploying frontend to Cloud Run..."
gcloud run deploy canopy-web-frontend \
  --image="${REPO}/frontend:${TAG}" \
  --region="${REGION}" \
  --platform=managed \
  --port=3000 \
  --memory=256Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --set-env-vars="BACKEND_URL=${BACKEND_URL}" \
  --allow-unauthenticated \
  --quiet

FRONTEND_URL=$(gcloud run services describe canopy-web-frontend --region="${REGION}" --format="value(status.url)")
echo ""
echo "==> Deployment complete!"
echo "    Frontend: ${FRONTEND_URL}"
echo "    Backend:  ${BACKEND_URL}"
echo ""
echo "    To run migrations:"
echo "    gcloud run jobs execute canopy-web-migrate --region=${REGION}"
