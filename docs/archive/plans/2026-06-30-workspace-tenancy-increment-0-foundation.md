# Workspace Tenancy — Increment 0: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay the multi-tenancy foundation — a `current_workspace()` resolver, a `/api/w/{ws}` parent router with a flat-route compat shim, the `/w/` → `/walkthrough/` reclaim, and a frontend `WorkspaceProvider` + header switcher — then migrate the already-scoped **agents** surface under `/w/:ws/agents` end-to-end to prove the pattern.

**Architecture:** Workspace is the tenant anchor. Roots carry a `workspace` FK (agents already do); the parent Ninja router resolves + membership-checks the workspace once. Existing flat routes stay as a deprecated shim that resolves the caller's default workspace, so the PAT/agent fleet keeps working. Frontend reads the workspace from the URL (`/w/:workspace/...`); a header dropdown navigates between memberships.

**Tech Stack:** Django 5 + Django Ninja 1.x + Pydantic v2 (backend), React 19 + React Router + Vite + openapi-fetch (frontend), pytest + vitest.

## Global Constraints

- Backend deps via `uv`; run tests with `uv run pytest`.
- All API errors are RFC 7807 `application/problem+json`; raise `ninja.errors.HttpError` (already handler-wrapped).
- Default workspace slug is `dimagi` (`apps.workspaces.services.DEFAULT_WORKSPACE_SLUG`).
- Non-member access to a workspace-scoped resource returns **404** (no existence leak), matching `apps/agents/api.py:_get_agent_or_404`.
- Frontend: no raw palette literals — semantic tokens only (`bg-card`, `text-muted-foreground`, …).
- Regenerate types with `cd frontend && npm run gen:api` after any `apps/**/api.py` or `schemas.py` change; type-check with `npm run build`.
- Tenant prefix in the browser is `/w/:workspace`; the public walkthrough viewer moves to `/walkthrough/:id`. `/w/` no longer means "walkthrough".

---

## File Structure

- `apps/workspaces/services.py` — add `current_workspace()` + `user_default_workspace()`.
- `apps/api/tenancy.py` (**new**) — the `/api/w/{ws}` parent router factory + `resolve_workspace` dependency; shared by all scoped routers.
- `apps/api/api.py` — mount agents/agent_runs routers under the parent router *and* keep the flat mounts (compat).
- `config/urls.py` — move the walkthrough content stream route `w/<uuid>/content` → `walkthrough/<uuid>/content`.
- `apps/walkthroughs/streaming.py` — docstring only (path reference).
- `apps/common/middleware.py` — allowlist `/walkthrough/` instead of `/w/`.
- `frontend/src/workspace/WorkspaceProvider.tsx` (**new**) — context + `useWorkspace()`.
- `frontend/src/router.tsx` — `/w/:workspace` parent route for agents; rename viewer to `/walkthrough/:id`; legacy redirects.
- `frontend/src/components/AppLayout/AppLayout.tsx` — header workspace switcher.
- `frontend/src/api/agents.ts` — build agent calls under `/api/w/{ws}/agents/...`.

---

## Task 1: `current_workspace()` resolver (backend service)

**Files:**
- Modify: `apps/workspaces/services.py`
- Test: `apps/workspaces/tests/test_current_workspace.py` (new)

**Interfaces:**
- Consumes: `Workspace`, `WorkspaceMembership`, `ensure_member`, `is_member` (existing).
- Produces:
  - `user_default_workspace(user) -> Workspace | None` — the user's sole membership, else `None` if 0 or 2+.
  - `current_workspace(user, explicit: str | None = None) -> Workspace` — explicit slug (must be a member) → that workspace; else the sole membership; else raise `ValueError`.

- [ ] **Step 1: Write the failing test**

