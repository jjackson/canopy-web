import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.projects.models import Project
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db


def test_slugs_include_workspace_across_workspaces():
    user = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    ws_a = Workspace.objects.create(slug="alpha", display_name="Alpha", created_by=user)
    ws_b = Workspace.objects.create(slug="beta", display_name="Beta", created_by=user)
    for ws in (ws_a, ws_b):
        WorkspaceMembership.objects.create(user=user, workspace=ws, role=WorkspaceMembership.OWNER)
    Project.objects.create(slug="canopy-web", name="Canopy Web", status="active", workspace=ws_a, created_by=user)
    Project.objects.create(slug="ace-web", name="ACE Web", status="active", workspace=ws_b, created_by=user)

    c = Client()
    c.force_login(user)
    r = c.get("/api/projects/slugs/")
    assert r.status_code == 200, r.content
    by_slug = {p["slug"]: p for p in r.json()}
    # cross-workspace union, each labeled with its own workspace
    assert by_slug["canopy-web"]["workspace"] == "alpha"
    assert by_slug["ace-web"]["workspace"] == "beta"
