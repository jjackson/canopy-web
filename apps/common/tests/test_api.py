"""Contract tests for apps/common/api.py (v2 common surface)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.common.schemas import AiAuthPollOut, AiStatusOut, MeOut

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    return Client()


@pytest.fixture()
def user(db):
    return User.objects.create_user(
        username="tester",
        email="tester@dimagi.com",
        password="pass",
    )


@pytest.fixture()
def authed_client(client, user):
    client.force_login(user)
    return client


# ---------------------------------------------------------------------------
# 1. /health/ — public, no auth
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_health_public_no_auth(client):
    resp = client.get("/api/v2/health/")
    assert resp.status_code == 200
    body = json.loads(resp.content)
    assert body == {"status": "ok"}


# ---------------------------------------------------------------------------
# 2. /me/ — authed
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_me_authed(authed_client):
    resp = authed_client.get("/api/v2/me/")
    assert resp.status_code == 200
    body = json.loads(resp.content)
    parsed = MeOut.model_validate(body)
    assert parsed.email == "tester@dimagi.com"
    assert parsed.avatar_url == ""  # no social account attached


# ---------------------------------------------------------------------------
# 3. /me/ — anonymous → 401 + problem+json
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_me_anonymous_401(client):
    resp = client.get("/api/v2/me/")
    assert resp.status_code == 401
    ct = resp.get("Content-Type", "")
    assert "problem+json" in ct or "json" in ct
    body = json.loads(resp.content)
    # RFC 7807 problem+json must have status field
    assert body.get("status") == 401


# ---------------------------------------------------------------------------
# 4. /ai/status/ — 200 + AiStatusOut shape
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_ai_status(authed_client, settings):
    settings.AI_BACKEND = "api"
    settings.ANTHROPIC_API_KEY = "sk-test-key"
    resp = authed_client.get("/api/v2/ai/status/")
    assert resp.status_code == 200
    body = json.loads(resp.content)
    parsed = AiStatusOut.model_validate(body)
    assert parsed.backend == "api"
    assert parsed.authenticated is True


# ---------------------------------------------------------------------------
# 5. /ai/switch/ — bogus backend → 422 + problem+json
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_ai_switch_validates_backend(authed_client):
    resp = authed_client.post(
        "/api/v2/ai/switch/",
        data=json.dumps({"backend": "bogus"}),
        content_type="application/json",
    )
    assert resp.status_code == 422
    ct = resp.get("Content-Type", "")
    assert "problem+json" in ct or "json" in ct
    body = json.loads(resp.content)
    assert body.get("status") == 422


# ---------------------------------------------------------------------------
# 6a. /ai/auth/poll/ — idle when no active session
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_ai_auth_poll_idle(authed_client):
    # auth_flow.poll() returns {active: False, authenticated: False} when idle
    with patch("apps.common.auth_flow.poll", return_value={"active": False, "authenticated": False}):
        resp = authed_client.get("/api/v2/ai/auth/poll/")
    assert resp.status_code == 200
    body = json.loads(resp.content)
    parsed = AiAuthPollOut.model_validate(body)
    assert parsed.state == "idle"


# ---------------------------------------------------------------------------
# 6b. /ai/auth/poll/ — ok when authenticated
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_ai_auth_poll_ok(authed_client):
    with patch("apps.common.auth_flow.poll", return_value={"active": False, "authenticated": True}):
        resp = authed_client.get("/api/v2/ai/auth/poll/")
    assert resp.status_code == 200
    body = json.loads(resp.content)
    parsed = AiAuthPollOut.model_validate(body)
    assert parsed.state == "ok"


# ---------------------------------------------------------------------------
# 6c. /ai/auth/poll/ — pending when active session in progress
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_ai_auth_poll_pending(authed_client):
    with patch(
        "apps.common.auth_flow.poll",
        return_value={"active": True, "authenticated": False, "elapsed_seconds": 5},
    ):
        resp = authed_client.get("/api/v2/ai/auth/poll/")
    assert resp.status_code == 200
    body = json.loads(resp.content)
    parsed = AiAuthPollOut.model_validate(body)
    assert parsed.state == "pending"


# ---------------------------------------------------------------------------
# 6d. /ai/auth/start/ — start smoke (mocked subprocess flow)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_ai_auth_start_smoke(authed_client):
    with patch(
        "apps.common.auth_flow.start",
        return_value={
            "auth_url": "https://claude.com/cai/oauth/authorize?state=abc",
            "token": None,
            "status": "awaiting_code",
        },
    ):
        resp = authed_client.post("/api/v2/ai/auth/start/")
    assert resp.status_code == 200
    body = json.loads(resp.content)
    assert body["auth_url"].startswith("https://")
    assert body["state"] == "awaiting_code"


# ---------------------------------------------------------------------------
# 6e. /ai/auth/complete/ — complete smoke (mocked token return)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_ai_auth_complete_smoke(authed_client):
    fake_token = "sk-ant-oat01-" + "x" * 40
    with patch("apps.common.auth_flow.complete", return_value=fake_token):
        resp = authed_client.post(
            "/api/v2/ai/auth/complete/",
            data=json.dumps({"code": "some-oauth-code"}),
            content_type="application/json",
        )
    assert resp.status_code == 200
    body = json.loads(resp.content)
    assert body["ok"] is True
    assert "detail" in body


# ---------------------------------------------------------------------------
# 6f. /ai/switch/ — valid switch round-trips backend name
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_ai_switch_valid(authed_client, settings):
    settings.AI_BACKEND = "api"
    resp = authed_client.post(
        "/api/v2/ai/switch/",
        data=json.dumps({"backend": "cli"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = json.loads(resp.content)
    assert body["backend"] == "cli"
