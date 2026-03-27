from django.db import models


class WorkspaceSession(models.Model):
    STATUS_CHOICES = [
        ("created", "Created"),
        ("analyzing", "Analyzing Sources"),
        ("proposed", "Approach Proposed"),
        ("editing", "User Editing"),
        ("testing", "Running Eval"),
        ("published", "Published"),
    ]

    collection = models.ForeignKey(
        "collections.Collection", on_delete=models.CASCADE, related_name="workspace_sessions"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="created")
    proposed_approach = models.JSONField(default=dict, blank=True)
    proposed_eval_cases = models.JSONField(default=list, blank=True)
    skill_draft = models.JSONField(default=dict, blank=True)
    edit_history = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"WorkspaceSession {self.pk} ({self.status})"
