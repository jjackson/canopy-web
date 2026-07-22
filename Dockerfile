# ─── Stage 1: build the React SPA ────────────────────────────────────
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# Path prefix for the deployment (e.g. /canopy/ as a labs tenant). Defaults to
# "/" (root / GCP). Drives Vite base → import.meta.env.BASE_URL.
ARG VITE_BASE_PATH=/
# Django CSRF cookie name. Path-scoped per tenant on the shared labs host
# (csrftoken_canopy for /canopy) so writes send the right token; defaults to
# Django's "csrftoken" for the root deployment.
ARG VITE_CSRF_COOKIE_NAME=csrftoken
RUN VITE_BASE_PATH="$VITE_BASE_PATH" \
    VITE_CSRF_COOKIE_NAME="$VITE_CSRF_COOKIE_NAME" \
    npm run build


# ─── Stage 2: Python runtime ─────────────────────────────────────────
FROM python:3.12-slim

# Install Node.js for the optional Claude Code CLI backend
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

WORKDIR /app

# Install Python deps first for better layer caching. canopy-web depends on the
# in-repo `canopy-runs` package (a uv path source — see [tool.uv.sources]), so
# copy it into the context and install via uv (which resolves path sources);
# plain `pip install .` can't find canopy-runs on PyPI.
COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
RUN pip install uv && uv pip install --system .

# Application code. This includes ./canopy when the deploy step has cloned the
# (private) canopy plugin into the build context — see deploy.sh. apps.system
# reads it at /app/canopy/plugins/canopy to render the /system catalog;
# settings' _resolve_canopy_plugin_path() locates it. When absent (local builds,
# missing token), the catalog degrades to an empty state with a warning.
COPY . .

# Built SPA from stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Collect static assets so WhiteNoise can serve them.
# SECRET_KEY/DATABASE_URL aren't used by collectstatic; dummy values keep Django happy.
ENV DJANGO_SETTINGS_MODULE=config.settings.production
RUN SECRET_KEY=build-placeholder \
    DATABASE_URL=sqlite:///tmp/build.sqlite3 \
    ALLOWED_HOSTS=* \
    GOOGLE_OAUTH_CLIENT_ID=placeholder \
    GOOGLE_OAUTH_CLIENT_SECRET=placeholder \
    python manage.py collectstatic --noinput

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
# WS keepalive note: the shared labs proxy drops an idle WebSocket at ~6-8s and —
# proven empirically — does NOT count ws ping/pong CONTROL frames as activity, only
# application DATA frames. So these uvicorn ping flags do NOT by themselves keep a
# client alive through the proxy; the real keepalive is an app-level data frame sent
# every ~4s by each client (the runner's `keepalive` action; browser clients send
# their own). The flags stay as sane dead-peer detection defaults.
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", \
     "--ws-ping-interval", "5", "--ws-ping-timeout", "20"]
