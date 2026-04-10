# Project Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a project registry with public API and dense tile-grid homepage to canopy-web, replacing the skill discovery feed as the landing page.

**Architecture:** New `apps/projects/` Django app with `Project` and `ProjectContext` models. Function-based DRF views following existing envelope pattern. React tile-grid page using Warm Earth color palette. Existing discovery page moves to `/skills`.

**Tech Stack:** Django 5, DRF, PostgreSQL, React 19, Tailwind CSS 4, Zustand, TypeScript

**Spec:** `docs/superpowers/specs/2026-04-10-project-workbench-design.md`

---

## File Structure

**Backend (new files):**
- `apps/projects/__init__.py` — empty
- `apps/projects/models.py` — Project + ProjectContext models
- `apps/projects/serializers.py` — DRF serializers
- `apps/projects/views.py` — API endpoints
- `apps/projects/urls.py` — URL routing
- `apps/projects/management/__init__.py` — empty
- `apps/projects/management/commands/__init__.py` — empty
- `apps/projects/management/commands/seed_projects.py` — seed 13 projects

**Backend (modified files):**
- `config/settings/base.py` — add `apps.projects` to INSTALLED_APPS
- `config/urls.py` — add `api/projects/` include

**Frontend (new files):**
- `frontend/src/pages/ProjectsPage.tsx` — tile-grid homepage
- `frontend/src/api/projects.ts` — API client methods for projects

**Frontend (modified files):**
- `frontend/src/router.tsx` — new routes, move discovery to `/skills`
- `frontend/src/components/AppLayout/AppLayout.tsx` — update nav items
- `frontend/src/api/client.ts` — add PATCH helper

**Tests (new files):**
- `tests/test_projects.py` — backend API tests

---

### Task 1: Project and ProjectContext Models

**Files:**
- Create: `apps/projects/__init__.py`
- Create: `apps/projects/models.py`

- [ ] **Step 1: Write the test for Project model**

Create `tests/test_projects.py`:

```python
import pytest
from apps.projects.models import Project, ProjectContext


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
        c1 = ProjectContext.objects.create(
            project=project, context_type="current_work",
            content="First", source="jonathan",
        )
        c2 = ProjectContext.objects.create(
            project=project, context_type="current_work",
            content="Second", source="jonathan",
        )
        latest = project.contexts.filter(context_type="current_work").first()
        assert latest.content == "Second"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_projects.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.projects'`

- [ ] **Step 3: Create the models**

Create `apps/projects/__init__.py` (empty file).

Create `apps/projects/models.py`:

```python
from django.db import models


class Project(models.Model):
    VISIBILITY_CHOICES = [
        ("public", "Public"),
        ("private", "Private"),
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("stale", "Stale"),
        ("archived", "Archived"),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    repo_url = models.URLField(blank=True, default="")
    deploy_url = models.URLField(blank=True, default="")
    visibility = models.CharField(
        max_length=10, choices=VISIBILITY_CHOICES, default="public"
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default="active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class ProjectContext(models.Model):
    CONTEXT_TYPES = [
        ("current_work", "Current Work"),
        ("next_step", "Next Step"),
        ("summary", "Summary"),
        ("note", "Note"),
        ("insight", "Insight"),
    ]

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="contexts"
    )
    context_type = models.CharField(max_length=20, choices=CONTEXT_TYPES)
    content = models.TextField()
    source = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.project.slug}:{self.context_type}"
```

- [ ] **Step 4: Register app and create migration**

Add `"apps.projects"` to `INSTALLED_APPS` in `config/settings/base.py` (after `"apps.evals"`).

Run:
```bash
uv run python manage.py makemigrations projects
uv run python manage.py migrate
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_projects.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add apps/projects/ tests/test_projects.py config/settings/base.py
git commit -m "feat(projects): add Project and ProjectContext models"
```

---

### Task 2: Project Serializers

**Files:**
- Create: `apps/projects/serializers.py`

- [ ] **Step 1: Create serializers**

Create `apps/projects/serializers.py`:

