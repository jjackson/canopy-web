# Canopy Web

Collaborative web workspace for building reusable AI skills from conversations.

## Architecture

- **Backend:** Django 5 ASGI + uvicorn, Django Ninja 1.x + Pydantic v2, PostgreSQL.
  OpenAPI 3.1 schema auto-generated at `/api/openapi.json`; Scalar UI at
  `/api/docs/`; Redoc at `/api/redoc/`. All errors return RFC 7807
  `application/problem+json`. Frontend TypeScript types are generated from the
  schema (`frontend/src/api/generated.ts`) and consumed via `openapi-fetch`.
- **Frontend:** React 19 + Vite + Tailwind CSS 4 + shadcn/ui
- **AI:** Anthropic Claude API via SSE streaming. Dual backend — direct API key (`AI_BACKEND=api`) or Claude Code CLI subscription (`AI_BACKEND=cli`), switchable at runtime via `/api/ai/switch/`.
- **Runtime adapters:** `apps/skills/adapters/` produces skill artifacts for `web`, `claude_code`, and `open_claw` runtimes.
- **MCP server:** `apps/mcp/` is a FastMCP 3.x Streamable-HTTP server mounted into the ASGI app at `/api/mcp/` (wired in `config/asgi.py`). Tools run **as the authenticated user** via per-user PAT (`CanopyPATVerifier`) and reuse the same service functions as the REST views, so the two surfaces can't drift. See `docs/architecture/mcp-surface.md`.
- **Deployment:** GCP Cloud Run + Cloud SQL on the `canopy-494811` project. `./deploy.sh` builds via Cloud Build (`cloudbuild.yaml`) and `gcloud run deploy`s — no local Docker daemon required. Production settings in `config/settings/production.py`.

## Development

