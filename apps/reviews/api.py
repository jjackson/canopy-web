"""Django Ninja v2 router for the reviews surface.

Endpoints:
  GET    /api/reviews/            — list all review requests (DDD-plans dashboard)
  POST   /api/reviews/            — create a review_request (orchestrator → server)
  GET    /api/reviews/<id>/       — poll for status (orchestrator) / show to human
  POST   /api/reviews/<id>/submit/ — human submits decisions + narration edits
  DELETE /api/reviews/<id>/       — delete a review request (dashboard cleanup)

Auth strategy: the same PAT Bearer flow used everywhere else in canopy-web.
The canopy-side orchestrator mints a Personal Access Token (via manage.py
create_token) and sends `Authorization: Bearer <raw>` on every call.
BearerTokenAuthMiddleware resolves the token to a real Django user, so all
three endpoints see an authenticated request.user — no special allowlist
hacks needed. The human review page uses the same session_auth (already
logged in via Google OAuth) or, if visibility=="link", the review is readable
by anyone with the URL (no ?t= token required).
"""
from __future__ import annotations

import logging
from uuid import UUID

from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Status

from apps.api.auth import session_auth
from apps.api.errors import TYPE_FORBIDDEN, TYPE_NOT_FOUND, ProblemError
from apps.common.ddd import narrative_slug_from_run_id
from apps.workspaces import services as wsvc

from .models import ReviewRequest
from .schemas import (
    ReviewCreateIn,
    ReviewCreateOut,
    ReviewListItemOut,
    ReviewRequestOut,
    ReviewSubmitIn,
)

log = logging.getLogger(__name__)

router = Router(auth=session_auth, tags=["reviews"])

# Gates whose reviews hang off the RUN, not the narrative timeline. These never get a
# narrative_slug or a monotonic narrative version (see create_review) — so they don't
# pollute the version numbering or show up as narrative-version rows in the DDD shell.
RUN_CHILD_GATES = ("product_findings",)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_or_404(rid: UUID) -> ReviewRequest:
    r = ReviewRequest.objects.filter(pk=rid).first()
    if r is None:
        raise ProblemError(404, "Review request not found", type_=TYPE_NOT_FOUND)
    return r


def _is_owner(request: HttpRequest, review: ReviewRequest) -> bool:
    return (
        request.user.is_authenticated
        and review.owner_id is not None
        and review.owner_id == request.user.id
    )


def _can_read(request: HttpRequest, review: ReviewRequest) -> bool:
    """Authenticated users see all reviews; public (link) reviews are readable by anyone."""
    return (
        request.user.is_authenticated
        or review.visibility == ReviewRequest.VISIBILITY_LINK
    )


def _can_write(request: HttpRequest, review: ReviewRequest) -> bool:
    """Submitting a decision (approve/redraft) requires a Dimagi login —
    public-readable does NOT grant anonymous write."""
    return request.user.is_authenticated


def _detail_payload(review: ReviewRequest, *, is_owner: bool) -> dict:
    return {
        "id": review.id,
        "run_id": review.run_id,
        "gate": review.gate,
        "status": review.status,
        "visibility": review.visibility,
        "narrative_slug": (getattr(review, "narrative_slug", None) or "").strip()
        or narrative_slug_from_run_id(review.run_id),
        "request_json": review.request_json,
        "response_json": review.response_json,
        "is_owner": is_owner,
        "created_at": review.created_at,
        "resolved_at": review.resolved_at,
    }


def _list_title(request_json: dict) -> str | None:
    """A short human label: the narrative's first line, else the first scene title."""
    # Run-child product-findings reviews have no narrative — label by cluster count.
    if request_json.get("gate") == "product_findings":
        clusters = request_json.get("clusters") or []
        iteration = request_json.get("iteration")
        n = len(clusters) if isinstance(clusters, list) else 0
        label = f"Findings review — {n} finding{'s' if n != 1 else ''}"
        return f"{label} (iter {iteration})" if iteration is not None else label
    narrative = (request_json.get("narrative") or "").strip()
    if narrative:
        first = narrative.splitlines()[0].strip()
        return first[:140] if first else None
    narration = request_json.get("narration") or []
    if narration and isinstance(narration[0], dict):
        t = (narration[0].get("title") or "").strip()
        return t or None
    return None


