"""Tests for title-based narrative/run inference, anchored on real prod titles."""
from __future__ import annotations

from datetime import date

import pytest

from apps.runs.inference import infer, narrative_slug, run_token


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Program Admin Report — HTML deck (v4)", "program-admin-report"),
        ("Demo-Driven Development — hero demo", "demo-driven-development"),
        ("Microplans — Left-rail redesign (video)", "microplans-left-rail"),
        ("Madobi two-arm rooftop study — DDD walkthrough", "madobi-rooftop-study"),
        ("Microplan → Opportunity — full cycle (tightened, 2.5min)", "microplan-to-opp"),
        ("microplans-10-wards iter1 video (2026-06-01-002)", "microplans-10-wards"),
        ("Microplans 10 wards — Madobi LGA / Kim (scenes 1-5)", "microplans-10-wards"),
        ("compare page — simplified", "microplans-10-wards"),
        ("something totally unrelated", None),
    ],
)
def test_narrative_slug(title, expected):
    assert narrative_slug(title) == expected


def test_madobi_lga_is_10_wards_not_rooftop():
    # "Madobi LGA" inside a 10-wards title must NOT route to the rooftop study.
    assert narrative_slug("Microplans 10 wards — Madobi LGA — dead-space fixed") == "microplans-10-wards"


def test_run_token_prefers_stamp_then_iter_then_version_then_date():
    d = date(2026, 5, 28)
    assert run_token("microplans-10-wards iter1 video (2026-06-01-002)", d) == "2026-06-01-002"
    assert run_token("microplans-10-wards iter1 clip", d) == "iter1"
    assert run_token("Program Admin Report — HTML deck (v4)", d) == "v4"
    assert run_token("Program Admin Report — HTML deck (final)", d) == "final"
    assert run_token("microplans-10-wards — documentation", d) == "2026-05-28"


def test_infer_builds_slug_and_run_id():
    assert infer("microplans-10-wards iter0 video (2026-06-01-002)", date(2026, 6, 1)) == (
        "microplans-10-wards",
        "microplans-10-wards-2026-06-01-002",
    )
    assert infer("Program Admin Report — manager flow (v3)", date(2026, 5, 28)) == (
        "program-admin-report",
        "program-admin-report-v3",
    )
    assert infer("unrelated thing", date(2026, 1, 1)) is None