```python
from rest_framework import serializers
from .models import Project, ProjectContext


class ProjectContextSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectContext
        fields = ["id", "context_type", "content", "source", "created_at"]


class ProjectListSerializer(serializers.ModelSerializer):
    """Project with latest context per type, used in list view."""

    latest_context = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id", "name", "slug", "repo_url", "deploy_url",
            "visibility", "status", "latest_context",
            "created_at", "updated_at",
        ]

    def get_latest_context(self, obj):
        result = {}
        if hasattr(obj, "_prefetched_contexts"):
            contexts = obj._prefetched_contexts
        else:
            contexts = obj.contexts.all()
        seen = set()
        for ctx in contexts:
            if ctx.context_type not in seen:
                seen.add(ctx.context_type)
                result[ctx.context_type] = {
                    "content": ctx.content,
                    "source": ctx.source,
                    "created_at": ctx.created_at.isoformat(),
                }
        return result


class ProjectDetailSerializer(serializers.ModelSerializer):
    """Project with full context history, used in detail view."""

    contexts = ProjectContextSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "name", "slug", "repo_url", "deploy_url",
            "visibility", "status", "contexts",
            "created_at", "updated_at",
        ]


class ProjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["name", "slug", "repo_url", "deploy_url", "visibility", "status"]

    def validate_slug(self, value):
        if Project.objects.filter(slug=value).exists():
            raise serializers.ValidationError("A project with this slug already exists.")
        return value


class ProjectContextCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectContext
        fields = ["context_type", "content", "source"]

    def validate_content(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Content cannot be empty.")
        return value
```

- [ ] **Step 2: Commit**

```bash
git add apps/projects/serializers.py
git commit -m "feat(projects): add serializers for Project and ProjectContext"
```

---

### Task 3: Project API Views and URLs

**Files:**
- Create: `apps/projects/views.py`
- Create: `apps/projects/urls.py`
- Modify: `config/urls.py`

- [ ] **Step 1: Write API tests**

Append to `tests/test_projects.py`:

```python
from django.test import Client


@pytest.fixture
def client():
    return Client()


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_projects.py::TestProjectListAPI -v`
Expected: FAIL — `404` (no URL route)

- [ ] **Step 3: Create views**

Create `apps/projects/views.py`:

