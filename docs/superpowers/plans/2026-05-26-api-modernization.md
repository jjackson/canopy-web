# API Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace DRF with Django Ninja, make Pydantic v2 the single source of truth for every API request/response shape, generate the frontend TypeScript client from the OpenAPI 3.1 schema, kill the `{success, data, timing_ms}` envelope in favor of RFC 7807 `application/problem+json`, add Schemathesis contract tests in CI, and expose a curated read-only slice as MCP tools via FastMCP. Keep Django (ORM, allauth, middleware, SSE streaming) untouched.

**Architecture:** Mount Django Ninja at `/api/v2/` alongside the existing DRF surface at `/api/`. Build a Pydantic schema library in `apps/<app>/schemas.py`. Port endpoints app-by-app under v2. Generate `frontend/src/api/generated.ts` from the live OpenAPI schema via `openapi-typescript`; replace `frontend/src/api/client.ts` + per-resource files with `openapi-fetch` calls against v2. Once every frontend call moves to v2, delete DRF, delete `apps/common/envelope.py`, remove `/api/`, and rename `/api/v2/` → `/api/`. Wire FastMCP as an additional surface that exposes endpoints flagged with `x-mcp-expose: true`.

**Tech Stack:** Django 5 (kept), Django Ninja 1.x, Pydantic v2, `orjson` renderer, Scalar (docs UI), `openapi-typescript` + `openapi-fetch` + TanStack Query-compatible types (frontend), Schemathesis (contract tests in CI), FastMCP (MCP exposure).

**Out of scope:** No changes to django-allauth Google OAuth, `LoginRequiredMiddleware`, SSE streaming in `apps/workspace/views.py`, Bearer-token bypass machinery, the `_canopy_e2e_session` / `_canopy_debug_session` markers, custom AnthropicClient module, or any business logic. This is a transport-layer modernization; behavior is identical end-to-end.

**Reference:** This plan is modeled on ace-web's `docs/plans/2026-05-14-api-modernization.md` and its shipped `apps/api/` package (`/Users/acedimagi/emdash/repositories/ace-web/apps/api/`). When in doubt, mirror ace-web's structure.

> **⚠ Walkthrough work is ongoing — Tasks 8-14 are still committing to `main`:** PR #40 (the foundation — model, Drive client, 6 REST endpoints) is merged, but the walkthrough author continues to ship Tasks 8-14 (per `docs/superpowers/plans/2026-05-26-walkthrough-sharing.md`): streaming `/w/<id>/content` endpoint with HTTP Range, `walkthrough_count` on project detail, `frontend/src/api/walkthroughs.ts`, `WalkthroughsPage.tsx`, `WalkthroughViewerPage.tsx`, project-tile integration, docs sweep. **Each phase of this plan starts with a Rebase Checkpoint** — `git fetch && git rebase origin/main` then `gh pr list --state merged --search "walkthroughs"` since the last checkpoint. Address any newly landed surface in the relevant phase's task list:
>
> - **New endpoints** under `apps/walkthroughs/` or `/w/<id>/...` → add Task 2.7.X with the Task 2.1.2 worked-example pattern. Streaming endpoints (Task 8 of the walkthrough plan) need `response=None` and the SSE preservation treatment from Task 2.5.2.
> - **New fields on existing models** (e.g. Task 9 adds `walkthrough_count` to project responses) → add the field to the relevant `Out` schema in Phase 1, regenerate frontend types, update the contract test fixtures.
> - **New frontend client files** (`frontend/src/api/walkthroughs.ts` when Task 10 lands) → add as Phase 4 task using the Task 4.1 pattern. Multipart upload from the frontend uses native `FormData` + the typed client's `bodySerializer` override.
> - **New tests** in `tests/test_walkthroughs_*.py` → during Phase 5.1.6a deletion, distinguish transport-coupled (delete; coverage moved to `apps/walkthroughs/tests/test_api.py`) from transport-agnostic (keep — model + Drive client tests).
>
> Foundation work (Phases 0, 6, 7, 8) doesn't touch walkthroughs and can proceed in parallel without rebase blocking. Spec for the entire walkthrough effort: `docs/superpowers/specs/2026-05-26-walkthrough-sharing-design.md`.

**Canopy-web-specific gotchas the engineer must respect:**

1. **SSE preservation.** `apps/workspace/views.py` has two streaming endpoints (`start_workspace`, `analyze_workspace`) that return `StreamingHttpResponse`. Ninja handlers can return Django `HttpResponse` subclasses directly — declare them as `response=None` and document the SSE event format in the route docstring; do not try to type the stream body. **The SSE event format must be byte-identical post-migration** — the frontend consumes `event:` / `data:` lines verbatim.

2. **Bearer-token middleware compatibility.** `apps/common/middleware.LoginRequiredMiddleware` admits machine callers via `Authorization: Bearer <WORKBENCH_WRITE_TOKEN>` on a narrow allowlist (writes to `/api/projects/*/actions/` + `/api/projects/*/context/`, reads of `/api/projects/slugs/` + `/api/insights/`). The middleware sets `request._dont_enforce_csrf_checks = True` and `request._workbench_token_auth = True` before handing off. Ninja **must not** re-challenge these requests — see Task 0.6.

3. **No multi-tenancy.** Unlike ace-web's `resolve_workspace_for_member` (404-not-403 to hide existence), canopy-web is single-tenant. Skip the workspace-membership dep. Per-resource ownership (e.g. `WorkspaceSession.collection`) is enforced at the query layer or implicitly via `LoginRequiredMiddleware`.

4. **django-allauth, not hand-rolled OAuth.** `request.user` is populated by allauth's session middleware exactly as in Django default auth — Ninja's `SessionAuth` works without wrapping. Adopt ace-web's `DjangoSessionAuth` only for the problem+json 401 body.

5. **Anthropic SDK stays put for now.** `apps/common/anthropic_client.py` and the workspace engine's direct calls are out of scope; the Pydantic AI swap is Phase 8 and optional.

6. **Rich response shapes win over thin Pydantic outputs.** Ace-web's PR #346 silently dropped `display_name`, `tags`, `eval_score`, etc. when they tried to tighten payloads. For each canopy-web endpoint, **capture the live DRF response with `curl` first** and write the round-trip test against that exact dict before writing the schema. Skim ace-web's CLAUDE.md "Rich response shapes over strict Pydantic outputs" decision before touching opps-like cards.

---

## File structure

This plan introduces / touches these files (paths relative to the repo root):

### New backend package

- `apps/api/__init__.py` — package marker
- `apps/api/api.py` — single `NinjaAPI` instance + exception handlers
- `apps/api/errors.py` — `Problem` model + `ProblemError` + `TYPE_*` URIs
- `apps/api/renderers.py` — `OrjsonRenderer` + `ProblemJsonRenderer`
- `apps/api/auth.py` — `DjangoSessionAuth` raising problem+json 401
- `apps/api/deps.py` — `require_authenticated`, helpers
- `apps/api/pagination.py` — `Page[T]` generic
- `apps/api/etag.py` — `compute_etag` + `maybe_not_modified`
- `apps/api/views.py` — static HTML for Scalar + Redoc
- `apps/api/mcp_server.py` — FastMCP server (Phase 7)
- `apps/api/tests/test_smoke.py` — package-level smoke tests
- `apps/api/tests/test_pagination.py`
- `apps/api/tests/test_etag.py`

### Per-app new files

For each of `collections`, `projects`, `skills`, `evals`, `workspace`, `walkthroughs`, `common`:

- `apps/<app>/schemas.py` — Pydantic request/response models
- `apps/<app>/api.py` — Ninja router
- `apps/<app>/tests/test_schemas.py` — round-trip tests
- `apps/<app>/tests/test_api.py` — contract tests

### Modified files

- `pyproject.toml` — add deps; later remove DRF
- `config/urls.py` — mount `/api/v2/` then later rename to `/api/`
- `config/settings/base.py` — remove `rest_framework` from `INSTALLED_APPS` in Phase 5
- `apps/common/middleware.py` — verify Bearer + Ninja compatibility (Task 0.6)
- `frontend/package.json` — add `openapi-typescript` + `openapi-fetch`
- `frontend/src/api/client.ts` — rewrite as typed client
- `frontend/src/api/projects.ts` — migrate to typed client
- `frontend/src/api/insights.ts` — migrate to typed client
- `.github/workflows/ci.yml` — add `contract-tests` job

### New CI workflow

- `.github/workflows/regen-openapi.yml` — auto-commit regenerated types on PR

### Deleted (Phase 5)

- `apps/collections/views.py`, `apps/collections/serializers.py`, `apps/collections/urls.py`
- `apps/evals/views.py`, `apps/evals/serializers.py`, `apps/evals/urls.py`
- `apps/projects/views.py`, `apps/projects/views_insights.py`, `apps/projects/serializers.py`, `apps/projects/urls.py`
- `apps/skills/views.py`, `apps/skills/serializers.py`, `apps/skills/urls.py`
- `apps/workspace/views.py` (replaced by `apps/workspace/api.py` — SSE handlers move into the Ninja router)
- `apps/workspace/urls.py`
- `apps/walkthroughs/views.py`, `apps/walkthroughs/serializers.py`, `apps/walkthroughs/urls.py` (replaced by `apps/walkthroughs/api.py`)
- `apps/common/views.py` (AI backend endpoints move into the Ninja router), `apps/common/urls.py`
- `apps/common/envelope.py`
- `frontend/src/api/client.ts` (functions move into per-resource modules using `openapi-fetch`)

Endpoints that **stay as bare Django views** (not ported to Ninja):

- `GET /health/` — public, keep as `config/views.health_check`
- `GET /api/csrf/` — sets the CSRF cookie via `@ensure_csrf_cookie`; Ninja-incompatible
- `POST /api/auth/e2e-login/` — uses `csrf_exempt` + custom session marker logic
- `POST /api/debug/mint-session/` — manipulates `SessionStore` directly
- `/accounts/...` — django-allauth-owned URLs

These are documented in OpenAPI as out-of-band auxiliary endpoints; `LoginRequiredMiddleware` already covers them.

---

## Phase 0: Foundation

Stand up Django Ninja, Pydantic v2, Scalar, the shared problem+json error model, and the `/api/v2/` namespace. Zero behavior change to existing endpoints.

### Task 0.1: Add Ninja + Pydantic + orjson dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add deps**

Edit `pyproject.toml` `[project] dependencies` to add (alongside existing entries — leave `djangorestframework` alone for now):

```toml
"django-ninja>=1.3,<2.0",
"pydantic>=2.8,<3.0",
"pydantic[email]>=2.8,<3.0",  # for EmailStr
"orjson>=3.10",
```

- [ ] **Step 2: Sync**

Run: `uv sync --extra dev`
Expected: clean install, no resolver conflicts. uv.lock updates.

- [ ] **Step 3: Verify imports**

Run: `uv run python -c "import ninja, pydantic, orjson; print(ninja.__version__, pydantic.VERSION, orjson.__version__)"`
Expected: prints three version numbers without error.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat(api): add django-ninja + pydantic v2 + orjson dependencies"
```

### Task 0.2: Create the v2 NinjaAPI singleton with problem+json error model

**Files:**
- Create: `apps/api/__init__.py`
- Create: `apps/api/errors.py`
- Create: `apps/api/renderers.py`
- Create: `apps/api/api.py`

- [ ] **Step 1: Create the empty package**

```python
# apps/api/__init__.py
"""Django Ninja v2 API.

Pydantic-first replacement for the legacy DRF surface in apps/<app>/views.py.
Mounted at /api/v2/ during the migration; renamed to /api/ in Phase 5.
"""
```

- [ ] **Step 2: Create the problem+json error model**

```python
# apps/api/errors.py
"""RFC 7807 problem+json error model + helpers."""
from __future__ import annotations

from typing import Any

from ninja.errors import HttpError
from pydantic import BaseModel, Field


class Problem(BaseModel):
    """RFC 7807 application/problem+json body.

    `type` is a stable URI identifying the error class.
    `title` is human-readable, stable per `type`.
    `status` mirrors the HTTP status.
    `detail` is the per-occurrence message.
    `instance` is the request path (optional).
    """

    type: str = Field(default="about:blank")
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    extras: dict[str, Any] | None = None


class ProblemError(HttpError):
    """Raise this anywhere in a v2 handler to short-circuit with a problem+json response."""

    def __init__(
        self,
        status: int,
        title: str,
        *,
        type_: str = "about:blank",
        detail: str | None = None,
        extras: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status, title)
        self.problem_type = type_
        self.problem_title = title
        self.problem_detail = detail
        self.problem_extras = extras


# Common type URIs — extend as needed.
TYPE_VALIDATION = "https://canopy-web.dimagi.com/problems/validation"
TYPE_AUTH = "https://canopy-web.dimagi.com/problems/auth"
TYPE_FORBIDDEN = "https://canopy-web.dimagi.com/problems/forbidden"
TYPE_NOT_FOUND = "https://canopy-web.dimagi.com/problems/not-found"
TYPE_CONFLICT = "https://canopy-web.dimagi.com/problems/conflict"
TYPE_RATE_LIMIT = "https://canopy-web.dimagi.com/problems/rate-limit"
TYPE_UPSTREAM = "https://canopy-web.dimagi.com/problems/upstream"
TYPE_INTERNAL = "https://canopy-web.dimagi.com/problems/internal"
TYPE_PAYLOAD_TOO_LARGE = "https://canopy-web.dimagi.com/problems/payload-too-large"
TYPE_DRIVE_NOT_CONFIGURED = "https://canopy-web.dimagi.com/problems/drive-not-configured"
TYPE_DRIVE_UPLOAD_FAILED = "https://canopy-web.dimagi.com/problems/drive-upload-failed"
```

- [ ] **Step 3: Create the orjson renderer**

```python
# apps/api/renderers.py
"""orjson-backed renderer + problem+json content-type override."""
from __future__ import annotations

import orjson
from ninja.renderers import BaseRenderer


class OrjsonRenderer(BaseRenderer):
    media_type = "application/json"

    def render(self, request, data, *, response_status):
        return orjson.dumps(data, option=orjson.OPT_NON_STR_KEYS | orjson.OPT_UTC_Z)


class ProblemJsonRenderer(OrjsonRenderer):
    """Used by the global error handler — sets `application/problem+json`."""

    media_type = "application/problem+json"
```

- [ ] **Step 4: Create the v2 NinjaAPI**

```python
# apps/api/api.py
"""Single NinjaAPI instance for the /api/v2/ namespace.

All v2 routers register against this. Routers live in
`apps/<app>/api.py` and are imported below.
"""
from __future__ import annotations

import logging

from django.http import Http404, HttpRequest, HttpResponse
from ninja import NinjaAPI
from ninja.errors import AuthenticationError, HttpError, ValidationError

from .errors import (
    TYPE_AUTH,
    TYPE_INTERNAL,
    TYPE_NOT_FOUND,
    TYPE_VALIDATION,
    Problem,
    ProblemError,
)
from .renderers import OrjsonRenderer

logger = logging.getLogger(__name__)


api = NinjaAPI(
    title="canopy-web API",
    version="2.0.0",
    description=(
        "Pydantic-typed API surface for canopy-web. "
        "Replaces the legacy /api/ DRF endpoints. "
        "Errors are RFC 7807 application/problem+json."
    ),
    urls_namespace="api_v2",
    renderer=OrjsonRenderer(),
    docs_url=None,  # Scalar is mounted separately in config/urls.py
    openapi_url="/openapi.json",
)


def _problem_response(request: HttpRequest, problem: Problem) -> HttpResponse:
    body = problem.model_dump(exclude_none=True)
    response = HttpResponse(
        content=OrjsonRenderer().render(request, body, response_status=problem.status),
        status=problem.status,
        content_type="application/problem+json",
    )
    return response


@api.exception_handler(ProblemError)
def _on_problem_error(request: HttpRequest, exc: ProblemError) -> HttpResponse:
    problem = Problem(
        type=exc.problem_type,
        title=exc.problem_title,
        status=exc.status_code,
        detail=exc.problem_detail,
        instance=request.path,
        extras=exc.problem_extras,
    )
    return _problem_response(request, problem)


@api.exception_handler(ValidationError)
def _on_validation_error(request: HttpRequest, exc: ValidationError) -> HttpResponse:
    problem = Problem(
        type=TYPE_VALIDATION,
        title="Request validation failed",
        status=422,
        detail="One or more fields failed validation.",
        instance=request.path,
        extras={"errors": exc.errors},
    )
    return _problem_response(request, problem)


@api.exception_handler(AuthenticationError)
def _on_auth_error(request: HttpRequest, exc: AuthenticationError) -> HttpResponse:
    problem = Problem(
        type=TYPE_AUTH,
        title="Authentication required",
        status=401,
        detail="This endpoint requires an authenticated session.",
        instance=request.path,
    )
    return _problem_response(request, problem)


@api.exception_handler(HttpError)
def _on_http_error(request: HttpRequest, exc: HttpError) -> HttpResponse:
    """Bare HttpError (raised from handlers using ninja's shortcut) → problem+json."""
    problem = Problem(
        type="about:blank",
        title=exc.message if hasattr(exc, "message") else "HTTP error",
        status=exc.status_code,
        detail=str(exc) if str(exc) else None,
        instance=request.path,
    )
    return _problem_response(request, problem)


@api.exception_handler(Http404)
def _on_http404(request: HttpRequest, exc: Http404) -> HttpResponse:
    """Django Http404 (from get_object_or_404) → problem+json."""
    problem = Problem(
        type=TYPE_NOT_FOUND,
        title="Not found",
        status=404,
        detail=str(exc) if str(exc) else None,
        instance=request.path,
    )
    return _problem_response(request, problem)


@api.exception_handler(Exception)
def _on_unhandled(request: HttpRequest, exc: Exception) -> HttpResponse:
    logger.exception("Unhandled exception in v2 handler")
    problem = Problem(
        type=TYPE_INTERNAL,
        title="Internal server error",
        status=500,
        detail="An unexpected error occurred.",
        instance=request.path,
    )
    return _problem_response(request, problem)
