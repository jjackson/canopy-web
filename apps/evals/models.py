from django.db import models


class EvalSuite(models.Model):
    skill = models.OneToOneField("skills.Skill", on_delete=models.CASCADE, related_name="eval_suite")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"EvalSuite for {self.skill}"


class EvalCase(models.Model):
    suite = models.ForeignKey(EvalSuite, on_delete=models.CASCADE, related_name="cases")
    name = models.CharField(max_length=255)
    input_data = models.JSONField(default=dict)
    expected_output = models.JSONField(default=dict)
    source_excerpt = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class EvalRun(models.Model):
    suite = models.ForeignKey(EvalSuite, on_delete=models.CASCADE, related_name="runs")
    status = models.CharField(max_length=20, default="pending")
    results = models.JSONField(default=dict)
    overall_score = models.FloatField(null=True, blank=True)
    runtime = models.CharField(max_length=20, default="web")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"EvalRun {self.pk} ({self.status})"
