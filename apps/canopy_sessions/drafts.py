"""The co-edited outgoing draft. Optimistic `version` guard + a DERIVED soft-lock
(holder = last_editor, while edited within the idle window AND still present). No
CRDT — coarse single-draft locking, right for a few teammates per session."""
from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

from . import presence
from .models import Draft, Session

IDLE_WINDOW = dt.timedelta(seconds=2)


class DraftVersionMismatch(Exception):
    def __init__(self, current_version: int, current_body: str):
        self.current_version = current_version
        self.current_body = current_body
        super().__init__("draft version mismatch")


class DraftLockHeld(Exception):
    def __init__(self, holder_id: int):
        self.holder_id = holder_id
        super().__init__("draft lock held by another editor")


def active_draft(session: Session) -> Draft:
    draft, _ = Draft.objects.get_or_create(session=session, slot="next")
    return draft


def lock_holder(draft: Draft) -> int | None:
    """The soft-lock holder id, or None when the draft is free (idle past the window,
    or the last editor is no longer present)."""
    if draft.last_editor_id is None:
        return None
    if timezone.now() - draft.updated_at > IDLE_WINDOW:
        return None
    if not presence.is_present(draft.session_id, draft.last_editor_id):
        return None
    return draft.last_editor_id


def update_draft(session: Session, *, expected_version: int, body: str, editor) -> Draft:
    with transaction.atomic():
        draft = Draft.objects.select_for_update().get(pk=active_draft(session).pk)
        holder = lock_holder(draft)
        if holder is not None and holder != editor.id:
            raise DraftLockHeld(holder)
        if expected_version != draft.version:
            raise DraftVersionMismatch(draft.version, draft.body)
        draft.body = body
        draft.version += 1
        draft.last_editor = editor
        draft.save(update_fields=["body", "version", "last_editor", "updated_at"])
    return draft


def take_over(session: Session, *, editor) -> Draft:
    with transaction.atomic():
        draft = Draft.objects.select_for_update().get(pk=active_draft(session).pk)
        holder = lock_holder(draft)
        if holder is not None and holder != editor.id:
            raise DraftLockHeld(holder)
        draft.last_editor = editor
        draft.save(update_fields=["last_editor", "updated_at"])
    return draft


def commit_active_draft(session: Session) -> str:
    """Take the active draft's text and reset it (bump version, clear body) so the
    next message starts fresh. Returns the committed text."""
    with transaction.atomic():
        draft = Draft.objects.select_for_update().get(pk=active_draft(session).pk)
        text = draft.body
        draft.body = ""
        draft.version += 1
        draft.last_editor = None
        draft.save(update_fields=["body", "version", "last_editor", "updated_at"])
    return text
