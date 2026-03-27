from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.common.envelope import error_response, start_timing, success_response

from .adapters import get_adapter
from .models import Skill
from .serializers import SkillSerializer


@api_view(["GET"])
def skill_list(request):
    start_timing()

    sort = request.query_params.get("sort", "-created_at")
    allowed_sort_fields = {
        "name", "-name",
        "created_at", "-created_at",
        "updated_at", "-updated_at",
        "usage_count", "-usage_count",
        "version", "-version",
    }
    if sort not in allowed_sort_fields:
        sort = "-created_at"

    skills = Skill.objects.all().order_by(sort)
    serializer = SkillSerializer(skills, many=True)
    return Response(success_response(serializer.data))


@api_view(["GET"])
def skill_detail(request, pk):
    start_timing()

    try:
        skill = Skill.objects.get(pk=pk)
    except Skill.DoesNotExist:
        return Response(
            error_response("NOT_FOUND", "Skill not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = SkillSerializer(skill)
    return Response(success_response(serializer.data))


@api_view(["POST"])
def generate_adapter(request, pk):
    start_timing()

    try:
        skill = Skill.objects.get(pk=pk)
    except Skill.DoesNotExist:
        return Response(
            error_response("NOT_FOUND", "Skill not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    runtime = request.data.get("runtime")
    if not runtime:
        return Response(
            error_response("VALIDATION_ERROR", "runtime field is required."),
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        adapter = get_adapter(runtime)
    except ValueError as e:
        return Response(
            error_response("INVALID_RUNTIME", str(e)),
            status=status.HTTP_400_BAD_REQUEST,
        )

    result = adapter.generate(skill.definition)
    return Response(success_response(result))
