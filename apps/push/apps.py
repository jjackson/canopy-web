from django.apps import AppConfig


class PushConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.push"

    def ready(self) -> None:
        from . import signals  # noqa: F401  — registers the post_save receivers
