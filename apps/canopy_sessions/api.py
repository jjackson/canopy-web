"""Django Ninja router for /api/canopy-sessions — live chat sessions.

Session-authed + workspace-membership gated. A "send" enqueues a session Turn;
in SP2a the stub executor runs it inline (the SP2b cloud runner will claim it
async instead — no API change when that lands).
"""
from __future__ import annotations

import uuid

from django.db.models import Max

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from apps.agents import services as agent_services
from apps.api.auth import session_auth
from apps.api.pagination import clamp_limit
from apps.workspaces import services as wsvc

from . import services
from .models import Session
from .schemas import (
    BackfillStateOut,
    MessageOut,
    MessagePageOut,
    SendIn,
    SendOut,
    SessionCreateIn,
    SessionDetailOut,
    SessionOut,
    StreamStateOut,
)

router = Router(auth=session_auth, tags=["chat"])


def _out(session: Session) -> dict:
    binding = getattr(session, "runner_binding", None)  # reverse 1:1 -> None when absent
    runner = binding.runner if (binding and binding.runner_id) else None
    return {
        "id": session.id,
        "agent_slug": session.agent.slug if session.agent_id else None,
        "project": session.project,
        "workspace": session.workspace_id,
        # The name a human recognises for a runner-bound session is the emdash
        # task (what they see in emdash), not a thread_key hash a fallback title
        # may have captured. Web chats keep their own title.
        "title": (binding.session_key if (binding and binding.session_key) else session.title),
        "status": session.status,
        "created_at": session.created_at,
        # When it last DID something (binding > newest message > created).
        "last_activity_at": services.last_activity_at(session, binding),
        # --- liveness (Plan 4): one shape, computed from the binding ---
        "origin": session.origin,
        "running": services.is_session_running(binding),
        "runner_name": runner.name if runner else None,
        "runner_location": runner.location if runner else None,
        "session_key": binding.session_key if binding else "",
    }


def _visible_slugs(request: HttpRequest) -> set[str]:
    wsvc.auto_join_workspaces(request.user)
    pinned = getattr(request, "workspace_slug", None)
    return {pinned} if pinned else set(wsvc.user_workspace_slugs(request.user))


def _session_or_404(request: HttpRequest, session_id: uuid.UUID) -> Session:
    session = get_object_or_404(
        Session.objects.select_related("agent", "runner_binding", "runner_binding__runner")
        .annotate(_last_msg_at=Max("messages__created_at")),
        pk=session_id,
    )
    if session.workspace_id not in _visible_slugs(request):
        raise HttpError(404, "session not found")  # wrong tenant / non-member
    return session


@router.post("/", response=SessionOut, summary="Create a chat session")
def create_session(request: HttpRequest, payload: SessionCreateIn):
    if payload.agent_slug and payload.project:
        raise HttpError(422, "a session targets an agent or a project, not both")
    try:
        workspace = wsvc.current_workspace(request.user, getattr(request, "workspace_slug", None))
    except ValueError as exc:
        raise HttpError(422, str(exc))
    agent = None
    if payload.agent_slug:
        agent = agent_services.get_agent(payload.agent_slug)
        if agent is None or agent.workspace_id != workspace.slug:
            raise HttpError(404, f"agent '{payload.agent_slug}' not found in this workspace")
    session = services.create_session(
        workspace=workspace, created_by=request.user, agent=agent,
        project=payload.project, title=payload.title, metadata=payload.metadata,
    )
    return _out(session)