```python
import json

from django.db.models import Prefetch
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.common.envelope import error_response, start_timing, success_response

from .models import Project, ProjectContext
from .serializers import (
    ProjectContextCreateSerializer,
    ProjectContextSerializer,
    ProjectCreateSerializer,
    ProjectDetailSerializer,
    ProjectListSerializer,
)


def _get_project_or_404(slug):
    try:
        return Project.objects.get(slug=slug)
    except Project.DoesNotExist:
        return None


@api_view(["GET", "POST"])
def project_list(request):
    start_timing()

    if request.method == "GET":
        projects = Project.objects.prefetch_related(
            Prefetch(
                "contexts",
                queryset=ProjectContext.objects.order_by("-created_at"),
                to_attr="_prefetched_contexts",
            )
        ).all()
        serializer = ProjectListSerializer(projects, many=True)
        return Response(success_response(serializer.data))

    serializer = ProjectCreateSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(
            success_response(serializer.data), status=status.HTTP_201_CREATED
        )
    return Response(
        error_response("VALIDATION_ERROR", serializer.errors),
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["GET", "PATCH", "DELETE"])
def project_detail(request, slug):
    start_timing()

    project = _get_project_or_404(slug)
    if project is None:
        return Response(
            error_response("NOT_FOUND", "Project not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        serializer = ProjectDetailSerializer(project)
        return Response(success_response(serializer.data))

    if request.method == "PATCH":
        serializer = ProjectCreateSerializer(
            project, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(success_response(serializer.data))
        return Response(
            error_response("VALIDATION_ERROR", serializer.errors),
            status=status.HTTP_400_BAD_REQUEST,
        )

    # DELETE
    project.delete()
    return Response(success_response({"deleted": slug}))


@api_view(["GET", "POST"])
def project_context(request, slug):
    start_timing()

    project = _get_project_or_404(slug)
    if project is None:
        return Response(
            error_response("NOT_FOUND", "Project not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        contexts = project.contexts.all()
        context_type = request.query_params.get("type")
        if context_type:
            contexts = contexts.filter(context_type=context_type)
        serializer = ProjectContextSerializer(contexts, many=True)
        return Response(success_response(serializer.data))

    serializer = ProjectContextCreateSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(project=project)
        return Response(
            success_response(ProjectContextSerializer(serializer.instance).data),
            status=status.HTTP_201_CREATED,
        )
    return Response(
        error_response("VALIDATION_ERROR", serializer.errors),
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["GET"])
def project_context_latest(request, slug):
    start_timing()

    project = _get_project_or_404(slug)
    if project is None:
        return Response(
            error_response("NOT_FOUND", "Project not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    result = {}
    for ctx in project.contexts.order_by("-created_at"):
        if ctx.context_type not in result:
            result[ctx.context_type] = {
                "content": ctx.content,
                "source": ctx.source,
                "created_at": ctx.created_at.isoformat(),
            }
    return Response(success_response(result))


@api_view(["POST"])
def seed_projects(request):
    start_timing()

    projects_data = request.data.get("projects", [])
    created = 0
    skipped = 0

    for item in projects_data:
        slug = item.get("slug")
        if not slug:
            continue
        if Project.objects.filter(slug=slug).exists():
            skipped += 1
            continue
        Project.objects.create(
            name=item.get("name", slug),
            slug=slug,
            repo_url=item.get("repo_url", ""),
            deploy_url=item.get("deploy_url", ""),
            visibility=item.get("visibility", "public"),
            status=item.get("status", "active"),
        )
        created += 1

    return Response(
        success_response({"created": created, "skipped": skipped}),
        status=status.HTTP_201_CREATED,
    )
```

- [ ] **Step 4: Create URL routing**

Create `apps/projects/urls.py`:

```python
from django.urls import path

from . import views

urlpatterns = [
    path("", views.project_list, name="project-list"),
    path("seed/", views.seed_projects, name="seed-projects"),
    path("<slug:slug>/", views.project_detail, name="project-detail"),
    path("<slug:slug>/context/", views.project_context, name="project-context"),
    path(
        "<slug:slug>/context/latest/",
        views.project_context_latest,
        name="project-context-latest",
    ),
]
```

- [ ] **Step 5: Wire into root URLs**

Add to `config/urls.py` after the evals include:

```python
path("api/projects/", include("apps.projects.urls")),
```

- [ ] **Step 6: Run all project tests**

Run: `uv run pytest tests/test_projects.py -v`
Expected: All tests PASS (model + API tests)

- [ ] **Step 7: Commit**

```bash
git add apps/projects/views.py apps/projects/urls.py apps/projects/serializers.py config/urls.py tests/test_projects.py
git commit -m "feat(projects): add API views, URLs, and tests"
```

---

### Task 4: Seed Management Command

**Files:**
- Create: `apps/projects/management/__init__.py`
- Create: `apps/projects/management/commands/__init__.py`
- Create: `apps/projects/management/commands/seed_projects.py`

- [ ] **Step 1: Create management command**

Create `apps/projects/management/__init__.py` (empty).
Create `apps/projects/management/commands/__init__.py` (empty).

Create `apps/projects/management/commands/seed_projects.py`:

