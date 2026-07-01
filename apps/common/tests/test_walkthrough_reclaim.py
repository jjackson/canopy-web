"""Reclaiming /w/ for workspaces: the public walkthrough viewer moves to
/walkthrough/, and /w/ (now the authed tenant shell) is no longer allowlisted."""
from __future__ import annotations

from apps.common.middleware import _is_walkthrough_link


class _Req:
    def __init__(self, path, method="GET"):
        self.path = path
        self.method = method


def test_walkthrough_viewer_path_is_public():
    assert _is_walkthrough_link(_Req("/walkthrough/abc-123")) is True
    assert _is_walkthrough_link(_Req("/walkthrough/abc-123/content")) is True


def test_bare_w_prefix_is_no_longer_public():
    # /w/ now means workspace — the tenant shell, which REQUIRES auth.
    assert _is_walkthrough_link(_Req("/w/dimagi/agents")) is False


def test_legacy_w_uuid_content_is_public():
    # Old rendered artifacts (DDD decks, review embeds) have
    # /w/<uuid>/content baked in; the anon holder must reach the
    # back-compat redirect. Only the UUID-shaped content path — a
    # workspace slug doesn't match.
    uuid = "2f9a1c34-5b6d-4e7f-8a9b-0c1d2e3f4a5b"
    assert _is_walkthrough_link(_Req(f"/w/{uuid}/content")) is True
    assert _is_walkthrough_link(_Req(f"/w/{uuid}")) is False
    assert _is_walkthrough_link(_Req("/w/dimagi/content")) is False


def test_walkthrough_detail_get_still_public():
    assert _is_walkthrough_link(_Req("/api/walkthroughs/abc/")) is True
    # the collection stays auth'd (list/upload)
    assert _is_walkthrough_link(_Req("/api/walkthroughs/")) is False
