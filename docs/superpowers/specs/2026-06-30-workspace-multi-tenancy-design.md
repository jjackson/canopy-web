# Workspace-as-Tenant: Full Multi-Tenancy Design

**Status:** Design (approved in brainstorm 2026-06-30)
**Author:** Jonathan Jackson + Claude
**Scope:** Make `Workspace` the tenant anchor for every product surface that owns
data/state, reclaim `/w/` for workspaces, and move each scoped surface under a
`/w/:workspace/` URL. Decomposed into a foundation increment plus per-app rollouts.

---

## 1. Motivation

Multi-tenancy was ported from ace-web as *framework-tier scaffolding*: the
`apps/workspaces` app (`Workspace` + `WorkspaceMembership` owner/editor/viewer +
`WorkspaceInvite`) exists and is enforced, but only the **agents** surface is
actually scoped to a workspace. Everything else (projects, walkthroughs, DDD
narratives/runs/reviews, shareouts) is effectively single-tenant, and there is no
way in the product to see, pick, or switch a workspace. CLAUDE.md records this:
"The product surface is still effectively single-tenant."

This design makes **workspace the core of a tenant**: every object that has
data/state lives under a workspace, the workspace is the anchor in the URL, and a
second workspace becomes a real isolation boundary rather than a latent column.

## 2. Decisions (locked in brainstorm)

1. **Tenant data model — anchor roots, inherit children.** Root entities carry a
   `workspace` FK; child entities derive tenancy by traversing their parent.
   - Roots: `Project`, `Agent` (done), DDD `Narrative`, `Walkthrough`, `Shareout`.
   - Children (no column): `Review` and `Run` inherit via
     `narrative.workspace_id` (`.filter(narrative__workspace_id=ws)`).
   - A standalone (project-less) `Walkthrough` is itself a root and carries its own
     `workspace_id`; when it *has* a project, the project's workspace must match.