@router.get("/", response=list[SessionOut], summary="List sessions (web + runner-discovered)")
def list_sessions(request: HttpRequest, state: str = "active", limit: int = 200):
    # The ONE unified list (Plan 4): every session the caller can see in their
    # workspaces — their own web sessions UNION any session that has a
    # RunnerBinding (runner-discovered or live). Deduped, running-first, then
    # newest. Replaces the creator-only list + the harness OpenSessions projection.
    #
    # `state` gives that list an END. Two rules combine into "archived":
    #   - WRITTEN: status == archived (the runner saw the emdash task archived, or
    #     a human called /archive). Durable.
    #   - DERIVED: a RUNNER-origin session whose binding has not been seen within
    #     SESSION_STALE_AFTER. Computed here, never stored, so it reverses itself
    #     the moment the task is reported again. Web sessions are exempt — they
    #     have no runner to be seen by, so only an explicit archive ends them.
    from django.db.models import Max, Q

    if state not in ("active", "archived", "all"):
        raise HttpError(422, "state must be one of: active, archived, all")

    slugs = _visible_slugs(request)
    rows = (
        Session.objects.select_related("agent", "runner_binding", "runner_binding__runner")
        .filter(workspace_id__in=slugs)
        .filter(Q(created_by=request.user) | Q(runner_binding__isnull=False))
        .annotate(_last_msg_at=Max("messages__created_at"))
        .distinct()
        .order_by("-created_at")
    )
    unseen = services.unseen_q()   # defined once in staleness.py; see Step 3
    if state == "active":
        rows = rows.filter(status=Session.ACTIVE).exclude(unseen)
    elif state == "archived":
        rows = rows.filter(Q(status=Session.ARCHIVED) | unseen)

    out = [_out(s) for s in rows]
    # Running first, then genuinely-most-recent. Sorting by created_at made a
    # dead repo and a live one interleave arbitrarily (both "created" in the
    # same report sweep); last_activity_at is the real signal. The client can
    # re-group by project — this is the default order.
    out.sort(key=lambda r: (not r["running"], -(r["last_activity_at"].timestamp())))
    # Clamp AFTER the sort, never as a queryset slice: the queryset is ordered by
    # -created_at, so slicing it could drop the running session this sort exists to
    # float. `state=active` already bounds the set; this is a payload backstop.
    return out[: clamp_limit(limit)]


@router.get("/{session_id}", response=SessionDetailOut, summary="Get a session + transcript tail")
def get_session(request: HttpRequest, session_id: uuid.UUID, full: bool = False):
    # Tail-first: never ship the whole transcript by default. The client gets the
    # last SESSION_TAIL_DEFAULT messages + a backward cursor; ?full=true is the
    # explicit escape hatch. Scroll-back pages via GET /{id}/messages?before=.
    session = _session_or_404(request, session_id)
    data = _out(session)
    rows, has_more, oldest = services.visible_transcript(session, full=full)
    data["messages"] = [MessageOut.from_orm(m) for m in rows]
    data["has_more_before"] = has_more
    data["oldest_loaded_turn_index"] = oldest
    return data


@router.get(
    "/{session_id}/messages",
    response=MessagePageOut,
    summary="Load earlier transcript (scroll-back)",
)
def list_messages(
    request: HttpRequest,
    session_id: uuid.UUID,
    before: int,
    limit: int = services.SCROLLBACK_PAGE_DEFAULT,
):
    # Cursor-based backward paging: the window of `limit` messages immediately
    # older than `before` (a turn_index), chronological, + whether older exists.
    # Clamp here (not in services.messages_before, which stays a pure helper) —
    # an unclamped `?limit=-1`/`0` hits `queryset[:limit]` and raises
    # ValueError("Negative indexing is not supported"), surfacing as a 500.
    session = _session_or_404(request, session_id)
    limit = clamp_limit(limit)
    rows, has_more = services.messages_before(session, before=before, limit=limit)
    return {
        "messages": [MessageOut.from_orm(m) for m in rows],
        "has_more_before": has_more,
    }


@router.post("/{session_id}/send", response=SendOut, summary="Send a message")
def send(request: HttpRequest, session_id: uuid.UUID, payload: SendIn):
    session = _session_or_404(request, session_id)
    if not payload.text.strip():
        raise HttpError(422, "message text is required")
    message, turn = services.send_message(
        session=session, text=payload.text, user=request.user, client_id=payload.client_id,
    )
    # Dev/test: run the stub inline. Production: leave it queued for a cloud runner.
    services.maybe_execute_inline(turn)
    return {"turn_id": turn.id if turn else None, "message": MessageOut.from_orm(message)}


@router.post("/{session_id}/attach", response=StreamStateOut, summary="Attach a viewer (start live streaming)")
def attach_session(request: HttpRequest, session_id: uuid.UUID):
    session = _session_or_404(request, session_id)
    return {"streaming": services.attach_session(session)}


@router.post("/{session_id}/detach", response=StreamStateOut, summary="Detach a viewer (stop when last leaves)")
def detach_session(request: HttpRequest, session_id: uuid.UUID):
    session = _session_or_404(request, session_id)
    return {"streaming": services.detach_session(session)}


@router.post("/{session_id}/backfill", response=BackfillStateOut, summary="Request full history from the runner")
def request_backfill(request: HttpRequest, session_id: uuid.UUID):
    session = _session_or_404(request, session_id)
    return {"status": services.request_backfill(session)}
