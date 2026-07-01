"""canopy.origin/v1 records — the provenance + *understanding* behind an architect-routed GitHub issue.

The GitHub issue stays clean and portable; this is the queryable database the operating model calls for
(`canopy issue create` filed it, an agent in the target repo reads it back via `canopy issue context`).

Session TRANSCRIPTS are NEVER stored here — `corpus["drilled"]` and `evidence[].session` hold path
POINTERS only. They resolve via `canopy harvest strip` ONLY on a machine where that session exists; you
cannot recover a transcript from the web record. Web = the understanding; local = the evidence.
"""
from __future__ import annotations

from django.db import models


class OriginIssue(models.Model):
    repo = models.CharField(max_length=200)            # "owner/repo"
    number = models.IntegerField()                     # GitHub issue number
    title = models.CharField(max_length=300)
    source = models.CharField(max_length=100, default="hal-architect")
    agent = models.CharField(max_length=100, default="hal")
    skill = models.CharField(max_length=100, default="architect")
    initiative = models.CharField(max_length=200, default="")
    ledger = models.CharField(max_length=500, blank=True, default="")
    created = models.CharField(max_length=40, default="")    # architect-stamped pass date (freshness signal)
    disposition = models.CharField(max_length=20, default="route")
    confidence = models.CharField(max_length=20, default="medium")
    mandate = models.TextField(blank=True, default="")
    done_when = models.TextField(blank=True, default="")
    intent = models.TextField(blank=True, default="")
    evidence = models.JSONField(default=list, blank=True)    # [{claim, session(POINTER)}]
    corpus = models.JSONField(default=dict, blank=True)      # {sessions_scanned, cross_user, drilled:[POINTERS]}
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["repo", "number"], name="uniq_origin_issue_repo_number"),
        ]

    def __str__(self) -> str:
        return f"{self.repo}#{self.number}"
