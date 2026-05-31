"""
ASGI config for canopy-web project.

It exposes the ASGI callable as a module-level variable named ``application``.

The FastMCP 3.x Streamable-HTTP server (apps/mcp) is mounted at /api/mcp/.
Auth is enforced INSIDE the MCP app via FastMCP MultiAuth (per-user PAT +
optional OAuth) — there is no hand-rolled gate here anymore.

Streamable-HTTP requires the MCP app's lifespan to run for session
management. Django's bare ASGI app has no lifespan, so we build a
combined app: a Starlette router that mounts the Django ASGI app at "/"
and the MCP app under /api/mcp, with the MCP app's lifespan wired into
the Starlette app. Starlette owns the ASGI `lifespan` events; Django
sub-mounts only ever see `http`/`websocket` scopes.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

from django.core.asgi import get_asgi_application  # noqa: E402

# Initialize Django (populates the app registry) before importing any
# module that touches ORM models (apps.mcp.server imports tools that
# import services/models).
_django_asgi_app = get_asgi_application()

from starlette.applications import Starlette  # noqa: E402
from starlette.routing import Mount  # noqa: E402

from apps.mcp.server import build_http_app  # noqa: E402

_MCP_PREFIX = "/api/mcp"

# Streamable-HTTP ASGI app. path="/" -> the MCP endpoint is the mount
# root, i.e. /api/mcp/.
_mcp_app = build_http_app()

application = Starlette(
    routes=[
        Mount(_MCP_PREFIX, app=_mcp_app),
        # Django handles everything else (mounted last as the catch-all).
        Mount("/", app=_django_asgi_app),
    ],
    # Run the MCP session-manager lifespan for the whole process.
    lifespan=_mcp_app.lifespan,
)