```python
# apps/workspaces/tests/test_current_workspace.py
import pytest
from django.contrib.auth import get_user_model
from apps.workspaces import services as wsvc
from apps.workspaces.models import Workspace, WorkspaceMembership

User = get_user_model()
pytestmark = pytest.mark.django_db


def _mk_user(email="a@dimagi.com"):
    return User.objects.create(username=email, email=email)


def _mk_ws(slug, owner):
    ws = Workspace.objects.create(slug=slug, display_name=slug.title(), created_by=owner)
    wsvc.ensure_member(ws, owner, WorkspaceMembership.OWNER)
    return ws


def test_sole_membership_is_default():
    u = _mk_user()
    ws = _mk_ws("dimagi", u)
    assert wsvc.user_default_workspace(u) == ws
    assert wsvc.current_workspace(u) == ws


def test_explicit_member_slug_resolves():
    u = _mk_user()
    _mk_ws("dimagi", u)
    other = _mk_ws("acme", u)
    assert wsvc.current_workspace(u, explicit="acme") == other


def test_explicit_non_member_raises():
    u = _mk_user()
    _mk_ws("dimagi", u)
    stranger = _mk_user("b@dimagi.com")
    ghost = _mk_ws("ghost", stranger)  # u is NOT a member
    with pytest.raises(ValueError):
        wsvc.current_workspace(u, explicit="ghost")


def test_ambiguous_without_explicit_raises():
    u = _mk_user()
    _mk_ws("dimagi", u)
    _mk_ws("acme", u)  # two memberships, no explicit
    assert wsvc.user_default_workspace(u) is None
    with pytest.raises(ValueError):
        wsvc.current_workspace(u)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/workspaces/tests/test_current_workspace.py -v`
Expected: FAIL (`AttributeError: module ... has no attribute 'current_workspace'`).

- [ ] **Step 3: Implement**

```python
# append to apps/workspaces/services.py
def user_default_workspace(user) -> Workspace | None:
    """The user's workspace when unambiguous — their sole membership, else None
    (0 or 2+ memberships). Used to resolve a default for headless PAT callers."""
    qs = WorkspaceMembership.objects.filter(user=user).select_related("workspace")[:2]
    rows = list(qs)
    return rows[0].workspace if len(rows) == 1 else None


def current_workspace(user, explicit: str | None = None) -> Workspace:
    """Resolve the workspace a caller is acting in.

    explicit slug (caller must be a member) -> that workspace;
    else the caller's sole membership; else ValueError (none / ambiguous).
    Single resolution point for PAT callers, MCP tools, and the flat compat shim.
    """
    if explicit:
        ws = Workspace.objects.filter(slug=explicit).first()
        if ws is None or not is_member(user, explicit):
            raise ValueError(f"workspace '{explicit}' not found or not a member")
        return ws
    ws = user_default_workspace(user)
    if ws is None:
        raise ValueError("no unambiguous workspace for user; specify one")
    return ws
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest apps/workspaces/tests/test_current_workspace.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/workspaces/services.py apps/workspaces/tests/test_current_workspace.py
git commit -m "Add current_workspace() resolver for tenant scoping"
```

---

## Task 2: `/api/w/{ws}` parent router + `resolve_workspace` dependency

**Files:**
- Create: `apps/api/tenancy.py`
- Test: `apps/api/tests/test_tenancy_router.py` (new)

**Interfaces:**
- Consumes: `apps.workspaces.services.is_member`, `apps.workspaces.services.auto_join_workspaces`, `apps.api.auth.session_auth`.
- Produces:
  - `resolve_workspace(request, ws: str) -> str` — auto-joins domain users, 404s a non-member, stashes `request.workspace_slug = ws`, returns the slug.
  - `make_tenant_router() -> ninja.Router` — a router whose handlers receive the `{ws}` path param and are membership-gated. (Child routers are added by the composition root.)

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_tenancy_router.py
import pytest
from django.test import Client
from django.contrib.auth import get_user_model
from apps.workspaces import services as wsvc
from apps.workspaces.models import Workspace, WorkspaceMembership

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def member(client):
    u = User.objects.create(username="m@dimagi.com", email="m@dimagi.com")
    ws = Workspace.objects.create(slug="dimagi", display_name="Dimagi", created_by=u)
    wsvc.ensure_member(ws, u, WorkspaceMembership.OWNER)
    client.force_login(u)
    return u, ws, client


