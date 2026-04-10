import pytest
from apps.projects.models import Project, ProjectContext
from django.test import Client


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def project(db):
    return Project.objects.create(
        name="canopy-web",
        slug="canopy-web",
        repo_url="https://github.com/jjackson/canopy-web",
        deploy_url="https://canopy.run.app",
        visibility="public",
        status="active",
    )


@pytest.fixture
def context_entry(db, project):
    return ProjectContext.objects.create(
        project=project,
        context_type="current_work",
        content="Building project workbench feature",
        source="jonathan",
    )


class TestProjectModel:
    def test_create_project(self, project):
        assert project.name == "canopy-web"
        assert project.slug == "canopy-web"
        assert project.status == "active"
        assert project.visibility == "public"
        assert str(project) == "canopy-web"

    def test_create_project_minimal(self, db):
        p = Project.objects.create(name="test", slug="test")
        assert p.status == "active"
        assert p.visibility == "public"
        assert p.repo_url == ""
        assert p.deploy_url == ""

    def test_slug_unique(self, db, project):
        with pytest.raises(Exception):
            Project.objects.create(name="dupe", slug="canopy-web")


class TestProjectContextModel:
    def test_create_context(self, context_entry):
        assert context_entry.context_type == "current_work"
        assert context_entry.source == "jonathan"

    def test_context_ordering(self, db, project):
        ProjectContext.objects.create(
            project=project, context_type="current_work",
            content="First", source="jonathan",
        )
        ProjectContext.objects.create(
            project=project, context_type="current_work",
            content="Second", source="jonathan",
        )
        latest = project.contexts.filter(context_type="current_work").first()
        assert latest.content == "Second"


class TestProjectListAPI:
    def test_list_empty(self, client, db):
        response = client.get("/api/projects/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == []

    def test_list_with_projects(self, client, project):
        response = client.get("/api/projects/")
        body = response.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["slug"] == "canopy-web"

    def test_list_includes_latest_context(self, client, project, context_entry):
        response = client.get("/api/projects/")
        body = response.json()
        ctx = body["data"][0]["latest_context"]
        assert "current_work" in ctx
        assert ctx["current_work"]["content"] == "Building project workbench feature"

    def test_create_project(self, client, db):
        response = client.post(
            "/api/projects/",
            data={"name": "new-project", "slug": "new-project"},
            content_type="application/json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["slug"] == "new-project"

    def test_create_duplicate_slug(self, client, project):
        response = client.post(
            "/api/projects/",
            data={"name": "dupe", "slug": "canopy-web"},
            content_type="application/json",
        )
        assert response.status_code == 400


class TestProjectDetailAPI:
    def test_get_by_slug(self, client, project, context_entry):
        response = client.get("/api/projects/canopy-web/")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["slug"] == "canopy-web"
        assert len(body["data"]["contexts"]) == 1

    def test_get_not_found(self, client, db):
        response = client.get("/api/projects/nonexistent/")
        assert response.status_code == 404

    def test_patch_project(self, client, project):
        response = client.patch(
            "/api/projects/canopy-web/",
            data={"deploy_url": "https://new.example.com"},
            content_type="application/json",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["deploy_url"] == "https://new.example.com"

    def test_delete_project(self, client, project):
        response = client.delete("/api/projects/canopy-web/")
        assert response.status_code == 200
        assert Project.objects.count() == 0


class TestProjectContextAPI:
    def test_post_context(self, client, project):
        response = client.post(
            "/api/projects/canopy-web/context/",
            data={
                "context_type": "current_work",
                "content": "Working on API",
                "source": "jonathan",
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["data"]["content"] == "Working on API"

    def test_list_context(self, client, project, context_entry):
        response = client.get("/api/projects/canopy-web/context/")
        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 1

    def test_filter_context_by_type(self, client, project, context_entry):
        ProjectContext.objects.create(
            project=project, context_type="next_step",
            content="Deploy", source="jonathan",
        )
        response = client.get("/api/projects/canopy-web/context/?type=current_work")
        body = response.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["context_type"] == "current_work"

    def test_latest_context(self, client, project):
        ProjectContext.objects.create(
            project=project, context_type="current_work",
            content="Old work", source="jonathan",
        )
        ProjectContext.objects.create(
            project=project, context_type="current_work",
            content="New work", source="jonathan",
        )
        ProjectContext.objects.create(
            project=project, context_type="next_step",
            content="Ship it", source="jonathan",
        )
        response = client.get("/api/projects/canopy-web/context/latest/")
        body = response.json()
        assert body["data"]["current_work"]["content"] == "New work"
        assert body["data"]["next_step"]["content"] == "Ship it"

    def test_post_context_empty_content(self, client, project):
        response = client.post(
            "/api/projects/canopy-web/context/",
            data={
                "context_type": "note",
                "content": "  ",
                "source": "jonathan",
            },
            content_type="application/json",
        )
        assert response.status_code == 400


class TestSeedAPI:
    def test_seed_projects(self, client, db):
        response = client.post(
            "/api/projects/seed/",
            data={
                "projects": [
                    {"name": "alpha", "slug": "alpha"},
                    {"name": "beta", "slug": "beta", "repo_url": "https://github.com/x/beta"},
                ]
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["data"]["created"] == 2

    def test_seed_skips_existing(self, client, project):
        response = client.post(
            "/api/projects/seed/",
            data={
                "projects": [
                    {"name": "canopy-web", "slug": "canopy-web"},
                    {"name": "new", "slug": "new"},
                ]
            },
            content_type="application/json",
        )
        body = response.json()
        assert body["data"]["created"] == 1
        assert body["data"]["skipped"] == 1
