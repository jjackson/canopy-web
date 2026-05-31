"""MCP audit log.

One row per MCP tool invocation: who called it, which tool, a short
summary of the args, when, and whether it succeeded. Written by the
tool wrapper in `apps.mcp.audit` on every call (best-effort — an audit
write failure must never mask the tool result).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class MCPAuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mcp_audit_logs",
    )
    tool = models.CharField(max_length=200, db_index=True)
    args_summary = models.CharField(max_length=500, blank=True, default="")
    ok = models.BooleanField(default=True)
    error = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "mcp_audit_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["tool", "-created_at"]),
        ]

    def __str__(self):
        status = "ok" if self.ok else "ERR"
        return f"[{status}] {self.tool} by {self.user_id} @ {self.created_at:%Y-%m-%d %H:%M}"
