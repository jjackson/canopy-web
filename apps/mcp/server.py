"""The canopy-web FastMCP server instance.

Auth model — dual auth via FastMCP `MultiAuth`:

  * PAT (priority, always on): `CanopyPATVerifier` resolves a per-user
    Personal Access Token to the Django user. This is the path machine
    callers (CLIs, agents) use today; it replaces the old single shared
    `CANOPY_MCP_BEARER`.

  * OAuth (interactive, env-gated seam): when the Google OAuth client
    creds are present AND `MCP_OAUTH_ENABLED=true`, a FastMCP
    `GoogleProvider` is wired as the MultiAuth `server=`, letting
    interactive MCP clients browser-login with Google. It is OFF by
    default — see the note in `_build_oauth_provider` for why it is a
    seam rather than always-on.

Tools are registered as a side effect of importing `apps.mcp.tools`.

The module exposes:
  * `mcp`            — the FastMCP instance (auth attached)
  * `build_http_app()` — builds the Streamable-HTTP ASGI app (called
    once from config/asgi.py at mount time)
"""
from __future__ import annotations

import logging

from django.conf import settings
from fastmcp import FastMCP
from fastmcp.server.auth import MultiAuth

from .auth import CanopyPATVerifier

logger = logging.getLogger(__name__)


def _mcp_base_url() -> str:
    """Public base URL where the MCP mount is reachable.

    Used by the OAuth provider for redirect/discovery metadata. Defaults
    to the configured public origin + the /api/mcp mount path.
    """
    return getattr(settings, "MCP_BASE_URL", "") or "http://localhost:8000/api/mcp"


def _build_oauth_provider():
    """Return a FastMCP OAuth provider, or None if the seam is disabled.

    SEAM (intentionally easy to complete, OFF by default):

    canopy-web already owns a Google OAuth client (GOOGLE_OAUTH_CLIENT_ID
    / GOOGLE_OAUTH_CLIENT_SECRET) — but it is registered for django-allauth's
    redirect URI, not FastMCP's. Turning OAuth on therefore also requires
    registering FastMCP's redirect path ("<MCP_BASE_URL>/auth/callback")
    in the Google Cloud console, and verifying token claims map to a real
    canopy-web user. Rather than ship a half-working OAuth path that breaks
    the PAT priority, we gate it behind `MCP_OAUTH_ENABLED`.

    To complete the seam:
      1. Add "<MCP_BASE_URL>/auth/callback" as an authorized redirect URI
         on the existing Google OAuth client.
      2. Set MCP_OAUTH_ENABLED=true and MCP_BASE_URL=<public mount url>.
      3. (Optional) map GoogleProvider token claims (email) to a Django
         user, the same domain restriction allauth applies.
    """
    if not getattr(settings, "MCP_OAUTH_ENABLED", False):
        return None

    client_id = settings.SOCIALACCOUNT_PROVIDERS.get("google", {}).get("APP", {}).get("client_id", "")
    client_secret = settings.SOCIALACCOUNT_PROVIDERS.get("google", {}).get("APP", {}).get("secret", "")
    if not client_id or not client_secret:
        logger.warning("MCP_OAUTH_ENABLED but Google OAuth creds missing; OAuth disabled.")
        return None

    from fastmcp.server.auth.providers.google import GoogleProvider

    return GoogleProvider(
        client_id=client_id,
        client_secret=client_secret,
        base_url=_mcp_base_url(),
        required_scopes=[
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
        ],
    )


def _build_auth() -> MultiAuth:
    """Dual auth: OAuth (optional seam) + the always-on PAT verifier."""
    return MultiAuth(
        server=_build_oauth_provider(),
        verifiers=[CanopyPATVerifier()],
    )


mcp = FastMCP("canopy-web", auth=_build_auth())

# Registering tools is a side effect of importing the tools package.
from . import tools  # noqa: E402,F401


def build_http_app():
    """Build the Streamable-HTTP ASGI app for mounting at /api/mcp/.

    `path="/"` because config/asgi.py mounts this app under the
    /api/mcp prefix; the MCP endpoint then lives at /api/mcp/.
    """
    return mcp.http_app(path="/", transport="streamable-http")
