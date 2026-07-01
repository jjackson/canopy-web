"""Tenancy service helpers — the non-breaking glue for scoping agents to a
workspace: a default workspace, domain auto-join, and membership lookups.

Runtime counterparts to the one-time backfill data migration. Auto-join is what
keeps NEW domain users (and the board UI) seeing the default workspace's agents
after scoping turns on.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model

from .models import Workspace, WorkspaceMembership

DEFAULT_WORKSPACE_SLUG = "dimagi"
DEFAULT_WORKSPACE_NAME = "Dimagi"


def allowed_domains() -> list[str]:
    raw = getattr(settings, "AUTH_ALLOWED_EMAIL_DOMAIN", "") or ""
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


def _email_domain(email: str) -> str:
    email = (email or "").strip().lower()
    return email.rsplit("@", 1)[-1] if "@" in email else ""


def ensure_default_workspace() -> Workspace | None:
    """Return the default workspace, creating it (owned by the first superuser,
    else the first user) on first call. Returns None if there are no users yet
    (a fresh DB) — there is nothing to scope then."""
    ws = Workspace.objects.filter(slug=DEFAULT_WORKSPACE_SLUG).first()
    if ws is not None:
        return ws
    User = get_user_model()
    owner = (
        User.objects.filter(is_superuser=True).order_by("id").first()
        or User.objects.order_by("id").first()
    )
    if owner is None:
        return None
    ws = Workspace.objects.create(
        slug=DEFAULT_WORKSPACE_SLUG,
        display_name=DEFAULT_WORKSPACE_NAME,
        created_by=owner,
        auto_join_domains=allowed_domains(),
    )
    ensure_member(ws, owner, WorkspaceMembership.OWNER)
    return ws


def ensure_member(ws: Workspace, user, role: str = WorkspaceMembership.EDITOR) -> WorkspaceMembership:
    m, _ = WorkspaceMembership.objects.get_or_create(
        workspace=ws, user=user, defaults={"role": role}
    )
    return m


def auto_join_workspaces(user) -> None:
    """Add `user` (as editor) to every workspace whose auto_join_domains include
    their email domain. Cheap + idempotent; safe to call per request."""
    domain = _email_domain(getattr(user, "email", ""))
    if not domain:
        return
    for ws in Workspace.objects.exclude(auto_join_domains=[]):
        if domain in [d.lower() for d in (ws.auto_join_domains or [])]:
            ensure_member(ws, user, WorkspaceMembership.EDITOR)


def user_workspace_slugs(user) -> set[str]:
    return set(
        WorkspaceMembership.objects.filter(user=user).values_list("workspace_id", flat=True)
    )


def is_member(user, slug: str) -> bool:
    return WorkspaceMembership.objects.filter(user=user, workspace_id=slug).exists()


def user_default_workspace(user) -> Workspace | None:
    """The user's workspace when unambiguous — their sole membership, else None
    (0 or 2+ memberships). Used to resolve a default for headless PAT callers."""
    rows = list(
        WorkspaceMembership.objects.filter(user=user).select_related("workspace")[:2]
    )
    return rows[0].workspace if len(rows) == 1 else None


def current_workspace(user, explicit: str | None = None) -> Workspace:
    """Resolve the workspace a caller is acting in.

    explicit slug (caller must be a member) -> that workspace;
    else the caller's sole membership; else ValueError (none / ambiguous).
    Single resolution point for PAT callers, MCP tools, and the flat compat shim.
    """
    if explicit:
        ws = Workspace.objects.filter(slug=explicit).first()
        if ws is None or not is_member(user, explicit):
            raise ValueError(f"workspace '{explicit}' not found or not a member")
        return ws
    ws = user_default_workspace(user)
    if ws is None:
        raise ValueError("no unambiguous workspace for user; specify one")
    return ws
