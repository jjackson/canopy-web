from django.db import models


class Collection(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Source(models.Model):
    SOURCE_TYPES = [
        ("slack", "Slack Thread"),
        ("transcript", "AI Session Transcript"),
        ("document", "Document"),
        ("text", "Raw Text"),
    ]

    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="sources")
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPES)
    title = models.CharField(max_length=255, blank=True, default="")
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_source_type_display()}: {self.title or self.pk}"
