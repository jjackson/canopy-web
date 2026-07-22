"""Fan-out receivers: turn the harness write path into live WS frames.

Mirrors apps/push/signals.py — a signal / post_save receiver schedules a
group_send on transaction.on_commit. Every publish is null-safe (see
groups.publish), so a realtime failure never breaks the write that triggered it.

Three sources, three frame types:
  - turn_events_appended (harness)       -> turn.{id}            "turn.event"
  - post_save Runner (harness)           -> supervisor.user.{id} "supervisor.runner"
  - post_save AgentWaitingSnapshot(push) -> supervisor.user.{id} "supervisor.waiting"

turn_events_appended is already sent post-commit (append_events fires it inside
its own on_commit), so its receiver publishes directly. The two post_save
receivers fire mid-transaction, so they defer their publish to on_commit.
"""
from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.harness.models import Runner, Turn
from apps.harness.signals import turn_events_appended
from apps.push.models import AgentWaitingSnapshot
from apps.workspaces.services import workspace_member_ids

from . import groups


@receiver(turn_events_appended, dispatch_uid="realtime_turn_events")
def _on_turn_events(sender, turn, rows, **kwargs):
    events = [groups.serialize_turn_event(row) for row in rows]
    group = groups.turn_group(turn.id)
    for event in events:
        groups.publish(group, {"type": "turn.event", "event": event})
    # A session turn also fans out to the per-session multiplayer group (SP3), so
    # every participant on the session socket sees the streamed response. Uses the
    # field only (turn.chat_session_id) — no chat-app import here.
    if turn.chat_session_id:
        sgroup = groups.session_group(turn.chat_session_id)
        for event in events:
            groups.publish(sgroup, {"type": "chat.turn_event", "event": event})


@receiver(post_save, sender=Turn, dispatch_uid="realtime_runnable_wake")
def _on_turn_enqueued(sender, instance: Turn, created, **kwargs):
    """A newly-QUEUED turn wakes runners in its tenant so a blocked/idle runner
    claims it now instead of waiting out its poll interval. Coarse per-workspace
    wake — it only PROMPTS a claim; claim_next_turn still gates everything. Deferred
    to on_commit (create fires mid-transaction) and null-safe like every publish."""
    if not created or instance.status != Turn.QUEUED:
        return
    slug = groups.turn_workspace_slug(instance)
    if not slug:
        return
    transaction.on_commit(
        lambda: groups.publish(groups.runnable_group(slug), {"type": "runner.wake"})
    )


@receiver(post_save, sender=Runner, dispatch_uid="realtime_runner")
def _on_runner_saved(sender, instance: Runner, **kwargs):
    # A runner with no pairer has no user to notify (and no derivable tenant).
    if not instance.paired_by_id:
        return
    frame = {
        "type": "supervisor.runner",
        "runner": {
            "id": str(instance.id),
            "name": instance.name,
            "kind": instance.kind,
            "status": instance.live_status,
            "last_heartbeat_at": (
                instance.last_heartbeat_at.isoformat() if instance.last_heartbeat_at else None
            ),
        },
    }
    group = groups.supervisor_user_group(instance.paired_by_id)
    transaction.on_commit(lambda: groups.publish(group, frame))


@receiver(post_save, sender=AgentWaitingSnapshot, dispatch_uid="realtime_waiting")
def _on_waiting_saved(sender, instance: AgentWaitingSnapshot, **kwargs):
    agent = instance.agent
    if not agent.workspace_id:
        return
    frame = {
        "type": "supervisor.waiting",
        "agent": agent.slug,
        "waiting_count": instance.waiting_count,
    }
    member_ids = workspace_member_ids(agent.workspace)

    def _fire():
        for uid in member_ids:
            groups.publish(groups.supervisor_user_group(uid), frame)

    transaction.on_commit(_fire)
