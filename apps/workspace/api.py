"""Django Ninja v2 router for the workspace surface.

Provides 6 endpoints mirroring /api/workspace/:
  - GET  /                   list sessions
  - GET  /{session_id}/      session detail
  - PATCH /{session_id}/edit/  edit skill draft
  - POST /{session_id}/publish/  publish skill (201)
  - POST /start/{collection_id}/   SSE stream — initial analysis
  - POST /analyze/{collection_id}/ synchronous JSON — re-run analysis (201)

Only /start/ is SSE; /analyze/ is a synchronous JSON endpoint that blocks
until the AI responds and returns the parsed proposal directly (DRF parity).
"""
from __future__ import annotations

from django.http import HttpRequest, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja import Status

from apps.api.auth import session_auth
from apps.api.errors import TYPE_INTERNAL, TYPE_NOT_FOUND, TYPE_VALIDATION, ProblemError
from apps.api.pagination import Page, paginate
from apps.collections.models import Collection
from apps.common.anthropic_client import call_ai
from apps.evals.models import EvalCase, EvalSuite
from apps.skills.models import Skill
from apps.skills.schemas import SkillOut

from . import prompts
from .engine import WorkspaceEngine
from .models import WorkspaceSession
from .schemas import EditSkillIn, PublishSkillIn, WorkspaceAnalyzeOut, WorkspaceSessionListItemOut, WorkspaceSessionOut
from .stream import stream_re_proposal, stream_workspace_analysis