def _list_item_payload(request: HttpRequest, review: ReviewRequest) -> dict:
    rj = review.request_json if isinstance(review.request_json, dict) else {}
    narration = rj.get("narration") or []
    is_own = _is_owner(request, review)
    if review.gate == "product_findings":
        clusters = rj.get("clusters") or []
        item_count = len(clusters) if isinstance(clusters, list) else 0
    else:
        item_count = len(narration) if isinstance(narration, list) else 0
    return {
        "id": review.id,
        "run_id": review.run_id,
        "gate": review.gate,
        "status": review.status,
        "visibility": review.visibility,
        "narrative_slug": narrative_slug_from_run_id(review.run_id),
        "title": _list_title(rj),
        "scene_count": item_count,
        "created_at": review.created_at,
        "resolved_at": review.resolved_at,
        "last_activity_at": review.resolved_at or review.created_at,
        "is_owner": is_own,
    }


# ---------------------------------------------------------------------------
# List (DDD-plans dashboard)
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response=list[ReviewListItemOut],
    summary="List review requests (DDD-plans dashboard)",
)
def list_reviews(
    request: HttpRequest,
    q: str = "",
    status: str = "",
    order: str = "-last_activity",
) -> list[ReviewListItemOut]:
    """
    List every review request for the DDD-plans dashboard.

    Team-internal: any authenticated user (session or PAT) sees all reviews —
    same read rule as GET /<id>/. Supports a free-text `q` (matches narrative_slug,
    run_id, gate, or title), an optional `status` filter (pending|resolved),
    and `order` ∈ {-last_activity, last_activity, -created, created, narrative_slug}.
    Default sort is most-recently-edited first.
    """
    # Workspace scoping: honor the /w/{ws} prefix when present (already
    # membership-checked by WorkspaceResolveMiddleware); on the flat mount,
    # scope to every workspace the caller belongs to. Domain teammates are
    # auto-joined first so the default-workspace case keeps working. Legacy
    # rows with workspace=None stay visible on the flat mount (backfill safety).
    wsvc.auto_join_workspaces(request.user)
    ws = getattr(request, "workspace_slug", None)
    slugs = {ws} if ws else wsvc.user_workspace_slugs(request.user)

    qs = ReviewRequest.objects.filter(workspace_id__in=slugs)
    if ws is None:
        qs = qs | ReviewRequest.objects.filter(workspace__isnull=True)
    if status in (ReviewRequest.STATUS_PENDING, ReviewRequest.STATUS_RESOLVED):
        qs = qs.filter(status=status)

    # Build derived rows once, then filter/sort in Python — the review set is
    # team-internal and small, and narrative_slug/title live inside the JSON payload.
    items = [_list_item_payload(request, r) for r in qs.iterator()]

    needle = q.strip().lower()
    if needle:
        items = [
            it
            for it in items
            if needle in it["narrative_slug"].lower()
            or needle in it["run_id"].lower()
            or needle in it["gate"].lower()
            or needle in (it["title"] or "").lower()
        ]

    sort_keys = {
        "-last_activity": (lambda it: it["last_activity_at"], True),
        "last_activity": (lambda it: it["last_activity_at"], False),
        "-created": (lambda it: it["created_at"], True),
        "created": (lambda it: it["created_at"], False),
        "narrative_slug": (lambda it: it["narrative_slug"].lower(), False),
    }
    key_fn, reverse = sort_keys.get(order, sort_keys["-last_activity"])
    items.sort(key=key_fn, reverse=reverse)

    return [ReviewListItemOut.model_validate(it) for it in items]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response={201: ReviewCreateOut},
    summary="Create a review request (orchestrator)",
)
def create_review(request: HttpRequest, payload: ReviewCreateIn) -> Status:
    """
    Called by the canopy orchestrator when it hits a pause gate.

    The orchestrator authenticates via a Personal Access Token (PAT).
    Returns the review's UUID and the share URL the human will visit.
    """
    request_json = payload.request_json
    run_id = str(request_json.get("run_id", ""))
    gate = str(request_json.get("gate", ""))

    # Narrative identity + version. `narrative_slug` (narrative_id) is explicit when the
    # plugin sends it, else derived from the run_id slug. A narrative-agreement
    # review (gate concept_change) opens a NEW version; other narrative gates attach to
    # the current version so version numbers stay clean (1, 2, 3, …).
    #
    # RUN-CHILD gates (product_findings) are NOT narrative versions — they hang off the
    # run, not the narrative timeline. Carrying a narrative_slug here is what made the
    # findings review surface as a bogus "v3" row, so run-child gates get
    # narrative_slug=None and version=0 (the sentinel for "not a narrative version").
    is_narrative_gate = gate in ("concept_change", "narrative-agreement")
    if gate in RUN_CHILD_GATES:
        narrative_slug = None
        version = 0
    else:
        narrative_slug = (request_json.get("narrative_slug") or narrative_slug_from_run_id(run_id)) or None
        if is_narrative_gate:
            version = ReviewRequest.next_version(narrative_slug)
        else:
            version = max(ReviewRequest.next_version(narrative_slug) - 1, 1)

    # Assign the owning workspace: the /w/{ws} prefix pins it (membership already
    # verified upstream); else fall back to the org default so an unchanged
    # orchestrator call keeps working. ensure_member keeps the creator's access.
    pinned = getattr(request, "workspace_slug", None)
    ws = (
        wsvc.Workspace.objects.filter(slug=pinned).first() if pinned else None
    ) or wsvc.ensure_default_workspace()
    if ws is not None and request.user.is_authenticated:
        wsvc.ensure_member(ws, request.user)

    review = ReviewRequest.objects.create(
        run_id=run_id,
        narrative_slug=narrative_slug,
        version=version,
        gate=gate,
        status=ReviewRequest.STATUS_PENDING,
        request_json=request_json,
        response_json=None,
        visibility=payload.visibility,
        owner=request.user if request.user.is_authenticated else None,
        workspace=ws,
    )

    # Build the hosted-review URL.  The frontend SPA handles /review/<id>.
    url = f"/review/{review.id}/"

    return Status(
        201,
        ReviewCreateOut(id=review.id, url=url),
    )