```

- [ ] **Step 5: Commit**

```bash
git add apps/api/__init__.py apps/api/errors.py apps/api/renderers.py apps/api/api.py
git commit -m "feat(api): add Ninja v2 namespace + RFC 7807 problem+json error model"
```

### Task 0.3: Mount /api/v2/ in URL conf

**Files:**
- Modify: `config/urls.py`

- [ ] **Step 1: Read current URL conf**

Open `config/urls.py`. Locate the existing `urlpatterns` list and the `path("api/me/", ...)` entry.

- [ ] **Step 2: Add v2 mount**

Add (just before the SPA catch-all, after every other `path("api/...")` entry):

```python
from apps.api.api import api as api_v2

urlpatterns = [
    ...,  # existing entries
    path("api/v2/", api_v2.urls),
    # ...SPA catch-all stays last
]
```

- [ ] **Step 3: Add the public-path allowlist entry**

Edit `apps/common/middleware.py`:

```python
PUBLIC_PATH_PREFIXES = (
    "/accounts/",
    "/admin/",
    "/health/",
    "/static/",
    "/api/csrf/",
    "/api/auth/e2e-login/",
    "/api/v2/openapi.json",  # NEW — needed for openapi-typescript to fetch the schema
    "/api/v2/docs/",          # NEW — Scalar HTML
    "/api/v2/redoc/",         # NEW — Redoc HTML
)
```

(The OpenAPI schema endpoint and docs pages must be readable without auth so external tools and CI can read them.)

- [ ] **Step 4: Verify it starts**

Run: `uv run python manage.py runserver 0.0.0.0:8000`
Open: `http://localhost:8000/api/v2/openapi.json`
Expected: returns a valid OpenAPI 3.1 JSON document with `info.title == "canopy-web API"` and zero paths (no routers registered yet).

- [ ] **Step 5: Create tests dir + write smoke tests**

```python
# apps/api/tests/__init__.py
```

```python
# apps/api/tests/test_smoke.py
import pytest
from django.test import Client


@pytest.mark.django_db
def test_openapi_schema_serves():
    client = Client()
    response = client.get("/api/v2/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    assert payload["info"]["title"] == "canopy-web API"
    assert payload["openapi"].startswith("3.1")


@pytest.mark.django_db
def test_unknown_route_returns_problem_json():
    client = Client()
    response = client.get("/api/v2/does-not-exist")
    assert response.status_code == 404
```

- [ ] **Step 6: Run smoke tests**

Run: `uv run pytest apps/api/tests/test_smoke.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add config/urls.py apps/common/middleware.py apps/api/tests/
git commit -m "feat(api): mount Django Ninja v2 at /api/v2/ with smoke tests"
```

### Task 0.4: Wire Scalar + Redoc docs UI

**Files:**
- Create: `apps/api/views.py`
- Modify: `config/urls.py`

- [ ] **Step 1: Create the Scalar/Redoc views**

```python
# apps/api/views.py
"""Static docs UI views — Scalar (primary) and Redoc (reference).

Scalar fetches /api/v2/openapi.json client-side and renders it; no
Python deps needed beyond Django.
"""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse

_SCALAR_HTML = """<!doctype html>
<html>
<head>
  <title>canopy-web API — Scalar</title>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
</head>
<body>
  <script id="api-reference" data-url="/api/v2/openapi.json"></script>
  <script>
    var configuration = {
      theme: "default",
      layout: "modern",
      hideDownloadButton: false,
      searchHotKey: "k",
    };
    document.getElementById("api-reference").dataset.configuration =
      JSON.stringify(configuration);
  </script>
  <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
</body>
</html>
"""

_REDOC_HTML = """<!doctype html>
<html>
<head>
  <title>canopy-web API — Redoc</title>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>body { margin: 0; padding: 0; }</style>
</head>
<body>
  <redoc spec-url="/api/v2/openapi.json"></redoc>
  <script src="https://cdn.jsdelivr.net/npm/redoc/bundles/redoc.standalone.js"></script>
</body>
</html>
"""


def scalar_docs(request: HttpRequest) -> HttpResponse:
    return HttpResponse(_SCALAR_HTML, content_type="text/html; charset=utf-8")


def redoc_docs(request: HttpRequest) -> HttpResponse:
    return HttpResponse(_REDOC_HTML, content_type="text/html; charset=utf-8")
```

- [ ] **Step 2: Mount docs routes**

Edit `config/urls.py`:

```python
from apps.api.views import redoc_docs, scalar_docs

urlpatterns = [
    ...,
    path("api/v2/", api_v2.urls),
    path("api/v2/docs/", scalar_docs, name="api_docs_scalar"),
    path("api/v2/redoc/", redoc_docs, name="api_docs_redoc"),
    ...
]
```

- [ ] **Step 3: Smoke test the docs pages**

Add to `apps/api/tests/test_smoke.py`:

```python
@pytest.mark.django_db
def test_scalar_docs_serves_html():
    client = Client()
    response = client.get("/api/v2/docs/")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    assert b"api-reference" in response.content


@pytest.mark.django_db
def test_redoc_docs_serves_html():
    client = Client()
    response = client.get("/api/v2/redoc/")
    assert response.status_code == 200
    assert b"redoc" in response.content
```

- [ ] **Step 4: Run and verify**

Run: `uv run pytest apps/api/tests/test_smoke.py -v`
Expected: 4 passed.

Open `http://localhost:8000/api/v2/docs/` — Scalar should render (empty endpoints list at this stage).

- [ ] **Step 5: Commit**

```bash
git add apps/api/views.py config/urls.py apps/api/tests/test_smoke.py
git commit -m "feat(api): mount Scalar + Redoc docs UI for v2 OpenAPI schema"
```

### Task 0.5: Auth integration — Django session auth for Ninja

**Files:**
- Create: `apps/api/auth.py`
- Modify: `apps/api/api.py`
- Modify: `apps/api/tests/test_smoke.py`

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/test_smoke.py`:

```python
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_session_auth_rejects_anonymous(client):
    response = client.get("/api/v2/_auth_smoke/")
    assert response.status_code == 401
    body = response.json()
    assert body["status"] == 401
    assert body["type"].endswith("/auth")


@pytest.mark.django_db
def test_session_auth_accepts_logged_in_user(client):
    user = User.objects.create_user(
        username="alice", email="alice@dimagi.com", password="pw"
    )
    client.force_login(user)
    response = client.get("/api/v2/_auth_smoke/")
    assert response.status_code == 200
    assert response.json() == {"email": "alice@dimagi.com"}
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest apps/api/tests/test_smoke.py::test_session_auth_rejects_anonymous -v`
Expected: FAIL — route doesn't exist yet.

- [ ] **Step 3: Create the auth class**

```python
# apps/api/auth.py
"""Session-cookie auth for Django Ninja routes.

Trusts `request.user` populated by Django's auth middleware
(django-allauth sits on top of this). Raises
`ProblemError(401, "Authentication required")` when no user
is attached. Matches the standard Django auth model — Ninja
sees `request.user` exactly as a DRF view does.

The upstream `LoginRequiredMiddleware` already short-circuits
anonymous /api/ requests with a 401 JSON response. This auth
class is defense-in-depth + lets the schema declare auth.
"""
from __future__ import annotations

from django.http import HttpRequest
from ninja.security import SessionAuth

from .errors import TYPE_AUTH, ProblemError


class DjangoSessionAuth(SessionAuth):
    """Session auth that raises problem+json instead of returning None.

    Special-case: requests pre-authorized by the Bearer-token bypass
    in `apps/common/middleware.py` (writes to /api/projects/*/actions/
    + /api/projects/*/context/, reads of /api/projects/slugs/ +
    /api/insights/) carry `_workbench_token_auth = True`. We accept
    those even without an authenticated user.
    """

    def authenticate(self, request: HttpRequest, key: str | None) -> object | None:
        if getattr(request, "_workbench_token_auth", False):
            return getattr(request, "user", None)  # may be AnonymousUser — that's fine
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise ProblemError(
                401,
                "Authentication required",
                type_=TYPE_AUTH,
                detail="This endpoint requires an authenticated session.",
            )
        return user


session_auth = DjangoSessionAuth()
```

- [ ] **Step 4: Add the smoke route + enable CSRF**

Edit `apps/api/api.py`. Change the `NinjaAPI(...)` constructor to add `csrf=True`. Then below the exception handlers, add:

```python
from .auth import session_auth


@api.get("/_auth_smoke/", auth=session_auth, response={200: dict})
def _auth_smoke(request: HttpRequest) -> dict:
    """Internal smoke route — verifies session auth works."""
    return {"email": request.user.email}
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest apps/api/tests/test_smoke.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/auth.py apps/api/api.py apps/api/tests/test_smoke.py
git commit -m "feat(api): wire Django session auth + CSRF into v2 with problem+json 401"
```

### Task 0.6: Bearer-token middleware compatibility test

This task verifies that `LoginRequiredMiddleware`'s Bearer-token bypass continues to work after Ninja routes are registered. The Bearer bypass sets `request._dont_enforce_csrf_checks = True` and `request._workbench_token_auth = True` — Ninja's CSRF + session auth must respect both.

**Files:**
- Create: `apps/api/tests/test_bearer_compat.py`

- [ ] **Step 1: Write the test**

```python
# apps/api/tests/test_bearer_compat.py
"""Smoke tests: Bearer-token bypass continues to work for Ninja routes.

LoginRequiredMiddleware admits machine callers presenting a Bearer
token on a narrow allowlist (projects/*/actions/, projects/*/context/,
projects/slugs/, insights/). It sets `_workbench_token_auth = True`
and `_dont_enforce_csrf_checks = True` before handing off; Ninja's
CSRF + session_auth must honor both.

These tests use the smoke route under /api/v2/_auth_smoke/ — it's
NOT on the bypass allowlist, so we can't test the real flow here.
Real Bearer compatibility is covered by per-app contract tests in
Phase 2 (Task 2.3 — projects bearer-readable endpoints).

Instead we test the auth class directly: a request carrying
_workbench_token_auth=True bypasses the is_authenticated check.
"""
from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from apps.api.auth import session_auth


def test_session_auth_accepts_anonymous_when_bearer_authed():
    rf = RequestFactory()
    request = rf.get("/api/v2/_anything")
    request.user = AnonymousUser()
    request._workbench_token_auth = True
    # Should not raise; should return whatever request.user is.
    result = session_auth.authenticate(request, None)
    assert result is request.user


def test_session_auth_rejects_anonymous_without_bearer_marker():
    from apps.api.errors import ProblemError

    rf = RequestFactory()
    request = rf.get("/api/v2/_anything")
    request.user = AnonymousUser()
    with pytest.raises(ProblemError) as exc_info:
        session_auth.authenticate(request, None)
    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run**

Run: `uv run pytest apps/api/tests/test_bearer_compat.py -v`
Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/test_bearer_compat.py
git commit -m "feat(api): verify Bearer-token bypass remains compatible with Ninja session auth"
```

### Task 0.7: Pagination helpers

**Files:**
- Create: `apps/api/pagination.py`
- Create: `apps/api/tests/test_pagination.py`

- [ ] **Step 1: Write the pagination test**

```python
# apps/api/tests/test_pagination.py
from apps.api.pagination import Page, paginate


def test_paginate_returns_page_with_metadata():
    items = list(range(95))
    page = paginate(items, offset=20, limit=25)
    assert isinstance(page, Page)
    assert page.items == list(range(20, 45))
    assert page.total == 95
    assert page.offset == 20
    assert page.limit == 25


def test_paginate_handles_overflow_gracefully():
    items = list(range(10))
    page = paginate(items, offset=50, limit=25)
    assert page.items == []
    assert page.total == 10


def test_paginate_defaults():
    items = list(range(5))
    page = paginate(items, offset=0, limit=100)
    assert page.items == items
    assert page.total == 5
```

- [ ] **Step 2: Implement**

```python
# apps/api/pagination.py
"""Offset/limit pagination shared across v2 list endpoints.

Every list endpoint declares its response as `Page[ItemSchema]` so
the OpenAPI schema knows the item type.
"""
from __future__ import annotations

from typing import Generic, Sequence, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)


def paginate(items: Sequence[T], *, offset: int, limit: int) -> Page[T]:
    total = len(items)
    sliced = list(items[offset : offset + limit])
    return Page(items=sliced, total=total, offset=offset, limit=limit)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest apps/api/tests/test_pagination.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add apps/api/pagination.py apps/api/tests/test_pagination.py
git commit -m "feat(api): add Page[T] pagination helper for v2"
```

### Task 0.8: ETag helpers

**Files:**
- Create: `apps/api/etag.py`
- Create: `apps/api/tests/test_etag.py`

- [ ] **Step 1: Write the ETag test**

```python
# apps/api/tests/test_etag.py
from django.http import HttpResponseNotModified
from django.test import RequestFactory

from apps.api.etag import compute_etag, maybe_not_modified


def test_compute_etag_stable_for_same_payload():
    e1 = compute_etag({"a": 1, "b": [2, 3]})
    e2 = compute_etag({"b": [2, 3], "a": 1})  # key order shouldn't matter
    assert e1 == e2


def test_compute_etag_changes_for_different_payload():
    e1 = compute_etag({"a": 1})
    e2 = compute_etag({"a": 2})
    assert e1 != e2


def test_maybe_not_modified_returns_304_on_match():
    rf = RequestFactory()
    etag = compute_etag({"a": 1})
    request = rf.get("/x", HTTP_IF_NONE_MATCH=etag)
    response = maybe_not_modified(request, etag)
    assert isinstance(response, HttpResponseNotModified)


def test_maybe_not_modified_returns_none_on_miss():
    rf = RequestFactory()
    request = rf.get("/x", HTTP_IF_NONE_MATCH='"different"')
    response = maybe_not_modified(request, compute_etag({"a": 1}))
    assert response is None


def test_maybe_not_modified_returns_none_without_header():
    rf = RequestFactory()
    request = rf.get("/x")
    response = maybe_not_modified(request, compute_etag({"a": 1}))
    assert response is None
```

- [ ] **Step 2: Implement**

```python
# apps/api/etag.py
"""ETag round-trip for v2 endpoints.

ETag is sha256 of the serialized response body with stable key
ordering. Returning `HttpResponseNotModified` short-circuits the
response writer and avoids re-serializing the body.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from django.http import HttpRequest, HttpResponseNotModified


def compute_etag(payload: Any) -> str:
    """sha256 of the canonically-serialized payload, wrapped in W/"..."."""
    serialized = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(serialized).hexdigest()
    return f'W/"{digest}"'


def maybe_not_modified(request: HttpRequest, etag: str) -> HttpResponseNotModified | None:
    """Return 304 if the request's If-None-Match matches `etag`, else None."""
    inm = request.headers.get("If-None-Match")
    if inm and inm == etag:
        response = HttpResponseNotModified()
        response["ETag"] = etag
        return response
    return None
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest apps/api/tests/ -v`
Expected: all pass (≥11 tests across the foundation).

- [ ] **Step 4: Commit**

```bash
git add apps/api/etag.py apps/api/tests/test_etag.py
git commit -m "feat(api): add ETag helpers for v2"
```

### Task 0.9: Phase 0 gate

- [ ] **Step 1: Run the entire foundation test suite**

Run: `uv run pytest apps/api/ -v`
Expected: every test passes; coverage spans schema serving, docs pages, session auth (happy + sad), bearer-bypass interop, pagination, ETag.

- [ ] **Step 2: Open `/api/v2/docs/` in a browser**

Verify Scalar renders. Only `_auth_smoke/` shows under endpoints — that's correct.

- [ ] **Step 3: Tag**

```bash
git tag api-v2-foundation
```

---

## Phase 1: Pydantic schema library

**Rebase checkpoint** — before starting Phase 1:

```bash
git fetch origin main
git rebase origin/main
gh pr list --state merged --search "walkthroughs" --limit 5
```

If new walkthroughs PRs landed since this plan was written (2026-05-26), inspect each merged PR's diff (`gh pr view <num> --json files`) and:
- New model fields → extend the relevant `Out` schema in Task 1.7.
- New endpoints → defer to Phase 2 (the new endpoint becomes a Task 2.7.X).
- New `apps/walkthroughs/serializers.py` shape → re-capture the `curl` payload before Task 1.7's round-trip test.

Define request/response shapes for every resource as Pydantic models. No views are migrated yet — just shapes. This phase locks naming, optionality, and nullability decisions before any endpoint is touched.

**Convention:** schemas live in `apps/<app>/schemas.py`. Read-only output schemas are suffixed `Out`; input schemas are suffixed `In`; "patch" schemas use `Patch`. Cross-cutting types live in `apps/common/schemas.py`.

**Capture-before-write discipline:** for each endpoint, run the current DRF endpoint with `curl` (logged in via the dev server) and save the JSON payload as a test fixture. Write the round-trip test against that exact dict before defining the schema. This guards against the "thin Pydantic outputs drop fields" trap ace-web hit in PR #346.

### Task 1.1: Cross-cutting schemas

**Files:**
- Create: `apps/common/schemas.py`
- Create: `apps/common/tests/__init__.py`
- Create: `apps/common/tests/test_schemas.py`

- [ ] **Step 1: Write the round-trip test**

```python
# apps/common/tests/test_schemas.py
import datetime as dt

from apps.common.schemas import StrictModel, TimestampMixin, UserRefOut


def test_user_ref_round_trip():
    raw = {"id": 42, "email": "alice@dimagi.com", "display_name": "Alice"}
    parsed = UserRefOut.model_validate(raw)
    assert parsed.email == "alice@dimagi.com"
    dumped = parsed.model_dump()
    assert dumped == raw


def test_user_ref_display_name_optional():
    parsed = UserRefOut.model_validate({"id": 1, "email": "a@b.com"})
    assert parsed.display_name is None


def test_timestamp_mixin_iso8601():
    when = dt.datetime(2026, 5, 26, 12, 0, tzinfo=dt.UTC)

    class _S(TimestampMixin):
        pass

    s = _S(created_at=when, updated_at=when)
    dumped = s.model_dump(mode="json")
    assert dumped["created_at"].endswith("Z") or "+00:00" in dumped["created_at"]


