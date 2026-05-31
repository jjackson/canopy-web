"""Per-user write rate limiting for mutating MCP tools."""
from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import override_settings

from apps.mcp.rate_limit import RateLimitError, check_write_limit


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@override_settings(MCP_WRITE_LIMIT=3, MCP_WRITE_WINDOW_SECONDS=60)
def test_allows_up_to_limit():
    for _ in range(3):
        check_write_limit("user-1")  # no raise


@override_settings(MCP_WRITE_LIMIT=3, MCP_WRITE_WINDOW_SECONDS=60)
def test_raises_over_limit():
    for _ in range(3):
        check_write_limit("user-1")
    with pytest.raises(RateLimitError):
        check_write_limit("user-1")


@override_settings(MCP_WRITE_LIMIT=2, MCP_WRITE_WINDOW_SECONDS=60)
def test_limits_are_per_user():
    check_write_limit("user-1")
    check_write_limit("user-1")
    # A different user has their own budget.
    check_write_limit("user-2")
    check_write_limit("user-2")
    with pytest.raises(RateLimitError):
        check_write_limit("user-1")
