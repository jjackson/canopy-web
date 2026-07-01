from django.db import models

from apps.projects.models import Project


class Shareout(models.Model):
    """A dated, teammate-facing work briefing.

    One row per project per period; a row with `project=None` is the
    cross-project roll-up for that period. Posted by the `canopy:shareout`
    skill. Re-running the same period from the same source replaces the
    prior rows (see `apps.shareouts.services.upsert_shareouts`), so the feed
    is a clean log rather than an append pile.
    """

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="shareouts",
        null=True,
        blank=True,
        help_text="Null = cross-project roll-up for the period.",
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.PROTECT,
        related_name="shareouts",
        null=True,
        blank=True,
        help_text=(
            "The tenant that owns this shareout. Shareout is its own tenant root "
            "(the project FK is orthogonal). Nullable for migration safety; the "
            "API always assigns one (default workspace when unspecified)."
        ),
    )
    # Timestamps (not dates): a shareout is rarely run on a clean day boundary,
    # so the window is precise to the second and consecutive shareouts chain
    # exactly (next.period_start == prev.period_end).
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True, default="")
    content = models.TextField()
    links = models.JSONField(default=list, blank=True)
    # Curated highlight links (subset of all_prs, most relevant first).
    all_prs = models.JSONField(default=list, blank=True)
    # Every PR in the window for this project: [{number,title,url,state}].
    author = models.CharField(max_length=100, blank=True, default="")
    source = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_end", "-created_at"]
        indexes = [
            models.Index(fields=["-period_end", "-period_start"]),
        ]

    def __str__(self):
        scope = self.project.slug if self.project_id else "roll-up"
        return f"shareout:{scope}:{self.period_start}..{self.period_end}"
