"""Tests for the backfill_run_ids management command."""
from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from .factories import make_review, make_user, make_walkthrough

pytestmark = pytest.mark.django_db


def test_backfill_from_review_video_link():
    u = make_user()
    w = make_walkthrough(u, kind="video", title="some hero video")  # no run_id
    assert w.run_id is None
    make_review(
        u,
        run_id="microplans-2026-06-02-001",
        request_json={
            "run_id": "microplans-2026-06-02-001",
            "gate": "x",
            "video": {"walkthrough_id": str(w.id)},
        },
    )
    call_command("backfill_run_ids", stdout=StringIO())
    w.refresh_from_db()
    assert w.run_id == "microplans-2026-06-02-001"
    assert w.feature == "microplans"


def test_backfill_infers_run_from_title():
    u = make_user()
    w = make_walkthrough(u, kind="video", title="microplans-10-wards iter1 video (2026-06-01-002)")
    call_command("backfill_run_ids", stdout=StringIO())
    w.refresh_from_db()
    assert w.feature == "microplans-10-wards"
    assert w.run_id == "microplans-10-wards-2026-06-01-002"


def test_backfill_dry_run_writes_nothing():
    u = make_user()
    w = make_walkthrough(u, kind="video", title="Program Admin Report — HTML deck (v4)")
    call_command("backfill_run_ids", "--dry-run", stdout=StringIO())
    w.refresh_from_db()
    assert w.run_id is None


def test_backfill_skips_existing_run_id():
    u = make_user()
    w = make_walkthrough(
        u, kind="video", title="microplans-10-wards iter1", run_id="already-2026-01-01-001", feature="already"
    )
    call_command("backfill_run_ids", stdout=StringIO())
    w.refresh_from_db()
    assert w.run_id == "already-2026-01-01-001"


def test_backfill_leaves_unclassifiable_untouched():
    u = make_user()
    w = make_walkthrough(u, kind="video", title="totally unrelated artifact")
    call_command("backfill_run_ids", stdout=StringIO())
    w.refresh_from_db()
    assert w.run_id is None
    assert w.feature is None
