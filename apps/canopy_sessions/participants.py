"""Session membership + access. A workspace member auto-joins as editor on first
touch (like ace-web); the creator is the owner (set in create_session)."""
from __future__ import annotations

from apps.workspaces import services as wsvc

from .models import Session, SessionParticipant


def ensure_participant(session: Session, user, role: str = SessionParticipant.EDITOR) -> SessionParticipant:
    obj, _ = SessionParticipant.objects.get_or_create(
        session=session, user=user, defaults={"role": role}
    )
    return obj


def can_access(session: Session, user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    # A durable participant keeps access even if later removed from the workspace:
    # session membership is an explicit, standalone grant (you were added to THIS
    # conversation), not a projection of workspace membership. Off-boarding a user
    # from the workspace does not auto-revoke sessions they already joined — remove
    # the SessionParticipant row to revoke. (The REST surface re-checks tenant each
    # request; this socket-side gate intentionally honors the durable grant.)
    if SessionParticipant.objects.filter(session=session, user=user).exists():
        return True
    # A workspace member is granted access and auto-joined as an editor.
    if session.workspace_id in wsvc.user_workspace_slugs(user):
        ensure_participant(session, user, SessionParticipant.EDITOR)
        return True
    return False


def role_for(session: Session, user) -> str | None:
    row = SessionParticipant.objects.filter(session=session, user=user).only("role").first()
    return row.role if row else None
