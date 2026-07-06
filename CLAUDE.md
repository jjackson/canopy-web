# Canopy Web

Collaborative web workspace for the canopy agent ecosystem — portfolio insights,
first-class AI agents, demo-driven development (DDD), walkthroughs, and shareouts.

## Architecture

- **Backend:** Django 5 ASGI + uvicorn, Django Ninja 1.x + Pydantic v2, PostgreSQL.
  OpenAPI 3.1 schema auto-generated at `/api/openapi.json`; Scalar UI at
  `/api/docs/`; Redoc at `/api/redoc/`. All errors return RFC 7807
  `application/problem+json`. Frontend TypeScript types are generated from the
  schema (`frontend/src/api/generated.ts`) and consumed via `openapi-fetch`.
- **Frontend:** React 19 + Vite + Tailwind CSS 4 + shadcn/ui
- **AI:** Anthropic Claude API via SSE streaming. Dual backend — direct API key (`AI_BACKEND=api`) or Claude Code CLI subscription (`AI_BACKEND=cli`), switchable at runtime via `/api/ai/switch/`.
- **MCP server:** `apps/mcp/` is a FastMCP 3.x Streamable-HTTP server mounted into the ASGI app at `/api/mcp/` (wired in `config/asgi.py`). Tools run **as the authenticated user** via per-user PAT (`CanopyPATVerifier`) and reuse the same service functions as the REST views, so the two surfaces can't drift. See `docs/architecture/mcp-surface.md`.
- **Deployment:** AWS ECS Fargate on the shared labs platform (account `858923557655`, `us-east-1`), served at `https://labs.connect.dimagi.com/canopy/` behind the shared ALB. One container (Django serves the built SPA + API + MCP). Deploys run from GitHub via the **Deploy to Labs (AWS)** workflow (`.github/workflows/deploy-labs.yml`): build → push to ECR (`labs-jj-canopy-web`) → register task-def revision → optional migrate → roll the ECS service. Infra is provisioned by `deploy/aws/canopy-web.cfn.yaml` (CloudFormation). Runtime settings in `config/settings/connectlabs.py` (extends `production.py`; `FORCE_SCRIPT_NAME=/canopy`, shared RDS `canopy_web` DB).
- **Framework/product boundary (the one invariant):** apps split into **framework** (generic, agent-agnostic substrate — `agents`, `agent_runs`, `workspaces`, `api`, `common`, `timeline`, `tokens`, `session_sharing`, `issues`, `mcp`, `system`) and **product** (canopy's own features — `projects`, `walkthroughs`, `reviews`, `shareouts`, `runs`). **Framework code must never import product code; product freely imports framework.** This keeps the blend cuttable (the framework apps could lift onto a standalone host without dragging canopy's product). It's a *direction, not a wall* — we don't move apps into `framework/`/`product/` folders. Enforced by `tests/test_architecture_boundary.py` (fails CI on a framework→product import, or on a new app left untiered). Full rationale, the per-app tier table, and the accepted carve-outs (the `api` composition root, the `mcp` insights tool): **`ARCHITECTURE.md`**. The framework apps are being harvested as the generic layer out of ACE — see `docs/superpowers/specs/2026-06-24-canopy-framework-harvest-design.md`.

## Development

