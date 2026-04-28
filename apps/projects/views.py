from django.db.models import Prefetch
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.common.envelope import error_response, start_timing, success_response

from .models import Project, ProjectAction, ProjectContext, ProjectGuide
from .serializers import (
    ProjectActionCreateSerializer,
    ProjectActionSerializer,
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


@api_view(["GET"])
def project_slugs(request):
    """Slim list of curated project slugs, intended for machine callers.

    Returns slug + name + status + visibility for active projects only —
    no contexts, actions, or guides. This is the canonical list of
    projects on canopy-web that the workbench bearer token can read.
    """
    start_timing()
    projects = (
        Project.objects.filter(status="active")
        .order_by("slug")
        .values("slug", "name", "status", "visibility")
    )
    return Response(success_response(list(projects)))


@api_view(["GET", "POST"])
def project_list(request):
    start_timing()

    if request.method == "GET":
        projects = Project.objects.prefetch_related(
            Prefetch(
                "contexts",
                queryset=ProjectContext.objects.order_by("-created_at"),
                to_attr="_prefetched_contexts",
            ),
            Prefetch(
                "actions",
                queryset=ProjectAction.objects.order_by("-started_at"),
                to_attr="_prefetched_actions",
            ),
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


@api_view(["GET", "POST"])
def project_actions(request, slug):
    start_timing()

    project = _get_project_or_404(slug)
    if project is None:
        return Response(
            error_response("NOT_FOUND", "Project not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        actions = project.actions.all()
        skill = request.query_params.get("skill")
        if skill:
            actions = actions.filter(skill_name=skill)
        serializer = ProjectActionSerializer(actions[:50], many=True)
        return Response(success_response(serializer.data))

    serializer = ProjectActionCreateSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(project=project)
        return Response(
            success_response(ProjectActionSerializer(serializer.instance).data),
            status=status.HTTP_201_CREATED,
        )
    return Response(
        error_response("VALIDATION_ERROR", serializer.errors),
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["GET"])
def project_actions_summary(request, slug):
    """Returns latest action per skill for a project."""
    start_timing()

    project = _get_project_or_404(slug)
    if project is None:
        return Response(
            error_response("NOT_FOUND", "Project not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    result = {}
    for action in project.actions.order_by("-started_at"):
        if action.skill_name not in result:
            result[action.skill_name] = {
                "status": action.status,
                "started_at": action.started_at.isoformat(),
                "completed_at": action.completed_at.isoformat() if action.completed_at else None,
                "duration_ms": action.duration_ms,
            }
    return Response(success_response(result))


@api_view(["POST"])
def batch_context(request):
    """
    Create context entries across multiple projects in one request.

    POST /api/projects/batch-context/
    Body: {"updates": {slug: [{context_type, content, source}, ...]}}

    Returns per-slug results with counts and errors. Partial success is allowed —
    valid slugs get their entries created even if other slugs fail.
    """
    start_timing()

    updates = request.data.get("updates")
    if not isinstance(updates, dict):
        return Response(
            error_response(
                "VALIDATION_ERROR",
                "'updates' must be an object mapping slug to a list of context entries.",
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )

    results = {}
    total_created = 0
    total_errors = 0

    for slug, entries in updates.items():
        if not isinstance(entries, list):
            results[slug] = {
                "created": 0,
                "errors": [{"code": "VALIDATION_ERROR", "message": "Entries must be a list."}],
            }
            total_errors += 1
            continue

        project = _get_project_or_404(slug)
        if project is None:
            results[slug] = {
                "created": 0,
                "errors": [{"code": "NOT_FOUND", "message": "Project not found."}],
            }
            total_errors += len(entries)
            continue

        created = 0
        errors = []
        for entry in entries:
            serializer = ProjectContextCreateSerializer(data=entry)
            if serializer.is_valid():
                serializer.save(project=project)
                created += 1
            else:
                errors.append({"code": "VALIDATION_ERROR", "message": serializer.errors})
                total_errors += 1

        results[slug] = {"created": created, "errors": errors}
        total_created += created

    return Response(
        success_response({
            "results": results,
            "total_created": total_created,
            "total_errors": total_errors,
        }),
        status=status.HTTP_201_CREATED if total_created else status.HTTP_200_OK,
    )


@api_view(["POST"])
def batch_actions(request):
    """
    Create action entries across multiple projects in one request.

    POST /api/projects/batch-actions/
    Body: {"updates": {slug: [{skill_name, status, started_at, ...}, ...]}}

    Returns per-slug results with counts and errors. Partial success is allowed.
    """
    start_timing()

    updates = request.data.get("updates")
    if not isinstance(updates, dict):
        return Response(
            error_response(
                "VALIDATION_ERROR",
                "'updates' must be an object mapping slug to a list of action entries.",
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )

    results = {}
    total_created = 0
    total_errors = 0

    for slug, entries in updates.items():
        if not isinstance(entries, list):
            results[slug] = {
                "created": 0,
                "errors": [{"code": "VALIDATION_ERROR", "message": "Entries must be a list."}],
            }
            total_errors += 1
            continue

        project = _get_project_or_404(slug)
        if project is None:
            results[slug] = {
                "created": 0,
                "errors": [{"code": "NOT_FOUND", "message": "Project not found."}],
            }
            total_errors += len(entries)
            continue

        created = 0
        errors = []
        for entry in entries:
            serializer = ProjectActionCreateSerializer(data=entry)
            if serializer.is_valid():
                serializer.save(project=project)
                created += 1
            else:
                errors.append({"code": "VALIDATION_ERROR", "message": serializer.errors})
                total_errors += 1

        results[slug] = {"created": created, "errors": errors}
        total_created += created

    return Response(
        success_response({
            "results": results,
            "total_created": total_created,
            "total_errors": total_errors,
        }),
        status=status.HTTP_201_CREATED if total_created else status.HTTP_200_OK,
    )


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
