import uuid

import pytest

from apps.walkthroughs.schemas import (
    WalkthroughDetailOut,
    WalkthroughListItemOut,
    WalkthroughPatchIn,
    WalkthroughUploadIn,
)


def test_walkthrough_list_item_round_trip():
    raw = {
        "id": str(uuid.uuid4()),
        "title": "ACE demo",
        "description": "Walkthrough of the opp workbench",
        "kind": "html",
        "project_slug": "ace-web",
        "visibility": "private",
        "owner_email": "alice@dimagi.com",
        "size_bytes": 12345,
        "duration_sec": None,
        "created_at": "2026-05-26T10:00:00Z",
        "updated_at": "2026-05-26T10:00:00Z",
    }
    parsed = WalkthroughListItemOut.model_validate(raw)
    assert parsed.kind == "html"
    assert parsed.project_slug == "ace-web"


def test_walkthrough_detail_out_owner_shape():
    raw = {
        "id": str(uuid.uuid4()),
        "title": "Demo",
        "description": "",
        "kind": "video",
        "project_slug": None,
        "visibility": "link",
        "owner_email": "alice@dimagi.com",
        "size_bytes": 9999,
        "duration_sec": 42,
        "content_type": "video/mp4",
        "is_owner": True,
        "created_at": "2026-05-26T10:00:00Z",
        "updated_at": "2026-05-26T10:00:00Z",
    }
    parsed = WalkthroughDetailOut.model_validate(raw)
    assert parsed.is_owner is True


def test_walkthrough_detail_out_non_owner_shape():
    parsed = WalkthroughDetailOut.model_validate(
        {
            "id": str(uuid.uuid4()),
            "title": "Demo",
            "description": "",
            "kind": "html",
            "project_slug": None,
            "visibility": "private",
            "owner_email": "bob@dimagi.com",
            "size_bytes": 1,
            "duration_sec": None,
            "content_type": "text/html",
            "is_owner": False,
            "created_at": "2026-05-26T10:00:00Z",
            "updated_at": "2026-05-26T10:00:00Z",
        }
    )
    assert parsed.is_owner is False


def test_walkthrough_kind_literal():
    with pytest.raises(ValueError):
        WalkthroughListItemOut.model_validate(
            {
                "id": str(uuid.uuid4()),
                "title": "x",
                "description": "",
                "kind": "bogus",
                "project_slug": None,
                "visibility": "private",
                "owner_email": "a@b.com",
                "size_bytes": 0,
                "duration_sec": None,
                "created_at": "2026-05-26T10:00:00Z",
                "updated_at": "2026-05-26T10:00:00Z",
            }
        )


def test_walkthrough_upload_in_kind_validation():
    obj = WalkthroughUploadIn(kind="html")
    assert obj.kind == "html"
    with pytest.raises(ValueError):
        WalkthroughUploadIn(kind="invalid")


def test_walkthrough_patch_partial():
    obj = WalkthroughPatchIn(visibility="link")
    dumped = obj.model_dump(exclude_unset=True)
    assert dumped == {"visibility": "link"}