def test_strict_model_rejects_extra_fields():
    import pytest
    from pydantic import ValidationError

    class _S(StrictModel):
        a: int

    with pytest.raises(ValidationError):
        _S.model_validate({"a": 1, "rogue": 2})
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest apps/common/tests/test_schemas.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```python
# apps/common/schemas.py
"""Cross-cutting Pydantic schemas reused across canopy-web apps.

Conventions:
- Output schemas end in `Out`, input in `In`, patches in `Patch`.
- IDs that are slugs use `str`; numeric PKs use `int`.
- All datetimes are timezone-aware ISO-8601 (Pydantic v2 default).
- Optional fields use `T | None = None`; required fields have no default.
"""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, EmailStr


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",  # request bodies reject unknown fields
        from_attributes=True,  # allow ORM-instance hydration
        str_strip_whitespace=True,
    )


class TimestampMixin(BaseModel):
    created_at: dt.datetime
    updated_at: dt.datetime | None = None


class UserRefOut(StrictModel):
    """Minimal user reference for embedding in other responses."""

    id: int
    email: EmailStr
    display_name: str | None = None


class MeOut(StrictModel):
    """Response for /api/me/."""

    email: EmailStr
    name: str
    avatar_url: str
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest apps/common/tests/test_schemas.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/common/schemas.py apps/common/tests/
git commit -m "feat(api): add cross-cutting Pydantic schemas (StrictModel, UserRef, Me, TimestampMixin)"
```

### Task 1.2: Collections schemas

**Files:**
- Create: `apps/collections/schemas.py`
- Create: `apps/collections/tests/__init__.py`
- Create: `apps/collections/tests/test_schemas.py`

- [ ] **Step 1: Capture current DRF response shapes**

With the dev server running, mint a debug session cookie and capture:

```bash
# Replace <COOKIE> with one from /api/debug/mint-session/
curl -sS -b "sessionid=<COOKIE>" http://localhost:8000/api/collections/1/ | python -m json.tool > /tmp/collection_1.json
```

Save the exact response as a fixture you'll use in the round-trip test.

- [ ] **Step 2: Write the round-trip test**

```python
# apps/collections/tests/test_schemas.py
import pytest

from apps.collections.schemas import (
    CollectionCreateIn,
    CollectionOut,
    SourceCreateIn,
    SourceOut,
)


def test_collection_out_round_trip():
    raw = {
        "id": 1,
        "name": "Discovery call — ACME",
        "description": "Notes from 2026-05-20 call",
        "sources": [
            {
                "id": 5,
                "source_type": "transcript",
                "title": "session.jsonl",
                "content": "...",
                "metadata": {"messages": 12},
                "created_at": "2026-05-20T10:00:00Z",
            }
        ],
        "created_at": "2026-05-20T10:00:00Z",
        "updated_at": "2026-05-20T10:00:00Z",
    }
    parsed = CollectionOut.model_validate(raw)
    assert parsed.id == 1
    assert len(parsed.sources) == 1
    assert parsed.sources[0].source_type == "transcript"


def test_collection_create_validates_name():
    with pytest.raises(ValueError):
        CollectionCreateIn(name="")
    obj = CollectionCreateIn(name="X")
    assert obj.name == "X"


def test_source_create_validates_content_size():
    obj = SourceCreateIn(source_type="text", content="hello")
    assert obj.content == "hello"
    with pytest.raises(ValueError):
        SourceCreateIn(source_type="text", content="")
    with pytest.raises(ValueError):
        SourceCreateIn(source_type="text", content="x" * 1_000_001)


def test_source_type_literal():
    with pytest.raises(ValueError):
        SourceCreateIn(source_type="not-a-real-type", content="x")
```

- [ ] **Step 3: Implement**

```python
# apps/collections/schemas.py
"""Pydantic schemas for the /api/v2/collections surface."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field

from apps.common.schemas import StrictModel

SourceType = Literal["slack", "transcript", "document", "text"]

MAX_SOURCE_SIZE = 1_000_000  # 1MB — mirrors the DRF serializer limit


class SourceOut(StrictModel):
    id: int
    source_type: SourceType
    title: str = ""
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: dt.datetime


class SourceCreateIn(StrictModel):
    source_type: SourceType
    title: str = ""
    content: str = Field(min_length=1, max_length=MAX_SOURCE_SIZE)
    metadata: dict = Field(default_factory=dict)


class CollectionOut(StrictModel):
    id: int
    name: str
    description: str = ""
    sources: list[SourceOut]
    created_at: dt.datetime
    updated_at: dt.datetime


class CollectionCreateIn(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest apps/collections/tests/test_schemas.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/collections/schemas.py apps/collections/tests/
git commit -m "feat(api): add Pydantic schemas for collections"
```

### Task 1.3: Skills schemas

**Files:**
- Create: `apps/skills/schemas.py`
- Create: `apps/skills/tests/__init__.py`
- Create: `apps/skills/tests/test_schemas.py`

- [ ] **Step 1: Capture current response**

```bash
curl -sS -b "sessionid=<COOKIE>" http://localhost:8000/api/skills/ | python -m json.tool > /tmp/skills.json
curl -sS -b "sessionid=<COOKIE>" http://localhost:8000/api/skills/1/ | python -m json.tool > /tmp/skill_1.json
```

Note the exact shape of `eval_score`, `eval_trend`, `last_eval_at` (all nullable).

- [ ] **Step 2: Write the round-trip test**

```python
# apps/skills/tests/test_schemas.py
import pytest

from apps.skills.schemas import (
    AdapterIn,
    AdapterOut,
    SkillOut,
)


def test_skill_out_round_trip():
    raw = {
        "id": 1,
        "name": "discovery-call-debrief",
        "description": "Summarize a discovery call.",
        "definition": {"prompt": "...", "evals": []},
        "version": 3,
        "usage_count": 17,
        "eval_score": 0.82,
        "eval_trend": "improving",
        "last_eval_at": "2026-05-24T18:00:00Z",
        "created_at": "2026-04-12T10:00:00Z",
        "updated_at": "2026-05-24T18:00:00Z",
    }
    parsed = SkillOut.model_validate(raw)
    assert parsed.eval_trend == "improving"


def test_skill_out_null_evals():
    raw = {
        "id": 1,
        "name": "x",
        "description": "",
        "definition": {},
        "version": 1,
        "usage_count": 0,
        "eval_score": None,
        "eval_trend": None,
        "last_eval_at": None,
        "created_at": "2026-04-12T10:00:00Z",
        "updated_at": "2026-04-12T10:00:00Z",
    }
    parsed = SkillOut.model_validate(raw)
    assert parsed.eval_score is None


def test_adapter_in_validates_runtime():
    obj = AdapterIn(runtime="web")
    assert obj.runtime == "web"
    with pytest.raises(ValueError):
        AdapterIn(runtime="bogus")


def test_eval_trend_literal():
    obj = SkillOut.model_validate({
        "id": 1, "name": "x", "description": "", "definition": {},
        "version": 1, "usage_count": 0, "eval_score": None,
        "eval_trend": "declining", "last_eval_at": None,
        "created_at": "2026-04-12T10:00:00Z",
        "updated_at": "2026-04-12T10:00:00Z",
    })
    assert obj.eval_trend == "declining"
```

- [ ] **Step 3: Implement**

```python
# apps/skills/schemas.py
"""Pydantic schemas for the /api/v2/skills surface."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field

from apps.common.schemas import StrictModel

EvalTrend = Literal["improving", "declining", "stable"] | None
RuntimeName = Literal["web", "claude_code", "open_claw"]


class SkillOut(StrictModel):
    id: int
    name: str
    description: str = ""
    definition: dict
    version: int = Field(ge=1)
    usage_count: int = Field(ge=0)
    eval_score: float | None = None
    eval_trend: EvalTrend = None
    last_eval_at: dt.datetime | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class AdapterIn(StrictModel):
    runtime: RuntimeName


class AdapterOut(StrictModel):
    runtime: RuntimeName
    content: str  # rendered adapter artifact (string body)
    format: Literal["markdown", "json", "yaml"]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest apps/skills/tests/test_schemas.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/skills/schemas.py apps/skills/tests/
git commit -m "feat(api): add Pydantic schemas for skills"
```

### Task 1.4: Evals schemas

**Files:**
- Create: `apps/evals/schemas.py`
- Create: `apps/evals/tests/__init__.py`
- Create: `apps/evals/tests/test_schemas.py`

- [ ] **Step 1: Capture current responses**

```bash
curl -sS -b "sessionid=<COOKIE>" http://localhost:8000/api/evals/1/ | python -m json.tool > /tmp/eval_suite_1.json
curl -sS -b "sessionid=<COOKIE>" http://localhost:8000/api/evals/1/history/ | python -m json.tool > /tmp/eval_history_1.json
```

- [ ] **Step 2: Write the round-trip test**

```python
# apps/evals/tests/test_schemas.py
import pytest

from apps.evals.schemas import (
    EvalCaseCreateIn,
    EvalCaseOut,
    EvalCasePatchIn,
    EvalRunOut,
    EvalSuiteOut,
)


def test_eval_suite_round_trip():
    raw = {
        "id": 1,
        "cases": [
            {
                "id": 10,
                "name": "happy path",
                "input_data": {"prompt": "x"},
                "expected_output": {"text": "y"},
                "source_excerpt": "from session 3",
                "created_at": "2026-05-20T10:00:00Z",
            }
        ],
        "runs": [
            {
                "id": 100,
                "status": "completed",
                "results": {"pass": 5, "fail": 0},
                "overall_score": 1.0,
                "runtime": "web",
                "created_at": "2026-05-21T10:00:00Z",
            }
        ],
        "created_at": "2026-05-20T10:00:00Z",
    }
    parsed = EvalSuiteOut.model_validate(raw)
    assert parsed.cases[0].name == "happy path"
    assert parsed.runs[0].overall_score == 1.0


def test_eval_case_create_validation():
    with pytest.raises(ValueError):
        EvalCaseCreateIn(name="", input_data={}, expected_output={})
    obj = EvalCaseCreateIn(name="x", input_data={}, expected_output={})
    assert obj.name == "x"


def test_eval_case_patch_partial():
    obj = EvalCasePatchIn(name="renamed")
    dumped = obj.model_dump(exclude_unset=True)
    assert dumped == {"name": "renamed"}


def test_eval_run_status_literal():
    obj = EvalRunOut.model_validate({
        "id": 1,
        "status": "running",
        "results": {},
        "overall_score": None,
        "runtime": "claude_code",
        "created_at": "2026-05-21T10:00:00Z",
    })
    assert obj.status == "running"
```

- [ ] **Step 3: Implement**

```python
# apps/evals/schemas.py
"""Pydantic schemas for the /api/v2/evals surface."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field

from apps.common.schemas import StrictModel

EvalRunStatus = Literal["pending", "running", "completed", "failed"]
RuntimeName = Literal["web", "claude_code", "open_claw"]


class EvalCaseOut(StrictModel):
    id: int
    name: str
    input_data: dict
    expected_output: dict
    source_excerpt: str = ""
    created_at: dt.datetime


class EvalCaseCreateIn(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    input_data: dict
    expected_output: dict
    source_excerpt: str = ""


class EvalCasePatchIn(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    input_data: dict | None = None
    expected_output: dict | None = None
    source_excerpt: str | None = None


class EvalRunOut(StrictModel):
    id: int
    status: EvalRunStatus
    results: dict
    overall_score: float | None = None
    runtime: RuntimeName = "web"
    created_at: dt.datetime


class EvalRunIn(StrictModel):
    """Body of POST /evals/<id>/run/."""
    runtime: RuntimeName = "web"


class EvalSuiteOut(StrictModel):
    id: int
    cases: list[EvalCaseOut]
    runs: list[EvalRunOut]
    created_at: dt.datetime
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest apps/evals/tests/test_schemas.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/evals/schemas.py apps/evals/tests/
git commit -m "feat(api): add Pydantic schemas for evals"
```

### Task 1.5: Projects schemas

**Files:**
- Create: `apps/projects/schemas.py`
- Create: `apps/projects/tests/__init__.py`
- Create: `apps/projects/tests/test_schemas.py`

- [ ] **Step 1: Capture current responses**

```bash
curl -sS -b "sessionid=<COOKIE>" http://localhost:8000/api/projects/ | python -m json.tool > /tmp/projects.json
curl -sS -b "sessionid=<COOKIE>" http://localhost:8000/api/projects/canopy-web/ | python -m json.tool > /tmp/project_detail.json
curl -sS -b "sessionid=<COOKIE>" http://localhost:8000/api/insights/ | python -m json.tool > /tmp/insights.json
```

Pay special attention to `latest_context`, `latest_actions`, `skills` (JSONField), and `insight_count`. Insight content uses the `[<category>]` prefix convention; preserve in the schema as a free-form string.

- [ ] **Step 2: Write the round-trip test**

```python
# apps/projects/tests/test_schemas.py
import pytest

from apps.projects.schemas import (
    BatchActionsIn,
    BatchContextIn,
    InsightOut,
    ProjectActionCreateIn,
    ProjectActionOut,
    ProjectActionSummaryOut,
    ProjectContextCreateIn,
    ProjectContextEntryOut,
    ProjectContextLatestOut,
    ProjectCreateIn,
    ProjectDetailOut,
    ProjectListOut,
    ProjectPatchIn,
    ProjectSlugOut,
)


def test_project_list_round_trip():
    raw = {
        "id": 1,
        "name": "canopy-web",
        "slug": "canopy-web",
        "repo_url": "https://github.com/dimagi/canopy",
        "deploy_url": "",
        "visibility": "public",
        "status": "active",
        "skills": [{"name": "discovery-call", "description": "X"}],
        "latest_context": {
            "current_work": {
                "content": "API modernization",
                "source": "session-review",
                "created_at": "2026-05-26T09:00:00Z",
            }
        },
        "latest_actions": {
            "session-review": {
                "status": "completed",
                "started_at": "2026-05-25T09:00:00Z",
                "completed_at": "2026-05-25T09:10:00Z",
            }
        },
        "insight_count": 3,
        "created_at": "2026-04-01T00:00:00Z",
        "updated_at": "2026-05-26T09:00:00Z",
    }
    parsed = ProjectListOut.model_validate(raw)
    assert parsed.slug == "canopy-web"
    assert "current_work" in parsed.latest_context


def test_project_create_slug_validation():
    obj = ProjectCreateIn(name="X", slug="canopy-web")
    assert obj.slug == "canopy-web"
    with pytest.raises(ValueError):
        ProjectCreateIn(name="X", slug="UPPERCASE")
    with pytest.raises(ValueError):
        ProjectCreateIn(name="X", slug="has spaces")


def test_project_patch_partial():
    obj = ProjectPatchIn(status="archived")
    dumped = obj.model_dump(exclude_unset=True)
    assert dumped == {"status": "archived"}


def test_insight_out_round_trip():
    raw = {
        "id": 100,
        "project_slug": "canopy-web",
        "project_name": "canopy-web",
        "content": "[ship_gap] Refactor branch open for 8 days",
        "source": "canopy:portfolio-review",
        "created_at": "2026-05-26T09:00:00Z",
    }
    parsed = InsightOut.model_validate(raw)
    assert parsed.content.startswith("[ship_gap]")


def test_batch_context_in_shape():
    obj = BatchContextIn.model_validate({
        "updates": {
            "canopy-web": [
                {"context_type": "current_work", "content": "x", "source": "y"}
            ]
        }
    })
    assert list(obj.updates.keys()) == ["canopy-web"]


def test_project_slug_out():
    parsed = ProjectSlugOut.model_validate({
        "slug": "canopy-web",
        "name": "canopy-web",
        "status": "active",
        "visibility": "public",
    })
    assert parsed.slug == "canopy-web"
```

- [ ] **Step 3: Implement**

```python
# apps/projects/schemas.py
"""Pydantic schemas for the /api/v2/projects + /api/v2/insights surface."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field

from apps.common.schemas import StrictModel

ProjectVisibility = Literal["public", "private"]
ProjectStatus = Literal["active", "stale", "archived"]
ProjectContextType = Literal["current_work", "next_step", "summary", "note", "insight"]
ActionStatus = Literal["started", "completed", "failed"]

SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


class ProjectSkillOut(StrictModel):
    name: str
    path: str = ""
    description: str = ""


class ProjectContextOut(StrictModel):
    """Latest-context entry value (no id — latest only)."""
    content: str
    source: str
    created_at: dt.datetime


class ProjectContextEntryOut(StrictModel):
    """Full context entry (with id — used by /context/ list)."""
    id: int
    context_type: ProjectContextType
    content: str
    source: str
    created_at: dt.datetime


class ProjectContextCreateIn(StrictModel):
    context_type: ProjectContextType
    content: str = Field(min_length=1)
    source: str = Field(min_length=1, max_length=100)


class ProjectActionLatestOut(StrictModel):
    status: ActionStatus
    started_at: dt.datetime
    completed_at: dt.datetime | None = None


class ProjectActionOut(StrictModel):
    id: int
    skill_name: str
    session_id: str = ""
    status: ActionStatus
    started_at: dt.datetime
    completed_at: dt.datetime | None = None
    duration_ms: int | None = None
    notes: str = ""
    created_at: dt.datetime


class ProjectActionCreateIn(StrictModel):
    skill_name: str = Field(min_length=1, max_length=100)
    session_id: str = ""
    status: ActionStatus = "started"
    started_at: dt.datetime
    completed_at: dt.datetime | None = None
    duration_ms: int | None = None
    notes: str = ""


class ProjectActionSummaryOut(StrictModel):
    skill_name: str
    status: ActionStatus
    started_at: dt.datetime
    completed_at: dt.datetime | None = None


class ProjectListOut(StrictModel):
    id: int
    name: str
    slug: str
    repo_url: str = ""
    deploy_url: str = ""
    visibility: ProjectVisibility
    status: ProjectStatus
    skills: list[ProjectSkillOut]
    latest_context: dict[str, ProjectContextOut]
    latest_actions: dict[str, ProjectActionLatestOut]
    insight_count: int = Field(ge=0)
    # walkthrough_count: int = Field(ge=0, default=0)  # add this when Task 9
    # of docs/superpowers/plans/2026-05-26-walkthrough-sharing.md lands.
    created_at: dt.datetime
    updated_at: dt.datetime


class ProjectDetailOut(ProjectListOut):
    """Detail view — same shape as list today. Diverge here if needed."""
    pass


class ProjectCreateIn(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=50, pattern=SLUG_PATTERN)
    repo_url: str = ""
    deploy_url: str = ""
    visibility: ProjectVisibility = "public"
    status: ProjectStatus = "active"
    skills: list[ProjectSkillOut] = Field(default_factory=list)


class ProjectPatchIn(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    repo_url: str | None = None
    deploy_url: str | None = None
    visibility: ProjectVisibility | None = None
    status: ProjectStatus | None = None
    skills: list[ProjectSkillOut] | None = None


class ProjectSlugOut(StrictModel):
    """Slim machine-readable shape from /api/v2/projects/slugs/."""
    slug: str
    name: str
    status: ProjectStatus
    visibility: ProjectVisibility


class ProjectContextLatestOut(StrictModel):
    contexts: dict[str, ProjectContextOut]


class BatchContextIn(StrictModel):
    """Body of POST /api/v2/projects/batch-context/.

    Each value is a list of ProjectContextCreateIn shapes.
    """
    updates: dict[str, list[ProjectContextCreateIn]]


class BatchActionsIn(StrictModel):
    """Body of POST /api/v2/projects/batch-actions/."""
    updates: dict[str, list[ProjectActionCreateIn]]


# --- Insights ----------------------------------------------------------


class InsightOut(StrictModel):
    id: int
    project_slug: str
    project_name: str
    content: str
    source: str
    created_at: dt.datetime


class InsightsClearOut(StrictModel):
    cleared: int


class InsightDismissOut(StrictModel):
    dismissed: int
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest apps/projects/tests/test_schemas.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/projects/schemas.py apps/projects/tests/
git commit -m "feat(api): add Pydantic schemas for projects + insights"
```

