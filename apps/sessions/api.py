"""Django Ninja routers for shared Claude Code session transcripts.

Two routers:
  * ``router`` (auth=session_auth) → /api/sessions  — owner upload + management
  * ``share_router`` (auth=None)   → /api/share     — public read-only view

The public read route is auth=None AND exempted in
``apps.common.middleware.LoginRequiredMiddleware`` (see ``_is_share_link``) so
an anonymous visitor with a valid token can load it without a dimagi session.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from django.db import transaction
from django.http import HttpRequest
from ninja import File, Form, Router, Status
from ninja.files import UploadedFile

from apps.api.auth import session_auth
from apps.api.errors import TYPE_FORBIDDEN, TYPE_NOT_FOUND, ProblemError

from . import redact
from .models import Message, Session, ShareToken
from .parser import parse_session_file
from .schemas import (
    SessionDetailOut,
    SessionListItemOut,
    SessionMessageOut,
    SessionPatchIn,
    SessionRotateTokenOut,
    SessionUploadOut,
    SessionVisibility,
    SharedSessionOut,
)

router = Router(auth=session_auth, tags=["sessions"])
share_router = Router(tags=["share"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB — transcripts are JSON, rarely large.


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _message_payloads(session: Session) -> list[dict]:
    return [
        {
            "turn_index": m.turn_index,
            "role": m.role,
            "content": m.content,
            "plaintext": m.plaintext,
        }
        for m in session.messages.all()
    ]


def _list_payload(session: Session, *, is_owner: bool) -> dict:
    token = session.active_token() if is_owner else None
    return {
        "slug": session.slug,
        "title": session.title,
        "project_slug": session.project_slug,
        "visibility": session.visibility,
        "owner_email": session.owner.email,
        "message_count": session.messages.count(),
        "redaction_count": session.redaction_count,
        "share_token": token.token if token else None,
        "is_owner": is_owner,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def _get_owned_or_403(request: HttpRequest, slug: str) -> Session:
    session = Session.objects.filter(slug=slug).select_related("owner").first()
    if session is None:
        raise ProblemError(404, "Session not found", type_=TYPE_NOT_FOUND)
    if not (request.user.is_authenticated and session.owner_id == request.user.id):
        raise ProblemError(403, "Forbidden — owner only", type_=TYPE_FORBIDDEN)
    return session


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post(
    "/upload",
    response={201: SessionUploadOut},
    summary="Upload a Claude .jsonl transcript (multipart)",
)
def upload_session(
    request: HttpRequest,
    file: UploadedFile = File(...),
    title: str = Form(""),
    project_slug: str = Form(""),
    visibility: SessionVisibility = Form("link"),
) -> Status:
    if file.size > MAX_UPLOAD_BYTES:
        raise ProblemError(
            413,
            "Payload too large",
            detail=f"Transcript exceeds {MAX_UPLOAD_BYTES} bytes.",
        )

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        for chunk in file.chunks():
            tmp.write(chunk)
        tmp_path = Path(tmp.name)
    try:
        parsed = parse_session_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    # Idempotent re-upload: if this owner already shared this CLI session,
    # return the existing link rather than creating a duplicate.
    if parsed.cli_session_id:
        existing = Session.objects.filter(
            owner=request.user, cli_session_id=parsed.cli_session_id
        ).first()
        if existing is not None:
            token = (
                existing.ensure_share_token(request.user)
                if existing.visibility == Session.VISIBILITY_LINK
                else existing.active_token()
            )
            return Status(
                201,
                SessionUploadOut(
                    slug=existing.slug,
                    message_count=existing.messages.count(),
                    redaction_count=existing.redaction_count,
                    visibility=existing.visibility,
                    share_token=token.token if token else None,
                    duplicate=True,
                ),
            )

    resolved_title = (title.strip() or file.name or "Claude session")[:500]
    resolved_project = project_slug.strip() or None

    with transaction.atomic():
        session = Session.objects.create(
            owner=request.user,
            title=resolved_title,
            project_slug=resolved_project,
            visibility=visibility,
            cli_session_id=parsed.cli_session_id or "",
            source_filename=(file.name or "")[:500],
            raw_bytes=parsed.raw_bytes,
            line_count=parsed.line_count,
        )

        total_redactions = 0
        rows: list[Message] = []
        for idx, turn in enumerate(parsed.turns, start=1):
            plaintext, content, n = redact.redact_turn(turn.plaintext, turn.content)
            total_redactions += n
            rows.append(
                Message(
                    session=session,
                    turn_index=idx,
                    role=turn.role,
                    content=content,
                    plaintext=plaintext,
                )
            )
        Message.objects.bulk_create(rows)

        session.redaction_count = total_redactions
        session.save(update_fields=["redaction_count", "updated_at"])

        token = None
        if visibility == Session.VISIBILITY_LINK:
            token = ShareToken.objects.create(session=session, created_by=request.user)

    return Status(
        201,
        SessionUploadOut(
            slug=session.slug,
            message_count=len(rows),
            redaction_count=total_redactions,
            visibility=session.visibility,
            share_token=token.token if token else None,
            duplicate=False,
        ),
    )


# ---------------------------------------------------------------------------
# List (owner's sessions)
# ---------------------------------------------------------------------------


@router.get("/", response=list[SessionListItemOut], summary="List my shared sessions")
def list_sessions(
    request: HttpRequest, project: str = ""
) -> list[SessionListItemOut]:
    qs = (
        Session.objects.select_related("owner")
        .filter(owner=request.user)
        .prefetch_related("share_tokens")
    )
    if project:
        qs = qs.filter(project_slug=project)
    return [
        SessionListItemOut.model_validate(_list_payload(s, is_owner=True)) for s in qs
    ]


# ---------------------------------------------------------------------------
# Detail (owner)
# ---------------------------------------------------------------------------


@router.get("/{slug}", response=SessionDetailOut, summary="Get one session (owner)")
def get_session(request: HttpRequest, slug: str) -> SessionDetailOut:
    session = _get_owned_or_403(request, slug)
    payload = _list_payload(session, is_owner=True)
    payload["messages"] = _message_payloads(session)
    return SessionDetailOut.model_validate(payload)


# ---------------------------------------------------------------------------
# Patch (owner) — title / project / visibility
# ---------------------------------------------------------------------------


@router.patch("/{slug}", response=SessionListItemOut, summary="Update a session (owner)")
def patch_session(
    request: HttpRequest, slug: str, payload: SessionPatchIn
) -> SessionListItemOut:
    session = _get_owned_or_403(request, slug)
    updates = payload.model_dump(exclude_unset=True)

    new_visibility = updates.pop("visibility", None)
    for field, value in updates.items():
        setattr(session, field, value)
    if updates:
        session.save()

    if new_visibility == Session.VISIBILITY_LINK:
        session.ensure_share_token(request.user)
    elif new_visibility == Session.VISIBILITY_PRIVATE:
        session.revoke_sharing()

    session.refresh_from_db()
    return SessionListItemOut.model_validate(_list_payload(session, is_owner=True))


# ---------------------------------------------------------------------------
# Delete (owner)
# ---------------------------------------------------------------------------


@router.delete("/{slug}", response={204: None}, summary="Delete a session (owner)")
def delete_session(request: HttpRequest, slug: str) -> Status:
    session = _get_owned_or_403(request, slug)
    session.delete()
    return Status(204, None)


# ---------------------------------------------------------------------------
# Rotate token (owner) — invalidate the old share link, mint a fresh one
# ---------------------------------------------------------------------------


@router.post(
    "/{slug}/rotate-token",
    response=SessionRotateTokenOut,
    summary="Rotate share token (owner)",
)
def rotate_token(request: HttpRequest, slug: str) -> SessionRotateTokenOut:
    session = _get_owned_or_403(request, slug)
    token = session.rotate_share_token(request.user)
    return SessionRotateTokenOut(share_token=token.token)


# ---------------------------------------------------------------------------
# Public read-only share view (no auth)
# ---------------------------------------------------------------------------


@share_router.get(
    "/{token}",
    auth=None,
    response=SharedSessionOut,
    summary="Public read-only view of a shared session",
)
def public_share_view(request: HttpRequest, token: str) -> SharedSessionOut:
    share = (
        ShareToken.objects.select_related("session")
        .filter(token=token)
        .first()
    )
    # 404 on missing OR revoked — never leak the difference.
    if share is None or share.revoked_at is not None:
        raise ProblemError(404, "Share link not found", type_=TYPE_NOT_FOUND)

    session = share.session
    messages = [
        SessionMessageOut(
            turn_index=m.turn_index,
            role=m.role,
            content=m.content,
            plaintext=m.plaintext,
        )
        for m in session.messages.all()
    ]
    return SharedSessionOut(
        title=session.title,
        redaction_count=session.redaction_count,
        messages=messages,
    )
