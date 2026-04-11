from django.db.models import Prefetch
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.common.envelope import error_response, start_timing, success_response

from .models import Project, ProjectContext, ProjectGuide
from .serializers import (
    ProjectContextCreateSerializer,
    ProjectContextSerializer,
    ProjectCreateSerializer,
    ProjectDetailSerializer,
    ProjectGuideSerializer,
    ProjectListSerializer,
)


def _get_project_or_404(slug):
    try:
        return Project.objects.get(slug=slug)
    except Project.DoesNotExist:
        return None


@api_view(["GET", "POST"])
def project_list(request):
    start_timing()

    if request.method == "GET":
        projects = Project.objects.prefetch_related(
            Prefetch(
                "contexts",
                queryset=ProjectContext.objects.order_by("-created_at"),
                to_attr="_prefetched_contexts",
            )
        ).all()
        serializer = ProjectListSerializer(projects, many=True)
        return Response(success_response(serializer.data))

    serializer = ProjectCreateSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(
            success_response(serializer.data), status=status.HTTP_201_CREATED
        )
    return Response(
        error_response("VALIDATION_ERROR", serializer.errors),
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["GET", "PATCH", "DELETE"])
def project_detail(request, slug):
    start_timing()

    project = _get_project_or_404(slug)
    if project is None:
        return Response(
            error_response("NOT_FOUND", "Project not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        serializer = ProjectDetailSerializer(project)
        return Response(success_response(serializer.data))

    if request.method == "PATCH":
        serializer = ProjectCreateSerializer(project, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(success_response(serializer.data))
        return Response(
            error_response("VALIDATION_ERROR", serializer.errors),
            status=status.HTTP_400_BAD_REQUEST,
        )

    # DELETE
    project.delete()
    return Response(success_response({"deleted": slug}))


@api_view(["GET", "POST"])
def project_context(request, slug):
    start_timing()

    project = _get_project_or_404(slug)
    if project is None:
        return Response(
            error_response("NOT_FOUND", "Project not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        contexts = project.contexts.all()
        context_type = request.query_params.get("type")
        if context_type:
            contexts = contexts.filter(context_type=context_type)
        serializer = ProjectContextSerializer(contexts, many=True)
        return Response(success_response(serializer.data))

    serializer = ProjectContextCreateSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(project=project)
        return Response(
            success_response(ProjectContextSerializer(serializer.instance).data),
            status=status.HTTP_201_CREATED,
        )
    return Response(
        error_response("VALIDATION_ERROR", serializer.errors),
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["GET"])
def project_context_latest(request, slug):
    start_timing()

    project = _get_project_or_404(slug)
    if project is None:
        return Response(
            error_response("NOT_FOUND", "Project not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    result = {}
    for ctx in project.contexts.order_by("-created_at"):
        if ctx.context_type not in result:
            result[ctx.context_type] = {
                "content": ctx.content,
                "source": ctx.source,
                "created_at": ctx.created_at.isoformat(),
            }
    return Response(success_response(result))


@api_view(["GET", "PUT", "DELETE"])
def project_guide(request, slug):
    start_timing()

    project = _get_project_or_404(slug)
    if project is None:
        return Response(
            error_response("NOT_FOUND", "Project not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        try:
            guide = project.guide
        except ProjectGuide.DoesNotExist:
            return Response(
                error_response("NOT_FOUND", "No guide for this project."),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(success_response(ProjectGuideSerializer(guide).data))

    if request.method == "PUT":
        content = request.data.get("content", "")
        source = request.data.get("source", "")
        if not content or not content.strip():
            return Response(
                error_response("VALIDATION_ERROR", "Guide content cannot be empty."),
                status=status.HTTP_400_BAD_REQUEST,
            )
        guide, _ = ProjectGuide.objects.update_or_create(
            project=project,
            defaults={"content": content, "source": source},
        )
        return Response(success_response(ProjectGuideSerializer(guide).data))

    # DELETE
    try:
        project.guide.delete()
    except ProjectGuide.DoesNotExist:
        pass
    return Response(success_response({"deleted": slug}))


@api_view(["POST"])
def seed_projects(request):
    start_timing()

    projects_data = request.data.get("projects", [])
    created = 0
    skipped = 0

    for item in projects_data:
        slug = item.get("slug")
        if not slug:
            continue
        if Project.objects.filter(slug=slug).exists():
            skipped += 1
            continue
        Project.objects.create(
            name=item.get("name", slug),
            slug=slug,
            repo_url=item.get("repo_url", ""),
            deploy_url=item.get("deploy_url", ""),
            visibility=item.get("visibility", "public"),
            status=item.get("status", "active"),
        )
        created += 1

    return Response(
        success_response({"created": created, "skipped": skipped}),
        status=status.HTTP_201_CREATED,
    )
