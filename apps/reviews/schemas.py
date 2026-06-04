"""Pydantic schemas for the /api/reviews/ surface."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from apps.common.schemas import StrictModel

ReviewStatus = Literal["pending", "resolved"]
ReviewVisibility = Literal["private", "link"]


class ReviewRequestOut(StrictModel):
    """Detail/list output for a review request."""

    id: uuid.UUID
    run_id: str
    # Narrative slug this review belongs to (explicit feature, else derived from
    # run_id) — lets the DDD shell highlight the right narrative on the editor.
    feature: str
    gate: str
    status: ReviewStatus
    visibility: ReviewVisibility
    request_json: dict[str, Any]
    response_json: dict[str, Any] | None = None
    share_token: str | None = None
    is_owner: bool
    created_at: dt.datetime
    resolved_at: dt.datetime | None = None


class ReviewListItemOut(StrictModel):
    """One row in the DDD-plans dashboard list (GET /api/reviews/)."""

    id: uuid.UUID
    run_id: str
    gate: str
    status: ReviewStatus
    visibility: ReviewVisibility
    # Derived from request_json for a scannable list — never the raw payload.
    feature: str
    title: str | None = None
    scene_count: int = 0
    created_at: dt.datetime
    resolved_at: dt.datetime | None = None
    # resolved_at when resolved, else created_at — the "last edit" the dashboard sorts by.
    last_activity_at: dt.datetime
    share_token: str | None = None
    is_owner: bool


class ReviewCreateIn(StrictModel):
    """Body of POST /api/reviews/: the inbound request_json plus optional meta."""

    # The full request_json payload from the canopy orchestrator.
    request_json: dict[str, Any]
    # Optional: link visibility so the review page is publicly shareable.
    visibility: ReviewVisibility = "link"


class ReviewSubmitIn(StrictModel):
    """Body of POST /api/reviews/<id>/submit/: the human's response."""

    response_json: dict[str, Any]


class ReviewCreateOut(StrictModel):
    """Slim response from POST /api/reviews/: just enough for the orchestrator to poll."""

    id: uuid.UUID
    url: str
    share_token: str
