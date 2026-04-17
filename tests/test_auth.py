"""Tests for the Google OAuth auth gate."""
from unittest.mock import Mock

import pytest
from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse

from apps.common.auth_adapter import CustomSocialAccountAdapter


@pytest.fixture
def auth_client(db):
    """A test Client logged in as a dimagi.com user."""
    User = get_user_model()
    user = User.objects.create_user(
        username="tester",
        email="tester@dimagi.com",
        password="irrelevant",
    )
    client = Client()
    client.force_login(user)
    return client


# ──────────────────────────────────────────────────────────────────────
# LoginRequiredMiddleware
# ──────────────────────────────────────────────────────────────────────


@override_settings(REQUIRE_AUTH=True)
def test_api_requires_auth_returns_401(db):
    client = Client()
    resp = client.get("/api/projects/")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Authentication required"}


@override_settings(REQUIRE_AUTH=True)
def test_page_requires_auth_redirects_to_login(db):
    client = Client()
    resp = client.get("/some-spa-route")
    assert resp.status_code == 302
    assert resp["Location"].startswith("/accounts/google/login/")
    assert "next=/some-spa-route" in resp["Location"]


@override_settings(REQUIRE_AUTH=True)
def test_health_is_public(db):
    client = Client()
    resp = client.get("/health/")
    assert resp.status_code == 200


@override_settings(REQUIRE_AUTH=True)
def test_csrf_endpoint_is_public(db):
    client = Client()
    resp = client.get("/api/csrf/")
    assert resp.status_code == 200
    assert "csrftoken" in resp.cookies


@override_settings(REQUIRE_AUTH=True)
def test_accounts_paths_are_public(db):
    client = Client()
    resp = client.get("/accounts/login/")
    assert resp.status_code in (200, 302)  # allauth may redirect, but not to our login


@override_settings(REQUIRE_AUTH=True)
def test_me_returns_401_when_unauthenticated(db):
    client = Client()
    resp = client.get("/api/me/")
    assert resp.status_code == 401


@override_settings(REQUIRE_AUTH=True)
def test_me_returns_user_when_authenticated(auth_client):
    resp = auth_client.get("/api/me/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "tester@dimagi.com"


@override_settings(REQUIRE_AUTH=True)
def test_authenticated_user_can_hit_api(auth_client):
    resp = auth_client.get("/api/projects/")
    assert resp.status_code == 200


@override_settings(REQUIRE_AUTH=False)
def test_auth_can_be_disabled(db):
    client = Client()
    resp = client.get("/api/projects/")
    assert resp.status_code == 200


# ──────────────────────────────────────────────────────────────────────
# CustomSocialAccountAdapter
# ──────────────────────────────────────────────────────────────────────


def _make_social_login(email: str) -> Mock:
    sociallogin = Mock()
    sociallogin.account = Mock()
    sociallogin.account.extra_data = {"email": email}
    return sociallogin


@override_settings(AUTH_ALLOWED_EMAIL_DOMAIN="dimagi.com")
def test_adapter_accepts_dimagi_email(rf):
    adapter = CustomSocialAccountAdapter()
    request = rf.get("/accounts/google/login/callback/")
    sociallogin = _make_social_login("alice@dimagi.com")
    # Should not raise
    adapter.pre_social_login(request, sociallogin)


@override_settings(AUTH_ALLOWED_EMAIL_DOMAIN="dimagi.com")
def test_adapter_rejects_other_email(rf):
    adapter = CustomSocialAccountAdapter()
    request = rf.get("/accounts/google/login/callback/")
    sociallogin = _make_social_login("mallory@gmail.com")
    with pytest.raises(ImmediateHttpResponse) as exc:
        adapter.pre_social_login(request, sociallogin)
    assert exc.value.response.status_code == 403


@override_settings(AUTH_ALLOWED_EMAIL_DOMAIN="dimagi.com")
def test_adapter_rejects_substring_match(rf):
    """Someone@evildimagi.com must not be treated as dimagi.com."""
    adapter = CustomSocialAccountAdapter()
    request = rf.get("/accounts/google/login/callback/")
    sociallogin = _make_social_login("attacker@evildimagi.com")
    with pytest.raises(ImmediateHttpResponse) as exc:
        adapter.pre_social_login(request, sociallogin)
    assert exc.value.response.status_code == 403


@override_settings(AUTH_ALLOWED_EMAIL_DOMAIN="dimagi.com")
def test_adapter_rejects_missing_email(rf):
    adapter = CustomSocialAccountAdapter()
    request = rf.get("/accounts/google/login/callback/")
    sociallogin = _make_social_login("")
    with pytest.raises(ImmediateHttpResponse):
        adapter.pre_social_login(request, sociallogin)


@override_settings(AUTH_ALLOWED_EMAIL_DOMAIN="")
def test_adapter_allows_any_when_domain_unset(rf):
    adapter = CustomSocialAccountAdapter()
    request = rf.get("/accounts/google/login/callback/")
    sociallogin = _make_social_login("anyone@example.com")
    # Should not raise
    adapter.pre_social_login(request, sociallogin)


@override_settings(AUTH_ALLOWED_EMAIL_DOMAIN="dimagi.com")
def test_adapter_case_insensitive(rf):
    adapter = CustomSocialAccountAdapter()
    request = rf.get("/accounts/google/login/callback/")
    sociallogin = _make_social_login("Alice@DIMAGI.COM")
    # Should not raise
    adapter.pre_social_login(request, sociallogin)


@override_settings(AUTH_ALLOWED_EMAIL_DOMAIN="dimagi.com")
def test_rejection_page_shows_email_domain_and_contact(rf):
    """The rejection response must tell the user their email, the allowed
    domain, and a way to request access — otherwise it's a dead end."""
    adapter = CustomSocialAccountAdapter()
    request = rf.get("/accounts/google/login/callback/")
    sociallogin = _make_social_login("mallory@gmail.com")
    with pytest.raises(ImmediateHttpResponse) as exc:
        adapter.pre_social_login(request, sociallogin)
    body = exc.value.response.content.decode()
    assert "mallory@gmail.com" in body
    assert "dimagi.com" in body
    assert "mailto:jjackson@dimagi.com" in body
    assert "accounts.google.com/Logout" in body


# ──────────────────────────────────────────────────────────────────────
# CSRF enforcement on state-mutating endpoints
# ──────────────────────────────────────────────────────────────────────


@override_settings(REQUIRE_AUTH=True)
def test_post_without_csrf_rejected(db):
    """When enforce_csrf_checks=True, state-mutating POSTs without a token fail."""
    User = get_user_model()
    user = User.objects.create_user(username="tester", email="tester@dimagi.com")
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    resp = client.post("/api/projects/", data={}, content_type="application/json")
    assert resp.status_code == 403
