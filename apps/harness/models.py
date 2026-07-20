"""Agent-execution harness: runner registry, turns, and the turn-event ledger.

Framework tier. A Turn is the execution envelope for one unit of agent work;
Runners are executors that dial out (heartbeat + claim); TurnEvents are the
append-only ledger. See docs/superpowers/specs/2026-07-05-agent-execution-
control-plane-design.md.
"""
from __future__ import annotations

import datetime as dt
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

# Owned here (not services.py) so Runner.live_status can use it without a
# models -> services import cycle (services already imports models). services.py
# imports this constant from here rather than declaring a second one.
HEARTBEAT_ONLINE_WINDOW = dt.timedelta(seconds=90)


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
    # Can this runner actually FIRE a turn right now — distinct from being online.
    # Set from the heartbeat: the runner self-reports cdp_healthy() AND not-recently-
    # failed. `available = live_status == ONLINE and ready` (the Phase B cascade gate).
    # Defaults True so an un-upgraded runner reads as able to fire, matching prior behavior.
    ready = models.BooleanField(default=True)
    ready_note = models.CharField(max_length=200, blank=True, default="")
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    # macOS user @ hostname that owns this runner. Load-bearing for session reuse:
    # emdash sessions are per-macOS-account (separate emdash4.db, worktrees, transcripts),
    # so a live session is reusable ONLY by the runner whose host matches the one that
    # created it. Jonathan runs the fleet under two accounts (token-limit failover).
    host = models.CharField(max_length=200, blank=True, default="")
    # The human who paired this runner. Load-bearing for authz AND for tenancy:
    # `_runner_visibility_q` requires paired_by to be the caller (or NULL, the
    # legacy-ungated path it keeps open on purpose), and BOTH `_runner_schedule_qs`
    # and `claim_next_turn` derive the tenant from it — a runner may sync/fire/claim
    # for agents in any workspace its pairer belongs to.
    #
    # OPERATIONAL CONSEQUENCE — deleting a pairing user permanently bricks their
    # runners. SET_NULL orphans the row rather than removing it; `paired_by_id`
    # becomes NULL, `_runner_schedule_qs` returns none() for a NULL pairer, and
    # `claim_next_turn` resolves an empty workspace set — so the orphan can never
    # sync, fire, or claim anything tenanted again. It must be re-paired (a fresh
    # row) and the orphan retired.
    #
    # This fail-closed behaviour is CORRECT and must stay: a runner whose owner no
    # longer exists has no tenant to derive, and inferring one would be a privilege
    # escalation. Deactivate a departing user (`is_active=False`) rather than
    # deleting them if their runners should stay operable for a successor.
    #
    # `workspace` (below) is where the runner LIVES — it is NOT the claim
    # boundary, and must not be made one. Scoping claims to that single FK is
    # exactly the outage this fleet hit: one laptop runner serves an agent fleet
    # that deliberately spans workspaces, so FK-scoping left 4 of 5 agents unable
    # to execute any turn. The FK gates runner VISIBILITY (`_runner_visibility_q`,
    # `list_runners`); `paired_by` gates what a runner may WORK FOR.
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

    def project_names(self) -> list[str]:
        """The repos this runner declares it can drive. Like `agents`, this is a
        self-declared ROUTING hint, not a security boundary — the workspace is the
        gate, and the two intersect (b4f5ead). Empties are stripped: a session turn
        has project="", so a stray "" here would let a non-session runner match it
        via `project__in`."""
        return [p for p in self.capabilities.get("projects", []) if p]

    def session_capable(self) -> bool:
        """Whether this runner executes chat-session turns (the interactive
        front-door — SP2b). Opt-in via `capabilities.sessions: true` so a chat send
        only reaches a runner built for it (a cloud runner with claude), never a
        laptop emdash daemon. Like the other capabilities, a hint gated by tenant."""
        return bool(self.capabilities.get("sessions", False))

    @property
    def live_status(self) -> str:
        """What we can OBSERVE, not what the runner last claimed.

        `heartbeat()` writes ONLINE and nothing demotes it — a runner that dies
        never gets to tell us. So liveness is derived from heartbeat age here,
        and RunnerOut serves this rather than the raw column. `degraded` is
        different: the runner self-reports it, so it survives as long as the
        runner is still fresh enough to be reporting anything at all.
        """
        if self.status == self.RETIRED:
            return self.RETIRED
        if self.last_heartbeat_at is None:
            return self.DISCONNECTED
        if timezone.now() - self.last_heartbeat_at > HEARTBEAT_ONLINE_WINDOW:
            return self.STALE
        return self.status


