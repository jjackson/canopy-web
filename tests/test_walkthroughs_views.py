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
