"""
URL configuration for canopy-web project.
"""
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from apps.api.api import api as api_v2
from apps.api.views import redoc_docs, scalar_docs
from apps.tokens.cli_authorize_views import cli_authorize as views_cli_authorize
from apps.walkthroughs.streaming import walkthrough_content as views_walkthrough_content
from config.views import csrf_view, health_check, spa_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("health/", health_check, name="health-check"),
    path("api/csrf/", csrf_view, name="csrf"),
    path("api/debug/", include("apps.common.urls_debug")),
    path("auth/cli/authorize/", views_cli_authorize, name="cli_authorize"),
    path("walkthrough/<uuid:wid>/content", views_walkthrough_content, name="walkthrough-content"),
    # Back-compat: the pre-reclaim stream URL is baked into already-rendered
    # artifacts (DDD decks, review embeds). Redirect, don't fall to the SPA.
    path(
        "w/<uuid:wid>/content",
        RedirectView.as_view(pattern_name="walkthrough-content", query_string=True),
        name="walkthrough-content-legacy",
    ),
    path("api/", api_v2.urls),
    path("api/docs/", scalar_docs, name="api_docs_scalar"),
    path("api/redoc/", redoc_docs, name="api_docs_redoc"),
    # Catch-all: serve the SPA for any non-API route (last).
    re_path(r"^(?!api/|admin/|accounts/|health/|static/|auth/).*$", spa_view, name="spa"),
]
