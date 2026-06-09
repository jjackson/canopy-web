"""Tokenless visibility behaviour for the walkthrough content stream + detail."""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from apps.walkthroughs.models import Walkthrough


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user(
        username="owner@dimagi.com", email="owner@dimagi.com",
    )


def _make(owner, **kw):
    defaults = dict(
        title="Demo", kind="video", owner=owner,
        drive_file_id="file-1", drive_folder_id="folder-1",
        content_type="video/mp4", size_bytes=10,
    )
    defaults.update(kw)
    return Walkthrough.objects.create(**defaults)


# Streaming returns bytes; stub the Drive download so tests stay offline.
# storage.download returns (data, start, end_inclusive, total).
def _stub_download():
    return patch(
        "apps.walkthroughs.streaming.storage.download",
        return_value=(b"data", 0, 3, 4),
    )


@override_settings(REQUIRE_AUTH=True)
def test_public_content_served_to_anonymous_without_token(owner):
    w = _make(owner, visibility="link")
    with _stub_download():
        resp = Client().get(f"/w/{w.id}/content")
    assert resp.status_code == 200


@override_settings(REQUIRE_AUTH=True)
def test_private_content_404s_anonymous(owner):
    w = _make(owner, visibility="private")
    resp = Client().get(f"/w/{w.id}/content")
    assert resp.status_code == 404


@override_settings(REQUIRE_AUTH=True)
def test_owner_sees_private_content(owner):
    w = _make(owner, visibility="private")
    client = Client()
    client.force_login(owner)
    with _stub_download():
        resp = client.get(f"/w/{w.id}/content")
    assert resp.status_code == 200


@override_settings(REQUIRE_AUTH=True)
def test_authed_non_owner_sees_private_content(owner):
    # The tokenless gate grants any authenticated Dimagi user access,
    # not just the owner.
    w = _make(owner, visibility="private")
    other = get_user_model().objects.create_user(
        username="other@dimagi.com", email="other@dimagi.com",
    )
    client = Client()
    client.force_login(other)
    with _stub_download():
        resp = client.get(f"/w/{w.id}/content")
    assert resp.status_code == 200


def test_detail_handler_404s_private_for_anonymous(owner):
    """With auth=None the handler itself must hide private rows from anonymous."""
    from django.test import RequestFactory
    from django.contrib.auth.models import AnonymousUser
    from apps.walkthroughs.api import get_walkthrough

    w = _make(owner, visibility="private")
    req = RequestFactory().get(f"/api/walkthroughs/{w.id}/")
    req.user = AnonymousUser()
    with pytest.raises(Exception):  # Http404 / ProblemError → not found
        get_walkthrough(req, w.id)
