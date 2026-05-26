"""Walkthrough model — one shareable HTML slideshow or MP4 video."""
import secrets
import uuid

from django.conf import settings
from django.db import models


class Walkthrough(models.Model):
    KIND_HTML = "html"
    KIND_VIDEO = "video"
    KIND_CHOICES = [
        (KIND_HTML, "HTML"),
        (KIND_VIDEO, "Video"),
    ]

    VISIBILITY_PRIVATE = "private"
    VISIBILITY_LINK = "link"
    VISIBILITY_CHOICES = [
        (VISIBILITY_PRIVATE, "Private (dimagi only)"),
        (VISIBILITY_LINK, "Link (anyone with token)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    project_slug = models.CharField(
        max_length=200, blank=True, null=True, db_index=True
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="walkthroughs",
    )
    visibility = models.CharField(
        max_length=10, choices=VISIBILITY_CHOICES, default=VISIBILITY_PRIVATE
    )
    share_token = models.CharField(
        max_length=64, blank=True, null=True, unique=True
    )
    drive_file_id = models.CharField(max_length=128)
    drive_folder_id = models.CharField(max_length=128)
    content_type = models.CharField(max_length=64)
    size_bytes = models.BigIntegerField()
    duration_sec = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project_slug", "-created_at"]),
            models.Index(fields=["owner", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.kind})"

    def ensure_share_token(self) -> str:
        """Mint a share token if none exists. Returns the token."""
        if not self.share_token:
            self.share_token = secrets.token_urlsafe(24)
            self.save(update_fields=["share_token", "updated_at"])
        return self.share_token

    def rotate_share_token(self) -> str:
        """Replace the existing share token with a fresh one."""
        self.share_token = secrets.token_urlsafe(24)
        self.save(update_fields=["share_token", "updated_at"])
        return self.share_token
