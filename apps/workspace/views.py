"""
Workspace API views.

Provides endpoints for starting workspace analysis, viewing session state,
editing skills, and publishing finalized skills.
"""
import json
import logging

from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.collections.models import Collection
from apps.common.anthropic_client import get_client
from apps.common.envelope import error_response, start_timing, success_response
from apps.evals.models import EvalCase, EvalSuite
from apps.skills.models import Skill

from . import prompts
from .engine import WorkspaceEngine
from .models import WorkspaceSession
from .stream import stream_re_proposal, stream_workspace_analysis

logger = logging.getLogger(__name__)


@require_POST
def start_workspace(request, collection_id):
    """
    Start a new workspace analysis session.

    POST /api/workspace/start/<collection_id>/

    Creates a session and returns a streaming SSE response with analysis results.
    The session ID is included in the X-Workspace-Session-Id header.
    """
    try:
        collection = Collection.objects.get(pk=collection_id)
    except Collection.DoesNotExist:
        start_timing()
        return JsonResponse(
            error_response("NOT_FOUND", "Collection not found."),
            status=404,
        )

    engine = WorkspaceEngine(collection)

    try:
        engine.build_analysis_prompt()
    except ValueError as e:
        start_timing()
        return JsonResponse(
            error_response("EMPTY_COLLECTION", str(e)),
            status=400,
        )

    session = engine.create_session()

    response = StreamingHttpResponse(
        stream_workspace_analysis(engine, session),
        content_type="text/event-stream",
    )
    response["X-Workspace-Session-Id"] = str(session.pk)
    response["Cache-Control"] = "no-cache"
    return response


@require_GET
def workspace_detail(request, session_id):
    """
    Get the current state of a workspace session.

    GET /api/workspace/<session_id>/
    """
    start_timing()

    try:
        session = WorkspaceSession.objects.get(pk=session_id)
    except WorkspaceSession.DoesNotExist:
        return JsonResponse(
            error_response("NOT_FOUND", "Workspace session not found."),
            status=404,
        )

    data = {
        "id": session.pk,
        "collection_id": session.collection_id,
        "status": session.status,
        "proposed_approach": session.proposed_approach,
        "proposed_eval_cases": session.proposed_eval_cases,
        "skill_draft": session.skill_draft,
        "edit_history": session.edit_history,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }

    return JsonResponse(success_response(data))