2. **Out of scope for this pass — user-scoped.** Shared **sessions/arcs**
   (`/sessions`, `/share/:token`) stay user-owned personal transcripts, and the
   **insights** feed (`/insights`) stays as-is (global/portfolio). Neither gets a
   `workspace` FK now. Revisit later if the portfolio feed should be per-tenant.
   **`/system` is app-global** too — it reads the canopy plugin's capability
   catalog live from the plugin, so it stays at root. `timeline`, by contrast,
   *is* per-tenant (only this workspace's activity).
3. **URL — `/w/:workspace/` is the tenant prefix.** Every surface that renders
   workspace-owned data lives under it. `/w/` is reclaimed from the public
   walkthrough viewer, which moves to the full word `/walkthrough/:id`.
4. **API — path-prefix parent router is canonical, flat routes demoted to a
   default-workspace compat shim.** `workspace` is pushed into the service layer;
   a `current_workspace()` helper is the single resolution point.
5. **Enforcement is real, not cosmetic.** Every scoped query filters by workspace;
   non-members 404; writes assert membership. Near-no-op while everyone auto-joins
   `dimagi`, but correct the day a second workspace exists.

## 3. Routing model

### 3.1 Tenant-prefixed (frontend)
```
/w/:ws                    → workbench (today's /)
/w/:ws/agents             → agents list        (also /w/:ws/agents/:slug)
/w/:ws/ddd                → DDD                 (/w/:ws/ddd/:narrative/:runId)
/w/:ws/walkthroughs       → walkthrough LIST
/w/:ws/shareouts          → shareouts           (/w/:ws/shareouts/:period)
/w/:ws/timeline           → activity feed (scoped to tenant)
```
`timeline` shows only the activity of *this* workspace's objects, so its
aggregation must filter by workspace — which depends on the underlying apps
carrying a `workspace` FK. Timeline scoping therefore lands *after* the per-app
FKs (Increments 1–4), not in the foundation.

### 3.2 Reclaiming `/w/`
```
/w/:id            (viewer)  → /walkthrough/:id
/w/:id/content    (stream)  → /walkthrough/:id/content
```
Backend: `apps/walkthroughs/streaming.py` view + `config/urls.py` route +
`LoginRequiredMiddleware` allowlist all move to `/walkthrough/`. `/w/` now means
"workspace" exclusively.

### 3.3 Public / tokenless — stay OUT of the tenant prefix
Addressed by their own secret, readable cross-tenant by link, mounted outside the
app shell. Objects still carry `workspace_id`, but the public read path bypasses
membership (same as today's tokenless model).
```
/walkthrough/:id     (public walkthrough viewer, visibility=link)
/share/:token        (shared session)
/review/:id          (public review read; submit still requires Dimagi login)
```

### 3.4 Personal / global — stay at root (not tenant-prefixed)
```
/sessions   /insights   /settings   /system
```
`/sessions` + `/insights` are **user/portfolio-scoped** (decision #2). `/system`
is **app-global**: it's the canopy plugin's capability catalog read live from the
plugin, not tenant data, so it is not workspace-prefixed. `/settings` is
per-user (AI backend, theme, debug).

### 3.5 Defaults & redirects
Bare `/` and any legacy unprefixed path (`/ddd`, `/agents`, `/shareouts`, …)
navigate to `/w/<last-used-or-default>/…`. `<default>` = the user's first
membership (today `dimagi`). Hitting `/w/:ws` you are not a member of → 404
(backend already enforces this for agents).

## 4. Backend design

### 4.1 Data model
Each root gains
`workspace = ForeignKey("workspaces.Workspace", on_delete=PROTECT, null=True, blank=True, related_name="<app>s")`,
backfilled to the default workspace, then flipped non-null — the exact pattern
`agents` used (`0006_agent_workspace` add-nullable → `0007_backfill_default_workspace`,
`on_delete=PROTECT` so a workspace with content can't be casually deleted).
Children (`Review`, `Run`) get **no** column.

Backfill reuses `workspaces.services.ensure_default_workspace()` → all existing
rows land in `dimagi`. `auto_join_workspaces` already makes every domain user a
member, so nothing disappears from view.

### 4.2 The `current_workspace()` resolver
Single resolution point for every non-browser caller (PAT plugin skills, MCP tools
when they eventually scope, the compat shim):
```
current_workspace(user, explicit: str | None = None) -> Workspace
    explicit slug (must be a member)      → that workspace
    else user's sole membership           → that workspace
    else (0 or 2+ memberships, no slug)   → error (ambiguous / none)
```
Today every user has exactly one membership, so the "sole membership" branch is
unambiguous through the whole transition.

### 4.3 API shape — parent router + compat shim
Canonical: scoped routers remount under a Ninja **parent router** at
`/api/w/{ws}` that resolves + membership-checks the workspace **once** (shared
dependency / router `auth`), then dispatches to child handlers:
```
/api/w/{ws}/projects/       /api/w/{ws}/walkthroughs/
/api/w/{ws}/ddd/…           /api/w/{ws}/shareouts/
/api/w/{ws}/agents/…        (migrate; already gated)
/api/w/{ws}/timeline/       (moves under parent once events carry workspace)
```
`/api/system/…` stays flat (app-global capability catalog — not tenant data).
`/api/sessions/…` and `/api/insights/…` also stay flat (user/portfolio-scoped).
Compat: the existing flat routes (`/api/projects/…`, `/api/shareouts/…`, …) stay
mounted as a **thin deprecated shim** that fills `workspace = current_workspace(user)`
(default) and calls the **same service**. So the agent/plugin fleet keeps working
and migrates route-by-route; no flag day.

The invariant lives below HTTP: **service functions in `apps/<app>/services.py`
gain an explicit `workspace` argument.** Both the parent router and the compat
shim funnel through them, so REST, MCP, and agents can't drift.

**Implementation note (Increment 0, as-built).** ninja forbids mounting one
`Router` instance twice, and double-mounting with `url_name_prefix` collides
operation IDs (the prefixed paths drop out of the schema). So the "parent router"
is realized as `apps.api.tenancy.WorkspaceResolveMiddleware`: scoped routers stay
mounted **flat once** (single clean OpenAPI schema), and the middleware gates
membership on `/api/w/{ws}/…`, pins `request.workspace_slug`, and **strips** the
`/w/{ws}` segment so the request reroutes to the flat mount. The middleware is
generic — it strips/pins for *any* `/api/w/{ws}/<app>/…`, so each per-app
increment only adds a `workspace` FK + query filtering, not routing plumbing.
Legacy flat `/api/<app>/…` calls fall through untouched (`workspace_slug` stays
`None` → handler default logic). The one concession vs. the original wording: the
schema documents the flat canonical paths; the `/api/w/{ws}/…` form is an
enforced routing alias (the frontend targets it; the schema type is the flat path).

### 4.4 Enforcement
- List/read: `.filter(workspace=ws)` (or `narrative__workspace=ws` for children).
- Detail/write: resolve object, assert `is_member(user, obj.workspace_id)`, else 404.
- Parent router does the membership gate once so child handlers can't forget it.

### 4.5 MCP surface — untouched this pass
The only in-process MCP tools are `list_insights` / `clear_insights`
(`apps/mcp/tools/insights.py`), and insights are user/global-scoped per decision
#2. MCP tools call services directly (no HTTP), so the path change doesn't affect
them. When insights eventually scope, they adopt `current_workspace()` via a
`workspace` tool arg.

## 5. Frontend design

- **`router.tsx`**: add a `/w/:workspace` parent route wrapping the scoped
  surfaces; public + personal routes stay top-level; rename the walkthrough viewer
  to `/walkthrough/:id`; add redirects from legacy unprefixed paths.
- **`WorkspaceProvider` / `useWorkspace()`** (mirrors `theme/ThemeProvider.tsx`):
  fetch `GET /api/workspaces/`, validate the `:workspace` segment against
  memberships, expose `{ workspaces, active }`. URL is the source of truth
  (localStorage only stores a "last used" hint for the bare-`/` redirect).
- **Header switcher** in `components/AppLayout/AppLayout.tsx` next to
  `ThemeToggle` — a dropdown that *navigates* (rewrites the `:workspace` segment);
  hidden when the user has a single membership.
- **API client** (`api/client.v2.ts` + `api/*.ts`): scoped calls take the active
  `ws` and build `/api/w/{ws}/…`; regen `frontend/src/api/generated.ts`
  (`npm run gen:api`).

## 6. Decomposition (each increment = one PR)

**Increment 0 — Foundation (no new migrations).**
- Reclaim `/w/`: rename walkthrough viewer + stream + login allowlist + redirects.
- Backend: `/api/w/{ws}` parent router + `current_workspace()` helper + flat-compat
  shim wiring.
- Frontend: `WorkspaceProvider` + `useWorkspace()` + header switcher + `/w/:ws`
  parent route.
- Migrate the **already-scoped agents surface** under `/w/:ws/agents` end-to-end to
  prove the pattern without any new migration.

**Increments 1–4 — per product app, one at a time.**
Projects → Walkthroughs → DDD (Narrative root; Review/Run inherit) → Shareouts.
Each: nullable `workspace` FK + backfill migration (mirror agents `0006`/`0007`),
`workspace` threaded into services, router mounted under the parent + compat shim,
frontend route moved under `/w/:ws`, real query filtering + membership gate, tests.

**Increment 4b — Timeline scoping.**
Filter the timeline aggregation to the active workspace and move it under
`/w/:ws/timeline` + `/api/w/{ws}/timeline`. Lands after 1–4 because it can only
scope events whose source apps already carry a `workspace` FK. (`/system` stays
app-global and is not touched.)

**Increment 5 — Hardening.**
Flip FKs non-null, add indexes/constraints, deprecate & remove the flat compat
routes and legacy redirects once the plugin fleet has migrated.

## 7. Testing

- **Backfill migrations**: existing rows land in `dimagi`; idempotent; reverse is
  a no-op (data stays), matching agents `0007`.
- **Membership gates**: per app, a non-member 404s on list/detail/write; a member
  sees only their workspace's rows.
- **Compat shim**: a flat-route call with no workspace resolves to the caller's
  default workspace and hits the same service as the prefixed route.
- **Architecture boundary** (`tests/test_architecture_boundary.py`): unchanged —
  `workspaces` is framework-tier; product apps importing it is an allowed
  product→framework direction.
- **Frontend**: `npm run build` (type check) after `gen:api`; switcher navigation;
  non-member redirect/404.

## 8. Risks & mitigations

- **Breaking the agent/plugin fleet** → the flat-route compat shim keeps every
  existing PAT call working (resolves `dimagi`); migrate skills route-by-route.
- **`/w/` rename breaking existing walkthrough links** → redirect `/w/:id` →
  `/walkthrough/:id` for a deprecation window.
- **Ambiguous `current_workspace()`** once users hold 2+ memberships → require an
  explicit workspace before that day (the frontend always supplies one via the URL;
  only headless PAT callers rely on the default, and they target one tenant).
- **Uneven ownership graph** → resolved by "anchor roots, inherit children";
  project-less walkthroughs are their own roots.

## 8.5 Implementation status (as-built, 2026-06-30)

Shipped on `emdash/tenant-9n48g` (all backend tests + frontend build green):
- **Foundation** — `current_workspace()`; `WorkspaceResolveMiddleware` (gate +
  prefix-strip); `/w/` reclaim → `/walkthrough/`; frontend `WorkspaceProvider`,
  switcher, and the full `/w/:workspace` route tree; central openapi-fetch rewrite
  of scoped calls to `/api/w/:ws/…`.
- **Tenant roots scoped** — `Agent`, `Project`, `Walkthrough`, `ReviewRequest`,
  `Shareout` each carry a `workspace` FK + backfill; children (`Review`/`Run` via
  narrative; `ProjectContext`/`ProjectAction` via project) inherit. DDD read-model
  (`apps/runs`) filters every base queryset by the caller's workspaces.
- **Preserved** — tokenless public reads (`visibility=link` walkthroughs/reviews),
  review-submit login rule, and the flat-route compat for the PAT/plugin fleet.

Known partials / deferred (consistent with how `agents` shipped):
- **Timeline** scopes only its DDD source today; a `_call_source` signature-opt-in
  seam lets the other product sources (walkthroughs/projects/shareouts/agents) scope
  in a follow-up **without** the framework-tier `timeline` app importing product
  models (architecture-boundary-safe).
- **Non-null FKs** left nullable + always-assigned (matches `agents`); `workspace_id`
  is indexed by Django's default FK index, so no hardening migration was needed.
- **Insights** + **sessions/arcs** remain user/global-scoped (decision #2).

## 9. Out of scope / deferred

- Per-tenant scoping of insights and shared sessions/arcs (decision #2).
- Subdomain-based tenancy (`tenant.canopy…`) — path-prefix only.
- Cross-tenant object moves / re-parenting.
- Removing the dormant walkthrough/review `share_token` columns.
