"""Live chat sessions — the interactive front-door to a durable harness Turn.

A Session is a conversation thread. A "send" enqueues a harness Turn (target=
session); the assistant's output lands in the TurnEvent ledger and is projected
here as Message rows. Framework tier, agent-agnostic: `metadata` carries opaque
product linkage (e.g. ace-web's opp_slug) the framework never interprets.

See docs/superpowers/specs/2026-07-16-sp2-unified-execution-spine-design.md.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class Session(models.Model):
    ACTIVE, ARCHIVED = "active", "archived"
    STATUS_CHOICES = [(ACTIVE, "Active"), (ARCHIVED, "Archived")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # You chat WITH an agent (nullable — a session can be agent-agnostic).
    agent = models.ForeignKey(
        "agents.Agent", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="chat_sessions",
    )
    # The tenant. Unlike agent turns (which derive tenancy via agent.workspace),
    # a session carries its own workspace so an agent-less session still has one.
    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.PROTECT, related_name="chat_sessions",
    )
    title = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=ACTIVE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
    )
    # Continuity hint for the real subprocess runner (SP2b): the claude CLI
    # session to --resume. Unused by the stub.
    cli_session_id = models.CharField(max_length=64, blank=True, default="")
    # Opaque product linkage (e.g. {"opp_slug": "..."}) — never interpreted here.
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"session:{self.id.hex[:8]}:{self.status}"


class Message(models.Model):
    """A projected transcript row. User messages are written at send time; the
    rest are materialized from the TurnEvent ledger by the projection receiver.
    turn_index is monotonic per session (a session-wide order across turns)."""

    USER, ASSISTANT, TOOL_USE, TOOL_RESULT, SYSTEM = (
        "user", "assistant", "tool_use", "tool_result", "system",
    )
    ROLE_CHOICES = [
        (USER, "User"), (ASSISTANT, "Assistant"), (TOOL_USE, "Tool use"),
        (TOOL_RESULT, "Tool result"), (SYSTEM, "System"),
    ]

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="messages")
    # Null for user messages (a human send precedes any turn execution).
    turn = models.ForeignKey(
        "harness.Turn", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="messages",
    )
    turn_index = models.PositiveIntegerField()
    role = models.CharField(max_length=12, choices=ROLE_CHOICES)
    content = models.JSONField(default=dict, blank=True)
    plaintext = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["turn_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "turn_index"], name="message_index_unique_per_session"
            )
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"msg:{self.session_id.hex[:8]}:{self.turn_index}:{self.role}"


class SessionParticipant(models.Model):
    """Durable membership + role in a session (SP3 multiplayer). Presence — who is
    here *right now* — is ephemeral and lives in the cache (apps/chat/presence.py);
    this row is the authority for access and role."""

    OWNER, EDITOR, VIEWER = "owner", "editor", "viewer"
    ROLE_CHOICES = [(OWNER, "Owner"), (EDITOR, "Editor"), (VIEWER, "Viewer")]

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=EDITOR)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "user"], name="one_participant_per_session_user"
            )
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"participant:{self.session_id.hex[:8]}:{self.user_id}:{self.role}"


class Draft(models.Model):
    """The shared, co-edited outgoing message (SP3 multiplayer). One OPEN draft
    (slot='next') per session; an optimistic `version` guards concurrent edits, and
    the soft-lock holder is derived (last_editor + updated_at + presence), not stored."""

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="drafts")
    slot = models.CharField(max_length=16, default="next")
    body = models.TextField(blank=True, default="")
    version = models.PositiveIntegerField(default=0)
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session"],
                condition=models.Q(slot="next"),
                name="one_open_draft_per_session",
            )
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"draft:{self.session_id.hex[:8]}:v{self.version}"
