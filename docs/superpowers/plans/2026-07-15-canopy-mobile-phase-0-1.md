# canopy-mobile Phase 0 + 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the harness authorization hole, put the agent API on its already-generated types, and ship a `/supervisor` React route (needs-you inbox + agent KPI cards + runner status) that a phone will later install as a PWA.

**Architecture:** Phase 0 is invisible groundwork — a workspace FK on `Runner`, membership gating copied verbatim from `apps/agents`, and migrating `frontend/src/api/agents.ts` onto `apiV2`. Phase 1 adds two small read endpoints (list runners, fleet-wide needs-you) and one React route built on `canopy-ui`. Nothing here is mobile-specific yet: Phase 1 ships a desktop route that Phase 2 turns into a PWA.

**Tech Stack:** Django 5 + Django Ninja 1.x + Pydantic v2 + PostgreSQL; React 19 + Vite + Tailwind 4 + `canopy-ui`; `openapi-fetch` against generated types; pytest; Playwright.

**Spec:** `docs/superpowers/specs/2026-07-14-canopy-mobile-design.md` (§7 prerequisite, §8 authorization → Phase 0; Phases table → Phase 1).

## Global Constraints

- **Tenancy gate returns 404, never 403.** A non-member must not learn a resource exists. Copy `_get_agent_or_404` (`apps/agents/api.py:42-54`) exactly.
- **`Workspace`'s primary key is its slug** (`apps/workspaces/models.py:29`, `slug = CharField(primary_key=True)`). So `agent.workspace_id` **is a slug string**, not an integer. `wsvc.is_member(user, slug)` takes that slug.
- **A null workspace means "ungated".** `Agent.workspace` is nullable for migration safety, and existing tests create agents with no workspace. Every gate must preserve this: `if obj.workspace_id and not is_member(...)`. Breaking this breaks the existing suite.
- **Design tokens only.** No raw Tailwind palette literals (`stone-*`, `orange-*`, `zinc-*`, `emerald-*`, …). Use `bg-card`, `border-border`, `text-foreground`, `text-muted-foreground`, `text-primary`, `bg-muted`, `success`, `warning`, `info`, `destructive`.
- **Responsive rail contract:** `WorkbenchRail`'s `width` prop **must** be `md:`-prefixed (e.g. `md:w-64`). A bare `w-64` breaks the phone layout.
- **Tests:** pytest, `pytestmark = pytest.mark.django_db`, fixtures declared inline per file. There is **no `tests/conftest.py`** — do not assume shared fixtures exist.
- **Settings module for any manual Django invocation:** `config.settings.test` (there is no `config.settings.dev`; `manage.py` defaults to `config.settings.development`).
- **Never touch** `frontend/src/api/generated.ts` by hand — it is generated (`npm run gen:api`).

---

## File Structure

**Phase 0 — backend**
- Modify `apps/harness/models.py` — add `Runner.workspace` FK.
- Create `apps/harness/migrations/0002_runner_workspace.py` — the FK.
- Modify `apps/harness/api.py` — membership gating + `paired_by` binding.
- Modify `apps/harness/schemas.py` — expose `workspace` on `RunnerIn`/`RunnerOut`.
- Create `tests/test_harness_authz.py` — the gate's tests, separate from the existing lifecycle tests.

**Phase 0 — frontend**
- Modify `frontend/src/api/client.v2.ts` — add `/api/agents` to `WS_SCOPED_API_PREFIXES`.
- Modify `frontend/src/api/agents.ts` — migrate to `apiV2`, delete the hand-rolled fetch layer and the hand-declared interfaces.

**Phase 1 — backend**
- Modify `apps/harness/api.py` — `GET /runners/`.
- Modify `apps/agents/api.py` — `GET /needs-you` (fleet-wide).
- Modify `apps/agents/schemas.py` — `FleetNeedsYouOut`.
- Modify `tests/test_harness_api.py`, create `tests/test_agents_fleet_needs_you.py`.

**Phase 1 — frontend**
- Create `frontend/src/api/harness.ts` — the harness client (`listRunners`). Separate from `agents.ts`: a Runner is framework tier, the agent surface is product tier.
- Create `frontend/src/pages/SupervisorPage.tsx` — the route (fetch + layout only).
- Create `frontend/src/components/supervisor/RunnerStatus.tsx` — runner pills.
- Create `frontend/src/components/supervisor/AgentKpiCard.tsx` — one agent's KPIs.
- Create `frontend/src/components/supervisor/WaitingOnYou.tsx` — the cross-fleet inbox.
- Modify `frontend/src/router.tsx` — mount `/supervisor`.
- Modify `frontend/playwright.config.ts` — a mobile project.
- Create `frontend/e2e/supervisor.spec.ts` — the mobile-viewport e2e.

Components are split so each holds one responsibility and fits in context: `SupervisorPage` fetches and lays out; the three components render and own no fetching.

---

# PHASE 0

## Task 1: Put the agent API on its generated types

**Context for the implementer:** `frontend/src/api/agents.ts` opens with a comment saying the `/api/agents/*` routes "are not yet present in the generated OpenAPI types". **That comment is false and has been for some time.** `generated.ts` contains all 19 agent paths including `/api/agents/{slug}/needs-you`. The file therefore hand-rolls a fetch layer and hand-declares ~15 interfaces for no reason. Phase 1 is built on this surface, so it must be typed *before* a second consumer forks the drift.

**Files:**
- Modify: `frontend/src/api/client.v2.ts:38-46` (the `WS_SCOPED_API_PREFIXES` array)
- Modify: `frontend/src/api/agents.ts` (359 lines — the whole file)
- Test: `cd frontend && npm run build`

**Interfaces:**
- Consumes: `apiV2` from `frontend/src/api/client.v2.ts`; `paths` / `components` from `frontend/src/api/generated.ts`.
- Produces: the **same exported names** `agents.ts` exports today, so no caller changes. Types become aliases of generated schemas: `AgentOut`, `AgentDetailOut`, `NeedsYouOut`, `NeedsYouItem`, `NeedsYouType`, `AgentTaskOut`, `AgentTaskStatus`, `AgentSkillOut`, `AgentSyncOut`, `AgentTurnOut`, `AgentWorkProductOut`, `AgentCommandOut`, `AgentCommandKind`, `PostCommandResult`, `AgentTaskLink`, `Page<T>`, `ListAgentsParams`. Functions keep their signatures: `listAgents`, `getAgent`, `getNeedsYou`, `listAgentSyncs`, `listAgentTurns`, `listAgentWorkProducts`, `listAgentSkills`, `listAgentTasks`, `postTaskCommand`, `listAgentCommands`, `listPendingCommands`.

- [ ] **Step 1: Verify the premise before changing anything**

The whole task rests on the types already existing. Confirm:

```bash
cd frontend && grep -cE 'readonly "/api/agents[^"]*"' src/api/generated.ts
```

Expected: `19`. If it prints `0`, **stop** — the premise is wrong, run `npm run gen:api` (needs a server on `localhost:8000`) and re-check before continuing.

- [ ] **Step 2: Add `/api/agents` to the workspace-rewrite list**

This is load-bearing and easy to miss. `agents.ts` currently does its own tenant rewrite via a local `scopedAgentsPath` helper. Moving to `apiV2` without registering the prefix would silently drop workspace scoping — every agent call would hit the flat path and resolve the *default* workspace, which is exactly the cross-workspace bug commit `483c821` fixed for the menubar.

In `frontend/src/api/client.v2.ts`, extend the array:

```ts
const WS_SCOPED_API_PREFIXES = [
  "/api/projects",
  "/api/walkthroughs",
  "/api/reviews",
  "/api/shareouts",
  "/api/ddd",
  "/api/timeline",
  "/api/agents",
];
```

- [ ] **Step 3: Rewrite `agents.ts` onto `apiV2`**

Replace the entire contents of `frontend/src/api/agents.ts`. Types now alias the generated schemas; the local fetch helpers and the `scopedAgentsPath` rewrite are deleted (the middleware from Step 2 does that job now).

**Every type name below was verified to exist in `generated.ts` before this plan was written.** The public signatures are copied from the current `agents.ts` and **must not change** — callers depend on them, and "no caller changes" is this task's contract.

Two subtleties that will bite you if you skip them:

