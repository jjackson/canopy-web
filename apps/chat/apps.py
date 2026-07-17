from django.apps import AppConfig


class ChatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.chat"
    label = "chat"

    def ready(self) -> None:
        from . import signals  # noqa: F401  (Message projection receiver)
