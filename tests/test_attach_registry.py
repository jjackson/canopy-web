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
