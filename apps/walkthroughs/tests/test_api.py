"""Contract tests for the v2 walkthroughs Ninja surface (/api/v2/walkthroughs/).

Covers all 6 endpoints:
  POST   /  (multipart upload)
  GET    /  (list + filters)
  GET    /{wid}/
  PATCH  /{wid}/
  DELETE /{wid}/
  POST   /{wid}/rotate-token/

All Drive calls are intercepted by the fake_drive fixture.
"""
from __future__ import annotations

import json
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

from apps.walkthroughs import storage
from apps.walkthroughs.models import Walkthrough
from apps.walkthroughs.schemas import WalkthroughDetailOut, WalkthroughListItemOut
from tests.fixtures.fake_drive import FakeDriveClient

User = get_user_model()

BASE = "/api/v2/walkthroughs"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_drive(monkeypatch):
    inst = FakeDriveClient()
    monkeypatch.setattr(storage, "get_drive_client", lambda: inst)
    return inst


@pytest.fixture
def owner(db):
    return User.objects.create_user(
        username="owner@dimagi.com",
        email="owner@dimagi.com",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        username="other@dimagi.com",
        email="other@dimagi.com",
    )


@pytest.fixture
def auth_client(owner):
    c = Client()
    c.force_login(owner)
    return c


def _file_part(name: str, content: bytes, content_type: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type=content_type)


def _make_walkthrough(owner, **kwargs) -> Walkthrough:
    defaults = dict(
        title="test walk",
        kind="html",
        drive_file_id="fake-file",
        drive_folder_id="fake-folder",
        content_type="text/html",
        size_bytes=42,
    )
    defaults.update(kwargs)
    return Walkthrough.objects.create(owner=owner, **defaults)


