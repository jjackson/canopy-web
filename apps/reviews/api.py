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
logged in via Google OAuth) or, if visibility=="link", the ?t= query token.
"""
from __future__ import annotations

import logging
from uuid import UUID

from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Status

from apps.api.auth import session_auth
from apps.api.errors import TYPE_FORBIDDEN, TYPE_NOT_FOUND, ProblemError
from apps.common.ddd import feature_from_run_id

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


def _token_ok(request: HttpRequest, review: ReviewRequest) -> bool:
    """True when the ?t= query param matches the review's share_token."""
    t = request.GET.get("t", "")
    return bool(t and review.share_token and t == review.share_token)


def _can_read(request: HttpRequest, review: ReviewRequest) -> bool:
    """Authenticated users always see all reviews; link-visibility also allows ?t= bearer."""
    if request.user.is_authenticated:
        return True
    if review.visibility == ReviewRequest.VISIBILITY_LINK and _token_ok(request, review):
        return True
    return False


def _can_write(request: HttpRequest, review: ReviewRequest) -> bool:
    """Submit and token-rotation require owner or a valid ?t= bearer."""
    if _is_owner(request, review):
        return True
    if review.visibility == ReviewRequest.VISIBILITY_LINK and _token_ok(request, review):
        return True
    return False


def _detail_payload(review: ReviewRequest, *, is_owner: bool, expose_token: bool) -> dict:
    return {
        "id": review.id,
        "run_id": review.run_id,
        "gate": review.gate,
        "status": review.status,
        "visibility": review.visibility,
        "feature": (getattr(review, "feature", None) or "").strip()
        or feature_from_run_id(review.run_id),
        "request_json": review.request_json,
        "response_json": review.response_json,
        # share_token exposed to owner OR link-token holders (they demonstrably
        # have it and need it to re-poll / re-submit).
        "share_token": review.share_token if expose_token else None,
        "is_owner": is_owner,
        "created_at": review.created_at,
        "resolved_at": review.resolved_at,
    }


def _list_title(request_json: dict) -> str | None:
    """A short human label: the narrative's first line, else the first scene title."""
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
    return {
        "id": review.id,
        "run_id": review.run_id,
        "gate": review.gate,
        "status": review.status,
        "visibility": review.visibility,
        "feature": feature_from_run_id(review.run_id),
        "title": _list_title(rj),
        "scene_count": len(narration) if isinstance(narration, list) else 0,
        "created_at": review.created_at,
        "resolved_at": review.resolved_at,
        "last_activity_at": review.resolved_at or review.created_at,
        # Owners and link-visibility reviews expose the token so the dashboard can
        # build a working /review/<id>?t= link without a second round-trip.
        "share_token": review.share_token
        if (is_own or review.visibility == ReviewRequest.VISIBILITY_LINK)
        else None,
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
    same read rule as GET /<id>/. Supports a free-text `q` (matches feature,
    run_id, gate, or title), an optional `status` filter (pending|resolved),
    and `order` ∈ {-last_activity, last_activity, -created, created, feature}.
    Default sort is most-recently-edited first.
    """
    qs = ReviewRequest.objects.all()
    if status in (ReviewRequest.STATUS_PENDING, ReviewRequest.STATUS_RESOLVED):
        qs = qs.filter(status=status)

    # Build derived rows once, then filter/sort in Python — the review set is
    # team-internal and small, and feature/title live inside the JSON payload.
    items = [_list_item_payload(request, r) for r in qs.iterator()]

    needle = q.strip().lower()
    if needle:
        items = [
            it
            for it in items
            if needle in it["feature"].lower()
            or needle in it["run_id"].lower()
            or needle in it["gate"].lower()
            or needle in (it["title"] or "").lower()
        ]

    sort_keys = {
        "-last_activity": (lambda it: it["last_activity_at"], True),
        "last_activity": (lambda it: it["last_activity_at"], False),
        "-created": (lambda it: it["created_at"], True),
        "created": (lambda it: it["created_at"], False),
        "feature": (lambda it: it["feature"].lower(), False),
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

    # Narrative identity + version. `feature` (narrative_id) is explicit when the
    # plugin sends it, else derived from the run_id slug. A narrative-agreement
    # review (gate concept_change) opens a NEW version; other gates attach to the
    # current version so version numbers stay clean (1, 2, 3, …).
    feature = (request_json.get("feature") or feature_from_run_id(run_id)) or None
    is_narrative_gate = gate in ("concept_change", "narrative-agreement")
    if is_narrative_gate:
        version = ReviewRequest.next_version(feature)
    else:
        version = max(ReviewRequest.next_version(feature) - 1, 1)

    review = ReviewRequest.objects.create(
        run_id=run_id,
        feature=feature,
        version=version,
        gate=gate,
        status=ReviewRequest.STATUS_PENDING,
        request_json=request_json,
        response_json=None,
        visibility=payload.visibility,
        owner=request.user if request.user.is_authenticated else None,
    )

    # Always mint a share token: the orchestrator posts the URL to Slack /
    # wherever humans pick it up, and they may not be logged in.
    token = review.ensure_share_token()

    # Build the hosted-review URL.  The frontend SPA handles /review/<id>.
    url = f"/review/{review.id}/?t={token}"

    return Status(
        201,
        ReviewCreateOut(id=review.id, url=url, share_token=token),
    )


# ---------------------------------------------------------------------------
# Detail / Poll
# ---------------------------------------------------------------------------


@router.get(
    "/{rid}/",
    response=ReviewRequestOut,
    auth=None,  # Allow unauthenticated access when ?t= matches share_token
    summary="Get review request detail or poll for resolution",
)
def get_review(request: HttpRequest, rid: UUID) -> ReviewRequestOut:
    """
    Returns the full review request + current status.

    Access rules:
    - Any authenticated user can read any review (they're team-internal).
    - Unauthenticated callers may read if visibility=="link" and ?t= matches.
    - Otherwise → 404 (don't leak existence).
    """
    review = _get_or_404(rid)

    if not _can_read(request, review):
        raise ProblemError(404, "Review request not found", type_=TYPE_NOT_FOUND)

    is_own = _is_owner(request, review)
    # For link-token callers we still include the token in the payload —
    # they demonstrably have it already and need it to re-poll.
    expose_token = is_own or _token_ok(request, review)

    return ReviewRequestOut.model_validate(
        _detail_payload(review, is_owner=is_own, expose_token=expose_token)
    )


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


@router.post(
    "/{rid}/submit/",
    response=ReviewRequestOut,
    auth=None,  # Allow unauthenticated submit when ?t= matches share_token
    summary="Submit decisions + narration edits (human → server)",
)
def submit_review(request: HttpRequest, rid: UUID, payload: ReviewSubmitIn) -> ReviewRequestOut:
    """
    Human submits their decisions and any narration edits.

    Flips status to "resolved" and stamps resolved_at.  Can only be submitted
    once; re-submission on an already-resolved review → 403.
    """
    review = _get_or_404(rid)

    if not _can_write(request, review):
        raise ProblemError(404, "Review request not found", type_=TYPE_NOT_FOUND)

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
    expose_token = is_own or _token_ok(request, review)
    return ReviewRequestOut.model_validate(
        _detail_payload(review, is_owner=is_own, expose_token=expose_token)
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