Backend uses [`uv`](https://docs.astral.sh/uv/) for dependency management (uv.lock is committed). Install uv first if you don't have it: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

```bash
# Backend
cp .env.example .env  # Set AI_BACKEND=api + ANTHROPIC_API_KEY, or AI_BACKEND=cli
uv sync --extra dev
uv run python manage.py migrate
uv run python manage.py seed_projects   # optional: seed the initial 13 portfolio projects
uv run python manage.py runserver

# Frontend
cd frontend && npm install && npm run dev

# Both (via honcho)
uv run honcho start -f Procfile.dev

# Docker (backend + frontend + Postgres)
docker compose up

# Deploy to AWS labs (https://labs.connect.dimagi.com/canopy/). Deploys run from
# GitHub only — trigger the "Deploy to Labs (AWS)" workflow from the Actions tab
# (workflow_dispatch), or:
gh workflow run "Deploy to Labs (AWS)" --ref main -f run_migrations=false
gh workflow run "Deploy to Labs (AWS)" --ref main -f run_migrations=true   # when the change has a migration
# Production ships from `main` ONLY — the workflow hard-fails on any other ref.
# It builds+pushes the image to ECR, registers a task-def revision (image swap
# only), optionally migrates on a one-off Fargate task, then rolls the ECS
# service. See .github/workflows/deploy-labs.yml + deploy/aws/canopy-web.cfn.yaml.
```

When `AI_BACKEND=cli`, the `claude` binary must be on PATH and authenticated. In Docker, use the headless auth flow at `/settings` (drives `claude setup-token` via PTY; token persists in `CLAUDE_CODE_OAUTH_TOKEN`).

## Testing

```bash
uv run pytest                                    # All backend tests
uv run pytest tests/test_agents.py -v            # Specific
cd frontend && npm run build                     # Frontend type check + build
cd frontend && npm run gen:api                   # Regenerate TypeScript types from OpenAPI schema
```

CI (`.github/workflows/ci.yml`) runs both on every PR and on push to main. Deploy is a separate manual job in the same workflow — trigger it from the Actions tab via "Run workflow"; the deploy step waits for the test jobs to pass before shipping. Walkthrough QA spec at `docs/walkthroughs/project-workbench.yaml` (run via `/walkthrough project-workbench`).

## Key URLs

The app is **workspace-tenant-scoped** (PR #183). Every surface that owns tenant
data lives under `/w/:workspace/`; personal/global surfaces and public viewers
stay at root. A header workspace switcher appears when you belong to >1 workspace.
Bare `/` redirects to the active workspace's workbench, and the legacy flat paths
(`/timeline`, `/shareouts`, `/walkthroughs`, `/agents/*`, `/ddd/*`) redirect into
the active workspace. `/ddd-plans` and `/reviews` now redirect to `/`.

**Tenant-scoped (under `/w/:workspace/`):**
- `/w/:workspace` — Project workbench. Tile grid dashboard with a "Today's top 3" insight hero, freshness chip, inline insights triage, and self-prioritizing tile order by insight count.
- `/w/:workspace/timeline` — Team activity timeline (cross-app activity feed; link-out only)
- `/w/:workspace/shareouts` (+ `/shareouts/:period`) — Dated, teammate-facing work briefings (what shipped, why, how to leverage) posted by `/canopy:shareout`; `:period` is a copy-linkable permalink to one briefing
- `/w/:workspace/walkthroughs` — Sharable demos uploaded from `/canopy:walkthrough`
- `/w/:workspace/ddd` (+ `/ddd/:narrative`, `/ddd/:narrative/:runId`) — Demo-driven-development (DDD) views: narrative → version → run → package (video + deck + narrative + links)
- `/w/:workspace/agents` — First-class AI agents list (e.g. "Echo")
- `/w/:workspace/agents/:slug` — Agent workspace: a full-bleed rail + scrolling main built on `canopy-ui`. Sub-routes (rail): **Needs you** (the default landing — a typed/ranked supervisor inbox), Overview, Tasks (the "who has the ball" board), Turns (packaged units of work + optional transcript), Syncs, Work products, Skills

**Root / personal / global:**
- `/system` — Capability catalog + Workflows view (how canopy's plugin capabilities compose; read live from the canopy plugin)
- `/insights` — Cross-portfolio AI insights feed (user-scoped; deliberately not tenant-scoped)
- `/sessions` — My shared Claude Code sessions (transcripts uploaded via `/canopy:share-session`)
- `/settings` — AI backend status, switch backends, headless Claude CLI auth, theme toggle, and debug-session minting (consolidated under the user menu)
- `/walkthrough/:id` — Single walkthrough viewer (HTML iframe or video player). Reclaimed from `/w/:id` when `/w/` became the tenant prefix; a legacy `/w/<uuid>/content` link 302-redirects here
- `/review/:id` — Editable narrative review surface for DDD (approve / redraft a story before build); public (link-visibility) reviews are readable by anyone with the URL, but submitting a decision requires a Dimagi login
- `/share/:token` — Public, chrome-less read-only viewer for a shared session (no login; mounted outside the app shell)
- `/api/` — REST API
- `/admin/` — Django admin
- `/health/` — Health check

## API Endpoints

All endpoints are served by Django Ninja (Pydantic v2 typed) under `/api/`. Errors use RFC 7807 `application/problem+json`. The machine-readable schema lives at `/api/openapi.json`; browse at `/api/docs/` (Scalar) or `/api/redoc/`.

**Tenant routing:** the canonical tenant URL is `/api/w/{ws}/…`. `apps/api/tenancy.py::WorkspaceResolveMiddleware` gates membership (non-member → 404), pins `request.workspace_slug`, then strips the prefix and reroutes to the flat mount — so the OpenAPI schema stays single/clean (no double-mount, no colliding operation IDs). The flat `/api/…` routes below remain a **non-breaking compat shim**: `workspace_slug` resolves to the caller's default workspace, keeping the PAT/plugin fleet (e.g. Echo, the canopy plugin) working unchanged. Handlers read `getattr(request, "workspace_slug", None)` — truthy pins the workspace, `None` applies the handler's default.

### Auth + session (root)
- `GET /api/me/` — Current authenticated user
- `GET /api/csrf/` — CSRF token bootstrap
- `GET|POST /auth/cli/authorize/` — gh-style loopback flow: an authenticated browser mints a `PersonalToken` and 302-redirects it to a local CLI callback (validates the callback is a safe loopback target). Pairs with `/canopy:canopy-web-pat-mint`. Bare Django view (`apps/tokens/cli_authorize_views.py`).

### Projects
- `GET /api/projects/` — List projects with latest context
- `POST /api/projects/` — Create project
- `GET /api/projects/slugs/` — Lightweight slug list
- `GET /api/projects/{slug}/` — Project detail with full context
- `PATCH /api/projects/{slug}/` — Update project
- `DELETE /api/projects/{slug}/` — Delete project
- `POST /api/projects/{slug}/context/` — Push context entry
- `GET /api/projects/{slug}/context/` — List context entries
- `GET /api/projects/{slug}/context/latest/` — Latest context per type
- `POST /api/projects/seed/` — Bulk seed projects
- `POST /api/projects/batch-context/` — Create context entries across many projects in one request (body: `{updates: {slug: [...]}}`)
- `POST /api/projects/batch-actions/` — Record actions across many projects in one request (body: `{updates: {slug: [...]}}`)
- `POST /api/projects/{slug}/actions/` — Record a skill action
- `GET /api/projects/{slug}/actions/` — List actions (filter: ?skill=name)
- `GET /api/projects/{slug}/actions/summary/` — Latest action per skill

### Insights
- `GET /api/insights/` — List all insights across projects. Filters: `?category=<slug>` (matches `[<slug>]` content prefix), `?source=<producer>` (filters by writer), `?project=<slug>`. Bearer-readable for machine producers (e.g. `canopy:portfolio-review`) so they can dedupe before re-publishing.
- `DELETE /api/insights/{id}/` — Dismiss an insight (OAuth only — bearer is GET-only here).
- `POST /api/insights/clear/` — Clear insights (regeneration helper).

### Workspaces (`apps/workspaces`) — multi-tenancy
The tenant that owns agents + runs. `Workspace` + members (owner / editor / viewer) + email invites (ported from ace-web, domain-agnostic). Replaced the retired `apps/workspace` (singular) co-authoring session app — that whole SSE skill-authoring engine and its `/api/workspace/*` routes are gone.
- `POST /api/workspaces/` — Create a workspace
- `GET /api/workspaces/` — List my workspaces
- `GET /api/workspaces/{slug}/` — Get a workspace (member-only)
- `GET /api/workspaces/{slug}/members/` — List members (member-only)
- `DELETE /api/workspaces/{slug}/members/{user_id}/` — Remove a member (owner-only)
- `POST /api/workspaces/{slug}/invites/` — Invite by email (owner-only)
- `GET /api/workspaces/{slug}/invites/` — List invites (member-only)
- `POST /api/workspaces/{slug}/invites/{invite_id}/revoke` — Revoke an invite (owner-only)
- `POST /api/workspaces/invites/{token}/accept` — Accept an invite

### Issues (`apps/issues`)
A `canopy.origin` record store — GitHub issue provenance / evidence capture (the issues ACE files as it runs).
- `POST /api/issues/` — Upsert an origin record
- `GET /api/issues/` — List origin records (paginated)
- `GET /api/issues/{repo_slug}/{number}/` — Get an origin record
- `DELETE /api/issues/{repo_slug}/{number}/` — Delete an origin record (cleanup)

### AI backend (`apps/common`)
- `GET /api/ai/status/` — Current backend + auth state
- `POST /api/ai/switch/` — Switch between `api` and `cli` at runtime
- `POST /api/ai/auth/start/` — Begin headless Claude CLI login
- `POST /api/ai/auth/complete/` — Submit OAuth code
- `GET /api/ai/auth/poll/` — Poll auth status

### Personal Access Tokens (`apps/tokens`)
- `GET /api/tokens/` — list my tokens (no raw values)
- `POST /api/tokens/` — mint a token (raw returned once)
- `DELETE /api/tokens/{id}/` — revoke a token (owner-only; 404 hides other users' tokens)

Tokens are long-lived bearer credentials per Django user. The raw value is sha256-hashed at creation and never persisted. Pass `Authorization: Bearer <raw>` on any request; `apps.tokens.middleware.BearerTokenAuthMiddleware` resolves it to `request.user`. Replaces the retired `WORKBENCH_WRITE_TOKEN` shared-secret + `/api/auth/e2e-login/` flow.

Bootstrap a token via the management command:

```bash
uv run python manage.py create_token --email ace@dimagi-ai.com --label "canopy plugin" --create-user
```

### Walkthroughs
- `GET /api/walkthroughs/` — List. Filters: `?project=<slug>`, `?kind=html|video`, `?mine=true`
- `POST /api/walkthroughs/` — Upload (multipart). Fields: `file`, `title`, `kind` (html|video), optional `description`, `project_slug`, `visibility` (`private` | `link`; `link` = public/tokenless)
- `GET /api/walkthroughs/<uuid>/` — Detail. `auth=None`: public (`visibility=link`) walkthroughs are readable by anyone with the URL; private ones 404 to anonymous (no existence leak). `is_owner` flag tells the UI which toolbar to render
- `PATCH /api/walkthroughs/<uuid>/` — Owner-only update of title/description/project_slug/visibility
- `DELETE /api/walkthroughs/<uuid>/` — Owner-only. Deletes Drive file and the row
- `GET /walkthrough/<uuid>/content` — Streams file bytes. Session-auth OR `visibility=link` (tokenless — anyone with the URL; the UUID is the only secret). Range-aware (supports `<video>` scrubbing). Reclaimed from `/w/<uuid>/content` when `/w/` became the tenant prefix; the legacy `/w/<uuid>/content` path 302-redirects here (`RedirectView`, query string preserved)

Visibility is **tokenless**: `link` means "anyone with the link". The `share_token` column + model methods are retained but dormant (no rotate endpoint, never minted/returned) so the model is reversible.

Settings:
- `WALKTHROUGHS_ENABLED` (default `True`) — `/api/walkthroughs/` and `/w/<id>/content` 404 when off
- `CANOPY_DRIVE_SA_KEY_JSON` — Google Drive service-account key (JSON string). Empty disables uploads/streams (500 with `code=drive-not-configured`)
- `CANOPY_DRIVE_ROOT_FOLDER_ID` — Shared-drive folder ID. `walkthroughs/<uuid>/` subfolders are created under it
- `WALKTHROUGH_MAX_UPLOAD_BYTES` (default 75 MB)

### Debug access (`apps/common/views_debug`)
- `POST /api/debug/mint-session/` — authenticated user mints a short-lived Django session cookie (body: `{ttl_seconds: int}`, clamped to 60s–1w). Returns cookie + curl example. Used to hand access to an AI assistant without going through OAuth. UI lives at `/settings` → "Debug access".

### Reviews (`apps/reviews`) — DDD narrative review surface
- `GET /api/reviews/` — List review requests (the `/ddd` dashboard)
- `POST /api/reviews/` — Create a review request (DDD orchestrator)
- `GET /api/reviews/{rid}/` — Get review detail or poll for resolution
- `POST /api/reviews/{rid}/submit/` — Submit approve/redraft decisions + narration edits (human → server)
- `DELETE /api/reviews/{rid}/` — Delete a review request (dashboard cleanup)

Reviews are tokenless. `visibility=link` reviews are readable by anyone with the URL — the auth middleware lets anonymous holders through the `/review/:id` shell + the per-review read API (which self-enforce). **Submitting** a decision always requires a Dimagi login (public-readable never grants anonymous write).

### DDD runs (`apps/runs`, mounted at `/api/ddd`)
- `GET /api/ddd/narratives/` — List DDD narratives
- `GET /api/ddd/narratives/{slug}/` — Get a narrative + its runs (grouped by version)
- `GET /api/ddd/runs/{run_id}/` — Get a run package (video + deck + narrative + links)
- `PATCH /api/ddd/narratives/{slug}/visibility/` — Set Public/Private for an entire narrative; cascades visibility to every walkthrough + review under the slug (auth required). The narrative detail response carries a computed `visibility` (`public` / `private` / `mixed`)
- `DELETE /api/ddd/runs/{run_id}/` — Delete a run (cascades its walkthroughs + reviews)
- `DELETE /api/ddd/narratives/{slug}/versions/{version}/` — Delete a narrative version (and its runs)
- `DELETE /api/ddd/narratives/{slug}/` — Delete an entire narrative (all versions + runs)

The narrative is identified by `narrative_slug` (decoupled from `run_id`); a server backstop rejects narrative-less package artifacts.

### Shareouts (`apps/shareouts`)
- `GET /api/shareouts/` — List shareouts (teammate-facing work briefings, timestamped per window)
- `POST /api/shareouts/` — Create shareouts (batch; idempotent per `period`+`source`)
- `POST /api/shareouts/clear/` — Clear shareouts by source / project / date (AND-combined)

### Agents (`apps/agents`) — first-class AI-agent workspace
An `Agent` (e.g. "Echo") is a first-class entity — distinct from a code Project — with its own Google-Doc syncs, work products, skill catalog, packaged turns, and an actionable task board. The **DB is the source of truth**; the board renders by "who has the ball" (the agent vs a human). A human's board action POSTs a *command*; the agent drains pending commands on its next turn and marks them applied (`result_note` + `applied_at`). All routes are session-authed and `x-mcp-expose`d.
- `GET /api/agents/` — List agents
- `POST /api/agents/` — Create or update an agent (upsert by slug)
- `GET /api/agents/{slug}/` — Agent detail (with counts, incl. `turn_count` + `latest_turn_at`)
- `GET /api/agents/{slug}/needs-you` — Typed/ranked supervisor inbox (`review` → `question` → `notify`) + a `waiting_count` badge — "what does the agent need from me right now?"
- `GET|POST /api/agents/{slug}/turns/` — List / package an `AgentTurn`: the request(s) a turn advanced (`task_ext_ids`) → what it did (`title`/`summary`) → deliverables (`work_product_urls`) → optionally a `/share/<token>` transcript link (uploaded to the sessions app; the turn only holds its `slug`/`share_token`, so the apps stay decoupled). Idempotent per `(agent, cli_session_id)`. Drives the **Turns** rail section
- `GET|POST /api/agents/{slug}/syncs/` — List / post a Google-Doc manager sync (idempotent per period+source)
- `GET|POST /api/agents/{slug}/work-products/` — List / upsert work products (by url)
- `GET|PUT /api/agents/{slug}/skills/` — List / replace (PUT) the skill catalog so it mirrors the repo
- `GET /api/agents/{slug}/tasks/` — List the board
- `POST /api/agents/{slug}/tasks/sync` — Upsert tasks from the (legacy) source sheet (non-destructive)
- `POST /api/agents/{slug}/tasks/` — Create a task
- `PATCH /api/agents/{slug}/tasks/{task_id}/` — Update a task
- `POST /api/agents/{slug}/tasks/{task_id}/commands` — Post a board action (`accept`/`decline`/`dispatch`/`reassign`/`edit`/`comment`/`done`); some apply immediately server-side, `accept`/`dispatch` also queue agent work
- `GET /api/agents/{slug}/commands` — List commands (the agent reads `?status=pending`; each carries `result_note` + `applied_at`)
- `POST /api/agents/{slug}/commands/{cmd_id}/apply` — Mark a command applied (the agent calls this after acting)

### Agent runs (`apps/agent_runs`, mounted under `/api/agents`)
The unified agent **run lifecycle** (run → step → artifact → verdict/QA → decision → gate → fork) as a storage-agnostic read model behind a `RunStore` Protocol (DB adapter persists rows; Drive adapter reads ACE's YAML). The keystone of the framework harvest — see `docs/superpowers/specs/2026-06-29-unified-agent-run-lifecycle-design.md`. Backed by the installable Django-free `canopy_runs` library.
- `GET /api/agents/{slug}/runs/` — List an agent's runs (paginated)
- `POST /api/agents/{slug}/runs/` — Create a run
- `GET /api/agents/{slug}/runs/{run_id}/` — Full run read model
- `GET /api/agents/{slug}/runs/{run_id}/steps/` — A run's steps
- `POST /api/agents/{slug}/runs/{run_id}/steps/{step_key}/gate` — Record a gate decision on a step
- `POST /api/agents/{slug}/runs/{run_id}/steps/{step_key}/verdict` — Record a step verdict (QA/eval aggregate)
- `POST /api/agents/{slug}/runs/{run_id}/fork` — Fork a run at a step boundary

### Sessions (`apps/session_sharing`) — shared Claude Code transcripts
Token-based session sharing (the `/canopy:share-session` flow); the app was renamed from `sessions` to `session_sharing` to free the `sessions` name for the live-session harness. Routers still mount at `/api/sessions` + `/api/share`. This is a **separate** token model from the tokenless walkthrough/review visibility above — shared sessions (and arcs) carry a rotatable `share_token`.
- `POST /api/sessions/upload` — Upload a Claude `.jsonl` transcript (multipart)
- `GET /api/sessions/` — List my shared sessions
- `GET /api/sessions/{slug}` — Get one session (owner)
- `PATCH /api/sessions/{slug}` — Update a session (owner)
- `DELETE /api/sessions/{slug}` — Delete a session (owner)
- `POST /api/sessions/{slug}/rotate-token` — Rotate the share token (owner) — invalidates the old `/share/<token>` link

**Arcs** — a multi-session "arc" groups several transcripts into one shareable build (the `/share` for a whole build):
- `POST /api/sessions/arcs` — Create an arc
- `GET /api/sessions/arcs` — List my arcs (filter: `?project=<slug>`)
- `GET /api/sessions/arcs/{slug}` — Get one arc (owner)
- `PATCH /api/sessions/arcs/{slug}` — Update an arc (owner)
- `DELETE /api/sessions/arcs/{slug}` — Delete an arc (owner)
- `POST /api/sessions/arcs/{slug}/rotate-token` — Rotate an arc's share token (owner)

- `GET /api/share/{token}` — Public read-only view of a shared session (no login; `share_router` mounted at `/api/share`, drives `/share/:token`)

### Timeline (`apps/timeline`)
- `GET /api/timeline/` — Team activity timeline. Generic activity-log aggregation that reads other apps' events via a string registry (cursor-paginated; link-out only). See `docs/superpowers/specs/2026-06-19-team-activity-timeline-design.md`.

### System (`apps/system`)
- `GET /api/system/overview` — Capability catalog: the canopy plugin's skills/agents/commands, read live from the plugin.
- `GET /api/system/{kind}/{name}` — Capability detail for one skill/agent/command. Drives the `/system` Workflows view.

### MCP (`apps/mcp`, mounted at `/api/mcp/`)
Not a Ninja router — a FastMCP 3.x Streamable-HTTP ASGI app mounted in `config/asgi.py`. Auth is enforced inside the server via `MultiAuth` (per-user PAT `CanopyPATVerifier`, always on; interactive Google OAuth is an env-gated seam, `MCP_OAUTH_ENABLED`). Every tool call writes an `MCPAuditLog` row; mutating tools are rate-limited per user. Tools today: `list_insights` (read) + `clear_insights` (write). The legacy single-shared `CANOPY_MCP_BEARER` and the hand-rolled ASGI gate are gone. See `docs/architecture/mcp-surface.md`.

## Design Decisions

- **API is Pydantic-first via Django Ninja**: every request/response is a Pydantic v2 model declared in `apps/<app>/schemas.py`. Routes live in `apps/<app>/api.py`, registered on the single `NinjaAPI` instance in `apps/api/api.py`. Errors are RFC 7807 `application/problem+json`. Frontend types are generated from the OpenAPI 3.1 schema by `openapi-typescript` into `frontend/src/api/generated.ts` and consumed via `openapi-fetch`. The `regen-openapi.yml` GitHub workflow auto-commits regenerated types on PRs touching `apps/**/api.py` or `apps/**/schemas.py`.
- **Streaming endpoints stay on Django**: `GET /walkthrough/<uuid>/content` (the walkthrough viewer) is a bare Django view at `apps/walkthroughs/streaming.py` — HTTP Range support (for `<video>` scrubbing) doesn't fit the Ninja contract. It is the only `StreamingHttpResponse` left now that the co-authoring workspace SSE engine has been retired. (Reclaimed from `/w/<uuid>/content` by the tenancy migration; the legacy path 302-redirects.)
- **Bare Django views**: `/api/csrf/`, `/api/debug/mint-session/`, `/auth/cli/authorize/`, and `/health/` (the last is also Ninja-mountable via `public_router`) — they manipulate sessions/cookies/redirects directly. Matched in `config/urls.py` BEFORE the Ninja `/api/` catch-all so they don't get shadowed.
- **MCP is in-process FastMCP, not OpenAPI-derived**: `apps/mcp/` mounts a FastMCP 3.x Streamable-HTTP server at `/api/mcp/` whose tools are explicit Python functions calling the same service layer as the REST views (no HTTP self-loopback). Auth is per-user PAT inside the server (fail-closed), every call is audited, and writes are rate-limited.
- **Visibility is tokenless Public/Private:** `visibility=link` means "anyone with the URL" (the UUID is the only secret) for walkthroughs + reviews; `private` is Dimagi-OAuth-gated and 404s to anonymous. Walkthrough content/detail and review *read* are public when `link`; review *submit* and all mutations require auth. The login middleware (`apps/common/middleware.py`, default-deny with an allowlist) allowlists the `/walkthrough/` viewer shell + `/walkthrough/<uuid>/content` stream + walkthrough detail GET + the legacy `/w/<uuid>/content` redirect (alongside the `/review/` + `/share/` allowlists). Note `/w/` itself now means the **authed** workspace tenant shell and is NOT public. The narrative-level toggle (`PATCH /api/ddd/narratives/{slug}/visibility/`) cascades to every artifact + review under a narrative; the dormant `share_token` column is retained for reversibility. See `docs/superpowers/specs/2026-06-08-tokenless-narrative-visibility-design.md`.
- **Shared frontend kit (`canopy-ui`):** the DDD and Agent workspaces share a two-pane (left rail + scrolling main) shell plus the broader design-system primitives, all extracted to `frontend/packages/canopy-ui` (imported as `canopy-ui` / `canopy-ui/ui` / `canopy-ui/lib`; published to public npm as `canopy-ui`, also mirrored as `@marshellis/canopy-ui`). Started life as `@canopy/workbench` (just the Workbench shell) and was expanded + renamed in 0.2.0→0.3.0. Surfaces consume it instead of re-implementing chrome, and use semantic design tokens (`bg-card` / `border-border` / `text-foreground` / `text-muted-foreground` / `text-primary`) — not raw `stone-*`/`orange-*` palette literals. See `docs/superpowers/specs/2026-06-17-shared-workbench-package-design.md`.
- **Light + dark themes via one token set.** The app ships **both** themes off the same semantic tokens in `frontend/src/index.css`: `:root` = Warm Earth **light**, `.dark` = Warm Earth **dark** (the default). `index.html` applies `.dark` before first paint (default dark; an explicit `light` choice in `localStorage` removes it — no flash), and `src/theme/ThemeProvider.tsx` (`useTheme` / `<ThemeToggle/>`, mounted in the `AppLayout` header) toggles + persists the class on `<html>`. Because components only reference token names (never `dark:` variants), both themes "just work." The light palette deepens brand/status hues (~600) for contrast on white.
- **Design tokens are the single source of truth (no raw palette literals).** The whole authenticated app styles off the semantic tokens (`@theme inline` maps `--color-*` → the per-theme vars). Do **not** introduce raw Tailwind palette literals (`stone-*`, `orange-*`, `zinc-*`, `slate-*`, `red-*`, `amber-*`, `emerald-*`, `sky-*`, `violet-*`); use the tokens:
  - **Surfaces:** `bg-background` (page), `bg-card` (cards/popovers), `bg-muted` (fills/hover), `bg-input` (elevated controls). Borders: `border-border` (default), `border-input` (elevated/controls). Brand: `bg-primary` / `text-primary` / `border-primary` (+ `hover:bg-primary/90` for the button-hover darken).
  - **Text emphasis ladder** (brightest → dimmest): `text-foreground` (primary/headings) → `text-foreground-secondary` (secondary/body) → `text-muted-foreground` (meta/captions) → `text-foreground-subtle` (faint).
  - **Status / categorical accents:** `success` (emerald — opportunity), `warning` (amber — ship-gap), `info` (sky — alignment), `special` (violet — pattern), `destructive` (red — errors). Each has a `-foreground` for solid fills; tinted badges use `bg-<token>/10 text-<token> border-<token>/30`.
  - **Exception:** `/share/:token` (`SessionSharePage` + the `transcript/` components) is a deliberate **light-themed** public viewer mounted outside the app shell (`bg-white`); it intentionally uses neutral literals and is the one surface that does not consume the dark token set.
- APP UI: dense, readable, tables not cards
- SSE streaming for AI responses (Scout pattern)
- **Auth:** Google OAuth via django-allauth (allowed-domain restricted via `AUTH_ALLOWED_EMAIL_DOMAIN` — comma-separated list, default `dimagi.com`; `dimagi-associate.com` is also allowed). Personal Access Tokens (`apps/tokens/`) authenticate machine callers via `Authorization: Bearer <raw>` — `BearerTokenAuthMiddleware` resolves them upstream of `LoginRequiredMiddleware`. `/api/debug/mint-session/` lets an authenticated user mint a short-lived session cookie to hand to an AI assistant.
- **Multi-tenancy (Workspace is the tenant anchor):** `Workspace` (`apps/workspaces` — members owner/editor/viewer + email invites) anchors every surface that owns tenant data. `agents` + `agent_runs` carry a `workspace` FK, and the tenancy rollout (PR #183) added the same FK + backfill migration to the product roots `projects`, `walkthroughs`, `reviews`, and `shareouts`; their authenticated queries filter by `request.workspace_slug`. **Insights are deliberately excluded** (user-scoped, not tenant-scoped). Tenant surfaces live under `/w/:workspace/` (browser) and `/api/w/{ws}/` (API, via `WorkspaceResolveMiddleware`); a default workspace is assigned when unspecified and the flat `/api/…` routes stay as a compat shim, so the change was non-breaking / Echo-safe. Tokenless `visibility=link` public reads and review-submit-login are preserved through the scoping. See `docs/superpowers/specs/2026-06-30-workspace-multi-tenancy-design.md`.
- PostgreSQL on the shared labs RDS (`canopy_web` DB on `labs-jj-postgres`)
- Dual AI backend lets users run either against an API key or their own Claude Code subscription

## Reference Docs

Design **specs** (the "why" record) live in `docs/superpowers/specs/`. The executed **implementation plans** — point-in-time checklists that shipped as described — are archived under `docs/archive/plans/` (git-tracked, kept as historical record, not current-state); consult them only when you need the blow-by-blow of how something was built.

- `docs/architecture/mcp-surface.md` — MCP server surface: module layout, dual-auth model, audit + rate-limit, tool inventory
- `docs/superpowers/specs/2026-04-10-project-workbench-design.md` — Workbench design spec
- `docs/superpowers/specs/2026-04-14-google-oauth-auth-gate-design.md` — OAuth gate design spec
- `docs/superpowers/specs/2026-05-26-walkthrough-sharing-design.md` — Walkthrough sharing design spec
- `docs/superpowers/specs/2026-06-02-ddd-run-views-design.md` — DDD run views (narrative → run → package) design spec
- `docs/superpowers/specs/2026-06-03-ddd-narrative-run-versioning-design.md` — DDD narrative/version/run model design spec
- `docs/superpowers/specs/2026-06-08-tokenless-narrative-visibility-design.md` — Tokenless Public/Private + narrative-level visibility design spec (shipped, PR #105)
- `docs/superpowers/specs/2026-06-17-shared-workbench-package-design.md` — shared Workbench shell design (shipped as `@canopy/workbench`, since expanded + renamed to `canopy-ui`; PRs #123/#124)
- `docs/superpowers/specs/2026-06-19-team-activity-timeline-design.md` — `/timeline` team activity feed design (shipped, PR #138)
- `docs/superpowers/specs/2026-06-24-canopy-framework-harvest-design.md` — Canopy-as-the-framework harvest strategy (umbrella for Waves 0–4: the framework/product boundary + what moves out of ACE)
- `docs/superpowers/specs/2026-06-28-shared-agent-client-design.md` — Shared agent-client, the framework's first harvested piece
- `docs/superpowers/specs/2026-06-29-unified-agent-run-lifecycle-design.md` — Unified agent⊕run lifecycle (Wave 1 keystone; the `apps/agent_runs` + `canopy_runs` library, shipped PR #154)
- `docs/superpowers/specs/2026-06-29-wave2-3-harvest-execution.md` — Wave 2/3 execution spec (run-step verdicts + multi-tenant workspaces; shipped PRs #158–#162)
- `docs/superpowers/specs/2026-06-30-workspace-multi-tenancy-design.md` — Workspace-as-tenant full multi-tenancy design (anchor-roots-inherit-children, `/w/` reclaim, path-prefix API; shipped PR #183)
- `docs/designs/canopy-web-design.md` — Product design + glossary (open claw, skill, collection, eval suite, workspace session)
- `docs/designs/ceo-plan-conversation-to-agent.md` — CEO review, scope decisions, deferred work
- `docs/walkthroughs/project-workbench.yaml` — Project workbench walkthrough spec
- `docs/case-studies/workbench-self-improvement.md` — Self-improvement case study
- `docs/personas/jonathan.md` — Primary user persona
- `TODOS.md` — Deferred V2 work (proactive detection, prompt hardening, OAuth integrations, multi-tenant auth, cowork adapter)
