from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.common.envelope import error_response, start_timing, success_response
from apps.skills.models import Skill

from .models import EvalCase, EvalSuite
from .runner import EvalRunner
from .serializers import EvalCaseSerializer, EvalRunSerializer, EvalSuiteSerializer


@api_view(["GET"])
def eval_suite_detail(request, skill_id):
    """GET — Returns suite with cases and runs."""
    start_timing()

    try:
        skill = Skill.objects.get(pk=skill_id)
    except Skill.DoesNotExist:
        return Response(
            error_response("NOT_FOUND", "Skill not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    suite, _created = EvalSuite.objects.get_or_create(skill=skill)
    serializer = EvalSuiteSerializer(suite)
    return Response(success_response(serializer.data))


@api_view(["POST"])
def run_eval(request, skill_id):
    """POST — Executes eval suite, returns run results."""
    start_timing()

    try:
        skill = Skill.objects.get(pk=skill_id)
    except Skill.DoesNotExist:
        return Response(
            error_response("NOT_FOUND", "Skill not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    suite, _created = EvalSuite.objects.get_or_create(skill=skill)

    if not suite.cases.exists():
        return Response(
            error_response("NO_CASES", "Eval suite has no cases to run."),
            status=status.HTTP_400_BAD_REQUEST,
        )

    runner = EvalRunner(skill)
    run = runner.execute(suite)
    serializer = EvalRunSerializer(run)
    return Response(success_response(serializer.data))


@api_view(["GET"])
def eval_history(request, skill_id):
    """GET — Returns all runs ordered by date."""
    start_timing()

    try:
        skill = Skill.objects.get(pk=skill_id)
    except Skill.DoesNotExist:
        return Response(
            error_response("NOT_FOUND", "Skill not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    suite, _created = EvalSuite.objects.get_or_create(skill=skill)
    runs = suite.runs.order_by("-created_at")
    serializer = EvalRunSerializer(runs, many=True)
    return Response(success_response(serializer.data))


@api_view(["POST"])
def propose_eval_case(request, skill_id):
    """POST — Adds a new eval case. Body: {name, input_data, expected_output, source_excerpt?}"""
    start_timing()

    try:
        skill = Skill.objects.get(pk=skill_id)
    except Skill.DoesNotExist:
        return Response(
            error_response("NOT_FOUND", "Skill not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    name = request.data.get("name")
    input_data = request.data.get("input_data")
    expected_output = request.data.get("expected_output")

    if not name or input_data is None or expected_output is None:
        return Response(
            error_response("VALIDATION_ERROR", "name, input_data, and expected_output are required."),
            status=status.HTTP_400_BAD_REQUEST,
        )

    suite, _created = EvalSuite.objects.get_or_create(skill=skill)
    case = EvalCase.objects.create(
        suite=suite,
        name=name,
        input_data=input_data,
        expected_output=expected_output,
        source_excerpt=request.data.get("source_excerpt", ""),
    )
    serializer = EvalCaseSerializer(case)
    return Response(success_response(serializer.data), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
def eval_case_detail(request, skill_id, case_id):
    """PATCH/DELETE — Edit or delete an eval case."""
    start_timing()

    try:
        case = EvalCase.objects.select_related("suite__skill").get(
            pk=case_id, suite__skill_id=skill_id
        )
    except EvalCase.DoesNotExist:
        return Response(
            error_response("NOT_FOUND", "Eval case not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "DELETE":
        case.delete()
        return Response(success_response({"deleted": True}))

    # PATCH
    if "name" in request.data:
        case.name = request.data["name"]
    if "input_data" in request.data:
        case.input_data = request.data["input_data"]
    if "expected_output" in request.data:
        case.expected_output = request.data["expected_output"]
    case.save()

    serializer = EvalCaseSerializer(case)
    return Response(success_response(serializer.data))
