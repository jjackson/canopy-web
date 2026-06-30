"""Django settings for canopy-web deployed to the connect-labs AWS environment.

canopy-web runs as the third tenant on labs.connect.dimagi.com:
  - connect-labs (the primary) at the root
  - ace-web at /ace
  - canopy-web at /canopy   ← this

Inherits production security; configures for ALB TLS termination, the /canopy
path prefix, tenant-unique path-scoped cookies, the shared RDS (canopy_web DB),
and the shared ElastiCache Redis (cache now; Channels layer lands with W4).
Mirrors ace-web's connectlabs.py.
"""
from .production import *  # noqa: F401, F403

import environ  # noqa: E402

env = environ.Env()

# ALB terminates TLS at the edge; the ALB -> container hop is plain HTTP. Trust
# X-Forwarded-Proto so request.scheme is "https" and OAuth callback URLs are
# built as https:// (Google rejects http:// redirect_uris).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False  # ALB handles the redirect

ALLOWED_HOSTS = ["labs.connect.dimagi.com"]

# Served under /canopy on the shared ALB.
FORCE_SCRIPT_NAME = env("FORCE_SCRIPT_NAME", default="/canopy")

# `@login_required`/allauth build redirects from LOGIN_URL via resolve_url,
# which does NOT prepend FORCE_SCRIPT_NAME — so it must already carry /canopy,
# else an anonymous hit redirects to a path owned by a sibling labs tenant.
LOGIN_URL = "/canopy/accounts/google/login/"

# Tenant-unique, path-scoped cookies so state doesn't collide with or leak to
# the sibling tenants (connect-labs root, ace at /ace) on the shared hostname.
SESSION_COOKIE_NAME = "sessionid_canopy"
CSRF_COOKIE_NAME = "csrftoken_canopy"
SESSION_COOKIE_PATH = "/canopy/"
CSRF_COOKIE_PATH = "/canopy/"

CSRF_TRUSTED_ORIGINS = ["https://labs.connect.dimagi.com"]

# Static served under the prefix (the SPA's own assets are emitted by Vite with
# base=/canopy/; this covers Django/admin/staticfiles).
STATIC_URL = "/canopy/static/"

# Shared RDS (a dedicated canopy_web database on labs-jj-postgres).
DATABASES = {"default": env.db("DATABASE_URL")}

# Shared ElastiCache Redis. canopy uses a dedicated DB index (REDIS_URL ends in
# /1) so its keyspace doesn't collide with ace/connect-labs. The Channels layer
# (CHANNEL_LAYERS) is added in W4.1 once `channels` is a dependency; this cache
# config is the same endpoint and is safe to ship now.
_REDIS_URL = env("REDIS_URL", default="")
if _REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _REDIS_URL,
        }
    }
