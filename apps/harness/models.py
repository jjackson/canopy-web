"""Agent-execution harness: runner registry, turns, and the turn-event ledger.

Framework tier. A Turn is the execution envelope for one unit of agent work;
Runners are executors that dial out (heartbeat + claim); TurnEvents are the
append-only ledger. See docs/superpowers/specs/2026-07-05-agent-execution-
control-plane-design.md.
"""
from __future__ import annotations

import uuid

from django.db import models


class Runner(models.Model):
    """A paired executor (laptop emdash daemon, cloud container, remote box)."""

    EMDASH, CLOUD, REMOTE = "emdash", "cloud", "remote"
    KIND_CHOICES = [(EMDASH, "Emdash"), (CLOUD, "Cloud"), (REMOTE, "Remote")]

    ONLINE, STALE, DISCONNECTED, DEGRADED, RETIRED = (
        "online", "stale", "disconnected", "degraded", "retired",
    )
    STATUS_CHOICES = [
        (ONLINE, "Online"), (STALE, "Stale"), (DISCONNECTED, "Disconnected"),
        (DEGRADED, "Degraded"), (RETIRED, "Retired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    capabilities = models.JSONField(default=dict, help_text='e.g. {"agents": ["echo"]}')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=DISCONNECTED)
    status_note = models.CharField(max_length=255, blank=True, default="")
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    # macOS user @ hostname that owns this runner. Load-bearing for session reuse:
    # emdash sessions are per-macOS-account (separate emdash4.db, worktrees, transcripts),
    # so a live session is reusable ONLY by the runner whose host matches the one that
    # created it. Jonathan runs the fleet under two accounts (token-limit failover).
    host = models.CharField(max_length=200, blank=True, default="")
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="runners",
        help_text="The tenant that owns this runner. Nullable for migration "
        "safety; the API assigns one at pairing (the pairer's default workspace "
        "when unspecified). Mirrors Agent.workspace.",
    )
    paired_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    paired_at = models.DateTimeField(auto_now_add=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["kind", "status"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"runner:{self.name}:{self.kind}:{self.status}"

    def agent_slugs(self) -> list[str]:
        return list(self.capabilities.get("agents", []))


class Turn(models.Model):
    """One unit of agent work — the execution envelope around board commands."""

    QUEUED, CLAIMED, RUNNING, NEEDS_HUMAN = "queued", "claimed", "running", "needs_human"
    DONE, FAILED, LOST = "done", "failed", "lost"
    STATUS_CHOICES = [
        (QUEUED, "Queued"), (CLAIMED, "Claimed"), (RUNNING, "Running"),
        (NEEDS_HUMAN, "Needs human"), (DONE, "Done"), (FAILED, "Failed"), (LOST, "Lost"),
    ]
    TERMINAL = {DONE, FAILED, LOST}
    NON_TERMINAL = {QUEUED, CLAIMED, RUNNING, NEEDS_HUMAN}

    ORIGIN_BOARD, ORIGIN_API, ORIGIN_SLACK, ORIGIN_CRON, ORIGIN_MANUAL, ORIGIN_EMAIL = (
        "board", "api", "slack", "cron", "manual", "email",
    )
    ORIGIN_CHOICES = [
        (ORIGIN_BOARD, "Board"), (ORIGIN_API, "API"), (ORIGIN_SLACK, "Slack"),
        (ORIGIN_CRON, "Cron"), (ORIGIN_MANUAL, "Manual"), (ORIGIN_EMAIL, "Email"),
    ]

    PREFER_LOCAL, LOCAL_ONLY, ANY = "prefer_local", "local_only", "any"
    ROUTING_CHOICES = [(PREFER_LOCAL, "Prefer local"), (LOCAL_ONLY, "Local only"), (ANY, "Any")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # related_name is harness_turns (not "turns"): apps.agents.AgentTurn — the
    # packaged turn *report* — already claims agent.turns.
    agent = models.ForeignKey("agents.Agent", on_delete=models.CASCADE, related_name="harness_turns")
    origin = models.CharField(max_length=10, choices=ORIGIN_CHOICES)
    origin_ref = models.JSONField(default=dict, blank=True)
    prompt = models.TextField(blank=True, default="")
    routing = models.CharField(max_length=15, choices=ROUTING_CHOICES, default=PREFER_LOCAL)
    idempotency_key = models.CharField(max_length=128, unique=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=QUEUED)
    claimed_by = models.ForeignKey(
        Runner, on_delete=models.SET_NULL, null=True, blank=True, related_name="turns"
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    session_id = models.CharField(max_length=64, blank=True, default="")
    result_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["agent", "status"]),
        ]
        constraints = [
            # Serialize EXECUTION, not intake: queued turns stack freely.
            models.UniqueConstraint(
                fields=["agent"],
                condition=models.Q(status__in=["claimed", "running", "needs_human"]),
                name="one_executing_turn_per_agent",
            )
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"turn:{self.agent.slug}:{self.status}:{self.id.hex[:8]}"


class TurnEvent(models.Model):
    """Append-only per-turn ledger. seq is monotonic per turn (assigned in services)."""

    turn = models.ForeignKey(Turn, on_delete=models.CASCADE, related_name="events")
    seq = models.PositiveIntegerField()
    ts = models.DateTimeField(auto_now_add=True)
    kind = models.CharField(max_length=20)  # status|assistant|tool_start|tool_end|question|error|heartbeat
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["seq"]
        constraints = [
            models.UniqueConstraint(fields=["turn", "seq"], name="turnevent_seq_unique_per_turn")
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"evt:{self.turn_id}:{self.seq}:{self.kind}"


class SessionLink(models.Model):
    """Durable link between an external work thread (an email thread_id, or a topic
    key) and the agent session that handles it — the cross-account source of truth.

    Two halves, deliberately:

    - **Durable** (this row, on the server → reachable from ANY macOS account):
      `agent` + `thread_key` (unique together), the board task the thread maps to
      (`agent_task_ext_id`, for context), and a rolling `summary` used to rehydrate a
      fresh session when the live one can't be reused.
    - **Ephemeral live-session hint** (`live_*`): which emdash task / claude session
      currently embodies this thread, and which runner/macOS-host owns it. emdash is
      per-macOS-account, so this is reusable ONLY when the CURRENTLY-active runner owns
      it AND the session still exists (the runner verifies existence). Otherwise: spawn
      fresh under the current account and rehydrate from the durable half, then re-point.

    See docs + [[env-two-macos-users]]: Jonathan fails over between two macOS accounts,
    so the link can never be a local emdash id alone.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(
        "agents.Agent", on_delete=models.CASCADE, related_name="session_links"
    )
    thread_key = models.CharField(max_length=255, help_text="Gmail thread_id or a topic key")
    agent_task_ext_id = models.CharField(max_length=255, blank=True, default="")
    summary = models.TextField(blank=True, default="", help_text="Rolling context for rehydration")

    # Ephemeral live-session hint — verify-before-reuse (see class docstring).
    live_runner = models.ForeignKey(
        Runner, on_delete=models.SET_NULL, null=True, blank=True, related_name="session_links"
    )
    live_host = models.CharField(max_length=200, blank=True, default="")
    live_emdash_task_id = models.CharField(max_length=64, blank=True, default="")
    live_session_id = models.CharField(max_length=64, blank=True, default="")
    live_seen_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["agent", "thread_key"])]
        constraints = [
            models.UniqueConstraint(fields=["agent", "thread_key"], name="sessionlink_unique_per_agent_thread")
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"link:{self.agent.slug}:{self.thread_key[:16]}"

    def reusable_by(self, runner: "Runner") -> bool:
        """True if `runner` owns the live session hint (same runner + same macOS host)
        and a concrete emdash task is recorded. The runner STILL must verify the task
        actually exists in its emdash before driving it — this is the server-side gate."""
        return bool(
            self.live_emdash_task_id
            and self.live_runner_id == runner.id
            and self.live_host
            and self.live_host == runner.host
        )