def test_member_reaches_scoped_agents_list(member):
    _, _, client = member
    r = client.get("/api/w/dimagi/agents/")
    assert r.status_code == 200


def test_non_member_gets_404(member):
    stranger = User.objects.create(username="s@evil.com", email="s@evil.com")
    Workspace.objects.create(slug="secret", display_name="Secret", created_by=stranger)
    _, _, client = member  # logged in as dimagi member, not secret
    r = client.get("/api/w/secret/agents/")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/api/tests/test_tenancy_router.py -v`
Expected: FAIL (404 on the member route — parent router not mounted yet).

- [ ] **Step 3: Implement the parent router factory**

```python
# apps/api/tenancy.py
"""The /api/w/{ws} tenant-scoped parent router.

A single membership gate: `resolve_workspace` auto-joins domain users, 404s a
non-member (no existence leak), and stashes the slug on the request. Scoped
child routers (agents, projects, …) mount under the router this factory returns,
so per-handler code can't forget the gate.
"""
from __future__ import annotations

from django.http import HttpRequest
from ninja import Router
from ninja.errors import HttpError

from apps.api.auth import session_auth
from apps.workspaces import services as wsvc


def resolve_workspace(request: HttpRequest, ws: str) -> str:
    wsvc.auto_join_workspaces(request.user)
    if not wsvc.is_member(request.user, ws):
        raise HttpError(404, f"workspace '{ws}' not found")
    request.workspace_slug = ws  # type: ignore[attr-defined]
    return ws


def make_tenant_router() -> Router:
    """A router mounted at /w/{ws}; child routers are added by the composition
    root. The {ws} path param is available to every child handler."""
    return Router(auth=session_auth, tags=["tenant"])
```

- [ ] **Step 4: Mount it (in `apps/api/api.py`) — see Task 3, which wires agents under it**

(Deferred to Task 3; this task only defines the factory + dependency. Re-run
the test after Task 3.)

- [ ] **Step 5: Commit**

```bash
git add apps/api/tenancy.py apps/api/tests/test_tenancy_router.py
git commit -m "Add /api/w/{ws} tenant parent-router factory + membership gate"
```

---

## Task 3: Mount agents under `/api/w/{ws}` (keep flat compat)

**Files:**
- Modify: `apps/agents/api.py` (add `{ws}` param to routes via a scoped router; keep the existing router for flat compat)
- Modify: `apps/api/api.py` (mount agents router under the parent router at `/w/{ws}`; keep the flat `/agents` mount)
- Test: `apps/api/tests/test_tenancy_router.py` (from Task 2 — now passes)

**Interfaces:**
- Consumes: `make_tenant_router`, `resolve_workspace` (Task 2); `agents_router`, `agent_runs_router` (existing).
- Produces: agents reachable at both `/api/w/{ws}/agents/...` (canonical) and `/api/agents/...` (compat).

- [ ] **Step 1: Wire the parent router in `apps/api/api.py`**

Add after the existing router imports/mounts:

```python
# apps/api/api.py  (near the other add_router calls)
from apps.api.tenancy import make_tenant_router  # noqa: E402

tenant_router = make_tenant_router()
tenant_router.add_router("/agents", agents_router)
tenant_router.add_router("/agents", agent_runs_router)
api.add_router("/w/{ws}", tenant_router)  # canonical tenant-scoped surface

# Flat mounts below stay as the deprecated default-workspace compat shim.
```

Keep the existing `api.add_router("/agents", agents_router)` / `agent_runs_router` lines.

- [ ] **Step 2: Gate the scoped agent routes on the `{ws}` param**

In `apps/agents/api.py`, make `_get_agent_or_404` honor an explicit workspace when present on the request, and confirm the agent belongs to it:

```python
def _get_agent_or_404(request: HttpRequest, slug: str):
    agent = services.get_agent(slug)
    if agent is None:
        raise HttpError(404, f"agent '{slug}' not found")
    wsvc.auto_join_workspaces(request.user)
    ws = getattr(request, "workspace_slug", None)
    if ws and agent.workspace_id != ws:
        raise HttpError(404, f"agent '{slug}' not found")  # wrong tenant
    if agent.workspace_id and not wsvc.is_member(request.user, agent.workspace_id):
        raise HttpError(404, f"agent '{slug}' not found")
    return agent
