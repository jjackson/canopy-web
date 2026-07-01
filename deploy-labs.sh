#!/usr/bin/env bash
#
# Deploy canopy-web to the connect-labs AWS environment
# (labs.connect.dimagi.com/canopy — the /canopy tenant on the shared ALB).
#
# Replaces the retired GCP path (deploy.sh / cloudbuild.yaml). Builds the image
# locally, pushes to ECR, and rolls the ECS Fargate service. Requires:
#   - AWS SSO login:  aws sso login --profile labs
#   - Docker running locally (buildx; the image targets linux/amd64 for Fargate)
#
# Production ships from `main` ONLY (mirrors the old GCP guard).
set -euo pipefail

AWS_PROFILE="${AWS_PROFILE:-labs}"
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR="858923557655.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE="${ECR}/labs-jj-canopy-web:latest"
CLUSTER="labs-jj-cluster"
SERVICE="labs-jj-canopy-web"
export AWS_PROFILE AWS_REGION

# ── Main-branch guard (ALLOW_NON_MAIN_DEPLOY=1 to bypass in emergencies) ──────
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$BRANCH" != "main" ] && [ "${ALLOW_NON_MAIN_DEPLOY:-}" != "1" ]; then
  echo "ERROR: refusing to deploy from '$BRANCH' (production ships from main)." >&2
  echo "       Set ALLOW_NON_MAIN_DEPLOY=1 to override." >&2
  exit 1
fi

# ── Vendor the canopy plugin so apps.system renders the /system catalog ───────
# apps.system auto-detects ./canopy/plugins/canopy (see settings _resolve_canopy_plugin_path).
# The repo is public, so no token is needed. Absent → /system degrades to empty.
echo "==> Vendoring canopy plugin into build context..."
rm -rf canopy
if git clone --depth 1 https://github.com/jjackson/canopy.git canopy >/dev/null 2>&1; then
  echo "    plugin vendored at ./canopy/plugins/canopy"
else
  echo "    WARNING: plugin clone failed — /system catalog will be empty"
  rm -rf canopy
fi

# ── Build (linux/amd64 for Fargate) + push ───────────────────────────────────
# Build args drive the /canopy path prefix + the tenant-scoped CSRF cookie name.
echo "==> Logging in to ECR..."
aws ecr get-login-password | docker login --username AWS --password-stdin "$ECR"

echo "==> Building + pushing $IMAGE ..."
docker build --platform linux/amd64 \
  --build-arg VITE_BASE_PATH=/canopy/ \
  --build-arg VITE_CSRF_COOKIE_NAME=csrftoken_canopy \
  -t "$IMAGE" .
docker push "$IMAGE"

# ── Roll the service + run migrations ─────────────────────────────────────────
echo "==> Rolling ECS service $SERVICE ..."
aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" \
  --force-new-deployment >/dev/null
echo "==> Waiting for the service to stabilize..."
aws ecs wait services-stable --cluster "$CLUSTER" --services "$SERVICE"

echo "==> Done. Live at https://labs.connect.dimagi.com/canopy/"
echo "    NOTE: DB migrations run via the migrate one-off task, not here."
echo "    See deploy/aws/canopy-web.cfn.yaml for the infrastructure definition."