# ---------------------------------------------------------------------------
# 1. test_upload_walkthrough_html
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_ROOT_FOLDER_ID="root-folder",
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
)
def test_upload_walkthrough_html(auth_client, fake_drive, owner):
    html = b"<html><body>hello</body></html>"
    resp = auth_client.post(
        f"{BASE}/",
        data={
            "file": _file_part("slideshow.html", html, "text/html"),
            "title": "HTML Demo",
            "kind": "html",
            "visibility": "link",
        },
        format="multipart",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    out = WalkthroughDetailOut.model_validate(body)
    assert out.title == "HTML Demo"
    assert out.kind == "html"
    assert out.is_owner is True
    assert out.visibility == "link"
    # share_token minted when visibility=link
    assert out.share_token is not None


# ---------------------------------------------------------------------------
# 2. test_upload_requires_file
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(WALKTHROUGHS_ENABLED=True)
def test_upload_requires_file(auth_client):
    resp = auth_client.post(
        f"{BASE}/",
        data={"title": "x", "kind": "html"},
        format="multipart",
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 3. test_upload_rejects_invalid_kind
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(WALKTHROUGHS_ENABLED=True)
def test_upload_rejects_invalid_kind(auth_client):
    resp = auth_client.post(
        f"{BASE}/",
        data={
            "file": _file_part("a.pdf", b"data", "application/pdf"),
            "title": "x",
            "kind": "pdf",
        },
        format="multipart",
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 4. test_upload_oversize_returns_413
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_ROOT_FOLDER_ID="root-folder",
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
    WALKTHROUGH_MAX_UPLOAD_BYTES=10,
)
def test_upload_oversize_returns_413(auth_client, fake_drive):
    resp = auth_client.post(
        f"{BASE}/",
        data={
            "file": _file_part("big.html", b"x" * 20, "text/html"),
            "title": "big",
            "kind": "html",
        },
        format="multipart",
    )
    assert resp.status_code == 413
    body = resp.json()
    assert body.get("type", "").endswith("/payload-too-large")


# ---------------------------------------------------------------------------
# 5. test_upload_drive_not_configured_returns_500
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_ROOT_FOLDER_ID="root-folder",
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
)
def test_upload_drive_not_configured_returns_500(auth_client, monkeypatch):
    from apps.walkthroughs.drive_client import DriveNotConfigured

    def _raise(*args, **kwargs):
        raise DriveNotConfigured("no drive key")

    monkeypatch.setattr(storage, "store_upload", _raise)

    resp = auth_client.post(
        f"{BASE}/",
        data={
            "file": _file_part("s.html", b"<html/>", "text/html"),
            "title": "x",
            "kind": "html",
        },
        format="multipart",
    )
    assert resp.status_code == 500
    body = resp.json()
    assert body.get("type", "").endswith("/drive-not-configured")
    # no orphan row
    assert Walkthrough.objects.count() == 0


# ---------------------------------------------------------------------------
# 6. test_list_walkthroughs
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(WALKTHROUGHS_ENABLED=True)
def test_list_walkthroughs(auth_client, owner):
    _make_walkthrough(owner, title="alpha")
    _make_walkthrough(owner, title="beta", kind="video", content_type="video/mp4")
    resp = auth_client.get(f"{BASE}/")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    # Validate round-trip through schema
    for item in items:
        WalkthroughListItemOut.model_validate(item)


# ---------------------------------------------------------------------------
# 7. test_list_filter_by_project_kind_mine
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(WALKTHROUGHS_ENABLED=True)
def test_list_filter_by_project(auth_client, owner, other_user):
    _make_walkthrough(owner, title="canopy-html", project_slug="canopy-web")
    _make_walkthrough(owner, title="ace-html", project_slug="ace-web")
    resp = auth_client.get(f"{BASE}/?project=canopy-web")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["title"] == "canopy-html"


@pytest.mark.django_db
@override_settings(WALKTHROUGHS_ENABLED=True)
def test_list_filter_by_kind(auth_client, owner):
    _make_walkthrough(owner, title="html-walk", kind="html")
    _make_walkthrough(owner, title="vid-walk", kind="video", content_type="video/mp4")
    resp = auth_client.get(f"{BASE}/?kind=video")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["kind"] == "video"


@pytest.mark.django_db
@override_settings(WALKTHROUGHS_ENABLED=True)
def test_list_filter_mine(auth_client, owner, other_user):
    _make_walkthrough(owner, title="mine")
    _make_walkthrough(other_user, title="theirs")
    resp = auth_client.get(f"{BASE}/?mine=true")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["title"] == "mine"


# ---------------------------------------------------------------------------
# 8. test_get_detail_owner_sees_token
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(WALKTHROUGHS_ENABLED=True)
def test_get_detail_owner_sees_token(auth_client, owner):
    w = _make_walkthrough(owner, visibility="link")
    w.ensure_share_token()
    resp = auth_client.get(f"{BASE}/{w.id}/")
    assert resp.status_code == 200
    body = resp.json()
    out = WalkthroughDetailOut.model_validate(body)
    assert out.is_owner is True
    assert out.share_token == w.share_token


# ---------------------------------------------------------------------------
# 9. test_get_detail_non_owner_no_token
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(WALKTHROUGHS_ENABLED=True)
def test_get_detail_non_owner_no_token(owner, other_user):
    w = _make_walkthrough(owner, visibility="link")
    w.ensure_share_token()
    c = Client()
    c.force_login(other_user)
    resp = c.get(f"{BASE}/{w.id}/")
    assert resp.status_code == 200
    body = resp.json()
    out = WalkthroughDetailOut.model_validate(body)
    assert out.is_owner is False
    assert out.share_token is None


# ---------------------------------------------------------------------------
# 10. test_get_404
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(WALKTHROUGHS_ENABLED=True)
def test_get_404(auth_client):
    bogus = uuid.uuid4()
    resp = auth_client.get(f"{BASE}/{bogus}/")
    assert resp.status_code == 404
    body = resp.json()
    assert body.get("type", "").endswith("/not-found")


# ---------------------------------------------------------------------------
# 11. test_patch_owner_only (non-owner → 403)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(WALKTHROUGHS_ENABLED=True)
def test_patch_owner_only(owner, other_user):
    w = _make_walkthrough(owner)
    c = Client()
    c.force_login(other_user)
    resp = c.patch(
        f"{BASE}/{w.id}/",
        data=json.dumps({"title": "hacked"}),
        content_type="application/json",
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body.get("type", "").endswith("/forbidden")


# ---------------------------------------------------------------------------
# 12. test_patch_to_link_mints_token
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(WALKTHROUGHS_ENABLED=True)
def test_patch_to_link_mints_token(auth_client, owner):
    w = _make_walkthrough(owner, visibility="private")
    assert w.share_token is None
    resp = auth_client.patch(
        f"{BASE}/{w.id}/",
        data=json.dumps({"visibility": "link"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    out = WalkthroughDetailOut.model_validate(body)
    assert out.visibility == "link"
    assert out.share_token is not None


# ---------------------------------------------------------------------------
# 13. test_delete_owner_returns_204
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
    CANOPY_DRIVE_ROOT_FOLDER_ID="root-folder",
)
def test_delete_owner_returns_204(auth_client, fake_drive, owner):
    # Store a real fake file so delete_stored can find it
    stored = storage.store_upload(
        walkthrough_id=str(uuid.uuid4()),
        filename="slideshow.html",
        content_type="text/html",
        data=b"<html/>",
    )
    w = Walkthrough.objects.create(
        title="t",
        kind="html",
        owner=owner,
        drive_file_id=stored.file_id,
        drive_folder_id=stored.folder_id,
        content_type="text/html",
        size_bytes=7,
    )
    resp = auth_client.delete(f"{BASE}/{w.id}/")
    assert resp.status_code == 204
    assert not Walkthrough.objects.filter(id=w.id).exists()


# ---------------------------------------------------------------------------
# 14. test_delete_non_owner_403
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(WALKTHROUGHS_ENABLED=True)
def test_delete_non_owner_403(owner, other_user):
    w = _make_walkthrough(owner)
    c = Client()
    c.force_login(other_user)
    resp = c.delete(f"{BASE}/{w.id}/")
    assert resp.status_code == 403
    body = resp.json()
    assert body.get("type", "").endswith("/forbidden")
    # Row should still exist
    assert Walkthrough.objects.filter(id=w.id).exists()


# ---------------------------------------------------------------------------
# 15. test_rotate_token_owner_only
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(WALKTHROUGHS_ENABLED=True)
def test_rotate_token_owner_only(auth_client, owner):
    w = _make_walkthrough(owner, visibility="link")
    w.ensure_share_token()
    old_token = w.share_token

    resp = auth_client.post(f"{BASE}/{w.id}/rotate-token/")
    assert resp.status_code == 200
    body = resp.json()
    new_token = body["share_token"]
    assert new_token
    assert new_token != old_token


# ---------------------------------------------------------------------------
# 16. test_endpoints_404_when_disabled
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(WALKTHROUGHS_ENABLED=False)
def test_endpoints_404_when_disabled(auth_client, owner):
    bogus = uuid.uuid4()
    w = _make_walkthrough(owner)

    # POST /
    resp = auth_client.post(
        f"{BASE}/",
        data={"file": _file_part("s.html", b"x", "text/html"), "kind": "html"},
        format="multipart",
    )
    assert resp.status_code == 404

    # GET /
    resp = auth_client.get(f"{BASE}/")
    assert resp.status_code == 404

    # GET /{wid}/
    resp = auth_client.get(f"{BASE}/{w.id}/")
    assert resp.status_code == 404

    # PATCH /{wid}/
    resp = auth_client.patch(
        f"{BASE}/{w.id}/",
        data=json.dumps({"title": "x"}),
        content_type="application/json",
    )
    assert resp.status_code == 404

    # DELETE /{wid}/
    resp = auth_client.delete(f"{BASE}/{w.id}/")
    assert resp.status_code == 404

    # POST /{wid}/rotate-token/
    resp = auth_client.post(f"{BASE}/{w.id}/rotate-token/")
    assert resp.status_code == 404