class Turn(models.Model):
    """One unit of agent work — the execution envelope around board commands."""

    QUEUED, CLAIMED, RUNNING, NEEDS_HUMAN = "queued", "claimed", "running", "needs_human"
    DONE, FAILED, LOST, MISSED = "done", "failed", "lost", "missed"
    STATUS_CHOICES = [
        (QUEUED, "Queued"), (CLAIMED, "Claimed"), (RUNNING, "Running"),
        (NEEDS_HUMAN, "Needs human"), (DONE, "Done"), (FAILED, "Failed"),
        (LOST, "Lost"), (MISSED, "Missed"),
    ]
    TERMINAL = {DONE, FAILED, LOST, MISSED}
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
    # A turn targets EITHER an agent or a repo — exactly one (see the
    # target_is_agent_xor_project constraint).
    #
    # related_name is harness_turns (not "turns"): apps.agents.AgentTurn — the
    # packaged turn *report* — already claims agent.turns.
    agent = models.ForeignKey(
        "agents.Agent", on_delete=models.CASCADE, related_name="harness_turns",
        null=True, blank=True,
    )
    # The repo case. The session you want to revise from the phone is working on
    # canopy-web — a repo, not an agent (of 22 emdash projects, ~5 are agents).
    # This is a data-model gap, not a capability one: cdp_control.create_task is
    # already project-generic and has no concept of an agent.
    #
    # A pseudo-agent per repo was rejected: it would serialize repo work behind
    # one_executing_turn_per_agent (emdash gives every task its own worktree, so
    # repo work is *meant* to parallelize) and give every repo KPIs, a needs-you
    # inbox, and a skills catalog it has no meaning for.
    project = models.CharField(max_length=100, blank=True, default="")
    # The chat case: a session turn (the interactive front-door). Its tenancy
    # derives from chat_session.workspace, and it serializes per SESSION (not per
    # agent) so two conversations with the same agent don't block each other.
    # Named chat_session (not session) — Turn already has a session_id CharField
    # (the emdash/claude live-session hint). String ref avoids an import cycle
    # (chat.services imports harness.services).
    chat_session = models.ForeignKey(
        "chat.Session", on_delete=models.CASCADE, null=True, blank=True,
        related_name="turns",
    )
    # Tenancy is DERIVED for agent turns (turn.agent.workspace) and session turns
    # (turn.chat_session.workspace) — denormalized tenancy drifts. A project turn has
    # no agent/session to derive from, so it is the one accepted exception: it
    # carries its own FK, read ONLY when agent and chat_session are both null.
    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.PROTECT, null=True, blank=True,
        related_name="project_turns",
        help_text="Set only for project turns, which have no agent to derive tenancy from.",
    )
    # The Item whose approval enqueued this turn — the other half of the cycle
    # (Item.raised_by points back). Null for turns with no decision behind them:
    # the phone composer (a human asking directly), cron schedules, inbox polls.
    raised_from = models.ForeignKey(
        "Item", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="dispatched_turns",
    )
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
    # The human who launched this turn, when a person did (a manual / phone-composer
    # enqueue). Null for cron / email / system origins and for dispatched turns.
    # Lets you filter "turns I launched" and notify the launcher when theirs fails.
    enqueued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="turns_enqueued",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["agent", "status"]),
        ]
        constraints = [
            # Serialize EXECUTION, not intake: queued turns stack freely.
            #
            # Stays AGENT-ONLY on purpose. An agent is one identity with one
            # continuous session, so serializing it is correct; a repo is not —
            # emdash gives every task its own worktree. Widening this to projects
            # would funnel all canopy-web work into a single lane.
            #
            # Project turns have agent=NULL and NULLs never compare equal, so they
            # do not participate here at all. That is load-bearing, not incidental,
            # so it has its own test.
            models.UniqueConstraint(
                fields=["agent"],
                condition=models.Q(status__in=["claimed", "running", "needs_human"]),
                name="one_executing_turn_per_agent",
            ),
            # A session serializes its own execution — one running turn per
            # conversation. Session turns have agent=NULL so they do not
            # participate in one_executing_turn_per_agent; NULLs never compare
            # equal, so agent/project turns do not participate here.
            models.UniqueConstraint(
                fields=["chat_session"],
                condition=models.Q(status__in=["claimed", "running", "needs_human"]),
                name="one_executing_turn_per_session",
            ),
            models.CheckConstraint(
                # Exactly one target: agent XOR project XOR chat_session.
                condition=(
                    models.Q(agent__isnull=False, project="", chat_session__isnull=True)
                    | models.Q(agent__isnull=True, chat_session__isnull=True) & ~models.Q(project="")
                    | models.Q(agent__isnull=True, project="", chat_session__isnull=False)
                ),
                name="turn_targets_agent_xor_project_xor_session",
            ),
        ]

    @property
    def target(self) -> str:
        """The emdash project to drive — an agent's slug or a repo's name. The CDP
        layer underneath takes a project name either way. A session turn drives its
        session's agent when it has one, else a session marker (the cloud runner,
        SP2b, resolves the session directly)."""
        if self.agent_id:
            return self.agent.slug
        if self.chat_session_id:
            return (
                self.chat_session.agent.slug
                if self.chat_session.agent_id
                else f"session:{self.chat_session_id.hex[:8]}"
            )
        return self.project

    def __str__(self) -> str:  # pragma: no cover
        return f"turn:{self.target}:{self.status}:{self.id.hex[:8]}"


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
    # Mirrors Turn: a link belongs to an agent XOR a repo. The phone owns a
    # persistent thread per target (`phone:{user}:{target}`), which is what lets
    # the emdash mirror stay deferred — you never enumerate emdash to reach a
    # thread you started from the phone.
    agent = models.ForeignKey(
        "agents.Agent", on_delete=models.CASCADE, related_name="session_links",
        null=True, blank=True,
    )
    project = models.CharField(max_length=100, blank=True, default="")
    # Tenant for PROJECT links only. Agent links derive their tenant via
    # agent.workspace and are gated by _agent_or_404 at the API; a project link
    # has no agent, so without this any runner could read another user's rolling
    # `summary` + live task id by guessing thread_key. Set at record time from the
    # claimed turn's workspace (which already passed the claim tenant gate).
    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.PROTECT, null=True, blank=True,
        related_name="project_session_links",
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
        indexes = [
            models.Index(fields=["agent", "thread_key"]),
            models.Index(fields=["project", "thread_key"]),
        ]
        constraints = [
            # TWO partial constraints, not one over a nullable column.
            #
            # `UniqueConstraint(fields=["agent", "thread_key"])` alone does NOT
            # constrain project links: their agent is NULL, and NULL never equals
            # NULL, so ("canopy-web", NULL, "phone:jj:canopy-web") would be
            # insertable twice — every phone message forking a new session, which
            # is exactly the duplicate-session failure the reuse path exists to
            # prevent. Each partial constraint covers the rows it applies to.
            models.UniqueConstraint(
                fields=["agent", "thread_key"],
                condition=models.Q(agent__isnull=False),
                name="sessionlink_unique_per_agent_thread",
            ),
            models.UniqueConstraint(
                # workspace is in the project link's IDENTITY (services._link_target):
                # a link is scoped to its tenant, so a guessed thread_key from
                # another workspace creates a separate row and cannot hijack this
                # one. (project, workspace) both non-NULL for every project row.
                fields=["project", "workspace", "thread_key"],
                condition=models.Q(agent__isnull=True),
                name="sessionlink_unique_per_project_thread",
            ),
            models.CheckConstraint(
                # An agent link derives tenancy and stores NO workspace (a stored
                # copy would be the denormalization we avoid). A project link MUST
                # carry one — the unique constraint above only dedupes when
                # workspace is non-NULL, so a NULL-workspace project row would
                # silently permit duplicate live-session hijacks.
                condition=(
                    models.Q(agent__isnull=False, project="", workspace__isnull=True)
                    | (
                        models.Q(agent__isnull=True)
                        & ~models.Q(project="")
                        & models.Q(workspace__isnull=False)
                    )
                ),
                name="sessionlink_targets_agent_xor_project",
            ),
        ]

    @property
    def target(self) -> str:
        return self.agent.slug if self.agent_id else self.project

    def __str__(self) -> str:  # pragma: no cover
        return f"link:{self.target}:{self.thread_key[:16]}"

    def reusable_by(self, runner: Runner) -> bool:
        """True if `runner` owns the live session hint (same runner + same macOS host)
        and a concrete emdash task is recorded. The runner STILL must verify the task
        actually exists in its emdash before driving it — this is the server-side gate."""
        return bool(
            self.live_emdash_task_id
            and self.live_runner_id == runner.id
            and self.live_host
            and self.live_host == runner.host
        )


