"""Tests for the token-gated e2e-login endpoint.

Mirrors the pattern in ace-web's apps/auth/e2e_login_views.py: a pre-shared
token in CANOPY_E2E_AUTH_TOKEN lets automated tools (gstack walkthroughs,
autonomous PM cycles) sign in without going through Google OAuth.
"""
import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings


@pytest.fixture
def anon_client(db):
    return Client()


@override_settings(CANOPY_E2E_AUTH_TOKEN="")
def test_endpoint_disabled_when_token_unset(anon_client):
    resp = anon_client.post(
        "/api/auth/e2e-login/",
        data=json.dumps({"email": "ace@dimagi.com", "token": "anything"}),
        content_type="application/json",
    )
    assert resp.status_code == 404


@override_settings(CANOPY_E2E_AUTH_TOKEN="s3cret")
def test_invalid_token_rejected(anon_client):
    resp = anon_client.post(
        "/api/auth/e2e-login/",
        data=json.dumps({"email": "ace@dimagi.com", "token": "wrong"}),
        content_type="application/json",
    )
    assert resp.status_code == 403


@override_settings(CANOPY_E2E_AUTH_TOKEN="s3cret")
def test_missing_email_rejected(anon_client):
    resp = anon_client.post(
        "/api/auth/e2e-login/",
        data=json.dumps({"token": "s3cret"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


@override_settings(CANOPY_E2E_AUTH_TOKEN="s3cret", AUTH_ALLOWED_EMAIL_DOMAIN="dimagi.com")
def test_disallowed_domain_rejected(anon_client):
    resp = anon_client.post(
        "/api/auth/e2e-login/",
        data=json.dumps({"email": "outsider@example.com", "token": "s3cret"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


@override_settings(CANOPY_E2E_AUTH_TOKEN="s3cret", AUTH_ALLOWED_EMAIL_DOMAIN="dimagi.com")
def test_invalid_json_rejected(anon_client):
    resp = anon_client.post(
        "/api/auth/e2e-login/",
        data="not-json",
        content_type="application/json",
    )
    assert resp.status_code == 400


@override_settings(CANOPY_E2E_AUTH_TOKEN="s3cret", AUTH_ALLOWED_EMAIL_DOMAIN="dimagi.com")
def test_valid_token_creates_and_logs_in(anon_client, db):
    user_model = get_user_model()
    assert not user_model.objects.filter(email="ace@dimagi.com").exists()

    resp = anon_client.post(
        "/api/auth/e2e-login/",
        data=json.dumps({"email": "ace@dimagi.com", "token": "s3cret"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "ace@dimagi.com"
    assert body["created"] is True
    assert isinstance(body["user_id"], int)
    assert user_model.objects.filter(email="ace@dimagi.com").count() == 1


@override_settings(CANOPY_E2E_AUTH_TOKEN="s3cret", AUTH_ALLOWED_EMAIL_DOMAIN="dimagi.com")
def test_valid_token_reuses_existing_user(anon_client, db):
    user_model = get_user_model()
    user_model.objects.create_user(username="ace@dimagi.com", email="ace@dimagi.com")

    resp = anon_client.post(
        "/api/auth/e2e-login/",
        data=json.dumps({"email": "ace@dimagi.com", "token": "s3cret"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is False
    assert user_model.objects.filter(email="ace@dimagi.com").count() == 1


@override_settings(
    CANOPY_E2E_AUTH_TOKEN="s3cret",
    AUTH_ALLOWED_EMAIL_DOMAIN="dimagi.com",
    REQUIRE_AUTH=True,
)
def test_session_cookie_authorizes_gated_api(db):
    """End-to-end: e2e-login, then use the session cookie to hit a
    normally-OAuth-gated endpoint. Same client carries the cookie set by
    the login response."""
    client = Client()
    resp = client.post(
        "/api/auth/e2e-login/",
        data=json.dumps({"email": "ace@dimagi.com", "token": "s3cret"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    # Reuse the same client (it now carries sessionid).
    gated = client.get("/api/projects/")
    assert gated.status_code == 200


@override_settings(CANOPY_E2E_AUTH_TOKEN="s3cret", AUTH_ALLOWED_EMAIL_DOMAIN="dimagi.com")
def test_session_marker_set_for_audit(db):
    from django.contrib.sessions.models import Session

    client = Client()
    resp = client.post(
        "/api/auth/e2e-login/",
        data=json.dumps({"email": "ace@dimagi.com", "token": "s3cret"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    sessionid = client.cookies["sessionid"].value
    blob = Session.objects.get(session_key=sessionid).get_decoded()
    assert "_canopy_e2e_session" in blob
    assert blob["_canopy_e2e_session"]["email"] == "ace@dimagi.com"


@override_settings(CANOPY_E2E_AUTH_TOKEN="s3cret", AUTH_ALLOWED_EMAIL_DOMAIN="dimagi.com")
def test_get_method_rejected(anon_client):
    """Only POST is allowed — GET should 405."""
    resp = anon_client.get("/api/auth/e2e-login/")
    assert resp.status_code == 405