@require_http_methods(["PATCH"])
def edit_skill(request, session_id):
    """
    Edit the proposed skill in a workspace session.

    PATCH /api/workspace/<session_id>/edit/

    Body: {"edit": {...}, "structural": bool}

    If structural=true, returns SSE stream with re-proposal.
    If structural=false, applies the edit directly and returns JSON.
    """
    start_timing()

    try:
        session = WorkspaceSession.objects.get(pk=session_id)
    except WorkspaceSession.DoesNotExist:
        return JsonResponse(
            error_response("NOT_FOUND", "Workspace session not found."),
            status=404,
        )

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            error_response("INVALID_JSON", "Request body must be valid JSON."),
            status=400,
        )

    edit = body.get("edit", {})
    structural = body.get("structural", False)

    if structural:
        engine = WorkspaceEngine(session.collection)
        response = StreamingHttpResponse(
            stream_re_proposal(engine, session, edit),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        return response

    # Non-structural edit: apply directly
    session.status = "editing"
    session.edit_history.append(edit)

    # Merge the edit into the proposed approach
    if isinstance(edit, dict):
        session.proposed_approach.update(edit)

    session.save(update_fields=["status", "proposed_approach", "edit_history"])

    data = {
        "id": session.pk,
        "status": session.status,
        "proposed_approach": session.proposed_approach,
        "proposed_eval_cases": session.proposed_eval_cases,
    }

    return JsonResponse(success_response(data))


@require_POST
def publish_skill(request, session_id):
    """
    Publish the workspace session's proposed skill and eval cases.

    POST /api/workspace/<session_id>/publish/

    Creates a Skill, EvalSuite, and EvalCases from the session data.
    Returns the skill_id, name, and eval case count.
    """
    start_timing()

    try:
        session = WorkspaceSession.objects.get(pk=session_id)
    except WorkspaceSession.DoesNotExist:
        return JsonResponse(
            error_response("NOT_FOUND", "Workspace session not found."),
            status=404,
        )

    approach = session.proposed_approach
    if not approach:
        return JsonResponse(
            error_response("NO_PROPOSAL", "No proposed approach to publish."),
            status=400,
        )

    # Check if this is a revision of an existing skill
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}
    revise_skill_id = body.get("revise_skill_id")

    if revise_skill_id:
        # Revise existing skill — bump version, update definition
        try:
            skill = Skill.objects.get(pk=revise_skill_id)
        except Skill.DoesNotExist:
            return JsonResponse(
                error_response("NOT_FOUND", "Skill to revise not found."),
                status=404,
            )
        skill.definition = approach
        skill.description = approach.get("description", skill.description)
        skill.version += 1
        skill.workspace_session = session
        skill.save(update_fields=["definition", "description", "version", "workspace_session"])

        # Update eval cases if new ones proposed
        eval_cases = session.proposed_eval_cases or []
        if eval_cases:
            suite, _ = EvalSuite.objects.get_or_create(skill=skill)
            for case_data in eval_cases:
                EvalCase.objects.create(
                    suite=suite,
                    name=case_data.get("name", "Unnamed Case"),
                    input_data=case_data.get("input", {}),
                    expected_output=case_data.get("expected", {}),
                )
    else:
        # Create new skill
        skill = Skill.objects.create(
            name=approach.get("name", "Untitled Skill"),
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

    data = {
        "skill_id": skill.pk,
        "name": skill.name,
        "version": skill.version,
        "eval_count": len(session.proposed_eval_cases or []),
    }

    return JsonResponse(success_response(data), status=201)


@require_POST
def analyze_workspace(request, collection_id):
    """
    Start analysis synchronously. Returns session ID and results when done.

    POST /api/workspace/analyze/<collection_id>/

    Runs the full AI analysis in a single request (no streaming).
    Saves the proposal to the session and returns it as JSON.
    """
    start_timing()

    try:
        collection = Collection.objects.prefetch_related("sources").get(pk=collection_id)
    except Collection.DoesNotExist:
        return JsonResponse(
            error_response("NOT_FOUND", "Collection not found."),
            status=404,
        )

    engine = WorkspaceEngine(collection)

    try:
        prompt = engine.build_analysis_prompt()
    except ValueError as e:
        return JsonResponse(
            error_response("EMPTY_COLLECTION", str(e)),
            status=400,
        )

    session = engine.create_session()
    session.status = "analyzing"
    session.save(update_fields=["status"])

    try:
        from apps.common.anthropic_client import call_ai

        raw_text = call_ai(prompts.SYSTEM_PROMPT, prompt)
        result = engine.parse_ai_response(raw_text)

        session.proposed_approach = result.get("approach", {})
        session.proposed_eval_cases = result.get("eval_cases", [])
        session.skill_draft = result.get("approach", {})
        session.status = "proposed"
        session.save(
            update_fields=["status", "proposed_approach", "proposed_eval_cases", "skill_draft"]
        )

        return JsonResponse(
            success_response(
                {
                    "session_id": session.id,
                    "status": "proposed",
                    "approach": session.proposed_approach,
                    "eval_cases": session.proposed_eval_cases,
                }
            ),
            status=201,
        )
    except Exception as e:
        logger.exception("Error during synchronous workspace analysis")
        session.status = "created"
        session.save(update_fields=["status"])
        return JsonResponse(
            error_response("ANALYSIS_FAILED", str(e)),
            status=500,
        )
