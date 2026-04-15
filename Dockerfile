# ─── Stage 1: build the React SPA ────────────────────────────────────
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


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

# Install Python deps first for better layer caching
COPY pyproject.toml ./
RUN pip install .

# Application code
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
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
