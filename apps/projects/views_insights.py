from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.common.envelope import error_response, start_timing, success_response

from .models import ProjectContext
from .serializers import InsightSerializer


@api_view(["GET"])
def insights_list(request):
    start_timing()
    insights = ProjectContext.objects.filter(
        context_type="insight"
    ).select_related("project").order_by("-created_at")

    category = request.query_params.get("category")
    if category:
        insights = insights.filter(content__startswith=f"[{category}]")

    limit = int(request.query_params.get("limit", 20))
    limit = min(limit, 100)

    serializer = InsightSerializer(insights[:limit], many=True)
    return Response(success_response(serializer.data))


@api_view(["DELETE"])
def insight_dismiss(request, pk):
    start_timing()
    try:
        insight = ProjectContext.objects.get(pk=pk, context_type="insight")
    except ProjectContext.DoesNotExist:
        return Response(
            error_response("NOT_FOUND", "Insight not found."),
            status=status.HTTP_404_NOT_FOUND,
        )
    insight.delete()
    return Response(success_response({"dismissed": pk}))
