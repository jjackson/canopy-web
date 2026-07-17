"""SP1 Task 1 — the realtime app is installed and a channel layer is configured."""
from __future__ import annotations

from django.apps import apps


def test_realtime_app_is_installed():
    assert apps.is_installed("apps.realtime")


def test_channel_layers_configured(settings):
    assert "default" in settings.CHANNEL_LAYERS


def test_channel_layer_is_in_memory_under_tests(settings):
    # No REDIS_URL in the test env, so the in-memory layer is selected.
    assert settings.CHANNEL_LAYERS["default"]["BACKEND"].endswith("InMemoryChannelLayer")
