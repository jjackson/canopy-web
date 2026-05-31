"""The /api/mcp/ ASGI mount must be gated by CANOPY_MCP_BEARER.

The FastMCP SSE app sits outside Django's auth middleware, so the gate in
config.asgi is the only thing standing between the public internet and the
MCP tools (which re-enter the REST API with the server's bearer).
"""

import os
from unittest import mock

from config.asgi import _mcp_authorized


def _scope(auth: str | None = None):
    headers = []
    if auth is not None:
        headers.append((b"authorization", auth.encode("latin-1")))
    return {"type": "http", "path": "/api/mcp/sse", "headers": headers}


def test_rejects_when_bearer_unset():
    """Fail closed: no configured token => mount unreachable even with a header."""
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CANOPY_MCP_BEARER", None)
        assert _mcp_authorized(_scope("Bearer anything")) is False
        assert _mcp_authorized(_scope(None)) is False


def test_rejects_missing_or_wrong_token():
    with mock.patch.dict(os.environ, {"CANOPY_MCP_BEARER": "secret-pat"}):
        assert _mcp_authorized(_scope(None)) is False
        assert _mcp_authorized(_scope("Bearer wrong")) is False
        assert _mcp_authorized(_scope("secret-pat")) is False  # missing "Bearer "
        assert _mcp_authorized(_scope("Bearer secret-pat ")) is False  # trailing space


def test_accepts_exact_match():
    with mock.patch.dict(os.environ, {"CANOPY_MCP_BEARER": "secret-pat"}):
        assert _mcp_authorized(_scope("Bearer secret-pat")) is True