### Task 1.6: Workspace schemas

**Files:**
- Create: `apps/workspace/schemas.py`
- Create: `apps/workspace/tests/__init__.py`
- Create: `apps/workspace/tests/test_schemas.py`

- [ ] **Step 1: Capture current responses**

```bash
curl -sS -b "sessionid=<COOKIE>" http://localhost:8000/api/workspace/ | python -m json.tool > /tmp/workspace_list.json
curl -sS -b "sessionid=<COOKIE>" http://localhost:8000/api/workspace/1/ | python -m json.tool > /tmp/workspace_detail.json
```

The streaming endpoints (`start_workspace`, `analyze_workspace`) produce `text/event-stream` payloads; capture a sample with `curl --no-buffer` and treat them separately — they have no Pydantic response shape.

- [ ] **Step 2: Write the round-trip test**

```python
# apps/workspace/tests/test_schemas.py
import pytest

from apps.workspace.schemas import (
    EditSkillIn,
    PublishSkillIn,
    WorkspaceSessionListItemOut,
    WorkspaceSessionOut,
)


def test_workspace_session_list_item():
    raw = {
        "id": 1,
        "collection_id": 5,
        "collection_name": "Discovery call — ACME",
        "status": "proposed",
        "skill_name": "discovery-debrief",
        "created_at": "2026-05-20T10:00:00Z",
        "updated_at": "2026-05-20T10:05:00Z",
    }
    parsed = WorkspaceSessionListItemOut.model_validate(raw)
    assert parsed.status == "proposed"
    assert parsed.skill_name == "discovery-debrief"


def test_workspace_session_list_item_null_skill_name():
    raw = {
        "id": 1,
        "collection_id": 5,
        "collection_name": "X",
        "status": "created",
        "skill_name": None,
        "created_at": "2026-05-20T10:00:00Z",
        "updated_at": "2026-05-20T10:00:00Z",
    }
    parsed = WorkspaceSessionListItemOut.model_validate(raw)
    assert parsed.skill_name is None


def test_workspace_session_out_round_trip():
    raw = {
        "id": 1,
        "collection_id": 5,
        "status": "editing",
        "proposed_approach": {"name": "x", "description": "y"},
        "proposed_eval_cases": [{"name": "case1"}],
        "skill_draft": {"prompt": "..."},
        "edit_history": [{"timestamp": "2026-05-20T10:00:00Z", "change": "renamed"}],
        "created_at": "2026-05-20T10:00:00Z",
        "updated_at": "2026-05-20T10:05:00Z",
    }
    parsed = WorkspaceSessionOut.model_validate(raw)
    assert parsed.status == "editing"


def test_edit_skill_in():
    obj = EditSkillIn(skill_draft={"prompt": "x"})
    assert obj.skill_draft["prompt"] == "x"


def test_publish_skill_in_optional():
    obj = PublishSkillIn()
    dumped = obj.model_dump(exclude_unset=True)
    assert dumped == {}
```

- [ ] **Step 3: Implement**

```python
# apps/workspace/schemas.py
"""Pydantic schemas for the /api/v2/workspace surface.

Streaming endpoints (POST /workspace/start/<id>/ and
POST /workspace/analyze/<id>/) produce text/event-stream and do
NOT have a Pydantic response schema. They're declared in apps/workspace/api.py
with `response=None` and documented inline.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field

from apps.common.schemas import StrictModel

WorkspaceStatus = Literal[
    "created", "analyzing", "proposed", "editing", "testing", "published"
]


class WorkspaceSessionListItemOut(StrictModel):
    id: int
    collection_id: int
    collection_name: str | None
    status: WorkspaceStatus
    skill_name: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class WorkspaceSessionOut(StrictModel):
    id: int
    collection_id: int
    status: WorkspaceStatus
    proposed_approach: dict = Field(default_factory=dict)
    proposed_eval_cases: list = Field(default_factory=list)
    skill_draft: dict = Field(default_factory=dict)
    edit_history: list = Field(default_factory=list)
    created_at: dt.datetime
    updated_at: dt.datetime


class EditSkillIn(StrictModel):
    skill_draft: dict
    note: str | None = None


class PublishSkillIn(StrictModel):
    """Optional override for the published skill name."""
    name: str | None = None
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest apps/workspace/tests/test_schemas.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/workspace/schemas.py apps/workspace/tests/
git commit -m "feat(api): add Pydantic schemas for workspace"
```

### Task 1.7: Walkthroughs schemas

**Files:**
- Create: `apps/walkthroughs/schemas.py`
- Create: `apps/walkthroughs/tests/__init__.py`
- Create: `apps/walkthroughs/tests/test_schemas.py`

The walkthroughs app shipped in PR #40 with DRF serializers in `apps/walkthroughs/serializers.py`. Mirror their field set exactly — `WalkthroughListItemSerializer`, `WalkthroughDetailSerializer`, `WalkthroughUpdateSerializer` — then add Pydantic counterparts.

- [ ] **Step 1: Capture current responses**

```bash
# With a debug session cookie:
curl -sS -b "sessionid=<COOKIE>" http://localhost:8000/api/walkthroughs/ | python -m json.tool > /tmp/walkthroughs_list.json
curl -sS -b "sessionid=<COOKIE>" "http://localhost:8000/api/walkthroughs/?mine=true" | python -m json.tool > /tmp/walkthroughs_mine.json
# Detail capture requires an existing row; create one via the test fixture or admin first.
```

Pay attention to: `id` is a UUID (string in JSON), `project_slug` is nullable, `share_token` is `null` for non-owners (and missing entirely on list responses), `duration_sec` is nullable.

- [ ] **Step 2: Write the round-trip test**

```python
# apps/walkthroughs/tests/test_schemas.py
import uuid

import pytest

from apps.walkthroughs.schemas import (
    WalkthroughDetailOut,
    WalkthroughListItemOut,
    WalkthroughPatchIn,
    WalkthroughRotateTokenOut,
    WalkthroughUploadIn,
)


def test_walkthrough_list_item_round_trip():
    raw = {
        "id": str(uuid.uuid4()),
        "title": "ACE demo",
        "description": "Walkthrough of the opp workbench",
        "kind": "html",
        "project_slug": "ace-web",
        "visibility": "private",
        "owner_email": "alice@dimagi.com",
        "size_bytes": 12345,
        "duration_sec": None,
        "created_at": "2026-05-26T10:00:00Z",
        "updated_at": "2026-05-26T10:00:00Z",
    }
    parsed = WalkthroughListItemOut.model_validate(raw)
    assert parsed.kind == "html"
    assert parsed.project_slug == "ace-web"


def test_walkthrough_detail_out_owner_shape():
    raw = {
        "id": str(uuid.uuid4()),
        "title": "Demo",
        "description": "",
        "kind": "video",
        "project_slug": None,
        "visibility": "link",
        "owner_email": "alice@dimagi.com",
        "size_bytes": 9999,
        "duration_sec": 42,
        "share_token": "abc123",
        "content_type": "video/mp4",
        "is_owner": True,
        "created_at": "2026-05-26T10:00:00Z",
        "updated_at": "2026-05-26T10:00:00Z",
    }
    parsed = WalkthroughDetailOut.model_validate(raw)
    assert parsed.is_owner is True
    assert parsed.share_token == "abc123"


def test_walkthrough_detail_out_non_owner_null_token():
    parsed = WalkthroughDetailOut.model_validate({
        "id": str(uuid.uuid4()),
        "title": "Demo",
        "description": "",
        "kind": "html",
        "project_slug": None,
        "visibility": "private",
        "owner_email": "bob@dimagi.com",
        "size_bytes": 1,
        "duration_sec": None,
        "share_token": None,
        "content_type": "text/html",
        "is_owner": False,
        "created_at": "2026-05-26T10:00:00Z",
        "updated_at": "2026-05-26T10:00:00Z",
    })
    assert parsed.share_token is None


def test_walkthrough_kind_literal():
    with pytest.raises(ValueError):
        WalkthroughListItemOut.model_validate({
            "id": str(uuid.uuid4()),
            "title": "x", "description": "", "kind": "bogus",
            "project_slug": None, "visibility": "private",
            "owner_email": "a@b.com", "size_bytes": 0, "duration_sec": None,
            "created_at": "2026-05-26T10:00:00Z",
            "updated_at": "2026-05-26T10:00:00Z",
        })


def test_walkthrough_upload_in_kind_validation():
    obj = WalkthroughUploadIn(kind="html")
    assert obj.kind == "html"
    with pytest.raises(ValueError):
        WalkthroughUploadIn(kind="invalid")


def test_walkthrough_patch_partial():
    obj = WalkthroughPatchIn(visibility="link")
    dumped = obj.model_dump(exclude_unset=True)
    assert dumped == {"visibility": "link"}


def test_rotate_token_out():
    obj = WalkthroughRotateTokenOut(share_token="newtok")
    assert obj.share_token == "newtok"
```

- [ ] **Step 3: Implement**

```python
# apps/walkthroughs/schemas.py
"""Pydantic schemas for the /api/v2/walkthroughs surface.

Mirror the field set from apps/walkthroughs/serializers.py — the
walkthroughs app shipped in PR #40 (2026-05-26) with DRF serializers
that this replaces.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import EmailStr, Field

from apps.common.schemas import StrictModel

WalkthroughKind = Literal["html", "video"]
WalkthroughVisibility = Literal["private", "link"]


class WalkthroughListItemOut(StrictModel):
    id: uuid.UUID
    title: str
    description: str = ""
    kind: WalkthroughKind
    project_slug: str | None = None
    visibility: WalkthroughVisibility
    owner_email: EmailStr
    size_bytes: int = Field(ge=0)
    duration_sec: int | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class WalkthroughDetailOut(WalkthroughListItemOut):
    """Detail view adds share_token (owner only), content_type, is_owner."""
    share_token: str | None = None
    content_type: str
    is_owner: bool


class WalkthroughUploadIn(StrictModel):
    """Form-encoded body of POST /walkthroughs/ (alongside the multipart file).

    Used to validate the non-file form fields; the actual file comes
    through Ninja's UploadedFile primitive on the handler.
    """
    title: str = ""
    kind: WalkthroughKind
    project_slug: str = ""
    description: str = ""
    visibility: WalkthroughVisibility = "private"


class WalkthroughPatchIn(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    project_slug: str | None = None  # may be set to null to detach
    visibility: WalkthroughVisibility | None = None


class WalkthroughRotateTokenOut(StrictModel):
    share_token: str
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest apps/walkthroughs/tests/test_schemas.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/walkthroughs/schemas.py apps/walkthroughs/tests/
git commit -m "feat(api): add Pydantic schemas for walkthroughs"
```

### Task 1.8: Common (AI backend + auth) schemas

**Files:**
- Modify: `apps/common/schemas.py`
- Modify: `apps/common/tests/test_schemas.py`

- [ ] **Step 1: Capture current responses**

```bash
curl -sS -b "sessionid=<COOKIE>" http://localhost:8000/api/ai/status/ | python -m json.tool > /tmp/ai_status.json
curl -sS -b "sessionid=<COOKIE>" http://localhost:8000/api/me/ | python -m json.tool > /tmp/me.json
```

- [ ] **Step 2: Add the AI-backend round-trip test**

Append to `apps/common/tests/test_schemas.py`:

```python
from apps.common.schemas import (
    AiAuthCompleteIn,
    AiAuthCompleteOut,
    AiAuthPollOut,
    AiAuthStartOut,
    AiStatusOut,
    AiSwitchIn,
    AiSwitchOut,
    HealthOut,
    MeOut,
)


def test_health_out():
    parsed = HealthOut.model_validate({"status": "ok"})
    assert parsed.status == "ok"


def test_ai_status_out_round_trip():
    raw = {
        "backend": "api",
        "authenticated": True,
        "detail": "OK",
    }
    parsed = AiStatusOut.model_validate(raw)
    assert parsed.backend == "api"


def test_ai_switch_in_literal():
    AiSwitchIn(backend="api")
    AiSwitchIn(backend="cli")
    import pytest
    with pytest.raises(ValueError):
        AiSwitchIn(backend="bogus")


def test_me_out_round_trip():
    parsed = MeOut.model_validate({
        "email": "alice@dimagi.com",
        "name": "Alice",
        "avatar_url": "https://x.com/y.png",
    })
    assert parsed.email == "alice@dimagi.com"
```

- [ ] **Step 3: Extend the schemas module**

Append to `apps/common/schemas.py`:

```python
# --- Health ------------------------------------------------------------


class HealthOut(StrictModel):
    status: str


# --- AI backend (/api/ai/) --------------------------------------------

AiBackend = Literal["api", "cli"]


class AiStatusOut(StrictModel):
    backend: AiBackend
    authenticated: bool
    detail: str | None = None


class AiSwitchIn(StrictModel):
    backend: AiBackend


class AiSwitchOut(StrictModel):
    backend: AiBackend
    detail: str | None = None


class AiAuthStartOut(StrictModel):
    auth_url: str
    state: str


class AiAuthCompleteIn(StrictModel):
    code: str = Field(min_length=1)


class AiAuthCompleteOut(StrictModel):
    ok: bool
    detail: str | None = None


class AiAuthPollOut(StrictModel):
    state: Literal["idle", "pending", "ok", "error"]
    detail: str | None = None
```

Add the imports at the top of the file:

```python
from typing import Literal
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest apps/common/tests/test_schemas.py -v`
Expected: 8 passed (4 original + 4 new).

- [ ] **Step 5: Commit**

```bash
git add apps/common/schemas.py apps/common/tests/test_schemas.py
git commit -m "feat(api): add Pydantic schemas for AI backend + health"
```

### Task 1.9: Phase 1 gate

- [ ] **Step 1: Run every schema test**

Run: `uv run pytest -k "test_schemas" -v`
Expected: all per-app schema tests pass.

- [ ] **Step 2: Tag**

```bash
git tag api-v2-schemas-complete
```

---

## Phase 2: Endpoint migration

**Rebase checkpoint** — before starting Phase 2:

```bash
git fetch origin main
git rebase origin/main
gh pr list --state merged --search "walkthroughs" --limit 5
```

If new walkthroughs endpoints landed (especially **Task 8** of the walkthrough plan — `GET /w/<id>/content` streaming with HTTP Range), add a Task 2.7.X for each new endpoint. The streaming endpoint needs `response=None` + the SSE preservation pattern from Task 2.5.2.

Port endpoints app-by-app under `/api/v2/`. The full pattern is worked through for the projects `GET /api/v2/projects/` endpoint (Task 2.1.2) — the most complex single shape in the codebase. Subsequent endpoints follow the same pattern.

**Per-endpoint pattern:**

1. Write a contract test in `apps/<app>/tests/test_api.py` that hits the v2 URL and asserts:
   - HTTP status
   - Response body validates against the response Pydantic schema
   - Auth gating behaves correctly
   - On error: response is `application/problem+json` matching `Problem` shape
2. Write the Ninja handler in `apps/<app>/api.py`. Handler is thin: parse params → call existing helper (extract from the DRF view if needed) → return Pydantic model.
3. Run the contract test — expect it to pass.
4. Run the existing DRF test for the same endpoint — it should still pass (we have not touched DRF).
5. Commit.

### Task 2.1: Projects app migration

The projects surface has the largest response payload (`ProjectListOut` ≈ 14 fields, dict-of-typed-objects for `latest_context` and `latest_actions`). This is the worked example for the entire Phase 2.

**Files:**
- Create: `apps/projects/api.py`
- Create: `apps/projects/tests/test_api.py`
- Modify: `apps/api/api.py` (register router)

#### Task 2.1.1: Register the projects router

- [ ] **Step 1: Create the empty router module**

```python
# apps/projects/api.py
"""Django Ninja v2 router for the projects surface (+ insights).

Endpoints exposed via Bearer token in the LoginRequiredMiddleware bypass:
- GET /projects/slugs/        (read)
- POST /projects/<slug>/actions/  (write)
- POST/GET /projects/<slug>/context/  (write)
- POST /projects/batch-context/, POST /projects/batch-actions/  (write)
- GET /insights/              (read)

When `_workbench_token_auth = True` on the request, session_auth accepts
the call even though request.user is AnonymousUser.
"""
from __future__ import annotations

from ninja import Router

from apps.api.auth import session_auth

router = Router(auth=session_auth, tags=["projects"])
insights_router = Router(auth=session_auth, tags=["insights"])
```

- [ ] **Step 2: Register on the main NinjaAPI**

Edit `apps/api/api.py`. After the `_auth_smoke` route, add:

