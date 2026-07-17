from django.apps import AppConfig


class RealtimeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.realtime"
    label = "realtime"

    def ready(self) -> None:
        # Connect fan-out receivers (import for side effect). In ready() so wiring
        # happens once, after the app registry is populated.
        from . import signals  # noqa: F401
