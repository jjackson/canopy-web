"""Notification channels for schedule nags — a string registry, so new channels
are an entry plus a function, never a model change.

Copies the indirection apps/timeline/sources.py uses. Exactly ONE channel ships
today: "inbox" (the needs_you projection). Email / macOS / Slack land here later
without touching AgentSchedule.notify's shape.
"""
from __future__ import annotations

from collections.abc import Callable


def _inbox(agent, schedule, turn) -> dict:
    """The default channel: a typed needs_you item. Passive but omnipresent —
    it rides the 'N waiting on you' badge the supervisor surfaces already show.

    `turn` is always non-None here: the only caller, schedule_nag_items,
    `continue`s when turn is None."""
    return {
        "type": "review",
        "ref_kind": "schedule",
        "ref_id": schedule.id,
        "title": schedule.name,
        "subtitle": "Scheduled — not finished",
        "url": "",
        "created_at": turn.created_at,
    }


# channel id -> builder. Unknown ids in AgentSchedule.notify are ignored, so a
# half-rolled-out channel can never 500 the supervisor's inbox.
CHANNELS: dict[str, Callable] = {"inbox": _inbox}


def schedule_nag_items(agent) -> list[dict]:
    """Every enabled schedule of `agent` whose latest occurrence isn't done."""
    from . import services
    from .models import AgentSchedule, Turn

    items: list[dict] = []
    for schedule in AgentSchedule.objects.filter(agent=agent, enabled=True):
        turn = services.latest_occurrence_turn(schedule)
        if turn is None or turn.status == Turn.DONE:
            continue  # never fired, or you finished it — nothing owed
        for channel_id in schedule.notify:
            builder = CHANNELS.get(channel_id)
            if builder is not None:
                items.append(builder(agent, schedule, turn))
    return items
