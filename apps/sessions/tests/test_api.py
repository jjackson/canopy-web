"""Contract tests for the /api/sessions + /api/share surfaces."""
from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

from apps.sessions.models import Session

User = get_user_model()


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="owner@dimagi.com", email="owner@dimagi.com")


@pytest.fixture
def other(db):
    return User.objects.create_user(username="other@dimagi.com", email="other@dimagi.com")


@pytest.fixture
def auth_client(owner):
    c = Client()
    c.force_login(owner)
    return c


def _transcript(session_id: str = "sess-1", *, secret: bool = False) -> bytes:
    text = "the key is sk-abcdEFGH1234567890ijklMNOP" if secret else "hello"
    rows = [
        {"type": "system", "subtype": "init", "session_id": session_id},
        {"type": "user", "message": {"content": text}},
        {
            "type": "assistant",
            "message": {"id": "m1", "content": [{"type": "text", "text": "hi"}]},
        },
    ]
    return ("\n".join(json.dumps(r) for r in rows) + "\n").encode()


def _upload(client, content: bytes, **fields):
    data = {
        "file": SimpleUploadedFile("session.jsonl", content, content_type="application/x-ndjson"),
        "visibility": "link",
        **fields,
    }
    return client.post("/api/sessions/upload", data=data, format="multipart")


@pytest.mark.django_db
def test_upload_mints_share_token_and_counts_redactions(auth_client):
    resp = _upload(auth_client, _transcript(secret=True), title="My Session")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["message_count"] == 2
    assert body["visibility"] == "link"
    assert body["share_token"]
    assert body["redaction_count"] == 1
    assert body["duplicate"] is False


@pytest.mark.django_db
@override_settings(REQUIRE_AUTH=True)
def test_public_share_view_served_to_anonymous(auth_client):
    token = _upload(auth_client, _transcript(secret=True)).json()["share_token"]
    resp = Client().get(f"/api/share/{token}")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["redaction_count"] == 1
    assert len(body["messages"]) == 2
    # Secret never reaches the public payload.
    assert "sk-abcd" not in json.dumps(body)
    # No owner identity leaked.
    assert "owner_email" not in body


@pytest.mark.django_db
@override_settings(REQUIRE_AUTH=True)
def test_revoked_token_404s(auth_client):
    slug = _upload(auth_client, _transcript()).json()["slug"]
    token = Session.objects.get(slug=slug).active_token().token
    # Make private → revokes the active token.
    auth_client.patch(
        f"/api/sessions/{slug}",
        data=json.dumps({"visibility": "private"}),
        content_type="application/json",
    )
    assert Client().get(f"/api/share/{token}").status_code == 404


@pytest.mark.django_db
def test_rotate_token_invalidates_old_link(auth_client):
    up = _upload(auth_client, _transcript()).json()
    slug, old = up["slug"], up["share_token"]
    new = auth_client.post(f"/api/sessions/{slug}/rotate-token").json()["share_token"]
    assert new != old
    assert Client().get(f"/api/share/{old}").status_code == 404
    assert Client().get(f"/api/share/{new}").status_code == 200


@pytest.mark.django_db
def test_reupload_is_idempotent(auth_client):
    first = _upload(auth_client, _transcript("dup-1")).json()
    second = _upload(auth_client, _transcript("dup-1")).json()
    assert second["duplicate"] is True
    assert second["slug"] == first["slug"]
    assert Session.objects.filter(cli_session_id="dup-1").count() == 1


@pytest.mark.django_db
def test_list_only_returns_my_sessions(auth_client, other):
    _upload(auth_client, _transcript("mine"))
    other_client = Client()
    other_client.force_login(other)
    _upload(other_client, _transcript("theirs"))

    rows = auth_client.get("/api/sessions/").json()
    assert len(rows) == 1
    assert rows[0]["is_owner"] is True


@pytest.mark.django_db
def test_non_owner_cannot_read_detail(auth_client, other):
    slug = _upload(auth_client, _transcript()).json()["slug"]
    other_client = Client()
    other_client.force_login(other)
    assert other_client.get(f"/api/sessions/{slug}").status_code == 403
