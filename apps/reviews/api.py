"""Django Ninja v2 router for the reviews surface.

Three endpoints:
  POST   /api/reviews/            — create a review_request (orchestrator → server)
  GET    /api/reviews/<id>/       — poll for status (orchestrator) / show to human
  POST   /api/reviews/<id>/submit/ — human submits decisions + narration edits

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

from .models import ReviewRequest
from .schemas import ReviewCreateIn, ReviewCreateOut, ReviewRequestOut, ReviewSubmitIn

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
        "request_json": review.request_json,
        "response_json": review.response_json,
        # share_token exposed to owner OR link-token holders (they demonstrably
        # have it and need it to re-poll / re-submit).
        "share_token": review.share_token if expose_token else None,
        "is_owner": is_owner,
        "created_at": review.created_at,
        "resolved_at": review.resolved_at,
    }


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

    review = ReviewRequest.objects.create(
        run_id=run_id,
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
