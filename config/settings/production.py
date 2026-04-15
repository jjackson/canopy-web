"""
Production Django settings for Cloud Run + Cloud SQL deployment.
"""
from .base import *  # noqa: F401, F403

DEBUG = False

# Cloud Run sets PORT; uvicorn binds to it.
# ALLOWED_HOSTS was declared as a list type in base.py, so env() returns a list.
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])

# Security headers — Cloud Run terminates TLS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Static files — served by WhiteNoise in the single Cloud Run service
STATIC_URL = "/static/"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Also serve the built SPA (frontend/dist) at the root via WhiteNoise.
# WHITENOISE_INDEX_FILE makes it return index.html for directory requests
# like '/'. Routes that aren't files (e.g. /projects) fall through to Django's
# spa_view, which also returns index.html so React Router can take over.
WHITENOISE_ROOT = FRONTEND_DIST_DIR  # noqa: F405 (from base.py *)
WHITENOISE_INDEX_FILE = True

# CSRF trusted origins in prod come from ALLOWED_HOSTS
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h and h != "*"]

# Database — Cloud SQL via Unix socket
# DATABASE_URL format: postgres://USER:PASSWORD@//cloudsql/PROJECT:REGION:INSTANCE/DBNAME
# django-environ handles the //cloudsql/ socket path automatically

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": '{"severity":"%(levelname)s","message":"%(message)s","module":"%(module)s"}',
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
