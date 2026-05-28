"""ReviewRequest model — one pending-or-resolved human review gate."""
import secrets
import uuid

from django.conf import settings
from django.db import models


class ReviewRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RESOLVED = "resolved"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RESOLVED, "Resolved"),
    ]

    VISIBILITY_PRIVATE = "private"
    VISIBILITY_LINK = "link"
    VISIBILITY_CHOICES = [
        (VISIBILITY_PRIVATE, "Private (dimagi only)"),
        (VISIBILITY_LINK, "Link (anyone with token)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run_id = models.CharField(max_length=255, db_index=True)
    gate = models.CharField(max_length=128)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    request_json = models.JSONField()
    response_json = models.JSONField(null=True, blank=True)
    share_token = models.CharField(max_length=64, blank=True, null=True, unique=True)
    visibility = models.CharField(
        max_length=10, choices=VISIBILITY_CHOICES, default=VISIBILITY_PRIVATE
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="review_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["run_id", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return f"ReviewRequest({self.run_id!r}, gate={self.gate!r}, status={self.status})"

    def ensure_share_token(self) -> str:
        """Mint a share token if none exists. Returns the token."""
        if not self.share_token:
            self.share_token = secrets.token_urlsafe(24)
            self.save(update_fields=["share_token"])
        return self.share_token

    def rotate_share_token(self) -> str:
        """Replace the existing share token with a fresh one."""
        self.share_token = secrets.token_urlsafe(24)
        self.save(update_fields=["share_token"])
        return self.share_token
