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
    gate: str
    status: ReviewStatus
    visibility: ReviewVisibility
    request_json: dict[str, Any]
    response_json: dict[str, Any] | None = None
    share_token: str | None = None
    is_owner: bool
    created_at: dt.datetime
    resolved_at: dt.datetime | None = None


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
