from django.urls import path
from . import views

urlpatterns = [
    path("", views.project_list, name="project-list"),
    path("seed/", views.seed_projects, name="seed-projects"),
    path("slugs/", views.project_slugs, name="project-slugs"),
    path("batch-context/", views.batch_context, name="batch-context"),
    path("batch-actions/", views.batch_actions, name="batch-actions"),
    path("<slug:slug>/", views.project_detail, name="project-detail"),
    path("<slug:slug>/context/", views.project_context, name="project-context"),
    path("<slug:slug>/context/latest/", views.project_context_latest, name="project-context-latest"),
    path("<slug:slug>/guide/", views.project_guide, name="project-guide"),
    path("<slug:slug>/actions/", views.project_actions, name="project-actions"),
    path("<slug:slug>/actions/summary/", views.project_actions_summary, name="project-actions-summary"),
]