```python
from django.core.management.base import BaseCommand

from apps.projects.models import Project

PROJECTS = [
    {
        "name": "canopy-web",
        "slug": "canopy-web",
        "repo_url": "https://github.com/jjackson/canopy-web",
        "deploy_url": "https://canopy.run.app",
        "visibility": "public",
        "status": "active",
    },
    {
        "name": "ace",
        "slug": "ace",
        "repo_url": "https://github.com/jjackson/ace",
        "visibility": "public",
        "status": "active",
    },
    {
        "name": "ace-web",
        "slug": "ace-web",
        "repo_url": "https://github.com/jjackson/ace-web",
        "deploy_url": "https://labs.connect.dimagi.com/ace",
        "visibility": "public",
        "status": "active",
    },
    {
        "name": "commcare-ios",
        "slug": "commcare-ios",
        "repo_url": "https://github.com/jjackson/commcare-ios",
        "visibility": "public",
        "status": "active",
    },
    {
        "name": "connect-search",
        "slug": "connect-search",
        "repo_url": "https://github.com/jjackson/connect-search",
        "visibility": "private",
        "status": "active",
    },
    {
        "name": "connect-website",
        "slug": "connect-website",
        "repo_url": "https://github.com/jjackson/connect-website",
        "visibility": "public",
        "status": "active",
    },
    {
        "name": "canopy",
        "slug": "canopy",
        "repo_url": "https://github.com/jjackson/canopy",
        "visibility": "private",
        "status": "active",
    },
    {
        "name": "connect-labs",
        "slug": "connect-labs",
        "repo_url": "https://github.com/jjackson/connect-labs",
        "deploy_url": "https://labs.connect.dimagi.com",
        "visibility": "public",
        "status": "active",
    },
    {
        "name": "chrome-sales",
        "slug": "chrome-sales",
        "repo_url": "https://github.com/jjackson/chrome-sales",
        "visibility": "private",
        "status": "active",
    },
    {
        "name": "scout",
        "slug": "scout",
        "repo_url": "https://github.com/jjackson/scout",
        "visibility": "public",
        "status": "active",
    },
    {
        "name": "canopy-skills",
        "slug": "canopy-skills",
        "repo_url": "https://github.com/jjackson/canopy-skills",
        "visibility": "public",
        "status": "active",
    },
    {
        "name": "reef",
        "slug": "reef",
        "repo_url": "https://github.com/jjackson/reef",
        "visibility": "public",
        "status": "archived",
    },
    {
        "name": "commcare-connect",
        "slug": "commcare-connect",
        "repo_url": "https://github.com/jjackson/commcare-connect",
        "visibility": "public",
        "status": "active",
    },
]


class Command(BaseCommand):
    help = "Seed database with the initial 13 projects"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true", help="Delete all projects first"
        )

    def handle(self, *args, **options):
        if options["reset"]:
            count = Project.objects.count()
            Project.objects.all().delete()
            self.stdout.write(f"Deleted {count} projects.")

        created = 0
        skipped = 0

        for spec in PROJECTS:
            _, was_created = Project.objects.get_or_create(
                slug=spec["slug"],
                defaults={
                    "name": spec["name"],
                    "repo_url": spec.get("repo_url", ""),
                    "deploy_url": spec.get("deploy_url", ""),
                    "visibility": spec.get("visibility", "public"),
                    "status": spec.get("status", "active"),
                },
            )
            if was_created:
                created += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded projects: {created} created, {skipped} already existed."
            )
        )
```

- [ ] **Step 2: Test the command**

Run: `uv run python manage.py seed_projects`
Expected: `Seeded projects: 13 created, 0 already existed.`

Run again: `uv run python manage.py seed_projects`
Expected: `Seeded projects: 0 created, 13 already existed.`

- [ ] **Step 3: Commit**

```bash
git add apps/projects/management/
git commit -m "feat(projects): add seed_projects management command with 13 projects"
```

---

### Task 5: Frontend API Client

**Files:**
- Create: `frontend/src/api/projects.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add PATCH helper to client.ts**

In `frontend/src/api/client.ts`, check if there's already a generic PATCH method. If not, the `request` function already supports arbitrary `RequestInit`, so no change needed — PATCH is just `request(path, { method: 'PATCH', body: ... })`.

- [ ] **Step 2: Create projects API module**

Create `frontend/src/api/projects.ts`:

```typescript
const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  const data = await resp.json()
  if (!data.success) throw new Error(data.error?.message || 'Request failed')
  return data.data
}

export interface ProjectContext {
  content: string
  source: string
  created_at: string
}

