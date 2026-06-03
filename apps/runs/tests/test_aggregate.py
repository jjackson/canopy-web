"""Unit tests for the pure run-aggregation functions."""
from __future__ import annotations

import pytest

from apps.common.ddd import feature_from_run_id
from apps.runs import aggregate

from .factories import make_review, make_user, make_walkthrough

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# feature_from_run_id
# ---------------------------------------------------------------------------


def test_feature_strips_date_stamp():
    assert feature_from_run_id("microplans-2026-06-02-001") == "microplans"
    assert feature_from_run_id("micro-plans-study-2026-06-02-012") == "micro-plans-study"


def test_feature_fallbacks():
    assert feature_from_run_id("") == "(untitled)"
    assert feature_from_run_id("no-stamp-here") == "no-stamp-here"


# ---------------------------------------------------------------------------
# build_run — artifact selection
# ---------------------------------------------------------------------------


def test_build_run_picks_hero_video_and_docs_over_iteration_artifacts():
    u = make_user()
    rid = "microplans-2026-06-02-001"
    make_walkthrough(u, kind="video", run_id=rid, role="clip", title="iter0 clip")
    hero = make_walkthrough(u, kind="video", run_id=rid, role="hero_video", title="hero")
    make_walkthrough(u, kind="html", run_id=rid, role="deck", title="iter0 deck")
    docs = make_walkthrough(u, kind="html", run_id=rid, role="docs", title="docs page")

    run = aggregate.build_run(rid)
    assert run is not None
    assert run["video"]["id"] == hero.id
    assert run["deck"]["id"] == docs.id
    assert run["narrative_slug"] == "microplans"
    assert run["video"]["content_url"] == f"/w/{hero.id}/content"


def test_build_run_falls_back_to_kind_when_no_role():
    u = make_user()
    rid = "calendar-2026-06-01-002"
    vid = make_walkthrough(u, kind="video", run_id=rid)
    deck = make_walkthrough(u, kind="html", run_id=rid)
    run = aggregate.build_run(rid)
    assert run["video"]["id"] == vid.id
    assert run["deck"]["id"] == deck.id


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


def test_build_run_lists_previous_runs_in_same_narrative():
    u = make_user()
    make_walkthrough(u, kind="video", run_id="feat-2026-05-01-001", feature="feat")
    make_walkthrough(u, kind="video", run_id="feat-2026-06-01-002", feature="feat")
    make_walkthrough(u, kind="video", run_id="other-2026-06-01-001", feature="other")

    run = aggregate.build_run("feat-2026-06-01-002")
    prev_ids = {p["run_id"] for p in run["previous_runs"]}
    assert prev_ids == {"feat-2026-05-01-001"}


# ---------------------------------------------------------------------------
# Narrative list + detail
# ---------------------------------------------------------------------------


def test_list_narratives_groups_and_filters():
    u = make_user()
    other = make_user("other@dimagi.com")
    make_walkthrough(u, kind="video", run_id="a-2026-06-01-001", feature="a", project_slug="proj1")
    make_walkthrough(u, kind="html", run_id="a-2026-06-02-002", feature="a", project_slug="proj1")
    make_walkthrough(other, kind="video", run_id="b-2026-06-01-001", feature="b", project_slug="proj2")

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
    make_walkthrough(u, kind="video", run_id="feat-2026-05-01-001", feature="feat")
    make_walkthrough(u, kind="video", run_id="feat-2026-06-01-002", feature="feat")
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
    make_walkthrough(u, kind="video", run_id="run-a", feature="feat", narrative_review_id=v1.id)
    make_walkthrough(u, kind="video", run_id="run-b", feature="feat", narrative_review_id=v2.id)

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
    make_walkthrough(u, kind="video", run_id="run-b", feature="feat", narrative_review_id=v2.id)
    run = aggregate.build_run("run-b")
    assert run["narrative"]["review_id"] == str(v2.id)
    assert run["narrative"]["version"] == 2
    assert run["narrative"]["story"] == "Story v2"


def test_build_narrative_unknown_slug_is_none():
    assert aggregate.build_narrative("nope") is None
