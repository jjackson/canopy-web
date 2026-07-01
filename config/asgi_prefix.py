"""ASGI middleware that strips a script-name prefix (e.g. ``/canopy``) from
incoming http/websocket scopes.

canopy-web runs as a path-prefixed tenant on labs.connect.dimagi.com/canopy, but
its monolith has no nginx to strip the prefix (ace-web relies on nginx for /ace).
The ALB forwards ``/canopy/...`` verbatim to the container, where the ASGI app is
a Starlette router mounting MCP at ``/api/mcp`` and Django at ``/`` — so an
unstripped ``/canopy/api/mcp`` would miss the MCP mount and ``/canopy/api/me``
would reach Django as ``/canopy/api/me`` (no route).

This middleware strips the prefix on the way IN (so the inner routers see
``/api/mcp``, ``/api/me``, …); ``FORCE_SCRIPT_NAME`` independently re-adds it to
URLs Django GENERATES (redirects, reverse(), static). Mirrors what ace-web's
nginx does, but keeps canopy's single-container model.

No-op when ``prefix`` is empty (i.e. every non-labs environment).
"""
from __future__ import annotations


class StripScriptName:
    def __init__(self, app, prefix: str):
        self.app = app
        self.prefix = (prefix or "").rstrip("/")

    async def __call__(self, scope, receive, send):
        if self.prefix and scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if path == self.prefix or path.startswith(self.prefix + "/"):
                stripped = path[len(self.prefix):] or "/"
                scope = dict(scope)
                scope["path"] = stripped
                if scope.get("raw_path") is not None:
                    # preserve any query string already split out of raw_path
                    scope["raw_path"] = stripped.encode("utf-8")
        await self.app(scope, receive, send)
