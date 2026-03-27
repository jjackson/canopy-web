from django.urls import path

from . import views

urlpatterns = [
    path("start/<int:collection_id>/", views.start_workspace, name="start-workspace"),
    path("<int:session_id>/", views.workspace_detail, name="workspace-detail"),
    path("<int:session_id>/edit/", views.edit_skill, name="edit-skill"),
    path("<int:session_id>/publish/", views.publish_skill, name="publish-skill"),
]