class EmdashSession(models.Model):
    """A snapshot of one OPEN emdash session, reported by the runner that can see it.

    Ephemeral by design: the runner replaces its whole set every report tick, so this
    is "what emdash shows right now on that laptop", not a durable record. The durable
    half of continuing a session lives in SessionLink (the report upserts one too); this
    model is purely the phone's read model (list + recent messages).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    runner = models.ForeignKey(Runner, on_delete=models.CASCADE, related_name="emdash_sessions")
    # Tenant, first-class (defaults to dimagi at the reporting edge). PROTECT mirrors
    # the project-turn workspace: a tenant with live sessions should not vanish under them.
    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.PROTECT, related_name="emdash_sessions"
    )
    emdash_task = models.CharField(max_length=200, help_text="The emdash task NAME — what open_and_send targets.")
    project = models.CharField(max_length=100, blank=True, default="")
    status = models.CharField(max_length=40, blank=True, default="")
    last_interacted_at = models.DateTimeField(null=True, blank=True)
    recent_messages = models.JSONField(default=list, blank=True)  # Phase B fills this; [] in Phase A
    reported_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_interacted_at"]
        constraints = [
            models.UniqueConstraint(fields=["runner", "emdash_task"], name="emdashsession_unique_per_runner_task"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"emdash-session:{self.runner_id}:{self.emdash_task}"


def _default_notify() -> list:
    """Callable default — a mutable literal would be shared across rows."""
    return ["inbox"]


class AgentSchedule(models.Model):
    """A recurring turn declaration — "Echo's weekly manager report, Fridays 9am ET".

    Config lives here (server-side, so it is visible and editable in the Agent
    UI); the *firing* is done by the runner, which syncs these rows, evaluates
    the cron locally, and POSTs back a slot. The server then materializes a
    normal harness Turn via services.enqueue_turn — the scheduler is a producer
    of turns, not a second execution engine.

    The Turn IS the occurrence (origin=cron, origin_ref={schedule_id, slot},
    idempotency_key="sched:<id>:<slot>"); there is deliberately no occurrence
    table. See docs/superpowers/specs/2026-07-15-agent-scheduled-turns-design.md.

    int pk (not UUID like Runner/Turn): this projects into needs_you, whose
    NeedsYouItem.ref_id is typed int on a StrictModel.

    No workspace FK: a schedule is agent-owned and derives its tenant via
    agent.workspace, exactly as Turn does.
    """

    agent = models.ForeignKey("agents.Agent", on_delete=models.CASCADE, related_name="schedules")
    # WHO set this up / last changed it. Distinct from `agent` (which agent it fires)
    # and from tenancy (agent.workspace): a schedule is a person's standing request,
    # so the calendar can show "my schedules" and a MISSED occurrence can notify the
    # human who created it. Nullable — SET_NULL so a departed user doesn't cascade the
    # schedule away, and null for pre-attribution rows.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="schedules_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="schedules_updated",
    )
    name = models.CharField(max_length=200, help_text='e.g. "Weekly manager report"')
    prompt = models.TextField(help_text="What the turn is seeded with, e.g. /echo:manager-report")
    cron = models.CharField(max_length=120, help_text="5-field cron expression, e.g. '0 9 * * 5'")
    timezone = models.CharField(max_length=64, default="UTC", help_text="IANA tz, e.g. America/New_York")
    enabled = models.BooleanField(default=True, help_text="Pause without deleting.")
    routing = models.CharField(max_length=15, choices=Turn.ROUTING_CHOICES, default=Turn.PREFER_LOCAL)
    grace_minutes = models.PositiveIntegerField(
        default=120,
        help_text="How long an unattended fired turn may hold the agent before it is "
        "released as MISSED. Guards one_executing_turn_per_agent: an abandoned "
        "session would otherwise wedge the agent indefinitely.",
    )
    notify = models.JSONField(
        default=_default_notify, blank=True,
        help_text='Channel ids resolved through the notify registry, e.g. ["inbox"].',
    )
    last_slot = models.DateTimeField(
        null=True, blank=True,
        help_text="Newest slot fired. The supersede + no-backfill anchor.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["agent", "enabled"])]
        constraints = [
            models.UniqueConstraint(fields=["agent", "name"], name="uniq_agent_schedule_name"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"sched:{self.agent.slug}:{self.name}"

    @property
    def agent_slug(self) -> str:
        return self.agent.slug


class Item(models.Model):
    """A thing that needs addressing — the dual of Turn.

    Turn is work an agent does; Item is work YOU do. They form a cycle: a turn
    raises items, you decide them, and an approved item's `dispatch` enqueues
    turns. Ada's cross-agent fan-out is that same edge with TurnSpec.target_agent
    set; the default ("") is self-dispatch. A parameter, not a code path.

    The Item carries its OWN text. It is not a mirror of a subject living
    elsewhere — it is an utterance at a moment, like an email, which never
    re-reads the thing it describes. `origin_ref` is provenance (evidence, deep
    links), NOT identity: nothing resolves it to render this row. That is what
    keeps this model free of a source registry, of drift, and of any
    framework->product import.

    See docs/superpowers/specs/2026-07-15-item-and-turn-design.md.
    """

    REVIEW, QUESTION = "review", "question"
    KIND_CHOICES = [(REVIEW, "Review"), (QUESTION, "Question")]

    OPEN, DECIDED, DISMISSED = "open", "decided", "dismissed"
    STATE_CHOICES = [(OPEN, "Open"), (DECIDED, "Decided"), (DISMISSED, "Dismissed")]

    # CLOSED set. A generic inbox must be able to render three buttons for an Item
    # it has never seen; producer-defined verbs would make that impossible.
    # Only IMPLEMENT dispatches. DEFER decides the item and signals the producer to
    # raise it again later, on its own schedule.
    IMPLEMENT, SKIP, DEFER = "implement", "skip", "defer"
    DECISION_CHOICES = [(IMPLEMENT, "Implement"), (SKIP, "Skip"), (DEFER, "Defer")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(
        "agents.Agent", on_delete=models.CASCADE, related_name="items",
        help_text="Whose queue this belongs to — the agent ASKING, not the "
                  "dispatch target. Tenancy rides this FK, as Turn's does.",
    )
    raised_by = models.ForeignKey(
        Turn, on_delete=models.SET_NULL, null=True, blank=True, related_name="raised_items",
        help_text="The turn that produced this item. Null for items raised outside "
                  "a turn (an email poll, a manual post).",
    )

    origin = models.CharField(max_length=10, choices=Turn.ORIGIN_CHOICES)
    origin_ref = models.JSONField(default=dict, blank=True)

    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=REVIEW)
    title = models.CharField(max_length=300)
    body = models.TextField(blank=True, default="")

    state = models.CharField(max_length=10, choices=STATE_CHOICES, default=OPEN)
    decision = models.CharField(max_length=10, choices=DECISION_CHOICES, blank=True, default="")
    comment = models.TextField(
        blank=True, default="",
        help_text="kind=review: the reviewer's note (optional). "
                  "kind=question: the answer (required to decide).",
    )
    # decided_by is the human decision's attribution. The string is kept as a
    # display fallback (and for historical rows), but decided_by_user is the real
    # relationship — a member decides an item via a live request, so unlike the
    # ingest/caller-supplied deciders elsewhere, request.user IS the decider.
    decided_by = models.CharField(max_length=200, blank=True, default="")
    decided_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="items_decided",
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    dispatch = models.JSONField(
        default=list, blank=True,
        help_text='[TurnSpec] — deferred Turn enqueues fired on implement. '
                  'e.g. [{"target_agent": "hal", "prompt": "/hal:turn", "origin": "email"}]',
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)

    batch_key = models.CharField(
        max_length=120, blank=True, default="", db_index=True,
        help_text="Groups items reviewed in one sitting (e.g. a fleet audit).",
    )
    idempotency_key = models.CharField(max_length=128, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["agent", "state"]),
            models.Index(fields=["state", "created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"item:{self.agent.slug}:{self.kind}:{self.state}:{self.id.hex[:8]}"

    @property
    def agent_slug(self) -> str:
        return self.agent.slug