```

And in `list_agents`, when a workspace is pinned by the parent route, scope to it:

```python
def list_agents(request: HttpRequest, limit: int = 100) -> Page[AgentOut]:
    limit = min(limit, 500)
    wsvc.auto_join_workspaces(request.user)
    ws = getattr(request, "workspace_slug", None)
    slugs = {ws} if ws else wsvc.user_workspace_slugs(request.user)
    items = [
        AgentOut.model_validate(a)
        for a in services.list_agents()
        if a.workspace_id in slugs or (ws is None and a.workspace_id is None)
    ]
    return paginate(items, offset=0, limit=limit)
```

Note: the parent router passes `ws` as a handler kwarg. Add `ws: str = ""` to the
scoped handlers OR read it from `request.workspace_slug` (set by
`resolve_workspace`). Use the request attribute so the flat compat mount (no `{ws}`)
keeps the same handler signature. Register `resolve_workspace` as the tenant
router's dependency so it runs before each handler:

```python
# in make_tenant_router (apps/api/tenancy.py), enforce the gate for every child:
def make_tenant_router() -> Router:
    router = Router(auth=session_auth, tags=["tenant"])
    return router
# and in apps/api/api.py, gate via a before-request hook:
@tenant_router.api_operation  # pseudocode marker — see Step 3
```

- [ ] **Step 3: Enforce `resolve_workspace` on the parent path**

Ninja passes `{ws}` to each child handler. The simplest robust gate: a tiny
wrapper router-level auth is awkward, so instead resolve in each scoped handler
via a shared 1-liner. Add to the top of `list_agents`, `_get_agent_or_404`, and
each write handler that the tenant router serves:

```python
# when reached via the tenant router, ws is in the path; gate it:
def _pin_ws(request, ws: str | None):
    if ws:
        from apps.api.tenancy import resolve_workspace
        resolve_workspace(request, ws)
```

Because agents mount under `/w/{ws}`, add `ws: str = ""` to each scoped handler
signature and call `_pin_ws(request, ws)` first. The flat mount passes `ws=""`
(falsy) → no pin, existing behavior.

- [ ] **Step 4: Run the tenancy tests**

Run: `uv run pytest apps/api/tests/test_tenancy_router.py apps/agents/tests -v`
Expected: PASS (member reaches list; non-member 404s; existing agent tests green).

- [ ] **Step 5: Regenerate OpenAPI types + commit**

```bash
cd frontend && npm run gen:api && cd ..
git add apps/api/api.py apps/agents/api.py apps/api/tenancy.py frontend/src/api/generated.ts
git commit -m "Mount agents under /api/w/{ws}; keep flat compat"
```

---

## Task 4: Reclaim `/w/` → `/walkthrough/` (streaming route + middleware)

**Files:**
- Modify: `config/urls.py:20`
- Modify: `apps/common/middleware.py:49-62`
- Modify: `apps/walkthroughs/streaming.py` (docstring)
- Test: `apps/common/tests/test_walkthrough_reclaim.py` (new)

**Interfaces:**
- Produces: public walkthrough content at `/walkthrough/<uuid>/content`; `/w/...` now requires auth (it's the tenant SPA shell).

- [ ] **Step 1: Write the failing test**

```python
# apps/common/tests/test_walkthrough_reclaim.py
import pytest
from apps.common.middleware import _is_walkthrough_link

pytestmark = pytest.mark.django_db


class _Req:
    def __init__(self, path, method="GET"):
        self.path = path
        self.method = method


def test_walkthrough_viewer_path_is_public():
    assert _is_walkthrough_link(_Req("/walkthrough/abc-123")) is True
    assert _is_walkthrough_link(_Req("/walkthrough/abc-123/content")) is True