export interface ProjectContextEntry {
  id: number
  context_type: string
  content: string
  source: string
  created_at: string
}

export interface Project {
  id: number
  name: string
  slug: string
  repo_url: string
  deploy_url: string
  visibility: string
  status: string
  latest_context: Record<string, ProjectContext>
  created_at: string
  updated_at: string
}

export interface ProjectDetail {
  id: number
  name: string
  slug: string
  repo_url: string
  deploy_url: string
  visibility: string
  status: string
  contexts: ProjectContextEntry[]
  created_at: string
  updated_at: string
}

export const projectsApi = {
  list: () => request<Project[]>('/projects/'),

  get: (slug: string) => request<ProjectDetail>(`/projects/${slug}/`),

  create: (data: { name: string; slug: string; repo_url?: string; deploy_url?: string; visibility?: string; status?: string }) =>
    request<Project>('/projects/', { method: 'POST', body: JSON.stringify(data) }),

  update: (slug: string, data: Partial<{ name: string; repo_url: string; deploy_url: string; status: string; visibility: string }>) =>
    request<Project>(`/projects/${slug}/`, { method: 'PATCH', body: JSON.stringify(data) }),

  delete: (slug: string) =>
    request<{ deleted: string }>(`/projects/${slug}/`, { method: 'DELETE' }),

  postContext: (slug: string, data: { context_type: string; content: string; source: string }) =>
    request<ProjectContextEntry>(`/projects/${slug}/context/`, { method: 'POST', body: JSON.stringify(data) }),

  getContext: (slug: string, type?: string) =>
    request<ProjectContextEntry[]>(`/projects/${slug}/context/${type ? `?type=${type}` : ''}`),

  getLatestContext: (slug: string) =>
    request<Record<string, ProjectContext>>(`/projects/${slug}/context/latest/`),
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/projects.ts
git commit -m "feat(projects): add frontend API client for projects"
```

---

### Task 6: Projects Page (Tile Grid)

**Files:**
- Create: `frontend/src/pages/ProjectsPage.tsx`

- [ ] **Step 1: Create the ProjectsPage component**

Create `frontend/src/pages/ProjectsPage.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { type Project, type ProjectContextEntry, projectsApi } from '@/api/projects'

function DeployBadge({ url }: { url: string }) {
  if (!url) return <span className="text-[10px] text-stone-600">—</span>
  const hostname = (() => {
    try { return new URL(url).hostname.replace('www.', '') } catch { return url }
  })()
  return (
    <a href={url} target="_blank" rel="noopener noreferrer"
      className="inline-flex items-center gap-1.5 text-[10px] bg-stone-800 text-stone-400 px-2 py-0.5 rounded hover:text-stone-200 transition-colors"
      onClick={(e) => e.stopPropagation()}>
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_4px_rgba(74,222,128,0.4)]" />
      {hostname}
    </a>
  )
}

function StatusDot({ status }: { status: string }) {
  const color = status === 'active'
    ? 'bg-orange-400 shadow-[0_0_6px_rgba(251,146,60,0.3)]'
    : status === 'stale'
      ? 'bg-stone-500'
      : 'bg-stone-700'
  return <span className={`w-[7px] h-[7px] rounded-full shrink-0 ${color}`} />
}

function ContextLine({ label, text, muted }: { label: string; text?: string; muted?: boolean }) {
  if (!text) return null
  return (
    <div className={`text-xs leading-relaxed ${muted ? 'text-stone-600' : 'text-stone-400'}`}>
      <span className="text-stone-600 uppercase text-[9px] tracking-wide font-medium mr-2">{label}</span>
      {text}
    </div>
  )
}

