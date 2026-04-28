import pytest
from django.utils import timezone
from apps.projects.models import Project, ProjectAction, ProjectContext
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


class TestProjectSkillsField:
    def test_skills_default_empty(self, project):
        assert project.skills == []

    def test_set_skills_list(self, db):
        p = Project.objects.create(
            name="test", slug="test",
            skills=[{"name": "alpha", "path": "skills/alpha"}],
        )
        p.refresh_from_db()
        assert len(p.skills) == 1
        assert p.skills[0]["name"] == "alpha"

    def test_skills_in_list_response(self, client, db):
        Project.objects.create(
            name="x", slug="x",
            skills=[{"name": "s1", "path": "skills/s1", "description": "d"}],
        )
        response = client.get("/api/projects/")
        body = response.json()
        assert body["data"][0]["skills"][0]["name"] == "s1"

    def test_patch_project_skills(self, client, project):
        response = client.patch(
            "/api/projects/canopy-web/",
            data={"skills": [{"name": "new", "path": "skills/new"}]},
            content_type="application/json",
        )
        assert response.status_code == 200
        body = response.json()
        # The skills field should round-trip
        canopy = client.get("/api/projects/canopy-web/").json()["data"]
        assert canopy["skills"][0]["name"] == "new"


class TestProjectActionsAPI:
    def test_post_action(self, client, project):
        response = client.post(
            "/api/projects/canopy-web/actions/",
            data={
                "skill_name": "code-review",
                "session_id": "abc-123",
                "status": "completed",
                "started_at": "2026-04-10T12:00:00Z",
                "completed_at": "2026-04-10T12:05:00Z",
                "duration_ms": 300000,
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["data"]["skill_name"] == "code-review"
        assert body["data"]["status"] == "completed"

    def test_list_actions(self, client, project):
        from apps.projects.models import ProjectAction
        ProjectAction.objects.create(
            project=project, skill_name="doc-regen",
            status="completed", started_at=timezone.now(),
        )
        response = client.get("/api/projects/canopy-web/actions/")
        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 1

    def test_filter_by_skill(self, client, project):
        from apps.projects.models import ProjectAction
        ProjectAction.objects.create(
            project=project, skill_name="code-review",
            status="completed", started_at=timezone.now(),
        )
        ProjectAction.objects.create(
            project=project, skill_name="doc-regen",
            status="completed", started_at=timezone.now(),
        )
        response = client.get("/api/projects/canopy-web/actions/?skill=code-review")
        body = response.json()
        assert len(body["data"]) == 1

    def test_actions_summary(self, client, project):
        from apps.projects.models import ProjectAction
        ProjectAction.objects.create(
            project=project, skill_name="code-review",
            status="completed", started_at=timezone.now(),
        )
        ProjectAction.objects.create(
            project=project, skill_name="doc-regen",
            status="completed", started_at=timezone.now(),
        )
        response = client.get("/api/projects/canopy-web/actions/summary/")
        assert response.status_code == 200
        body = response.json()
        assert "code-review" in body["data"]
        assert "doc-regen" in body["data"]

    def test_latest_actions_in_list(self, client, project):
        from apps.projects.models import ProjectAction
        ProjectAction.objects.create(
            project=project, skill_name="code-review",
            status="completed", started_at=timezone.now(),
        )
        response = client.get("/api/projects/")
        body = response.json()
        proj = body["data"][0]
        assert "latest_actions" in proj
        assert "code-review" in proj["latest_actions"]

    def test_post_action_empty_skill(self, client, project):
        response = client.post(
            "/api/projects/canopy-web/actions/",
            data={
                "skill_name": "",
                "status": "started",
                "started_at": "2026-04-10T12:00:00Z",
            },
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_post_action_not_found(self, client, db):
        response = client.post(
            "/api/projects/nonexistent/actions/",
            data={
                "skill_name": "x",
                "status": "started",
                "started_at": "2026-04-10T12:00:00Z",
            },
            content_type="application/json",
        )
        assert response.status_code == 404


class TestInsightsAPI:
    def test_list_insights_empty(self, client, db):
        response = client.get("/api/insights/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == []

    def test_list_insights_returns_only_insights(self, client, project):
        ProjectContext.objects.create(
            project=project, context_type="insight",
            content="[ship_gap] ace-web has 6 commits since last deploy",
            source="canopy:portfolio-review",
        )
        ProjectContext.objects.create(
            project=project, context_type="summary",
            content="This is a summary", source="canopy:activity-summary",
        )
        response = client.get("/api/insights/")
        body = response.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["project_slug"] == "canopy-web"

    def test_list_insights_across_projects(self, client, db):
        p1 = Project.objects.create(name="alpha", slug="alpha")
        p2 = Project.objects.create(name="beta", slug="beta")
        ProjectContext.objects.create(project=p1, context_type="insight", content="A", source="test")
        ProjectContext.objects.create(project=p2, context_type="insight", content="B", source="test")
        response = client.get("/api/insights/")
        body = response.json()
        assert len(body["data"]) == 2

    def test_filter_by_category(self, client, project):
        ProjectContext.objects.create(project=project, context_type="insight", content="[ship_gap] X", source="test")
        ProjectContext.objects.create(project=project, context_type="insight", content="[hygiene] Y", source="test")
        response = client.get("/api/insights/?category=ship_gap")
        body = response.json()
        assert len(body["data"]) == 1

    def test_dismiss_insight(self, client, project):
        ctx = ProjectContext.objects.create(project=project, context_type="insight", content="X", source="test")
        response = client.delete(f"/api/insights/{ctx.id}/")
        assert response.status_code == 200
        assert ProjectContext.objects.filter(id=ctx.id).count() == 0

    def test_dismiss_not_found(self, client, db):
        response = client.delete("/api/insights/9999/")
        assert response.status_code == 404

    def test_default_limit(self, client, project):
        for i in range(25):
            ProjectContext.objects.create(project=project, context_type="insight", content=f"I{i}", source="test")
        response = client.get("/api/insights/")
        assert len(response.json()["data"]) == 20


class TestBatchContextAPI:
    def test_batch_creates_across_projects(self, client, db):
        Project.objects.create(name="alpha", slug="alpha")
        Project.objects.create(name="beta", slug="beta")
        response = client.post(
            "/api/projects/batch-context/",
            data={
                "updates": {
                    "alpha": [{"context_type": "summary", "content": "A1", "source": "test"}],
                    "beta": [
                        {"context_type": "summary", "content": "B1", "source": "test"},
                        {"context_type": "next_step", "content": "B2", "source": "test"},
                    ],
                }
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["data"]["total_created"] == 3
        assert body["data"]["total_errors"] == 0
        assert body["data"]["results"]["alpha"]["created"] == 1
        assert body["data"]["results"]["beta"]["created"] == 2
        assert ProjectContext.objects.filter(project__slug="alpha").count() == 1
        assert ProjectContext.objects.filter(project__slug="beta").count() == 2

    def test_batch_partial_success_unknown_slug(self, client, project):
        response = client.post(
            "/api/projects/batch-context/",
            data={
                "updates": {
                    "canopy-web": [{"context_type": "summary", "content": "Good", "source": "test"}],
                    "unknown": [{"context_type": "summary", "content": "X", "source": "test"}],
                }
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["data"]["results"]["canopy-web"]["created"] == 1
        assert body["data"]["results"]["unknown"]["created"] == 0
        assert body["data"]["results"]["unknown"]["errors"][0]["code"] == "NOT_FOUND"
        assert body["data"]["total_created"] == 1
        assert body["data"]["total_errors"] == 1

    def test_batch_entry_validation_error(self, client, project):
        response = client.post(
            "/api/projects/batch-context/",
            data={
                "updates": {
                    "canopy-web": [
                        {"context_type": "summary", "content": "Valid", "source": "test"},
                        {"context_type": "note", "content": "   ", "source": "test"},
                    ]
                }
            },
            content_type="application/json",
        )
        body = response.json()
        assert body["data"]["results"]["canopy-web"]["created"] == 1
        assert len(body["data"]["results"]["canopy-web"]["errors"]) == 1

    def test_batch_invalid_shape(self, client, db):
        response = client.post(
            "/api/projects/batch-context/",
            data={"updates": "not a dict"},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_batch_empty_updates(self, client, db):
        response = client.post(
            "/api/projects/batch-context/",
            data={"updates": {}},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["data"]["total_created"] == 0


class TestBatchActionsAPI:
    def test_batch_actions_across_projects(self, client, db):
        Project.objects.create(name="alpha", slug="alpha")
        Project.objects.create(name="beta", slug="beta")
        response = client.post(
            "/api/projects/batch-actions/",
            data={
                "updates": {
                    "alpha": [{
                        "skill_name": "code-review",
                        "status": "completed",
                        "started_at": "2026-04-10T12:00:00Z",
                    }],
                    "beta": [{
                        "skill_name": "doc-regen",
                        "status": "started",
                        "started_at": "2026-04-10T12:00:00Z",
                    }],
                }
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["data"]["total_created"] == 2
        assert ProjectAction.objects.filter(project__slug="alpha").count() == 1
        assert ProjectAction.objects.filter(project__slug="beta").count() == 1

    def test_batch_actions_invalid_entry(self, client, project):
        response = client.post(
            "/api/projects/batch-actions/",
            data={
                "updates": {
                    "canopy-web": [
                        {"skill_name": "", "status": "started", "started_at": "2026-04-10T12:00:00Z"},
                    ]
                }
            },
            content_type="application/json",
        )
        body = response.json()
        assert body["data"]["results"]["canopy-web"]["created"] == 0
        assert len(body["data"]["results"]["canopy-web"]["errors"]) == 1
