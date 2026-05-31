"""
ASGI config for canopy-web project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import hmac
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


def _mcp_authorized(scope) -> bool:
    """Gate the public /api/mcp/ mount.

    The MCP SSE app sits OUTSIDE Django's auth middleware, so without this
    check anyone on the internet could drive its tools (which re-enter the
    REST API with the server's bearer). We require the caller to present the
    same token the server uses for its loopback: ``CANOPY_MCP_BEARER``.

    Fail closed: if ``CANOPY_MCP_BEARER`` is unset, the mount is unreachable
    (no token can match an empty expected value).
    """
    expected = os.environ.get("CANOPY_MCP_BEARER", "")
    if not expected:
        return False
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            return hmac.compare_digest(
                value.decode("latin-1"), f"Bearer {expected}"
            )
    return False


async def _send_401(send) -> None:
    await send({
        "type": "http.response.start",
        "status": 401,
        "headers": [
            (b"content-type", b"application/json"),
            (b"www-authenticate", b'Bearer realm="canopy-web-mcp"'),
        ],
    })
    await send({
        "type": "http.response.body",
        "body": b'{"detail":"MCP mount requires a valid bearer token."}',
    })


async def application(scope, receive, send):
    if scope["type"] == "http" and scope.get("path", "").startswith(_MCP_PREFIX):
        if not _mcp_authorized(scope):
            await _send_401(send)
            return
        # Lazy-import so Django's app registry is fully loaded before we
        # touch apps.api.mcp_server (which imports ORM-backed modules).
        from apps.api.mcp_server import mcp_starlette_app  # noqa: PLC0415

        stripped_scope = dict(scope)
        stripped_scope["path"] = scope["path"][len(_MCP_PREFIX):] or "/"
        stripped_scope["root_path"] = scope.get("root_path", "") + _MCP_PREFIX
        await mcp_starlette_app(stripped_scope, receive, send)
    else:
        await _django_asgi_app(scope, receive, send)
