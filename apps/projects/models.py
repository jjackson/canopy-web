from django.db import models


class Project(models.Model):
    VISIBILITY_CHOICES = [
        ("public", "Public"),
        ("private", "Private"),
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("stale", "Stale"),
        ("archived", "Archived"),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    repo_url = models.URLField(blank=True, default="")
    deploy_url = models.URLField(blank=True, default="")
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default="public")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="active")
    skills = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class ProjectContext(models.Model):
    CONTEXT_TYPES = [
        ("current_work", "Current Work"),
        ("next_step", "Next Step"),
        ("summary", "Summary"),
        ("note", "Note"),
        ("insight", "Insight"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="contexts")
    context_type = models.CharField(max_length=20, choices=CONTEXT_TYPES)
    content = models.TextField()
    source = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.project.slug}:{self.context_type}"


class ProjectGuide(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="guide")
    content = models.TextField()
    source = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.project.slug}:guide"
