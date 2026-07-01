"""StripScriptName ASGI middleware — strips the /canopy prefix so the inner
Starlette (MCP at /api/mcp) + Django routers see unprefixed paths."""
import pytest

from config.asgi_prefix import StripScriptName


class _Recorder:
    """A trivial ASGI app that records the scope path it was called with."""
    def __init__(self):
        self.seen_path = None
        self.seen_root = None

    async def __call__(self, scope, receive, send):
        self.seen_path = scope.get("path")
        self.seen_root = scope.get("root_path")


async def _call(mw, path, scope_type="http"):
    rec = mw.app
    await mw({"type": scope_type, "path": path, "raw_path": path.encode()}, None, None)
    return rec.seen_path


@pytest.mark.asyncio
async def test_strips_prefix_from_http_path():
    mw = StripScriptName(_Recorder(), "/canopy")
    assert await _call(mw, "/canopy/api/me") == "/api/me"
    assert await _call(mw, "/canopy/api/mcp") == "/api/mcp"


@pytest.mark.asyncio
async def test_bare_prefix_becomes_root():
    mw = StripScriptName(_Recorder(), "/canopy")
    assert await _call(mw, "/canopy") == "/"
    assert await _call(mw, "/canopy/") == "/"


@pytest.mark.asyncio
async def test_non_matching_path_untouched():
    mw = StripScriptName(_Recorder(), "/canopy")
    # a path that doesn't start with the prefix is passed through verbatim
    assert await _call(mw, "/canopyfoo/x") == "/canopyfoo/x"
    assert await _call(mw, "/other") == "/other"


@pytest.mark.asyncio
async def test_strips_on_websocket_too():
    mw = StripScriptName(_Recorder(), "/canopy")
    assert await _call(mw, "/canopy/ws/sessions/abc", scope_type="websocket") == "/ws/sessions/abc"


@pytest.mark.asyncio
async def test_empty_prefix_is_noop():
    mw = StripScriptName(_Recorder(), "")
    assert await _call(mw, "/canopy/api/me") == "/canopy/api/me"
