"""First-class AI-agent workspace.

An `Agent` is a first-class entity (e.g. "Echo," a marketing agent) — distinct
from a code Project. Where a Project's work shows up as static markdown
shareouts, an Agent's periodic sync is a **Google Doc** (`AgentSync.doc_url`),
because an agent's sync spans both code/skill improvement AND work products and
is richer than a feed card. canopy-web stores the metadata, summary, and
self-grades for the feed; the body lives in the doc.
"""
from django.conf import settings
from django.db import models


class Agent(models.Model):
    """A first-class AI agent that publishes its work into canopy-web."""

    slug = models.SlugField(unique=True, max_length=80)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    persona = models.TextField(blank=True, default="", help_text="Who the agent is / its remit.")
    email = models.EmailField(blank=True, default="", help_text="The agent's own mailbox, if any.")
    avatar_url = models.URLField(blank=True, default="", max_length=500)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agents",
        help_text="The human who operates the agent.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"agent:{self.slug}"


class AgentSync(models.Model):
    """A periodic manager sync — a Google Doc covering code/skill improvement AND
    work products. Body lives in `doc_url`; canopy-web keeps the summary +
    self-grades for the feed. Idempotent per (agent, period_start, period_end,
    source): re-posting the same window from the same source replaces it."""

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="syncs")
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True, default="")
    doc_url = models.URLField(max_length=500, help_text="The Google Doc holding the full sync.")
    # Structured self-grades, e.g. {"work": "C+", "skills": "B-"}.
    self_grades = models.JSONField(default=dict, blank=True)
    source = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_end", "-created_at"]
        indexes = [models.Index(fields=["agent", "-period_end"])]

    def __str__(self):
        return f"sync:{self.agent.slug}:{self.period_start}..{self.period_end}"

    @property
    def agent_slug(self) -> str:
        return self.agent.slug


class AgentWorkProduct(models.Model):
    """A deliverable the agent produced — a gdoc, form, story, etc. Idempotent
    per (agent, url, source)."""

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="work_products")
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=40, blank=True, default="", help_text="doc / form / story / …")
    url = models.URLField(max_length=500)
    description = models.TextField(blank=True, default="")
    tags = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["agent", "url"], name="uniq_agent_workproduct_url"),
        ]

    def __str__(self):
        return f"work:{self.agent.slug}:{self.title}"

    @property
    def agent_slug(self) -> str:
        return self.agent.slug


class AgentSkill(models.Model):
    """An entry in the agent's skill catalog: what the skill does, a link to its
    definition (SKILL.md), and the latest improvement note. The catalog is
    replaced wholesale on each publish (PUT) so it always mirrors the repo."""

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="skills")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    url = models.URLField(max_length=500, blank=True, default="", help_text="Link to the SKILL.md.")
    improvement_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["agent", "name"], name="uniq_agent_skill"),
        ]

    def __str__(self):
        return f"skill:{self.agent.slug}:{self.name}"

    @property
    def agent_slug(self) -> str:
        return self.agent.slug


class AgentTask(models.Model):
    """A task in the agent's tracker. Source of truth is a Google Sheet the
    agent maintains; Echo syncs rows here so canopy-web can render a board.
    `status` is normalized to one of the board columns. Synced wholesale per
    agent, keyed by `ext_id` (stable sheet-row id) so edits/removals
    propagate."""

    # Suggested = the agent proposed it; a human must validate (Linear "Triage").
    # No "To do" (the agent would just do it) and no "Blocked" column — "waiting
    # on a person" is expressed by `assigned` being a human, shown as an overlay.
    SUGGESTED, IN_PROGRESS, DONE, DECLINED = "suggested", "in_progress", "done", "declined"
    STATUS_CHOICES = [
        (SUGGESTED, "Suggested"),
        (IN_PROGRESS, "In progress"),
        (DONE, "Done"),
        (DECLINED, "Declined"),
    ]

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="tasks")
    ext_id = models.CharField(max_length=64, help_text="Stable id from the source sheet.")
    title = models.CharField(max_length=300, help_text="The outcome.")
    next_action = models.CharField(max_length=300, blank=True, default="", help_text="The single concrete next step (verb-first).")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=SUGGESTED)
    owner = models.CharField(max_length=120, blank=True, default="", help_text="Human stakeholder who owns the outcome — never the agent.")
    assigned = models.CharField(max_length=120, blank=True, default="", help_text="Who the next action waits on — the agent or a person.")
    confidence = models.CharField(max_length=10, blank=True, default="", help_text="high / low — how sure the agent is about a suggestion.")
    due = models.DateField(null=True, blank=True)
    links = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True, default="")
    position = models.IntegerField(default=0, help_text="Order within a status column.")
    source = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["agent", "ext_id"], name="uniq_agent_task_extid"),
        ]
        indexes = [models.Index(fields=["agent", "status"])]

    def __str__(self):
        return f"task:{self.agent.slug}:{self.ext_id}:{self.status}"

    @property
    def agent_slug(self) -> str:
        return self.agent.slug
