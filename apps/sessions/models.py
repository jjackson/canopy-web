"""Models for shared Claude Code session transcripts.

A ``Session`` is one uploaded ``.jsonl`` transcript, decomposed into ordered
``Message`` rows. Sharing is link-by-default: every upload mints a
``ShareToken`` so the returned ``/share/<token>`` URL works immediately.
The owner can rotate (invalidate the old link) or revoke (make it private).

This is the generic counterpart to ace-web's opportunity-scoped sessions app:
the parser + message shape are ported verbatim, but the ACE opp-linkage,
multiplayer participants, drafts, and live-streaming machinery are dropped —
uploaded transcripts are static and single-owner.
"""
from __future__ import annotations

import secrets

from django.conf import settings
from django.db import IntegrityError, models, transaction


def generate_slug() -> str:
    """8-character URL-safe random slug for a session."""
    return secrets.token_urlsafe(6)[:8]


def generate_share_token() -> str:
    """24-byte URL-safe random token (~32 chars) for a public share link."""
    return secrets.token_urlsafe(24)


class Session(models.Model):
    VISIBILITY_PRIVATE = "private"
    VISIBILITY_LINK = "link"
    VISIBILITY_CHOICES = [
        (VISIBILITY_PRIVATE, "Private (dimagi only)"),
        (VISIBILITY_LINK, "Link (anyone with token)"),
    ]

    slug = models.CharField(max_length=32, unique=True, default=generate_slug)
    title = models.CharField(max_length=500, blank=True, default="")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shared_sessions",
    )
    project_slug = models.CharField(
        max_length=200, blank=True, null=True, db_index=True
    )
    visibility = models.CharField(
        max_length=10, choices=VISIBILITY_CHOICES, default=VISIBILITY_LINK
    )

    # The Claude CLI session id (from the `init` line). Used to dedup repeated
    # uploads of the same transcript — a second upload returns the existing
    # session instead of creating a duplicate.
    cli_session_id = models.CharField(max_length=200, blank=True, default="")

    # Best-effort secret scrub stats, stamped at ingest.
    redaction_count = models.IntegerField(default=0)

    # Ingest provenance (audit + UI metadata).
    source_filename = models.CharField(max_length=500, blank=True, default="")
    raw_bytes = models.BigIntegerField(default=0)
    line_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shared_sessions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["project_slug", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.slug}: {self.title or '(untitled)'}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = generate_slug()
        # Each attempt runs in its own savepoint so a duplicate-slug
        # IntegrityError rolls back only this attempt and doesn't poison an
        # enclosing transaction.
        for _ in range(5):
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                if not self.pk:
                    self.slug = generate_slug()
                    continue
                raise
        raise IntegrityError("Could not generate a unique slug after 5 attempts")

    def active_token(self) -> "ShareToken | None":
        return (
            self.share_tokens.filter(revoked_at__isnull=True)
            .order_by("-created_at")
            .first()
        )

    def ensure_share_token(self, created_by) -> "ShareToken":
        """Return the active token, minting one (and flipping to link) if none."""
        token = self.active_token()
        if token is None:
            token = ShareToken.objects.create(session=self, created_by=created_by)
            if self.visibility != self.VISIBILITY_LINK:
                self.visibility = self.VISIBILITY_LINK
                self.save(update_fields=["visibility", "updated_at"])
        return token

    def rotate_share_token(self, created_by) -> "ShareToken":
        """Revoke any active token and mint a fresh one. Returns the new token."""
        from django.utils import timezone

        self.share_tokens.filter(revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
        token = ShareToken.objects.create(session=self, created_by=created_by)
        if self.visibility != self.VISIBILITY_LINK:
            self.visibility = self.VISIBILITY_LINK
            self.save(update_fields=["visibility", "updated_at"])
        return token

    def revoke_sharing(self) -> None:
        """Revoke all active tokens and mark the session private."""
        from django.utils import timezone

        self.share_tokens.filter(revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
        if self.visibility != self.VISIBILITY_PRIVATE:
            self.visibility = self.VISIBILITY_PRIVATE
            self.save(update_fields=["visibility", "updated_at"])


class Message(models.Model):
    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
        ("system", "System"),
        ("tool_use", "Tool use"),
        ("tool_result", "Tool result"),
    ]

    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name="messages"
    )
    turn_index = models.IntegerField()
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.JSONField()
    plaintext = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shared_session_messages"
        ordering = ["session_id", "turn_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "turn_index"],
                name="unique_shared_session_turn",
            ),
        ]

    def __str__(self):
        return f"[{self.session_id}] turn {self.turn_index} ({self.role})"


class ShareToken(models.Model):
    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name="share_tokens"
    )
    token = models.CharField(max_length=64, unique=True, default=generate_share_token)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shared_session_share_tokens",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shared_session_share_tokens"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Token {self.token[:8]}… for session {self.session_id}"
