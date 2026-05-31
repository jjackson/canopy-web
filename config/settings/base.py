"""
Base Django settings for canopy-web.

Common settings shared across all environments.
"""
import os
import sys
from pathlib import Path

import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Add canopy submodule to sys.path if it exists
CANOPY_DIR = BASE_DIR / "canopy"
if CANOPY_DIR.exists():
    sys.path.insert(0, str(CANOPY_DIR))

# Environment
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)

# Read .env file if it exists
env_file = BASE_DIR / ".env"
if env_file.exists():
    env.read_env(str(env_file))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-me-in-production")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "corsheaders",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    # Local apps
    "apps.common",
    "apps.collections",
    "apps.workspace",
    "apps.skills",
    "apps.evals",
    "apps.projects",
    "apps.walkthroughs",
    "apps.tokens",
    "apps.reviews",
    "apps.mcp",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.tokens.middleware.BearerTokenAuthMiddleware",  # PAT bearer auth (after AuthenticationMiddleware, before LoginRequired)
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.common.middleware.LoginRequiredMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ASGI_APPLICATION = "config.asgi.application"

# Database
DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://localhost:5432/canopy_web"),
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Frontend SPA build output (served by catch-all view; WhiteNoise handles assets)
FRONTEND_DIST_DIR = BASE_DIR / "frontend" / "dist"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Authentication
SITE_ID = 1
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_URL = "/accounts/google/login/"
LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"

# allauth
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*"]
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_ADAPTER = "apps.common.auth_adapter.CustomSocialAccountAdapter"
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": env("GOOGLE_OAUTH_CLIENT_ID", default=""),
            "secret": env("GOOGLE_OAUTH_CLIENT_SECRET", default=""),
            "key": "",
        },
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
    }
}

# Restrict Google login to this email domain (empty = allow all)
AUTH_ALLOWED_EMAIL_DOMAIN = env("AUTH_ALLOWED_EMAIL_DOMAIN", default="dimagi.com")

# Whether LoginRequiredMiddleware enforces auth. Default on; toggle off during rollout.
REQUIRE_AUTH = env.bool("REQUIRE_AUTH", default=True)

# --- Walkthrough sharing (apps/walkthroughs) ---
# When False, all /api/walkthroughs/ endpoints 404 (rollout flag).
WALKTHROUGHS_ENABLED = env.bool("WALKTHROUGHS_ENABLED", default=True)

# Google Service Account JSON for the Drive that stores walkthrough
# files. Empty string disables uploads/downloads (returns 500 with
# code="drive-not-configured" — same affordance as ace-web).
CANOPY_DRIVE_SA_KEY_JSON = env("CANOPY_DRIVE_SA_KEY_JSON", default="")

# ID of the shared-drive folder under which "walkthroughs/<uuid>/"
# subfolders are created.
CANOPY_DRIVE_ROOT_FOLDER_ID = env("CANOPY_DRIVE_ROOT_FOLDER_ID", default="")

# Max upload size in bytes for a single walkthrough file. 75 MB covers
# small videos and large HTML decks.
WALKTHROUGH_MAX_UPLOAD_BYTES = env.int(
    "WALKTHROUGH_MAX_UPLOAD_BYTES", default=75 * 1024 * 1024,
)

# Machine-caller authentication: see apps/tokens/ for Personal Access
# Tokens. Mint with `manage.py create_token --email X --label Y`; the
# raw value goes in the `Authorization: Bearer <raw>` header and
# `apps.tokens.middleware.BearerTokenAuthMiddleware` resolves it to a
# real Django user. The legacy shared-secret WORKBENCH_WRITE_TOKEN +
# CANOPY_E2E_AUTH_TOKEN env vars were retired by the PAT refactor.

# --- MCP server (apps/mcp) -------------------------------------------
# FastMCP 3.x Streamable-HTTP server mounted at /api/mcp/. Auth is dual
# (MultiAuth): per-user Personal Access Token (always on) + Google OAuth
# (env-gated seam, off by default — see apps/mcp/server.py).
#
# Public base URL of the MCP mount (used for OAuth discovery/redirect
# metadata only). Set to the deployed origin + "/api/mcp" when OAuth is on.
MCP_BASE_URL = env("MCP_BASE_URL", default="")
# Turn on the interactive Google OAuth path. Requires the FastMCP redirect
# URI ("<MCP_BASE_URL>/auth/callback") to be registered on the Google
# OAuth client. PAT auth works regardless of this flag.
MCP_OAUTH_ENABLED = env.bool("MCP_OAUTH_ENABLED", default=False)
# Per-user write rate limit for mutating MCP tools (e.g. clear_insights).
MCP_WRITE_LIMIT = env.int("MCP_WRITE_LIMIT", default=10)
MCP_WRITE_WINDOW_SECONDS = env.int("MCP_WRITE_WINDOW_SECONDS", default=60)

# AI Backend: "api" (direct Anthropic SDK) or "cli" (claude code CLI)
AI_BACKEND = env("AI_BACKEND", default="api")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")

# CORS
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True