Backend uses [`uv`](https://docs.astral.sh/uv/) for dependency management (uv.lock is committed). Install uv first if you don't have it: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

```bash
# Backend
cp .env.example .env  # Set AI_BACKEND=api + ANTHROPIC_API_KEY, or AI_BACKEND=cli
uv sync --extra dev
uv run python manage.py migrate
uv run python manage.py seed_demo   # optional: 5 demo skills with eval history
uv run python manage.py runserver

# Frontend
cd frontend && npm install && npm run dev

# Both (via honcho)
uv run honcho start -f Procfile.dev

# Docker (backend + frontend + Postgres)
docker compose up

# Deploy to GCP Cloud Run. CI also has a manual deploy job — trigger it from
# the Actions tab ("CI / Deploy" → Run workflow).
# Production ships from `main` ONLY — merge your branch first. Both deploy
# paths enforce this: deploy.sh refuses unless on main + in sync with
# origin/main; the CI deploy job hard-fails unless dispatched from main.
./deploy.sh                  # Cloud Build → push → gcloud run deploy (must be on main)
SKIP_TESTS=1 ./deploy.sh     # bypass test gate (emergencies only)
ALLOW_NON_MAIN_DEPLOY=1 ./deploy.sh   # bypass the main-branch guard (emergencies only)
```

When `AI_BACKEND=cli`, the `claude` binary must be on PATH and authenticated. In Docker, use the headless auth flow at `/settings` (drives `claude setup-token` via PTY; token persists in `CLAUDE_CODE_OAUTH_TOKEN`).

## Testing

```bash
uv run pytest                                    # All backend tests
uv run pytest tests/test_workspace_engine.py -v  # Specific
cd frontend && npm run build                     # Frontend type check + build
cd frontend && npm run gen:api                   # Regenerate TypeScript types from OpenAPI schema
```

CI (`.github/workflows/ci.yml`) runs both on every PR and on push to main. Deploy is a separate manual job in the same workflow — trigger it from the Actions tab via "Run workflow"; the deploy step waits for the test jobs to pass before shipping. Walkthrough QA spec at `docs/walkthroughs/canopy-web-demo.yaml` (run via `/walkthrough canopy-web-demo`).

## Key URLs

- `/` — Project workbench. Tile grid dashboard with a "Today's top 3" insight hero, freshness chip, inline insights triage, and self-prioritizing tile order by insight count.
- `/skills` — Skill discovery feed
- `/workspaces` — Workspace session list (resume in-progress sessions)
- `/new` — New collection / source ingestion flow
- `/workspace/:sessionId` — Co-authoring workspace
- `/skills/:skillId` — Skill detail + eval history
- `/guide` — Interactive walkthrough using a "Discovery Call Debrief" sample collection (try-it / how-it-works / review / eval / deploy sections)
- `/insights` — Cross-portfolio AI insights feed
- `/shareouts` (+ `/shareouts/:period`) — Dated, teammate-facing work briefings (what shipped, why, how to leverage) posted by `/canopy:shareout`; `:period` is a copy-linkable permalink to one briefing
- `/walkthroughs` — Sharable demos uploaded from `/canopy:walkthrough`
- `/w/:id` — Single walkthrough viewer (HTML iframe or video player)
- `/ddd` (+ `/ddd/:narrative`, `/ddd/:narrative/:runId`) — Demo-driven-development (DDD) views: narrative → version → run → package (video + deck + narrative + links). `/ddd-plans` and `/reviews` redirect here
- `/review/:id` — Editable narrative review surface for DDD (approve / redraft a story before build); public (link-visibility) reviews are readable by anyone with the URL, but submitting a decision requires a Dimagi login
- `/agents` — First-class AI agents list (e.g. "Echo")
- `/agents/:slug` — Agent workspace: a full-bleed rail + scrolling main built on `@canopy/workbench`. Sub-routes (rail): **Needs you** (the default landing — a typed/ranked supervisor inbox), Overview, Tasks (the "who has the ball" board), Syncs, Work products, Skills
- `/sessions` — My shared Claude Code sessions (transcripts uploaded via `/canopy:share-session`)
- `/share/:token` — Public, chrome-less read-only viewer for a shared session (no login; mounted outside the app shell)
- `/settings` — AI backend status, switch backends, headless Claude CLI auth, debug-session minting
- `/api/` — REST API
- `/admin/` — Django admin
- `/health/` — Health check

## API Endpoints

All endpoints are served by Django Ninja (Pydantic v2 typed) under `/api/`. Errors use RFC 7807 `application/problem+json`. The machine-readable schema lives at `/api/openapi.json`; browse at `/api/docs/` (Scalar) or `/api/redoc/`.

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

### Collections
- `POST /api/collections/` — Create collection
- `GET /api/collections/{id}/` — Get collection with sources
- `POST /api/collections/{id}/sources/` — Add source

### Workspace
- `GET /api/workspace/` — List workspace sessions (filter: ?status=proposed, ?collection=id, ?limit=50)
- `POST /api/workspace/start/{collection_id}/` — Start workspace (SSE stream)
- `POST /api/workspace/analyze/{collection_id}/` — Run AI analysis to propose approach + eval
- `GET /api/workspace/{session_id}/` — Get workspace state
- `PATCH /api/workspace/{session_id}/edit/` — Edit skill draft
- `POST /api/workspace/{session_id}/publish/` — Publish skill

### Skills
- `GET /api/skills/` — List skills
- `GET /api/skills/{id}/` — Skill detail
- `POST /api/skills/{id}/adapter/` — Generate runtime adapter

### Evals
- `GET /api/evals/{skill_id}/` — Eval suite detail
- `POST /api/evals/{skill_id}/run/` — Run eval
- `GET /api/evals/{skill_id}/history/` — Eval history
- `POST /api/evals/{skill_id}/cases/` — Add eval case
- `PATCH /api/evals/{skill_id}/cases/{case_id}/` — Edit / remove eval case

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
- `GET /w/<uuid>/content` — Streams file bytes. Session-auth OR `visibility=link` (tokenless — anyone with the URL; the UUID is the only secret). Range-aware (supports `<video>` scrubbing)

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
An `Agent` (e.g. "Echo") is a first-class entity — distinct from a code Project — with its own Google-Doc syncs, work products, skill catalog, and an actionable task board. The **DB is the source of truth**; the board renders by "who has the ball" (the agent vs a human). A human's board action POSTs a *command*; the agent drains pending commands on its next turn and marks them applied (`result_note` + `applied_at`). All routes are session-authed and `x-mcp-expose`d.
- `GET /api/agents/` — List agents
- `POST /api/agents/` — Create or update an agent (upsert by slug)
- `GET /api/agents/{slug}/` — Agent detail (with counts)
- `GET /api/agents/{slug}/needs-you` — Typed/ranked supervisor inbox (`review` → `question` → `notify`) + a `waiting_count` badge — "what does the agent need from me right now?"
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

### Sessions (`apps/sessions`) — shared Claude Code transcripts
Token-based session sharing (the `/canopy:share-session` flow). Note this is a **separate** token model from the tokenless walkthrough/review visibility above — shared sessions carry a rotatable `share_token`.
- `POST /api/sessions/upload` — Upload a Claude `.jsonl` transcript (multipart)
- `GET /api/sessions/` — List my shared sessions
- `GET /api/sessions/{slug}` — Get one session (owner)
- `PATCH /api/sessions/{slug}` — Update a session (owner)
- `DELETE /api/sessions/{slug}` — Delete a session (owner)
- `POST /api/sessions/{slug}/rotate-token` — Rotate the share token (owner) — invalidates the old `/share/<token>` link
- `GET /api/share/{token}` — Public read-only view of a shared session (no login; `share_router` mounted at `/api/share`, drives `/share/:token`)

### MCP (`apps/mcp`, mounted at `/api/mcp/`)
Not a Ninja router — a FastMCP 3.x Streamable-HTTP ASGI app mounted in `config/asgi.py`. Auth is enforced inside the server via `MultiAuth` (per-user PAT `CanopyPATVerifier`, always on; interactive Google OAuth is an env-gated seam, `MCP_OAUTH_ENABLED`). Every tool call writes an `MCPAuditLog` row; mutating tools are rate-limited per user. Tools today: `list_insights` (read) + `clear_insights` (write). The legacy single-shared `CANOPY_MCP_BEARER` and the hand-rolled ASGI gate are gone. See `docs/architecture/mcp-surface.md`.

## Design Decisions

- **API is Pydantic-first via Django Ninja**: every request/response is a Pydantic v2 model declared in `apps/<app>/schemas.py`. Routes live in `apps/<app>/api.py`, registered on the single `NinjaAPI` instance in `apps/api/api.py`. Errors are RFC 7807 `application/problem+json`. Frontend types are generated from the OpenAPI 3.1 schema by `openapi-typescript` into `frontend/src/api/generated.ts` and consumed via `openapi-fetch`. The `regen-openapi.yml` GitHub workflow auto-commits regenerated types on PRs touching `apps/**/api.py` or `apps/**/schemas.py`.
- **Streaming endpoints stay on Django**: `POST /api/workspace/start/<id>/` returns `StreamingHttpResponse` directly from a Ninja handler (declared as `response=None`); the SSE event format is the contract. `GET /w/<uuid>/content` (the walkthrough viewer) stays as a bare Django view at `apps/walkthroughs/streaming.py` — HTTP Range support (for `<video>` scrubbing) doesn't fit the Ninja contract.
- **Bare Django views**: `/api/csrf/`, `/api/debug/mint-session/`, `/auth/cli/authorize/`, and `/health/` (the last is also Ninja-mountable via `public_router`) — they manipulate sessions/cookies/redirects directly. Matched in `config/urls.py` BEFORE the Ninja `/api/` catch-all so they don't get shadowed.
- **MCP is in-process FastMCP, not OpenAPI-derived**: `apps/mcp/` mounts a FastMCP 3.x Streamable-HTTP server at `/api/mcp/` whose tools are explicit Python functions calling the same service layer as the REST views (no HTTP self-loopback). Auth is per-user PAT inside the server (fail-closed), every call is audited, and writes are rate-limited.
- **Visibility is tokenless Public/Private:** `visibility=link` means "anyone with the URL" (the UUID is the only secret) for walkthroughs + reviews; `private` is Dimagi-OAuth-gated and 404s to anonymous. Walkthrough content/detail and review *read* are public when `link`; review *submit* and all mutations require auth. The login middleware allowlists the `/w/` shell + walkthrough detail GET (alongside the review-link allowlist). The narrative-level toggle (`PATCH /api/ddd/narratives/{slug}/visibility/`) cascades to every artifact + review under a narrative; the dormant `share_token` column is retained for reversibility. See `docs/superpowers/specs/2026-06-08-tokenless-narrative-visibility-design.md`.
- **Shared Workbench shell:** the DDD and Agent workspaces share a two-pane (left rail + scrolling main) shell extracted to `frontend/packages/workbench` (`@canopy/workbench`, published to GitHub Packages). Surfaces consume it instead of re-implementing chrome, and use semantic design tokens (`bg-card` / `border-border` / `text-foreground` / `text-muted-foreground` / `text-primary`) — not raw `stone-*`/`orange-*` palette literals. See `docs/superpowers/specs/2026-06-17-shared-workbench-package-design.md`.
- APP UI: dense, readable, tables not cards
- Workspace flow: Ingest → AI proposes Approach + Eval → Review/Edit → Test → Publish
- SSE streaming for AI responses (Scout pattern)
- Overwrite-with-history versioning
- **Auth:** Google OAuth via django-allauth (allowed-domain restricted via `AUTH_ALLOWED_EMAIL_DOMAIN` — comma-separated list, default `dimagi.com`). Personal Access Tokens (`apps/tokens/`) authenticate machine callers via `Authorization: Bearer <raw>` — `BearerTokenAuthMiddleware` resolves them upstream of `LoginRequiredMiddleware`. `/api/debug/mint-session/` lets an authenticated user mint a short-lived session cookie to hand to an AI assistant. Single-tenant in V1; multi-tenant scaffolding tracked in `TODOS.md`.
- PostgreSQL on Cloud SQL (GCP `canopy-494811`)
- Dual AI backend lets users run either against an API key or their own Claude Code subscription

## Reference Docs

- `docs/architecture/mcp-surface.md` — MCP server surface: module layout, dual-auth model, audit + rate-limit, tool inventory
- `docs/superpowers/plans/2026-04-13-portfolio-insights.md` — Cross-portfolio insights feed plan (shipped; historical)
- `docs/superpowers/plans/2026-05-26-api-modernization.md` — Django Ninja + Pydantic + OpenAPI migration plan (shipped; DRF retired, FastMCP layer)
- `docs/superpowers/specs/2026-04-10-project-workbench-design.md` — Workbench design spec
- `docs/superpowers/specs/2026-04-14-google-oauth-auth-gate-design.md` — OAuth gate design spec
- `docs/superpowers/specs/2026-05-26-walkthrough-sharing-design.md` — Walkthrough sharing design spec
- `docs/superpowers/specs/2026-06-02-ddd-run-views-design.md` — DDD run views (narrative → run → package) design spec
- `docs/superpowers/specs/2026-06-03-ddd-narrative-run-versioning-design.md` — DDD narrative/version/run model design spec
- `docs/superpowers/specs/2026-06-08-tokenless-narrative-visibility-design.md` — Tokenless Public/Private + narrative-level visibility design spec (shipped, PR #105)
- `docs/superpowers/plans/2026-06-09-tokenless-narrative-visibility.md` — Tokenless visibility implementation plan (shipped, PR #105)
- `docs/superpowers/specs/2026-06-17-shared-workbench-package-design.md` — `@canopy/workbench` shared Workbench shell design (shipped, PRs #123/#124)
- `docs/superpowers/plans/2026-06-17-shared-workbench-package.md` — `@canopy/workbench` extraction + migration plan (shipped, PRs #123/#124)
- `docs/designs/canopy-web-design.md` — Product design + glossary (open claw, skill, collection, eval suite, workspace session)
- `docs/designs/ceo-plan-conversation-to-agent.md` — CEO review, scope decisions, deferred work
- `docs/walkthroughs/canopy-web-demo.yaml` — Walkthrough QA spec (5 skills, varied scores)
- `docs/walkthroughs/project-workbench.yaml` — Project workbench walkthrough spec
- `docs/case-studies/workbench-self-improvement.md` — Self-improvement case study
- `docs/personas/jonathan.md` — Primary user persona
- `TODOS.md` — Deferred V2 work (proactive detection, prompt hardening, OAuth integrations, multi-tenant auth, cowork adapter)
