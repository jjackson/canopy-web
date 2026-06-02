"""Tests for the backfill_run_ids management command."""
from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from .factories import make_review, make_user, make_walkthrough

pytestmark = pytest.mark.django_db


def test_backfill_from_review_video_link():
    u = make_user()
    w = make_walkthrough(u, kind="video")  # no run_id yet
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


def test_backfill_dry_run_writes_nothing():
    u = make_user()
    w = make_walkthrough(u, kind="video")
    make_review(
        u,
        run_id="x-2026-06-02-001",
        request_json={"run_id": "x-2026-06-02-001", "gate": "g", "video": {"walkthrough_id": str(w.id)}},
    )
    call_command("backfill_run_ids", "--dry-run", stdout=StringIO())
    w.refresh_from_db()
    assert w.run_id is None


def test_backfill_is_idempotent_and_skips_existing():
    u = make_user()
    w = make_walkthrough(u, kind="video", run_id="already-2026-01-01-001", feature="already")
    make_review(
        u,
        run_id="new-2026-06-02-001",
        request_json={"run_id": "new-2026-06-02-001", "gate": "g", "video": {"walkthrough_id": str(w.id)}},
    )
    call_command("backfill_run_ids", stdout=StringIO())
    w.refresh_from_db()
    # Existing run_id must not be overwritten.
    assert w.run_id == "already-2026-01-01-001"


def test_backfill_from_titles_groups_by_feature():
    u = make_user()
    make_review(u, run_id="microplans-2026-06-02-001")
    w = make_walkthrough(u, kind="html", title="Microplans deep dive")
    call_command("backfill_run_ids", "--from-titles", stdout=StringIO())
    w.refresh_from_db()
    assert w.feature == "microplans"
    assert w.run_id is None  # a title alone doesn't pin a specific run
