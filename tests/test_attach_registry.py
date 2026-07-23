from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.canopy_sessions import attach

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


def test_renew_preserves_count_and_refreshes():
    sid = "11111111111111111111111111111111"
    attach.attach(sid)
    attach.attach(sid)          # count = 2
    assert attach.renew(sid) == 2
    assert attach.count(sid) == 2   # renewal must NOT change the count, only the TTL


def test_renew_is_noop_when_nothing_attached():
    sid = "22222222222222222222222222222222"
    assert attach.renew(sid) == 0
    assert attach.count(sid) == 0   # renew never resurrects / creates a phantom viewer


def test_renew_extends_the_key_ttl():
    """Prove renew() actually re-writes the cache key with a fresh TTL, not just
    reads the count. A no-op renew (delete the cache.set call in renew()) would
    still satisfy test_renew_preserves_count_and_refreshes — that test only
    checks the count survives, never that the TTL write happened. Spy on
    cache.set directly so this test fails red if that write is removed."""
    sid = "33333333333333333333333333333333"
    attach.attach(sid)
    attach.attach(sid)  # count = 2
    key = attach._key(sid)

    with patch("apps.canopy_sessions.attach.cache.set") as mock_set:
        result = attach.renew(sid)

    assert result == 2
    mock_set.assert_called_once_with(key, 2, timeout=attach._TTL)


def test_renew_does_not_call_cache_set_when_nothing_attached():
    """The no-op case must not just leave the count unchanged (that's already
    covered above) — it must not write to the cache at all, so a renew on a
    never-attached/expired session can't phantom-resurrect the key."""
    sid = "44444444444444444444444444444444"

    with patch("apps.canopy_sessions.attach.cache.set") as mock_set:
        result = attach.renew(sid)

    assert result == 0
    mock_set.assert_not_called()
