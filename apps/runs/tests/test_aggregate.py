"""Unit tests for the pure run-aggregation functions."""
from __future__ import annotations

import pytest

from apps.common.ddd import narrative_slug_from_run_id
from apps.runs import aggregate

from .factories import make_review, make_user, make_walkthrough

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# narrative_slug_from_run_id
# ---------------------------------------------------------------------------


def test_feature_strips_date_stamp():
    assert narrative_slug_from_run_id("microplans-2026-06-02-001") == "microplans"
    assert narrative_slug_from_run_id("micro-plans-study-2026-06-02-012") == "micro-plans-study"


def test_feature_fallbacks():
    assert narrative_slug_from_run_id("") == "(untitled)"
    assert narrative_slug_from_run_id("no-stamp-here") == "no-stamp-here"


# ---------------------------------------------------------------------------
# build_run — artifact selection
# ---------------------------------------------------------------------------


def test_build_run_surfaces_video_slides_and_documentation_as_first_class():
    u = make_user()
    rid = "microplans-2026-06-02-001"
    make_walkthrough(u, kind="video", run_id=rid, role="clip", title="iter0 clip")
    hero = make_walkthrough(u, kind="video", run_id=rid, role="hero_video", title="hero")
    slides = make_walkthrough(u, kind="html", run_id=rid, role="deck", title="slideshow")
    docs = make_walkthrough(u, kind="html", run_id=rid, role="docs", title="docs page")

    run = aggregate.build_run(rid)
    assert run is not None
    assert run["video"]["id"] == hero.id
    # slides (role=deck) and documentation (role=docs) are distinct first-class
    # objects — the slideshow must not be hidden behind the docs page.
    assert run["slides"]["id"] == slides.id
    assert run["documentation"]["id"] == docs.id
    assert run["narrative_slug"] == "microplans"
    assert run["video"]["content_url"] == f"/w/{hero.id}/content"


def test_build_run_unroled_html_falls_back_to_documentation():
    u = make_user()
    rid = "calendar-2026-06-01-002"
    vid = make_walkthrough(u, kind="video", run_id=rid)
    html = make_walkthrough(u, kind="html", run_id=rid)
    run = aggregate.build_run(rid)
    assert run["video"]["id"] == vid.id
    # An unroled HTML artifact surfaces as documentation, not slides.
    assert run["documentation"]["id"] == html.id
    assert run["slides"] is None


def test_build_run_returns_none_for_unknown_run():
    assert aggregate.build_run("does-not-exist-2026-01-01-001") is None


# ---------------------------------------------------------------------------
# build_run — narrative, links, previous runs
# ---------------------------------------------------------------------------


def test_build_run_uses_latest_review_with_narrative():
    u = make_user()
    rid = "onboarding-2026-06-02-001"
    make_review(u, run_id=rid, gate="early", request_json={"run_id": rid, "gate": "early"})
    make_review(
        u,
        run_id=rid,
        gate="narrative-agreement",
        request_json={
            "run_id": rid,
            "gate": "narrative-agreement",
            "narrative": "A field worker opens the app.\nThen magic happens.",
            "narration": [{"scene": 1, "id": "n1", "text": "Scene one"}],
            "personas": {"flw": {"name": "Ada"}},
        },
    )
    run = aggregate.build_run(rid)
    assert run["narrative"]["story"].startswith("A field worker opens the app.")
    assert run["narrative"]["title"] == "A field worker opens the app."
    assert run["phase"] == "narrative-agreement · pending"


def test_build_run_dedupes_links_across_artifacts():
    u = make_user()
    rid = "links-2026-06-02-001"
    make_walkthrough(
        u,
        kind="video",
        run_id=rid,
        links=[{"label": "Spec", "url": "https://x/spec", "kind": "narrative"}],
    )
    make_walkthrough(
        u,
        kind="html",
        run_id=rid,
        links=[
            {"label": "Spec", "url": "https://x/spec", "kind": "narrative"},
            {"label": "Repo", "url": "https://x/repo", "kind": "reference"},
        ],
    )
    run = aggregate.build_run(rid)
    urls = sorted((link["url"], link["kind"]) for link in run["links"])
    assert urls == [("https://x/repo", "reference"), ("https://x/spec", "narrative")]


# ---------------------------------------------------------------------------
# Narrative list + detail
# ---------------------------------------------------------------------------


def test_list_narratives_groups_and_filters():
    u = make_user()
    other = make_user("other@dimagi.com")
    make_walkthrough(u, kind="video", run_id="a-2026-06-01-001", narrative_slug="a", project_slug="proj1")
    make_walkthrough(u, kind="html", run_id="a-2026-06-02-002", narrative_slug="a", project_slug="proj1")
    make_walkthrough(other, kind="video", run_id="b-2026-06-01-001", narrative_slug="b", project_slug="proj2")

    all_narr = {n["slug"]: n for n in aggregate.list_narratives()}
    assert set(all_narr) == {"a", "b"}
    assert all_narr["a"]["run_count"] == 2
    assert all_narr["a"]["has_video"] and all_narr["a"]["has_deck"]

    proj1 = aggregate.list_narratives(project="proj1")
    assert {n["slug"] for n in proj1} == {"a"}

    mine = aggregate.list_narratives(owner_id=other.id)
    assert {n["slug"] for n in mine} == {"b"}


