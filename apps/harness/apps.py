from django.apps import AppConfig


class HarnessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.harness"
    verbose_name = "Agent execution harness"
