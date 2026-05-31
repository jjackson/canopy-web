"""The MCP server + ASGI mount construct without error.

The lifespan/mount wiring in config/asgi.py is the riskiest part of the
rebuild, so we assert it imports and builds a Starlette app with the MCP
app mounted and its lifespan attached.
"""
from __future__ import annotations

from starlette.applications import Starlette

from apps.mcp.server import build_http_app, mcp


def test_mcp_instance_uses_pat_verifier():
    from apps.mcp.auth import CanopyPATVerifier

    assert isinstance(mcp.auth, CanopyPATVerifier)


def test_build_http_app_constructs():
    app = build_http_app()
    assert app is not None
    assert hasattr(app, "lifespan")


def test_asgi_application_is_starlette_with_mcp_mount():
    import config.asgi as asgi

    assert isinstance(asgi.application, Starlette)
    # The MCP app's lifespan must be the app lifespan (session manager).
    assert asgi.application.router.lifespan_context is not None
    mounts = [r for r in asgi.application.routes if getattr(r, "path", "") == "/api/mcp"]
    assert mounts, "expected an /api/mcp mount"
