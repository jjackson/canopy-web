"""Read-time aggregation of DDD runs.

A DDD *run* (one ``run_id``) packages a hero video, an HTML walkthrough/deck, a
narrative, and companion links — but those live across two tables
(``Walkthrough`` and ``ReviewRequest``) with no FK. These pure functions join
them on ``run_id`` and roll runs up under their *narrative* (the run_id slug).

Everything here is queryset-in / plain-dict-out so it can be unit-tested without
the HTTP layer, and so the Ninja handlers stay thin.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from apps.common.ddd import narrative_slug_from_run_id
from apps.reviews.models import ReviewRequest
from apps.walkthroughs.models import Walkthrough

# ---------------------------------------------------------------------------
# Small predicates
# ---------------------------------------------------------------------------


def _is_video(w: Walkthrough) -> bool:
    return w.role in (Walkthrough.ROLE_HERO_VIDEO, Walkthrough.ROLE_CLIP) or (
        w.kind == Walkthrough.KIND_VIDEO
    )


def _is_deck(w: Walkthrough) -> bool:
    return w.role in (Walkthrough.ROLE_DOCS, Walkthrough.ROLE_DECK) or (
        w.kind == Walkthrough.KIND_HTML
    )


def narrative_of_walkthrough(w: Walkthrough) -> str:
    return (w.narrative_slug or "").strip() or narrative_slug_from_run_id(w.run_id or "")


def narrative_of_review(r: ReviewRequest) -> str:
    return (getattr(r, "narrative_slug", None) or "").strip() or narrative_slug_from_run_id(r.run_id)


def _is_narrative_version(r: ReviewRequest) -> bool:
    """A narrative version = a story-bearing review that isn't the external
    release gate (which also carries a one-line narration but is not the story)."""
    return _review_has_narrative(r) and r.gate != "external_release"


def _narrative_versions_for(narrative_slug: str) -> list[ReviewRequest]:
    """Narrative-version reviews for a narrative_slug, oldest version first."""
    out = [
        r
        for r in ReviewRequest.objects.all()
        if narrative_of_review(r) == narrative_slug and _is_narrative_version(r)
    ]
    out.sort(key=lambda r: (r.version, r.created_at))
    return out


def has_narrative_version(narrative_slug: str) -> bool:
    """True iff ``narrative_slug`` has at least one story-bearing narrative version.

    A narrative version is a ``concept_change`` review carrying a story (see
    :func:`_is_narrative_version`) — i.e. the ``ddd-narrative-review`` gate ran
    for this narrative. When this is False, any run uploaded under ``narrative_slug``
    renders as **"no narrative"**, so the upload path refuses to publish it.
    """
    return bool(_narrative_versions_for((narrative_slug or "").strip()))


def _narrative_payload(r: ReviewRequest | None) -> dict | None:
    if r is None:
        return None
    rj = r.request_json if isinstance(r.request_json, dict) else {}
    return {
        "review_id": str(r.id),
        "version": r.version,
        "run_id": r.run_id,
        "gate": r.gate,
        "title": _title_from_review(r),
        "story": (rj.get("narrative") or "").strip() or None,
        "narration": rj.get("narration") or [],
        "personas": rj.get("personas") or {},
        "why_brief": rj.get("why_brief"),
    }


def narrative_for_run_id(run_id: str, feature_map: dict[str, str] | None = None) -> str:
    """Narrative slug for a run.

    The explicitly-uploaded ``narrative_slug`` of any walkthrough in the run is the
    source of truth (the plugin sends it). Parsing the run_id slug
    (:func:`narrative_slug_from_run_id`) is only a last-resort fallback for runs that
    have no walkthrough carrying an explicit narrative_slug (e.g. a review-only run).
    """
    if feature_map and feature_map.get(run_id):
        return feature_map[run_id]
    return narrative_slug_from_run_id(run_id)


def _narrative_slug_map(walkthroughs) -> dict[str, str]:
    """run_id -> explicit narrative_slug, from walkthroughs that carry both."""
    m: dict[str, str] = {}
    for w in walkthroughs:
        feat = (getattr(w, "narrative_slug", None) or "").strip()
        if w.run_id and feat:
            m.setdefault(w.run_id, feat)
    return m


def _content_url(w: Walkthrough) -> str:
    """In-app viewer stream. Session auth covers private artifacts for the
    dimagi-gated app; share tokens are managed on the /w/<id> viewer page."""
    return f"/w/{w.id}/content"


def _viewer_url(w: Walkthrough) -> str:
    return f"/w/{w.id}"


def _artifact_payload(w: Walkthrough | None) -> dict | None:
    if w is None:
        return None
    return {
        "id": w.id,
        "title": w.title,
        "kind": w.kind,
        "role": w.role,
        "content_url": _content_url(w),
        "viewer_url": _viewer_url(w),
        "duration_sec": w.duration_sec,
    }


def _pick(wts: list[Walkthrough], *predicates) -> Walkthrough | None:
    """Return the most-recent walkthrough matching the earliest predicate that
    matches anything. ``wts`` must be newest-first."""
    for pred in predicates:
        for w in wts:
            if pred(w):
                return w
    return None


def _review_has_narrative(r: ReviewRequest) -> bool:
    rj = r.request_json if isinstance(r.request_json, dict) else {}
    return bool((rj.get("narrative") or "").strip() or rj.get("narration"))


def _title_from_review(r: ReviewRequest) -> str | None:
    rj = r.request_json if isinstance(r.request_json, dict) else {}
    narrative = (rj.get("narrative") or "").strip()
    if narrative:
        first = narrative.splitlines()[0].strip()
        return first[:140] if first else None
    narration = rj.get("narration") or []
    if narration and isinstance(narration[0], dict):
        t = (narration[0].get("title") or "").strip()
        return t or None
    return None


def _phase_label(r: ReviewRequest) -> str:
    return f"{r.gate} · {r.status}"


def _scene_count(r: ReviewRequest | None) -> int:
    if r is None:
        return 0
    rj = r.request_json if isinstance(r.request_json, dict) else {}
    narration = rj.get("narration") or []
    return len(narration) if isinstance(narration, list) else 0


# ---------------------------------------------------------------------------
# Single run package
# ---------------------------------------------------------------------------


def build_run(run_id: str) -> dict | None:
    """Aggregate one run_id into a package dict, or ``None`` if nothing matches."""
    wts = list(Walkthrough.objects.filter(run_id=run_id).select_related("owner"))
    revs = list(ReviewRequest.objects.filter(run_id=run_id))  # -created_at default
    if not wts and not revs:
        return None

    video = _pick(
        wts,
        lambda w: w.role == Walkthrough.ROLE_HERO_VIDEO,
        lambda w: w.role == Walkthrough.ROLE_CLIP,
        lambda w: w.kind == Walkthrough.KIND_VIDEO,
    )
    # First-class, single-valued outputs (newest of each role). `slides` is the
    # canopy:walkthrough HTML slideshow (role=deck); `documentation` is the
    # feature docs page (role=docs). An unroled HTML artifact falls back to
    # documentation so legacy uploads still surface somewhere, but a role=deck
    # artifact never leaks into documentation (and vice-versa).
    slides = _pick(wts, lambda w: w.role == Walkthrough.ROLE_DECK)
    documentation = _pick(
        wts,
        lambda w: w.role == Walkthrough.ROLE_DOCS,
        lambda w: w.kind == Walkthrough.KIND_HTML
        and w.role != Walkthrough.ROLE_DECK,
    )

    # Explicit narrative_slug (uploaded by the plugin) wins; run_id parsing is fallback.
    explicit_narrative_slug = next(
        (w.narrative_slug for w in wts if (w.narrative_slug or "").strip()), None
    )
    narrative_slug = explicit_narrative_slug or narrative_slug_from_run_id(run_id)

    # The narrative VERSION this run rendered. Prefer the explicit stamp
    # (narrative_review_id on the run's artifacts); else the run's own
    # story-bearing review; else the narrative's current version (legacy).
    stamped = next((w.narrative_review_id for w in wts if w.narrative_review_id), None)
    narrative_review = None
    if stamped:
        narrative_review = ReviewRequest.objects.filter(pk=stamped).first()
    if narrative_review is None:
        narrative_review = next((r for r in revs if _is_narrative_version(r)), None)
    if narrative_review is None:
        versions = _narrative_versions_for(narrative_slug)
        narrative_review = versions[-1] if versions else None

    narrative_payload = _narrative_payload(narrative_review)
    phase = _phase_label(revs[0]) if revs else None

    # Links: union across the run's walkthroughs, de-duped on (url, kind),
    # oldest-first for a stable order.
    links: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for w in sorted(wts, key=lambda x: x.created_at):
        for link in w.links or []:
            if not isinstance(link, dict):
                continue
            key = (link.get("url", ""), link.get("kind", "reference"))
            if key in seen:
                continue
            seen.add(key)
            links.append(
                {
                    "label": link.get("label", ""),
                    "url": link.get("url", ""),
                    "kind": link.get("kind", "reference"),
                }
            )

    all_artifacts = [
        {
            "id": w.id,
            "title": w.title,
            "kind": w.kind,
            "role": w.role,
            "created_at": w.created_at,
            "viewer_url": _viewer_url(w),
        }
        for w in sorted(wts, key=lambda x: x.created_at)
    ]

    timestamps = [w.created_at for w in wts] + [r.created_at for r in revs]
    created_at = min(timestamps) if timestamps else None
    latest_at = max(timestamps) if timestamps else None

    return {
        "run_id": run_id,
        "narrative_slug": narrative_slug,
        "created_at": created_at,
        "latest_at": latest_at,
        "phase": phase,
        "video": _artifact_payload(video),
        "slides": _artifact_payload(slides),
        "documentation": _artifact_payload(documentation),
        "narrative": narrative_payload,
        "links": links,
        "all_artifacts": all_artifacts,
    }


# ---------------------------------------------------------------------------
# Narrative list + detail
# ---------------------------------------------------------------------------


def _blank_narrative(slug: str) -> dict[str, Any]:
    return {
        "slug": slug,
        "title": None,
        "story": None,
        "phase": None,
        "project_slug": None,
        "run_ids": set(),
        "project_slugs": set(),
        "owner_ids": set(),
        "latest_at": None,
        "has_video": False,
        "has_deck": False,
        "has_narrative": False,
        "_latest_rev_at": None,
        "_latest_narr_at": None,
    }


def _max(a: datetime | None, b: datetime | None) -> datetime | None:
    if a is None:
        return b
    if b is None:
        return a
    return a if a >= b else b


def _aggregate(project: str | None, owner_id: int | None) -> dict[str, dict]:
    """Build the per-narrative aggregate map from both tables. Filters are
    applied at the narrative level afterwards by the callers."""
    wts = list(
        Walkthrough.objects.exclude(run_id__isnull=True)
        .exclude(run_id="")
        .select_related("owner")
    )
    revs = list(ReviewRequest.objects.all())

    feature_map = _narrative_slug_map(wts)

    narr: dict[str, dict] = {}
    for w in wts:
        slug = narrative_of_walkthrough(w)
        a = narr.get(slug) or narr.setdefault(slug, _blank_narrative(slug))
        a["run_ids"].add(w.run_id)
        if w.project_slug:
            a["project_slugs"].add(w.project_slug)
            if a["project_slug"] is None:
                a["project_slug"] = w.project_slug
        a["owner_ids"].add(w.owner_id)
        a["latest_at"] = _max(a["latest_at"], w.created_at)
        if _is_video(w):
            a["has_video"] = True
        if _is_deck(w):
            a["has_deck"] = True

    for r in revs:
        slug = narrative_for_run_id(r.run_id, feature_map)
        a = narr.setdefault(slug, _blank_narrative(slug))
        a["run_ids"].add(r.run_id)
        if r.owner_id:
            a["owner_ids"].add(r.owner_id)
        a["latest_at"] = _max(a["latest_at"], r.created_at)
        # Latest review overall drives the phase label.
        if a["_latest_rev_at"] is None or r.created_at > a["_latest_rev_at"]:
            a["_latest_rev_at"] = r.created_at
            a["phase"] = _phase_label(r)
        # Latest review carrying a story drives title/story.
        if _review_has_narrative(r) and (
            a["_latest_narr_at"] is None or r.created_at > a["_latest_narr_at"]
        ):
            a["_latest_narr_at"] = r.created_at
            a["has_narrative"] = True
            a["title"] = _title_from_review(r)
            rj = r.request_json if isinstance(r.request_json, dict) else {}
            a["story"] = (rj.get("narrative") or "").strip() or None

    # Narrative-level filters.
    def _keep(a: dict) -> bool:
        if project is not None and project not in a["project_slugs"]:
            return False
        if owner_id is not None and owner_id not in a["owner_ids"]:
            return False
        return True

    return {slug: a for slug, a in narr.items() if _keep(a)}


def list_narratives(
    project: str | None = None, owner_id: int | None = None
) -> list[dict]:
    """Narrative list items, newest activity first."""
    narr = _aggregate(project, owner_id)
    items = [
        {
            "slug": a["slug"],
            "title": a["title"],
            "phase": a["phase"],
            "project_slug": a["project_slug"],
            "run_count": len(a["run_ids"]),
            "latest_at": a["latest_at"],
            "has_video": a["has_video"],
            "has_deck": a["has_deck"],
            "has_narrative": a["has_narrative"],
        }
        for a in narr.values()
    ]
    items.sort(key=lambda it: it["latest_at"] or datetime.min, reverse=True)
    return items


def _run_summary(run_id, run_wts, run_revs) -> dict:
    run_revs = sorted(run_revs, key=lambda r: r.created_at, reverse=True)
    latest_rev = run_revs[0] if run_revs else None
    narr_rev = next((r for r in run_revs if _is_narrative_version(r)), latest_rev)
    ts = [w.created_at for w in run_wts] + [r.created_at for r in run_revs]
    return {
        "run_id": run_id,
        "created_at": min(ts) if ts else None,
        "latest_at": max(ts) if ts else None,
        "status": latest_rev.status if latest_rev else None,
        "gate": latest_rev.gate if latest_rev else None,
        "scene_count": _scene_count(narr_rev),
        "has_video": any(_is_video(w) for w in run_wts),
        "has_deck": any(_is_deck(w) for w in run_wts),
    }


def build_narrative(slug: str) -> dict | None:
    """Narrative landing: version-grouped — each narrative version with its runs
    nested beneath it (newest version first)."""
    narr = _aggregate(project=None, owner_id=None)
    a = narr.get(slug)
    if a is None:
        return None

    wts = [
        w
        for w in Walkthrough.objects.exclude(run_id__isnull=True)
        .exclude(run_id="")
        .select_related("owner")
        if narrative_of_walkthrough(w) == slug
    ]
    revs = [r for r in ReviewRequest.objects.all() if narrative_of_review(r) == slug]

    wts_by_run: dict[str, list[Walkthrough]] = {}
    for w in wts:
        wts_by_run.setdefault(w.run_id, []).append(w)
    revs_by_run: dict[str, list[ReviewRequest]] = {}
    for r in revs:
        revs_by_run.setdefault(r.run_id, []).append(r)

    # Narrative versions (story-bearing reviews), oldest first.
    versions = [r for r in revs if _is_narrative_version(r)]
    versions.sort(key=lambda r: (r.version, r.created_at))
    versions_by_id = {str(r.id): r for r in versions}
    current = versions[-1] if versions else None

    # Resolve which version each run rendered.
    def _version_review_for(run_id) -> ReviewRequest | None:
        run_wts = wts_by_run.get(run_id, [])
        stamped = next((w.narrative_review_id for w in run_wts if w.narrative_review_id), None)
        if stamped and str(stamped) in versions_by_id:
            return versions_by_id[str(stamped)]
        own = next(
            (r for r in revs_by_run.get(run_id, []) if _is_narrative_version(r)), None
        )
        if own is not None:
            return own
        return current

    # A "run" is a render — it has artifacts. Narrative-version reviews are NOT
    # runs (they're the story), so bucket only artifact-bearing run_ids.
    buckets: dict[str | None, list[dict]] = {}
    for run_id in wts_by_run:
        ver = _version_review_for(run_id)
        key = str(ver.id) if ver is not None else None
        summary = _run_summary(run_id, wts_by_run[run_id], revs_by_run.get(run_id, []))
        buckets.setdefault(key, []).append(summary)

    def _sorted_runs(rs):
        return sorted(rs, key=lambda it: it["latest_at"] or datetime.min, reverse=True)

    versions_payload = []
    for r in reversed(versions):  # newest version first
        np = _narrative_payload(r)
        versions_payload.append(
            {
                "version": r.version,
                "review_id": str(r.id),
                "title": np["title"],
                "story": np["story"],
                "created_at": r.created_at,
                "gate": r.gate,
                "status": r.status,
                "runs": _sorted_runs(buckets.get(str(r.id), [])),
            }
        )
    # Runs with no resolvable version (e.g. narrative has artifacts but no review).
    if buckets.get(None):
        versions_payload.append(
            {
                "version": None,
                "review_id": None,
                "title": None,
                "story": None,
                "created_at": None,
                "gate": None,
                "status": None,
                "runs": _sorted_runs(buckets[None]),
            }
        )

    current_payload = None
    if current is not None:
        cp = _narrative_payload(current)
        current_payload = {
            "review_id": cp["review_id"],
            "version": cp["version"],
            "title": cp["title"],
            "story": cp["story"],
        }

    return {
        "slug": slug,
        "title": a["title"],
        "story": a["story"],
        "phase": a["phase"],
        "project_slug": a["project_slug"],
        "current_version": current_payload,
        "versions": versions_payload,
    }
