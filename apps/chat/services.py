"""Chat services — create sessions, send messages (which enqueue a Turn), and
project the TurnEvent ledger into Message rows.

The write path is small: send_message writes the user Message + enqueues a session
Turn; the projection (driven by harness's turn_events_appended signal) materializes
the assistant/tool stream into Message rows. Because one_executing_turn_per_session
serializes a conversation, turn_index assignment never races within a session.
"""
from __future__ import annotations

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max

from apps.harness import services as harness_services
from apps.harness.models import Turn

from .models import Message, Session

# Ledger kinds we surface as transcript rows, and the Message role each maps to.
_ROLE_FOR_KIND = {
    "assistant": Message.ASSISTANT,
    "tool_start": Message.TOOL_USE,
    "tool_use": Message.TOOL_USE,
    "tool_end": Message.TOOL_RESULT,
    "tool_result": Message.TOOL_RESULT,
}


def create_session(*, workspace, created_by, agent=None, title: str = "", metadata: dict | None = None) -> Session:
    # The creator is the owner (SP3 multiplayer). Atomic so a session never exists
    # without its owner participant. Local imports avoid a cycle.
    from .models import SessionParticipant
    from .participants import ensure_participant

    with transaction.atomic():
        session = Session.objects.create(
            workspace=workspace, agent=agent, created_by=created_by,
            title=title, metadata=metadata or {},
        )
        ensure_participant(session, created_by, SessionParticipant.OWNER)
    return session


def _next_index(session: Session) -> int:
    current = Message.objects.filter(session=session).aggregate(m=Max("turn_index"))["m"]
    return 0 if current is None else current + 1


def send_message(*, session: Session, text: str, user, client_id: str = "") -> tuple[Message, Turn]:
    """Record the human's message and enqueue the session Turn that answers it.

    Idempotency: pass a stable `client_id` (a client-generated nonce) to make a
    retried/double-submitted send collapse onto the SAME user Message + Turn.
    Without one, the key falls back to the message's session index — best-effort
    only (a genuine retry after the first commit would compute a new index), so a
    nonce is required for true double-submit safety.
    """
    with transaction.atomic():
        Session.objects.select_for_update().get(pk=session.pk)
        if client_id:
            existing = Message.objects.filter(
                session=session, role=Message.USER, content__client_id=client_id
            ).first()
            if existing is not None:
                key = f"chat:{session.id.hex}:{client_id}"
                turn = Turn.objects.filter(idempotency_key=key).first()
                return existing, turn
        index = _next_index(session)
        content = {"text": text}
        if client_id:
            content["client_id"] = client_id
        message = Message.objects.create(
            session=session, turn_index=index, role=Message.USER, plaintext=text, content=content,
        )
        turn, _created = harness_services.enqueue_turn(
            session=session,
            origin=Turn.ORIGIN_API,
            idempotency_key=f"chat:{session.id.hex}:{client_id or index}",
            prompt=text,
            # Continuity: every send in a chat reuses ONE emdash session (the runner's
            # _thread_key reads this), so a conversation is one durable thread rather
            # than a fresh session per message. chat_session_id tells a session-capable
            # runner to BRIDGE the emdash response back into the ledger (vs the normal
            # fire-and-continue), so the website streams the reply.
            origin_ref={"thread_key": str(session.id), "chat_session_id": str(session.id)},
        )
    # RC4 — multiplayer interjection: if a turn is ALREADY running for this session,
    # the human's message is an interjection. Push it down to the runner executing
    # that turn (over its control channel) so the live agent sees it, on top of the
    # new turn that queues behind it. Post-commit + null-safe (a realtime hiccup
    # never breaks the send).
    _maybe_interject(session, message)
    return message, turn


def _maybe_interject(session: Session, message: Message) -> None:
    from apps.realtime import groups

    running = (
        Turn.objects.filter(
            chat_session=session,
            status__in=[Turn.CLAIMED, Turn.RUNNING, Turn.NEEDS_HUMAN],
            claimed_by__isnull=False,
        )
        .order_by("-created_at")
        .first()
    )
    if running is None:
        return
    groups.publish(groups.runner_group(running.claimed_by_id), {
        "type": "runner.interject",
        "turn_id": str(running.id),
        "session_id": str(session.id),
        "message": message.plaintext,
    })


def maybe_execute_inline(turn: Turn | None) -> None:
    """The chat send's executor hop. In dev/test (CHAT_STUB_EXECUTOR=True) run the
    stub inline so the turn completes with no runner. In production (False) leave it
    QUEUED for a session-capable cloud runner to claim + run real claude — the same
    ledger + Message projection either way. The one seam between stub and cloud.

    Guarded on QUEUED + IntegrityError so a truly-concurrent same-session send (the
    one_executing_turn_per_session race) never 500s the already-committed message."""
    if not getattr(settings, "CHAT_STUB_EXECUTOR", True):
        return
    if turn is None or turn.status != Turn.QUEUED:
        return
    from .executor import execute_turn_stub

    try:
        execute_turn_stub(turn)
    except IntegrityError:
        pass


def project_events(turn: Turn, rows) -> int:
    """Materialize a turn's newly-appended assistant/tool events into Message rows.
    Idempotent per source ledger seq, so a re-delivered signal never doubles a row."""
    if not turn.chat_session_id:
        return 0
    created = 0
    with transaction.atomic():
        session = Session.objects.select_for_update().get(pk=turn.chat_session_id)
        index = _next_index(session)
        for row in rows:
            role = _ROLE_FOR_KIND.get(row.kind)
            if role is None:
                continue  # status/heartbeat/error etc. are not transcript rows
            if Message.objects.filter(turn=turn, content__source_seq=row.seq).exists():
                continue
            payload = row.payload or {}
            Message.objects.create(
                session=session, turn=turn, turn_index=index, role=role,
                content={**payload, "source_seq": row.seq},
                plaintext=str(payload.get("text", "")),
            )
            index += 1
            created += 1
    return created