```python
from apps.projects.api import insights_router, router as projects_router

api.add_router("/projects", projects_router)
api.add_router("/insights", insights_router)
```

- [ ] **Step 3: Verify schema lists the tag**

Run: `curl -sS http://localhost:8000/api/v2/openapi.json | python -m json.tool | grep -A1 '"tags"' | head -20`
Expected: `"projects"` and `"insights"` appear.

- [ ] **Step 4: Commit**

```bash
git add apps/projects/api.py apps/api/api.py
git commit -m "feat(api): register projects + insights routers"
```

#### Task 2.1.2: Worked example — `GET /api/v2/projects/` (list projects)

This is the canonical per-endpoint task. All other endpoint tasks reference it.

- [ ] **Step 1: Write the contract test**

```python
# apps/projects/tests/test_api.py
import pytest
from django.contrib.auth import get_user_model

from apps.projects.models import Project, ProjectAction, ProjectContext
from apps.projects.schemas import ProjectListOut

User = get_user_model()


@pytest.fixture
def authed_client(db, client):
    user = User.objects.create_user(
        username="alice", email="alice@dimagi.com", password="pw"
    )
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_list_projects_returns_pydantic_validated_payload(authed_client):
    project = Project.objects.create(
        name="canopy-web", slug="canopy-web", status="active", visibility="public"
    )
    ProjectContext.objects.create(
        project=project,
        context_type="current_work",
        content="API modernization",
        source="session-review",
    )

    response = authed_client.get("/api/v2/projects/")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    # Validate every item round-trips through the Pydantic schema.
    items = [ProjectListOut.model_validate(item) for item in body["items"]]
    assert any(p.slug == "canopy-web" for p in items)


@pytest.mark.django_db
def test_list_projects_401_anonymous(db, client):
    response = client.get("/api/v2/projects/")
    assert response.status_code == 401
    assert response["Content-Type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 401
    assert body["type"].endswith("/auth")
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest apps/projects/tests/test_api.py -v`
Expected: tests FAIL — route doesn't exist; `404` on the path.

- [ ] **Step 3: Inspect the existing DRF implementation**

Open `apps/projects/views.py` and read `project_list`. Note the prefetch pattern, the `ProjectListSerializer` shape, and the `start_timing()` / `success_response()` envelope. The v2 handler must produce the same shape *under* `items` (because we wrap in `Page[T]`).

- [ ] **Step 4: Extract a clean service function**

In `apps/projects/views.py` the prefetch + serialize logic lives inside the view. Extract it to a pure function. Edit `apps/projects/views.py` to:

```python
def _build_project_list_data(qs):
    """Return [ProjectListOut-shaped dicts] for the given queryset.

    Extracted so the v2 Ninja handler can reuse the exact shape the DRF
    view returns, without duplicating prefetch + serialization logic.
    """
    qs = qs.prefetch_related(
        Prefetch(
            "contexts",
            queryset=ProjectContext.objects.order_by("-created_at"),
            to_attr="_prefetched_contexts",
        ),
        Prefetch(
            "actions",
            queryset=ProjectAction.objects.order_by("-started_at"),
            to_attr="_prefetched_actions",
        ),
    )
    return ProjectListSerializer(qs, many=True).data
```

Then have `project_list` call it. (No behavior change — pure refactor.)

- [ ] **Step 5: Implement the v2 handler**

Append to `apps/projects/api.py`:

```python
from django.http import HttpRequest

from apps.api.pagination import Page, paginate

from .models import Project
from .schemas import ProjectListOut
from .views import _build_project_list_data


@router.get("/", response=Page[ProjectListOut], summary="List projects")
def list_projects(
    request: HttpRequest,
    offset: int = 0,
    limit: int = 100,
) -> Page[ProjectListOut]:
    qs = Project.objects.all().order_by("-updated_at")
    serialized = _build_project_list_data(qs)
    items = [ProjectListOut.model_validate(item) for item in serialized]
    return paginate(items, offset=offset, limit=limit)
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest apps/projects/tests/test_api.py -v`
Expected: 2 passed.

- [ ] **Step 7: Verify the legacy DRF endpoint still works**

Run: `uv run pytest apps/projects/ -v --ignore=apps/projects/tests/test_api.py --ignore=apps/projects/tests/test_schemas.py`
Expected: every existing test still passes.

- [ ] **Step 8: Verify the OpenAPI schema is well-formed**

Run: `curl -sS http://localhost:8000/api/v2/openapi.json | python -c "import json, sys; d = json.load(sys.stdin); print('paths:', list(d['paths'].keys()))"`
Expected: includes `/projects/`.

Open `http://localhost:8000/api/v2/docs/` and confirm `GET /projects/` appears under the "projects" tag.

- [ ] **Step 9: Commit**

```bash
git add apps/projects/api.py apps/projects/views.py apps/projects/tests/test_api.py
git commit -m "feat(api): port GET /projects/ to v2 with contract tests"
```

#### Task 2.1.3 – 2.1.13: Remaining projects endpoints

For each endpoint below, follow the Task 2.1.2 pattern exactly: capture the current DRF response with `curl`, write the contract test (happy path + 401 + at least one error case), run-fail, extract a service helper if needed, implement the handler, run-pass, verify DRF still works, commit individually.

- [ ] **2.1.3** `POST /projects/` — create project.
   - Body: `ProjectCreateIn`. Response: `ProjectDetailOut` (201).
   - Errors: 409 on duplicate slug (map `IntegrityError`); 422 on bad slug.

- [ ] **2.1.4** `GET /projects/slugs/` — slim slug list (Bearer-readable).
   - Response: `list[ProjectSlugOut]`.
   - Contract test must include a Bearer-token case:
     ```python
     def test_slugs_accessible_via_bearer(db, client, settings):
         settings.WORKBENCH_WRITE_TOKEN = "test-token"
         Project.objects.create(name="x", slug="x", status="active")
         response = client.get(
             "/api/v2/projects/slugs/",
             HTTP_AUTHORIZATION="Bearer test-token",
         )
         assert response.status_code == 200
     ```

- [ ] **2.1.5** `POST /projects/seed/` — bulk seed (request body is `list[ProjectCreateIn]`; declare via `Body(list[ProjectCreateIn])`).
   - Response: `list[ProjectDetailOut]` (201).

- [ ] **2.1.6** `POST /projects/batch-context/` — batch context writes (Bearer-writable).
   - Body: `BatchContextIn`. Response: `dict[str, int]` (slug → entries created).
   - Bearer-token contract test: write to `/api/v2/projects/canopy-web/context/` via Bearer must succeed for slug paths that match the `/actions/` or `/context/` suffix.
   - **Path mismatch caveat:** the middleware's `_is_token_writable_path` checks the path *prefix* `/api/projects/`. After Phase 5 rename of `/api/v2/` → `/api/`, this is fine. During Phase 2, `/api/v2/projects/...` is **not** Bearer-writable. We'll update the middleware in Phase 5 Task 5.4 alongside the rename. **For now, document the limitation** in the contract test as a `@pytest.mark.xfail(reason="Bearer bypass updates in Phase 5.4")`.

- [ ] **2.1.7** `POST /projects/batch-actions/` — same shape; same Bearer caveat.

- [ ] **2.1.8** `GET /projects/<slug>/` — project detail.
   - Response: `ProjectDetailOut`. 404 → problem+json `TYPE_NOT_FOUND`.

- [ ] **2.1.9** `PATCH /projects/<slug>/` — update project.
   - Body: `ProjectPatchIn`. Response: `ProjectDetailOut`.

- [ ] **2.1.10** `DELETE /projects/<slug>/` — delete project. Response: 204 no body.

- [ ] **2.1.11** `GET /projects/<slug>/context/` + `POST /projects/<slug>/context/`.
   - List response: `list[ProjectContextEntryOut]`.
   - Create body: `ProjectContextCreateIn`. Create response: `ProjectContextEntryOut` (201).
   - Bearer-writable (same Phase-5 path-rename caveat as 2.1.6).

- [ ] **2.1.12** `GET /projects/<slug>/context/latest/` — latest entry per type. Response: `ProjectContextLatestOut`.

- [ ] **2.1.13** `GET /projects/<slug>/actions/` (with optional `?skill=` filter) + `POST /projects/<slug>/actions/`.
   - List response: `list[ProjectActionOut]`.
   - Create body: `ProjectActionCreateIn`. Response: `ProjectActionOut` (201).
   - Bearer-writable.

- [ ] **2.1.14** `GET /projects/<slug>/actions/summary/` — latest action per skill. Response: `list[ProjectActionSummaryOut]`.

- [ ] **2.1.15** `GET /insights/` (under the `insights_router`) — filterable by `category`, `source`, `project`, `limit`.
   - Response: `Page[InsightOut]`. Bearer-readable (works under `/api/v2/insights/` once middleware is updated in Phase 5.4 — for now mark as `xfail` like the project context endpoints).

- [ ] **2.1.16** `POST /insights/clear/` — Response: `InsightsClearOut`.

- [ ] **2.1.17** `DELETE /insights/<int:pk>/` — Response: `InsightDismissOut`. 404 on missing.

- [ ] **2.1.18 — Final regression**

Run: `uv run pytest apps/projects/ -v`
Expected: every existing test + every new contract test passes.

**Commit each endpoint individually** with `feat(api): port <METHOD> <path> to v2 with contract tests`.

### Task 2.2: Collections app migration

3 endpoints. Apply the Task 2.1.2 pattern per endpoint.

**Files:**
- Create: `apps/collections/api.py`
- Create: `apps/collections/tests/__init__.py`
- Create: `apps/collections/tests/test_api.py`
- Modify: `apps/api/api.py` (register router)

- [ ] **2.2.1** Register router: `api.add_router("/collections", collections_router)`.
- [ ] **2.2.2** `POST /collections/` — create collection. Body: `CollectionCreateIn`. Response: `CollectionOut` (201).
- [ ] **2.2.3** `GET /collections/<int:pk>/` — collection detail (with sources). Response: `CollectionOut`. 404 → problem+json.
- [ ] **2.2.4** `POST /collections/<int:pk>/sources/` — add source. Body: `SourceCreateIn`. Response: `SourceOut` (201). 422 on oversize content.
- [ ] **2.2.5** Final regression: `uv run pytest apps/collections/ -v`.
- [ ] **2.2.6** Commit each endpoint individually.

### Task 2.3: Skills app migration

3 endpoints.

**Files:**
- Create: `apps/skills/api.py`
- Create: `apps/skills/tests/__init__.py`
- Create: `apps/skills/tests/test_api.py`
- Modify: `apps/api/api.py`

- [ ] **2.3.1** Register router: `api.add_router("/skills", skills_router)`.
- [ ] **2.3.2** `GET /skills/` — paginated list. Response: `Page[SkillOut]`.
- [ ] **2.3.3** `GET /skills/<int:pk>/` — skill detail. Response: `SkillOut`. 404 → problem+json.
- [ ] **2.3.4** `POST /skills/<int:pk>/adapter/` — generate adapter for runtime. Body: `AdapterIn`. Response: `AdapterOut`.
- [ ] **2.3.5** Final regression: `uv run pytest apps/skills/ -v`.
- [ ] **2.3.6** Commit each endpoint individually.

### Task 2.4: Evals app migration

5 endpoints.

**Files:**
- Create: `apps/evals/api.py`
- Create: `apps/evals/tests/__init__.py`
- Create: `apps/evals/tests/test_api.py`
- Modify: `apps/api/api.py`

- [ ] **2.4.1** Register router: `api.add_router("/evals", evals_router)`.
- [ ] **2.4.2** `GET /evals/<int:skill_id>/` — eval suite detail (auto-create on first read; mirror current DRF behavior). Response: `EvalSuiteOut`.
- [ ] **2.4.3** `POST /evals/<int:skill_id>/run/` — kick off eval run. Body: `EvalRunIn`. Response: `EvalRunOut` (202 if async, 200 if sync — match current behavior).
- [ ] **2.4.4** `GET /evals/<int:skill_id>/history/` — historical runs. Response: `Page[EvalRunOut]`.
- [ ] **2.4.5** `POST /evals/<int:skill_id>/cases/` — add eval case. Body: `EvalCaseCreateIn`. Response: `EvalCaseOut` (201).
- [ ] **2.4.6** `PATCH /evals/<int:skill_id>/cases/<int:case_id>/` — edit case. Body: `EvalCasePatchIn`. Response: `EvalCaseOut`.
- [ ] **2.4.7** `DELETE /evals/<int:skill_id>/cases/<int:case_id>/` — remove case. Response: 204.
- [ ] **2.4.8** Final regression: `uv run pytest apps/evals/ -v`.
- [ ] **2.4.9** Commit each endpoint individually.

### Task 2.5: Workspace app migration

6 endpoints, including **two SSE endpoints** that need special handling.

**Files:**
- Create: `apps/workspace/api.py`
- Create: `apps/workspace/tests/__init__.py`
- Create: `apps/workspace/tests/test_api.py`
- Modify: `apps/api/api.py`

#### Task 2.5.1: Register router

- [ ] **Step 1: Create router**

```python
# apps/workspace/api.py
"""Django Ninja v2 router for the workspace surface.

Streaming endpoints (POST /start/<id>/ and POST /analyze/<id>/)
return Django StreamingHttpResponse directly. Ninja allows this
— they bypass the renderer and the OpenAPI response schema
declares `response=None`.
"""
from __future__ import annotations

from ninja import Router

from apps.api.auth import session_auth

router = Router(auth=session_auth, tags=["workspace"])
```

- [ ] **Step 2: Register**

In `apps/api/api.py` add:

```python
from apps.workspace.api import router as workspace_router

api.add_router("/workspace", workspace_router)
```

- [ ] **Step 3: Commit**

```bash
git add apps/workspace/api.py apps/api/api.py
git commit -m "feat(api): register workspace router"
```

#### Task 2.5.2: SSE preservation — `POST /workspace/start/<int:collection_id>/`

The current DRF view returns `StreamingHttpResponse(stream_workspace_analysis(...), content_type="text/event-stream")`. The migration must preserve the **byte-exact event stream**.

- [ ] **Step 1: Write a contract test that asserts the response is an SSE stream**

```python
# apps/workspace/tests/test_api.py
import pytest
from django.contrib.auth import get_user_model

from apps.collections.models import Collection

User = get_user_model()


@pytest.fixture
def authed_client(db, client):
    user = User.objects.create_user(
        username="alice", email="alice@dimagi.com", password="pw"
    )
    client.force_login(user)
    return client


@pytest.fixture
def collection(db):
    return Collection.objects.create(name="x")


@pytest.mark.django_db
def test_start_workspace_returns_event_stream(authed_client, collection, monkeypatch):
    # Stub the streaming generator so the test doesn't call Anthropic.
    def fake_stream(*args, **kwargs):
        yield b"event: start\ndata: {}\n\n"
        yield b"event: done\ndata: {}\n\n"

    monkeypatch.setattr("apps.workspace.api.stream_workspace_analysis", fake_stream)

    response = authed_client.post(f"/api/v2/workspace/start/{collection.pk}/")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/event-stream")
    body = b"".join(response.streaming_content)
    assert b"event: start" in body
    assert b"event: done" in body


@pytest.mark.django_db
def test_start_workspace_401_anonymous(db, client, collection):
    response = client.post(f"/api/v2/workspace/start/{collection.pk}/")
    assert response.status_code == 401
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest apps/workspace/tests/test_api.py::test_start_workspace_returns_event_stream -v`
Expected: FAIL — route doesn't exist.

- [ ] **Step 3: Implement**

Append to `apps/workspace/api.py`:

```python
from django.http import HttpRequest, StreamingHttpResponse
from django.shortcuts import get_object_or_404

from apps.collections.models import Collection

from .stream import stream_re_proposal, stream_workspace_analysis


@router.post(
    "/start/{collection_id}/",
    response=None,  # streaming; no Pydantic body
    summary="Start workspace analysis (SSE stream)",
    description=(
        "Returns a text/event-stream of `event:` / `data:` SSE frames "
        "as the AI analyzes the collection sources. The stream emits "
        "incremental tokens followed by terminal `event: done`."
    ),
)
def start_workspace(request: HttpRequest, collection_id: int) -> StreamingHttpResponse:
    collection = get_object_or_404(Collection, pk=collection_id)
    return StreamingHttpResponse(
        stream_workspace_analysis(collection),
        content_type="text/event-stream",
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest apps/workspace/tests/test_api.py -v`
Expected: 2 passed.

- [ ] **Step 5: Manual SSE smoke**

In a real browser, with the dev server running and logged in:
- Open DevTools Network tab, filter EventStream.
- Go to a collection page, click "Start workspace" (or hit `/api/v2/workspace/start/<id>/` directly).
- Verify the stream emits `event:` / `data:` frames identical to the legacy `/api/workspace/start/<id>/` endpoint. Side-by-side `diff` is reliable here.

- [ ] **Step 6: Commit**

```bash
git add apps/workspace/api.py apps/workspace/tests/test_api.py
git commit -m "feat(api): port POST /workspace/start/<id>/ SSE to v2"
```

#### Task 2.5.3 – 2.5.7: Remaining workspace endpoints

- [ ] **2.5.3** `POST /workspace/analyze/<int:collection_id>/` — same SSE pattern as 2.5.2 (uses `stream_re_proposal`). Mirror the SSE test.
- [ ] **2.5.4** `GET /workspace/` — list sessions with `?status=`, `?collection=`, `?limit=` filters. Response: `Page[WorkspaceSessionListItemOut]`.
- [ ] **2.5.5** `GET /workspace/<int:session_id>/` — session detail. Response: `WorkspaceSessionOut`.
- [ ] **2.5.6** `PATCH /workspace/<int:session_id>/edit/` — edit skill draft. Body: `EditSkillIn`. Response: `WorkspaceSessionOut`.
- [ ] **2.5.7** `POST /workspace/<int:session_id>/publish/` — publish skill. Body: `PublishSkillIn` (optional name override). Response: `SkillOut` (201).

- [ ] **2.5.8** Final regression: `uv run pytest apps/workspace/ -v`.
- [ ] **2.5.9** Commit each endpoint individually.

### Task 2.6: Common app migration (AI backend + auxiliary)

