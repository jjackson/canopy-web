"""Production must never boot on the insecure dev SECRET_KEY default.

Regression guard for the DJANGO_SECRET_KEY/SECRET_KEY env-name mismatch that let
production silently sign session/CSRF/reset tokens with the public placeholder in
config/settings/base.py. config.settings.production now refuses to import unless
SECRET_KEY is supplied from the environment.

Settings modules import-and-cache once per process, so we load the settings in a
fresh interpreter per case. Accessing any setting forces Django to import the
settings module, which runs production.py's top-level guard — the real startup
failure mode — without populating the app registry.
"""
import os
import subprocess
import sys

from config.settings.base import INSECURE_DEV_SECRET_KEY

_BOOT = "from django.conf import settings; settings.DEBUG"


def _boot_production(secret_key: str | None) -> subprocess.CompletedProcess:
    # Inherit the real environment (keeps the venv/interpreter resolvable), then
    # override only what this test controls.
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "ALLOWED_HOSTS": "example.com",
    }
    if secret_key is None:
        env.pop("SECRET_KEY", None)
    else:
        env["SECRET_KEY"] = secret_key
    return subprocess.run(
        [sys.executable, "-c", _BOOT],
        env=env,
        capture_output=True,
        text=True,
    )


def test_production_refuses_the_insecure_default():
    # No SECRET_KEY in the env → base.py falls back to the insecure default →
    # production.py must raise ImproperlyConfigured and the process must die.
    result = _boot_production(None)
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert "SECRET_KEY" in result.stderr


def test_production_boots_with_a_real_secret_key():
    result = _boot_production("a-real-strong-secret-value-not-the-default")
    assert result.returncode == 0, result.stderr


def test_the_default_is_recognisably_insecure():
    # The marker prefix Django uses is load-bearing for the assertion's intent.
    assert INSECURE_DEV_SECRET_KEY.startswith("django-insecure-")
