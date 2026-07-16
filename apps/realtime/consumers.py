"""WebSocket consumers over the realtime transport.

TurnConsumer live-tails one turn's append-only TurnEvent ledger. Replay is
cursor-based (?after=seq) reusing the same read the REST endpoint uses, then live
frames arrive via the turn.{id} group. Frames are idempotent on the client by seq.

SupervisorConsumer (Task 7) pushes runner-status + waiting-count deltas.
"""
from __future__ import annotations

import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.harness.models import Turn

from . import groups


class TurnConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not getattr(user, "is_authenticated", False):
            await self.close(code=4001)
            return
        raw_id = self.scope["url_route"]["kwargs"]["turn_id"]
        turn = await self._get_turn(raw_id)
        if turn is None:
            await self.close(code=4004)
            return
        if not await database_sync_to_async(groups.user_can_read_turn)(user, turn):
            await self.close(code=4003)
            return
        self.group = groups.turn_group(turn.id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        # Cursor replay: send everything after the client's last-seen seq, then
        # live-tail via turn_event group messages.
        after = self._after_from_query()
        for event in await self._replay(turn, after):
            await self.send_json({"event": event})

    async def disconnect(self, code):
        group = getattr(self, "group", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def turn_event(self, message):
        # group_send type="turn.event" dispatches here (dots -> underscores).
        await self.send_json({"event": message["event"]})

    # -- helpers --
    @database_sync_to_async
    def _get_turn(self, raw_id):
        try:
            turn_id = uuid.UUID(str(raw_id))
        except (ValueError, TypeError):
            return None
        return (
            Turn.objects.select_related("agent")
            .filter(pk=turn_id)
            .first()
        )

    @database_sync_to_async
    def _replay(self, turn, after: int):
        rows = turn.events.filter(seq__gt=after).order_by("seq")[:500]
        return [groups.serialize_turn_event(row) for row in rows]

    def _after_from_query(self) -> int:
        raw = (self.scope.get("query_string") or b"").decode()
        for part in raw.split("&"):
            if part.startswith("after="):
                try:
                    return int(part[len("after="):])
                except ValueError:
                    return 0
        return 0