5 AI backend endpoints + `/api/me/` + `/health/`.

**Files:**
- Create: `apps/common/api.py`
- Create: `apps/common/tests/test_api.py`
- Modify: `apps/api/api.py`

- [ ] **2.6.1** Register two routers:

```python
# apps/common/api.py
from ninja import Router
from apps.api.auth import session_auth

ai_router = Router(auth=session_auth, tags=["ai"])
common_router = Router(auth=session_auth, tags=["common"])
public_router = Router(tags=["public"])  # health — no auth
```

In `apps/api/api.py`:

```python
from apps.common.api import ai_router, common_router, public_router
api.add_router("/ai", ai_router)
api.add_router("", common_router)
api.add_router("", public_router)
```

- [ ] **2.6.2** `GET /me/` — current user. Response: `MeOut`. 401 → problem+json.
   - Source: existing `config/views.py::me_view`. Port the avatar-from-socialaccount logic; keep `config/views.py::me_view` alive in parallel (it's behind `/api/me/`, not `/api/v2/me/`).

- [ ] **2.6.3** `GET /health/` — `auth=None` on the route. Response: `HealthOut`.

- [ ] **2.6.4** `GET /ai/status/` — Response: `AiStatusOut`.

- [ ] **2.6.5** `POST /ai/switch/` — Body: `AiSwitchIn`. Response: `AiSwitchOut`.

- [ ] **2.6.6** `POST /ai/auth/start/` — Response: `AiAuthStartOut`.

- [ ] **2.6.7** `POST /ai/auth/complete/` — Body: `AiAuthCompleteIn`. Response: `AiAuthCompleteOut`.

- [ ] **2.6.8** `GET /ai/auth/poll/` — Response: `AiAuthPollOut`.

- [ ] **2.6.9** Final regression: `uv run pytest apps/common/ -v`.
- [ ] **2.6.10** Commit each endpoint individually.

### Task 2.7: Walkthroughs app migration

6 endpoints from the PR #40 surface. The upload endpoint is multipart (form fields + `UploadedFile`). The DRF implementation maps custom error codes — preserve them as distinct problem+json types (`TYPE_PAYLOAD_TOO_LARGE`, `TYPE_DRIVE_NOT_CONFIGURED`, `TYPE_DRIVE_UPLOAD_FAILED`) so callers can branch on `problem.type`.

**Files:**
- Create: `apps/walkthroughs/api.py`
- Create: `apps/walkthroughs/tests/test_api.py`
- Modify: `apps/api/api.py` (register router)

#### Task 2.7.1: Register the walkthroughs router

- [ ] **Step 1: Create empty router**

```python
# apps/walkthroughs/api.py
"""Django Ninja v2 router for the walkthroughs surface.

Mirrors apps/walkthroughs/views.py (DRF, shipped in PR #40) but emits
Pydantic-typed responses + problem+json on errors.
"""
from __future__ import annotations

from django.conf import settings
from django.http import Http404
from ninja import Router

from apps.api.auth import session_auth

router = Router(auth=session_auth, tags=["walkthroughs"])


def _require_enabled() -> None:
    """Honor the WALKTHROUGHS_ENABLED rollout flag."""
    if not getattr(settings, "WALKTHROUGHS_ENABLED", True):
        raise Http404("walkthroughs disabled")
```

- [ ] **Step 2: Register**

In `apps/api/api.py` add:

```python
from apps.walkthroughs.api import router as walkthroughs_router

api.add_router("/walkthroughs", walkthroughs_router)
```

- [ ] **Step 3: Commit**

```bash
git add apps/walkthroughs/api.py apps/api/api.py
git commit -m "feat(api): register walkthroughs router"
```

#### Task 2.7.2: `POST /walkthroughs/` — multipart upload

Worked example for the multipart pattern. Ninja's `File` + `Form` primitives carry the upload metadata.

- [ ] **Step 1: Write the contract test**

```python
# apps/walkthroughs/tests/test_api.py
import io

import pytest
from django.contrib.auth import get_user_model

from apps.walkthroughs.models import Walkthrough
from apps.walkthroughs.schemas import WalkthroughDetailOut

User = get_user_model()


@pytest.fixture
def authed_client(db, client):
    user = User.objects.create_user(
        username="alice", email="alice@dimagi.com", password="pw"
    )
    client.force_login(user)
    return client, user


@pytest.fixture
def fake_drive(monkeypatch):
    """Patch storage.store_upload to skip real Drive calls."""
    from apps.walkthroughs import storage

    class Stored:
        file_id = "drive-file-1"
        folder_id = "drive-folder-1"

    monkeypatch.setattr(storage, "store_upload", lambda **kwargs: Stored)
    return Stored


@pytest.mark.django_db
def test_upload_walkthrough_html(authed_client, fake_drive):
    client, user = authed_client
    upload = io.BytesIO(b"<html>...</html>")
    upload.name = "demo.html"
    response = client.post(
        "/api/v2/walkthroughs/",
        {
            "file": upload,
            "title": "ACE demo",
            "kind": "html",
            "project_slug": "ace-web",
            "visibility": "link",
        },
    )
    assert response.status_code == 201
    body = response.json()
    parsed = WalkthroughDetailOut.model_validate(body)
    assert parsed.kind == "html"
    assert parsed.is_owner is True
    assert parsed.share_token is not None  # auto-minted when visibility=link


@pytest.mark.django_db
def test_upload_requires_file(authed_client):
    client, _ = authed_client
    response = client.post("/api/v2/walkthroughs/", {"kind": "html"})
    assert response.status_code == 422
    assert response["Content-Type"].startswith("application/problem+json")


@pytest.mark.django_db
def test_upload_rejects_invalid_kind(authed_client, fake_drive):
    client, _ = authed_client
    upload = io.BytesIO(b"x")
    upload.name = "demo.html"
    response = client.post(
        "/api/v2/walkthroughs/",
        {"file": upload, "kind": "bogus"},
    )
    assert response.status_code == 422


@pytest.mark.django_db
def test_upload_oversize_returns_413(authed_client, settings):
    settings.WALKTHROUGH_MAX_UPLOAD_BYTES = 10  # 10 bytes
    client, _ = authed_client
    upload = io.BytesIO(b"way too much content for the limit")
    upload.name = "demo.html"
    response = client.post(
        "/api/v2/walkthroughs/",
        {"file": upload, "kind": "html"},
    )
    assert response.status_code == 413
    body = response.json()
    assert body["type"].endswith("/payload-too-large")


@pytest.mark.django_db
def test_upload_drive_not_configured_returns_500(authed_client, monkeypatch):
    from apps.walkthroughs import storage
    from apps.walkthroughs.drive_client import DriveNotConfigured

    def boom(**kwargs):
        raise DriveNotConfigured("no SA key")

    monkeypatch.setattr(storage, "store_upload", boom)
    client, _ = authed_client
    upload = io.BytesIO(b"x")
    upload.name = "demo.html"
    response = client.post(
        "/api/v2/walkthroughs/",
        {"file": upload, "kind": "html"},
    )
    assert response.status_code == 500
    body = response.json()
    assert body["type"].endswith("/drive-not-configured")
    # No orphan row should remain.
    assert Walkthrough.objects.count() == 0
```

- [ ] **Step 2: Implement**

```python
# Append to apps/walkthroughs/api.py
from django.conf import settings
from django.http import HttpRequest
from ninja import File, Form
from ninja.files import UploadedFile

from apps.api.errors import (
    TYPE_DRIVE_NOT_CONFIGURED,
    TYPE_DRIVE_UPLOAD_FAILED,
    TYPE_PAYLOAD_TOO_LARGE,
    TYPE_VALIDATION,
    ProblemError,
)

from . import storage
from .drive_client import DriveNotConfigured
from .models import Walkthrough
from .schemas import (
    WalkthroughDetailOut,
    WalkthroughKind,
    WalkthroughVisibility,
)

CONTENT_TYPE_BY_KIND = {"html": "text/html", "video": "video/mp4"}
FILENAME_BY_KIND = {"html": "slideshow.html", "video": "video.mp4"}


@router.post("/", response={201: WalkthroughDetailOut}, summary="Upload a walkthrough")
def upload_walkthrough(
    request: HttpRequest,
    file: UploadedFile = File(...),
    title: str = Form(""),
    kind: WalkthroughKind = Form(...),
    project_slug: str = Form(""),
    description: str = Form(""),
    visibility: WalkthroughVisibility = Form("private"),
):
    _require_enabled()

    max_bytes = getattr(
        settings, "WALKTHROUGH_MAX_UPLOAD_BYTES", 75 * 1024 * 1024
    )
    if file.size > max_bytes:
        raise ProblemError(
            413,
            "Upload too large",
            type_=TYPE_PAYLOAD_TOO_LARGE,
            detail=f"upload exceeds {max_bytes} bytes",
        )

    content_type = CONTENT_TYPE_BY_KIND[kind]
    data = file.read()
    final_title = (title.strip() or file.name)[:200]

    # Same two-step pattern as the DRF view: create row first for UUID,
    # then attempt the Drive write. On failure delete the row.
    w = Walkthrough.objects.create(
        title=final_title,
        description=description.strip(),
        kind=kind,
        project_slug=project_slug.strip() or None,
        owner=request.user,
        visibility=visibility,
        drive_file_id="",
        drive_folder_id="",
        content_type=content_type,
        size_bytes=len(data),
    )
    try:
        stored = storage.store_upload(
            walkthrough_id=str(w.id),
            filename=FILENAME_BY_KIND[kind],
            content_type=content_type,
            data=data,
        )
    except DriveNotConfigured as e:
        w.delete()
        raise ProblemError(
            500,
            "Drive not configured",
            type_=TYPE_DRIVE_NOT_CONFIGURED,
            detail=str(e),
        )
    except Exception as e:
        w.delete()
        raise ProblemError(
            502,
            "Drive upload failed",
            type_=TYPE_DRIVE_UPLOAD_FAILED,
            detail=str(e),
        )

    w.drive_file_id = stored.file_id
    w.drive_folder_id = stored.folder_id
    w.save(update_fields=["drive_file_id", "drive_folder_id", "updated_at"])
    if visibility == "link":
        w.ensure_share_token()

    body = _detail_payload(w, is_owner=True)
    return 201, body


def _detail_payload(w: Walkthrough, *, is_owner: bool) -> dict:
    """Build the WalkthroughDetailOut-shaped dict from a Walkthrough row.

    Token is null for non-owners regardless of model state.
    """
    return {
        "id": w.id,
        "title": w.title,
        "description": w.description,
        "kind": w.kind,
        "project_slug": w.project_slug,
        "visibility": w.visibility,
        "owner_email": w.owner.email,
        "size_bytes": w.size_bytes,
        "duration_sec": w.duration_sec,
        "share_token": w.share_token if is_owner else None,
        "content_type": w.content_type,
        "is_owner": is_owner,
        "created_at": w.created_at,
        "updated_at": w.updated_at,
    }
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest apps/walkthroughs/tests/test_api.py -v`
Expected: 5 passed.

- [ ] **Step 4: Verify the DRF endpoint still works**

Run: `uv run pytest tests/test_walkthroughs_views.py -v`
Expected: 13 passed (the PR #40 baseline).

- [ ] **Step 5: Commit**

```bash
git add apps/walkthroughs/api.py apps/walkthroughs/tests/
git commit -m "feat(api): port POST /walkthroughs/ multipart upload to v2 with contract tests"
```

#### Task 2.7.3 – 2.7.7: Remaining walkthrough endpoints

Follow the Task 2.7.2 pattern.

- [ ] **2.7.3** `GET /walkthroughs/` — list with `?project=`, `?kind=`, `?mine=true` filters. Response: `list[WalkthroughListItemOut]` (no pagination in the DRF baseline — match it; wrap in `Page[T]` only if the data set grows).

- [ ] **2.7.4** `GET /walkthroughs/<uuid:wid>/` — detail. Response: `WalkthroughDetailOut`. 404 → problem+json. `share_token` masked to `null` for non-owners. **Reuse `_detail_payload(w, is_owner=...)` from Task 2.7.2.**

- [ ] **2.7.5** `PATCH /walkthroughs/<uuid:wid>/` — owner-only update. Body: `WalkthroughPatchIn`. Response: `WalkthroughDetailOut`. 403 → problem+json `TYPE_FORBIDDEN` for non-owner. Auto-mint `share_token` when visibility flips to `"link"` (mirror DRF behavior — call `ensure_share_token()` after save).

- [ ] **2.7.6** `DELETE /walkthroughs/<uuid:wid>/` — owner-only. 204 no body. Best-effort `storage.delete_stored` call (swallow `DriveNotConfigured` and generic exceptions to keep ORM-vs-Drive in sync; log only).

- [ ] **2.7.7** `POST /walkthroughs/<uuid:wid>/rotate-token/` — owner-only. Response: `WalkthroughRotateTokenOut`.

- [ ] **2.7.8** **Disabled-flag contract test**

The DRF view raises `Http404` via `_require_enabled()` when `WALKTHROUGHS_ENABLED=False`. Add a contract test that flips the setting and asserts all six v2 endpoints return 404 problem+json:

```python
@pytest.mark.django_db
def test_endpoints_404_when_disabled(authed_client, settings):
    settings.WALKTHROUGHS_ENABLED = False
    client, _ = authed_client
    for path in [
        "/api/v2/walkthroughs/",
        f"/api/v2/walkthroughs/{uuid.uuid4()}/",
        f"/api/v2/walkthroughs/{uuid.uuid4()}/rotate-token/",
    ]:
        for method in ["get", "post", "patch", "delete"]:
            response = getattr(client, method)(path)
            if response.status_code != 405:  # method not allowed is fine
                assert response.status_code == 404
```

- [ ] **2.7.9 — Final regression**

Run: `uv run pytest apps/walkthroughs/ tests/test_walkthroughs_*.py -v`
Expected: every contract test passes AND every PR #40 test still passes.

- [ ] **2.7.10** Commit each endpoint individually.

> **Forward-looking note for Phase 4 (frontend cutover):** The walkthroughs frontend client (Task 10 of `docs/superpowers/plans/2026-05-26-walkthrough-sharing.md`, **not yet shipped**) will land as `frontend/src/api/walkthroughs.ts`. When it does, add a Phase 4 task — `frontend/src/api/walkthroughs.ts` migration — using the Task 4.1 pattern. Multipart upload from the frontend uses native `FormData` + the typed client's `bodySerializer` override; example will live in the walkthrough plan.

> **Forward-looking note for Tasks 8-14 (future walkthrough plan tasks):** Task 8 introduces `GET /w/<uuid>/content` (HTTP Range streaming for the public viewer) — this is mounted **outside** `/api/walkthroughs/`. When it lands, port it as a streaming Ninja handler with `response=None` (same SSE-style declaration as `POST /workspace/start/`). Token-based public access requires `LoginRequiredMiddleware` allowlist updates parallel to the existing Bearer bypass.

### Task 2.8: Backend-side cutover gate

- [ ] **Step 1: Full backend test sweep**

Run: `uv run pytest -v`
Expected: every existing test passes; every new `test_api.py` test passes.

- [ ] **Step 2: Manual smoke**

Open `http://localhost:8000/api/v2/docs/`. Every endpoint listed should be tagged correctly. Click into 3-4 endpoints, use "Try it" to exercise them, verify responses match Pydantic schemas. The SSE endpoints in workspace should render with `text/event-stream` content type.

- [ ] **Step 3: Tag**

```bash
git tag api-v2-backend-complete
git commit --allow-empty -m "milestone: v2 backend complete, ~30 endpoints ported"
```

---

## Phase 3: Frontend type generation

Replace the hand-maintained types in `frontend/src/api/projects.ts` + `insights.ts` + the inline shapes in `client.ts` with types generated from the live v2 OpenAPI schema. Frontend still calls `/api/` (DRF) at this phase — type generation only.

### Task 3.1: Install generators

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Add devDeps**

```bash
cd frontend && npm install --save-dev openapi-typescript openapi-fetch
```

- [ ] **Step 2: Add generation script**

Edit `frontend/package.json` `scripts`:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "...",
    "preview": "...",
    "gen:api": "openapi-typescript http://localhost:8000/api/v2/openapi.json --output src/api/generated.ts --immutable"
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "feat(frontend): add openapi-typescript + openapi-fetch dependencies"
```

### Task 3.2: Generate the types + typed client

**Files:**
- Create: `frontend/src/api/generated.ts` (autogenerated)
- Create: `frontend/src/api/client.v2.ts`
- Create: `frontend/src/api/__tests__/client.v2.test.ts` (if vitest exists; otherwise type check via `tsc`)

- [ ] **Step 1: Generate against a live backend**

```bash
# In one terminal:
uv run honcho start -f Procfile.dev
# In another:
cd frontend && npm run gen:api
```

Expected: `frontend/src/api/generated.ts` created. Inspect it — it should contain `paths` + `components.schemas` matching the OpenAPI doc.

- [ ] **Step 2: Create the v2 client**

```typescript
// frontend/src/api/client.v2.ts
import createClient from "openapi-fetch";
import type { paths } from "./generated";

function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function redirectToLogin(): never {
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.href = `/accounts/google/login/?next=${next}`;
  throw new Error("Redirecting to login");
}

export const apiV2 = createClient<paths>({
  baseUrl: "/api/v2",
  credentials: "same-origin",
});

// Attach CSRF + 401 handling globally via middleware.
apiV2.use({
  async onRequest({ request }) {
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
      const token = getCsrfToken();
      if (token) request.headers.set("X-CSRFToken", token);
    }
    return request;
  },
  async onResponse({ response }) {
    if (response.status === 401) {
      redirectToLogin();
    }
    return response;
  },
});
```

- [ ] **Step 3: Quick type-check**

```bash
cd frontend && npm run build
```

Expected: clean tsc build. Type errors here usually mean the schema is missing a field — fix the schema, not the call site.

- [ ] **Step 4: Add the CI script to refresh generated types**

Create `.github/workflows/regen-openapi.yml`:

```yaml
name: Regenerate OpenAPI types

on:
  pull_request:
    paths:
      - "apps/**/api.py"
      - "apps/**/schemas.py"
      - "apps/api/**"

jobs:
  regen:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.ref }}
          token: ${{ secrets.GITHUB_TOKEN }}
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - name: Boot Django for schema dump
        run: |
          uv sync --extra dev
          uv run python -c "
          import django, json, os
          os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.production'
          django.setup()
          from apps.api.api import api
          with open('frontend/openapi.json', 'w') as f:
              json.dump(api.get_openapi_schema(), f, indent=2)
          "
      - name: Regenerate types
        working-directory: frontend
        run: |
          npm install
          npx openapi-typescript openapi.json --output src/api/generated.ts --immutable
      - name: Commit if changed
        run: |
          git config user.name "github-actions"
          git config user.email "github-actions@github.com"
          if ! git diff --quiet frontend/src/api/generated.ts; then
            git add frontend/src/api/generated.ts
            git commit -m "chore(api): regenerate OpenAPI types"
            git push
          fi
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/generated.ts frontend/src/api/client.v2.ts .github/workflows/regen-openapi.yml
git commit -m "feat(frontend): generate types from v2 OpenAPI + typed openapi-fetch client + regen CI"
```

---

## Phase 4: Frontend cutover

**Rebase checkpoint** — before starting Phase 4:

```bash
git fetch origin main
git rebase origin/main
ls frontend/src/api/  # has walkthroughs.ts landed?
ls frontend/src/pages/ | grep -i walk  # WalkthroughsPage / WalkthroughViewerPage?
```

If **Task 10** of the walkthrough plan landed (`frontend/src/api/walkthroughs.ts`), add a Task 4.3.7 migrating it to the typed `apiV2` client. Multipart upload pattern:

```typescript
async function uploadWalkthrough(form: FormData) {
  // openapi-fetch supports raw FormData via bodySerializer override.
  const { data, error } = await apiV2.POST("/walkthroughs/", {
    body: form as unknown as Record<string, never>,
    bodySerializer: (body) => body as FormData,
  });
  if (error) throw new Error("Upload failed");
  return data;
}
```

If **Tasks 11-12** landed (`WalkthroughsPage.tsx`, `WalkthroughViewerPage.tsx`), they consume the client above — they don't need direct migration but verify they render after the client swap.

Migrate each function in `frontend/src/api/*.ts` from the hand-written DRF caller to the typed v2 client. Page components don't change — they call the wrapper functions, whose signatures stay the same.

**Per-resource pattern:**

1. Pick one file in `frontend/src/api/` (start with `insights.ts` — smallest surface).
2. Rewrite each function to use `apiV2.GET/POST/PATCH/DELETE("/path", ...)`. Response data is already typed; remove all manual unwrapping of `data.data`.
3. Replace hand-written input/output types with `components["schemas"]["XOut"]`.
4. Run `npm run build` + manually exercise the affected pages in the browser.
5. Commit.

### Task 4.1: Insights client

**Files:**
- Modify: `frontend/src/api/insights.ts`

- [ ] **Step 1: Inspect current shape**

Open `frontend/src/api/insights.ts`. Note each exported function and the page components that consume them (grep for `from .*insights`).

- [ ] **Step 2: Rewrite using v2 client**

For every function, replace the fetch with `apiV2.GET("/insights/", { params: { query: {...} } })` etc. Remove the manual `data.success` unwrap.

Example:

```typescript
// frontend/src/api/insights.ts
import { apiV2 } from "./client.v2";
import type { components } from "./generated";

export type Insight = components["schemas"]["InsightOut"];

export interface InsightsFilters {
  category?: string;
  source?: string;
  project?: string;
  limit?: number;
}

export async function listInsights(filters: InsightsFilters = {}): Promise<Insight[]> {
  const { data, error } = await apiV2.GET("/insights/", {
    params: { query: filters as any },
  });
  if (error) throw new Error("Failed to load insights");
  return data.items;
}

export async function dismissInsight(id: number): Promise<void> {
  const { error } = await apiV2.DELETE("/insights/{id}/", {
    params: { path: { id } },
  });
  if (error) throw new Error("Failed to dismiss insight");
}

export async function clearInsights(source?: string): Promise<number> {
  const { data, error } = await apiV2.POST("/insights/clear/", {
    params: { query: source ? { source } : {} },
  });
  if (error) throw new Error("Failed to clear insights");
  return data.cleared;
}
```

- [ ] **Step 3: Build + test**

```bash
cd frontend && npm run build
```

Expected: clean build.

- [ ] **Step 4: Manual UI test**

Open `http://localhost:8000/insights`. The cross-portfolio feed should load, dismiss should work, clear should work. Also verify the dashboard's inline insights triage still renders (it consumes the same client).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/insights.ts
git commit -m "feat(frontend): migrate insights client to v2 typed openapi-fetch"
```

### Task 4.2: Projects client

**Files:**
- Modify: `frontend/src/api/projects.ts`

- [ ] **Step 1: Rewrite each function**

Apply the pattern from Task 4.1. The `Project` type becomes `components["schemas"]["ProjectListOut"]`; remove the hand-written interface.

- [ ] **Step 2: Build + test**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Manual UI test**

The whole dashboard (`/`) and project workbench tiles consume this. Verify: tile grid loads, "Today's top 3" hero renders, freshness chip works, inline insights triage works, tile order by insight count works.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/projects.ts
git commit -m "feat(frontend): migrate projects client to v2 typed openapi-fetch"
```

### Task 4.3: Split client.ts into per-resource files

`frontend/src/api/client.ts` currently bundles `api.createCollection`, `api.addSource`, `api.getCollection`, plus skills, evals, workspace, AI backend calls. Split each resource into its own file using the typed client.

- [ ] **4.3.1** `frontend/src/api/me.ts` — `getMe()` → `apiV2.GET("/me/")`. Update callers in `frontend/src/components/Layout.tsx` (or wherever `MeResponse` is imported).

- [ ] **4.3.2** `frontend/src/api/collections.ts` — `createCollection`, `getCollection`, `addSource`.

- [ ] **4.3.3** `frontend/src/api/skills.ts` — `listSkills`, `getSkill`, `generateAdapter`.

- [ ] **4.3.4** `frontend/src/api/evals.ts` — `getEvalSuite`, `runEval`, `getEvalHistory`, `addEvalCase`, `editEvalCase`, `deleteEvalCase`.

- [ ] **4.3.5** `frontend/src/api/workspace.ts` — `listWorkspaces`, `getWorkspace`, `editSkill`, `publishSkill`. The two SSE endpoints stay as raw `fetch` calls (openapi-fetch doesn't model streams cleanly):
   ```typescript
   export async function startWorkspaceStream(collectionId: number): Promise<Response> {
     const csrf = getCsrfToken();
     return fetch(`/api/v2/workspace/start/${collectionId}/`, {
       method: "POST",
       headers: { "X-CSRFToken": csrf },
       credentials: "same-origin",
     });
   }
   ```
   Pull `getCsrfToken` out into a shared utility (`frontend/src/api/csrf.ts`) since it's now needed in two places.

- [ ] **4.3.6** `frontend/src/api/ai.ts` — `aiStatus`, `aiSwitch`, `aiAuthStart`, `aiAuthComplete`, `aiAuthPoll`.

- [ ] **4.3.7** Run `npm run build` after each split; commit each split individually.

### Task 4.4: Delete the old client.ts shell

Once every function in `client.ts` has moved out:

- [ ] **Step 1: Verify no imports remain**

```bash
cd frontend && rg "from .*['\"].*api/client['\"]" src/
```

Expected: zero results.

- [ ] **Step 2: Delete**

```bash
rm frontend/src/api/client.ts
```

- [ ] **Step 3: Build + test**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(frontend): delete client.ts — functions moved to per-resource files"
```

### Task 4.5: Frontend cutover gate

- [ ] **Step 1: Full frontend regression**

```bash
cd frontend && npm run build
```

Expected: clean tsc build.

- [ ] **Step 2: End-to-end smoke**

Walk through every primary surface in a real browser. Each page should load and function identically to before:
- `/` — dashboard with "Today's top 3" hero + tile grid + inline triage
- `/insights` — cross-portfolio feed; dismiss + clear flows
- `/skills` — skill discovery feed; click into a skill detail
- `/workspaces` — workspace session list
- `/workspace/:sessionId` — workspace detail with edit + publish
- `/new` — create a new collection, start a workspace, **SSE stream renders incrementally**
- `/leaderboard` — eval improvement leaderboard
- `/guide` — walkthrough sample collection
- `/settings` — AI backend status + switch + headless CLI auth

- [ ] **Step 3: Tag**

```bash
git tag api-v2-frontend-complete
git commit --allow-empty -m "milestone: v2 frontend cutover complete"
```

---

## Phase 5: DRF removal + envelope cleanup + rename

Frontend no longer calls `/api/` (only `/api/v2/`). Delete DRF, the envelope module, the legacy URL conf entries, the `djangorestframework` dependency. Then rename `/api/v2/` → `/api/`.

### Task 5.1: Delete DRF view modules per app

For each app, delete the DRF view module(s), strip the URL conf entry, run tests, commit.

- [ ] **5.1.1 — collections**
   ```bash
   git rm apps/collections/views.py apps/collections/serializers.py apps/collections/urls.py
   ```
   Remove the include in `config/urls.py`.
   Run: `uv run pytest apps/collections/ -v` (only schema + api_v2 tests should remain).
   Commit: `chore(api): remove legacy DRF surface from collections`.

- [ ] **5.1.2 — skills** — same pattern.

- [ ] **5.1.3 — evals** — same pattern.

- [ ] **5.1.4 — workspace** — same pattern. Delete `apps/workspace/views.py`; the SSE handlers live in `apps/workspace/api.py` now.

- [ ] **5.1.5 — common (AI backend)** — delete `apps/common/views.py` (the AI backend views; `views_auth_e2e.py` and `views_debug.py` STAY). Delete `apps/common/urls.py`. Remove the include from `config/urls.py`.

- [ ] **5.1.6 — projects + insights** — delete `apps/projects/views.py`, `apps/projects/views_insights.py`, `apps/projects/serializers.py`, `apps/projects/urls.py`. Remove the inline `path("api/insights/...")` entries from `config/urls.py`.

- [ ] **5.1.6a — walkthroughs** — delete `apps/walkthroughs/views.py`, `apps/walkthroughs/serializers.py`, `apps/walkthroughs/urls.py`. Remove the include from `config/urls.py`. Also delete `tests/test_walkthroughs_views.py` (the DRF-specific test file from PR #40) — its coverage has been moved to `apps/walkthroughs/tests/test_api.py`. `tests/test_walkthroughs_models.py` + `tests/test_walkthroughs_drive.py` stay (they're transport-agnostic).

   **Note:** Task 2.1.2 introduced `_build_project_list_data` inside `apps/projects/views.py`. That helper now needs a new home — move it into `apps/projects/api.py` (or `apps/projects/_serializers.py` if it grows; prefer the former).

- [ ] **5.1.7 — config/views.py::me_view** — once `/api/v2/me/` is in use, delete `me_view` from `config/views.py` and remove the `path("api/me/", me_view, ...)` entry from `config/urls.py`. Keep `health_check`, `csrf_view`, and `spa_view` (these aren't Ninja-portable).

- [ ] **5.1.8 — final inventory check**

```bash
rg "from rest_framework|@api_view|serializers.ModelSerializer" apps/
```

Expected: zero results.

### Task 5.2: Delete the envelope module

**Files:**
- Delete: `apps/common/envelope.py`

- [ ] **Step 1: Verify no callers remain**

```bash
rg "from apps.common.envelope|success_response|error_response|start_timing" apps/ frontend/src/
```

Expected: zero results in `apps/`. (Frontend already stopped consuming `data.data` in Phase 4.) `views_debug.py` and `views_auth_e2e.py` were using `success_response`/`error_response` — port them to inline JSON responses (they're not REST API; the envelope was only ever scaffolding).

- [ ] **Step 2: Port the two debug/e2e views off the envelope**

Edit `apps/common/views_debug.py::mint_session`: replace `Response(success_response(...))` with `JsonResponse({...})` directly. Same for `error_response` → `JsonResponse({"detail": ...}, status=...)`.

Edit `apps/common/views_auth_e2e.py`: same migration.

- [ ] **Step 3: Delete**

```bash
git rm apps/common/envelope.py
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -v`
Expected: every test passes.

- [ ] **Step 5: Commit**

```bash
git add apps/common/views_debug.py apps/common/views_auth_e2e.py
git commit -m "chore(api): delete envelope module — replaced by problem+json + bare 2xx responses"
```

### Task 5.3: Remove DRF dependency

**Files:**
- Modify: `pyproject.toml`
- Modify: `config/settings/base.py`

- [ ] **Step 1: Remove `djangorestframework` from `pyproject.toml`**

Edit `pyproject.toml`:

```toml
# Remove this line:
"djangorestframework>=3.15,<4.0",
```

- [ ] **Step 2: Remove DRF from `INSTALLED_APPS` and the `REST_FRAMEWORK` setting**

Edit `config/settings/base.py`. Remove `"rest_framework"` from `INSTALLED_APPS`. Remove the entire `REST_FRAMEWORK = {...}` dict.

- [ ] **Step 3: Resync**

Run: `uv sync --extra dev`
Expected: clean install with DRF gone; uv.lock updates.

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -v`
Expected: every test passes.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock config/settings/base.py
git commit -m "chore(api): remove djangorestframework dependency"
```

### Task 5.4: Rename /api/v2/ → /api/ + update Bearer middleware

**Files:**
- Modify: `config/urls.py`
- Modify: `apps/api/api.py` (urls_namespace, docstrings)
- Modify: `apps/api/views.py` (Scalar/Redoc HTML)
- Modify: `apps/common/middleware.py` (public path allowlist, Bearer-readable allowlist)
- Modify: `frontend/src/api/client.v2.ts` (baseUrl)
- Modify: `.github/workflows/regen-openapi.yml` (schema URL)
- Modify: `frontend/package.json` (`gen:api` script URL)

- [ ] **Step 1: Change the mount**

Edit `config/urls.py`:

```python
# Before:
path("api/v2/", api_v2.urls),
path("api/v2/docs/", scalar_docs, ...),
path("api/v2/redoc/", redoc_docs, ...),

# After:
path("api/", api_v2.urls),
path("api/docs/", scalar_docs, ...),
path("api/redoc/", redoc_docs, ...),
```

- [ ] **Step 2: Update Ninja singleton**

Edit `apps/api/api.py`:
- `openapi_url="/openapi.json"` stays the same (relative; resolves to `/api/openapi.json`).
- Update the description string to drop the "/api/v2/" reference.

- [ ] **Step 3: Update Scalar/Redoc HTML**

Edit `apps/api/views.py` — change `data-url="/api/v2/openapi.json"` → `data-url="/api/openapi.json"`. Same for the Redoc spec-url.

- [ ] **Step 4: Update the middleware allowlist**

Edit `apps/common/middleware.py`:

```python
PUBLIC_PATH_PREFIXES = (
    "/accounts/",
    "/admin/",
    "/health/",
    "/static/",
    "/api/csrf/",
    "/api/auth/e2e-login/",
    "/api/openapi.json",  # was /api/v2/openapi.json
    "/api/docs/",          # was /api/v2/docs/
    "/api/redoc/",         # was /api/v2/redoc/
)
```

The existing Bearer-bypass allowlists already key off `/api/projects/` and `/api/insights/`, so they now match the renamed v2 paths automatically.

- [ ] **Step 5: Update frontend baseUrl**

Edit `frontend/src/api/client.v2.ts`:

```typescript
export const apiV2 = createClient<paths>({
  baseUrl: "/api",  // was "/api/v2"
  ...
});
```

(Optional renaming `client.v2.ts` → `client.ts` is pure churn — defer. Keep the file name; everyone knows what it means.)

- [ ] **Step 6: Update CI workflow + npm script**

Edit `.github/workflows/regen-openapi.yml`: workflow already uses `api.get_openapi_schema()` directly, no path change needed for the dump itself; verify the path filters still trigger on `apps/**/api.py` + `apps/**/schemas.py`.

Edit `frontend/package.json`:

```json
"gen:api": "openapi-typescript http://localhost:8000/api/openapi.json --output src/api/generated.ts --immutable"
```

- [ ] **Step 7: Re-mark xfail tests**

Find the `pytest.mark.xfail(reason="Bearer bypass updates in Phase 5.4")` markers added in Tasks 2.1.6, 2.1.7, 2.1.11, 2.1.13, 2.1.15 and remove the xfail decorators. Re-run those tests — they should now pass.

```bash
rg "Bearer bypass updates in Phase 5.4" apps/
```

For each match: remove the `@pytest.mark.xfail(...)` line above the test.

- [ ] **Step 8: Regenerate frontend types**

```bash
uv run honcho start -f Procfile.dev &
sleep 5
cd frontend && npm run gen:api
```

Open `frontend/src/api/generated.ts` and verify paths are now `/projects/` not `/v2/projects/`.

- [ ] **Step 9: Full test sweep**

```bash
uv run pytest -v
cd frontend && npm run build
```

Expected: all pass.

- [ ] **Step 10: Manual smoke**

Open `http://localhost:8000/api/docs/` (no more `/v2/`). Scalar should render. Hit `/api/projects/` directly — should respond. Hit `/api/v2/projects/` — should 404 now.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "chore(api): rename /api/v2/ to /api/ now that legacy DRF surface is gone"
```

### Task 5.5: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the "Architecture" section**

Replace the line about DRF with:

```markdown
- **Backend:** Django 5 ASGI + uvicorn, Django Ninja 1.x + Pydantic v2, PostgreSQL.
  OpenAPI 3.1 schema auto-generated at `/api/openapi.json`; Scalar UI at
  `/api/docs/`; Redoc at `/api/redoc/`. All errors return RFC 7807
  `application/problem+json`. Frontend TypeScript types are generated from the
  schema (`frontend/src/api/generated.ts`).
