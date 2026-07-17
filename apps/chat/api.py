"""Django Ninja router for /api/chat — live chat sessions.

Session-authed + workspace-membership gated. A "send" enqueues a session Turn;
in SP2a the stub executor runs it inline (the SP2b cloud runner will claim it
async instead — no API change when that lands).
"""
from __future__ import annotations

import uuid

from django.db import IntegrityError
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from apps.agents import services as agent_services
from apps.api.auth import session_auth
from apps.harness.models import Turn
from apps.workspaces import services as wsvc

from . import services
from .executor import execute_turn_stub
from .models import Message, Session
from .schemas import MessageOut, SendIn, SendOut, SessionCreateIn, SessionDetailOut, SessionOut

router = Router(auth=session_auth, tags=["chat"])


def _out(session: Session) -> dict:
    return {
        "id": session.id,
        "agent_slug": session.agent.slug if session.agent_id else None,
        "workspace": session.workspace_id,
        "title": session.title,
        "status": session.status,
        "created_at": session.created_at,
    }


def _visible_slugs(request: HttpRequest) -> set[str]:
    wsvc.auto_join_workspaces(request.user)
    pinned = getattr(request, "workspace_slug", None)
    return {pinned} if pinned else set(wsvc.user_workspace_slugs(request.user))


def _session_or_404(request: HttpRequest, session_id: uuid.UUID) -> Session:
    session = get_object_or_404(Session.objects.select_related("agent"), pk=session_id)
    if session.workspace_id not in _visible_slugs(request):
        raise HttpError(404, "session not found")  # wrong tenant / non-member
    return session


@router.post("/", response=SessionOut, summary="Create a chat session")
def create_session(request: HttpRequest, payload: SessionCreateIn):
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
        title=payload.title, metadata=payload.metadata,
    )
    return _out(session)


@router.get("/", response=list[SessionOut], summary="List my chat sessions")
def list_sessions(request: HttpRequest):
    # "My" sessions — scoped to the caller (session sharing across a workspace is
    # SP3 multiplayer). Still tenant-bounded so a stale membership can't leak.
    slugs = _visible_slugs(request)
    rows = (
        Session.objects.select_related("agent")
        .filter(workspace_id__in=slugs, created_by=request.user)
        .order_by("-created_at")
    )
    return [_out(s) for s in rows]


@router.get("/{session_id}", response=SessionDetailOut, summary="Get a session + transcript")
def get_session(request: HttpRequest, session_id: uuid.UUID):
    session = _session_or_404(request, session_id)
    data = _out(session)
    data["messages"] = [
        MessageOut.from_orm(m) for m in session.messages.order_by("turn_index")
    ]
    return data


@router.post("/{session_id}/send", response=SendOut, summary="Send a message")
def send(request: HttpRequest, session_id: uuid.UUID, payload: SendIn):
    session = _session_or_404(request, session_id)
    if not payload.text.strip():
        raise HttpError(422, "message text is required")
    message, turn = services.send_message(
        session=session, text=payload.text, user=request.user, client_id=payload.client_id,
    )
    # SP2a: run the stub inline. SP2b: the cloud runner claims the queued turn.
    # Guard against the one_executing_turn_per_session race (a truly concurrent
    # send to the same session): leave the turn queued rather than 500 the
    # already-committed user message. Moot once SP2b makes execution async.
    if turn is not None and turn.status == Turn.QUEUED:
        try:
            execute_turn_stub(turn)
        except IntegrityError:
            pass
    return {"turn_id": turn.id if turn else None, "message": MessageOut.from_orm(message)}
