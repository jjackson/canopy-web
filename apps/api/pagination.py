"""Offset/limit pagination shared across v2 list endpoints.

Every list endpoint declares its response as `Page[ItemSchema]` so
the OpenAPI schema knows the item type.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)


#: Default upper bound for a list route's page size. Routes with a cheaper
#: payload budget pass their own ``cap``; the *floor* is not negotiable — it is
#: dictated by ``Page.limit``'s ``ge=1`` (see ``clamp_limit``).
DEFAULT_LIMIT_CAP = 500


def clamp_limit(limit: int, *, cap: int = DEFAULT_LIMIT_CAP) -> int:
    """Clamp a caller-supplied ``?limit=`` into ``Page.limit``'s valid range.

    The floor matters as much as the cap: ``Page.limit`` is ``Field(ge=1, le=500)``,
    so an unfloored ``min(limit, cap)`` lets ``?limit=0`` or ``?limit=-5`` through
    to the *response* model, where pydantic raises **inside** serialization and
    Django Ninja can only answer 500. Clamping here keeps a nonsense limit a
    harmless no-op instead of a server error.

    The cap varies by route (payload cost); the floor never does — hence one
    helper with an overridable ``cap`` rather than N copies of ``max(1, min(...))``.
    """
    return max(1, min(limit, cap))


def clamp_offset(offset: int) -> int:
    """Clamp a caller-supplied ``?offset=`` into ``Page.offset``'s valid range.

    Same failure mode as ``clamp_limit``: ``Page.offset`` is ``Field(ge=0)``, so a
    negative offset 500s inside the response model. It would also silently slice
    from the *end* of the list on the way there.
    """
    return max(0, offset)


def paginate(items: Sequence[T], *, offset: int, limit: int) -> Page[T]:
    total = len(items)
    sliced = list(items[offset : offset + limit])
    return Page(items=sliced, total=total, offset=offset, limit=limit)