```

- [ ] **Step 2: Add to "Design Decisions"**

```markdown
- **API is Pydantic-first via Django Ninja**: every request/response is a Pydantic v2 model declared in `apps/<app>/schemas.py`. Routes live in `apps/<app>/api.py`, registered on the single `NinjaAPI` instance in `apps/api/api.py`. Errors are RFC 7807 `application/problem+json`. Frontend types are generated from the OpenAPI 3.1 schema by `openapi-typescript` into `frontend/src/api/generated.ts` and consumed via `openapi-fetch`. Contract tests run in CI via Schemathesis (Phase 6).
- **Streaming endpoints stay on Django**: `POST /api/workspace/start/<id>/` and `POST /api/workspace/analyze/<id>/` return `StreamingHttpResponse` directly from Ninja handlers. The SSE event format is the contract; OpenAPI declares them as `response=None`.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md to reflect Ninja + Pydantic + OpenAPI architecture"
```

### Task 5.6: Phase 5 gate

- [ ] **Step 1: Final regression**

```bash
uv run pytest -v
cd frontend && npm run build
```

- [ ] **Step 2: Tag**

```bash
git tag api-v2-cleanup-complete
git commit --allow-empty -m "milestone: DRF gone, /api/ namespace owned by Ninja"
```

---

## Phase 6: Schemathesis CI contract tests

Wire Schemathesis to fuzz the OpenAPI spec against a running app, and add the job to CI.

### Task 6.1: Install + write a baseline run

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/contract/__init__.py`
- Create: `tests/contract/test_schemathesis.py`

