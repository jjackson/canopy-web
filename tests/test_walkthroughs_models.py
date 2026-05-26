"""Tests for the Walkthrough model."""
import pytest
from django.contrib.auth import get_user_model

from apps.walkthroughs.models import Walkthrough


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user(
        username="ace@dimagi.com",
        email="ace@dimagi.com",
    )


def test_create_minimal_html_walkthrough(db, owner):
    w = Walkthrough.objects.create(
        title="Skill Builder Demo",
        kind="html",
        owner=owner,
        drive_file_id="drive-file-1",
        drive_folder_id="drive-folder-1",
        content_type="text/html",
        size_bytes=1024,
    )
    assert w.id is not None
    assert w.visibility == "private"
    assert w.share_token is None
    assert w.project_slug is None
    assert w.description == ""
    assert w.created_at is not None


def test_uuid_primary_key(db, owner):
    w = Walkthrough.objects.create(
        title="t",
        kind="html",
        owner=owner,
        drive_file_id="x",
        drive_folder_id="y",
        content_type="text/html",
        size_bytes=1,
    )
    # UUID hex is 32 chars
    assert len(str(w.id).replace("-", "")) == 32


def test_share_token_must_be_unique(db, owner):
    Walkthrough.objects.create(
        title="a", kind="html", owner=owner,
        drive_file_id="x1", drive_folder_id="y1",
        content_type="text/html", size_bytes=1,
        visibility="link", share_token="duplicate-token-abc",
    )
    with pytest.raises(Exception):  # IntegrityError
        Walkthrough.objects.create(
            title="b", kind="html", owner=owner,
            drive_file_id="x2", drive_folder_id="y2",
            content_type="text/html", size_bytes=1,
            visibility="link", share_token="duplicate-token-abc",
        )


def test_ensure_share_token_generates_when_link_visibility(db, owner):
    w = Walkthrough.objects.create(
        title="t", kind="video", owner=owner,
        drive_file_id="x", drive_folder_id="y",
        content_type="video/mp4", size_bytes=1,
    )
    assert w.share_token is None
    w.visibility = "link"
    w.ensure_share_token()
    assert w.share_token is not None
    assert len(w.share_token) >= 24


def test_rotate_share_token_changes_value(db, owner):
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id="x", drive_folder_id="y",
        content_type="text/html", size_bytes=1,
        visibility="link",
    )
    w.ensure_share_token()
    old = w.share_token
    w.rotate_share_token()
    assert w.share_token is not None
    assert w.share_token != old