def test_bare_w_prefix_is_no_longer_public():
    # /w/ now means workspace — the tenant shell, which REQUIRES auth.
    assert _is_walkthrough_link(_Req("/w/dimagi/agents")) is False


def test_walkthrough_detail_get_still_public():
    assert _is_walkthrough_link(_Req("/api/walkthroughs/abc/")) is True
    assert _is_walkthrough_link(_Req("/api/walkthroughs/")) is False  # collection stays auth'd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/common/tests/test_walkthrough_reclaim.py -v`
Expected: FAIL (`/w/dimagi/agents` currently returns True).

- [ ] **Step 3: Update the middleware allowlist**

```python
# apps/common/middleware.py — replace _is_walkthrough_link body
def _is_walkthrough_link(request) -> bool:
    # The public walkthrough viewer SPA shell (/walkthrough/<uuid>) and the
    # content stream (/walkthrough/<uuid>/content), plus the per-walkthrough
    # detail GET, self-enforce tokenless public access. /w/ now means
    # "workspace" (the authed tenant shell) and is NOT allowlisted here.
    path = request.path
    if path.startswith("/walkthrough/"):
        return True
    return (
        request.method == "GET"
        and path.startswith("/api/walkthroughs/")
        and path != "/api/walkthroughs/"
    )
```

- [ ] **Step 4: Move the streaming route**

```python
# config/urls.py — replace the /w/<uuid>/content line
    path("walkthrough/<uuid:wid>/content", views_walkthrough_content, name="walkthrough-content"),
```

Update the SPA catch-all so `/walkthrough/...` is served by the SPA (it already
is — the negative-lookahead only excludes api/admin/accounts/health/static/auth).
Update `apps/walkthroughs/streaming.py` module docstring: "Mounted at
/walkthrough/<uuid:wid>/content in config/urls.py."

- [ ] **Step 5: Run tests + commit**

Run: `uv run pytest apps/common/tests/test_walkthrough_reclaim.py apps/walkthroughs/tests -v`
Expected: PASS.

```bash
git add config/urls.py apps/common/middleware.py apps/walkthroughs/streaming.py apps/common/tests/test_walkthrough_reclaim.py
git commit -m "Reclaim /w/ for workspaces; move walkthrough viewer to /walkthrough/"
```

---

## Task 5: Frontend `WorkspaceProvider` + `useWorkspace()`

**Files:**
- Create: `frontend/src/workspace/WorkspaceProvider.tsx`
- Modify: `frontend/src/api/workspaces.ts` (new thin client if absent) or reuse `client.v2`
- Test: `frontend/src/workspace/WorkspaceProvider.test.tsx` (vitest)

**Interfaces:**
- Produces:
  - `WorkspaceProvider` — fetches `GET /api/workspaces/`, exposes context.
  - `useWorkspace() -> { workspaces: WorkspaceOut[]; active: string | null; setActive(slug): void }`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/workspace/WorkspaceProvider.test.tsx
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { WorkspaceProvider, useWorkspace } from './WorkspaceProvider'

vi.mock('../api/workspaces', () => ({
  listWorkspaces: vi.fn().mockResolvedValue([
    { slug: 'dimagi', display_name: 'Dimagi', role: 'owner' },
  ]),
}))

function Probe() {
  const { workspaces, active } = useWorkspace()
  return <div>{active}:{workspaces.length}</div>
}