- [ ] **Step 1: Add dep**

Edit `pyproject.toml` `[project.optional-dependencies] dev`:

```toml
"schemathesis>=3.30,<4.0",
```

Run: `uv sync --extra dev`

- [ ] **Step 2: Write the runner**

```python
# tests/contract/test_schemathesis.py
"""Property-based contract tests: fuzz the OpenAPI spec against the running app.

Auto-generates a request for every (path × method) combination, hits the
endpoint, and asserts:
- response status matches one declared in the spec
- response body matches the declared response schema
- response content-type matches the spec

Auth-protected routes are skipped unless `SCHEMATHESIS_AUTH_COOKIE` is set
(populate via the e2e-login flow before running).
"""
from __future__ import annotations

import os

import schemathesis

SCHEMA_URL = os.environ.get(
    "SCHEMATHESIS_SCHEMA_URL", "http://localhost:8000/api/openapi.json"
)
AUTH_COOKIE = os.environ.get("SCHEMATHESIS_AUTH_COOKIE")

schema = schemathesis.from_uri(SCHEMA_URL)


@schema.parametrize()
def test_api_conforms_to_schema(case):
    headers: dict[str, str] = {}
    cookies: dict[str, str] = {}
    if AUTH_COOKIE:
        cookies["sessionid"] = AUTH_COOKIE
    response = case.call(headers=headers, cookies=cookies)
    case.validate_response(response)
```

- [ ] **Step 3: Add a `tests/contract/__init__.py`** (empty file).

- [ ] **Step 4: Run locally against public endpoints first**

```bash
uv run honcho start -f Procfile.dev &
sleep 5
uv run pytest tests/contract/test_schemathesis.py -v -k "health"
```

Expected: every health endpoint passes the spec conformance check.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/contract/
git commit -m "feat(api): add schemathesis contract tests baseline"
```

### Task 6.2: Wire CI job with auth bootstrapping

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add a new job**

Add to `.github/workflows/ci.yml` (alongside the existing test jobs):

```yaml
  contract-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: canopy_web
        ports: ["5432:5432"]
        options: --health-cmd pg_isready --health-interval 10s
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - run: uv sync --extra dev
      - name: Apply migrations
        run: uv run python manage.py migrate
        env:
          DATABASE_URL: postgres://postgres:postgres@localhost:5432/canopy_web
          DJANGO_SETTINGS_MODULE: config.settings.production
          SECRET_KEY: ci-secret
          ALLOWED_HOSTS: localhost,127.0.0.1
          CANOPY_E2E_AUTH_TOKEN: ci-fake-token
          AUTH_ALLOWED_EMAIL_DOMAIN: dimagi-ai.com
      - name: Start backend
        run: |
          uv run python manage.py runserver 0.0.0.0:8000 &
          sleep 5
        env:
          DATABASE_URL: postgres://postgres:postgres@localhost:5432/canopy_web
          DJANGO_SETTINGS_MODULE: config.settings.production
          SECRET_KEY: ci-secret
          ALLOWED_HOSTS: localhost,127.0.0.1
          CANOPY_E2E_AUTH_TOKEN: ci-fake-token
          AUTH_ALLOWED_EMAIL_DOMAIN: dimagi-ai.com
          REQUIRE_AUTH: "True"
      - name: Bootstrap test session
        run: |
          curl -c cookies.txt -X POST http://localhost:8000/api/auth/e2e-login/ \
            -H "Content-Type: application/json" \
            -d '{"email": "ace@dimagi-ai.com", "token": "ci-fake-token"}'
          echo "SCHEMATHESIS_AUTH_COOKIE=$(grep sessionid cookies.txt | awk '{print $7}')" >> $GITHUB_ENV
      - name: Run schemathesis
        run: uv run pytest tests/contract/test_schemathesis.py -v
```

- [ ] **Step 2: Commit + push to a PR + verify the job passes**

```bash
git add .github/workflows/ci.yml
git commit -m "feat(ci): add schemathesis contract test job"
```

Push and open a PR. Watch the `contract-tests` job. Each failure surfaces either a schema or a handler bug — fix whichever is wrong.

### Task 6.3: Iterate to green

- [ ] **Step 1: Read every schemathesis failure**

For each failure, classify:
- "Handler returns a field not in the schema" → add the field to the schema OR remove it from the handler.
- "Handler returns a wrong type" → fix the handler.
- "Endpoint returns a status not declared" → add the status to the handler's `response={...}` dict.

- [ ] **Step 2: Loop until green**

Run locally:

```bash
uv run honcho start -f Procfile.dev &
sleep 5
SCHEMATHESIS_AUTH_COOKIE=<value> uv run pytest tests/contract/test_schemathesis.py -v
```

Fix, commit, repeat. Each fix is its own commit: `fix(api): align <endpoint> with declared schema`.

- [ ] **Step 3: Once green, push, verify CI passes**

---

## Phase 7: FastMCP layer

Expose a curated set of v2 endpoints as MCP tools. AI agents (Claude Code, future LLM consumers) can call canopy-web routes as native tools.

### Task 7.1: Install FastMCP + wire a minimal server

**Files:**
- Modify: `pyproject.toml`
- Create: `apps/api/mcp_server.py`
- Modify: `config/urls.py`

- [ ] **Step 1: Add dep**

```toml
"fastmcp>=0.4,<1.0",
```

Run: `uv sync --extra dev`

- [ ] **Step 2: Create the MCP server module**

```python
# apps/api/mcp_server.py
"""FastMCP server exposing v2 routes as MCP tools.

Strategy: walk the live OpenAPI schema and register one MCP tool per
(path, method) marked `x-mcp-expose: true` in its OpenAPI extension.
Endpoints opt in via `openapi_extra={"x-mcp-expose": True}` on the
Ninja route decorator.

Each tool invokes the same endpoint via an HTTP loopback call with a
Bearer token for authentication — reuses every middleware (auth,
CSRF, throttling) and so behaves identically to a frontend caller.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from fastmcp import FastMCP

from .api import api as ninja_api

mcp = FastMCP("canopy-web")

BACKEND_BASE = os.environ.get("CANOPY_MCP_LOOPBACK_BASE", "http://localhost:8000")
BEARER = os.environ.get("CANOPY_MCP_BEARER", "")


def _build_tool(path: str, method: str, op: dict[str, Any], operation_id: str):
    @mcp.tool(name=operation_id, description=op.get("summary", ""))
    async def _tool(**kwargs: Any) -> Any:
        url_path = path
        path_params = {}
        for key, value in list(kwargs.items()):
            placeholder = "{" + key + "}"
            if placeholder in url_path:
                url_path = url_path.replace(placeholder, str(value))
                path_params[key] = kwargs.pop(key)
        url = f"{BACKEND_BASE}/api{url_path}"
        headers = {"Authorization": f"Bearer {BEARER}"} if BEARER else {}
        async with httpx.AsyncClient() as client:
            if method.lower() == "get":
                resp = await client.get(url, params=kwargs, headers=headers)
            else:
                resp = await client.request(method.upper(), url, json=kwargs, headers=headers)
        resp.raise_for_status()
        return resp.json()

    return _tool


def register_tools() -> None:
    """Walk the OpenAPI schema and register tools for opted-in endpoints."""
    schema = ninja_api.get_openapi_schema()
    for path, methods in schema["paths"].items():
        for method, op in methods.items():
            if method not in {"get", "post", "patch", "delete"}:
                continue
            if not op.get("x-mcp-expose"):
                continue
            operation_id = op.get("operationId") or f"{method}_{path.replace('/', '_')}"
            _build_tool(path, method, op, operation_id)


register_tools()
```

- [ ] **Step 3: Mount the MCP endpoint**

Edit `config/urls.py`:

```python
from apps.api.mcp_server import mcp

urlpatterns = [
    ...,
    path("api/mcp/", mcp.asgi_app()),
    ...
]
```

- [ ] **Step 4: Allowlist the MCP path in middleware**

The MCP endpoint authenticates via Bearer; add it to `PUBLIC_PATH_PREFIXES` in `apps/common/middleware.py`:

```python
PUBLIC_PATH_PREFIXES = (
    ...,
    "/api/mcp/",
)
```

- [ ] **Step 5: Smoke test**

```bash
curl -i http://localhost:8000/api/mcp/  # should return MCP handshake (or empty if no tools registered yet)
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock apps/api/mcp_server.py config/urls.py apps/common/middleware.py
git commit -m "feat(api): add FastMCP server skeleton mounted at /api/mcp/"
```

### Task 7.2: Opt endpoints into MCP exposure

Start with read-only endpoints: project slugs + insights.

- [ ] **Step 1: Mark endpoints**

Edit `apps/projects/api.py`. Add `openapi_extra={"x-mcp-expose": True}` to:
- `list_project_slugs`
- (in `insights_router`) `list_insights`

Example:

```python
@router.get(
    "/slugs/",
    response=list[ProjectSlugOut],
    openapi_extra={"x-mcp-expose": True},
    summary="List project slugs (machine-readable)",
)
def list_project_slugs(request: HttpRequest) -> list[ProjectSlugOut]:
    ...
```

- [ ] **Step 2: Restart + verify**

```bash
uv run honcho start -f Procfile.dev
curl http://localhost:8000/api/mcp/  # should now list 2 tools
```

- [ ] **Step 3: Connect Claude Code**

Add to `~/.claude/mcp.json` (or the project's `.mcp.json`):

```json
{
  "canopy-web": {
    "url": "http://localhost:8000/api/mcp/",
    "headers": { "Authorization": "Bearer <WORKBENCH_WRITE_TOKEN>" }
  }
}
```

Restart Claude Code; verify the `list_project_slugs` + `list_insights` tools show up. Call one — should return the JSON payload.

- [ ] **Step 4: Commit**

```bash
git add apps/projects/api.py
git commit -m "feat(api): expose project slugs + insights as MCP tools"
```

### Task 7.3: Document the MCP surface

**Files:**
- Create: `docs/architecture/mcp-surface.md`

- [ ] **Step 1: Write the doc**

Cover:
- How an endpoint opts into MCP exposure (`openapi_extra={"x-mcp-expose": True}`)
- The auth model (Bearer-token loopback via `LoginRequiredMiddleware`'s allowlist)
- Which endpoints are exposed today (`/projects/slugs/`, `/insights/`)
- How to connect Claude Code to the local MCP server
- Production exposure: same Bearer-token contract

- [ ] **Step 2: Commit**

```bash
git add docs/architecture/mcp-surface.md
git commit -m "docs(api): document the MCP surface and how to expose endpoints"
```

### Task 7.4: Phase 7 gate

- [ ] **Step 1: Smoke**

Boot the server, hit `/api/mcp/` from Claude Code, exercise both exposed tools.

- [ ] **Step 2: Tag**

```bash
git tag api-v2-mcp-complete
```

---

## Phase 8: Orthogonal tooling modernization (optional)

Each task is independent — skip any that don't appeal. None are required to ship the modernization; they're orthogonal hygiene wins.

### Task 8.1: basedpyright type checking

**Files:**
- Modify: `pyproject.toml`
- Create: `.github/workflows/typecheck.yml`

- [ ] **Step 1: Add config**

Edit `pyproject.toml`:

```toml
[tool.basedpyright]
include = ["apps", "config"]
exclude = ["**/migrations", "**/__pycache__"]
pythonVersion = "3.11"
typeCheckingMode = "standard"
```

- [ ] **Step 2: Run locally**

```bash
uv pip install basedpyright
uv run basedpyright apps/ config/
```

Triage initial errors. Use `# pyright: ignore` for genuinely-tricky Django dynamic attrs.

- [ ] **Step 3: Wire CI**

Create `.github/workflows/typecheck.yml`:

```yaml
name: Type check

on: [push, pull_request]

jobs:
  basedpyright:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - run: uv sync --extra dev
      - run: uv pip install basedpyright
      - run: uv run basedpyright apps/ config/
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml .github/workflows/typecheck.yml
git commit -m "chore: add basedpyright type checking + CI gate"
```

### Task 8.2: Pydantic AI for Anthropic SDK calls

**Files:**
- Modify: any module that imports `anthropic` directly (start with `apps/common/anthropic_client.py` and `apps/workspace/engine.py` / `apps/workspace/stream.py`)

- [ ] **Step 1: Inventory current usages**

```bash
rg "from anthropic|import anthropic|get_client\(\)" apps/
```

Note each call site.

- [ ] **Step 2: Add dep**

```toml
"pydantic-ai>=0.0.30,<1.0",
```

Run: `uv sync --extra dev`

- [ ] **Step 3: Migrate one call site at a time**

For each call site, replace the hand-rolled `client.messages.create(...)` with a typed `Agent` from Pydantic AI. Use a typed `result_type` so the response is a parsed Pydantic object, not a free-form string.

```python
from pydantic import BaseModel
from pydantic_ai import Agent


class ProposedApproach(BaseModel):
    name: str
    description: str
    prompt_template: str


approach_agent = Agent("claude-sonnet-4-6", result_type=ProposedApproach)
result = await approach_agent.run(prompt)
approach: ProposedApproach = result.data
```

The SSE engine in `apps/workspace/stream.py` needs care — Pydantic AI supports streaming via `run_stream`. Migrate it last and verify the SSE event format stays identical end-to-end.

Each migration is its own commit.

- [ ] **Step 4: Drop the `anthropic` dependency once unused**

```bash
rg "from anthropic|import anthropic" apps/
```

If empty: remove `"anthropic>=0.40,<1.0"` from `pyproject.toml`. Run `uv sync`. Commit.

### Task 8.3: Phase 8 wrap

- [ ] **Step 1: Tag**

```bash
git tag api-v2-orthogonal-complete
```

---

## Final regression + deploy

### Task F.1: Full repository test sweep

- [ ] **Step 1: Backend**

```bash
uv run pytest -v
```

Expected: every test passes.

- [ ] **Step 2: Frontend**

```bash
cd frontend && npm run build
```

Expected: clean build.

- [ ] **Step 3: Schemathesis**

```bash
uv run honcho start -f Procfile.dev &
sleep 5
SCHEMATHESIS_AUTH_COOKIE=<value> uv run pytest tests/contract/ -v
```

Expected: every endpoint conforms to its schema.

- [ ] **Step 4: Manual smoke**

Walk through every primary surface in a real browser:
- Scalar docs at `/api/docs/` — every endpoint listed, "Try it" works
- Redoc at `/api/redoc/` — clean rendering
- Login → dashboard → projects → insights → workspaces → workspace detail → SSE start → publish skill
- Skills list → skill detail → eval suite → run eval
- Settings → AI backend status + switch

### Task F.2: Deploy to Cloud Run

- [ ] **Step 1: Open PR**

```bash
gh pr create --title "API modernization: DRF → Django Ninja + Pydantic + OpenAPI + FastMCP" --body "..."
```

- [ ] **Step 2: Merge after review**

- [ ] **Step 3: Deploy via the existing Cloud Build pipeline**

```bash
./deploy.sh
```

(Or trigger the manual "CI / Deploy" job from the Actions tab.)

- [ ] **Step 4: Verify in prod**

Open the production URL + `/api/docs/`. Scalar should render the full schema. Spot-check 3-4 endpoints via "Try it". Run schemathesis against prod (read-only endpoints only).

---

## Acceptance criteria

This plan is complete when:

1. [ ] `/api/docs/` (Scalar) renders the full schema for every endpoint.
2. [ ] `frontend/src/api/client.ts` no longer exists; every frontend client uses `openapi-fetch` typed against `generated.ts`.
3. [ ] `apps/common/envelope.py` no longer exists.
4. [ ] `djangorestframework` is not in `pyproject.toml` or `INSTALLED_APPS`.
5. [ ] Every endpoint has a Pydantic schema and a contract test.
6. [ ] Schemathesis CI job is green.
7. [ ] `/api/mcp/` exposes `/projects/slugs/` and `/insights/`; Claude Code can call them.
8. [ ] CLAUDE.md reflects the new architecture.
9. [ ] Production deploy is live and Scalar docs are accessible.
10. [ ] An external caller can read `/api/docs/`, generate a client in any language from the same OpenAPI 3.1 schema, and call canopy-web — and CI proves the schema matches reality.
11. [ ] The SSE event format on `POST /api/workspace/start/<id>/` and `POST /api/workspace/analyze/<id>/` is byte-identical to the pre-migration `/api/workspace/...` endpoints (verified via side-by-side stream capture).
12. [ ] Bearer-token machine callers can still write to `/api/projects/<slug>/actions/` and `/api/projects/<slug>/context/` and read `/api/projects/slugs/` + `/api/insights/`.
13. [ ] All 6 walkthroughs endpoints (upload / list / detail / patch / delete / rotate-token) respond identically to their PR #40 DRF baseline. The 5 PR-#40 walkthroughs view tests (`tests/test_walkthroughs_views.py`) have been replaced by `apps/walkthroughs/tests/test_api.py` with the same coverage. Walkthrough-specific problem types (`drive-not-configured`, `drive-upload-failed`, `payload-too-large`) appear in the schema.
