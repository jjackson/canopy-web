"""
ASGI config for canopy-web project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

_django_asgi_app = get_asgi_application()

# Mount the FastMCP SSE server at /api/mcp/ via a thin path-dispatching
# wrapper.  We do this at the ASGI layer (not in urls.py) because FastMCP
# produces a Starlette ASGI app that cannot be registered as a Django view
# directly.  The dispatcher strips the /api/mcp prefix from scope['path']
# before forwarding to the Starlette sub-app, which then routes /sse and
# /messages internally.
#
# Import is deferred inside the wrapper to avoid loading Django models
# before the app registry is ready (asgi.py is evaluated very early).

_MCP_PREFIX = "/api/mcp"


async def application(scope, receive, send):
    if scope["type"] == "http" and scope.get("path", "").startswith(_MCP_PREFIX):
        # Lazy-import so Django's app registry is fully loaded before we
        # touch apps.api.mcp_server (which imports ORM-backed modules).
        from apps.api.mcp_server import mcp_starlette_app  # noqa: PLC0415

        stripped_scope = dict(scope)
        stripped_scope["path"] = scope["path"][len(_MCP_PREFIX):] or "/"
        stripped_scope["root_path"] = scope.get("root_path", "") + _MCP_PREFIX
        await mcp_starlette_app(stripped_scope, receive, send)
    else:
        await _django_asgi_app(scope, receive, send)