1. **`syncs`, `turns`, and `work-products` return `Page<T>`, not arrays.** `skills` and `tasks` return plain arrays. That asymmetry is real (the server paginates the first three); preserve it exactly.
2. **`generated.ts` is generated with `--immutable`**, so its shapes are `readonly items: readonly T[]`. The local `Page<T>` is mutable and callers rely on that (`setState(page.items)`). Assigning readonly → mutable does not typecheck, so paged responses go through `toPage()`, which copies. Do not "fix" this with an `as` cast — the copy is what makes it type-safe.

```ts
// Agent Workspace API client — a thin, typed wrapper over the generated
// OpenAPI client. Response entity types alias the generated schemas, so this
// file cannot drift from the server. Workspace scoping is handled by apiV2's
// middleware (see WS_SCOPED_API_PREFIXES in ./client.v2), not here.
import { apiV2 } from './client.v2'
import type { components } from './generated'

type Schemas = components['schemas']

export type AgentOut = Schemas['AgentOut']
export type AgentDetailOut = Schemas['AgentDetailOut']
export type AgentTurnOut = Schemas['AgentTurnOut']
export type AgentSyncOut = Schemas['AgentSyncOut']
export type AgentWorkProductOut = Schemas['AgentWorkProductOut']
export type AgentSkillOut = Schemas['AgentSkillOut']
export type AgentTaskOut = Schemas['AgentTaskOut']
export type AgentTaskLink = Schemas['AgentTaskLink']
export type AgentCommandOut = Schemas['AgentTaskCommandOut']
export type NeedsYouOut = Schemas['NeedsYouOut']
export type NeedsYouItem = Schemas['NeedsYouItem']
export type PostCommandResult = Schemas['CommandResultOut']

export type NeedsYouType = NeedsYouItem['type']
export type AgentTaskStatus = AgentTaskOut['status']
export type AgentCommandKind = Schemas['AgentTaskCommandIn']['kind']

// Stays hand-declared, deliberately: openapi-typescript emits a CONCRETE alias
// per payload (Page_AgentOut_, Page_AgentSyncOut_, …), never a generic, so
// there is nothing to alias a generic to. Mutable because callers assign
// page.items straight into useState.
export interface Page<T> {
  items: T[]
  total: number
  offset: number
  limit: number
}

export interface ListAgentsParams {
  limit?: number
  offset?: number
}

// openapi-fetch returns { data, error }. Every call here is a read or a command
// post whose failure is a bug, not a user-facing state — so unwrap and throw. A
// 401 never reaches here: apiV2's middleware redirects to login first.
function unwrap<T>(res: { data?: T; error?: unknown }, what: string): T {
  if (res.error !== undefined || res.data === undefined) {
    throw new Error(`${what} failed: ${JSON.stringify(res.error ?? 'no data')}`)
  }
  return res.data
}

// Generated shapes are readonly (--immutable); Page<T> is mutable. Copy across
// the boundary rather than casting, so the compiler keeps checking us.
function toPage<T>(p: {
  readonly items: readonly T[]
  readonly total: number
  readonly offset: number
  readonly limit: number
}): Page<T> {
  return { items: [...p.items], total: p.total, offset: p.offset, limit: p.limit }
}

export async function listAgents(params: ListAgentsParams = {}): Promise<Page<AgentOut>> {
  const res = await apiV2.GET('/api/agents/', { params: { query: { limit: params.limit } } })
  return toPage(unwrap(res, 'listAgents'))
}

export async function getAgent(slug: string): Promise<AgentDetailOut> {
  const res = await apiV2.GET('/api/agents/{slug}/', { params: { path: { slug } } })
  return unwrap(res, 'getAgent')
}

export async function getNeedsYou(slug: string): Promise<NeedsYouOut> {
  const res = await apiV2.GET('/api/agents/{slug}/needs-you', { params: { path: { slug } } })
  return unwrap(res, 'getNeedsYou')
}

export async function listAgentSyncs(
  slug: string,
  params: ListAgentsParams = {},
): Promise<Page<AgentSyncOut>> {
  const res = await apiV2.GET('/api/agents/{slug}/syncs/', {
    params: { path: { slug }, query: { limit: params.limit, offset: params.offset } },
  })
  return toPage(unwrap(res, 'listAgentSyncs'))
}

export async function listAgentTurns(
  slug: string,
  params: ListAgentsParams = {},
): Promise<Page<AgentTurnOut>> {
  const res = await apiV2.GET('/api/agents/{slug}/turns/', {
    params: { path: { slug }, query: { limit: params.limit, offset: params.offset } },
  })
  return toPage(unwrap(res, 'listAgentTurns'))
}

export async function listAgentWorkProducts(
  slug: string,
  params: ListAgentsParams = {},
): Promise<Page<AgentWorkProductOut>> {
  const res = await apiV2.GET('/api/agents/{slug}/work-products/', {
    params: { path: { slug }, query: { limit: params.limit, offset: params.offset } },
  })
  return toPage(unwrap(res, 'listAgentWorkProducts'))
}

export async function listAgentSkills(slug: string): Promise<AgentSkillOut[]> {
  const res = await apiV2.GET('/api/agents/{slug}/skills/', { params: { path: { slug } } })
  return [...unwrap(res, 'listAgentSkills')]
}

// Plain array, not paginated.
export async function listAgentTasks(slug: string): Promise<AgentTaskOut[]> {
  const res = await apiV2.GET('/api/agents/{slug}/tasks/', { params: { path: { slug } } })
  return [...unwrap(res, 'listAgentTasks')]
}

export async function postTaskCommand(
  slug: string,
  taskId: number,
  body: Schemas['AgentTaskCommandIn'],
): Promise<PostCommandResult> {
  const res = await apiV2.POST('/api/agents/{slug}/tasks/{task_id}/commands', {
    params: { path: { slug, task_id: taskId } },
    body,
  })
  return unwrap(res, 'postTaskCommand')
}

export async function listAgentCommands(slug: string, status?: string): Promise<AgentCommandOut[]> {
  const res = await apiV2.GET('/api/agents/{slug}/commands', {
    params: { path: { slug }, query: { status } },
  })
  return [...unwrap(res, 'listAgentCommands')]
}

export async function listPendingCommands(slug: string): Promise<AgentCommandOut[]> {
  return listAgentCommands(slug, 'pending')
}
```

- [ ] **Step 4: Let the compiler resolve each endpoint's query params**

The `query` objects above are written from the current client's behaviour. The generated types are the authority on what each endpoint actually accepts — e.g. `GET /api/agents/` takes `limit` only (`apps/agents/api.py:59`), so passing `offset` there will not typecheck.

Where TS rejects a query param, **delete it** rather than casting around it. A param the client sent that the server never accepted is exactly the drift this migration exists to surface — note each one you find in the commit message.

Compare each signature against the current file before you replace it:

```bash
cd frontend && git show HEAD:src/api/agents.ts | grep -nE "^export (async function|interface|type)"
```

Every name and return type in your new file must match that list. If one doesn't, you've broken a caller.

- [ ] **Step 5: Typecheck — this is the real test**

There is no unit test for a type migration; the compiler is the test. Every caller (`NeedsYouSection`, `AgentTasksSection`, `TasksBoard`, the other five sections) compiles against these names, so any drift fails here.

```bash
cd frontend && npm run build
```

Expected: PASS. If a caller errors on a property that no longer exists, the hand-declared interface had drifted from the server — **fix the caller, not the alias.** That drift is the bug this task exists to kill; record it in the commit message.

- [ ] **Step 6: Verify workspace scoping survived**

The one behaviour that could silently regress. Confirm the middleware rewrites agent calls:

```bash
cd frontend && grep -n '"/api/agents"' src/api/client.v2.ts && grep -c "scopedAgentsPath" src/api/agents.ts
```

Expected: the prefix present, and `0` for `scopedAgentsPath` (the local rewrite is gone).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/agents.ts frontend/src/api/client.v2.ts
git commit -m "refactor(frontend): put the agent API on its generated types

