"""The per-session multiplayer WebSocket (SP3).

One socket per session carries presence, the co-edited draft, and the streamed
turn. It uses realtime.groups for the (chat-agnostic) group name and realtime's
fan-out for turn events; the draft/presence/participant domain is chat's own.
"""
from __future__ import annotations

import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db import IntegrityError

from apps.harness.models import Turn
from apps.realtime.groups import session_group

from . import drafts, participants, presence
from . import services as chat_services
from .executor import execute_turn_stub
from .models import Session, SessionParticipant

_EDIT_ROLES = {SessionParticipant.OWNER, SessionParticipant.EDITOR}


class SessionConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not getattr(user, "is_authenticated", False):
            await self.close(code=4001)
            return
        raw_id = self.scope["url_route"]["kwargs"]["session_id"]
        session = await self._get_session(raw_id)
        if session is None:
            await self.close(code=4004)
            return
        if not await database_sync_to_async(participants.can_access)(session, user):
            await self.close(code=4003)
            return
        self.session = session
        self.user = user
        # can_access auto-joins a workspace member as editor, so a role always
        # exists by now; default to editor defensively.
        self.role = await database_sync_to_async(participants.role_for)(session, user) or SessionParticipant.EDITOR
        self.group = session_group(session.id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await database_sync_to_async(presence.touch)(session.id, user.id)
        await self.send_json(await self._snapshot())
        await self._broadcast({"type": "presence.joined", "user_id": user.id})

    async def disconnect(self, code):
        group = getattr(self, "group", None)
        if not group:
            return
        await database_sync_to_async(presence.leave)(self.session.id, self.user.id)
        await self._broadcast({"type": "presence.left", "user_id": self.user.id})
        await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = content.get("action")
        data = content.get("data") or {}
        if action == "presence.heartbeat":
            await database_sync_to_async(presence.touch)(self.session.id, self.user.id)
            return
        if action in ("draft.update", "draft.take_over", "draft.commit"):
            if self.role not in _EDIT_ROLES:
                await self.send_json({"event": "error", "data": {"code": "forbidden"}})
                return
        if action == "draft.update":
            await self._draft_update(data)
        elif action == "draft.take_over":
            await self._draft_take_over()
        elif action == "draft.commit":
            await self._draft_commit()

    # -- actions --
    async def _draft_update(self, data):
        try:
            draft = await database_sync_to_async(drafts.update_draft)(
                self.session,
                expected_version=int(data.get("expected_version", 0)),
                body=str(data.get("body", "")),
                editor=self.user,
            )
        except drafts.DraftVersionMismatch as exc:
            await self.send_json({
                "event": "draft.conflict",
                "data": {"current_version": exc.current_version, "current_body": exc.current_body},
            })
            return
        except drafts.DraftLockHeld as exc:
            await self.send_json({"event": "draft.locked", "data": {"holder_id": exc.holder_id}})
            return
        await self._broadcast_draft(draft)

    async def _draft_take_over(self):
        try:
            draft = await database_sync_to_async(drafts.take_over)(self.session, editor=self.user)
        except drafts.DraftLockHeld as exc:
            await self.send_json({"event": "draft.locked", "data": {"holder_id": exc.holder_id}})
            return
        await self._broadcast_draft(draft)

    async def _draft_commit(self):
        # commit deliberately ignores lock/version (spec: any editor can commit the
        # shared draft). Broadcast the cleared draft FIRST so co-editors' UI always
        # resets, even if execution below is a no-op / races a concurrent turn.
        text = await database_sync_to_async(drafts.commit_active_draft)(self.session)
        draft = await database_sync_to_async(drafts.active_draft)(self.session)
        await self._broadcast_draft(draft)
        if not text.strip():
            return
        await database_sync_to_async(self._send_and_execute)(text)
        # turn events fan out to the session group automatically (realtime signal).

    def _send_and_execute(self, text):
        _msg, turn = chat_services.send_message(session=self.session, text=text, user=self.user)
        # Mirror the REST send guard: only drive a queued turn, and survive the
        # one_executing_turn_per_session race (a concurrent send) rather than
        # tearing down the socket. SP2b's async runner replaces this inline call.
        if turn is not None and turn.status == Turn.QUEUED:
            try:
                execute_turn_stub(turn)
            except IntegrityError:
                pass

    # -- group frame handlers (dots -> underscores) --
    async def chat_turn_event(self, message):
        await self.send_json({"event": "chat.turn_event", "data": message["event"]})

    async def draft_updated(self, message):
        await self.send_json({"event": "draft.updated", "data": message["draft"]})

    async def presence_joined(self, message):
        await self.send_json({"event": "presence.joined", "data": {"user_id": message["user_id"]}})

    async def presence_left(self, message):
        await self.send_json({"event": "presence.left", "data": {"user_id": message["user_id"]}})

    # -- helpers --
    async def _broadcast(self, message):
        await self.channel_layer.group_send(self.group, message)

    async def _broadcast_draft(self, draft):
        await self.channel_layer.group_send(
            self.group,
            {
                "type": "draft.updated",
                "draft": {
                    "body": draft.body,
                    "version": draft.version,
                    "last_editor": draft.last_editor_id,
                },
            },
        )

    @database_sync_to_async
    def _get_session(self, raw_id):
        try:
            return Session.objects.get(pk=uuid.UUID(str(raw_id)))
        except (Session.DoesNotExist, ValueError):
            return None

    @database_sync_to_async
    def _snapshot(self):
        parts = [
            {"user_id": p.user_id, "role": p.role}
            for p in self.session.participants.all()
        ]
        draft = drafts.active_draft(self.session)
        recent = [
            {"turn_index": m.turn_index, "role": m.role, "plaintext": m.plaintext}
            for m in self.session.messages.order_by("turn_index")[:200]
        ]
        return {
            "event": "session.state",
            "data": {
                "participants": parts,
                "present": sorted(presence.present_ids(self.session.id)),
                "draft": {"body": draft.body, "version": draft.version, "last_editor": draft.last_editor_id},
                "messages": recent,
            },
        }
