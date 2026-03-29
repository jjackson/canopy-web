from django.db import models


class Skill(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")
    definition = models.JSONField(default=dict)
    version = models.IntegerField(default=1)
    workspace_session = models.ForeignKey(
        "workspace.WorkspaceSession", on_delete=models.SET_NULL, null=True, blank=True
    )
    usage_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} v{self.version}"