function ProjectTile({ project, onContextSaved }: { project: Project; onContextSaved: () => void }) {
  const [expanded, setExpanded] = useState(false)
  const [editType, setEditType] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [saving, setSaving] = useState(false)

  const ctx = project.latest_context || {}

  async function saveContext() {
    if (!editType || !editValue.trim()) return
    setSaving(true)
    try {
      await projectsApi.postContext(project.slug, {
        context_type: editType,
        content: editValue.trim(),
        source: 'jonathan',
      })
      setEditType(null)
      setEditValue('')
      onContextSaved()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className={`bg-stone-900 border rounded-lg cursor-pointer transition-colors ${
        expanded ? 'border-stone-700' : 'border-stone-800 hover:border-stone-700'
      }`}
      onClick={() => setExpanded(!expanded)}
    >
      {/* Collapsed view */}
      <div className="p-4">
        <div className="flex items-center gap-3 mb-2">
          <StatusDot status={project.status} />
          <span className="text-sm font-semibold text-stone-100">{project.name}</span>
          <div className="ml-auto flex items-center gap-2">
            {project.visibility === 'private' && (
              <span className="text-[9px] text-stone-500 border border-orange-400/15 bg-orange-400/5 px-1.5 py-0.5 rounded uppercase tracking-wide">private</span>
            )}
            <DeployBadge url={project.deploy_url} />
          </div>
        </div>
        <ContextLine label="now" text={ctx.current_work?.content} />
        <ContextLine label="next" text={ctx.next_step?.content} muted />
        {!ctx.current_work && !ctx.next_step && (
          <div className="text-xs text-stone-700 italic">No context yet</div>
        )}
      </div>

      {/* Expanded view */}
      {expanded && (
        <div className="border-t border-stone-800 px-4 pb-4 pt-3" onClick={(e) => e.stopPropagation()}>
          {/* Links */}
          <div className="flex gap-4 mb-3 text-[11px]">
            {project.repo_url && (
              <a href={project.repo_url} target="_blank" rel="noopener noreferrer"
                className="text-orange-400/70 hover:text-orange-400 transition-colors">
                GitHub ↗
              </a>
            )}
            {project.deploy_url && (
              <a href={project.deploy_url} target="_blank" rel="noopener noreferrer"
                className="text-orange-400/70 hover:text-orange-400 transition-colors">
                Live Site ↗
              </a>
            )}
          </div>

          {/* Summary if present */}
          {ctx.summary && (
            <div className="bg-stone-950 border-l-2 border-orange-400 rounded-r-lg p-3 mb-3 text-xs text-stone-400 leading-relaxed">
              {ctx.summary.content}
              <div className="text-[10px] text-stone-700 mt-1">
                {ctx.summary.source} · {new Date(ctx.summary.created_at).toLocaleDateString()}
              </div>
            </div>
          )}

          {/* Inline edit */}
          {editType ? (
            <div className="flex gap-2 mt-2">
              <input
                type="text"
                className="flex-1 bg-stone-950 border border-stone-700 rounded px-3 py-1.5 text-xs text-stone-200 placeholder:text-stone-600 focus:outline-none focus:border-orange-400/50"
                placeholder={`Update ${editType === 'current_work' ? 'current work' : 'next step'}...`}
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') saveContext(); if (e.key === 'Escape') setEditType(null) }}
                autoFocus
              />
              <button onClick={saveContext} disabled={saving}
                className="text-xs px-3 py-1.5 rounded bg-orange-400/10 border border-orange-400/30 text-orange-400 hover:bg-orange-400/20 disabled:opacity-50 transition-colors">
                {saving ? '...' : 'Save'}
              </button>
            </div>
          ) : (
            <div className="flex gap-2 mt-2">
              <button onClick={() => setEditType('current_work')}
                className="text-[11px] px-2.5 py-1 rounded bg-stone-950 border border-stone-700 text-stone-500 hover:text-stone-300 hover:border-stone-600 transition-colors">
                Update current work
              </button>
              <button onClick={() => setEditType('next_step')}
                className="text-[11px] px-2.5 py-1 rounded bg-stone-950 border border-stone-700 text-stone-500 hover:text-stone-300 hover:border-stone-600 transition-colors">
                Update next step
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void (async () => {
      try {
        const data = await projectsApi.list()
        if (!cancelled) setProjects(data)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load projects')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [refreshKey])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-stone-600 text-sm">
        Loading projects...
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400 text-sm">
        {error}
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold text-stone-100">Projects</h1>
        <span className="text-xs text-stone-600 bg-stone-900 px-2.5 py-1 rounded">
          {projects.length} projects
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
        {projects.map((project) => (
          <ProjectTile key={project.id} project={project} onContextSaved={() => setRefreshKey((k) => k + 1)} />
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/ProjectsPage.tsx
git commit -m "feat(projects): add ProjectsPage tile-grid component"
```

---

### Task 7: Router and Nav Updates

**Files:**
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/components/AppLayout/AppLayout.tsx`

- [ ] **Step 1: Update router**

In `frontend/src/router.tsx`:

1. Add import: `import { ProjectsPage } from './pages/ProjectsPage'`
2. Change the `/` route from `<DiscoveryPage />` to `<ProjectsPage />`
3. Add new route: `{ path: '/skills', element: <DiscoveryPage /> }`

The children array should become:

```typescript
children: [
  { path: '/', element: <ProjectsPage /> },
  { path: '/skills', element: <DiscoveryPage /> },
  { path: '/new', element: <NewCollectionPage /> },
  { path: '/workspace/:sessionId', element: <WorkspacePage /> },
  { path: '/skills/:skillId', element: <SkillDetailPage /> },
  { path: '/leaderboard', element: <LeaderboardPage /> },
  { path: '/guide', element: <GuidePage /> },
  { path: '/settings', element: <SettingsPage /> },
],
```

- [ ] **Step 2: Update nav items**

In `frontend/src/components/AppLayout/AppLayout.tsx`:

Update the `NAV_ITEMS` array to:

```typescript
const NAV_ITEMS = [
  { path: '/', label: 'Projects' },
  { path: '/skills', label: 'Skills' },
  { path: '/leaderboard', label: 'Leaderboard' },
  { path: '/guide', label: 'Guide' },
  { path: '/settings', label: 'Settings' },
]
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/router.tsx frontend/src/components/AppLayout/AppLayout.tsx
git commit -m "feat(projects): wire up ProjectsPage as homepage, move skills to /skills"
```

---

### Task 8: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update key URLs section**

Add the new route to the Key URLs section in `CLAUDE.md`:

```
- `/` — Project workbench (tile grid dashboard)
- `/skills` — Skill discovery feed
```

Remove or update the old `/` entry that said "Skill discovery feed".

- [ ] **Step 2: Update API Endpoints section**

Add a new `### Projects` subsection to the API Endpoints section:

```markdown
### Projects
- `GET /api/projects/` — List projects with latest context
- `POST /api/projects/` — Create project
- `GET /api/projects/{slug}/` — Project detail with full context
- `PATCH /api/projects/{slug}/` — Update project
- `DELETE /api/projects/{slug}/` — Delete project
- `POST /api/projects/{slug}/context/` — Push context entry
- `GET /api/projects/{slug}/context/` — List context entries
- `GET /api/projects/{slug}/context/latest/` — Latest context per type
- `POST /api/projects/seed/` — Bulk seed projects
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with project workbench routes and API"
```

---

### Task 9: Run Full Test Suite

**Files:** None (verification only)

- [ ] **Step 1: Run all backend tests**

Run: `uv run pytest -v`
Expected: All tests pass, including existing tests and new project tests.

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 3: Manual smoke test**

Start both servers:
```bash
uv run honcho start -f Procfile.dev
```

1. Open `http://localhost:5173` — should show ProjectsPage with empty grid
2. Run: `uv run python manage.py seed_projects` — seed the 13 projects
3. Refresh — should show 13 project tiles
4. Click a tile — should expand with links and edit buttons
5. Click "Update current work" — type something, press Enter — should save
6. Navigate to `/skills` — should show the old discovery page
7. Hit `GET /api/projects/` — should return JSON with all projects
8. Hit `GET /api/projects/canopy-web/context/latest/` — should return latest context

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address smoke test issues"
```
