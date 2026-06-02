"""Single NinjaAPI instance for the /api/ namespace.

All v2 routers register against this. Routers live in
`apps/<app>/api.py` and are imported below.
"""
from __future__ import annotations

import logging

from django.http import Http404, HttpRequest, HttpResponse
from ninja import NinjaAPI
from ninja.errors import AuthenticationError, HttpError, ValidationError

from .auth import session_auth
from .errors import (
    TYPE_AUTH,
    TYPE_INTERNAL,
    TYPE_NOT_FOUND,
    TYPE_VALIDATION,
    Problem,
    ProblemError,
)
from .renderers import OrjsonRenderer

logger = logging.getLogger(__name__)


api = NinjaAPI(
    title="canopy-web API",
    version="2.0.0",
    description=(
        "Pydantic-typed API surface for canopy-web. "
        "Replaces the legacy /api/ DRF endpoints. "
        "Errors are RFC 7807 application/problem+json."
    ),
    urls_namespace="api_v2",
    renderer=OrjsonRenderer(),
    docs_url=None,  # Scalar is mounted separately in config/urls.py
    openapi_url="/openapi.json",
)


def _problem_response(request: HttpRequest, problem: Problem) -> HttpResponse:
    body = problem.model_dump(exclude_none=True)
    response = HttpResponse(
        content=OrjsonRenderer().render(request, body, response_status=problem.status),
        status=problem.status,
        content_type="application/problem+json",
    )
    return response


@api.exception_handler(ProblemError)
def _on_problem_error(request: HttpRequest, exc: ProblemError) -> HttpResponse:
    problem = Problem(
        type=exc.problem_type,
        title=exc.problem_title,
        status=exc.status_code,
        detail=exc.problem_detail,
        instance=request.path,
        extras=exc.problem_extras,
    )
    return _problem_response(request, problem)


@api.exception_handler(ValidationError)
def _on_validation_error(request: HttpRequest, exc: ValidationError) -> HttpResponse:
    problem = Problem(
        type=TYPE_VALIDATION,
        title="Request validation failed",
        status=422,
        detail="One or more fields failed validation.",
        instance=request.path,
        extras={"errors": exc.errors},
    )
    return _problem_response(request, problem)


@api.exception_handler(AuthenticationError)
def _on_auth_error(request: HttpRequest, exc: AuthenticationError) -> HttpResponse:
    problem = Problem(
        type=TYPE_AUTH,
        title="Authentication required",
        status=401,
        detail="This endpoint requires an authenticated session.",
        instance=request.path,
    )
    return _problem_response(request, problem)


@api.exception_handler(HttpError)
def _on_http_error(request: HttpRequest, exc: HttpError) -> HttpResponse:
    """Bare HttpError (raised from handlers using ninja's shortcut) → problem+json."""
    problem = Problem(
        type="about:blank",
        title=exc.message if hasattr(exc, "message") else "HTTP error",
        status=exc.status_code,
        detail=str(exc) if str(exc) else None,
        instance=request.path,
    )
    return _problem_response(request, problem)


@api.exception_handler(Http404)
def _on_http404(request: HttpRequest, exc: Http404) -> HttpResponse:
    """Django Http404 (from get_object_or_404) → problem+json."""
    problem = Problem(
        type=TYPE_NOT_FOUND,
        title="Not found",
        status=404,
        detail=str(exc) if str(exc) else None,
        instance=request.path,
    )
    return _problem_response(request, problem)


@api.exception_handler(Exception)
def _on_unhandled(request: HttpRequest, exc: Exception) -> HttpResponse:
    logger.exception("Unhandled exception in v2 handler")
    problem = Problem(
        type=TYPE_INTERNAL,
        title="Internal server error",
        status=500,
        detail="An unexpected error occurred.",
        instance=request.path,
    )
    return _problem_response(request, problem)


@api.get("/_auth_smoke/", auth=session_auth, response={200: dict})
def _auth_smoke(request: HttpRequest) -> dict:
    """Internal smoke route — verifies session auth works."""
    return {"email": getattr(request.user, "email", "")}


from apps.collections.api import router as collections_router  # noqa: E402
from apps.common.api import ai_router, common_router, public_router  # noqa: E402
from apps.evals.api import router as evals_router  # noqa: E402
from apps.projects.api import insights_router  # noqa: E402
from apps.projects.api import router as projects_router  # noqa: E402
from apps.skills.api import router as skills_router  # noqa: E402
from apps.tokens.api import router as tokens_router  # noqa: E402
from apps.reviews.api import router as reviews_router  # noqa: E402
from apps.runs.api import router as runs_router  # noqa: E402
from apps.walkthroughs.api import router as walkthroughs_router  # noqa: E402
from apps.workspace.api import router as workspace_router  # noqa: E402

api.add_router("/projects", projects_router)
api.add_router("/insights", insights_router)
api.add_router("/collections", collections_router)
api.add_router("/skills", skills_router)
api.add_router("/evals", evals_router)
api.add_router("/workspace", workspace_router)
api.add_router("/ai", ai_router)
api.add_router("", common_router)
api.add_router("", public_router)
api.add_router("/walkthroughs", walkthroughs_router)
api.add_router("/tokens", tokens_router)
api.add_router("/reviews", reviews_router)
api.add_router("/ddd", runs_router)
