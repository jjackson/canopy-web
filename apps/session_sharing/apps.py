from django.apps import AppConfig


class SessionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.session_sharing"
    label = "shared_sessions"
    verbose_name = "Shared Claude sessions"
