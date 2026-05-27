"""FastMCP server exposing canopy-web's v2 routes as MCP tools.

Strategy: walk the live OpenAPI schema and register one MCP tool per
(path, method) marked `x-mcp-expose: true` in its OpenAPI extension.
Endpoints opt in via `openapi_extra={"x-mcp-expose": True}` on the
Ninja route decorator.

Each tool invokes the same endpoint via an HTTP loopback call with a
Bearer token for authentication — reuses every middleware (auth,
CSRF, throttling) and behaves identically to a frontend caller.

Auth model: machine callers present `Authorization: Bearer <WORKBENCH_WRITE_TOKEN>`
(the existing canopy-web Bearer-bypass mechanism). MCP tools include
this header automatically via env-var `CANOPY_MCP_BEARER`.

Mounting: This module exposes `mcp_starlette_app`, a Starlette ASGI app
(SSE transport) that is mounted at /api/mcp/ in config/asgi.py via a
thin path-dispatching wrapper. FastMCP 0.4.x does not provide a
Django-mountable view; the ASGI-level mount is the proper integration
point for Starlette-backed sub-applications.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route

from .api import api as ninja_api

mcp = FastMCP("canopy-web")

BACKEND_BASE = os.environ.get("CANOPY_MCP_LOOPBACK_BASE", "http://localhost:8000")
BEARER = os.environ.get("CANOPY_MCP_BEARER", "")

# SSE message endpoint is relative to the /api/mcp/ mount prefix.
# Starlette sees paths after the prefix is stripped by the dispatcher.
_sse = SseServerTransport("/messages")


def _build_tool(path: str, method: str, op: dict[str, Any], operation_id: str):
    """Register one MCP tool for a (path, method) endpoint.

    The tool's kwargs map onto path/query/body params; path placeholders
    like {slug} are filled from kwargs and removed before the HTTP call.
    """
    summary = op.get("summary") or op.get("description") or operation_id

    async def _tool(**kwargs: Any) -> Any:
        # Substitute path params; collect the rest for query string or body.
        url_path = path
        leftover: dict[str, Any] = {}
        for key, value in kwargs.items():
            placeholder = "{" + key + "}"
            if placeholder in url_path:
                url_path = url_path.replace(placeholder, str(value))
            else:
                leftover[key] = value
        url = f"{BACKEND_BASE}{url_path}"
        headers = {"Authorization": f"Bearer {BEARER}"} if BEARER else {}
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method.lower() == "get":
                resp = await client.get(url, params=leftover, headers=headers)
            else:
                resp = await client.request(method.upper(), url, json=leftover, headers=headers)
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            return resp.text

    # Give the inner function a unique name so FastMCP's tool manager can
    # distinguish tools registered in a loop (otherwise all closures share
    # the same __name__ = "_tool").
    _tool.__name__ = operation_id
    _tool.__qualname__ = f"mcp_tool.{operation_id}"

    mcp.add_tool(_tool, name=operation_id, description=summary)
    return _tool


def register_tools() -> None:
    """Walk the OpenAPI schema and register tools for opted-in endpoints."""
    schema = ninja_api.get_openapi_schema()
    for path, methods in schema.get("paths", {}).items():
        for method, op in methods.items():
            if method not in {"get", "post", "patch", "delete"}:
                continue
            if not op.get("x-mcp-expose"):
                continue
            operation_id = (
                op.get("operationId")
                or f"{method}_{path.replace('/', '_').replace('{', '').replace('}', '')}"
            )
            _build_tool(path, method, op, operation_id)


register_tools()


# ---------------------------------------------------------------------------
# Starlette SSE ASGI app — mounted at /api/mcp/ in config/asgi.py.
# FastMCP 0.4.x builds this same app internally in run_sse_async(); we
# replicate the construction here so we can reuse the app without spawning
# a separate server process.
# ---------------------------------------------------------------------------

async def _handle_sse(request):
    async with _sse.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp._mcp_server.run(
            streams[0],
            streams[1],
            mcp._mcp_server.create_initialization_options(),
        )


async def _handle_messages(request):
    await _sse.handle_post_message(request.scope, request.receive, request._send)


mcp_starlette_app = Starlette(
    routes=[
        Route("/sse", endpoint=_handle_sse),
        Route("/messages", endpoint=_handle_messages, methods=["POST"]),
    ],
)
