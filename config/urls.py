"""
URL configuration for canopy-web project.
"""
from django.contrib import admin
from django.urls import include, path, re_path

from apps.api.api import api as api_v2
from apps.api.views import redoc_docs, scalar_docs
from apps.common import views_auth_e2e
from apps.walkthroughs.streaming import walkthrough_content as views_walkthrough_content
from config.views import csrf_view, health_check, spa_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("health/", health_check, name="health-check"),
    path("api/csrf/", csrf_view, name="csrf"),
    path("api/auth/e2e-login/", views_auth_e2e.e2e_login, name="auth-e2e-login"),
    path("api/debug/", include("apps.common.urls_debug")),
    path("w/<uuid:wid>/content", views_walkthrough_content, name="walkthrough-content"),
    path("api/", api_v2.urls),
    path("api/docs/", scalar_docs, name="api_docs_scalar"),
    path("api/redoc/", redoc_docs, name="api_docs_redoc"),
    # Catch-all: serve the SPA for any non-API route (last).
    re_path(r"^(?!api/|admin/|accounts/|health/|static/).*$", spa_view, name="spa"),
]