describe('WorkspaceProvider', () => {
  it('loads memberships and defaults active to first', async () => {
    render(
      <WorkspaceProvider initialSlug={null}>
        <Probe />
      </WorkspaceProvider>,
    )
    await waitFor(() => expect(screen.getByText('dimagi:1')).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/workspace/WorkspaceProvider.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```tsx
// frontend/src/workspace/WorkspaceProvider.tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { listWorkspaces, type WorkspaceOut } from '../api/workspaces'

type Ctx = {
  workspaces: WorkspaceOut[]
  active: string | null
  setActive: (slug: string) => void
}
const WorkspaceContext = createContext<Ctx | null>(null)

export function WorkspaceProvider({
  initialSlug,
  children,
}: {
  initialSlug: string | null
  children: ReactNode
}) {
  const [workspaces, setWorkspaces] = useState<WorkspaceOut[]>([])
  const [active, setActive] = useState<string | null>(initialSlug)

  useEffect(() => {
    listWorkspaces().then((ws) => {
      setWorkspaces(ws)
      setActive((cur) => cur ?? ws[0]?.slug ?? null)
    })
  }, [])

  return (
    <WorkspaceContext.Provider value={{ workspaces, active, setActive }}>
      {children}
    </WorkspaceContext.Provider>
  )
}

export function useWorkspace(): Ctx {
  const ctx = useContext(WorkspaceContext)
  if (!ctx) throw new Error('useWorkspace must be used within WorkspaceProvider')
  return ctx
}
```

```ts
// frontend/src/api/workspaces.ts
import { client } from './client.v2'
export type WorkspaceOut = {
  slug: string
  display_name: string
  role: string
  auto_join_domains?: string[]
  created_at?: string
}
export async function listWorkspaces(): Promise<WorkspaceOut[]> {
  const { data } = await client.GET('/workspaces/')
  return (data as WorkspaceOut[]) ?? []
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/workspace/WorkspaceProvider.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/workspace/WorkspaceProvider.tsx frontend/src/api/workspaces.ts frontend/src/workspace/WorkspaceProvider.test.tsx
git commit -m "Add frontend WorkspaceProvider + useWorkspace()"
```

---

## Task 6: `/w/:workspace` route for agents + `/walkthrough/:id` rename + redirects

**Files:**
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/api/agents.ts` (build paths under `/api/w/{ws}/agents/...`)

**Interfaces:**
- Consumes: `WorkspaceProvider`, `useWorkspace` (Task 5).
- Produces: agents surface at `/w/:workspace/agents` + `/w/:workspace/agents/:slug`; viewer at `/walkthrough/:id`; legacy `/agents`, `/agents/:slug`, `/w/:id` redirect.

- [ ] **Step 1: Move agents routes under `/w/:workspace`; rename viewer; add redirects**

```tsx
// frontend/src/router.tsx — inside the AppLayout children array
// (1) rename the viewer
{ path: '/walkthrough/:id', element: <WalkthroughViewerPage /> },
// (2) legacy walkthrough viewer redirect
{ path: '/w/:id', element: <Navigate to="/walkthrough/:id" replace /> },  // see note
// (3) agents under the tenant prefix
{
  path: '/w/:workspace/agents',
  element: <AgentsPage />,
},
{
  path: '/w/:workspace/agents/:slug',
  element: <AgentWorkspacePage />,
  children: [ /* unchanged child routes: needs-you, overview, tasks, syncs, work-products, skills */ ],
},
// (4) legacy agents redirects → resolve default workspace at runtime
{ path: '/agents', element: <WorkspaceRedirect to="agents" /> },
{ path: '/agents/:slug/*', element: <WorkspaceRedirect to="agents" keepTail /> },
```

Note: React Router can't interpolate `:id` in a static `Navigate`. Implement a
tiny `WorkspaceRedirect` / `LegacyWalkthroughRedirect` component that reads
`useParams()` + `useWorkspace()` and issues `<Navigate>` to the resolved path.
Wrap the whole `AppLayout` element tree in `<WorkspaceProvider initialSlug={...}>`
by reading the `:workspace` param in an `AppLayout` wrapper (Task 7 mounts the
provider in `AppLayout`).

- [ ] **Step 2: Point the agents API client at the tenant path**

```ts
// frontend/src/api/agents.ts — thread the active workspace into the path
// each call becomes /api/w/${ws}/agents/... ; the ws comes from useWorkspace()
// (pass ws as an argument from the calling page/hook).
export function agentsBase(ws: string) {
  return `/api/w/${ws}/agents`
}
```

Update agent fetch hooks/pages to pass the active workspace slug into the path.
(Flat `/api/agents/...` still works via the compat shim, so this can be done
incrementally; do the list + detail here.)

- [ ] **Step 3: Type-check the build**

Run: `cd frontend && npm run build`
Expected: PASS (tsc + vite build, no type errors).

- [ ] **Step 4: Manual smoke (optional but recommended)**

Run backend + frontend (`uv run honcho start -f Procfile.dev`), visit
`/w/dimagi/agents`, confirm the list renders and `/agents` redirects to it.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/router.tsx frontend/src/api/agents.ts
git commit -m "Route agents under /w/:workspace; rename viewer to /walkthrough/:id"
```

---

## Task 7: Header workspace switcher + mount provider

**Files:**
- Modify: `frontend/src/components/AppLayout/AppLayout.tsx`

**Interfaces:**
- Consumes: `useWorkspace`, `WorkspaceProvider`, `react-router` `useParams`/`useNavigate`.
- Produces: a header dropdown that navigates between workspaces; hidden with a single membership.

- [ ] **Step 1: Wrap AppLayout in the provider (reading `:workspace`)**

```tsx
// AppLayout.tsx (sketch)
import { useParams, useNavigate } from 'react-router-dom'
import { WorkspaceProvider, useWorkspace } from '../../workspace/WorkspaceProvider'

export function AppLayout() {
  const { workspace } = useParams()
  return (
    <WorkspaceProvider initialSlug={workspace ?? null}>
      <AppShell />
    </WorkspaceProvider>
  )
}
```

- [ ] **Step 2: Add the switcher next to `<ThemeToggle/>`**

```tsx
function WorkspaceSwitcher() {
  const { workspaces, active } = useWorkspace()
  const navigate = useNavigate()
  if (workspaces.length <= 1) return null  // nothing to switch
  return (
    <select
      className="bg-input border border-input text-foreground text-[13px] rounded px-2 py-1"
      value={active ?? ''}
      onChange={(e) => navigate(`/w/${e.target.value}/agents`)}
    >
      {workspaces.map((w) => (
        <option key={w.slug} value={w.slug}>{w.display_name}</option>
      ))}
    </select>
  )
}
```

Mount `<WorkspaceSwitcher />` in the header row where `<ThemeToggle/>` lives.

- [ ] **Step 3: Type-check + build**

Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/AppLayout/AppLayout.tsx
git commit -m "Add header workspace switcher (hidden with single membership)"
```

---

## Task 8: Full-suite green + architecture boundary check

**Files:** none (verification task)

- [ ] **Step 1: Backend suite**

Run: `uv run pytest -q`
Expected: PASS (no regressions; new tenancy tests green).

- [ ] **Step 2: Architecture boundary**

Run: `uv run pytest tests/test_architecture_boundary.py -v`
Expected: PASS (`workspaces` is framework-tier; `agents`/`api` importing it is allowed).

- [ ] **Step 3: Frontend build**

Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 4: Commit any fixups + push branch**

```bash
git add -A && git commit -m "Increment 0 foundation: full suite green" || true
```

---

## Self-Review Notes

- **Spec coverage:** current_workspace (§4.2 ✓ T1), parent router + compat (§4.3 ✓ T2/T3),
  enforcement (§4.4 ✓ T3), `/w/` reclaim (§3.2 ✓ T4), WorkspaceProvider/switcher (§5 ✓ T5/T7),
  agents under prefix (§6 Increment 0 ✓ T3/T6). MCP untouched (§4.5 — no task, correct).
- **Deferred to later increments (not this plan):** Project/Walkthrough/Shareout/Narrative
  FKs + backfills (Increments 1–4), timeline scoping (4b), non-null hardening (5).
- **Known soft spot:** Task 3's `{ws}` gate uses a per-handler `_pin_ws` call rather than a
  true router-level dependency because Ninja's parent-router path param must be a handler kwarg.
  If a cleaner router-level `auth`/dependency proves viable during execution, prefer it and
  drop the per-handler calls (update the tests accordingly).
