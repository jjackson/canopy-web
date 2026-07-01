"""Workspaces REST API — create/list/get with membership-scoped RBAC.
A workspace is visible only to its members; a non-member gets 404 (no existence
leak), mirroring the tokenless-visibility discipline elsewhere."""
from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.workspaces.models import WorkspaceMembership

pytestmark = pytest.mark.django_db
User = get_user_model()


def _user(email):
    return User.objects.create(username=email, email=email)


def _client(user):
    c = Client()
    c.force_login(user)
    return c


def _post(c, url, data):
    return c.post(url, data=json.dumps(data), content_type="application/json")


def test_list_requires_auth():
    assert Client().get("/api/workspaces/").status_code in (401, 403)


def test_create_makes_creator_an_owner():
    u = _user("a@dimagi.com")
    r = _post(_client(u), "/api/workspaces/", {
        "slug": "acme", "display_name": "Acme", "auto_join_domains": ["acme.com"],
    })
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["slug"] == "acme"
    assert body["role"] == "owner"
    assert body["auto_join_domains"] == ["acme.com"]
    assert WorkspaceMembership.objects.get(workspace_id="acme", user=u).role == "owner"


def test_list_is_member_scoped():
    a, b = _user("a@dimagi.com"), _user("b@dimagi.com")
    _post(_client(a), "/api/workspaces/", {"slug": "acme", "display_name": "Acme"})
    _post(_client(b), "/api/workspaces/", {"slug": "beta", "display_name": "Beta"})
    a_slugs = {w["slug"] for w in _client(a).get("/api/workspaces/").json()}
    assert a_slugs == {"acme"}


def test_get_is_member_only_else_404():
    a, b = _user("a@dimagi.com"), _user("b@dimagi.com")
    _post(_client(a), "/api/workspaces/", {"slug": "acme", "display_name": "Acme"})
    assert _client(a).get("/api/workspaces/acme/").json()["role"] == "owner"
    # a non-member can't even tell it exists
    assert _client(b).get("/api/workspaces/acme/").status_code == 404


def test_duplicate_slug_conflicts():
    a = _user("a@dimagi.com")
    _post(_client(a), "/api/workspaces/", {"slug": "acme", "display_name": "Acme"})
    dup = _post(_client(a), "/api/workspaces/", {"slug": "acme", "display_name": "Dup"})
    assert dup.status_code == 409
