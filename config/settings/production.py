"""
Production Django settings for Cloud Run + Cloud SQL deployment.
"""
from .base import *  # noqa: F401, F403

DEBUG = False

# Cloud Run sets PORT; uvicorn binds to it
ALLOWED_HOSTS = env("ALLOWED_HOSTS", default="*").split(",")

# Security headers — Cloud Run terminates TLS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

# Static files — served by frontend nginx, not Django
STATIC_URL = "/static/"

# Database — Cloud SQL via Unix socket
# DATABASE_URL format: postgres://USER:PASSWORD@//cloudsql/PROJECT:REGION:INSTANCE/DBNAME
# django-environ handles the //cloudsql/ socket path automatically

# CORS — allow all in production for now (single-tenant, no auth)
CORS_ALLOW_ALL_ORIGINS = True

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
