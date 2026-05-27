"""Django Ninja v2 router for the skills surface."""
from __future__ import annotations

import json

from django.http import HttpRequest
from ninja import Router

from apps.api.auth import session_auth
from apps.api.errors import TYPE_NOT_FOUND, ProblemError
from apps.api.pagination import Page, paginate

from .adapters import get_adapter
from .models import Skill
from .schemas import AdapterIn, AdapterOut, SkillOut

router = Router(auth=session_auth, tags=["skills"])


def _skill_eval_fields(skill: Skill) -> dict:
    """Derive eval_score, eval_trend, last_eval_at from the latest EvalRuns.

    Mirrors SkillSerializer.get_eval_score / get_eval_trend / get_last_eval_at
    without touching the DRF serializer.
    """
    eval_score = None
    eval_trend = None
    last_eval_at = None

    try:
        runs_qs = skill.eval_suite.runs.order_by("-created_at")
        scores = list(runs_qs.values_list("overall_score", "created_at")[:2])
        if scores:
            eval_score = scores[0][0]
            last_eval_at = scores[0][1]
            if len(scores) == 2:
                current, previous = scores[0][0], scores[1][0]
                if current is not None and previous is not None:
                    if current > previous:
                        eval_trend = "improving"
                    elif current < previous:
                        eval_trend = "declining"
                    else:
                        eval_trend = "stable"
    except Exception:
        pass

    return {
        "eval_score": eval_score,
        "eval_trend": eval_trend,
        "last_eval_at": last_eval_at,
    }


def _skill_to_out(skill: Skill) -> SkillOut:
    """Build a SkillOut from a Skill ORM instance."""
    data = {
        "id": skill.pk,
        "name": skill.name,
        "description": skill.description,
        "definition": skill.definition,
        "version": skill.version,
        "usage_count": skill.usage_count,
        "created_at": skill.created_at,
        "updated_at": skill.updated_at,
    }
    data.update(_skill_eval_fields(skill))
    return SkillOut.model_validate(data)


@router.get("/", response=Page[SkillOut], summary="List skills")
def list_skills(
    request: HttpRequest,
    offset: int = 0,
    limit: int = 100,
) -> Page[SkillOut]:
    skills = list(Skill.objects.all().order_by("-created_at"))
    items = [_skill_to_out(s) for s in skills]
    return paginate(items, offset=offset, limit=limit)


@router.get("/{pk}/", response=SkillOut, summary="Get skill detail")
def get_skill(request: HttpRequest, pk: int) -> SkillOut:
    skill = Skill.objects.filter(pk=pk).first()
    if skill is None:
        raise ProblemError(404, "Skill not found", type_=TYPE_NOT_FOUND)
    return _skill_to_out(skill)


@router.post("/{pk}/adapter/", response=AdapterOut, summary="Generate runtime adapter")
def generate_adapter(request: HttpRequest, pk: int, payload: AdapterIn) -> AdapterOut:
    skill = Skill.objects.filter(pk=pk).first()
    if skill is None:
        raise ProblemError(404, "Skill not found", type_=TYPE_NOT_FOUND)

    # AdapterIn already validated runtime via Literal — no unknown-runtime path here.
    adapter = get_adapter(payload.runtime)
    result = adapter.generate(skill.definition)
    content = json.dumps(result)
    return AdapterOut(runtime=payload.runtime, content=content, format="json")
