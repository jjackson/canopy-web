"""Tests for the walkthroughs REST endpoints."""
import json

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.walkthroughs import storage
from apps.walkthroughs.models import Walkthrough
from tests.fixtures.fake_drive import FakeDriveClient


@pytest.fixture
def fake_drive(monkeypatch):
    inst = FakeDriveClient()
    monkeypatch.setattr(storage, "get_drive_client", lambda: inst)
    return inst


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user(
        username="ace@dimagi.com", email="ace@dimagi.com",
    )


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(
        username="other@dimagi.com", email="other@dimagi.com",
    )


@pytest.fixture
def auth_client(client, owner):
    client.force_login(owner)
    return client


# ---- Upload ----

@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_ROOT_FOLDER_ID="root-folder",
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',  # bypass DriveNotConfigured
)
def test_upload_html_walkthrough(auth_client, fake_drive, owner):
    html = b"<html><body>demo</body></html>"
    resp = auth_client.post(
        "/api/walkthroughs/",
        data={
            "file": _file_part("slideshow.html", html, "text/html"),
            "title": "Skill Builder Demo",
            "kind": "html",
        },
        format="multipart",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()["data"]
    assert body["title"] == "Skill Builder Demo"
    assert body["kind"] == "html"
    assert body["visibility"] == "private"
    w = Walkthrough.objects.get(id=body["id"])
    assert w.owner == owner
    assert w.drive_file_id in fake_drive.files
    assert fake_drive.files[w.drive_file_id].data == html


@override_settings(WALKTHROUGHS_ENABLED=False)
def test_upload_404_when_flag_off(auth_client):
    resp = auth_client.post("/api/walkthroughs/", data={})
    assert resp.status_code == 404


@override_settings(WALKTHROUGHS_ENABLED=True, REQUIRE_AUTH=True)
def test_upload_requires_login(client):
    resp = client.post("/api/walkthroughs/", data={})
    assert resp.status_code in (302, 401)


@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_ROOT_FOLDER_ID="root",
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
    WALKTHROUGH_MAX_UPLOAD_BYTES=10,
)
def test_upload_rejects_oversize(auth_client, fake_drive):
    resp = auth_client.post(
        "/api/walkthroughs/",
        data={
            "file": _file_part("a.html", b"x" * 20, "text/html"),
            "title": "x", "kind": "html",
        },
        format="multipart",
    )
    assert resp.status_code == 413


@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_ROOT_FOLDER_ID="root",
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
)
def test_upload_rejects_unknown_kind(auth_client, fake_drive):
    resp = auth_client.post(
        "/api/walkthroughs/",
        data={
            "file": _file_part("a.pdf", b"x", "application/pdf"),
            "title": "x", "kind": "pdf",
        },
        format="multipart",
    )
    assert resp.status_code == 400


# Helper — Django test client wants SimpleUploadedFile for multipart.
def _file_part(name, content, content_type):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, content, content_type=content_type)


# ---- List ----

@override_settings(WALKTHROUGHS_ENABLED=True)
def test_list_returns_all(auth_client, db, owner):
    Walkthrough.objects.create(
        title="a", kind="html", owner=owner,
        drive_file_id="f1", drive_folder_id="d1",
        content_type="text/html", size_bytes=1,
    )
    Walkthrough.objects.create(
        title="b", kind="video", owner=owner,
        drive_file_id="f2", drive_folder_id="d2",
        content_type="video/mp4", size_bytes=1,
    )
    resp = auth_client.get("/api/walkthroughs/")
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) == 2


@override_settings(WALKTHROUGHS_ENABLED=True)
def test_list_filters_by_project_and_kind(auth_client, db, owner):
    Walkthrough.objects.create(
        title="a", kind="html", owner=owner, project_slug="canopy-web",
        drive_file_id="f1", drive_folder_id="d1",
        content_type="text/html", size_bytes=1,
    )
    Walkthrough.objects.create(
        title="b", kind="video", owner=owner, project_slug="ace-web",
        drive_file_id="f2", drive_folder_id="d2",
        content_type="video/mp4", size_bytes=1,
    )
    resp = auth_client.get("/api/walkthroughs/?project=canopy-web")
    assert [w["title"] for w in resp.json()["data"]] == ["a"]
    resp = auth_client.get("/api/walkthroughs/?kind=video")
    assert [w["title"] for w in resp.json()["data"]] == ["b"]


# ---- Detail ----

@override_settings(WALKTHROUGHS_ENABLED=True)
def test_detail_owner_sees_token_and_is_owner_true(auth_client, db, owner):
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id="f", drive_folder_id="d",
        content_type="text/html", size_bytes=1,
        visibility="link",
    )
    w.ensure_share_token()
    resp = auth_client.get(f"/api/walkthroughs/{w.id}/")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["is_owner"] is True
    assert body["share_token"] == w.share_token


@override_settings(WALKTHROUGHS_ENABLED=True)
def test_detail_non_owner_does_not_see_token(client, db, owner, other_user):
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id="f", drive_folder_id="d",
        content_type="text/html", size_bytes=1,
        visibility="link",
    )
    w.ensure_share_token()
    client.force_login(other_user)
    resp = client.get(f"/api/walkthroughs/{w.id}/")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["is_owner"] is False
    assert body["share_token"] is None


