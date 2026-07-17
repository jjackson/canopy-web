"""Shared insight query/mutation logic.

Single source of truth for the insights queryset shaping and the
filter-aware clear, used by BOTH the Django Ninja REST views
(`apps.projects.api`) and the FastMCP tools (`apps.mcp.tools.insights`).

Keeping the queryset construction here means the REST surface and the
MCP surface can never drift on what "an insight" is or how a filter is
applied. Both call into the same functions.

These functions are deliberately framework-agnostic (no request object,
no Ninja schemas) — callers translate their own input into plain kwargs.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import ProjectContext


def insights_queryset(
    *,
    workspace_slugs: set[str],
    category: str | None = None,
    source: str | None = None,
    project: str | None = None,
    older_than_days: int | None = None,
):
    """Return a filtered, ordered queryset of insight ProjectContext rows.

    `workspace_slugs` is REQUIRED and is the hard tenant boundary: only insights
    whose project belongs to one of those workspaces (or a legacy null-workspace
    project) are ever returned — so no caller can read or clear across the
    boundary. Pass the empty set to match nothing.

    The rest are optional, AND-combined:
      - category: content starts with "[<category>]"
      - source: ProjectContext.source exact match
      - project: project slug exact match
      - older_than_days: created_at older than N days ago
    """
    qs = (
        ProjectContext.objects.filter(context_type="insight")
        .filter(Q(project__workspace_id__in=workspace_slugs) | Q(project__workspace__isnull=True))
        .select_related("project")
        .order_by("-created_at")
    )
    if category:
        qs = qs.filter(content__startswith=f"[{category}]")
    if source:
        qs = qs.filter(source=source)
    if project:
        qs = qs.filter(project__slug=project)
    if older_than_days is not None:
        cutoff = timezone.now() - timedelta(days=older_than_days)
        qs = qs.filter(created_at__lt=cutoff)
    return qs


def list_insights(
    *,
    workspace_slugs: set[str],
    category: str | None = None,
    source: str | None = None,
    project: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Return up to `limit` insights as plain serializable dicts, scoped to
    `workspace_slugs` (required — the tenant boundary).

    Shape matches InsightOut: id, project_slug, project_name, content,
    source, created_at (ISO string). `limit` is clamped to 100.
    """
    limit = min(max(limit, 0), 100)
    qs = insights_queryset(
        workspace_slugs=workspace_slugs, category=category, source=source, project=project
    )
    return [
        {
            "id": ins.pk,
            "project_slug": ins.project.slug,
            "project_name": ins.project.name,
            "content": ins.content,
            "source": ins.source,
            "created_at": ins.created_at.isoformat(),
        }
        for ins in qs[:limit]
    ]


def clear_insights(
    *,
    workspace_slugs: set[str],
    source: str | None = None,
    category: str | None = None,
    project: str | None = None,
    older_than_days: int | None = None,
) -> int:
    """Delete insights matching the filters; return the count deleted. Scoped to
    `workspace_slugs` (required): a no-filter clear deletes everything in the
    CALLER'S workspaces, never across the tenant boundary.
    """
    qs = insights_queryset(
        workspace_slugs=workspace_slugs,
        category=category,
        source=source,
        project=project,
        older_than_days=older_than_days,
    )
    count = qs.count()
    qs.delete()
    return count
