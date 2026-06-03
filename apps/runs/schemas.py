"""Pydantic schemas for the /api/ddd surface (read-only run aggregation)."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from apps.common.schemas import StrictModel
from apps.walkthroughs.schemas import WalkthroughKind, WalkthroughLink


class NarrativeListItemOut(StrictModel):
    slug: str
    title: str | None = None
    phase: str | None = None
    project_slug: str | None = None
    run_count: int = 0
    latest_at: dt.datetime | None = None
    has_video: bool = False
    has_deck: bool = False
    has_narrative: bool = False


class NarrativeRunOut(StrictModel):
    run_id: str
    created_at: dt.datetime | None = None
    latest_at: dt.datetime | None = None
    status: str | None = None
    gate: str | None = None
    scene_count: int = 0
    has_video: bool = False
    has_deck: bool = False


class NarrativeVersionOut(StrictModel):
    version: int | None = None
    review_id: str | None = None
    title: str | None = None
    story: str | None = None
    created_at: dt.datetime | None = None
    gate: str | None = None
    status: str | None = None
    runs: list[NarrativeRunOut] = []


class NarrativeStoryOut(StrictModel):
    """The current narrative version, for the narrative header + edit link."""

    review_id: str | None = None
    version: int | None = None
    title: str | None = None
    story: str | None = None


class NarrativeDetailOut(StrictModel):
    slug: str
    title: str | None = None
    story: str | None = None
    phase: str | None = None
    project_slug: str | None = None
    current_version: NarrativeStoryOut | None = None
    versions: list[NarrativeVersionOut] = []


class RunArtifactOut(StrictModel):
    id: uuid.UUID
    title: str
    kind: WalkthroughKind
    role: str | None = None
    content_url: str
    viewer_url: str
    duration_sec: int | None = None


class RunArtifactRefOut(StrictModel):
    id: uuid.UUID
    title: str
    kind: WalkthroughKind
    role: str | None = None
    created_at: dt.datetime
    viewer_url: str


class RunNarrativeOut(StrictModel):
    review_id: str | None = None
    version: int | None = None
    run_id: str
    gate: str
    title: str | None = None
    story: str | None = None
    # Sub-shapes live inside ReviewRequest.request_json; kept loosely typed.
    narration: list[dict[str, Any]] = []
    personas: dict[str, Any] = {}
    why_brief: dict[str, Any] | None = None


class PreviousRunOut(StrictModel):
    run_id: str
    latest_at: dt.datetime | None = None


class RunPackageOut(StrictModel):
    run_id: str
    narrative_slug: str
    created_at: dt.datetime | None = None
    latest_at: dt.datetime | None = None
    phase: str | None = None
    video: RunArtifactOut | None = None
    deck: RunArtifactOut | None = None
    narrative: RunNarrativeOut | None = None
    links: list[WalkthroughLink] = []
    all_artifacts: list[RunArtifactRefOut] = []
    previous_runs: list[PreviousRunOut] = []
