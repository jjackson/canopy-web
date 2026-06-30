"""Member + invite management with owner RBAC.

Owners manage members and invites; editors/viewers cannot. Invites are accepted
by token, but only by the user whose email the invite names. The last owner
can't be removed.
"""
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


def _client(u):
    c = Client()
    c.force_login(u)
    return c


def _post(c, url, data=None):
    return c.post(url, data=json.dumps(data or {}), content_type="application/json")


def _ws(owner, slug="acme"):
    _post(_client(owner), "/api/workspaces/", {"slug": slug, "display_name": slug.title()})
    return slug


def _invite(owner, slug, email, role="editor"):
    return _post(_client(owner), f"/api/workspaces/{slug}/invites/", {"email": email, "role": role}).json()


def test_list_members_is_member_only():
    a = _user("a@dimagi.com")
    _ws(a)
    members = _client(a).get("/api/workspaces/acme/members/").json()
    assert len(members) == 1
    assert members[0]["email"] == "a@dimagi.com" and members[0]["role"] == "owner"
    b = _user("b@dimagi.com")
    assert _client(b).get("/api/workspaces/acme/members/").status_code == 404


def test_owner_invites_and_invitee_accepts():
    a = _user("a@dimagi.com")
    _ws(a)
    inv = _invite(a, "acme", "b@dimagi.com", "editor")
    assert inv["role"] == "editor" and inv["email"] == "b@dimagi.com" and inv["token"]
    b = _user("b@dimagi.com")
    r = _post(_client(b), f"/api/workspaces/invites/{inv['token']}/accept")
    assert r.status_code == 200, r.content
    assert r.json()["role"] == "editor"
    assert WorkspaceMembership.objects.get(workspace_id="acme", user=b).role == "editor"


def test_accept_requires_matching_email():
    a = _user("a@dimagi.com")
    _ws(a)
    inv = _invite(a, "acme", "b@dimagi.com")
    c = _user("c@dimagi.com")
    assert _post(_client(c), f"/api/workspaces/invites/{inv['token']}/accept").status_code == 403


def test_revoked_invite_cannot_be_accepted():
    a = _user("a@dimagi.com")
    _ws(a)
    inv = _invite(a, "acme", "b@dimagi.com")
    assert _post(_client(a), f"/api/workspaces/acme/invites/{inv['id']}/revoke").status_code == 204
    b = _user("b@dimagi.com")
    assert _post(_client(b), f"/api/workspaces/invites/{inv['token']}/accept").status_code == 410


def test_non_owner_cannot_invite():
    a = _user("a@dimagi.com")
    _ws(a)
    inv = _invite(a, "acme", "b@dimagi.com", "editor")
    b = _user("b@dimagi.com")
    _post(_client(b), f"/api/workspaces/invites/{inv['token']}/accept")  # b is now an editor
    assert _post(_client(b), "/api/workspaces/acme/invites/", {"email": "d@dimagi.com"}).status_code == 403


def test_remove_member_owner_only_and_protects_last_owner():
    a = _user("a@dimagi.com")
    _ws(a)
    inv = _invite(a, "acme", "b@dimagi.com", "editor")
    b = _user("b@dimagi.com")
    _post(_client(b), f"/api/workspaces/invites/{inv['token']}/accept")
    # an editor can't remove anyone
    assert _client(b).delete(f"/api/workspaces/acme/members/{a.id}/").status_code == 403
    # the owner can remove the editor
    assert _client(a).delete(f"/api/workspaces/acme/members/{b.id}/").status_code == 204
    # the last owner can't be removed
    assert _client(a).delete(f"/api/workspaces/acme/members/{a.id}/").status_code == 400
