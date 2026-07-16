import pytest

from apps.api.pagination import Page, clamp_limit, clamp_offset, paginate


def test_paginate_returns_page_with_metadata():
    items = list(range(95))
    page = paginate(items, offset=20, limit=25)
    assert isinstance(page, Page)
    assert page.items == list(range(20, 45))
    assert page.total == 95
    assert page.offset == 20
    assert page.limit == 25


def test_paginate_handles_overflow_gracefully():
    items = list(range(10))
    page = paginate(items, offset=50, limit=25)
    assert page.items == []
    assert page.total == 10


def test_paginate_defaults():
    items = list(range(5))
    page = paginate(items, offset=0, limit=100)
    assert page.items == items
    assert page.total == 5


# ---- clamps -----------------------------------------------------------------
# These pin the *floor*, not just the cap. An unfloored `min(limit, cap)` lets 0
# and negatives reach Page.limit (ge=1), where pydantic raises inside the
# response model and the route can only answer 500.


@pytest.mark.parametrize(("supplied", "expected"), [
    (0, 1), (-5, 1),          # floor: the bug this helper exists for
    (1, 1), (25, 25), (500, 500),   # pass-through inside the range
    (501, 500), (99999, 500),       # cap
])
def test_clamp_limit_lands_inside_page_limit_bounds(supplied, expected):
    assert clamp_limit(supplied) == expected
    # whatever comes out must satisfy Page.limit's own constraint
    Page[int](items=[], total=0, offset=0, limit=clamp_limit(supplied))


def test_clamp_limit_respects_a_route_specific_cap():
    # the cap is route policy (payload cost) and varies; the floor never does
    assert clamp_limit(99999, cap=100) == 100
    assert clamp_limit(0, cap=100) == 1


@pytest.mark.parametrize(("supplied", "expected"), [(-1, 0), (0, 0), (20, 20)])
def test_clamp_offset_lands_inside_page_offset_bounds(supplied, expected):
    assert clamp_offset(supplied) == expected
    Page[int](items=[], total=0, offset=clamp_offset(supplied), limit=1)
