"""Tests for migrate_narrative_versions."""
from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from .factories import make_review, make_user, make_walkthrough

pytestmark = pytest.mark.django_db


def _narr_json(run_id):
    return {"run_id": run_id, "gate": "concept_change",
            "narrative": "Story", "narration": [{"id": "n", "text": "x"}]}


def test_assigns_feature_and_sequential_versions():
    u = make_user()
    # Two narrative versions for narrative_slug "feat" (created in order).
    r1 = make_review(u, run_id="feat-2026-06-01-001", request_json=_narr_json("feat-2026-06-01-001"))
    r2 = make_review(u, run_id="feat-2026-06-02-001", request_json=_narr_json("feat-2026-06-02-001"))
    call_command("migrate_narrative_versions", stdout=StringIO())
    r1.refresh_from_db()
    r2.refresh_from_db()
    assert r1.narrative_slug == "feat" and r2.narrative_slug == "feat"
    assert (r1.version, r2.version) == (1, 2)


def test_stamps_walkthrough_to_current_version():
    u = make_user()
    make_review(u, run_id="feat-2026-06-01-001", request_json=_narr_json("feat-2026-06-01-001"))
    r2 = make_review(u, run_id="feat-2026-06-02-001", request_json=_narr_json("feat-2026-06-02-001"))
    w = make_walkthrough(u, kind="video", run_id="render-1", narrative_slug="feat")
    assert w.narrative_review_id is None
    call_command("migrate_narrative_versions", stdout=StringIO())
    w.refresh_from_db()
    # linked to the latest narrative version (r2)
    assert str(w.narrative_review_id) == str(r2.id)


def test_dry_run_writes_nothing():
    u = make_user()
    r1 = make_review(u, run_id="feat-2026-06-01-001", request_json=_narr_json("feat-2026-06-01-001"))
    call_command("migrate_narrative_versions", "--dry-run", stdout=StringIO())
    r1.refresh_from_db()
    assert r1.narrative_slug is None


def test_idempotent():
    u = make_user()
    make_review(u, run_id="feat-2026-06-01-001", request_json=_narr_json("feat-2026-06-01-001"))
    out1 = StringIO()
    call_command("migrate_narrative_versions", stdout=out1)
    out2 = StringIO()
    call_command("migrate_narrative_versions", stdout=out2)
    assert "updated 0 review(s), stamped 0" in out2.getvalue()
