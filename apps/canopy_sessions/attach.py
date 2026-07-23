"""Cache-backed count of attached viewers per session — the "is anyone watching?"
signal that drives live streaming. Mirrors presence.py (get->mutate->set through
Django's cache), but a COUNT rather than a set: streaming stays desired while >=1
viewer is attached and stops at zero. A crashed viewer that never detaches leaves
the count high (streaming stays on) until the row is otherwise cleared — acceptable
for a single user; presence's TTL is the eventual backstop."""
from __future__ import annotations

from django.core.cache import cache

_TTL = 3600  # long; a live WS connection refreshes nothing, so keep it well above a session


def _key(session_id) -> str:
    sid = session_id.hex if hasattr(session_id, "hex") else str(session_id)
    return f"chat:attach:{sid}"


def attach(session_id) -> int:
    key = _key(session_id)
    n = int(cache.get(key) or 0) + 1
    cache.set(key, n, timeout=_TTL)
    return n


def detach(session_id) -> int:
    key = _key(session_id)
    n = max(0, int(cache.get(key) or 0) - 1)
    cache.set(key, n, timeout=_TTL)
    return n


def count(session_id) -> int:
    return int(cache.get(_key(session_id)) or 0)
