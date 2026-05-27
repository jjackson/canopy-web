"""Django Ninja v2 router for the evals surface."""
from __future__ import annotations

from django.http import HttpRequest
from ninja import Router

from apps.api.auth import session_auth
from apps.api.errors import TYPE_NOT_FOUND, ProblemError
from apps.api.pagination import Page, paginate
from apps.skills.models import Skill

from .models import EvalCase, EvalRun, EvalSuite
from .schemas import (
    EvalCaseCreateIn,
    EvalCaseOut,
    EvalCasePatchIn,
    EvalRunIn,
    EvalRunOut,
    EvalSuiteOut,
)

router = Router(auth=session_auth, tags=["evals"])


def _suite_to_out(suite: EvalSuite) -> EvalSuiteOut:
    cases = [
        EvalCaseOut(
            id=c.pk,
            name=c.name,
            input_data=c.input_data,
            expected_output=c.expected_output,
            source_excerpt=c.source_excerpt,
            created_at=c.created_at,
        )
        for c in suite.cases.order_by("created_at")
    ]
    runs = [
        _run_to_out(r)
        for r in suite.runs.order_by("-created_at")
    ]
    return EvalSuiteOut(
        id=suite.pk,
        cases=cases,
        runs=runs,
        created_at=suite.created_at,
    )


def _run_to_out(run: EvalRun) -> EvalRunOut:
    # EvalRunOut.runtime is Literal["web","claude_code","open_claw"]; runner stores
    # elapsed string like "1.23s" in the runtime field (legacy). Coerce unknowns to "web".
    valid_runtimes = {"web", "claude_code", "open_claw"}
    runtime = run.runtime if run.runtime in valid_runtimes else "web"
    return EvalRunOut(
        id=run.pk,
        status=run.status,
        results=run.results,
        overall_score=run.overall_score,
        runtime=runtime,
        created_at=run.created_at,
    )


def _get_skill_or_404(skill_id: int) -> Skill:
    skill = Skill.objects.filter(pk=skill_id).first()
    if skill is None:
        raise ProblemError(404, "Skill not found", type_=TYPE_NOT_FOUND)
    return skill


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{skill_id}/", response=EvalSuiteOut, summary="Eval suite detail")
def eval_suite_detail(request: HttpRequest, skill_id: int) -> EvalSuiteOut:
    """Return the eval suite for a skill. Auto-creates the suite on first read."""
    skill = _get_skill_or_404(skill_id)
    suite, _created = EvalSuite.objects.get_or_create(skill=skill)
    return _suite_to_out(suite)


@router.post(
    "/{skill_id}/run/",
    response={200: EvalRunOut, 400: dict},
    summary="Run eval suite",
)
def run_eval(request: HttpRequest, skill_id: int, payload: EvalRunIn) -> tuple[int, EvalRunOut]:
    """Execute the eval suite and return the run result."""
    skill = _get_skill_or_404(skill_id)
    suite, _created = EvalSuite.objects.get_or_create(skill=skill)

    if not suite.cases.exists():
        raise ProblemError(
            400,
            "Eval suite has no cases to run.",
            detail="Add at least one eval case before running.",
        )

    from .runner import EvalRunner

    runner = EvalRunner(skill)
    run = runner.execute(suite)
    return 200, _run_to_out(run)


@router.get(
    "/{skill_id}/history/",
    response=Page[EvalRunOut],
    summary="Eval run history",
)
def eval_history(
    request: HttpRequest,
    skill_id: int,
    offset: int = 0,
    limit: int = 100,
) -> Page[EvalRunOut]:
    """Return paginated eval runs for a skill, ordered newest first."""
    skill = _get_skill_or_404(skill_id)
    suite, _created = EvalSuite.objects.get_or_create(skill=skill)
    runs = [_run_to_out(r) for r in suite.runs.order_by("-created_at")]
    return paginate(runs, offset=offset, limit=limit)


@router.post(
    "/{skill_id}/cases/",
    response={201: EvalCaseOut},
    summary="Create eval case",
)
def create_eval_case(
    request: HttpRequest, skill_id: int, payload: EvalCaseCreateIn
) -> tuple[int, EvalCaseOut]:
    """Add a new eval case to the suite. Auto-creates the suite if missing."""
    skill = _get_skill_or_404(skill_id)
    suite, _created = EvalSuite.objects.get_or_create(skill=skill)
    case = EvalCase.objects.create(
        suite=suite,
        name=payload.name,
        input_data=payload.input_data,
        expected_output=payload.expected_output,
        source_excerpt=payload.source_excerpt,
    )
    out = EvalCaseOut(
        id=case.pk,
        name=case.name,
        input_data=case.input_data,
        expected_output=case.expected_output,
        source_excerpt=case.source_excerpt,
        created_at=case.created_at,
    )
    return 201, out


@router.patch(
    "/{skill_id}/cases/{case_id}/",
    response=EvalCaseOut,
    summary="Update eval case",
)
def patch_eval_case(
    request: HttpRequest, skill_id: int, case_id: int, payload: EvalCasePatchIn
) -> EvalCaseOut:
    """Partial update of an eval case."""
    case = (
        EvalCase.objects.select_related("suite__skill")
        .filter(pk=case_id, suite__skill_id=skill_id)
        .first()
    )
    if case is None:
        raise ProblemError(404, "Eval case not found", type_=TYPE_NOT_FOUND)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(case, field, value)
    if updates:
        case.save(update_fields=list(updates.keys()))

    return EvalCaseOut(
        id=case.pk,
        name=case.name,
        input_data=case.input_data,
        expected_output=case.expected_output,
        source_excerpt=case.source_excerpt,
        created_at=case.created_at,
    )


@router.delete(
    "/{skill_id}/cases/{case_id}/",
    response={204: None},
    summary="Delete eval case",
)
def delete_eval_case(
    request: HttpRequest, skill_id: int, case_id: int
) -> tuple[int, None]:
    """Delete an eval case."""
    case = (
        EvalCase.objects.select_related("suite__skill")
        .filter(pk=case_id, suite__skill_id=skill_id)
        .first()
    )
    if case is None:
        raise ProblemError(404, "Eval case not found", type_=TYPE_NOT_FOUND)

    case.delete()
    return 204, None
