"""
URL configuration for canopy-web project.
"""
from django.contrib import admin
from django.urls import include, path

from config.views import health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health-check"),
    path("api/collections/", include("apps.collections.urls")),
    path("api/workspace/", include("apps.workspace.urls")),
    path("api/skills/", include("apps.skills.urls")),
    path("api/evals/", include("apps.evals.urls")),
]