# ---- PATCH ----

@override_settings(WALKTHROUGHS_ENABLED=True)
def test_patch_owner_can_update(auth_client, db, owner):
    w = Walkthrough.objects.create(
        title="old", kind="html", owner=owner,
        drive_file_id="f", drive_folder_id="d",
        content_type="text/html", size_bytes=1,
    )
    resp = auth_client.patch(
        f"/api/walkthroughs/{w.id}/",
        data=json.dumps({"title": "new", "visibility": "link"}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    w.refresh_from_db()
    assert w.title == "new"
    assert w.visibility == "link"
    assert w.share_token is not None  # auto-minted on link switch


@override_settings(WALKTHROUGHS_ENABLED=True)
def test_patch_non_owner_forbidden(client, db, owner, other_user):
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id="f", drive_folder_id="d",
        content_type="text/html", size_bytes=1,
    )
    client.force_login(other_user)
    resp = client.patch(
        f"/api/walkthroughs/{w.id}/",
        data=json.dumps({"title": "x"}),
        content_type="application/json",
    )
    assert resp.status_code == 403


# ---- DELETE ----

@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
    CANOPY_DRIVE_ROOT_FOLDER_ID="root",
)
def test_delete_owner_drops_row_and_drive_file(auth_client, fake_drive, owner):
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id="manual-file", drive_folder_id="manual-folder",
        content_type="text/html", size_bytes=1,
    )
    fake_drive.files["manual-file"] = fake_drive.files.get(
        "manual-file"
    ) or type(fake_drive.files[fake_drive.root_id])(
        file_id="manual-file", parent_id="manual-folder", name="x",
        content_type="text/html", data=b"x", is_folder=False,
    )
    resp = auth_client.delete(f"/api/walkthroughs/{w.id}/")
    assert resp.status_code == 204
    assert not Walkthrough.objects.filter(id=w.id).exists()
    assert "manual-file" not in fake_drive.files


# ---- Rotate token ----

@override_settings(WALKTHROUGHS_ENABLED=True)
def test_rotate_token(auth_client, db, owner):
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id="f", drive_folder_id="d",
        content_type="text/html", size_bytes=1,
        visibility="link",
    )
    w.ensure_share_token()
    old = w.share_token
    resp = auth_client.post(f"/api/walkthroughs/{w.id}/rotate-token/")
    assert resp.status_code == 200
    new_token = resp.json()["data"]["share_token"]
    assert new_token and new_token != old


# ---- Content streaming ----

@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
    CANOPY_DRIVE_ROOT_FOLDER_ID="root",
)
def test_content_private_requires_session(client, db, owner, fake_drive):
    stored = storage.store_upload(
        walkthrough_id="abc", filename="slideshow.html",
        content_type="text/html", data=b"<html>x</html>",
    )
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id=stored.file_id, drive_folder_id=stored.folder_id,
        content_type="text/html", size_bytes=12,
    )
    # Anonymous → middleware redirects or 401
    resp = client.get(f"/w/{w.id}/content")
    assert resp.status_code in (302, 401, 404)


@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
    CANOPY_DRIVE_ROOT_FOLDER_ID="root",
)
def test_content_link_visibility_serves_with_token(client, db, owner, fake_drive):
    stored = storage.store_upload(
        walkthrough_id="abc", filename="slideshow.html",
        content_type="text/html", data=b"<html>linked</html>",
    )
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id=stored.file_id, drive_folder_id=stored.folder_id,
        content_type="text/html", size_bytes=17,
        visibility="link",
    )
    w.ensure_share_token()
    resp = client.get(f"/w/{w.id}/content?t={w.share_token}")
    assert resp.status_code == 200
    assert b"".join(resp.streaming_content) == b"<html>linked</html>"
    assert resp["Content-Type"].startswith("text/html")


@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
    CANOPY_DRIVE_ROOT_FOLDER_ID="root",
)
def test_content_wrong_token_returns_404_not_403(client, db, owner, fake_drive):
    stored = storage.store_upload(
        walkthrough_id="abc", filename="slideshow.html",
        content_type="text/html", data=b"x",
    )
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id=stored.file_id, drive_folder_id=stored.folder_id,
        content_type="text/html", size_bytes=1,
        visibility="link",
    )
    w.ensure_share_token()
    resp = client.get(f"/w/{w.id}/content?t=wrongtoken")
    assert resp.status_code == 404


@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
    CANOPY_DRIVE_ROOT_FOLDER_ID="root",
)
def test_content_range_request_serves_partial(client, db, owner, fake_drive):
    stored = storage.store_upload(
        walkthrough_id="abc", filename="video.mp4",
        content_type="video/mp4", data=b"0123456789",
    )
    w = Walkthrough.objects.create(
        title="t", kind="video", owner=owner,
        drive_file_id=stored.file_id, drive_folder_id=stored.folder_id,
        content_type="video/mp4", size_bytes=10,
        visibility="link",
    )
    w.ensure_share_token()
    resp = client.get(
        f"/w/{w.id}/content?t={w.share_token}",
        HTTP_RANGE="bytes=2-5",
    )
    assert resp.status_code == 206
    assert b"".join(resp.streaming_content) == b"2345"
    assert resp["Content-Range"] == "bytes 2-5/10"
    assert resp["Accept-Ranges"] == "bytes"
