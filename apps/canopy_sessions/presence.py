"""Ephemeral presence — who is in a session right now.

Cache-backed (LocMem in dev/test, the connectlabs Redis in prod) with a TTL
heartbeat, mirroring ace-web's Redis HASH but through Django's cache abstraction so
it's testable without standalone Redis. The durable membership authority is
SessionParticipant; this is only the live "who's here" set.

KNOWN LOSSINESS (follow-up, tied to the prod Redis cutover): touch/leave do a
non-atomic get→mutate→set, so on the Redis-backed prod path concurrent updates to
one session can drop an entry (last writer wins the whole hash). Presence is
advisory — a lost entry only flickers a user absent until their next heartbeat (and
can briefly free the derived draft lock) — but the durable path should move to
native Redis HASH field atomics (hset/hdel + per-field expiry) as ace-web did.
"""
from __future__ import annotations

import datetime as dt

from django.core.cache import cache
from django.utils import timezone

PRESENCE_TTL_SECONDS = 60  # a heartbeat renews within this window


def _key(session_id) -> str:
    sid = session_id.hex if hasattr(session_id, "hex") else str(session_id)
    return f"chat:presence:{sid}"


def touch(session_id, user_id, *, ttl: int = PRESENCE_TTL_SECONDS) -> None:
    key = _key(session_id)
    data = dict(cache.get(key) or {})
    data[str(user_id)] = (timezone.now() + dt.timedelta(seconds=ttl)).timestamp()
    cache.set(key, data, timeout=ttl * 2)


def leave(session_id, user_id) -> None:
    key = _key(session_id)
    data = dict(cache.get(key) or {})
    if data.pop(str(user_id), None) is not None:
        cache.set(key, data, timeout=PRESENCE_TTL_SECONDS * 2)


def present_ids(session_id) -> set[int]:
    data = cache.get(_key(session_id)) or {}
    now = timezone.now().timestamp()
    return {int(uid) for uid, expiry in data.items() if expiry > now}


def is_present(session_id, user_id) -> bool:
    return int(user_id) in present_ids(session_id)
