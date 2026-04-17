"""Tests for the debug-session mint endpoint."""
import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings


@pytest.fixture
def auth_client(db):
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username="tester",
        email="tester@dimagi.com",
        password="irrelevant",
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def anon_client(db):
    return Client()


@override_settings(REQUIRE_AUTH=True)
def test_mint_requires_auth(anon_client):
    resp = anon_client.post("/api/debug/mint-session/")
    assert resp.status_code == 401


def test_mint_returns_cookie_shape(auth_client):
    resp = auth_client.post("/api/debug/mint-session/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["cookie_name"] == "sessionid"
    assert data["cookie_value"]
    assert len(data["cookie_value"]) >= 16
    assert data["email"] == "tester@dimagi.com"
    assert data["ttl_seconds"] == 24 * 3600
    assert "curl" in data["curl_example"]
    assert data["cookie_value"] in data["curl_example"]


def test_mint_custom_ttl(auth_client):
    resp = auth_client.post(
        "/api/debug/mint-session/",
        data=json.dumps({"ttl_seconds": 3600}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["ttl_seconds"] == 3600


def test_mint_ttl_clamped_upper(auth_client):
    resp = auth_client.post(
        "/api/debug/mint-session/",
        data=json.dumps({"ttl_seconds": 10_000_000}),
        content_type="application/json",
    )
    # Max is 1 week
    assert resp.json()["data"]["ttl_seconds"] == 7 * 24 * 3600


def test_mint_ttl_clamped_lower(auth_client):
    resp = auth_client.post(
        "/api/debug/mint-session/",
        data=json.dumps({"ttl_seconds": 1}),
        content_type="application/json",
    )
    # Min is 60 seconds
    assert resp.json()["data"]["ttl_seconds"] == 60


@override_settings(REQUIRE_AUTH=True)
def test_minted_cookie_authorizes_api(auth_client, db):
    """End-to-end: mint a cookie, then use it on a fresh client to hit a
    normally-gated endpoint. This is the whole point of the endpoint —
    if this doesn't work, the feature is broken."""
    mint = auth_client.post("/api/debug/mint-session/").json()["data"]

    fresh = Client()
    fresh.cookies["sessionid"] = mint["cookie_value"]
    resp = fresh.get("/api/projects/")
    assert resp.status_code == 200


def test_mint_session_is_marked_for_audit(auth_client):
    """Minted sessions carry a marker so they can be audited or bulk-revoked later."""
    from django.contrib.sessions.models import Session

    mint = auth_client.post("/api/debug/mint-session/").json()["data"]
    session = Session.objects.get(session_key=mint["cookie_value"])
    data = session.get_decoded()
    assert "_canopy_debug_session" in data
    assert data["_canopy_debug_session"]["minted_for_email"] == "tester@dimagi.com"