The comment atop agents.ts claimed the /api/agents/* routes weren't in the
generated OpenAPI types. They are — all 19, including needs-you, and have been
for some time. So the hand-rolled fetch layer and ~15 hand-declared response
interfaces were duplicating a typed client that already existed.

Migrate to apiV2 + components['schemas']. agents.ts now declares no response
shapes of its own and cannot drift from the server. Registers /api/agents in
WS_SCOPED_API_PREFIXES so the middleware owns tenant rewriting and the local
scopedAgentsPath helper can go.

Prereq for the /supervisor surface, which would otherwise fork the drift into
a second consumer."
```

---

## Task 2: `Runner.workspace` FK

**Context:** `Runner` has no tenant. Task 3 gates on it, so the column lands first, on its own, with no behaviour change. `Turn` gets **no** FK — it derives its tenant via `turn.agent.workspace` (spec §8).

**Files:**
- Modify: `apps/harness/models.py:15-54` (the `Runner` model)
- Modify: `apps/harness/schemas.py:10-26` (`RunnerIn`, `RunnerOut`)
- Modify: `apps/harness/api.py:63-74` (`pair_runner`)
- Create: `apps/harness/migrations/0002_runner_workspace.py`
- Test: `tests/test_harness_models.py`

**Interfaces:**
- Consumes: `apps.workspaces.models.Workspace` (PK is a slug string); `apps.workspaces.services` as `wsvc` — `user_default_workspace(user) -> Workspace | None`.
- Produces: `Runner.workspace_id` (a slug string or `None`) — Task 3 gates on it, Task 5 filters on it. `RunnerIn.workspace: str = ""`; `RunnerOut.workspace: str | None`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_harness_models.py`:

```python
def test_runner_workspace_defaults_to_null_and_accepts_a_slug():
    """Nullable for migration safety — existing runners predate tenancy. The API
    assigns one at pairing (Task 2 step 5); the model must permit both."""
    from apps.harness.models import Runner

    bare = Runner.objects.create(name="legacy", kind=Runner.EMDASH)
    assert bare.workspace_id is None

    from django.contrib.auth.models import User
    from apps.workspaces.models import Workspace

    owner = User.objects.create_user("ws-owner", "ws-owner@dimagi.com", "pw")
    ws = Workspace.objects.create(slug="canopy", display_name="Canopy", created_by=owner)
    homed = Runner.objects.create(name="jj-mbp", kind=Runner.EMDASH, workspace=ws)
    assert homed.workspace_id == "canopy"  # PK is the slug, not an int
```

- [ ] **Step 2: Run it and watch it fail**

```bash
uv run pytest tests/test_harness_models.py::test_runner_workspace_defaults_to_null_and_accepts_a_slug -v
```

Expected: FAIL — `TypeError: Runner() got unexpected keyword arguments: 'workspace'`.

- [ ] **Step 3: Add the field**

In `apps/harness/models.py`, inside `class Runner`, after the `host` field:

```python
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="runners",
        help_text="The tenant that owns this runner. Nullable for migration "
        "safety; the API assigns one at pairing (the pairer's default workspace "
        "when unspecified). Mirrors Agent.workspace.",
    )
```

`PROTECT` and `null=True` mirror `Agent.workspace` (`apps/agents/models.py:31`) — deleting a workspace must not silently orphan runners.

- [ ] **Step 4: Generate the migration**

```bash
uv run python manage.py makemigrations harness --name runner_workspace
```

Expected: creates `apps/harness/migrations/0002_runner_workspace.py`. Open it and confirm it contains only `AddField` for `workspace` — nothing else. If it wants to alter other fields, your working tree has unrelated model drift; resolve that first.

- [ ] **Step 5: Assign a workspace at pairing**

In `apps/harness/schemas.py`:

```python
class RunnerIn(Schema):
    name: str
    kind: str  # emdash|cloud|remote
    capabilities: dict = {}
    host: str = ""  # macOS user@hostname — load-bearing for session reuse across accounts
    workspace: str = ""  # tenant slug; defaults to the pairer's default workspace


class RunnerOut(Schema):
    id: uuid.UUID
    name: str
    kind: str
    status: str
    status_note: str
    last_heartbeat_at: dt.datetime | None
    capabilities: dict
    host: str
    workspace: str | None

    @staticmethod
    def resolve_workspace(obj) -> str | None:
        return obj.workspace_id
```

In `apps/harness/api.py`, add the import and rewrite `pair_runner`:

```python
from apps.workspaces import services as wsvc
```

```python
@router.post("/runners/", response={201: RunnerOut})
def pair_runner(request: HttpRequest, payload: RunnerIn):
    if payload.kind not in dict(Runner.KIND_CHOICES):
        raise HttpError(422, f"unknown runner kind '{payload.kind}'")
    wsvc.auto_join_workspaces(request.user)
    explicit = (payload.workspace or "").strip()
    if explicit:
        # Membership-gated: a missing workspace and a non-member get the same
        # 404 (no existence leak), exactly as apps/agents does on explicit homing.
        if not wsvc.is_member(request.user, explicit):
            raise HttpError(404, f"workspace '{explicit}' not found")
        ws_slug = explicit
    else:
        default = wsvc.user_default_workspace(request.user)
        ws_slug = default.slug if default else None
    runner = Runner.objects.create(
        name=payload.name,
        kind=payload.kind,
        capabilities=payload.capabilities,
        host=payload.host,
        paired_by=request.user,
        workspace_id=ws_slug,
    )
    return 201, runner
```

- [ ] **Step 6: Run the tests**

```bash
uv run pytest tests/test_harness_models.py tests/test_harness_api.py -v
```

Expected: PASS, including the pre-existing lifecycle tests. Those pair a runner without a `workspace` key — they must still work, which is what the `""` default and the null fallback guarantee.

- [ ] **Step 7: Commit**

```bash
git add apps/harness/models.py apps/harness/schemas.py apps/harness/api.py apps/harness/migrations/0002_runner_workspace.py tests/test_harness_models.py
git commit -m "feat(harness): Runner.workspace FK

Runner had no tenant. Add the FK (nullable + PROTECT, mirroring Agent.workspace)
and assign it at pairing — explicit slug if given and the pairer is a member,
else the pairer's default workspace. No gating yet; that's the next commit.

Turn deliberately gets no FK: its tenant derives via turn.agent.workspace. See
spec 2026-07-14 section 8."
```

---

## Task 3: Membership-gate the harness

**Context:** Today any authenticated PAT can enqueue a turn for any agent, claim as any runner, append events to any turn, or finish any turn (`TODOS.md:96-98`). This is the hole the phone would build remote actuation on top of. Copy the pattern from `apps/agents/api.py:42-54` verbatim — the harness should be indistinguishable from it.

**Files:**
- Modify: `apps/harness/api.py` (`_runner_or_404`, `_turn_or_404`, `enqueue_turn`, `list_turns`, `resolve_session`, `record_session`)
- Create: `tests/test_harness_authz.py`

**Interfaces:**
- Consumes: `Runner.workspace_id` (Task 2); `wsvc.auto_join_workspaces(user)`, `wsvc.is_member(user, slug) -> bool`, `wsvc.user_workspace_slugs(user) -> set[str]`.
- Produces: `_runner_or_404(request, runner_id) -> Runner` and `_turn_or_404(request, turn_id) -> Turn` — **note the added `request` first argument**; every existing call site must be updated. Also `_agent_or_404(request, slug) -> Agent`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_harness_authz.py`:

```python
"""Authorization tests for /api/harness — a non-member must get 404, never 403,
and never a leak that the resource exists. Mirrors apps/agents' posture."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.agents.models import Agent
from apps.harness.models import Runner, Turn
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db


@pytest.fixture()
def owner():
    return User.objects.create_user("owner", "owner@dimagi.com", "pw")


@pytest.fixture()
def workspace(owner):
    ws = Workspace.objects.create(slug="canopy", display_name="Canopy", created_by=owner)
    WorkspaceMembership.objects.create(user=owner, workspace=ws, role=WorkspaceMembership.OWNER)
    return ws


@pytest.fixture()
def stranger():
    """Authenticated, but a member of nothing. auto_join_workspaces keys off the
    email domain, so use one outside the auto-join set."""
    return User.objects.create_user("stranger", "stranger@example.org", "pw")


@pytest.fixture()
def agent(workspace):
    return Agent.objects.create(slug="echo", name="Echo", workspace=workspace)


@pytest.fixture()
def owner_client(owner):
    c = Client()
    c.force_login(owner)
    return c


@pytest.fixture()
def stranger_client(stranger):
    c = Client()
    c.force_login(stranger)
    return c


def _enqueue(client, slug="echo", key="k1"):
    return client.post(
        "/api/harness/turns/",
        {"agent_slug": slug, "origin": "manual", "idempotency_key": key, "prompt": "/echo:turn"},
        content_type="application/json",
    )


def test_member_can_enqueue(owner_client, agent):
    assert _enqueue(owner_client).status_code == 201


def test_stranger_enqueueing_for_someone_elses_agent_gets_404(stranger_client, agent):
    """404, not 403: a non-member must not learn the agent exists."""
    resp = _enqueue(stranger_client)
    assert resp.status_code == 404


def test_stranger_cannot_read_someone_elses_turn(owner_client, stranger_client, agent):
    turn_id = _enqueue(owner_client).json()["id"]
    assert stranger_client.get(f"/api/harness/turns/{turn_id}").status_code == 404


def test_stranger_cannot_finish_someone_elses_turn(owner_client, stranger_client, agent):
    turn_id = _enqueue(owner_client).json()["id"]
    resp = stranger_client.post(
        f"/api/harness/turns/{turn_id}/finish",
        {"status": "done", "result_note": "pwned"},
        content_type="application/json",
    )
    assert resp.status_code == 404
    assert Turn.objects.get(pk=turn_id).status == Turn.QUEUED  # untouched


def test_stranger_cannot_heartbeat_someone_elses_runner(owner_client, stranger_client, workspace):
    rid = owner_client.post(
        "/api/harness/runners/",
        {"name": "jj-mbp", "kind": "emdash", "capabilities": {"agents": ["echo"]}},
        content_type="application/json",
    ).json()["id"]
    resp = stranger_client.post(
        f"/api/harness/runners/{rid}/heartbeat",
        {"active_turn_ids": [], "degraded": False, "note": ""},
        content_type="application/json",
    )
    assert resp.status_code == 404


def test_stranger_cannot_claim_as_someone_elses_runner(owner_client, stranger_client, agent):
    rid = owner_client.post(
        "/api/harness/runners/",
        {"name": "jj-mbp", "kind": "emdash", "capabilities": {"agents": ["echo"]}},
        content_type="application/json",
    ).json()["id"]
    _enqueue(owner_client)
    assert stranger_client.post(f"/api/harness/runners/{rid}/claim").status_code == 404


def test_list_turns_only_shows_my_tenants_turns(owner_client, stranger_client, agent):
    _enqueue(owner_client)
    resp = stranger_client.get("/api/harness/turns/")
    assert resp.status_code == 200
    assert resp.json() == []  # filtered, not 404 — a list of nothing


def test_null_workspace_agent_stays_ungated(owner_client):
    """Agents predating tenancy have workspace=None. They must keep working —
    the existing suite creates agents exactly this way."""
    Agent.objects.create(slug="legacy", name="Legacy")
    assert _enqueue(owner_client, slug="legacy", key="k-legacy").status_code == 201
```

- [ ] **Step 2: Run them and watch them fail**

```bash
uv run pytest tests/test_harness_authz.py -v
```

Expected: the `test_member_can_enqueue` and `test_null_workspace_agent_stays_ungated` tests PASS (no gate exists yet, so everything is permitted); every `stranger` test FAILS, returning 200/201/204 where 404 is expected. That failure *is* the vulnerability, now pinned by a test.

- [ ] **Step 3: Implement the gate**

In `apps/harness/api.py`, add the import:

```python
from apps.workspaces import services as wsvc
```

Replace `_runner_or_404` and `_turn_or_404`, and add `_agent_or_404`:

```python
def _agent_or_404(request: HttpRequest, slug: str) -> Agent:
    """Resolve an agent, gated by workspace membership. A non-member gets the same
    404 as a missing agent (no existence leak). Mirrors apps/agents/api.py:42."""
    agent = Agent.objects.filter(slug=slug).first()
    if agent is None:
        raise HttpError(404, f"agent '{slug}' not found")
    wsvc.auto_join_workspaces(request.user)
    ws = getattr(request, "workspace_slug", None)
    if ws and agent.workspace_id != ws:
        raise HttpError(404, f"agent '{slug}' not found")  # wrong tenant
    if agent.workspace_id and not wsvc.is_member(request.user, agent.workspace_id):
        raise HttpError(404, f"agent '{slug}' not found")
    return agent


def _runner_or_404(request: HttpRequest, runner_id: uuid.UUID) -> Runner:
    """Resolve a live runner, gated on BOTH workspace membership and the pairing
    user. Binding to runner.paired_by (not to a specific token) is deliberate:
    BearerTokenAuthMiddleware stamps request.user = token.user and discards which
    token was used, and PATs are rotated by design (canopy:canopy-web-pat-mint is
    documented "re-run to rotate"), so token-binding would break the runner on
    every rotation. Accepted residual: another token of the SAME user still works.
    """
    runner = Runner.objects.filter(pk=runner_id).exclude(status=Runner.RETIRED).first()
    if runner is None:
        raise HttpError(404, "runner not found")
    wsvc.auto_join_workspaces(request.user)
    if runner.workspace_id and not wsvc.is_member(request.user, runner.workspace_id):
        raise HttpError(404, "runner not found")
    if runner.paired_by_id and runner.paired_by_id != request.user.id:
        raise HttpError(404, "runner not found")
    return runner


def _turn_or_404(request: HttpRequest, turn_id: uuid.UUID) -> Turn:
    """Resolve a turn, gated via its agent's workspace — a Turn has no workspace
    FK of its own; it derives its tenant one hop away (spec section 8)."""
    turn = Turn.objects.select_related("agent", "claimed_by").filter(pk=turn_id).first()
    if turn is None:
        raise HttpError(404, "turn not found")
    _agent_or_404(request, turn.agent.slug)  # raises 404 on wrong tenant
    return turn
```

- [ ] **Step 4: Update every call site**

Both helpers gained a `request` argument. In `apps/harness/api.py`, apply these exact substitutions:

- `runner_heartbeat`: `_runner_or_404(runner_id)` → `_runner_or_404(request, runner_id)`
- `claim_turn`: `_runner_or_404(runner_id)` → `_runner_or_404(request, runner_id)`
- `resolve_session`: `_runner_or_404(runner_id)` → `_runner_or_404(request, runner_id)`; and replace the `Agent.objects.filter(...)` block with `agent = _agent_or_404(request, payload.agent_slug)`
- `record_session`: same two changes as `resolve_session`
- `get_turn`, `append_turn_events`, `read_turn_events`, `start_turn`, `finish_turn`: `_turn_or_404(turn_id)` → `_turn_or_404(request, turn_id)`

Then rewrite `enqueue_turn` and `list_turns`:

```python
@router.post("/turns/", response={200: TurnOut, 201: TurnOut})
def enqueue_turn(request: HttpRequest, payload: TurnIn):
    agent = _agent_or_404(request, payload.agent_slug)
    if payload.origin not in dict(Turn.ORIGIN_CHOICES):
        raise HttpError(422, f"unknown origin '{payload.origin}'")
    if payload.routing not in dict(Turn.ROUTING_CHOICES):
        raise HttpError(422, f"unknown routing '{payload.routing}'")
    turn, created = services.enqueue_turn(
        agent=agent,
        origin=payload.origin,
        idempotency_key=payload.idempotency_key,
        prompt=payload.prompt,
        origin_ref=payload.origin_ref,
        routing=payload.routing,
    )
    return (201 if created else 200), turn


@router.get("/turns/", response=list[TurnOut])
def list_turns(request: HttpRequest, agent: str | None = None, status: str | None = None):
    wsvc.auto_join_workspaces(request.user)
    ws = getattr(request, "workspace_slug", None)
    slugs = {ws} if ws else wsvc.user_workspace_slugs(request.user)
    qs = Turn.objects.select_related("agent", "claimed_by").order_by("-created_at")
    if agent:
        qs = qs.filter(agent__slug=agent)
    if status:
        qs = qs.filter(status__in=status.split(","))
    # Tenant filter: a turn's tenant is its agent's. Null-workspace agents stay
    # visible (ungated, per the migration-safety rule).
    qs = qs.filter(Q(agent__workspace_id__in=slugs) | Q(agent__workspace_id__isnull=True))
    return list(qs[:100])  # filter BEFORE slicing — a sliced queryset cannot be filtered
```

Add to the imports at the top of `apps/harness/api.py`:

```python
from django.db.models import Q
```

- [ ] **Step 5: Run the authz tests**

```bash
uv run pytest tests/test_harness_authz.py -v
```

Expected: all PASS.

- [ ] **Step 6: Run the whole harness suite — no regressions**

The pre-existing tests pair runners and create agents with **no workspace**, which must remain permitted.

```bash
uv run pytest tests/test_harness_api.py tests/test_harness_services.py tests/test_harness_session_link.py tests/test_harness_models.py -v
```

Expected: all PASS. If a pre-existing test now 404s, the null-workspace path was gated by mistake — the `if agent.workspace_id and ...` guard is what prevents that.

- [ ] **Step 7: Run the full backend suite**

The runner and other callers hit these endpoints; a signature change can ripple.

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/harness/api.py tests/test_harness_authz.py
git commit -m "feat(harness): membership-gate the control plane

Closes TODOS.md:96-98. Any authenticated PAT could enqueue a turn for any
agent, claim as any runner, or finish any turn. Contained while the only actor
was your own daemon — not once a phone can drive it remotely.

Gate copied from apps/agents/api.py:42 so the two are indistinguishable: 404
not 403, so non-membership never leaks existence. A Turn derives its tenant via
agent.workspace (no FK of its own). Runner ops additionally bind to paired_by —
the user, not a specific token, since BearerTokenAuthMiddleware discards token
identity and PATs are rotated by design.

Null-workspace agents stay ungated (migration safety); the pre-existing suite
covers that path."
```

---

# PHASE 1

## Task 4: `GET /api/harness/runners/`

**Context:** The harness has `POST /runners/` (pair) but **no list endpoint** — the supervisor's runner status has nothing to read. Small, and needed before the UI.

**Files:**
- Modify: `apps/harness/api.py` (add the route after `pair_runner`)
- Test: `tests/test_harness_api.py`

**Interfaces:**
- Consumes: `_runner_or_404`'s gating rules (Task 3); `RunnerOut` (Task 2, now carrying `workspace`).
- Produces: `GET /api/harness/runners/` → `list[RunnerOut]`, tenant-filtered, excluding retired, newest heartbeat first. Task 6's `RunnerStatus.tsx` renders it.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_harness_api.py`:

```python
def test_list_runners_returns_my_runners_newest_heartbeat_first(client, agent):
    rid = _pair(client)
    _hb(client, rid)
    resp = client.get("/api/harness/runners/")
    assert resp.status_code == 200
    body = resp.json()
    assert [r["id"] for r in body] == [rid]
    assert body[0]["status"] == "online"
    assert body[0]["host"] == ""


def test_list_runners_excludes_retired(client, agent):
    from apps.harness.models import Runner

    rid = _pair(client)
    Runner.objects.filter(pk=rid).update(status=Runner.RETIRED)
    assert client.get("/api/harness/runners/").json() == []
```

- [ ] **Step 2: Run and watch it fail**

```bash
uv run pytest tests/test_harness_api.py::test_list_runners_returns_my_runners_newest_heartbeat_first -v
```

Expected: FAIL — 404 (or 405), the route doesn't exist.

- [ ] **Step 3: Implement**

In `apps/harness/api.py`, immediately after `pair_runner`:

```python
@router.get("/runners/", response=list[RunnerOut], summary="List my runners")
def list_runners(request: HttpRequest):
    """The supervisor's runner status. Tenant-filtered and scoped to the pairing
    user, matching _runner_or_404's gate — a runner you cannot act on must not be
    listed. Retired runners are excluded at lookup, as everywhere else."""
    wsvc.auto_join_workspaces(request.user)
    ws = getattr(request, "workspace_slug", None)
    slugs = {ws} if ws else wsvc.user_workspace_slugs(request.user)
    qs = (
        Runner.objects.exclude(status=Runner.RETIRED)
        .filter(Q(workspace_id__in=slugs) | Q(workspace_id__isnull=True))
        .filter(Q(paired_by=request.user) | Q(paired_by__isnull=True))
        .order_by(models.F("last_heartbeat_at").desc(nulls_last=True))
    )
    return list(qs[:50])
```

Add to the imports:

```python
from django.db import models
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_harness_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/harness/api.py tests/test_harness_api.py
git commit -m "feat(harness): GET /runners/ — list my runners

The harness could pair a runner but never list them, so the supervisor's runner
status had nothing to read. Tenant-filtered and paired_by-scoped to match
_runner_or_404 — a runner you can't act on isn't listed. Retired excluded."
```

---

## Task 5: `GET /api/agents/needs-you` — fleet-wide

**Context:** `needs_you()` is per-agent, and the supervisor is cross-fleet. The menubar solves this with a client-side fan-out over a `ThreadPoolExecutor` (`menubar.py:336`) — an N+1 that is tolerable on a LAN and bad on cellular, which is where this surface is going. One endpoint, one round trip.

**Files:**
- Modify: `apps/agents/api.py` (add the route **before** `_get_agent_or_404`'s `/{slug}/` routes)
- Modify: `apps/agents/schemas.py` (add `FleetNeedsYouOut`)
- Create: `tests/test_agents_fleet_needs_you.py`

**Interfaces:**
- Consumes: `services.needs_you(agent, notify_limit=5) -> dict` with keys `agent_slug`, `waiting_count`, `items`; `services.list_agents() -> list[Agent]`; `NeedsYouOut` (`apps/agents/schemas.py:266`).
- Produces: `GET /api/agents/needs-you` → `FleetNeedsYouOut{ total_waiting: int, agents: list[NeedsYouOut] }`. Task 7's `WaitingOnYou.tsx` renders it; the generated types expose it as `components['schemas']['FleetNeedsYouOut']`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_agents_fleet_needs_you.py`:

```python
"""The supervisor's home screen: one call for the whole fleet's needs-you."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.agents.models import Agent, AgentTask
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db


@pytest.fixture()
def owner():
    return User.objects.create_user("owner", "owner@dimagi.com", "pw")


@pytest.fixture()
def workspace(owner):
    ws = Workspace.objects.create(slug="canopy", display_name="Canopy", created_by=owner)
    WorkspaceMembership.objects.create(user=owner, workspace=ws, role=WorkspaceMembership.OWNER)
    return ws


@pytest.fixture()
def client(owner):
    c = Client()
    c.force_login(owner)
    return c


def test_fleet_needs_you_sums_waiting_across_agents(client, workspace):
    echo = Agent.objects.create(slug="echo", name="Echo", workspace=workspace)
    hal = Agent.objects.create(slug="hal", name="Hal", workspace=workspace)
    AgentTask.objects.create(agent=echo, ext_id="t1", title="Draft a story", status="suggested")
    AgentTask.objects.create(agent=hal, ext_id="t2", title="Sweep security", status="suggested")

    resp = client.get("/api/agents/needs-you")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_waiting"] == 2
    assert {a["agent_slug"] for a in body["agents"]} == {"echo", "hal"}


def test_fleet_needs_you_ranks_busiest_agent_first(client, workspace):
    quiet = Agent.objects.create(slug="quiet", name="Quiet", workspace=workspace)
    busy = Agent.objects.create(slug="busy", name="Busy", workspace=workspace)
    AgentTask.objects.create(agent=quiet, ext_id="q1", title="One", status="suggested")
    for i in range(3):
        AgentTask.objects.create(agent=busy, ext_id=f"b{i}", title=f"Task {i}", status="suggested")

    body = client.get("/api/agents/needs-you").json()
    assert [a["agent_slug"] for a in body["agents"]] == ["busy", "quiet"]


def test_fleet_needs_you_excludes_other_tenants(client, owner):
    other_owner = User.objects.create_user("other", "other@example.org", "pw")
    other_ws = Workspace.objects.create(slug="other", display_name="Other", created_by=other_owner)
    secret = Agent.objects.create(slug="secret", name="Secret", workspace=other_ws)
    AgentTask.objects.create(agent=secret, ext_id="s1", title="Classified", status="suggested")

    body = client.get("/api/agents/needs-you").json()
    assert body["total_waiting"] == 0
    assert body["agents"] == []
```

- [ ] **Step 2: Run and watch it fail**

```bash
uv run pytest tests/test_agents_fleet_needs_you.py -v
```

Expected: FAIL — 404, or a route collision resolving `needs-you` as a `{slug}`.

- [ ] **Step 3: Add the schema**

In `apps/agents/schemas.py`, immediately after `NeedsYouOut` (line ~270):

```python
class FleetNeedsYouOut(StrictModel):
    """Every agent's needs-you in one response — the supervisor's home screen.
    One round trip instead of an N+1 fan-out, which matters on cellular."""

    total_waiting: int  # sum of per-agent waiting_count — the app-icon badge
    agents: list[NeedsYouOut] = Field(default_factory=list)
```

- [ ] **Step 4: Add the route**

In `apps/agents/api.py`. **Placement matters:** it must be declared *before* the `/{slug}/…` routes so Ninja does not resolve `needs-you` as a slug. Put it immediately after `list_agents`:

```python
@router.get("/needs-you", response=FleetNeedsYouOut,
            summary="Fleet-wide needs-you (the supervisor home screen)")
def fleet_needs_you(request: HttpRequest) -> FleetNeedsYouOut:
    """Every agent's needs-you in one call, ranked busiest-first. Declared BEFORE
    the /{slug}/ routes so 'needs-you' isn't resolved as a slug. Tenant scoping
    mirrors list_agents exactly."""
    wsvc.auto_join_workspaces(request.user)
    ws = getattr(request, "workspace_slug", None)
    slugs = {ws} if ws else wsvc.user_workspace_slugs(request.user)
    mine = [
        a for a in services.list_agents()
        if a.workspace_id in slugs or (ws is None and a.workspace_id is None)
    ]
    blocks = [NeedsYouOut.model_validate(services.needs_you(a)) for a in mine]
    blocks.sort(key=lambda b: (-b.waiting_count, b.agent_slug))
    return FleetNeedsYouOut(
        total_waiting=sum(b.waiting_count for b in blocks),
        agents=blocks,
    )
```

Add `FleetNeedsYouOut` to the schema imports at the top of the file.

- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/test_agents_fleet_needs_you.py -v
```

Expected: PASS. If `test_fleet_needs_you_sums_waiting_across_agents` 404s, the route is declared after `/{slug}/` — move it above.

- [ ] **Step 6: Confirm no route collision**

`GET /api/agents/echo/` must still resolve to the detail route, not the new one:

```bash
uv run pytest tests/test_agents.py -q
```

Expected: PASS.

- [ ] **Step 7: Regenerate the frontend types**

The new endpoint must reach the typed client. This needs a server on port 8000:

```bash
uv run python manage.py runserver 8000 &
sleep 5
cd frontend && npm run gen:api
kill %1
```

Verify it landed:

```bash
cd frontend && grep -c '"/api/agents/needs-you"' src/api/generated.ts
```

Expected: `1`.

- [ ] **Step 8: Commit**

```bash
git add apps/agents/api.py apps/agents/schemas.py tests/test_agents_fleet_needs_you.py frontend/src/api/generated.ts
git commit -m "feat(agents): GET /needs-you — fleet-wide supervisor inbox

needs_you() was per-agent, so a cross-fleet view meant an N+1 fan-out — what
menubar.py does with a ThreadPoolExecutor. Fine on a LAN, bad on cellular,
which is where this surface is headed. One call, ranked busiest-first, with
total_waiting for the app-icon badge.

Declared before the /{slug}/ routes so 'needs-you' isn't read as a slug."
```

---

## Task 6: The `/supervisor` route — runner status + agent KPI cards

**Context:** The one React surface the phone, the menubar's WKWebView, and the desktop browser will all load (spec §"The thesis"). This task builds the shell and the two read-only bands; Task 7 adds the inbox.

**Files:**
- Create: `frontend/src/components/supervisor/RunnerStatus.tsx`
- Create: `frontend/src/components/supervisor/AgentKpiCard.tsx`
- Create: `frontend/src/pages/SupervisorPage.tsx`
- Modify: `frontend/src/router.tsx`
- Test: `cd frontend && npm run build`

**Interfaces:**
- Consumes: `listAgents()` → `Page<AgentOut>` and `AgentOut` from `@/api/agents` (Task 1); `apiV2` from `@/api/client.v2`; `Skeleton` from `canopy-ui`.
- Produces: `frontend/src/api/harness.ts` exporting `listRunners(): Promise<RunnerOut[]>` and `RunnerOut` — Task 7 imports both from there, not from `@/api/agents`. Also `<RunnerStatus runners={RunnerOut[]} />`, `<AgentKpiCard agent={AgentOut} waiting={number} />`, and the route `/supervisor`. Task 7 adds `<WaitingOnYou />` to `SupervisorPage`.

- [ ] **Step 1: Add a typed harness client**

`RunnerOut` is a harness type, not an agent one — it goes in its own file rather than into `agents.ts`. Create `frontend/src/api/harness.ts`:

```ts
// Harness API client — the runner registry and turn lifecycle. Separate from
// ./agents because a Runner is not an agent: the harness is framework tier and
// the agent surface is product tier (see ARCHITECTURE.md).
import { apiV2 } from './client.v2'
import type { components } from './generated'

export type RunnerOut = components['schemas']['RunnerOut']

function unwrap<T>(res: { data?: T; error?: unknown }, what: string): T {
  if (res.error !== undefined || res.data === undefined) {
    throw new Error(`${what} failed: ${JSON.stringify(res.error ?? 'no data')}`)
  }
  return res.data
}

export async function listRunners(): Promise<RunnerOut[]> {
  const res = await apiV2.GET('/api/harness/runners/')
  return [...unwrap(res, 'listRunners')]
}
```

The duplicated `unwrap` is deliberate and is the smaller of two evils: the alternative is `agents.ts` importing from `harness.ts` or a shared module existing solely for a 5-line helper. If a third client appears, extract it then — not now.

**Note:** `/api/harness` is deliberately **not** added to `WS_SCOPED_API_PREFIXES` — the harness has no `/api/w/{ws}/harness/…` tenant mount, so the rewrite would produce a 404. It scopes server-side off `request.user` instead (Task 4).

- [ ] **Step 2: Build `RunnerStatus`**

Create `frontend/src/components/supervisor/RunnerStatus.tsx`:

```tsx
import type { JSX } from 'react'
import type { RunnerOut } from '@/api/harness'

// Mirrors menubar.py's four derived states (_runner_state, menubar.py:224) so
// the two surfaces read identically — until Phase 5, when the panel loads this
// page and there is only one.
const DOT: Record<string, string> = {
  online: 'bg-success',
  degraded: 'bg-warning',
  stale: 'bg-warning',
  disconnected: 'bg-muted-foreground',
}

function relative(iso: string | null): string {
  if (!iso) return 'never'
  const secs = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (secs < 60) return `${secs}s ago`
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`
  return `${Math.round(secs / 3600)}h ago`
}

export function RunnerStatus({ runners }: { runners: RunnerOut[] }): JSX.Element {
  if (runners.length === 0) {
    return (
      <p className="rounded-lg border border-border bg-card p-3 text-[13px] text-muted-foreground">
        No runner paired. Work you queue will wait until one comes online.
      </p>
    )
  }
  return (
    <div className="flex flex-col gap-2" data-testid="runner-status">
      {runners.map((r) => (
        <div
          key={r.id}
          className="flex items-center gap-2.5 rounded-lg border border-border bg-card px-3 py-2"
          data-testid={`runner-${r.name}`}
        >
          <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[r.status] ?? 'bg-muted-foreground'}`} />
          <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-foreground">{r.name}</span>
          {r.host && <span className="hidden truncate text-[11px] text-foreground-subtle sm:inline">{r.host}</span>}
          <span className="shrink-0 text-[11px] text-muted-foreground">{relative(r.last_heartbeat_at)}</span>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 3: Build `AgentKpiCard`**

Create `frontend/src/components/supervisor/AgentKpiCard.tsx`:

```tsx
import type { JSX } from 'react'
import { Link } from 'react-router-dom'
import type { AgentOut } from '@/api/agents'

// One agent's KPIs — the React counterpart of menubar.py's _card (menubar.py:385).
// Links to the agent's OWN workspace: the fleet spans workspaces, and the flat
// /agents/<slug> path resolves the ACTIVE workspace, which 404s agents living
// elsewhere (the bug that hid Ada and Eva — commit 483c821).
export function AgentKpiCard({ agent, waiting }: { agent: AgentOut; waiting: number }): JSX.Element {
  const href = agent.workspace ? `/w/${agent.workspace}/agents/${agent.slug}` : `/agents/${agent.slug}`
  return (
    <Link
      to={href}
      data-testid={`agent-card-${agent.slug}`}
      className="flex items-center gap-3 rounded-lg border border-border bg-card p-3 transition-colors hover:border-primary/40"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-semibold text-foreground">{agent.name}</p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          {waiting > 0 ? `${waiting} waiting on you` : 'nothing waiting'}
        </p>
      </div>
      {waiting > 0 && (
        <span className="shrink-0 rounded border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-[11px] font-medium text-primary">
          {waiting}
        </span>
      )}
    </Link>
  )
}
```

**Note:** this reads `agent.workspace`. Confirm the property name against the generated schema before running:

```bash
cd frontend && grep -A 12 "AgentOut: {" src/api/generated.ts | head -14
```

If the field is absent or named differently, use the actual name — do not add a backend field for it.

- [ ] **Step 4: Build the page**

Create `frontend/src/pages/SupervisorPage.tsx`:

```tsx
import { useEffect, useState, type JSX } from 'react'
import { listAgents, type AgentOut } from '@/api/agents'
import { listRunners, type RunnerOut } from '@/api/harness'
import { RunnerStatus } from '@/components/supervisor/RunnerStatus'
import { AgentKpiCard } from '@/components/supervisor/AgentKpiCard'
import { Skeleton } from 'canopy-ui'

// The ONE supervisor surface (spec 2026-07-14). Three consumers will load this
// same route: the phone as an installed PWA, the menubar's WKWebView (Phase 5),
// and a desktop browser. Phone-first layout — a single column that widens.
export default function SupervisorPage(): JSX.Element {
  const [agents, setAgents] = useState<AgentOut[] | null>(null)
  const [runners, setRunners] = useState<RunnerOut[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([listAgents({ limit: 100 }), listRunners()])
      .then(([page, rs]) => {
        if (cancelled) return
        setAgents(page.items)
        setRunners(rs)
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load')
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (error) {
    return (
      <div className="mx-auto max-w-2xl p-4">
        <p className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-[13px] text-destructive">
          {error}
        </p>
      </div>
    )
  }

  const loading = agents === null || runners === null

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5 p-4" data-testid="supervisor-page">
      <header>
        <h1 className="text-lg font-semibold text-foreground">Supervisor</h1>
        <p className="mt-0.5 text-[12px] text-muted-foreground">Your fleet, and what it needs from you.</p>
      </header>

      <section>
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Runners</h2>
        {loading ? <Skeleton className="h-12 w-full" /> : <RunnerStatus runners={runners} />}
      </section>

      <section>
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Agents</h2>
        {loading ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {agents.map((a) => (
              <AgentKpiCard key={a.slug} agent={a} waiting={0} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
```

`waiting={0}` is a deliberate placeholder for exactly one task — Task 7 wires the real counts from the fleet endpoint. It is not a TODO left behind; Task 7's first step replaces it.

- [ ] **Step 5: Mount the route**

In `frontend/src/router.tsx`, add the import alongside the other page imports:

```tsx
import SupervisorPage from '@/pages/SupervisorPage'
```

Add the route inside the `AppLayout` children array, next to the other root-level personal routes (beside `/insights`, `/sessions`):

```tsx
      { path: '/supervisor', element: <SupervisorPage /> },
```

`/supervisor` is a **root** route, not `/w/:workspace/…`: the fleet spans workspaces (commit `483c821`), so the supervisor is deliberately cross-tenant — like `/insights`. Each card links into its agent's own workspace.

- [ ] **Step 6: Typecheck and build**

```bash
cd frontend && npm run build
```

Expected: PASS. A failure on `RunnerOut` means Task 5's `gen:api` step didn't run or the harness schema didn't land — re-run it.

- [ ] **Step 7: Look at it**

```bash
cd frontend && npm run dev
```

Open `http://localhost:3000/supervisor`. Expect the header, a runner band, and agent cards. Resize to a 390px-wide viewport: the layout must stay single-column with **no horizontal scroll**.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/SupervisorPage.tsx frontend/src/components/supervisor/ frontend/src/router.tsx frontend/src/api/harness.ts
git commit -m "feat(frontend): the /supervisor route — runners + agent KPIs

The one supervisor surface. Three consumers will load this same route: the
phone as an installed PWA, the menubar's WKWebView (Phase 5), and a desktop
browser. Today it renders in a browser; nothing here is mobile-specific yet.

A ROOT route, not /w/:workspace — the fleet spans workspaces, so like /insights
this is deliberately cross-tenant, and each card links into its agent's own
workspace (the 483c821 bug that hid Ada and Eva).

Waiting counts are stubbed at 0; the next commit wires the fleet endpoint."
```

---

## Task 7: The cross-fleet "Waiting on you" inbox

**Context:** The reason the phone exists. `NeedsYouSection` is per-agent and rail-mounted; this is the cross-fleet, phone-first equivalent, reading Task 5's single endpoint. It renders **read-only rows that link out** — acting on items (accept/decline inline) is Phase 3, and adding it here would drag `TaskCard` and its command-posting into a screen that has no composer yet.

**Files:**
- Create: `frontend/src/components/supervisor/WaitingOnYou.tsx`
- Modify: `frontend/src/pages/SupervisorPage.tsx`
- Modify: `frontend/src/api/agents.ts`
- Test: `cd frontend && npm run build`

**Interfaces:**
- Consumes: `GET /api/agents/needs-you` (Task 5) → `FleetNeedsYouOut`; `NeedsYouItem`, `NeedsYouType` from `@/api/agents` (Task 1).
- Produces: `getFleetNeedsYou(): Promise<FleetNeedsYouOut>`; `<WaitingOnYou fleet={FleetNeedsYouOut} />`. Phase 2's push trigger reads `total_waiting` for the badge.

- [ ] **Step 1: Add the typed client call**

Append to `frontend/src/api/agents.ts`:

```ts
export type FleetNeedsYouOut = Schemas['FleetNeedsYouOut']

export async function getFleetNeedsYou(): Promise<FleetNeedsYouOut> {
  const res = await apiV2.GET('/api/agents/needs-you')
  return unwrap(res, 'getFleetNeedsYou')
}
```

- [ ] **Step 2: Build `WaitingOnYou`**

Create `frontend/src/components/supervisor/WaitingOnYou.tsx`:

```tsx
import type { JSX } from 'react'
import type { FleetNeedsYouOut, NeedsYouItem, NeedsYouType } from '@/api/agents'

// Cross-fleet "waiting on you" — the React counterpart of menubar.py's section
// (menubar.py:427). Ranked exactly as the server ranks it: review, then
// question, then notify. Read-only for now: rows link out. Acting on an item
// inline is Phase 3, with the composer.
const RANK: NeedsYouType[] = ['review', 'question', 'notify']

const BAND: Record<NeedsYouType, { label: string; dot: string }> = {
  review: { label: 'Review', dot: 'bg-info' },
  question: { label: 'Question', dot: 'bg-warning' },
  notify: { label: 'Notify', dot: 'bg-primary/50' },
}

type Row = NeedsYouItem & { agent_slug: string }

function ItemRow({ item }: { item: Row }): JSX.Element {
  const body = (
    <>
      <div className="flex items-start gap-2">
        <p className="min-w-0 flex-1 text-[13px] font-semibold leading-snug text-foreground">{item.title}</p>
        {item.url && <span aria-hidden className="shrink-0 text-primary/70">↗</span>}
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        {item.agent_slug}
        {item.subtitle ? ` · ${item.subtitle}` : ''}
      </p>
    </>
  )
  const cls = 'block rounded-lg border border-border bg-card p-3 transition-colors hover:border-primary/40'
  return item.url ? (
    <a href={item.url} target="_blank" rel="noreferrer" className={cls} data-testid={`waiting-${item.ref_kind}-${item.ref_id}`}>
      {body}
    </a>
  ) : (
    <div className={cls} data-testid={`waiting-${item.ref_kind}-${item.ref_id}`}>{body}</div>
  )
}

export function WaitingOnYou({ fleet }: { fleet: FleetNeedsYouOut }): JSX.Element {
  // Flatten agent-grouped blocks into one cross-fleet list, tagging each row
  // with its agent — on a phone the ranked queue matters more than the grouping.
  const rows: Row[] = fleet.agents.flatMap((block) =>
    (block.items ?? []).map((item) => ({ ...item, agent_slug: block.agent_slug })),
  )

  if (rows.length === 0) {
    return (
      <p className="rounded-lg border border-border bg-card p-3 text-[13px] text-muted-foreground" data-testid="waiting-empty">
        Nothing waiting on you.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-3" data-testid="waiting-on-you">
      {RANK.map((type) => {
        const band = rows.filter((r) => r.type === type)
        if (band.length === 0) return null
        return (
          <section key={type}>
            <div className="mb-1.5 flex items-center gap-1.5">
              <span className={`h-1.5 w-1.5 rounded-full ${BAND[type].dot}`} />
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                {BAND[type].label}
              </h3>
              <span className="text-[11px] text-foreground-subtle">{band.length}</span>
            </div>
            <div className="flex flex-col gap-2">
              {band.map((r) => (
                <ItemRow key={`${r.agent_slug}-${r.ref_kind}-${r.ref_id}`} item={r} />
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 3: Verify `NeedsYouItem`'s real fields**

The component reads `type`, `title`, `subtitle`, `url`, `ref_kind`, `ref_id`. Confirm against the schema rather than trusting this plan:

```bash
cd frontend && grep -A 12 "NeedsYouItem: {" src/api/generated.ts | head -14
```

Fix any mismatch in Step 2.

- [ ] **Step 4: Wire it into the page**

In `frontend/src/pages/SupervisorPage.tsx`, extend the imports:

```tsx
import { listAgents, getFleetNeedsYou, type AgentOut, type FleetNeedsYouOut } from '@/api/agents'
import { listRunners, type RunnerOut } from '@/api/harness'
import { WaitingOnYou } from '@/components/supervisor/WaitingOnYou'
```

Add state:

```tsx
  const [fleet, setFleet] = useState<FleetNeedsYouOut | null>(null)
```

Replace the `Promise.all` block:

```tsx
    Promise.all([listAgents({ limit: 100 }), listRunners(), getFleetNeedsYou()])
      .then(([page, rs, f]) => {
        if (cancelled) return
        setAgents(page.items)
        setRunners(rs)
        setFleet(f)
      })
```

Update the loading guard:

```tsx
  const loading = agents === null || runners === null || fleet === null
```

Insert the inbox section **above** Runners — it is the reason the screen exists and must be the first thing a thumb reaches:

```tsx
      <section>
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Waiting on you {fleet && fleet.total_waiting > 0 ? `· ${fleet.total_waiting}` : ''}
        </h2>
        {loading ? <Skeleton className="h-24 w-full" /> : <WaitingOnYou fleet={fleet} />}
      </section>
```

Replace the stubbed `waiting={0}` with the real count:

```tsx
            {agents.map((a) => (
              <AgentKpiCard
                key={a.slug}
                agent={a}
                waiting={fleet.agents.find((b) => b.agent_slug === a.slug)?.waiting_count ?? 0}
              />
            ))}
```

- [ ] **Step 5: Build**

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 6: Verify against real data**

```bash
cd frontend && npm run dev
```

Open `/supervisor`. The waiting counts on the agent cards must match the badge in each agent's own rail at `/w/<ws>/agents/<slug>/needs-you` — same server aggregation, so any disagreement is a real bug in the fleet endpoint's scoping.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/supervisor/WaitingOnYou.tsx frontend/src/pages/SupervisorPage.tsx frontend/src/api/agents.ts
git commit -m "feat(frontend): cross-fleet 'waiting on you' on /supervisor

The reason the phone exists. NeedsYouSection is per-agent and rail-mounted;
this is the cross-fleet, phone-first equivalent, reading the single fleet
endpoint rather than fanning out N+1 like menubar.py does.

Flattens agent-grouped blocks into one ranked queue (review, question, notify)
— on a phone the queue matters more than the grouping. Read-only: rows link
out. Acting inline is Phase 3, with the composer.

Also replaces the stubbed waiting=0 on the agent cards with real counts."
```

---

## Task 8: Prove it works on a phone-sized screen

**Context:** `playwright.config.ts` defines **no mobile viewport** — nothing in this repo has ever tested a phone layout. Phase 2 makes this an installed app; a layout regression must fail CI before that, not after.

**Files:**
- Modify: `frontend/playwright.config.ts`
- Create: `frontend/e2e/supervisor.spec.ts`
- Test: `cd frontend && npx playwright test --project=mobile`

**Interfaces:**
- Consumes: the `/supervisor` route (Task 6) and its `data-testid`s: `supervisor-page`, `runner-status`, `waiting-on-you` / `waiting-empty`, `agent-card-<slug>`.
- Produces: a `mobile` Playwright project. Later phases add specs to it.

- [ ] **Step 1: Add the mobile project**

In `frontend/playwright.config.ts`, add the import:

```ts
import { defineConfig, devices } from '@playwright/test'
```

Add a `projects` array after `use`:

```ts
  // Nothing here has ever been tested at phone width. Phase 2 makes /supervisor
  // an installed PWA, so a layout regression has to fail CI before that lands.
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
```

`Pixel 7` (412×915) matches the Android target. `storageState` and `baseURL` stay in the top-level `use` and are inherited by both projects.

- [ ] **Step 2: Write the failing test**

Create `frontend/e2e/supervisor.spec.ts`:

```ts
import { test, expect } from '@playwright/test'

test.describe('/supervisor', () => {
  test('renders the fleet at phone width without horizontal scroll', async ({ page }) => {
    await page.goto('/supervisor')
    await expect(page.getByTestId('supervisor-page')).toBeVisible()
    await expect(page.getByTestId('runner-status').or(page.getByText('No runner paired'))).toBeVisible()
    await expect(page.getByTestId('waiting-on-you').or(page.getByTestId('waiting-empty'))).toBeVisible()

    // The body must never scroll sideways. Wide content scrolls in its OWN
    // container; a page-level overflow means a component broke the contract.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })

  test('waiting-on-you is above the fold', async ({ page }) => {
    await page.goto('/supervisor')
    const inbox = page.getByTestId('waiting-on-you').or(page.getByTestId('waiting-empty'))
    await expect(inbox).toBeInViewport()
  })
})
```

- [ ] **Step 3: Run it**

```bash
cd frontend && npx playwright test --project=mobile supervisor.spec.ts
```

Expected: PASS. The config boots the backend and dev server itself (`webServer`).

If the horizontal-scroll assertion fails, **fix the component, not the test** — find the offending element:

```ts
await page.evaluate(() => {
  const w = document.documentElement.clientWidth
  return [...document.querySelectorAll('*')]
    .filter((el) => el.getBoundingClientRect().right > w + 1)
    .map((el) => el.className)
})
```

The usual culprit is a bare `w-64` where the rail contract requires `md:w-64`.

- [ ] **Step 4: Confirm the desktop project still passes**

```bash
cd frontend && npx playwright test --project=desktop
```

Expected: PASS — adding `projects` must not change existing specs' behaviour.

- [ ] **Step 5: Commit**

```bash
git add frontend/playwright.config.ts frontend/e2e/supervisor.spec.ts
git commit -m "test(e2e): mobile viewport + /supervisor specs

playwright.config.ts had no mobile viewport — no phone layout has ever been
tested here. Adds a Pixel 7 project (matching the Android target) alongside
desktop, and specs asserting /supervisor renders at phone width with NO
page-level horizontal scroll and the inbox above the fold.

Phase 2 turns this route into an installed PWA; a layout regression should fail
CI before that, not after."
```

---

## Definition of Done

- [ ] `uv run pytest -q` passes.
- [ ] `cd frontend && npm run build` passes.
- [ ] `cd frontend && npx playwright test` passes both projects.
- [ ] A non-member PAT gets **404** (never 403) from every `/api/harness` endpoint.
- [ ] A PAT whose user is not `runner.paired_by` cannot heartbeat, claim, or read that runner.
- [ ] Agents with `workspace=None` still work end to end (the migration-safety path).
- [ ] `frontend/src/api/agents.ts` declares **no response entity shapes** of its own — every one aliases `components['schemas']`. `Page<T>` and `ListAgentsParams` remain hand-declared and that is correct: openapi-typescript emits concrete `Page_AgentOut_`-style aliases rather than a generic, and `ListAgentsParams` is a request shape.
- [ ] Every exported name and return type in `agents.ts` is unchanged from before the migration (`git show HEAD:src/api/agents.ts | grep -E "^export"`), so no caller needed editing.
- [ ] `/supervisor` renders at 412px with no page-level horizontal scroll.
- [ ] Agent-card waiting counts match each agent's own rail badge.

## What this plan does NOT do

Named so nobody builds them early:

- **No PWA.** No manifest, service worker, install prompt, push, or badge. Phase 2.
- **No pause/resume, no `is_active`, no `/activate`.** Phase 4 — and it carries the resume-while-paused fix (the runner must stop discarding its heartbeat response, and the menubar's pause must POST desired-state instead of writing `~/.canopy/PAUSED`).
- **No composer, no `launchable`/`args_hint`, no repo targets, no session input.** Phase 3.
- **No menubar change.** `menubar.py` keeps rendering its own HTML until Phase 5, deliberately: it is a daily tool and is not replaced until Phases 1–4 give the replacement parity.
- **No emdash mirror.** Deferred; and when built it reads `emdash4.db`, not the DOM (spec §Deferred).
- **`/supervisor` is read-only.** Every row links out. This is a conscious Phase 1 boundary.
