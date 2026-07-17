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
    REPLAY_PAGE = 500

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
        # live-tail via turn_event group messages. Paged to exhaustion — a turn
        # with more than REPLAY_PAGE unseen events (routine on the SP2 chat path,
        # where a turn streams token-level events) must not be silently truncated:
        # those rows predate the group join, so the live tail would never re-emit
        # them, leaving a hole between the replayed page and new appends.
        after = self._after_from_query()
        while True:
            batch = await self._replay_batch(turn, after)
            if not batch:
                break
            for event in batch:
                await self.send_json({"event": event})
            after = batch[-1]["seq"]
            if len(batch) < self.REPLAY_PAGE:
                break

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
            Turn.objects.select_related("agent", "chat_session")
            .filter(pk=turn_id)
            .first()
        )

    @database_sync_to_async
    def _replay_batch(self, turn, after: int):
        rows = turn.events.filter(seq__gt=after).order_by("seq")[: self.REPLAY_PAGE]
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


class SupervisorConsumer(AsyncJsonWebsocketConsumer):
    """Live /supervisor: a per-user group receives runner-status and
    waiting-count deltas; a snapshot is sent on connect. The socket spans all the
    user's workspaces (the fleet is cross-tenant, like /insights)."""

    async def connect(self):
        user = self.scope.get("user")
        if not getattr(user, "is_authenticated", False):
            await self.close(code=4001)
            return
        self.group = groups.supervisor_user_group(user.id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.send_json(await self._snapshot(user))

    async def disconnect(self, code):
        group = getattr(self, "group", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def supervisor_runner(self, message):
        await self.send_json(message)

    async def supervisor_waiting(self, message):
        await self.send_json(message)

    @database_sync_to_async
    def _snapshot(self, user):
        from .snapshot import supervisor_snapshot

        return supervisor_snapshot(user)
