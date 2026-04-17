"""
URL configuration for canopy-web project.
"""
from django.contrib import admin
from django.urls import include, path, re_path

from apps.projects import views_insights
from config.views import csrf_view, health_check, me_view, spa_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("health/", health_check, name="health-check"),
    path("api/me/", me_view, name="me"),
    path("api/csrf/", csrf_view, name="csrf"),
    path("api/collections/", include("apps.collections.urls")),
    path("api/workspace/", include("apps.workspace.urls")),
    path("api/skills/", include("apps.skills.urls")),
    path("api/evals/", include("apps.evals.urls")),
    path("api/insights/", views_insights.insights_list, name="insights-list"),
    path("api/insights/clear/", views_insights.insights_clear, name="insights-clear"),
    path("api/insights/<int:pk>/", views_insights.insight_dismiss, name="insight-dismiss"),
    path("api/projects/", include("apps.projects.urls")),
    path("api/ai/", include("apps.common.urls")),
    path("api/debug/", include("apps.common.urls_debug")),
    # Catch-all: serve the SPA for any non-API route (last).
    re_path(r"^(?!api/|admin/|accounts/|health/|static/).*$", spa_view, name="spa"),
]