def test_build_narrative_lists_runs_newest_first():
    u = make_user()
    make_walkthrough(u, kind="video", run_id="feat-2026-05-01-001", narrative_slug="feat")
    make_walkthrough(u, kind="video", run_id="feat-2026-06-01-002", narrative_slug="feat")
    make_review(
        u,
        run_id="feat-2026-06-01-002",
        request_json={
            "run_id": "feat-2026-06-01-002",
            "gate": "narrative-agreement",
            "narrative": "The story.",
            "narration": [{"scene": 1, "id": "n1", "text": "x"}],
        },
    )

    narrative = aggregate.build_narrative("feat")
    assert narrative is not None
    # One narrative version; both runs nest under it, newest first.
    assert len(narrative["versions"]) == 1
    v = narrative["versions"][0]
    assert v["story"] == "The story."
    assert [r["run_id"] for r in v["runs"]] == [
        "feat-2026-06-01-002",
        "feat-2026-05-01-001",
    ]
    assert v["runs"][0]["scene_count"] == 1
    assert narrative["current_version"]["story"] == "The story."


def test_build_narrative_groups_runs_under_their_version():
    u = make_user()
    # v1 review + a run stamped to it; v2 review + a run stamped to it.
    v1 = make_review(
        u, run_id="feat-2026-06-01-001", version=1,
        request_json={"run_id": "feat-2026-06-01-001", "gate": "concept_change",
                      "narrative": "Story v1", "narration": [{"id": "n", "text": "x"}]},
    )
    v2 = make_review(
        u, run_id="feat-2026-06-02-001", version=2,
        request_json={"run_id": "feat-2026-06-02-001", "gate": "concept_change",
                      "narrative": "Story v2", "narration": [{"id": "n", "text": "x"}]},
    )
    make_walkthrough(u, kind="video", run_id="run-a", narrative_slug="feat", narrative_review_id=v1.id)
    make_walkthrough(u, kind="video", run_id="run-b", narrative_slug="feat", narrative_review_id=v2.id)

    narrative = aggregate.build_narrative("feat")
    # newest version first
    assert [v["version"] for v in narrative["versions"]] == [2, 1]
    by_ver = {v["version"]: v for v in narrative["versions"]}
    assert [r["run_id"] for r in by_ver[1]["runs"]] == ["run-a"]
    assert [r["run_id"] for r in by_ver[2]["runs"]] == ["run-b"]
    assert narrative["current_version"]["version"] == 2


def test_build_run_resolves_version_from_stamp():
    u = make_user()
    v2 = make_review(
        u, run_id="feat-2026-06-02-001", version=2,
        request_json={"run_id": "feat-2026-06-02-001", "gate": "concept_change",
                      "narrative": "Story v2", "narration": [{"id": "n", "text": "x"}]},
    )
    make_walkthrough(u, kind="video", run_id="run-b", narrative_slug="feat", narrative_review_id=v2.id)
    run = aggregate.build_run("run-b")
    assert run["narrative"]["review_id"] == str(v2.id)
    assert run["narrative"]["version"] == 2
    assert run["narrative"]["story"] == "Story v2"


def test_build_narrative_unknown_slug_is_none():
    assert aggregate.build_narrative("nope") is None


def test_product_findings_review_is_not_a_narrative_version():
    """A run-child product_findings review carries a narration *mirror*, but it must
    NOT be counted as a narrative version — otherwise it shows as a bogus 'v0' row in
    the DDD shell and hijacks the narrative's title/phase from the real story."""
    u = make_user()
    rid = "program-admin-report-2026-06-11-001"
    # The real narrative.
    make_review(
        u,
        run_id=rid,
        gate="narrative-agreement",
        request_json={
            "run_id": rid,
            "gate": "narrative-agreement",
            "narrative": "Amani opens the weekly nutrition review.\nThe table has already flagged a worker.",
            "narration": [{"scene": 1, "id": "n1", "text": "Scene one"}],
        },
    )
    # A run-child findings review (carries a narration mirror + a one-line title).
    make_review(
        u,
        run_id=rid,
        gate="product_findings",
        request_json={
            "run_id": rid,
            "gate": "product_findings",
            "clusters": [{"id": "c1", "title": "x"}],
            "narration": [{"scene": 1, "id": "f1", "title": "The interaction model is coherent"}],
        },
    )

    feature = narrative_slug_from_run_id(rid)
    versions = aggregate._narrative_versions_for(feature)
    # Only the narrative-agreement review is a version — the findings review is excluded.
    assert [v.gate for v in versions] == ["narrative-agreement"]

    run = aggregate.build_run(rid)
    # Title/current_version come from the real narrative, not the findings cluster text.
    assert run["narrative"]["title"] == "Amani opens the weekly nutrition review."