router = Router(auth=session_auth, tags=["workspace"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_to_list_item(s: WorkspaceSession) -> WorkspaceSessionListItemOut:
    return WorkspaceSessionListItemOut(
        id=s.pk,
        collection_id=s.collection_id,
        collection_name=s.collection.name if s.collection else None,
        status=s.status,  # type: ignore[arg-type]
        skill_name=(s.proposed_approach or {}).get("name") or None,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _session_to_out(s: WorkspaceSession) -> WorkspaceSessionOut:
    return WorkspaceSessionOut(
        id=s.pk,
        collection_id=s.collection_id,
        status=s.status,  # type: ignore[arg-type]
        proposed_approach=s.proposed_approach or {},
        proposed_eval_cases=s.proposed_eval_cases or [],
        skill_draft=s.skill_draft or {},
        edit_history=s.edit_history or [],
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _get_session_or_404(session_id: int) -> WorkspaceSession:
    try:
        return WorkspaceSession.objects.select_related("collection").get(pk=session_id)
    except WorkspaceSession.DoesNotExist:
        raise ProblemError(
            404,
            "Workspace session not found",
            type_=TYPE_NOT_FOUND,
            detail=f"No workspace session with id={session_id}.",
        )


def _skill_to_out(skill: Skill) -> SkillOut:
    from apps.skills.api import _skill_to_out as _base  # avoid circular at module level
    return _base(skill)


# ---------------------------------------------------------------------------
# Standard JSON endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response=Page[WorkspaceSessionListItemOut],
    summary="List workspace sessions",
)
def list_sessions(
    request: HttpRequest,
    status: str | None = None,
    collection: int | None = None,
    limit: int = 50,
) -> Page[WorkspaceSessionListItemOut]:
    """List sessions ordered by most-recently updated.

    Optional filters:
    - ``status``: one of created / analyzing / proposed / editing / testing / published
    - ``collection``: filter by collection primary key
    - ``limit``: max rows (default 50, clamped to 200)
    """
    limit = min(limit, 200)
    qs = WorkspaceSession.objects.select_related("collection").order_by("-updated_at")

    if status is not None:
        qs = qs.filter(status=status)
    if collection is not None:
        qs = qs.filter(collection_id=collection)

    items = [_session_to_list_item(s) for s in qs[:limit]]
    return paginate(items, offset=0, limit=max(limit, 1))


@router.get(
    "/{session_id}/",
    response=WorkspaceSessionOut,
    summary="Get workspace session detail",
)
def get_session(request: HttpRequest, session_id: int) -> WorkspaceSessionOut:
    """Return the full state of a workspace session. 404 → problem+json."""
    session = _get_session_or_404(session_id)
    return _session_to_out(session)


@router.patch(
    "/{session_id}/edit/",
    response=WorkspaceSessionOut,
    summary="Edit skill draft",
)
def edit_skill(
    request: HttpRequest,
    session_id: int,
    payload: EditSkillIn,
) -> WorkspaceSessionOut:
    """Update ``skill_draft`` and append the entry to ``edit_history``.

    The ``note`` field from the payload is stored as the edit history entry.
    """
    session = _get_session_or_404(session_id)

    session.skill_draft = payload.skill_draft
    entry: dict = {"skill_draft": payload.skill_draft}
    if payload.note is not None:
        entry["note"] = payload.note
    session.edit_history = list(session.edit_history or []) + [entry]
    session.status = "editing"
    session.save(update_fields=["skill_draft", "edit_history", "status"])

    return _session_to_out(session)


@router.post(
    "/{session_id}/publish/",
    response={201: SkillOut},
    summary="Publish workspace skill",
)
def publish_skill(
    request: HttpRequest,
    session_id: int,
    payload: PublishSkillIn,
) -> tuple[int, SkillOut]:
    """Publish the session's proposed approach as a Skill.

    Creates (or revises) a :class:`~apps.skills.models.Skill`, an
    :class:`~apps.evals.models.EvalSuite`, and one
    :class:`~apps.evals.models.EvalCase` per proposed eval case.

    Mirrors the logic in ``apps/workspace/views.py::publish_skill`` exactly.
    """
    session = _get_session_or_404(session_id)

    approach = session.proposed_approach
    if not approach:
        raise ProblemError(
            400,
            "No proposed approach to publish",
            detail="Run workspace analysis first to generate a proposal.",
        )

    name_override = payload.name

    # Create new skill
    skill_name = name_override or approach.get("name", "Untitled Skill")
    skill = Skill.objects.create(
        name=skill_name,
        description=approach.get("description", ""),
        definition=approach,
        workspace_session=session,
    )

    # Create eval suite and cases
    eval_suite = EvalSuite.objects.create(skill=skill)
    eval_cases = session.proposed_eval_cases or []
    for case_data in eval_cases:
        EvalCase.objects.create(
            suite=eval_suite,
            name=case_data.get("name", "Unnamed Case"),
            input_data=case_data.get("input", {}),
            expected_output=case_data.get("expected", {}),
        )

    # Update session status
    session.status = "published"
    session.save(update_fields=["status"])

    return Status(201, _skill_to_out(skill))


# ---------------------------------------------------------------------------
# SSE streaming endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/start/{collection_id}/",
    response=None,
    summary="Start workspace analysis (SSE stream)",
    description=(
        "Returns a text/event-stream of ``event:`` / ``data:`` SSE frames "
        "as the AI analyzes the collection sources. The stream emits "
        "incremental tokens followed by a terminal ``event: done`` frame. "
        "The ``X-Workspace-Session-Id`` response header carries the new "
        "session primary key."
    ),
)
def start_workspace(request: HttpRequest, collection_id: int) -> StreamingHttpResponse:
    """Kick off a fresh workspace analysis session; return SSE stream.

    Creates a :class:`~apps.workspace.models.WorkspaceSession` then streams
    AI analysis events in SSE format.  The byte stream is *identical* to what
    the legacy ``POST /api/workspace/start/<id>/`` endpoint produces —
    the frontend consumes the same ``event:`` / ``data:`` frames.
    """
    collection = get_object_or_404(Collection, pk=collection_id)

    engine = WorkspaceEngine(collection)
    try:
        engine.build_analysis_prompt()
    except ValueError:
        raise ProblemError(
            400,
            "Collection has no sources to analyze.",
            type_=TYPE_VALIDATION,
            detail="Add at least one source before starting a workspace session.",
        )

    session = engine.create_session()

    response = StreamingHttpResponse(
        stream_workspace_analysis(engine, session),
        content_type="text/event-stream",
    )
    response["X-Workspace-Session-Id"] = str(session.pk)
    response["Cache-Control"] = "no-cache"
    return response


@router.post(
    "/analyze/{collection_id}/",
    response={201: WorkspaceAnalyzeOut},
    summary="Run workspace analysis synchronously (JSON, no streaming)",
    description=(
        "Synchronously runs AI analysis for a collection and returns the parsed "
        "proposal as JSON (201). NOT an SSE stream. Mirrors the DRF baseline "
        "``POST /api/workspace/analyze/<id>/`` behaviour exactly."
    ),
)
def analyze_workspace(request: HttpRequest, collection_id: int):
    """Re-run workspace analysis; block until done and return JSON proposal.

    DRF-parity: creates a session, calls the AI synchronously, persists the
    parsed proposal, and returns 201 with :class:`~apps.workspace.schemas.WorkspaceAnalyzeOut`.
    """
    collection = (
        Collection.objects.prefetch_related("sources").filter(pk=collection_id).first()
    )
    if collection is None:
        raise ProblemError(404, "Collection not found", type_=TYPE_NOT_FOUND)

    engine = WorkspaceEngine(collection)
    try:
        prompt = engine.build_analysis_prompt()
    except ValueError as e:
        raise ProblemError(400, "Empty collection", type_=TYPE_VALIDATION, detail=str(e))

    session = engine.create_session()
    session.status = "analyzing"
    session.save(update_fields=["status"])

    try:
        raw_text = call_ai(prompts.SYSTEM_PROMPT, prompt)
        result = engine.parse_ai_response(raw_text)
        session.proposed_approach = result.get("approach", {})
        session.proposed_eval_cases = result.get("eval_cases", [])
        session.skill_draft = result.get("approach", {})
        session.status = "proposed"
        session.save(
            update_fields=[
                "status", "proposed_approach", "proposed_eval_cases", "skill_draft",
            ]
        )
        return 201, WorkspaceAnalyzeOut(
            session_id=session.id,
            status="proposed",
            approach=session.proposed_approach,
            eval_cases=session.proposed_eval_cases,
        )
    except Exception as e:
        session.status = "created"
        session.save(update_fields=["status"])
        raise ProblemError(500, "Analysis failed", type_=TYPE_INTERNAL, detail=str(e))