# ---------------------------------------------------------------------------
# Detail / Poll
# ---------------------------------------------------------------------------


@router.get(
    "/{rid}/",
    response=ReviewRequestOut,
    auth=None,  # Public (visibility=link) reviews are readable without a session.
    summary="Get review request detail or poll for resolution",
)
def get_review(request: HttpRequest, rid: UUID) -> ReviewRequestOut:
    """
    Returns the full review request + current status.

    Access rules:
    - Any authenticated user can read any review (they're team-internal).
    - Unauthenticated callers may read if visibility=="link" (no token required).
    - Otherwise → 404 (don't leak existence).
    """
    review = _get_or_404(rid)

    if not _can_read(request, review):
        raise ProblemError(404, "Review request not found", type_=TYPE_NOT_FOUND)

    is_own = _is_owner(request, review)

    return ReviewRequestOut.model_validate(
        _detail_payload(review, is_owner=is_own)
    )


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


@router.post(
    "/{rid}/submit/",
    response=ReviewRequestOut,
    auth=None,  # handler enforces _can_write (auth required); 403 not 401 for readable-but-anonymous
    summary="Submit decisions + narration edits (human → server)",
)
def submit_review(request: HttpRequest, rid: UUID, payload: ReviewSubmitIn) -> ReviewRequestOut:
    """
    Human submits their decisions and any narration edits.

    Flips status to "resolved" and stamps resolved_at.  Can only be submitted
    once; re-submission on an already-resolved review → 403.
    """
    review = _get_or_404(rid)

    # Give a 404 (not 403) when the caller can't even read the review, so we don't
    # leak existence.  When they CAN read but lack write permission (e.g. anonymous
    # caller on a public review), return 403.
    if not _can_read(request, review):
        raise ProblemError(404, "Review request not found", type_=TYPE_NOT_FOUND)
    if not _can_write(request, review):
        raise ProblemError(403, "Authentication required to submit a review", type_=TYPE_FORBIDDEN)

    if review.status == ReviewRequest.STATUS_RESOLVED:
        raise ProblemError(
            403,
            "Review already resolved",
            type_=TYPE_FORBIDDEN,
            detail="This review has already been submitted and cannot be re-submitted.",
        )

    review.response_json = payload.response_json
    review.status = ReviewRequest.STATUS_RESOLVED
    review.resolved_at = timezone.now()
    review.save(update_fields=["response_json", "status", "resolved_at"])

    is_own = _is_owner(request, review)
    return ReviewRequestOut.model_validate(
        _detail_payload(review, is_owner=is_own)
    )


# ---------------------------------------------------------------------------
# Delete (dashboard cleanup)
# ---------------------------------------------------------------------------


@router.delete(
    "/{rid}/",
    response={204: None},
    summary="Delete a review request (dashboard cleanup)",
)
def delete_review(request: HttpRequest, rid: UUID):
    """
    Delete a review request.

    Team-internal cleanup: any authenticated user (session or PAT) may delete —
    reviews are owned by whichever identity posted them (often the orchestrator's
    PAT, not the human browsing), so restricting to owner would make the human
    unable to tidy up. The router's session_auth already blocks anonymous callers.
    """
    review = _get_or_404(rid)
    review.delete()
    return Status(204, None)
