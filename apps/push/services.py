"""Push policy. The only place that decides WHETHER to push.

The trigger problem: apps.agents.services.needs_you() is an aggregation (tasks +
run gates + failed steps), so nothing emits "the fleet needs you now". We
snapshot each agent's waiting_count and push only when it goes UP.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.db import transaction
from pywebpush import WebPushException, webpush

from apps.agents.models import Agent
from apps.agents.services import needs_you

from .models import AgentWaitingSnapshot, PushSubscription

logger = logging.getLogger(__name__)

# Agents touched in the current transaction. Flushed once in on_commit, so a
# bulk sync of N tasks is ONE recompute per agent rather than N.
_dirty: set[int] = set()


def _send_one(sub: PushSubscription, payload: dict) -> None:
    """The raw send. Patched in tests — keep it dependency-free and dumb."""
    webpush(
        subscription_info={
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        },
        data=json.dumps(payload),
        vapid_private_key=settings.VAPID_PRIVATE_KEY,
        vapid_claims={"sub": settings.VAPID_SUBJECT},
    )


def send_to_user(user, title: str, body: str, url: str) -> int:
    """Push to every browser this user has registered. Returns sends that stuck.

    A subscription dies silently when the app is uninstalled — the push service
    starts returning 404/410. That is the only reliable signal we get, so we
    prune on it. Any other failure is the service's problem, not the
    subscription's: count it and keep the row.
    """
    if not settings.VAPID_PRIVATE_KEY:
        return 0  # push not configured — stay silent rather than raise
    sent = 0
    for sub in list(user.push_subscriptions.all()):
        try:
            _send_one(sub, {"title": title, "body": body, "url": url})
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                logger.info("push: pruning dead subscription %s (%s)", sub.pk, status)
                sub.delete()
            else:
                PushSubscription.objects.filter(pk=sub.pk).update(
                    failure_count=sub.failure_count + 1
                )
                logger.warning("push: send failed sub=%s status=%s: %s", sub.pk, status, exc)
        except Exception:  # noqa: BLE001
            logger.exception("push: unexpected send failure sub=%s", sub.pk)
    return sent


def refresh_agent_waiting(agent: Agent) -> int:
    """Recompute this agent's waiting_count, push if it went UP, store it.

    Returns the number of pushes sent. The snapshot advances even when nobody is
    subscribed — otherwise the first push after subscribing would fire for items
    that were already sitting there.
    """
    count = int(needs_you(agent).get("waiting_count") or 0)
    snap, created = AgentWaitingSnapshot.objects.get_or_create(agent=agent)
    previous = 0 if created else snap.waiting_count
    if count != previous:
        snap.waiting_count = count
        snap.save(update_fields=["waiting_count", "updated_at"])
    if count <= previous:
        return 0  # cleared or unchanged — silence
    owner = getattr(agent, "owner", None)
    if owner is None:
        return 0
    delta = count - previous
    return send_to_user(
        owner,
        title=f"{agent.name} needs you",
        body=f"{delta} new item{'s' if delta != 1 else ''} · {count} waiting",
        url="/supervisor",
    )


def _flush() -> None:
    """Recompute every agent touched in the just-committed transaction, once."""
    ids = set(_dirty)
    _dirty.clear()
    for agent in Agent.objects.filter(id__in=ids):
        try:
            refresh_agent_waiting(agent)
        except Exception:  # noqa: BLE001
            # A push must never break the request that triggered it.
            logger.exception("push: refresh failed for agent=%s", agent.slug)


def mark_dirty(agent_id: int) -> None:
    """Note that an agent's waiting set may have changed.

    Registers the flush unconditionally. Redundant callbacks are free: the first
    one to run drains the set and does the work, and the rest find it empty and
    no-op — so a bulk sync of N rows is still ONE recompute per agent.

    Do NOT re-add a `if not _dirty` guard around the registration. Django
    discards on_commit callbacks when a transaction rolls back, but this set is
    not transactional and keeps its entries — so the guard would see a non-empty
    set forever after the first rollback, never register again, and silently
    kill push process-wide until restart.
    """
    _dirty.add(agent_id)
    transaction.on_commit(_flush)
