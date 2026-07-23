"""Cache-backed count of attached viewers per session — the "is anyone watching?"
signal that drives live streaming. Mirrors presence.py (get->mutate->set through
Django's cache), but a COUNT rather than a set: streaming stays desired while >=1
viewer is attached and stops at zero. A crashed viewer that never detaches leaves
the count high (streaming stays on) until the row is otherwise cleared — acceptable
for a single user; the count is renewed on the chat WS heartbeat (`renew`, called
from `SessionConsumer`'s `presence.heartbeat` handler), so a connected viewer never
loses it even across a >1h session."""
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


def renew(session_id) -> int:
    """Re-write the current count with a fresh TTL so a long-lived viewer doesn't
    lose its attach count. Without this the key expires after _TTL and a later
    detach reads 0 -> the 1->0 edge fires and clears stream_desired while a viewer
    is still attached (and miscounts the edge in a multi-viewer session). Mirrors
    presence.touch's renew-on-heartbeat. No-op when nothing is attached."""
    key = _key(session_id)
    n = int(cache.get(key) or 0)
    if n > 0:
        cache.set(key, n, timeout=_TTL)
    return n
