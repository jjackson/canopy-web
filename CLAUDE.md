# Canopy Web

Collaborative web workspace for building reusable AI skills from conversations.

## Architecture

- **Backend:** Django 5 ASGI + uvicorn, PostgreSQL
- **Frontend:** React 19 + Vite + Tailwind CSS 4 + shadcn/ui
- **AI:** Anthropic Claude API via SSE streaming. Dual backend — direct API key (`AI_BACKEND=api`) or Claude Code CLI subscription (`AI_BACKEND=cli`), switchable at runtime via `/api/ai/switch/`.
- **Runtime adapters:** `apps/skills/adapters/` produces skill artifacts for `web`, `claude_code`, and `open_claw` runtimes.
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
./deploy.sh                  # Cloud Build → push → gcloud run deploy
SKIP_TESTS=1 ./deploy.sh     # bypass test gate (emergencies only)
```

When `AI_BACKEND=cli`, the `claude` binary must be on PATH and authenticated. In Docker, use the headless auth flow at `/settings` (drives `claude setup-token` via PTY; token persists in `CLAUDE_CODE_OAUTH_TOKEN`).

## Testing

```bash
uv run pytest                                    # All backend tests
uv run pytest tests/test_workspace_engine.py -v  # Specific
cd frontend && npm run build                     # Frontend type check + build
```

CI (`.github/workflows/ci.yml`) runs both on every PR and on push to main. Deploy is a separate manual job in the same workflow — trigger it from the Actions tab via "Run workflow"; the deploy step waits for the test jobs to pass before shipping. Walkthrough QA spec at `docs/walkthroughs/canopy-web-demo.yaml` (run via `/walkthrough canopy-web-demo`).

## Key URLs

- `/` — Project workbench. Tile grid dashboard with a "Today's top 3" insight hero, freshness chip, inline insights triage, and self-prioritizing tile order by insight count.
- `/skills` — Skill discovery feed
- `/workspaces` — Workspace session list (resume in-progress sessions)
- `/new` — New collection / source ingestion flow
- `/workspace/:sessionId` — Co-authoring workspace
- `/skills/:skillId` — Skill detail + eval history
- `/leaderboard` — Eval improvement leaderboard
- `/guide` — Interactive walkthrough using a "Discovery Call Debrief" sample collection (try-it / how-it-works / review / eval / deploy sections)
- `/insights` — Cross-portfolio AI insights feed
- `/settings` — AI backend status, switch backends, headless Claude CLI auth, debug-session minting
- `/api/` — REST API
- `/admin/` — Django admin
- `/health/` — Health check

## API Endpoints

### Auth + session (root)
- `GET /api/me/` — Current authenticated user
- `GET /api/csrf/` — CSRF token bootstrap

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

### Automated-tool login (`apps/common/views_auth_e2e`)
- `POST /api/auth/e2e-login/` — token-gated login for automated tools (gstack walkthroughs, autonomous PM cycles, AI-driven QA). Body: `{email, token}`. Disabled by default — returns 404 unless `CANOPY_E2E_AUTH_TOKEN` is set. Email must be in `AUTH_ALLOWED_EMAIL_DOMAIN`. Sessions carry `_canopy_e2e_session` marker for audit. See `docs/e2e-login.md`.

### Debug access (`apps/common/views_debug`)
- `POST /api/debug/mint-session/` — authenticated user mints a short-lived Django session cookie (body: `{ttl_seconds: int}`, clamped to 60s–1w). Returns cookie + curl example. Used to hand access to an AI assistant without going through OAuth. UI lives at `/settings` → "Debug access".

## Design Decisions

- APP UI: dense, readable, tables not cards
- Workspace flow: Ingest → AI proposes Approach + Eval → Review/Edit → Test → Publish
- SSE streaming for AI responses (Scout pattern)
- Overwrite-with-history versioning
- **Auth:** Google OAuth via django-allauth (allowed-domain restricted via `AUTH_ALLOWED_EMAIL_DOMAIN`, default `dimagi.com`). `LoginRequiredMiddleware` enforces auth at the app layer. Two automation bypasses: `/api/auth/e2e-login/` (token-gated, for headless tools) and `/api/debug/mint-session/` (authenticated user mints a short-lived cookie for an AI assistant). Single-tenant in V1; multi-tenant scaffolding tracked in `TODOS.md`.
- PostgreSQL on Cloud SQL (GCP `canopy-494811`)
- Dual AI backend lets users run either against an API key or their own Claude Code subscription

## Reference Docs

- `docs/superpowers/plans/2026-03-27-canopy-web-implementation.md` — Original implementation plan and file structure
- `docs/superpowers/plans/2026-04-10-project-workbench.md` — Project workbench dashboard plan
- `docs/superpowers/plans/2026-04-13-portfolio-insights.md` — Cross-portfolio insights feed plan
- `docs/superpowers/specs/2026-04-10-project-workbench-design.md` — Workbench design spec
- `docs/superpowers/specs/2026-04-14-google-oauth-auth-gate-design.md` — OAuth gate design spec
- `docs/designs/canopy-web-design.md` — Product design + glossary (open claw, skill, collection, eval suite, workspace session)
- `docs/designs/ceo-plan-conversation-to-agent.md` — CEO review, scope decisions, deferred work
- `docs/walkthroughs/canopy-web-demo.yaml` — Walkthrough QA spec (5 skills, varied scores)
- `docs/walkthroughs/project-workbench.yaml` — Project workbench walkthrough spec
- `docs/case-studies/workbench-self-improvement.md` — Self-improvement case study
- `docs/personas/jonathan.md` — Primary user persona
- `docs/e2e-login.md` — Token-gated automation login (`/api/auth/e2e-login/`) usage and contract
- `TODOS.md` — Deferred V2 work (proactive detection, MCP layer, prompt hardening, OAuth integrations, multi-tenant auth, cowork adapter)
